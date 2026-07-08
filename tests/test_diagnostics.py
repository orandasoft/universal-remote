"""Tests for Universal Remote diagnostics."""

from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
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
async def test_diagnostics_supports_receiver_only_entry(
    hass: HomeAssistant,
) -> None:
    """Test diagnostics supports receiver-only universal remote entries."""
    receiver_entity_id = "infrared.test_receiver"
    hass.states.async_set(receiver_entity_id, STATE_ON)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Receiver Remote",
        data={
            CONF_REMOTE_ID: "receiver_only",
            CONF_REMOTE_NAME: "Receiver Only",
            CONF_INFRARED_RECEIVER_ID: receiver_entity_id,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options={CONF_REMOTE_COMMANDS: {"POWER": "38000:1,2"}},
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

    remote = diagnostics["universal_remote"]
    assert remote["id"] == "receiver_only"
    assert remote["name"] == "Receiver Only"
    assert remote["infrared_emitter_id"] is None
    assert remote["infrared_emitter_exists"] is False
    assert remote["infrared_emitter_available"] is False
    assert remote["infrared_receiver_id"] == receiver_entity_id
    assert remote["infrared_receiver_exists"] is True
    assert remote["infrared_receiver_available"] is True
    assert remote["receiver_event_expected"] is True
    assert remote["receiver_decoder"] == "nec"
    assert remote["receiver_codeset_supported"] is True
    assert remote["receiver_event_type_count"] >= 3
    assert remote["device_type"] == DEVICE_TYPE_TV
    assert remote["codeset"] == "lg_tv"
    assert remote["media_player_expected"] is False
    assert remote["button_count"] == 0
    assert remote["source_count"] == 0
    assert remote["command_count"] == 1
    assert remote["commands"] == ["POWER"]




async def test_diagnostics_redacts_command_payloads(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test diagnostics exposes command names but not raw infrared payloads."""
    raw_payload = "38000:1,2,3,4,5,6"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data={
            CONF_REMOTE_ID: "living_room_tv",
            CONF_REMOTE_NAME: "Living Room TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER_ON": raw_payload,
                "MUTE": {
                    CONF_COMMAND_DATA: raw_payload,
                    CONF_COMMAND_CREATE_BUTTON: True,
                },
            },
        },
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["options"][CONF_REMOTE_COMMANDS] == ["MUTE", "POWER_ON"]
    assert diagnostics["universal_remote"]["commands"] == ["MUTE", "POWER_ON"]
    assert raw_payload not in str(diagnostics)


async def test_diagnostics_redacts_learned_pronto_command_payloads(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test diagnostics redacts Pronto payloads from learned commands."""
    learned_pronto = (
        "0000 006D 0022 0002 0157 00AC 0016 0015 0016 0015 0016 0015 "
        "0016 0015 0016 0015 0016 0015 0016 0015 0016 0015 0016 0040 "
        "0016 0040 0016 0040 0016 0040 0016 0040 0016 0040 0016 0040 "
        "0016 0040 0016 0015 0016 0040 0016 0015 0016 0040 0016 0015 "
        "0016 0015 0016 0015 0016 0015 0016 0040 0016 0015 0016 0040 "
        "0016 0015 0016 0040 0016 0040 0016 0040 0016 0040 0016 05F7 "
        "0157 0055 0016 0E6C"
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Learned Remote",
        data={
            CONF_REMOTE_ID: "learned_remote",
            CONF_REMOTE_NAME: "Learned Remote",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "LEARNED_POWER": {
                    CONF_COMMAND_DATA: learned_pronto,
                    CONF_COMMAND_CREATE_BUTTON: True,
                },
            },
        },
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["options"][CONF_REMOTE_COMMANDS] == ["LEARNED_POWER"]
    assert diagnostics["universal_remote"]["commands"] == ["LEARNED_POWER"]
    assert learned_pronto not in str(diagnostics)
    assert "0000 006D" not in str(diagnostics)
    assert "0157 00AC" not in str(diagnostics)
