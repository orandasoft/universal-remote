"""Tests for stable codeset definitions and bindings."""

from __future__ import annotations

from typing import cast

import pytest

from custom_components.universal_remote.codesets import (
    CODESET_REGISTRY,
    LG_TV_JP_CODESET,
    CodesetDefinition,
    CodesetRegistryError,
    build_codeset_registry,
)
from custom_components.universal_remote.const import DEVICE_TYPE_TV
from custom_components.universal_remote.profiles import (
    CAPABILITY_JAPANESE_TUNER,
    JAPANESE_TUNER_CAPABILITY,
    TV_PROFILE,
    DeviceProfile,
    ProfileCapability,
    build_profile_registry,
)


def _definition(
    codeset_id: str,
    *,
    profile_id: str = DEVICE_TYPE_TV,
    decoder_family_id: str | None = None,
    capabilities: tuple[str, ...] = (),
) -> CodesetDefinition:
    """Return one focused codeset definition."""
    return CodesetDefinition(
        codeset_id=codeset_id,
        label="Test codeset",
        module="test.module",
        enum_class="TestCode",
        profile_id=profile_id,
        decoder_family_id=decoder_family_id,
        capabilities=capabilities,
    )


def test_production_codeset_registry_is_deterministic() -> None:
    """Test production codesets retain explicit order and bindings."""
    assert tuple(CODESET_REGISTRY.definitions) == (
        "lg_tv",
        "lg_tv_jp",
        "samsung_tv",
        "sharp_aquos_tv",
        "vizio_tv",
    )

    assert CODESET_REGISTRY.definition_for_id("lg_tv_jp") is LG_TV_JP_CODESET
    assert CODESET_REGISTRY.definition_for_id("missing") is None
    assert CODESET_REGISTRY.resolved_for_id("missing") is None

    resolved = CODESET_REGISTRY.resolved_for_id("lg_tv_jp")
    assert resolved is not None
    assert resolved.definition is LG_TV_JP_CODESET
    assert resolved.profile is TV_PROFILE
    assert resolved.capabilities == (JAPANESE_TUNER_CAPABILITY,)

    plain_tv = CODESET_REGISTRY.resolved_for_id("lg_tv")
    assert plain_tv is not None
    assert plain_tv.profile.device_type == DEVICE_TYPE_TV
    assert plain_tv.capabilities == ()


def test_codeset_registry_merges_profile_and_codeset_capabilities() -> None:
    """Test profile capabilities precede codeset additions deterministically."""
    base_capability = ProfileCapability("base")
    extra_capability = ProfileCapability("extra")
    profile = DeviceProfile(
        profile_id="receiver",
        device_type="receiver",
        capabilities=("base",),
    )
    profile_registry = build_profile_registry(
        (profile,),
        (base_capability, extra_capability),
    )

    registry = build_codeset_registry(
        (
            _definition(
                "receiver_codeset",
                profile_id="receiver",
                capabilities=("base", "extra"),
            ),
        ),
        profile_registry=profile_registry,
    )

    resolved = registry.resolved_for_id("receiver_codeset")
    assert resolved is not None
    assert resolved.capabilities == (
        base_capability,
        extra_capability,
    )


def test_codeset_registry_mappings_are_immutable() -> None:
    """Test registry mappings cannot be modified."""
    mutable_definitions = cast(
        dict[str, CodesetDefinition],
        CODESET_REGISTRY.definitions,
    )

    with pytest.raises(TypeError):
        mutable_definitions["other"] = _definition("other")


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        (
            CodesetDefinition(
                codeset_id="",
                label="Label",
                module="module",
                enum_class="Code",
                profile_id=DEVICE_TYPE_TV,
            ),
            "Codeset codeset id must not be empty",
        ),
        (
            CodesetDefinition(
                codeset_id="empty_label",
                label="",
                module="module",
                enum_class="Code",
                profile_id=DEVICE_TYPE_TV,
            ),
            "Codeset label must not be empty",
        ),
        (
            CodesetDefinition(
                codeset_id="empty_module",
                label="Label",
                module="",
                enum_class="Code",
                profile_id=DEVICE_TYPE_TV,
            ),
            "Codeset module must not be empty",
        ),
        (
            CodesetDefinition(
                codeset_id="empty_enum",
                label="Label",
                module="module",
                enum_class="",
                profile_id=DEVICE_TYPE_TV,
            ),
            "Codeset enum class must not be empty",
        ),
        (
            CodesetDefinition(
                codeset_id="empty_profile",
                label="Label",
                module="module",
                enum_class="Code",
                profile_id="",
            ),
            "Codeset profile id must not be empty",
        ),
        (
            _definition(
                "duplicate_capabilities",
                capabilities=(
                    CAPABILITY_JAPANESE_TUNER,
                    CAPABILITY_JAPANESE_TUNER,
                ),
            ),
            ("Codeset duplicate_capabilities contains duplicate capability ids"),
        ),
    ],
)
def test_codeset_registry_rejects_invalid_definitions(
    definition: CodesetDefinition,
    message: str,
) -> None:
    """Test structurally invalid codesets are rejected."""
    with pytest.raises(CodesetRegistryError, match=message):
        build_codeset_registry((definition,))


def test_codeset_registry_rejects_duplicate_ids() -> None:
    """Test codeset IDs must be unique."""
    with pytest.raises(
        CodesetRegistryError,
        match="Duplicate codeset id: duplicate",
    ):
        build_codeset_registry(
            (
                _definition("duplicate"),
                _definition("duplicate"),
            )
        )


def test_codeset_registry_rejects_missing_profile() -> None:
    """Test profile references are validated."""
    with pytest.raises(
        CodesetRegistryError,
        match="Codeset missing_profile references missing profile: missing",
    ):
        build_codeset_registry(
            (
                _definition(
                    "missing_profile",
                    profile_id="missing",
                ),
            )
        )


def test_codeset_registry_rejects_missing_decoder_family() -> None:
    """Test decoder-family references are validated."""
    with pytest.raises(
        CodesetRegistryError,
        match=("Codeset missing_decoder references missing decoder family: missing"),
    ):
        build_codeset_registry(
            (
                _definition(
                    "missing_decoder",
                    decoder_family_id="missing",
                ),
            )
        )


def test_codeset_registry_rejects_missing_capability() -> None:
    """Test capability references are validated."""
    with pytest.raises(
        CodesetRegistryError,
        match=("Codeset missing_capability references missing capabilities: missing"),
    ):
        build_codeset_registry(
            (
                _definition(
                    "missing_capability",
                    capabilities=("missing",),
                ),
            )
        )
