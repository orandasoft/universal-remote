"""Tests for Universal Remote diagnostics."""

from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.universal_remote.infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_diagnostics_supports_single_entry_remote(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test diagnostics supports one universal remote per config entry storage."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TV",
        data={
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={CONF_REMOTE_COMMANDS: {"POWER_ON": "38000:1,2"}},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["summary"] == {
        "remote_count": 1,
        "command_count": 1,
        "button_count": 0,
        "media_player_count": 0,
        "missing_infrared_emitter_count": 0,
        "missing_infrared_receiver_count": 0,
    }
    assert diagnostics["universal_remote"] == {
        "id": "tv",
        "name": "TV",
        "infrared_emitter_id": infrared_emitter,
        "infrared_emitter_exists": True,
        "infrared_emitter_available": True,
        "infrared_receiver_id": None,
        "infrared_receiver_exists": False,
        "infrared_receiver_available": False,
        "receiver_event_expected": False,
        "receiver_decoder": None,
        "receiver_codeset_supported": False,
        "receiver_event_type_count": 0,
        "device_type": DEVICE_TYPE_GENERIC,
        "codeset": NO_INFRARED_LIBRARY_CODESET,
        "media_player_expected": False,
        "button_count": 0,
        "source_count": 0,
        "command_count": 1,
        "commands": ["POWER_ON"],
    }


async def test_diagnostics_reports_receiver_event_metadata(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test diagnostics includes receiver event metadata for supported codesets."""
    receiver_entity_id = "infrared.test_receiver"
    hass.states.async_set(receiver_entity_id, STATE_ON)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="LG TV",
        data={
            CONF_REMOTE_ID: "lg_tv",
            CONF_REMOTE_NAME: "LG TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_INFRARED_RECEIVER_ID: receiver_entity_id,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options={CONF_REMOTE_COMMANDS: {"POWER": "38000:1,2"}},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    remote = diagnostics["universal_remote"]

    assert remote["infrared_receiver_id"] == receiver_entity_id
    assert remote["infrared_receiver_exists"] is True
    assert remote["infrared_receiver_available"] is True
    assert remote["receiver_event_expected"] is True
    assert remote["receiver_decoder"] == "nec"
    assert remote["receiver_codeset_supported"] is True
    assert remote["receiver_event_type_count"] >= 3
