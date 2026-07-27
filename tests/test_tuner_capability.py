"""Tests for tuner profile capabilities."""

from __future__ import annotations

import pytest

from custom_components.universal_remote.profiles import (
    CAPABILITY_JAPANESE_TUNER,
    JAPANESE_TUNER_CAPABILITY,
    PROFILE_REGISTRY,
    TV_PROFILE,
    DeviceProfile,
    ProfileCapability,
    ProfileRegistryError,
    TunerCapability,
    TunerRule,
    build_profile_registry,
)


def _fake_tuner_capability(
    capability_id: str = "radio_tuner",
) -> TunerCapability:
    """Return a focused non-TV tuner capability."""
    return TunerCapability(
        capability_id=capability_id,
        tuners=(
            TunerRule(
                tuner_id="FM",
                selector_candidates=("FM", "RADIO_FM"),
            ),
        ),
        numbers=(1, 2),
    )


def test_production_tuner_capability_is_registered() -> None:
    """Test the Japanese tuner capability has deterministic registration."""
    assert tuple(PROFILE_REGISTRY.capabilities) == (CAPABILITY_JAPANESE_TUNER,)
    assert (
        PROFILE_REGISTRY.capability_for_id(CAPABILITY_JAPANESE_TUNER)
        is JAPANESE_TUNER_CAPABILITY
    )
    assert PROFILE_REGISTRY.capability_for_id("missing") is None

    assert [rule.tuner_id for rule in JAPANESE_TUNER_CAPABILITY.tuners] == [
        "DTV",
        "BS",
        "CS1",
        "CS2",
        "BS4K",
        "CS4K",
    ]
    assert JAPANESE_TUNER_CAPABILITY.numbers == tuple(range(1, 13))
    assert JAPANESE_TUNER_CAPABILITY.update_after_sent_success
    assert JAPANESE_TUNER_CAPABILITY.update_after_received_match

    # Regional tuner behavior is not an unconditional base-TV capability.
    assert PROFILE_REGISTRY.capabilities_for_profile(TV_PROFILE) == ()


def test_available_tuners_require_selector_and_prefixed_number() -> None:
    """Test tuner discovery preserves current selector and keypad rules."""
    commands = {
        "dtv": "selector",
        "dtv num 1": "number",
        "BS": "selector-only",
        "CS1": "selector",
        "cs1-num-5": "number",
        "CS4K_NUM_12": "number-only",
    }

    assert JAPANESE_TUNER_CAPABILITY.available_tuners(commands) == (
        "DTV",
        "CS1",
    )
    assert (
        JAPANESE_TUNER_CAPABILITY.selector_command_name(
            "DTV",
            commands,
        )
        == "dtv"
    )
    assert (
        JAPANESE_TUNER_CAPABILITY.tuner_number_command_name(
            "DTV",
            1,
            commands,
        )
        == "dtv num 1"
    )


def test_fake_tuner_capability_resolves_aliases_and_keypad_overlay() -> None:
    """Test a non-TV tuner capability works without consumer changes."""
    capability = _fake_tuner_capability()
    commands = {
        "radio fm": "selector",
        "fm num 2": "number",
        "NUM_2": "fallback",
    }

    assert capability.available_tuners(commands) == ("FM",)
    assert capability.selector_command_name("FM", commands) == "radio fm"
    assert capability.keypad_number("num-2") == 2
    assert (
        capability.routed_keypad_command_name(
            "FM",
            "num 2",
            commands,
        )
        == "fm num 2"
    )
    assert capability.implied_tuner("radio-fm") == "FM"
    assert capability.implied_tuner("fm num 2") == "FM"


def test_tuner_capability_returns_none_for_unmatched_commands() -> None:
    """Test unsupported routing leaves generic command lookup unchanged."""
    capability = _fake_tuner_capability()
    commands = {"FM": "selector"}

    assert capability.selector_command_name("AM", commands) is None
    assert capability.tuner_number_command_name("AM", 1, commands) is None
    assert capability.tuner_number_command_name("FM", 3, commands) is None
    assert capability.keypad_number("POWER") is None
    assert (
        capability.routed_keypad_command_name(
            None,
            "NUM_1",
            commands,
        )
        is None
    )
    assert (
        capability.routed_keypad_command_name(
            "FM",
            "POWER",
            commands,
        )
        is None
    )
    assert (
        capability.routed_keypad_command_name(
            "FM",
            "NUM_1",
            commands,
        )
        is None
    )
    assert capability.implied_tuner("POWER") is None


