"""Protocol-neutral command-name normalization and lookup."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

_COMMAND_NAME_RE = re.compile(r"[^A-Z0-9_]+")


def normalize_command_name(name: str) -> str:
    """Normalize a user-provided command name."""
    value = name.strip().upper().replace(" ", "_")
    value = _COMMAND_NAME_RE.sub("_", value)
    return value.strip("_")


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


def find_configured_command(
    commands: Mapping[str, Any],
    command_name: str,
) -> tuple[str, Any] | None:
    """Return the configured command key and value matching a command name."""
    if command_name in commands:
        return command_name, commands[command_name]

    command_key = find_command_key(
        commands,
        normalize_command_name(command_name),
    )
    if command_key is None:
        return None

    return command_key, commands[command_key]
