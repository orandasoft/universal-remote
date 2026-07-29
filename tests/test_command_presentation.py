"""Tests for capability-aware command presentation."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.universal_remote.button import (
    UniversalRemoteButton,
    async_setup_entry as async_setup_button_entry,
)
from custom_components.universal_remote.command_ui import (
    COMMAND_CATEGORY_INPUT,
    COMMAND_CATEGORY_NUMERIC,
    command_category,
    command_icon,
    command_label,
)
from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from custom_components.universal_remote.profiles import (
    CommandPresentation,
    DeviceProfile,
    ProfileCapability,
    TunerCapability,
    TunerRule,
)
from custom_components.universal_remote.resolved import ResolvedRemoteProfile
from custom_components.universal_remote.runtime import (
    UniversalRemoteData,
    UniversalRemoteRuntime,
)
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import INFRARED_EMITTER_ID, RAW_COMMAND, REMOTE_ID, REMOTE_NAME

FAKE_TUNER_CAPABILITY = TunerCapability(
    capability_id="radio_tuner",
    tuners=(TunerRule("FM", ("RADIO",)),),
    numbers=(7,),
)

FAKE_PROFILE = DeviceProfile(
    profile_id="receiver",
    device_type="receiver",
)

FAKE_RESOLVED_PROFILE = ResolvedRemoteProfile(
    profile=FAKE_PROFILE,
    codeset=None,
    capabilities=(FAKE_TUNER_CAPABILITY,),
)


def test_base_capability_has_no_command_presentation() -> None:
    """Test plain capabilities do not claim presentation semantics."""
    capability = ProfileCapability("plain")

    assert capability.presentation("RADIO") is None


@pytest.mark.parametrize(
    ("command_name", "expected"),
    [
        (
            "RADIO",
            CommandPresentation(
                label="FM",
                icon="mdi:import",
                category=COMMAND_CATEGORY_INPUT,
            ),
        ),
        (
            "FM_NUM_7",
            CommandPresentation(
                label="FM Number 7",
                category=COMMAND_CATEGORY_NUMERIC,
            ),
        ),
        ("POWER", None),
    ],
)
def test_tuner_capability_supplies_command_presentation(
    command_name: str,
    expected: CommandPresentation | None,
) -> None:
    """Test tuner presentation follows declared aliases and numbers."""
    assert FAKE_TUNER_CAPABILITY.presentation(command_name) == expected


def test_resolved_presentation_merges_profile_and_capability_fields() -> None:
    """Test profile overrides precede capability presentation fields."""
    profile = DeviceProfile(
        profile_id="receiver",
        device_type="receiver",
        presentation_overrides={
            "RADIO": CommandPresentation(label="Broadcast"),
        },
    )
    resolved = ResolvedRemoteProfile(
        profile=profile,
        codeset=None,
        capabilities=(FAKE_TUNER_CAPABILITY,),
    )

    assert resolved.presentation("RADIO") == CommandPresentation(
        label="Broadcast",
        icon="mdi:import",
        category=COMMAND_CATEGORY_INPUT,
    )
    assert resolved.presentation("UNKNOWN") is None


@pytest.mark.parametrize(
    ("command_name", "label", "icon", "category"),
    [
        (
            "RADIO",
            "FM",
            "mdi:import",
            COMMAND_CATEGORY_INPUT,
        ),
        (
            "FM_NUM_7",
            "FM Number 7",
            "mdi:numeric-7",
            COMMAND_CATEGORY_NUMERIC,
        ),
    ],
)
def test_command_ui_uses_resolved_capability_presentation(
    command_name: str,
    label: str,
    icon: str,
    category: str,
) -> None:
    """Test command UI consumes the resolved semantic model."""
    assert (
        command_label(
            command_name,
            resolved_profile=FAKE_RESOLVED_PROFILE,
        )
        == label
    )
    assert (
        command_icon(
            command_name,
            resolved_profile=FAKE_RESOLVED_PROFILE,
        )
        == icon
    )
    assert (
        command_category(
            command_name,
            resolved_profile=FAKE_RESOLVED_PROFILE,
        )
        == category
    )


def test_context_free_prefixed_number_presentation_remains_supported() -> None:
    """Test public command helpers retain generic prefixed-number behavior."""
    assert command_label("SATELLITE_NUM_11") == "Satellite Number 11"
    assert command_icon("SATELLITE_NUM_11") == "mdi:numeric"
    assert command_category("SATELLITE_NUM_11") == COMMAND_CATEGORY_NUMERIC


async def test_button_setup_uses_resolved_capability_presentation(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test command buttons consume resolved capability presentation."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "RADIO": {
                    CONF_COMMAND_DATA: RAW_COMMAND,
                    CONF_COMMAND_CREATE_BUTTON: True,
                },
            },
        },
        unique_id="radio_remote",
    )
    entry.runtime_data = UniversalRemoteData(
        runtime=UniversalRemoteRuntime(
            hass=hass,
            infrared_emitter_id=INFRARED_EMITTER_ID,
            commands={"RADIO": RAW_COMMAND},
            tuner_capability=FAKE_TUNER_CAPABILITY,
        ),
        resolved_profile=FAKE_RESOLVED_PROFILE,
    )
    entry.add_to_hass(hass)
    async_add_entities = Mock()

    await async_setup_button_entry(
        hass,
        entry,
        async_add_entities,
    )

    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args.args[0]
    assert len(entities) == 1

    entity = entities[0]
    assert isinstance(entity, UniversalRemoteButton)
    assert entity.entity_description.name == "FM"
    assert entity.entity_description.icon == "mdi:import"
