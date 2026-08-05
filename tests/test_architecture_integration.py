"""End-to-end integration tests for the v0.7.0 resolved architecture."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.remote import DOMAIN as REMOTE_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from infrared_protocols.codes.lg.tv import LGTVCodeJP
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.universal_remote.button import button_unique_id
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
from custom_components.universal_remote.event import event_unique_id
from custom_components.universal_remote.infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
)
from custom_components.universal_remote.media_player import media_player_unique_id
from custom_components.universal_remote.profiles import (
    CAPABILITY_JAPANESE_TUNER,
    PROFILE_TV,
)
from custom_components.universal_remote.protocols import (
    PROTOCOL_NEC,
    PROTOCOL_NEC1_F16,
    PROTOCOL_UNKNOWN,
)
from custom_components.universal_remote.remote import remote_unique_id
from custom_components.universal_remote.runtime import UniversalRemoteData
from custom_components.universal_remote.select import select_unique_id

REMOTE_ID = "architecture_tv"
REMOTE_NAME = "Architecture TV"
RECEIVER_ID = "infrared.test_receiver"

RAW_POWER_ON = "38000:9000,4500,560,560"
RAW_MUTE = "38000:9000,2250,560,560"
RAW_HDMI_1 = "38000:4500,4500,560,560"
RAW_DTV = "38000:4500,2250,560,560"
RAW_DTV_NUM_2 = "38000:2250,2250,560,560"

SignalCallback = Callable[[InfraredReceivedSignal], None]


def _command(command_data: str, *, create_button: bool = False) -> dict[str, object]:
    """Return one persisted command object."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: create_button,
    }


def _entity_id(
    hass: HomeAssistant,
    domain: str,
    unique_id: str,
) -> str:
    """Return one entity id from the entity registry."""
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


def _entry_entity_ids(
    hass: HomeAssistant,
    entry_id: str,
) -> dict[tuple[str, str], str]:
    """Return config-entry entity ids keyed by domain and unique id."""
    return {
        (entity_entry.domain, entity_entry.unique_id): entity_entry.entity_id
        for entity_entry in er.async_entries_for_config_entry(
            er.async_get(hass),
            entry_id,
        )
    }


def _sent_timings(mock_send: AsyncMock) -> list[list[int]]:
    """Return raw timings passed to the infrared send helper."""
    return [call.args[2].get_raw_timings() for call in mock_send.await_args_list]


@contextmanager
def _available_receiver(
    hass: HomeAssistant,
    receiver_id: str = RECEIVER_ID,
) -> Generator[list[SignalCallback], None, None]:
    """Expose one available receiver and capture its consumer callbacks."""
    callbacks: list[SignalCallback] = []
    hass.states.async_set(receiver_id, "on")

    def subscribe_receiver(
        _hass: HomeAssistant,
        subscribed_receiver_id: str,
        callback: SignalCallback,
    ) -> Callable[[], None]:
        """Capture one receiver-consumer callback."""
        assert subscribed_receiver_id == receiver_id
        callbacks.append(callback)

        def unsubscribe() -> None:
            """Remove the captured callback."""
            if callback in callbacks:
                callbacks.remove(callback)

        return unsubscribe

    with (
        patch(
            "custom_components.universal_remote.event.infrared.async_get_receivers",
            return_value={receiver_id},
        ),
        patch(
            "homeassistant.components.infrared.helpers.async_subscribe_receiver",
            side_effect=subscribe_receiver,
        ),
    ):
        yield callbacks


