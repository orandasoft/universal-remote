"""Tests for Universal Remote media player entities."""

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.media_player import (
    UniversalRemoteTvMediaPlayer,
    cleanup_stale_media_player_entities,
    media_player_unique_id,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .conftest import RAW_COMMAND, REMOTE_ID, REMOTE_NAME

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _command_object(command_data: str) -> dict[str, object]:
    """Return a stored command object."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: False,
    }


def _media_player_entry(
    hass: HomeAssistant,
    infrared_emitter: str,
    *,
    device_type: str = DEVICE_TYPE_TV,
) -> MockConfigEntry:
    """Create a config entry for media-player tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: device_type,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER_ON": _command_object(RAW_COMMAND),
                "POWER_OFF": _command_object(RAW_COMMAND),
                "VOLUME_UP": _command_object(RAW_COMMAND),
                "VOLUME_DOWN": _command_object(RAW_COMMAND),
                "MUTE": _command_object(RAW_COMMAND),
                "CHANNEL_UP": _command_object(RAW_COMMAND),
                "CHANNEL_DOWN": _command_object(RAW_COMMAND),
                "PLAY": _command_object(RAW_COMMAND),
                "PAUSE": _command_object(RAW_COMMAND),
                "STOP": _command_object(RAW_COMMAND),
                "HDMI_1": _command_object(RAW_COMMAND),
                "INPUT": _command_object(RAW_COMMAND),
                "NETFLIX": _command_object(RAW_COMMAND),
            },
        },
    )
    entry.add_to_hass(hass)
    return entry


def _media_player_entity(
    hass: HomeAssistant,
    infrared_emitter: str,
    commands: Mapping[str, Mapping[str, Any]] | None = None,
) -> UniversalRemoteTvMediaPlayer:
    """Create a media player entity for behavior tests."""
    entity = UniversalRemoteTvMediaPlayer(
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        infrared_emitter_id=infrared_emitter,
        commands=commands
        or {
            "POWER_ON": _command_object(RAW_COMMAND),
            "POWER_OFF": _command_object(RAW_COMMAND),
            "VOLUME_UP": _command_object(RAW_COMMAND),
            "VOLUME_DOWN": _command_object(RAW_COMMAND),
            "MUTE": _command_object(RAW_COMMAND),
            "CHANNEL_UP": _command_object(RAW_COMMAND),
            "CHANNEL_DOWN": _command_object(RAW_COMMAND),
            "PLAY": _command_object(RAW_COMMAND),
            "PAUSE": _command_object(RAW_COMMAND),
            "STOP": _command_object(RAW_COMMAND),
            "HDMI_1": _command_object(RAW_COMMAND),
            "INPUT": _command_object(RAW_COMMAND),
            "NETFLIX": _command_object(RAW_COMMAND),
        },
        unique_id="entry_media_player_living_room_tv",
    )
    entity.hass = hass
    return entity


def _media_player_entity_without_hass(
    infrared_emitter: str,
) -> UniversalRemoteTvMediaPlayer:
    """Create a media player entity that has not been added to Home Assistant."""
    return UniversalRemoteTvMediaPlayer(
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        infrared_emitter_id=infrared_emitter,
        commands={"POWER_ON": _command_object(RAW_COMMAND)},
        unique_id="entry_media_player_living_room_tv",
    )


