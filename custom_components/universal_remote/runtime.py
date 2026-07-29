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
from .profiles.capabilities.japanese_tuner import TunerCapability
from .resolved import ResolvedRemoteProfile
from .send import async_send_infrared_command


@dataclass(slots=True)
class UniversalRemoteData:
    """Runtime data stored on a Universal Remote config entry."""

    runtime: UniversalRemoteRuntime | None
    resolved_profile: ResolvedRemoteProfile | None = None


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
        tuner_capability: TunerCapability | None = None,
        translation_domain: str = DOMAIN,
    ) -> None:
        """Initialize the runtime."""
        self.hass = hass
        self.infrared_emitter_id = infrared_emitter_id
        self._commands = dict(commands)
        self._tuner_capability = tuner_capability
        self._translation_domain = translation_domain
        self._selected_tuner: str | None = None
        self._send_lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []

        self._commands_by_normalized_name: dict[str, str] = {}
        for configured_name in self._commands:
            normalized = normalize_command_name(configured_name)
            self._commands_by_normalized_name.setdefault(normalized, configured_name)

        self._available_tuners = (
            tuner_capability.available_tuners(self._commands)
            if tuner_capability is not None
            else ()
        )

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
        capability = self._tuner_capability
        if capability is None or not capability.update_after_received_match:
            return

        implied_tuner = capability.implied_tuner(command_name)
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
        capability = self._tuner_capability
        if capability is not None:
            routed_name = capability.routed_keypad_command_name(
                self._selected_tuner,
                command_name,
                self._commands,
            )
            if routed_name is not None:
                return ResolvedCommand(
                    requested_name=command_name,
                    command_name=routed_name,
                    payload=self._commands[routed_name],
                    configured=True,
                    implied_tuner=self._selected_tuner,
                    update_tuner_after_success=False,
                )

        configured_name = self._lookup_configured_name(command_name)
        if configured_name is not None:
            implied_tuner = (
                capability.implied_tuner(configured_name)
                if capability is not None
                else None
            )
            return ResolvedCommand(
                requested_name=command_name,
                command_name=configured_name,
                payload=self._commands[configured_name],
                configured=True,
                implied_tuner=implied_tuner,
                update_tuner_after_success=(
                    implied_tuner is not None
                    and capability is not None
                    and capability.update_after_sent_success
                ),
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
