"""Integration-flow tests for Universal Remote runtime sharing."""

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.event import DOMAIN as EVENT_DOMAIN
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.remote import DOMAIN as REMOTE_DOMAIN
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

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
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.event import event_unique_id
from custom_components.universal_remote.media_player import media_player_unique_id
from custom_components.universal_remote.remote import remote_unique_id
from custom_components.universal_remote.select import select_unique_id

from .conftest import REMOTE_ID, REMOTE_NAME

RAW_BS = "38000:9000,4500,560,560"
RAW_NUM_1 = "38000:9000,2250,560,560"
RAW_BS_NUM_1 = "38000:4500,4500,560,560"
RAW_CS4K = "38000:4500,2250,560,560"
RAW_CS4K_NUM_1 = "38000:2250,2250,560,560"
LEARNED_POWER = "0000 006D 0002 0000 0152 00AA 0014 0017"
LEARNED_BS_NUM_1 = "0000 006D 0002 0000 0152 00AA 0014 0017"
LEARNED_PRONTO_TIMINGS = [8888, -4470, 526, -605]


def _command(command_data: str, *, create_button: bool = False) -> dict[str, object]:
    """Return a stored command object."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: create_button,
    }


def _entity_id(
    hass: HomeAssistant,
    domain: str,
    unique_id: str,
) -> str:
    """Return an entity id from the entity registry."""
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id


def _sent_timings(mock_send: AsyncMock) -> list[list[int]]:
    """Return raw timings sent through the patched infrared API."""
    return [call.args[2].get_raw_timings() for call in mock_send.await_args_list]


async def _update_entry_options_and_wait_for_reload(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    options: dict[str, Any],
) -> None:
    """Update entry options and wait for the registered update-listener reload."""
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    await hass.async_block_till_done()


async def test_setup_entities_share_runtime_across_services(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test real setup shares runtime across select, remote, button, and media player."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "BS": _command(RAW_BS, create_button=True),
                "NUM_1": _command(RAW_NUM_1, create_button=True),
                "BS_NUM_1": _command(RAW_BS_NUM_1, create_button=True),
                "CS4K": _command(RAW_CS4K, create_button=True),
                "CS4K_NUM_1": _command(RAW_CS4K_NUM_1, create_button=True),
            },
        },
        unique_id=REMOTE_ID,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    remote_entity_id = _entity_id(
        hass,
        REMOTE_DOMAIN,
        remote_unique_id(entry.entry_id, REMOTE_ID),
    )
    num_1_button_entity_id = _entity_id(
        hass,
        BUTTON_DOMAIN,
        button_unique_id(entry.entry_id, REMOTE_ID, "NUM_1"),
    )
    media_player_entity_id = _entity_id(
        hass,
        MEDIA_PLAYER_DOMAIN,
        media_player_unique_id(entry.entry_id, REMOTE_ID),
    )
    select_entity_id = _entity_id(
        hass,
        SELECT_DOMAIN,
        select_unique_id(entry.entry_id, REMOTE_ID),
    )

    select_state = hass.states.get(select_entity_id)
    assert select_state is not None
    assert select_state.state == "unknown"

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await hass.services.async_call(
            SELECT_DOMAIN,
            "select_option",
            {
                ATTR_ENTITY_ID: select_entity_id,
                "option": "BS",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        await hass.services.async_call(
            REMOTE_DOMAIN,
            "send_command",
            {
                ATTR_ENTITY_ID: remote_entity_id,
                "command": "NUM_1",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        await hass.services.async_call(
            BUTTON_DOMAIN,
            "press",
            {
                ATTR_ENTITY_ID: num_1_button_entity_id,
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        await hass.services.async_call(
            MEDIA_PLAYER_DOMAIN,
            "select_source",
            {
                ATTR_ENTITY_ID: media_player_entity_id,
                "source": "CS4K",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert [call.args[1] for call in mock_send.await_args_list] == [
        infrared_emitter,
        infrared_emitter,
        infrared_emitter,
        infrared_emitter,
    ]
    assert _sent_timings(mock_send) == [
        [9000, -4500, 560, -560],
        [4500, -4500, 560, -560],
        [4500, -4500, 560, -560],
        [4500, -2250, 560, -560],
    ]

    select_state = hass.states.get(select_entity_id)
    assert select_state is not None
    assert select_state.state == "CS4K"

    media_state = hass.states.get(media_player_entity_id)
    assert media_state is not None
    assert media_state.attributes["source"] == "CS4K"


async def test_receiver_only_setup_creates_event_without_send_entities(
    hass: HomeAssistant,
) -> None:
    """Test receiver-only setup creates event entity without send/select entities."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Receiver Remote",
        data={
            CONF_REMOTE_ID: "receiver_remote",
            CONF_REMOTE_NAME: "Receiver Remote",
            CONF_INFRARED_RECEIVER_ID: "infrared.test_receiver",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options={},
        unique_id="receiver_remote",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.universal_remote.event.infrared.async_get_receivers",
        return_value={"infrared.test_receiver"},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    registry = er.async_get(hass)
    event_entity_id = registry.async_get_entity_id(
        EVENT_DOMAIN,
        DOMAIN,
        event_unique_id("receiver_remote"),
    )
    assert event_entity_id is not None

    domains = {
        entity_entry.domain
        for entity_entry in er.async_entries_for_config_entry(
            registry,
            entry.entry_id,
        )
    }
    assert EVENT_DOMAIN in domains
    assert REMOTE_DOMAIN not in domains
    assert BUTTON_DOMAIN not in domains
    assert MEDIA_PLAYER_DOMAIN not in domains
    assert SELECT_DOMAIN not in domains


async def test_learned_command_reload_refreshes_runtime_send_path(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test a learned Pronto command is usable after options reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER": _command(RAW_BS),
            },
        },
        unique_id="learned_reload_remote",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await _update_entry_options_and_wait_for_reload(
        hass,
        entry,
        {
            CONF_REMOTE_COMMANDS: {
                "POWER": _command(RAW_BS),
                "LEARNED_POWER": _command(LEARNED_POWER),
            },
        },
    )

    remote_entity_id = _entity_id(
        hass,
        REMOTE_DOMAIN,
        remote_unique_id(entry.entry_id, REMOTE_ID),
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
                "command": "LEARNED_POWER",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert [call.args[1] for call in mock_send.await_args_list] == [infrared_emitter]
    assert _sent_timings(mock_send) == [LEARNED_PRONTO_TIMINGS]


async def test_learned_tuner_number_reload_enables_select_and_num_overlay(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test learned tuner-specific number commands refresh select/runtime behavior."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "BS": _command(RAW_BS),
                "NUM_1": _command(RAW_NUM_1),
            },
        },
        unique_id="learned_tuner_remote",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    select_unique = select_unique_id(entry.entry_id, REMOTE_ID)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id(SELECT_DOMAIN, DOMAIN, select_unique) is None

    await _update_entry_options_and_wait_for_reload(
        hass,
        entry,
        {
            CONF_REMOTE_COMMANDS: {
                "BS": _command(RAW_BS),
                "NUM_1": _command(RAW_NUM_1),
                "BS_NUM_1": _command(LEARNED_BS_NUM_1),
            },
        },
    )

    remote_entity_id = _entity_id(
        hass,
        REMOTE_DOMAIN,
        remote_unique_id(entry.entry_id, REMOTE_ID),
    )
    select_entity_id = _entity_id(hass, SELECT_DOMAIN, select_unique)

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await hass.services.async_call(
            SELECT_DOMAIN,
            "select_option",
            {
                ATTR_ENTITY_ID: select_entity_id,
                "option": "BS",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

        await hass.services.async_call(
            REMOTE_DOMAIN,
            "send_command",
            {
                ATTR_ENTITY_ID: remote_entity_id,
                "command": "NUM_1",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert [call.args[1] for call in mock_send.await_args_list] == [
        infrared_emitter,
        infrared_emitter,
    ]
    assert _sent_timings(mock_send) == [
        [9000, -4500, 560, -560],
        LEARNED_PRONTO_TIMINGS,
    ]

    select_state = hass.states.get(select_entity_id)
    assert select_state is not None
    assert select_state.state == "BS"


async def test_receiver_event_entity_survives_learned_command_reload(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test receiver event entity remains available after learned command reload."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_INFRARED_RECEIVER_ID: "infrared.test_receiver",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_REMOTE_CODESET: "lg_tv",
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER": _command(RAW_BS),
            },
        },
        unique_id="learned_event_remote",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.universal_remote.event.infrared.async_get_receivers",
        return_value={"infrared.test_receiver"},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        await _update_entry_options_and_wait_for_reload(
            hass,
            entry,
            {
                CONF_REMOTE_COMMANDS: {
                    "POWER": _command(RAW_BS),
                    "LEARNED_POWER": _command(LEARNED_POWER),
                },
            },
        )

    event_entity_id = _entity_id(
        hass,
        EVENT_DOMAIN,
        event_unique_id(REMOTE_ID),
    )
    remote_entity_id = _entity_id(
        hass,
        REMOTE_DOMAIN,
        remote_unique_id(entry.entry_id, REMOTE_ID),
    )

    event_state = hass.states.get(event_entity_id)
    assert event_state is not None

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await hass.services.async_call(
            REMOTE_DOMAIN,
            "send_command",
            {
                ATTR_ENTITY_ID: remote_entity_id,
                "command": "LEARNED_POWER",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    assert _sent_timings(mock_send) == [LEARNED_PRONTO_TIMINGS]
