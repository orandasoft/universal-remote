"""Tests for Universal Remote diagnostics."""

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest

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
    TV_SOURCE_COMMAND_MAP,
)
from custom_components.universal_remote.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.universal_remote.infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
)
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def mock_available_infrared_receivers() -> Generator[Mock, None, None]:
    """Mock selectable infrared receivers for diagnostics tests."""
    with patch(
        "custom_components.universal_remote.diagnostics.available_infrared_receivers",
        return_value={},
    ) as mock_receivers:
        yield mock_receivers


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
        "learning": {
            "receiver_configured": False,
            "receiver_available": False,
            "selectable_receiver_count": 0,
            "configured_receiver_selectable": False,
            "alternative_receiver_available": False,
            "emitter_configured": True,
            "emitter_available": True,
            "available_decoders": ["nec", "nec1_f16"],
            "learn_command_available": False,
        },
    }


async def test_diagnostics_reports_receiver_event_metadata(
    hass: HomeAssistant,
    infrared_emitter: str,
    mock_available_infrared_receivers: Mock,
) -> None:
    """Test diagnostics includes receiver event metadata for supported codesets."""
    receiver_entity_id = "infrared.test_receiver"
    hass.states.async_set(receiver_entity_id, STATE_ON)
    mock_available_infrared_receivers.return_value = {
        receiver_entity_id: {
            "value": receiver_entity_id,
            "label": "Test Receiver",
        }
    }
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
    mock_available_infrared_receivers: Mock,
) -> None:
    """Test diagnostics supports receiver-only universal remote entries."""
    receiver_entity_id = "infrared.test_receiver"
    hass.states.async_set(receiver_entity_id, STATE_ON)
    mock_available_infrared_receivers.return_value = {
        receiver_entity_id: {
            "value": receiver_entity_id,
            "label": "Test Receiver",
        }
    }

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
    assert remote["learning"] == {
        "receiver_configured": True,
        "receiver_available": True,
        "selectable_receiver_count": 1,
        "configured_receiver_selectable": True,
        "alternative_receiver_available": False,
        "emitter_configured": False,
        "emitter_available": False,
        "available_decoders": ["nec", "nec1_f16"],
        "learn_command_available": True,
    }


async def test_diagnostics_source_count_matches_tv_source_map(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test diagnostics counts every source exposed by the TV source map."""
    source_commands = {
        command_name: "38000:1,2" for command_name in TV_SOURCE_COMMAND_MAP.values()
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TV Sources",
        data={
            CONF_REMOTE_ID: "tv_sources",
            CONF_REMOTE_NAME: "TV Sources",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                **source_commands,
                "POWER_ON": "38000:1,2",
            }
        },
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["universal_remote"]["source_count"] == len(TV_SOURCE_COMMAND_MAP)


async def test_diagnostics_source_count_uses_normalized_source_lookup(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test diagnostics and media-player source matching use the same rules."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Normalized TV Sources",
        data={
            CONF_REMOTE_ID: "normalized_tv_sources",
            CONF_REMOTE_NAME: "Normalized TV Sources",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "hdmi 1": "38000:1,2",
                "amazon-prime": "38000:1,2",
                "VOLUME_UP": "38000:1,2",
            }
        },
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["universal_remote"]["source_count"] == 2


async def test_diagnostics_redacts_commands_from_entry_data(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test command payloads are redacted from legacy config-entry data."""
    raw_payload = "38000:1,2,3,4,5,6"
    learned_pronto = "0000 006D 0002 0000 0152 00AA 0014 0017"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Legacy Commands",
        data={
            CONF_REMOTE_ID: "legacy_commands",
            CONF_REMOTE_NAME: "Legacy Commands",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_COMMANDS: {
                "RAW": raw_payload,
                "LEARNED": {
                    CONF_COMMAND_DATA: learned_pronto,
                    CONF_COMMAND_CREATE_BUTTON: True,
                },
            },
        },
        options={},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"][CONF_REMOTE_COMMANDS] == [
        "LEARNED",
        "RAW",
    ]
    assert diagnostics["universal_remote"]["commands"] == ["LEARNED", "RAW"]
    assert raw_payload not in str(diagnostics)
    assert learned_pronto not in str(diagnostics)


async def test_diagnostics_redacts_malformed_command_storage(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test malformed command storage is redacted rather than exposed."""
    raw_payload = "38000:9,8,7,6"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Malformed Commands",
        data={
            CONF_REMOTE_ID: "malformed_commands",
            CONF_REMOTE_NAME: "Malformed Commands",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={CONF_REMOTE_COMMANDS: raw_payload},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["options"][CONF_REMOTE_COMMANDS] == "<redacted>"
    assert diagnostics["universal_remote"]["command_count"] == 0
    assert raw_payload not in str(diagnostics)


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


async def test_diagnostics_reports_learning_capabilities(
    hass: HomeAssistant,
    infrared_emitter: str,
    mock_available_infrared_receivers: Mock,
) -> None:
    """Test diagnostics includes privacy-safe learning capability metadata."""
    receiver_entity_id = "infrared.test_receiver"
    hass.states.async_set(receiver_entity_id, STATE_ON)
    mock_available_infrared_receivers.return_value = {
        receiver_entity_id: {
            "value": receiver_entity_id,
            "label": "Test Receiver",
        }
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Learnable Remote",
        data={
            CONF_REMOTE_ID: "learnable_remote",
            CONF_REMOTE_NAME: "Learnable Remote",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_INFRARED_RECEIVER_ID: receiver_entity_id,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options={CONF_REMOTE_COMMANDS: {"POWER": "38000:1,2"}},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["universal_remote"]["learning"] == {
        "receiver_configured": True,
        "receiver_available": True,
        "selectable_receiver_count": 1,
        "configured_receiver_selectable": True,
        "alternative_receiver_available": False,
        "emitter_configured": True,
        "emitter_available": True,
        "available_decoders": ["nec", "nec1_f16"],
        "learn_command_available": True,
    }


async def test_diagnostics_reports_alternative_learning_receiver(
    hass: HomeAssistant,
    infrared_emitter: str,
    mock_available_infrared_receivers: Mock,
) -> None:
    """Test learning remains available through an alternative receiver."""
    configured_receiver_id = "infrared.configured_receiver"
    alternative_receiver_id = "infrared.alternative_receiver"
    hass.states.async_set(configured_receiver_id, STATE_UNAVAILABLE)
    mock_available_infrared_receivers.return_value = {
        alternative_receiver_id: {
            "value": alternative_receiver_id,
            "label": "Alternative Receiver",
        }
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Alternative Receiver Remote",
        data={
            CONF_REMOTE_ID: "alternative_receiver_remote",
            CONF_REMOTE_NAME: "Alternative Receiver Remote",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_INFRARED_RECEIVER_ID: configured_receiver_id,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options={CONF_REMOTE_COMMANDS: {"POWER": "38000:1,2"}},
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["summary"]["missing_infrared_receiver_count"] == 1
    assert diagnostics["universal_remote"]["learning"] == {
        "receiver_configured": True,
        "receiver_available": False,
        "selectable_receiver_count": 1,
        "configured_receiver_selectable": False,
        "alternative_receiver_available": True,
        "emitter_configured": True,
        "emitter_available": True,
        "available_decoders": ["nec", "nec1_f16"],
        "learn_command_available": True,
    }
