"""Helper functions for the Universal Remote integration."""

from collections.abc import Mapping
import re
from typing import Any

import voluptuous as vol

from homeassistant.components import infrared
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, selector

from .const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
)
from .infrared_library import (
    infrared_library_codeset_device_type,
    validate_infrared_library_device_type,
)

_REMOTE_ID_RE = re.compile(r"[^a-z0-9_]+")
_COMMAND_NAME_RE = re.compile(r"[^A-Z0-9_]+")


def available_infrared_emitters(
    hass: HomeAssistant,
) -> dict[str, selector.SelectOptionDict]:
    """Return available infrared emitters.

    Multiple universal remotes may use the same infrared transmitter because one
    physical IR output can control multiple appliances, for example through
    dual emitters or a blaster.
    """
    registry = er.async_get(hass)
    options: dict[str, selector.SelectOptionDict] = {}

    for entity_id in infrared.async_get_emitters(hass):
        registry_entry = registry.async_get(entity_id)

        if registry_entry is not None and registry_entry.disabled_by is not None:
            continue

        label = entity_id
        if registry_entry is not None:
            label = (
                registry_entry.name
                or registry_entry.original_name
                or registry_entry.entity_id
            )

        options[entity_id] = selector.SelectOptionDict(
            value=entity_id,
            label=label,
        )

    return dict(sorted(options.items()))


def infrared_emitter_selector(
    available_emitters: dict[str, selector.SelectOptionDict],
    *,
    current_emitter_id: str | None = None,
) -> selector.SelectSelector:
    """Return an infrared emitter selector."""
    options = dict(available_emitters)

    if current_emitter_id and current_emitter_id not in options:
        options[current_emitter_id] = selector.SelectOptionDict(
            value=current_emitter_id,
            label=f"{current_emitter_id} (unavailable)",
        )

    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(options.values()),
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def infrared_emitter_field(
    default_emitter_id: str,
    available_emitters: dict[str, selector.SelectOptionDict],
) -> vol.Required:
    """Return a required infrared emitter field with a valid default if possible."""
    if default_emitter_id and default_emitter_id in available_emitters:
        return vol.Required(CONF_INFRARED_EMITTER_ID, default=default_emitter_id)

    return vol.Required(CONF_INFRARED_EMITTER_ID)


def infrared_emitter_field_with_current(
    default_emitter_id: str,
    _available_emitters: dict[str, selector.SelectOptionDict],
) -> vol.Required:
    """Return an infrared emitter field allowing a stale current emitter default."""
    if default_emitter_id:
        return vol.Required(CONF_INFRARED_EMITTER_ID, default=default_emitter_id)

    return vol.Required(CONF_INFRARED_EMITTER_ID)


def normalize_remote_id(name: str) -> str:
    """Create a stable id from a remote name."""
    value = name.strip().casefold().replace(" ", "_")
    value = _REMOTE_ID_RE.sub("_", value)
    value = value.strip("_")
    return value or "remote"


def unique_remote_id(
    name: str,
    remotes: list[dict[str, Any]],
    *,
    current_remote_id: str | None = None,
) -> str:
    """Create a remote id which is unique among configured remotes."""
    remote_id = normalize_remote_id(name)
    existing_ids = {
        str(remote.get(CONF_REMOTE_ID))
        for remote in remotes
        if remote.get(CONF_REMOTE_ID) != current_remote_id
    }

    if remote_id not in existing_ids:
        return remote_id

    counter = 2
    while f"{remote_id}_{counter}" in existing_ids:
        counter += 1

    return f"{remote_id}_{counter}"


def normalize_command_name(name: str) -> str:
    """Normalize a user-provided command name."""
    value = name.strip().upper().replace(" ", "_")
    value = _COMMAND_NAME_RE.sub("_", value)
    return value.strip("_")


def command_payload(command: Any) -> str | None:
    """Return command payload from a stored command value."""
    if isinstance(command, str) and command:
        return command

    if not isinstance(command, Mapping):
        return None

    data = command.get(CONF_COMMAND_DATA)
    return data if isinstance(data, str) and data else None


def command_create_button(command: Any) -> bool:
    """Return whether a stored command should expose a button entity."""
    return (
        isinstance(command, Mapping) and command.get(CONF_COMMAND_CREATE_BUTTON) is True
    )


