"""Diagnostics support for Universal Remote."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .command_ui import command_is_media_player_source
from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
)
from .helpers import command_create_button, universal_remotes_from_config_entry
from .infrared_library import NO_INFRARED_LIBRARY_CODESET

TO_REDACT = {"device_id", "unique_id", "uuid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    remote_diagnostics = _diagnostic_remotes(hass, entry)

    diagnostics_data: dict[str, Any] = {
        "entry": async_redact_data(
            {
                "title": entry.title,
                "domain": entry.domain,
                "data": dict(entry.data),
                "options": _redacted_options(entry.options),
                "unique_id": entry.unique_id,
            },
            TO_REDACT,
        ),
        "summary": {
            "remote_count": len(remote_diagnostics),
            "command_count": sum(
                remote["command_count"] for remote in remote_diagnostics
            ),
            "button_count": sum(
                remote["button_count"] for remote in remote_diagnostics
            ),
            "media_player_count": sum(
                1 for remote in remote_diagnostics if remote["media_player_expected"]
            ),
            "missing_infrared_emitter_count": sum(
                1
                for remote in remote_diagnostics
                if remote["infrared_emitter_id"]
                and not remote["infrared_emitter_available"]
            ),
            "missing_infrared_receiver_count": sum(
                1
                for remote in remote_diagnostics
                if remote["infrared_receiver_id"]
                and not remote["infrared_receiver_available"]
            ),
        },
    }

    diagnostics_data["universal_remote"] = (
        remote_diagnostics[0] if remote_diagnostics else None
    )

    return diagnostics_data


def _redacted_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return options without full infrared command payloads."""
    redacted = dict(options)

    commands = redacted.get(CONF_REMOTE_COMMANDS)
    if isinstance(commands, dict):
        redacted[CONF_REMOTE_COMMANDS] = sorted(commands)

    return redacted


def _diagnostic_remotes(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> list[dict[str, Any]]:
    """Return sanitized universal remote diagnostics."""
    diagnostics: list[dict[str, Any]] = []
    for item in universal_remotes_from_config_entry(entry):
        infrared_emitter_id = item.get(CONF_INFRARED_EMITTER_ID)
        infrared_receiver_id = item.get(CONF_INFRARED_RECEIVER_ID)
        commands = item.get(CONF_REMOTE_COMMANDS, {})
        command_names = sorted(commands) if isinstance(commands, dict) else []
        button_count = (
            sum(1 for command in commands.values() if command_create_button(command))
            if isinstance(commands, dict)
            else 0
        )
        source_count = sum(
            1
            for command_name in command_names
            if command_is_media_player_source(command_name)
        )
        device_type = str(item.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC))
        infrared_emitter_state = (
            hass.states.get(infrared_emitter_id)
            if isinstance(infrared_emitter_id, str)
            else None
        )
        infrared_receiver_state = (
            hass.states.get(infrared_receiver_id)
            if isinstance(infrared_receiver_id, str)
            else None
        )
        diagnostics.append(
            {
                "id": item.get(CONF_REMOTE_ID),
                "name": item.get(CONF_REMOTE_NAME),
                "infrared_emitter_id": infrared_emitter_id,
                "infrared_emitter_exists": infrared_emitter_state is not None,
                "infrared_emitter_available": (
                    infrared_emitter_state is not None
                    and infrared_emitter_state.state != STATE_UNAVAILABLE
                ),
                "infrared_receiver_id": infrared_receiver_id,
                "infrared_receiver_exists": infrared_receiver_state is not None,
                "infrared_receiver_available": (
                    infrared_receiver_state is not None
                    and infrared_receiver_state.state != STATE_UNAVAILABLE
                ),
                "device_type": device_type,
                "codeset": item.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET),
                "media_player_expected": (
                    device_type == DEVICE_TYPE_TV
                    and isinstance(infrared_emitter_id, str)
                ),
                "button_count": button_count,
                "source_count": source_count,
                "command_count": len(commands) if isinstance(commands, dict) else 0,
                "commands": command_names,
            }
        )

    return diagnostics
