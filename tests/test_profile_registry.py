"""Tests for device-profile contracts and registration."""

from __future__ import annotations

from typing import cast

import pytest

from custom_components.universal_remote.const import (
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
)
from custom_components.universal_remote.profiles import (
    GENERIC_PROFILE,
    PROFILE_REGISTRY,
    TV_PROFILE,
    CommandPresentation,
    CommandRole,
    DeviceProfile,
    ProfileRegistryError,
    SourceRule,
    build_profile_registry,
)


def _profile(
    profile_id: str,
    *,
    device_type: str | None = None,
) -> DeviceProfile:
    """Return one minimal profile for registry tests."""
    return DeviceProfile(
        profile_id=profile_id,
        device_type=device_type or profile_id,
    )


def test_production_profile_registry_is_deterministic() -> None:
    """Test production profiles retain explicit registration order."""
    assert tuple(PROFILE_REGISTRY.profiles) == (
        DEVICE_TYPE_GENERIC,
        DEVICE_TYPE_TV,
    )
    assert PROFILE_REGISTRY.profile_for_id(DEVICE_TYPE_GENERIC) is GENERIC_PROFILE
    assert PROFILE_REGISTRY.profile_for_device_type(DEVICE_TYPE_TV) is TV_PROFILE
    assert PROFILE_REGISTRY.profile_for_id("missing") is None
    assert PROFILE_REGISTRY.profile_for_device_type("missing") is None


def test_generic_profile_has_no_device_specific_semantics() -> None:
    """Test the generic profile does not enable TV behavior."""
    assert GENERIC_PROFILE.roles == ()
    assert GENERIC_PROFILE.sources == ()
    assert GENERIC_PROFILE.capabilities == ()
    assert not GENERIC_PROFILE.supports_entity("media_player")


def test_tv_profile_preserves_role_and_source_order() -> None:
    """Test the TV profile captures current media-player semantics."""
    assert [role.role_id for role in TV_PROFILE.roles] == [
        "turn_on",
        "turn_off",
        "volume_up",
        "volume_down",
        "mute",
        "channel_up",
        "channel_down",
        "play",
        "pause",
        "stop",
    ]
    assert TV_PROFILE.role("volume_up") == CommandRole(
        "volume_up",
        ("VOLUME_UP", "VOL_UP"),
    )
    assert TV_PROFILE.role("missing") is None
    assert [source.label for source in TV_PROFILE.sources[:5]] == [
        "TV",
        "TV input",
        "DTV",
        "BS",
        "BS4K",
    ]
    assert TV_PROFILE.supports_entity("media_player")


def test_profile_presentation_overrides_are_immutable() -> None:
    """Test profile presentation data is copied and frozen."""
    overrides = {
        "SPECIAL": CommandPresentation(
            label="Special command",
            icon="mdi:star",
            category="other",
        )
    }
    profile = DeviceProfile(
        profile_id="presentation",
        device_type="presentation",
        presentation_overrides=overrides,
    )
    overrides["SPECIAL"] = CommandPresentation(label="Changed")

    assert profile.presentation("special") == CommandPresentation(
        label="Special command",
        icon="mdi:star",
        category="other",
    )
    assert profile.presentation("missing") is None

    mutable_overrides = cast(
        dict[str, CommandPresentation],
        profile.presentation_overrides,
    )
    with pytest.raises(TypeError):
        mutable_overrides["OTHER"] = CommandPresentation()


def test_fake_profile_registers_without_consumer_changes() -> None:
    """Test a fake profile can supply roles, sources and presentation."""
    fake = DeviceProfile(
        profile_id="fake",
        device_type="fake_device",
        entity_domains=frozenset({"media_player"}),
        roles=(CommandRole("activate", ("ACTIVATE", "ON")),),
        sources=(SourceRule("Aux", ("AUX", "INPUT_AUX")),),
        presentation_overrides={
            "ACTIVATE": CommandPresentation(
                label="Activate",
                icon="mdi:power",
                category="power",
            )
        },
    )
    registry = build_profile_registry((fake,))

    assert registry.profile_for_id("fake") is fake
    assert registry.profile_for_device_type("fake_device") is fake
    assert fake.role("activate") is not None
    assert fake.presentation("activate") is not None


@pytest.mark.parametrize(
    ("profiles", "message"),
    [
        (
            (_profile("duplicate"), _profile("duplicate", device_type="other")),
            "Duplicate profile id: duplicate",
        ),
        (
            (
                _profile("first", device_type="same"),
                _profile("second", device_type="same"),
            ),
            "Duplicate profile device type: same",
        ),
        (
            (
                DeviceProfile(
                    profile_id="roles",
                    device_type="roles",
                    roles=(
                        CommandRole("power", ("POWER",)),
                        CommandRole("power", ("POWER_ON",)),
                    ),
                ),
            ),
            "Profile roles contains duplicate role ids",
        ),
        (
            (
                DeviceProfile(
                    profile_id="sources",
                    device_type="sources",
                    sources=(
                        SourceRule("Input", ("INPUT",)),
                        SourceRule("Input", ("SOURCE",)),
                    ),
                ),
            ),
            "Profile sources contains duplicate source labels",
        ),
        (
            (
                DeviceProfile(
                    profile_id="capabilities",
                    device_type="capabilities",
                    capabilities=("one", "one"),
                ),
            ),
            "Profile capabilities contains duplicate capability ids",
        ),
    ],
)
def test_profile_registry_rejects_duplicate_definitions(
    profiles: tuple[DeviceProfile, ...],
    message: str,
) -> None:
    """Test duplicate profile declarations fail deterministically."""
    with pytest.raises(ProfileRegistryError, match=message):
        build_profile_registry(profiles)


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (
            DeviceProfile(profile_id="", device_type="valid"),
            "Profile id must not be empty",
        ),
        (
            DeviceProfile(profile_id="valid", device_type=""),
            "Profile valid device type must not be empty",
        ),
        (
            DeviceProfile(
                profile_id="role",
                device_type="role",
                roles=(CommandRole("", ("POWER",)),),
            ),
            "Profile role contains an invalid role",
        ),
        (
            DeviceProfile(
                profile_id="source",
                device_type="source",
                sources=(SourceRule("", ("INPUT",)),),
            ),
            "Profile source contains an invalid source",
        ),
    ],
)
def test_profile_registry_rejects_invalid_profiles(
    profile: DeviceProfile,
    message: str,
) -> None:
    """Test structurally invalid profiles are rejected."""
    with pytest.raises(ProfileRegistryError, match=message):
        build_profile_registry((profile,))