def command_object(command_data: str, *, create_button: bool) -> dict[str, Any]:
    """Return a stored command object."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: create_button,
    }


def find_command_key(
    commands: Mapping[str, Any],
    normalized_command_name: str,
) -> str | None:
    """Return the existing command key matching a normalized command name."""
    return next(
        (
            command_name
            for command_name in commands
            if normalize_command_name(str(command_name)) == normalized_command_name
        ),
        None,
    )


def universal_remote_from_config_entry_data(
    value: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return a normalized single universal remote definition from config entry data."""
    remote_id = value.get(CONF_REMOTE_ID)
    name = value.get(CONF_REMOTE_NAME)
    infrared_emitter_id = value.get(CONF_INFRARED_EMITTER_ID)

    if (
        not isinstance(remote_id, str)
        or not remote_id
        or not isinstance(name, str)
        or not name
        or not isinstance(infrared_emitter_id, str)
        or not infrared_emitter_id
    ):
        return None

    remote: dict[str, Any] = {
        CONF_REMOTE_ID: remote_id,
        CONF_REMOTE_NAME: name,
        CONF_INFRARED_EMITTER_ID: infrared_emitter_id,
    }

    _copy_optional_codeset(value, remote)
    _copy_optional_device_type(value, remote)

    commands = normalize_command_objects(value.get(CONF_REMOTE_COMMANDS, {}))
    if commands:
        remote[CONF_REMOTE_COMMANDS] = commands

    return remote


def universal_remotes_from_config_entry(entry: ConfigEntry) -> list[dict[str, Any]]:
    """Return the single universal remote definition for a config entry."""
    single_remote = universal_remote_from_config_entry_data(
        {
            **entry.data,
            **entry.options,
        }
    )
    return [single_remote] if single_remote is not None else []


def command_options(commands: Mapping[str, Any]) -> list[selector.SelectOptionDict]:
    """Return selector options for command names."""
    return [
        selector.SelectOptionDict(value=command_name, label=command_name)
        for command_name in sorted(normalize_command_mapping(commands))
    ]


def normalize_command_mapping(value: Any) -> dict[str, str]:
    """Return a normalized command-name-to-payload mapping."""
    return {
        key: payload
        for key, command in normalize_command_objects(value).items()
        if (payload := command_payload(command)) is not None
    }


def normalize_command_objects(value: Any) -> dict[str, dict[str, Any]]:
    """Return normalized command objects."""
    if not isinstance(value, Mapping):
        return {}

    commands: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            continue

        if isinstance(item, str) and item:
            commands[key] = command_object(item, create_button=False)
            continue

        if not isinstance(item, Mapping):
            continue

        data = item.get(CONF_COMMAND_DATA)
        if not isinstance(data, str) or not data:
            continue

        commands[key] = command_object(
            data,
            create_button=item.get(CONF_COMMAND_CREATE_BUTTON) is True,
        )

    return commands


def _copy_optional_device_type(
    source: Mapping[str, Any],
    remote: dict[str, Any],
) -> None:
    """Copy or infer an universal remote device type."""
    device_type = source.get(CONF_REMOTE_DEVICE_TYPE)
    stored_device_type = (
        device_type
        if isinstance(device_type, str)
        and validate_infrared_library_device_type(device_type)
        else None
    )

    codeset = remote.get(CONF_REMOTE_CODESET)
    codeset_device_type = (
        infrared_library_codeset_device_type(codeset)
        if isinstance(codeset, str)
        else None
    )

    if codeset_device_type is not None:
        if stored_device_type is None or stored_device_type == DEVICE_TYPE_GENERIC:
            remote[CONF_REMOTE_DEVICE_TYPE] = codeset_device_type
            return

        if stored_device_type == codeset_device_type:
            remote[CONF_REMOTE_DEVICE_TYPE] = stored_device_type
            return

        remote.pop(CONF_REMOTE_CODESET, None)
        remote[CONF_REMOTE_DEVICE_TYPE] = stored_device_type
        return

    remote.pop(CONF_REMOTE_CODESET, None)
    remote[CONF_REMOTE_DEVICE_TYPE] = stored_device_type or DEVICE_TYPE_GENERIC


def _copy_optional_codeset(
    source: Mapping[str, Any],
    remote: dict[str, Any],
) -> None:
    """Copy a valid infrared library codeset into a remote definition."""
    codeset = source.get(CONF_REMOTE_CODESET)
    if (
        isinstance(codeset, str)
        and codeset
        and infrared_library_codeset_device_type(codeset) is not None
    ):
        remote[CONF_REMOTE_CODESET] = codeset