def _combined_lg_tv_jp_entry(
    hass: HomeAssistant,
    infrared_emitter: str,
    *,
    unique_id: str,
) -> MockConfigEntry:
    """Create a combined LG TV Japan config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_INFRARED_RECEIVER_ID: RECEIVER_ID,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv_jp",
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER_ON": _command(RAW_POWER_ON),
                "MUTE": _command(RAW_MUTE),
                "HDMI_1": _command(RAW_HDMI_1, create_button=True),
                "DTV": _command(RAW_DTV),
                "DTV_NUM_2": _command(RAW_DTV_NUM_2),
            },
        },
        unique_id=unique_id,
    )
    entry.add_to_hass(hass)
    return entry


async def test_combined_entry_resolves_models_and_all_platforms(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup composes the complete v0.7.0 resolved architecture."""
    entry = _combined_lg_tv_jp_entry(
        hass,
        infrared_emitter,
        unique_id="combined_architecture",
    )

    with _available_receiver(hass) as receiver_callbacks:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    assert isinstance(runtime_data, UniversalRemoteData)
    assert runtime_data.runtime is not None

    resolved_profile = runtime_data.resolved_profile
    assert resolved_profile is not None
    assert resolved_profile.profile.profile_id == PROFILE_TV
    assert resolved_profile.codeset is not None
    assert resolved_profile.codeset.codeset_id == "lg_tv_jp"
    assert tuple(
        capability.capability_id for capability in resolved_profile.capabilities
    ) == (CAPABILITY_JAPANESE_TUNER,)

    resolved_receiver = runtime_data.resolved_receiver
    assert resolved_receiver is not None
    assert resolved_receiver.codeset_id == "lg_tv_jp"
    assert resolved_receiver.decoder_family_id == PROTOCOL_NEC
    assert tuple(handler.protocol_id for handler in resolved_receiver.handlers) == (
        PROTOCOL_NEC,
        PROTOCOL_NEC1_F16,
    )
    assert resolved_receiver.match_map_for_protocol(PROTOCOL_NEC)
    assert "unknown" in resolved_receiver.event_types
    assert "dtv_num_2" in resolved_receiver.event_types

    assert len(receiver_callbacks) == 1

    entity_domains = {
        entity_entry.domain
        for entity_entry in er.async_entries_for_config_entry(
            er.async_get(hass),
            entry.entry_id,
        )
    }
    assert entity_domains == {
        BUTTON_DOMAIN,
        EVENT_DOMAIN,
        MEDIA_PLAYER_DOMAIN,
        REMOTE_DOMAIN,
        SELECT_DOMAIN,
    }

    assert (
        hass.states.get(
            _entity_id(
                hass,
                REMOTE_DOMAIN,
                remote_unique_id(entry.entry_id, REMOTE_ID),
            )
        )
        is not None
    )
    assert (
        hass.states.get(
            _entity_id(
                hass,
                BUTTON_DOMAIN,
                button_unique_id(entry.entry_id, REMOTE_ID, "HDMI_1"),
            )
        )
        is not None
    )
    assert (
        hass.states.get(
            _entity_id(
                hass,
                MEDIA_PLAYER_DOMAIN,
                media_player_unique_id(entry.entry_id, REMOTE_ID),
            )
        )
        is not None
    )
    assert (
        hass.states.get(
            _entity_id(
                hass,
                SELECT_DOMAIN,
                select_unique_id(entry.entry_id, REMOTE_ID),
            )
        )
        is not None
    )
    assert (
        hass.states.get(
            _entity_id(
                hass,
                EVENT_DOMAIN,
                event_unique_id(REMOTE_ID),
            )
        )
        is not None
    )


