"""Runtime command resolution for Universal Remote."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .helpers import normalize_command_name
from .send import async_send_infrared_command

JAPANESE_TUNERS: tuple[str, ...] = ("DTV", "BS", "CS1", "CS2", "BS4K", "CS4K")
JAPANESE_NUMBERS = range(1, 13)


@dataclass(slots=True)
class UniversalRemoteData:
    """Runtime data stored on a Universal Remote config entry."""

    runtime: UniversalRemoteRuntime | None


@dataclass(frozen=True, slots=True)
class ResolvedCommand:
    """Resolved command ready to send through an infrared emitter."""

    requested_name: str
    command_name: str | None
    payload: str
    configured: bool
    implied_tuner: str | None
    update_tuner_after_success: bool


class UniversalRemoteRuntime:
    """Resolve and send Universal Remote commands with assumed tuner state."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        infrared_emitter_id: str,
        commands: Mapping[str, str],
        translation_domain: str = DOMAIN,
    ) -> None:
        """Initialize the runtime."""
        self.hass = hass
        self.infrared_emitter_id = infrared_emitter_id
        self._commands = dict(commands)
        self._translation_domain = translation_domain
        self._selected_tuner: str | None = None
        self._send_lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []

        self._commands_by_normalized_name: dict[str, str] = {}
        for configured_name in self._commands:
            normalized = normalize_command_name(configured_name)
            self._commands_by_normalized_name.setdefault(normalized, configured_name)

        self._available_tuners = self._detect_available_tuners()

    @property
    def selected_tuner(self) -> str | None:
        """Return the current assumed tuner."""
        return self._selected_tuner

    @property
    def available_tuners(self) -> tuple[str, ...]:
        """Return tuner selectors with tuner-specific keypad support."""
        return self._available_tuners

    async def async_send_command_name(
        self,
        command_name: str,
        *,
        parse_kwargs: Mapping[str, Any] | None = None,
        check_available: bool = True,
        allow_raw: bool = False,
    ) -> None:
        """Send one command by configured command name."""
        await self.async_send_command_sequence(
            [command_name],
            num_repeats=1,
            delay_secs=0,
            parse_kwargs=parse_kwargs,
            check_available=check_available,
            allow_raw=allow_raw,
        )

    async def async_send_command_sequence(
        self,
        command_names: Iterable[str],
        *,
        num_repeats: int,
        delay_secs: float,
        parse_kwargs: Mapping[str, Any] | None = None,
        check_available: bool = True,
        allow_raw: bool = False,
    ) -> None:
        """Send a sequence of command names in order."""
        commands = (
            [command_names] if isinstance(command_names, str) else list(command_names)
        )
        if not commands:
            return

        kwargs = dict(parse_kwargs or {})
        total = len(commands) * num_repeats
        sent = 0

        async with self._send_lock:
            for _ in range(num_repeats):
                for command_name in commands:
                    resolved = self._resolve_command(command_name, allow_raw=allow_raw)
                    await self._async_send_resolved_command(
                        resolved,
                        parse_kwargs=kwargs,
                        check_available=check_available,
                    )
                    self._apply_sent_tuner_update(resolved)
                    sent += 1

                    if delay_secs and sent < total:
                        await asyncio.sleep(delay_secs)

    @callback
    def async_note_received_command(self, command_name: str) -> None:
        """Update assumed tuner state from a matched physical received command."""
        implied_tuner = self._implied_tuner(command_name)
        if implied_tuner is not None:
            self._set_selected_tuner(implied_tuner)

    @callback
    def async_add_tuner_listener(
        self,
        listener: Callable[[], None],
    ) -> Callable[[], None]:
        """Register a listener for tuner state changes."""
        self._listeners.append(listener)

        @callback
        def _remove_listener() -> None:
            """Remove a tuner listener."""
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return _remove_listener

    def _detect_available_tuners(self) -> tuple[str, ...]:
        """Return tuners that have selector and tuner-specific number commands."""
        normalized_commands = {
            normalize_command_name(command_name) for command_name in self._commands
        }
        tuners: list[str] = []

        for tuner in JAPANESE_TUNERS:
            if tuner not in normalized_commands:
                continue

            if any(
                f"{tuner}_NUM_{number}" in normalized_commands
                for number in JAPANESE_NUMBERS
            ):
                tuners.append(tuner)

        return tuple(tuners)

    def _lookup_configured_name(self, command_name: str) -> str | None:
        """Return the configured command key matching a command name."""
        if command_name in self._commands:
            return command_name

        return self._commands_by_normalized_name.get(
            normalize_command_name(command_name)
        )

    def _resolve_command(
        self, command_name: str, *, allow_raw: bool
    ) -> ResolvedCommand:
        """Resolve a requested command name to a payload."""
        normalized_name = normalize_command_name(command_name)

        if self._selected_tuner is not None and self._is_keypad_number(normalized_name):
            tuner_command_name = f"{self._selected_tuner}_{normalized_name}"
            configured_tuner_name = self._lookup_configured_name(tuner_command_name)
            if configured_tuner_name is not None:
                return ResolvedCommand(
                    requested_name=command_name,
                    command_name=configured_tuner_name,
                    payload=self._commands[configured_tuner_name],
                    configured=True,
                    implied_tuner=self._selected_tuner,
                    update_tuner_after_success=False,
                )

        configured_name = self._lookup_configured_name(command_name)
        if configured_name is not None:
            implied_tuner = self._implied_tuner(configured_name)
            return ResolvedCommand(
                requested_name=command_name,
                command_name=configured_name,
                payload=self._commands[configured_name],
                configured=True,
                implied_tuner=implied_tuner,
                update_tuner_after_success=implied_tuner is not None,
            )

        if allow_raw:
            return ResolvedCommand(
                requested_name=command_name,
                command_name=None,
                payload=command_name,
                configured=False,
                implied_tuner=None,
                update_tuner_after_success=False,
            )

        raise HomeAssistantError(
            translation_domain=self._translation_domain,
            translation_key="remote_command_missing",
            translation_placeholders={"command": command_name},
        )

    async def _async_send_resolved_command(
        self,
        resolved: ResolvedCommand,
        *,
        parse_kwargs: dict[str, Any],
        check_available: bool,
    ) -> None:
        """Send a resolved command payload."""
        try:
            await async_send_infrared_command(
                self.hass,
                self.infrared_emitter_id,
                resolved.payload,
                parse_kwargs=parse_kwargs,
                translation_domain=self._translation_domain,
                check_available=check_available,
            )
        except HomeAssistantError as err:
            if resolved.configured:
                raise

            if getattr(err, "translation_key", None) == "remote_infrared_missing":
                raise

            raise HomeAssistantError(
                translation_domain=self._translation_domain,
                translation_key="remote_unknown_or_invalid_command",
                translation_placeholders={"command": resolved.requested_name},
            ) from err

    def _apply_sent_tuner_update(self, resolved: ResolvedCommand) -> None:
        """Apply tuner state change after a successful send."""
        if resolved.update_tuner_after_success and resolved.implied_tuner is not None:
            self._set_selected_tuner(resolved.implied_tuner)

    def _set_selected_tuner(self, tuner: str) -> None:
        """Set selected tuner and notify listeners when it changes."""
        if self._selected_tuner == tuner:
            return

        self._selected_tuner = tuner
        for listener in list(self._listeners):
            listener()

    @staticmethod
    def _is_keypad_number(normalized_name: str) -> bool:
        """Return whether a normalized command is NUM_1 through NUM_12."""
        return any(normalized_name == f"NUM_{number}" for number in JAPANESE_NUMBERS)

    @staticmethod
    def _implied_tuner(command_name: str) -> str | None:
        """Return tuner implied by a command name."""
        normalized_name = normalize_command_name(command_name)

        for tuner in JAPANESE_TUNERS:
            if normalized_name == tuner:
                return tuner

            if any(
                normalized_name == f"{tuner}_NUM_{number}"
                for number in JAPANESE_NUMBERS
            ):
                return tuner

        return None