async def test_async_setup_entry_adds_tv_media_player(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup creates a media player for TV universal remotes."""
    entry = _media_player_entry(hass, infrared_emitter)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = entity_registry.async_get_entity_id(
        "media_player",
        DOMAIN,
        media_player_unique_id(entry.entry_id, REMOTE_ID),
    )

    assert entity_id is not None
    assert hass.states.get(entity_id) is not None

    entity = _media_player_entity(hass, infrared_emitter)
    assert entity.device_info == DeviceInfo(
        identifiers={(DOMAIN, REMOTE_ID)},
        name=REMOTE_NAME,
    )
    assert entity.source_list == ["HDMI 1", "Netflix"]
    assert entity.supported_features == (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )


async def test_async_setup_entry_skips_generic_remote(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup does not create a media player for generic remotes."""
    entry = _media_player_entry(
        hass,
        infrared_emitter,
        device_type=DEVICE_TYPE_GENERIC,
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    entity_id = entity_registry.async_get_entity_id(
        "media_player",
        DOMAIN,
        media_player_unique_id(entry.entry_id, REMOTE_ID),
    )

    assert entity_id is None


async def test_setup_entry_cleans_stale_media_player_entity(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup removes stale media player entity registry entries."""
    entry = _media_player_entry(hass, infrared_emitter)
    entity_registry = er.async_get(hass)
    stale_entry = entity_registry.async_get_or_create(
        "media_player",
        DOMAIN,
        f"{entry.entry_id}_media_player_stale_remote",
        config_entry=entry,
        suggested_object_id="stale_remote",
    )

    cleanup_stale_media_player_entities(
        hass,
        entry,
        {media_player_unique_id(entry.entry_id, REMOTE_ID)},
    )

    assert entity_registry.async_get(stale_entry.entity_id) is None


async def test_media_player_commands_send_infrared_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test media-player actions send the matching command."""
    entity = _media_player_entity(hass, infrared_emitter)

    with patch(
        "custom_components.universal_remote.media_player."
        "async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await entity.async_volume_up()
        await entity.async_select_source("HDMI 1")

    assert mock_send.await_args_list[0].args == (hass, infrared_emitter, RAW_COMMAND)
    assert mock_send.await_args_list[1].args == (hass, infrared_emitter, RAW_COMMAND)


async def test_media_player_role_actions_send_infrared_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test media-player role actions send their mapped commands."""
    entity = _media_player_entity(hass, infrared_emitter)

    with patch(
        "custom_components.universal_remote.media_player."
        "async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await entity.async_volume_down()
        await entity.async_mute_volume(True)
        await entity.async_media_next_track()
        await entity.async_media_previous_track()
        await entity.async_media_play()
        await entity.async_media_pause()
        await entity.async_media_stop()

    assert mock_send.await_count == 7
    assert all(
        call_args.args == (hass, infrared_emitter, RAW_COMMAND)
        for call_args in mock_send.await_args_list
    )


async def test_media_player_turn_on_and_off_update_assumed_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test power actions update the assumed media player state."""
    entity = _media_player_entity(hass, infrared_emitter)

    with (
        patch(
            "custom_components.universal_remote.media_player."
            "async_send_infrared_command",
            AsyncMock(),
        ),
        patch.object(entity, "async_write_ha_state") as write_state,
    ):
        await entity.async_turn_off()
        assert str(entity.state) == str(MediaPlayerState.OFF)

        await entity.async_turn_on()
        assert str(entity.state) == str(MediaPlayerState.ON)

    assert write_state.call_count == 2


def test_media_player_power_toggle_command_does_not_create_on_off_features(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test POWER toggle commands are not exposed as discrete on/off actions."""
    entity = _media_player_entity(
        hass,
        infrared_emitter,
        commands={"POWER": _command_object(RAW_COMMAND)},
    )

    assert not entity.supported_features & MediaPlayerEntityFeature.TURN_ON
    assert not entity.supported_features & MediaPlayerEntityFeature.TURN_OFF


async def test_media_player_invalid_source_raises(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selecting an invalid source raises HomeAssistantError."""
    entity = _media_player_entity(hass, infrared_emitter)

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_select_source("Input")

    assert err.value.translation_key == "media_player_source_unavailable"


async def test_media_player_missing_role_raises(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test sending an unavailable role raises HomeAssistantError."""
    entity = _media_player_entity(
        hass,
        infrared_emitter,
        commands={"HDMI_1": _command_object(RAW_COMMAND)},
    )

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_volume_up()

    assert err.value.translation_key == "media_player_role_unavailable"
    assert err.value.translation_placeholders == {"role": "volume_up"}


async def test_media_player_missing_command_raises(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test sending a stale command name raises HomeAssistantError."""
    entity = _media_player_entity(hass, infrared_emitter)

    with pytest.raises(HomeAssistantError) as err:
        await entity._send_command_name("MISSING")

    assert err.value.translation_key == "remote_command_missing"
    assert err.value.translation_placeholders == {"command": "MISSING"}


async def test_media_player_missing_command_payload_raises(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test sending a command without command data raises HomeAssistantError."""
    entity = _media_player_entity(
        hass,
        infrared_emitter,
        commands={"POWER_ON": _command_object(RAW_COMMAND)},
    )
    entity._commands["POWER_ON"] = {CONF_COMMAND_CREATE_BUTTON: False}

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_turn_on()

    assert err.value.translation_key == "remote_command_missing"
    assert err.value.translation_placeholders == {"command": "POWER_ON"}


async def test_media_player_availability_tracks_infrared_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test media player availability follows the linked infrared entity."""
    entity = _media_player_entity(hass, infrared_emitter)
    assert entity.available

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        hass.states.async_set(infrared_emitter, STATE_UNAVAILABLE)
        await hass.async_block_till_done()

    assert not entity.available
    write_state.assert_called_once()


def test_media_player_available_before_added_to_hass(infrared_emitter: str) -> None:
    """Test media player is available before it is added to Home Assistant."""
    entity = _media_player_entity_without_hass(infrared_emitter)

    assert entity.available