def test_profile_registry_composes_fake_capability() -> None:
    """Test a profile can reference an explicitly registered capability."""
    capability = _fake_tuner_capability()
    profile = DeviceProfile(
        profile_id="radio",
        device_type="radio",
        capabilities=(capability.capability_id,),
    )
    registry = build_profile_registry(
        (profile,),
        (capability,),
    )

    assert registry.capability_for_id("radio_tuner") is capability
    assert registry.capabilities_for_profile(profile) == (capability,)


def test_generic_capability_contract_registers() -> None:
    """Test the base capability contract supports other capability kinds."""
    capability = ProfileCapability(capability_id="generic_capability")
    profile = DeviceProfile(
        profile_id="generic_capability_profile",
        device_type="generic_capability_device",
        capabilities=(capability.capability_id,),
    )

    registry = build_profile_registry((profile,), (capability,))

    assert registry.capabilities_for_profile(profile) == (capability,)


def test_profile_registry_rejects_duplicate_capability_ids() -> None:
    """Test capability IDs are unique."""
    with pytest.raises(
        ProfileRegistryError,
        match="Duplicate capability id: duplicate",
    ):
        build_profile_registry(
            (),
            (
                ProfileCapability("duplicate"),
                ProfileCapability("duplicate"),
            ),
        )


def test_profile_registry_rejects_empty_capability_id() -> None:
    """Test capability IDs must not be empty."""
    with pytest.raises(
        ProfileRegistryError,
        match="Capability id must not be empty",
    ):
        build_profile_registry((), (ProfileCapability(""),))


def test_profile_registry_rejects_missing_capability_reference() -> None:
    """Test profile capability references are validated."""
    profile = DeviceProfile(
        profile_id="missing_reference",
        device_type="missing_reference",
        capabilities=("missing",),
    )

    with pytest.raises(
        ProfileRegistryError,
        match=("Profile missing_reference references missing capability: missing"),
    ):
        build_profile_registry((profile,))


@pytest.mark.parametrize(
    ("capability", "message"),
    [
        (
            TunerCapability(
                capability_id="empty_tuners",
                tuners=(),
                numbers=(1,),
            ),
            "Capability empty_tuners contains no tuners",
        ),
        (
            TunerCapability(
                capability_id="duplicate_tuners",
                tuners=(
                    TunerRule("FM", ("FM",)),
                    TunerRule("FM", ("FM_ALT",)),
                ),
                numbers=(1,),
            ),
            "Capability duplicate_tuners contains duplicate tuner ids",
        ),
        (
            TunerCapability(
                capability_id="invalid_tuner",
                tuners=(TunerRule("", ("FM",)),),
                numbers=(1,),
            ),
            "Capability invalid_tuner contains an invalid tuner",
        ),
        (
            TunerCapability(
                capability_id="missing_selectors",
                tuners=(TunerRule("FM", ()),),
                numbers=(1,),
            ),
            "Capability missing_selectors contains an invalid tuner",
        ),
        (
            TunerCapability(
                capability_id="invalid_selector",
                tuners=(TunerRule("FM", ("",)),),
                numbers=(1,),
            ),
            ("Capability invalid_selector contains an invalid selector candidate"),
        ),
        (
            TunerCapability(
                capability_id="duplicate_selectors",
                tuners=(
                    TunerRule("FM", ("RADIO FM",)),
                    TunerRule("AM", ("radio-fm",)),
                ),
                numbers=(1,),
            ),
            ("Capability duplicate_selectors contains duplicate selector candidates"),
        ),
        (
            TunerCapability(
                capability_id="empty_numbers",
                tuners=(TunerRule("FM", ("FM",)),),
                numbers=(),
            ),
            "Capability empty_numbers contains no keypad numbers",
        ),
        (
            TunerCapability(
                capability_id="duplicate_numbers",
                tuners=(TunerRule("FM", ("FM",)),),
                numbers=(1, 1),
            ),
            ("Capability duplicate_numbers contains duplicate keypad numbers"),
        ),
        (
            TunerCapability(
                capability_id="invalid_number",
                tuners=(TunerRule("FM", ("FM",)),),
                numbers=(0,),
            ),
            ("Capability invalid_number contains an invalid keypad number"),
        ),
    ],
)
def test_profile_registry_rejects_invalid_tuner_capabilities(
    capability: TunerCapability,
    message: str,
) -> None:
    """Test invalid tuner declarations fail registry validation."""
    with pytest.raises(ProfileRegistryError, match=message):
        build_profile_registry((), (capability,))
