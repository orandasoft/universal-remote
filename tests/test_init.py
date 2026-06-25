"""Tests for Universal Remote integration setup."""

from unittest.mock import patch

from custom_components.universal_remote import _async_update_listener
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

PLATFORMS = [Platform.BUTTON, Platform.MEDIA_PLAYER, Platform.REMOTE, Platform.EVENT]


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

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

    mock_forward.assert_called_once_with(config_entry, PLATFORMS)
    mock_unload.assert_called_once_with(config_entry, PLATFORMS)


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
        domain="universal_remote",
        title="Receiver Remote",
        data={
            "id": "receiver_remote",
            "name": "Receiver Remote",
            "infrared_receiver_id": "infrared.test_receiver",
            "device_type": "tv",
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

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    mock_forward.assert_called_once_with(entry, PLATFORMS)
    mock_unload.assert_called_once_with(entry, PLATFORMS)