async def test_received_signal_flows_through_resolved_models_and_updates_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test a physical signal drives event, tuner, and media-player state."""
    entry = _combined_lg_tv_jp_entry(
        hass,
        infrared_emitter,
        unique_id="received_architecture",
    )

    with _available_receiver(hass) as receiver_callbacks:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert len(receiver_callbacks) == 1

        command = LGTVCodeJP.DTV_NUM_2.to_command()
        receiver_callbacks[0](
            InfraredReceivedSignal(
                timings=command.get_raw_timings(),
                modulation=command.modulation,
            )
        )
        await hass.async_block_till_done()

    event_state = hass.states.get(
        _entity_id(
            hass,
            EVENT_DOMAIN,
            event_unique_id(REMOTE_ID),
        )
    )
    assert event_state is not None
    assert event_state.attributes["event_type"] == "dtv_num_2"
    assert event_state.attributes["command_name"] == "DTV_NUM_2"
    assert event_state.attributes["matched"] is True
    assert event_state.attributes["repeat"] is False
    assert event_state.attributes["protocol"] in {
        PROTOCOL_NEC,
        PROTOCOL_NEC1_F16,
    }
    recent_events = event_state.attributes["recent_events"]
    assert recent_events[0]["event_type"] == "dtv_num_2"
    assert "timings_preview" not in recent_events[0]

    select_state = hass.states.get(
        _entity_id(
            hass,
            SELECT_DOMAIN,
            select_unique_id(entry.entry_id, REMOTE_ID),
        )
    )
    assert select_state is not None
    assert select_state.state == "DTV"

    media_player_state = hass.states.get(
        _entity_id(
            hass,
            MEDIA_PLAYER_DOMAIN,
            media_player_unique_id(entry.entry_id, REMOTE_ID),
        )
    )
    assert media_player_state is not None
    assert media_player_state.attributes["source"] == "DTV"


async def test_receiver_without_codeset_emits_unknown_with_safe_history(
    hass: HomeAssistant,
) -> None:
    """Test no-codeset receiver setup keeps the documented unknown behavior."""
    remote_id = "generic_receiver"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Generic Receiver",
        data={
            CONF_REMOTE_ID: remote_id,
            CONF_REMOTE_NAME: "Generic Receiver",
            CONF_INFRARED_RECEIVER_ID: RECEIVER_ID,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={},
        unique_id="generic_receiver_architecture",
    )
    entry.add_to_hass(hass)

    with _available_receiver(hass) as receiver_callbacks:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert len(receiver_callbacks) == 1

        timings = [9000, -4500, 560, -560]
        receiver_callbacks[0](
            InfraredReceivedSignal(
                timings=timings,
                modulation=38000,
            )
        )
        await hass.async_block_till_done()

    runtime_data = entry.runtime_data
    assert runtime_data.runtime is None
    assert runtime_data.resolved_receiver is not None
    assert runtime_data.resolved_receiver.codeset_id == NO_INFRARED_LIBRARY_CODESET
    assert runtime_data.resolved_receiver.handlers == ()

    event_state = hass.states.get(
        _entity_id(
            hass,
            EVENT_DOMAIN,
            event_unique_id(remote_id),
        )
    )
    assert event_state is not None
    assert event_state.attributes["event_type"] == "unknown"
    assert event_state.attributes["codeset"] == NO_INFRARED_LIBRARY_CODESET
    assert event_state.attributes["decoder"] is None
    assert event_state.attributes["protocol"] == PROTOCOL_UNKNOWN
    assert event_state.attributes["decoded"] is False
    assert event_state.attributes["matched"] is False
    assert event_state.attributes["timings_count"] == len(timings)
    assert event_state.attributes["timings_preview"] == timings
    assert event_state.attributes["modulation"] == 38000
    recent_events = event_state.attributes["recent_events"]
    assert recent_events[0]["event_type"] == "unknown"
    assert "timings_preview" not in recent_events[0]


async def test_pre_v07_entry_reloads_without_persistence_or_entity_id_changes(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test an existing persisted entry loads and reloads without migration."""
    remote_id = "persisted_tv"
    options: dict[str, Any] = {
        CONF_REMOTE_COMMANDS: {
            "POWER_ON": _command(RAW_POWER_ON),
            "MUTE": _command(RAW_MUTE),
            "HDMI_1": _command(RAW_HDMI_1, create_button=True),
        },
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Persisted TV",
        data={
            CONF_REMOTE_ID: remote_id,
            CONF_REMOTE_NAME: "Persisted TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options=options,
        unique_id="persisted_tv_entry",
    )
    original_data = deepcopy(dict(entry.data))
    original_options = deepcopy(dict(entry.options))
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_ids_before = _entry_entity_ids(hass, entry.entry_id)
    assert entity_ids_before

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert dict(entry.data) == original_data
    assert dict(entry.options) == original_options
    assert _entry_entity_ids(hass, entry.entry_id) == entity_ids_before

    remote_entity_id = _entity_id(
        hass,
        REMOTE_DOMAIN,
        remote_unique_id(entry.entry_id, remote_id),
    )

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await hass.services.async_call(
            REMOTE_DOMAIN,
            "send_command",
            {
                ATTR_ENTITY_ID: remote_entity_id,
                "command": "POWER_ON",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert [call.args[1] for call in mock_send.await_args_list] == [infrared_emitter]
    assert _sent_timings(mock_send) == [[9000, -4500, 560, -560]]
    assert entry.options[CONF_REMOTE_COMMANDS] == original_options[CONF_REMOTE_COMMANDS]


async def test_media_player_mute_service_uses_desired_assumed_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test public mute service sends only for desired-state transitions."""
    remote_id = "mute_tv"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Mute TV",
        data={
            CONF_REMOTE_ID: remote_id,
            CONF_REMOTE_NAME: "Mute TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "MUTE": _command(RAW_MUTE),
            },
        },
        unique_id="mute_tv_entry",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    media_player_entity_id = _entity_id(
        hass,
        MEDIA_PLAYER_DOMAIN,
        media_player_unique_id(entry.entry_id, remote_id),
    )

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            "volume_mute",
            {
                ATTR_ENTITY_ID: media_player_entity_id,
                "is_volume_muted": True,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        muted_state = hass.states.get(media_player_entity_id)
        assert muted_state is not None
        assert muted_state.attributes["is_volume_muted"] is True
        assert mock_send.await_count == 1

        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            "volume_mute",
            {
                ATTR_ENTITY_ID: media_player_entity_id,
                "is_volume_muted": True,
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        assert mock_send.await_count == 1

        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            "volume_mute",
            {
                ATTR_ENTITY_ID: media_player_entity_id,
                "is_volume_muted": False,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        unmuted_state = hass.states.get(media_player_entity_id)
        assert unmuted_state is not None
        assert unmuted_state.attributes["is_volume_muted"] is False
        assert mock_send.await_count == 2

        mock_send.side_effect = HomeAssistantError("Transmission failed")
        with pytest.raises(HomeAssistantError, match="Transmission failed"):
            await hass.services.async_call(
                MEDIA_PLAYER_DOMAIN,
                "volume_mute",
                {
                    ATTR_ENTITY_ID: media_player_entity_id,
                    "is_volume_muted": True,
                },
                blocking=True,
            )
        await hass.async_block_till_done()

    failed_state = hass.states.get(media_player_entity_id)
    assert failed_state is not None
    assert failed_state.attributes["is_volume_muted"] is False
