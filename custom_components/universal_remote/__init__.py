"""The Universal Remote integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_INFRARED_EMITTER_ID, CONF_REMOTE_COMMANDS
from .helpers import normalize_command_mapping, universal_remote_from_config_entry_data
from .runtime import UniversalRemoteData, UniversalRemoteRuntime

PLATFORMS = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.EVENT,
    Platform.SELECT,
]

type UniversalRemoteConfigEntry = ConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
) -> bool:
    """Set up Universal Remote from a config entry."""
    entry.runtime_data = _runtime_data_from_config_entry(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
) -> None:
    """Reload Universal Remote when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


def _runtime_data_from_config_entry(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
) -> UniversalRemoteData:
    """Return runtime data for a Universal Remote config entry."""
    remote = universal_remote_from_config_entry_data(
        {
            **entry.data,
            **entry.options,
        }
    )
    runtime = None

    if remote is not None:
        infrared_emitter_id = remote.get(CONF_INFRARED_EMITTER_ID)
        if isinstance(infrared_emitter_id, str) and infrared_emitter_id:
            runtime = UniversalRemoteRuntime(
                hass=hass,
                infrared_emitter_id=infrared_emitter_id,
                commands=normalize_command_mapping(
                    remote.get(CONF_REMOTE_COMMANDS, {})
                ),
            )

    return UniversalRemoteData(runtime=runtime)
