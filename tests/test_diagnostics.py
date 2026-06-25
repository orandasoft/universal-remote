"""Tests for Universal Remote diagnostics."""

from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DOMAIN,
)
from custom_components.universal_remote.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.universal_remote.infrared_library import NO_INFRARED_LIBRARY_CODESET
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
        "device_type": DEVICE_TYPE_GENERIC,
        "codeset": NO_INFRARED_LIBRARY_CODESET,
        "media_player_expected": False,
        "button_count": 0,
        "source_count": 0,
        "command_count": 1,
        "commands": ["POWER_ON"],
    }
