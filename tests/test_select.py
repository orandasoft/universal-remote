"""Tests for Universal Remote tuner select entities."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.runtime import (
    UniversalRemoteData,
    UniversalRemoteRuntime,
)
from custom_components.universal_remote.select import (
    UniversalRemoteTunerSelect,
    async_setup_entry,
    cleanup_stale_select_entities,
    select_unique_id,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import RAW_COMMAND, REMOTE_ID, REMOTE_NAME

RAW_COMMAND_ALT = "38000:9000,2250,560,560"


def _select_entry(
    hass: HomeAssistant,
    infrared_emitter: str,
    commands: dict[str, str],
) -> MockConfigEntry:
    """Create a config entry for select tests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={CONF_REMOTE_COMMANDS: commands},
        unique_id=REMOTE_ID,
    )
    entry.runtime_data = UniversalRemoteData(
        runtime=UniversalRemoteRuntime(
            hass=hass,
            infrared_emitter_id=infrared_emitter,
            commands=commands,
        )
    )
    entry.add_to_hass(hass)
    return entry


def _tuner_select(
    hass: HomeAssistant,
    infrared_emitter: str,
    commands: dict[str, str],
) -> UniversalRemoteTunerSelect:
    """Create a tuner select entity for tests."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=infrared_emitter,
        commands=commands,
    )
    entity = UniversalRemoteTunerSelect(
        runtime=runtime,
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        unique_id=select_unique_id("entry", REMOTE_ID),
    )
    entity.hass = hass
    return entity


async def test_async_setup_entry_adds_tuner_select_when_supported(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup creates a tuner select when tuner support is detected."""
    entry = _select_entry(
        hass,
        infrared_emitter,
        {
            "DTV": RAW_COMMAND,
            "DTV_NUM_1": RAW_COMMAND,
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND,
            "CS4K": RAW_COMMAND,
            "CS4K_NUM_12": RAW_COMMAND,
        },
    )
    async_add_entities = Mock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once()
    entities = async_add_entities.call_args.args[0]
    assert len(entities) == 1

    entity = entities[0]
    assert isinstance(entity, UniversalRemoteTunerSelect)
    assert entity.unique_id == select_unique_id(entry.entry_id, REMOTE_ID)
    assert entity.options == ["DTV", "BS", "CS4K"]
    assert entity.current_option is None


async def test_async_setup_entry_skips_select_without_tuner_support(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup skips select when no tuner-specific keypad exists."""
    entry = _select_entry(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "NUM_1": RAW_COMMAND,
        },
    )
    async_add_entities = Mock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once_with([])


async def test_async_setup_entry_skips_select_without_runtime_data(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup skips select when runtime data is not present."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
        },
        options={},
        unique_id=REMOTE_ID,
    )
    entry.add_to_hass(hass)
    async_add_entities = Mock()

    await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once_with([])


async def test_select_option_sends_tuner_and_updates_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selecting a tuner sends the tuner command and updates state."""
    entity = _tuner_select(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )

    with (
        patch(
            "custom_components.universal_remote.runtime.async_send_infrared_command",
            AsyncMock(),
        ) as mock_send,
        patch.object(entity, "async_write_ha_state") as write_state,
    ):
        await entity.async_select_option("BS")

    assert mock_send.await_args is not None
    assert mock_send.await_args.args == (hass, infrared_emitter, RAW_COMMAND)
    assert entity.current_option == "BS"
    write_state.assert_called_once()


async def test_select_option_rejects_invalid_tuner(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selecting an unavailable tuner raises a validation error."""
    entity = _tuner_select(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )

    with pytest.raises(ServiceValidationError) as err:
        await entity.async_select_option("CS4K")

    assert err.value.translation_key == "select_tuner_unavailable"
    assert err.value.translation_placeholders == {"option": "CS4K"}


async def test_select_availability_tracks_infrared_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test select availability follows the linked infrared emitter."""
    entity = _tuner_select(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )
    assert entity.available

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        hass.states.async_set(infrared_emitter, STATE_UNAVAILABLE)
        await hass.async_block_till_done()

    assert not entity.available
    write_state.assert_called_once()


async def test_select_listener_updates_state_from_runtime(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test select listens for runtime tuner state changes."""
    entity = _tuner_select(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        entity._runtime.async_note_received_command("BS_NUM_1")

    assert entity.current_option == "BS"
    write_state.assert_called_once()


def test_select_available_without_hass_returns_true(
    infrared_emitter: str,
) -> None:
    """Test select is available before Home Assistant is attached."""
    runtime = UniversalRemoteRuntime(
        hass=Mock(),
        infrared_emitter_id=infrared_emitter,
        commands={"BS": RAW_COMMAND, "BS_NUM_1": RAW_COMMAND_ALT},
    )
    entity = UniversalRemoteTunerSelect(
        runtime=runtime,
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        unique_id=select_unique_id("entry", REMOTE_ID),
    )

    assert entity.available


def test_current_option_returns_none_for_unavailable_runtime_tuner(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test current option hides tuner state that is not an available option."""
    entity = _tuner_select(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )

    entity._runtime.async_note_received_command("DTV")

    assert entity.current_option is None


async def test_cleanup_stale_select_entities(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test stale tuner select entity registry entries are removed."""
    entry = _select_entry(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )
    entity_registry = er.async_get(hass)
    stale_entry = entity_registry.async_get_or_create(
        "select",
        DOMAIN,
        select_unique_id(entry.entry_id, REMOTE_ID),
        config_entry=entry,
        suggested_object_id="old_tuner",
    )

    cleanup_stale_select_entities(hass, entry, set())

    assert entity_registry.async_get(stale_entry.entity_id) is None


async def test_async_setup_entry_skips_invalid_remote_definition(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup skips malformed remote definitions."""
    entry = _select_entry(
        hass,
        infrared_emitter,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )
    async_add_entities = Mock()

    with patch(
        "custom_components.universal_remote.select.universal_remotes_from_config_entry",
        return_value=[{CONF_REMOTE_ID: "", CONF_REMOTE_NAME: REMOTE_NAME}],
    ):
        await async_setup_entry(hass, entry, async_add_entities)

    async_add_entities.assert_called_once_with([])
