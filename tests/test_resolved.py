"""Tests for setup-time remote-profile resolution."""

from __future__ import annotations

from typing import cast

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.commands import Command

from custom_components.universal_remote.codesets import (
    CODESET_REGISTRY,
    LG_TV_JP_CODESET,
    CodesetDefinition,
    build_codeset_registry,
)
from custom_components.universal_remote.const import (
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
)
from custom_components.universal_remote.profiles import (
    CAPABILITY_JAPANESE_TUNER,
    GENERIC_PROFILE,
    JAPANESE_TUNER_CAPABILITY,
    TV_PROFILE,
    DeviceProfile,
    ProfileCapability,
    build_profile_registry,
)
from custom_components.universal_remote.protocols.base import (
    CommandMatchKey,
    NormalizedInfraredCommand,
    ProtocolDecodeResult,
    ReceiveProtocolHandler,
)
from custom_components.universal_remote.resolved import (
    ResolvedReceiverModel,
    resolve_remote_profile,
)


def _fake_handler() -> ReceiveProtocolHandler:
    """Return a minimal fake receive handler."""

    def decode(_signal: InfraredReceivedSignal) -> ProtocolDecodeResult | None:
        return None

    def normalize(_command: Command) -> NormalizedInfraredCommand | None:
        return None

    return ReceiveProtocolHandler(
        protocol_id="fake",
        label_key="fake",
        learning_confidence=1,
        decode=decode,
        normalize=normalize,
    )


def test_resolved_receiver_model_freezes_match_maps() -> None:
    """Test receive-side match maps are copied and immutable."""
    match_key: CommandMatchKey = ("fake", "device", 1)
    source_map: dict[CommandMatchKey, str] = {match_key: "POWER"}
    model = ResolvedReceiverModel(
        codeset_id="fake_codeset",
        decoder_family_id="fake_family",
        handlers=(_fake_handler(),),
        match_maps={"fake": source_map},
        event_types=("fake", "power", "unknown"),
    )

    source_map[match_key] = "MUTE"

    assert model.match_map_for_protocol("fake")[match_key] == "POWER"
    assert model.match_map_for_protocol("missing") == {}
    with pytest.raises(TypeError):
        cast(dict[CommandMatchKey, str], model.match_maps["fake"])[match_key] = "MUTE"


@pytest.mark.parametrize(
    ("device_type", "expected_profile"),
    [
        (DEVICE_TYPE_GENERIC, GENERIC_PROFILE),
        (DEVICE_TYPE_TV, TV_PROFILE),
    ],
)
def test_manual_remote_resolves_from_device_type(
    device_type: str,
    expected_profile: DeviceProfile,
) -> None:
    """Test a manual remote resolves without a codeset."""
    resolved = resolve_remote_profile(device_type)

    assert resolved is not None
    assert resolved.profile is expected_profile
    assert resolved.codeset is None
    assert resolved.capabilities == ()


def test_lg_tv_jp_resolves_regional_tuner_capability() -> None:
    """Test LG TV Japan resolves its regional tuner capability."""
    resolved = resolve_remote_profile(
        DEVICE_TYPE_TV,
        "lg_tv_jp",
    )

    assert resolved is not None
    assert resolved.profile is TV_PROFILE
    assert resolved.codeset is LG_TV_JP_CODESET
    assert resolved.capabilities == (JAPANESE_TUNER_CAPABILITY,)
    assert (
        resolved.capability_for_id(CAPABILITY_JAPANESE_TUNER)
        is JAPANESE_TUNER_CAPABILITY
    )
    assert resolved.capability_for_id("missing") is None


@pytest.mark.parametrize(
    "codeset_id",
    [
        "lg_tv",
        "samsung_tv",
        "sharp_aquos_tv",
        "vizio_tv",
    ],
)
def test_other_tv_codesets_do_not_resolve_japanese_tuner(
    codeset_id: str,
) -> None:
    """Test ordinary TV codesets do not receive Japanese tuner behavior."""
    resolved = resolve_remote_profile(
        DEVICE_TYPE_TV,
        codeset_id,
    )

    assert resolved is not None
    assert resolved.profile is TV_PROFILE
    assert resolved.codeset is CODESET_REGISTRY.definition_for_id(codeset_id)
    assert resolved.capabilities == ()


