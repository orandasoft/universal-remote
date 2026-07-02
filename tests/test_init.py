"""Tests for Universal Remote integration setup."""

from unittest.mock import patch

from custom_components.universal_remote import _async_update_listener
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
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import INFRARED_EMITTER_ID, RAW_COMMAND, REMOTE_ID, REMOTE_NAME

PLATFORMS = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.EVENT,
    Platform.SELECT,
]


def _runtime_data(entry: MockConfigEntry) -> UniversalRemoteData:
    """Return runtime data from a mock config entry."""
    runtime_data = getattr(entry, "runtime_data")
    assert isinstance(runtime_data, UniversalRemoteData)
    return runtime_data


async def test_setup_and_unload_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test setup forwards platforms and unloads them."""
    with (
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            return_value=True,
        ) as mock_forward,
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            return_value=True,
        ) as mock_unload,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        runtime_data = _runtime_data(config_entry)
        assert isinstance(runtime_data.runtime, UniversalRemoteRuntime)
        assert runtime_data.runtime.infrared_emitter_id == INFRARED_EMITTER_ID

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

    mock_forward.assert_called_once_with(config_entry, PLATFORMS)
    mock_unload.assert_called_once_with(config_entry, PLATFORMS)


async def test_setup_creates_runtime_for_empty_command_map(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup creates runtime even when commands are empty."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Raw Remote",
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={CONF_REMOTE_COMMANDS: {}},
        unique_id="raw_remote",
    )
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        return_value=True,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = _runtime_data(entry)
    assert isinstance(runtime_data.runtime, UniversalRemoteRuntime)
    assert runtime_data.runtime.infrared_emitter_id == INFRARED_EMITTER_ID
    assert runtime_data.runtime.available_tuners == ()


async def test_setup_creates_runtime_with_normalized_commands(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup creates runtime from stored command objects."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Tuner Remote",
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "BS": RAW_COMMAND,
                "BS_NUM_1": RAW_COMMAND,
            },
        },
        unique_id="tuner_remote",
    )
    entry.add_to_hass(hass)

    with patch.object(
        hass.config_entries,
        "async_forward_entry_setups",
        return_value=True,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    runtime_data = _runtime_data(entry)
    assert isinstance(runtime_data.runtime, UniversalRemoteRuntime)
    assert runtime_data.runtime.available_tuners == ("BS",)


async def test_options_update_listener_reloads_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test options update listener reloads config entry."""
    with (
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            return_value=True,
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            return_value=None,
        ) as mock_reload,
    ):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        await _async_update_listener(hass, config_entry)

    mock_reload.assert_called_once_with(config_entry.entry_id)


async def test_setup_and_unload_receiver_only_entry(
    hass: HomeAssistant,
) -> None:
    """Test receiver-only setup forwards all platforms for cleanup safety."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Receiver Remote",
        data={
            CONF_REMOTE_ID: "receiver_remote",
            CONF_REMOTE_NAME: "Receiver Remote",
            "infrared_receiver_id": "infrared.test_receiver",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            "codeset": "lg_tv",
        },
        options={},
        unique_id="receiver_remote",
    )
    entry.add_to_hass(hass)

    with (
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            return_value=True,
        ) as mock_forward,
        patch.object(
            hass.config_entries,
            "async_unload_platforms",
            return_value=True,
        ) as mock_unload,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        runtime_data = _runtime_data(entry)
        assert runtime_data.runtime is None

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    mock_forward.assert_called_once_with(entry, PLATFORMS)
    mock_unload.assert_called_once_with(entry, PLATFORMS)
