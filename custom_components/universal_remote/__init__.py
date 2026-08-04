"""The Universal Remote integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
)
from .event import resolve_receiver_model
from .helpers import normalize_command_mapping, universal_remote_from_config_entry_data
from .infrared_library import NO_INFRARED_LIBRARY_CODESET
from .profiles import CAPABILITY_JAPANESE_TUNER, TunerCapability
from .resolved import resolve_remote_profile
from .runtime import (
    UniversalRemoteConfigEntry,
    UniversalRemoteData,
    UniversalRemoteRuntime,
)

PLATFORMS = [
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.REMOTE,
    Platform.EVENT,
    Platform.SELECT,
]


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
    resolved_profile = None
    resolved_receiver = None

    if remote is not None:
        device_type = remote.get(CONF_REMOTE_DEVICE_TYPE)
        codeset_id = remote.get(CONF_REMOTE_CODESET)
        resolved_profile = resolve_remote_profile(
            device_type=device_type if isinstance(device_type, str) else None,
            codeset_id=codeset_id if isinstance(codeset_id, str) else None,
        )

        infrared_receiver_id = remote.get(CONF_INFRARED_RECEIVER_ID)
        if isinstance(infrared_receiver_id, str) and infrared_receiver_id:
            resolved_receiver = resolve_receiver_model(
                codeset_id
                if isinstance(codeset_id, str) and codeset_id
                else NO_INFRARED_LIBRARY_CODESET
            )

        tuner_capability = None
        if resolved_profile is not None:
            resolved_capability = resolved_profile.capability_for_id(
                CAPABILITY_JAPANESE_TUNER
            )
            if isinstance(resolved_capability, TunerCapability):
                tuner_capability = resolved_capability

        infrared_emitter_id = remote.get(CONF_INFRARED_EMITTER_ID)
        if isinstance(infrared_emitter_id, str) and infrared_emitter_id:
            runtime = UniversalRemoteRuntime(
                hass=hass,
                infrared_emitter_id=infrared_emitter_id,
                commands=normalize_command_mapping(
                    remote.get(CONF_REMOTE_COMMANDS, {})
                ),
                tuner_capability=tuner_capability,
            )

    return UniversalRemoteData(
        runtime=runtime,
        resolved_profile=resolved_profile,
        resolved_receiver=resolved_receiver,
    )