@pytest.mark.parametrize(
    "device_type",
    [
        DEVICE_TYPE_GENERIC,
        "missing",
        None,
    ],
)
def test_codeset_infers_profile_from_generic_or_invalid_type(
    device_type: str | None,
) -> None:
    """Test a valid codeset infers its bound profile."""
    resolved = resolve_remote_profile(
        device_type,
        "lg_tv_jp",
    )

    assert resolved is not None
    assert resolved.profile is TV_PROFILE
    assert resolved.codeset is LG_TV_JP_CODESET
    assert resolved.capabilities == (JAPANESE_TUNER_CAPABILITY,)


def test_stale_codeset_is_ignored() -> None:
    """Test an unknown codeset preserves the stored profile."""
    resolved = resolve_remote_profile(
        DEVICE_TYPE_TV,
        "missing",
    )

    assert resolved is not None
    assert resolved.profile is TV_PROFILE
    assert resolved.codeset is None
    assert resolved.capabilities == ()


def test_invalid_profile_and_stale_codeset_fall_back_to_generic() -> None:
    """Test completely stale semantics fall back to generic."""
    resolved = resolve_remote_profile(
        "missing",
        "missing",
    )

    assert resolved is not None
    assert resolved.profile is GENERIC_PROFILE
    assert resolved.codeset is None
    assert resolved.capabilities == ()


def test_conflicting_explicit_profile_discards_codeset() -> None:
    """Test an explicit non-generic profile wins over a conflicting codeset."""
    base_capability = ProfileCapability("base")
    extra_capability = ProfileCapability("extra")

    generic_profile = DeviceProfile(
        profile_id="generic",
        device_type=DEVICE_TYPE_GENERIC,
    )
    tv_profile = DeviceProfile(
        profile_id="tv",
        device_type=DEVICE_TYPE_TV,
    )
    receiver_profile = DeviceProfile(
        profile_id="receiver",
        device_type="receiver",
        capabilities=("base",),
    )

    profile_registry = build_profile_registry(
        (
            generic_profile,
            tv_profile,
            receiver_profile,
        ),
        (
            base_capability,
            extra_capability,
        ),
    )
    codeset_registry = build_codeset_registry(
        (
            CodesetDefinition(
                codeset_id="receiver_codeset",
                label="Receiver",
                module="test.module",
                enum_class="ReceiverCode",
                profile_id="receiver",
                capabilities=("base", "extra"),
            ),
        ),
        profile_registry=profile_registry,
    )

    resolved = resolve_remote_profile(
        DEVICE_TYPE_TV,
        "receiver_codeset",
        profile_registry=profile_registry,
        codeset_registry=codeset_registry,
    )

    assert resolved is not None
    assert resolved.profile is tv_profile
    assert resolved.codeset is None
    assert resolved.capabilities == ()


def test_codeset_capabilities_augment_profile_without_duplicates() -> None:
    """Test resolved capabilities preserve profile-first deterministic order."""
    base_capability = ProfileCapability("base")
    extra_capability = ProfileCapability("extra")

    generic_profile = DeviceProfile(
        profile_id="generic",
        device_type=DEVICE_TYPE_GENERIC,
    )
    receiver_profile = DeviceProfile(
        profile_id="receiver",
        device_type="receiver",
        capabilities=("base",),
    )

    profile_registry = build_profile_registry(
        (
            generic_profile,
            receiver_profile,
        ),
        (
            base_capability,
            extra_capability,
        ),
    )
    codeset_registry = build_codeset_registry(
        (
            CodesetDefinition(
                codeset_id="receiver_codeset",
                label="Receiver",
                module="test.module",
                enum_class="ReceiverCode",
                profile_id="receiver",
                capabilities=("base", "extra"),
            ),
        ),
        profile_registry=profile_registry,
    )

    resolved = resolve_remote_profile(
        DEVICE_TYPE_GENERIC,
        "receiver_codeset",
        profile_registry=profile_registry,
        codeset_registry=codeset_registry,
    )

    assert resolved is not None
    assert resolved.profile is receiver_profile
    assert resolved.codeset is not None
    assert resolved.codeset.codeset_id == "receiver_codeset"
    assert resolved.capabilities == (
        base_capability,
        extra_capability,
    )


def test_missing_generic_fallback_returns_none() -> None:
    """Test a custom registry without an applicable fallback returns none."""
    tv_profile = DeviceProfile(
        profile_id="tv",
        device_type=DEVICE_TYPE_TV,
    )
    profile_registry = build_profile_registry((tv_profile,))
    codeset_registry = build_codeset_registry(
        (),
        profile_registry=profile_registry,
    )

    assert (
        resolve_remote_profile(
            "missing",
            "missing",
            profile_registry=profile_registry,
            codeset_registry=codeset_registry,
        )
        is None
    )
