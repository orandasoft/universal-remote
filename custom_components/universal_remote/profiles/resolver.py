"""Profile-based command resolution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..command_names import find_configured_command
from .base import DeviceProfile


def profile_role_commands(
    profile: DeviceProfile,
    commands: Mapping[str, Any],
) -> dict[str, str]:
    """Return profile roles mapped to configured command names."""
    roles: dict[str, str] = {}

    for role in profile.roles:
        for candidate_name in role.candidates:
            configured_command = find_configured_command(
                commands,
                candidate_name,
            )
            if configured_command is not None:
                roles[role.role_id] = configured_command[0]
                break

    return roles


def profile_source_commands(
    profile: DeviceProfile,
    commands: Mapping[str, Any],
) -> dict[str, str]:
    """Return profile source labels mapped to configured command names."""
    sources: dict[str, str] = {}

    for source in profile.sources:
        for candidate_name in source.candidates:
            configured_command = find_configured_command(
                commands,
                candidate_name,
            )
            if configured_command is not None:
                sources[source.label] = configured_command[0]
                break

    return sources


def command_is_profile_source(
    profile: DeviceProfile,
    command_name: str,
) -> bool:
    """Return whether one command matches a profile source rule."""
    return bool(
        profile_source_commands(
            profile,
            {command_name: None},
        )
    )
