"""Event entities for Universal Remote infrared receivers."""

from collections import deque
from enum import Enum
from functools import lru_cache
from importlib import import_module
import logging
from time import monotonic
from typing import Any, cast, override

from homeassistant.components import infrared
from homeassistant.components.event import EventEntity
from homeassistant.components.infrared import (
    InfraredReceivedSignal,
    InfraredReceiverConsumerEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from infrared_protocols.commands import Command

from .const import (
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
)
from .helpers import (
    universal_remote_from_config_entry_data,
    universal_remote_device_info,
)
from .infrared_library import (
    INFRARED_LIBRARY_CODESETS,
    NO_INFRARED_LIBRARY_CODESET,
    infrared_library_codeset_receiver_decoder_id,
    is_infrared_library_codeset_selected,
)
from .protocols import PROTOCOL_UNKNOWN
from .protocols.base import (
    CommandMatchKey,
    NormalizedInfraredCommand,
    ReceiveProtocolHandler,
)
from .protocols.registry import PROTOCOL_REGISTRY
from .runtime import UniversalRemoteData, UniversalRemoteRuntime
from .repairs import (
    async_create_linked_infrared_receiver_missing_issue,
    async_delete_linked_infrared_receiver_missing_issue,
    async_delete_stale_linked_infrared_receiver_missing_issues,
)

EVENT_UNKNOWN = "unknown"

MAX_RECEIVED_EVENT_HISTORY = 30
TIMINGS_PREVIEW_LENGTH = 12
NEC_REPEAT_ASSOCIATION_TIMEOUT = 0.5

_DIAGNOSTIC_RESERVED_EVENT_KEYS = frozenset(
    {
        "codeset",
        "decoder",
        "protocol",
        "decoded",
        "matched",
        "repeat",
        "command_name",
        "timings_count",
        "timings_preview",
        "modulation",
    }
)

_LOGGER = logging.getLogger(__name__)


type UniversalRemoteConfigEntry = ConfigEntry


def event_unique_id(remote_id: str) -> str:
    """Return the unique id for a received-command event entity."""
    return f"{remote_id}_received_command"


@callback
def cleanup_stale_received_command_event_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    expected_unique_ids: set[str],
) -> None:
    """Remove stale received-command event entity registry entries."""
    entity_registry = er.async_get(hass)

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "event":
            continue

        unique_id = entity_entry.unique_id
        if (
            isinstance(unique_id, str)
            and unique_id.endswith("_received_command")
            and unique_id not in expected_unique_ids
        ):
            entity_registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Universal Remote event entities from a config entry."""
    entities: list[UniversalRemoteReceivedCommandEventEntity] = []
    expected_unique_ids: set[str] = set()
    configured_receiver_remote_ids: set[str] = set()

    runtime_data = getattr(entry, "runtime_data", None)
    runtime = (
        runtime_data.runtime if isinstance(runtime_data, UniversalRemoteData) else None
    )

    remote = universal_remote_from_config_entry_data({**entry.data, **entry.options})
    if remote is not None:
        receiver_entity_id = remote.get(CONF_INFRARED_RECEIVER_ID)
        if isinstance(receiver_entity_id, str) and receiver_entity_id:
            remote_id = str(remote[CONF_REMOTE_ID])
            remote_name = str(remote[CONF_REMOTE_NAME])
            configured_receiver_remote_ids.add(remote_id)

            if receiver_entity_id not in infrared.async_get_receivers(hass):
                async_create_linked_infrared_receiver_missing_issue(
                    hass,
                    remote_id=remote_id,
                    remote_name=remote_name,
                    infrared_receiver_id=receiver_entity_id,
                )
            else:
                async_delete_linked_infrared_receiver_missing_issue(
                    hass,
                    remote_id=remote_id,
                )

            unique_id = event_unique_id(remote_id)
            expected_unique_ids.add(unique_id)
            codeset_id = str(
                remote.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET)
            )
            entities.append(
                UniversalRemoteReceivedCommandEventEntity(
                    remote_id=remote_id,
                    remote_name=remote_name,
                    receiver_entity_id=receiver_entity_id,
                    codeset_id=codeset_id,
                    runtime=runtime,
                )
            )

    async_delete_stale_linked_infrared_receiver_missing_issues(
        hass,
        configured_remote_ids=configured_receiver_remote_ids,
    )
    cleanup_stale_received_command_event_entities(hass, entry, expected_unique_ids)
    async_add_entities(entities)


class UniversalRemoteReceivedCommandEventEntity(
    InfraredReceiverConsumerEntity,
    EventEntity,
):
    """Event entity for commands received by an infrared receiver."""

    _attr_has_entity_name = True
    _attr_name = "Received command"

    def __init__(
        self,
        *,
        remote_id: str,
        remote_name: str,
        receiver_entity_id: str,
        codeset_id: str,
        runtime: UniversalRemoteRuntime | None = None,
    ) -> None:
        """Initialize the received command event entity."""
        self._runtime = runtime
        self._attr_unique_id = event_unique_id(remote_id)
        self._attr_device_info = universal_remote_device_info(remote_id, remote_name)
        self._infrared_receiver_entity_id = receiver_entity_id
        self._codeset_id = codeset_id
        self._attr_event_types = _event_types_for_codeset(codeset_id)
        self._received_event_history: deque[dict[str, Any]] = deque(
            maxlen=MAX_RECEIVED_EVENT_HISTORY,
        )
        self._last_decoded_event: dict[str, Any] | None = None
        self._last_decoded_event_time: float | None = None

    @override
    @callback
    def _handle_signal(self, signal: InfraredReceivedSignal) -> None:
        """Handle an infrared signal received by the linked receiver."""
        now = monotonic()
        previous_decoded_event = self._last_decoded_event
        if previous_decoded_event is not None and (
            self._last_decoded_event_time is None
            or now - self._last_decoded_event_time > NEC_REPEAT_ASSOCIATION_TIMEOUT
        ):
            previous_decoded_event = None
            self._last_decoded_event = None
            self._last_decoded_event_time = None

        event_type, event_data = _decode_signal_event(
            self._codeset_id,
            signal,
            previous_decoded_event=previous_decoded_event,
        )
        if event_data.get("decoded") and event_data.get("protocol") != PROTOCOL_UNKNOWN:
            self._last_decoded_event = {"event_type": event_type, **event_data}
            self._last_decoded_event_time = now
        elif event_data.get("repeat"):
            if previous_decoded_event is not None:
                self._last_decoded_event_time = now
            else:
                self._last_decoded_event = None
                self._last_decoded_event_time = None
        else:
            self._last_decoded_event = None
            self._last_decoded_event_time = None

        command_name = event_data.get("command_name")
        if (
            self._runtime is not None
            and event_data.get("matched")
            and not event_data.get("repeat")
            and isinstance(command_name, str)
        ):
            self._runtime.async_note_received_command(command_name)

        self._received_event_history.appendleft(
            {
                "event_type": event_type,
                **event_data,
            }
        )
        self._trigger_event(
            event_type,
            {
                **event_data,
                "recent_events": list(self._received_event_history),
            },
        )
        self.async_write_ha_state()


def receiver_event_types_for_codeset(codeset_id: str) -> list[str]:
    """Return received-command event types exposed by a receiver codeset."""
    return _event_types_for_codeset(codeset_id)


def _event_types_for_codeset(codeset_id: str) -> list[str]:
    """Return event types exposed by a receiver codeset."""
    event_types = {EVENT_UNKNOWN}

    decoder_id = infrared_library_codeset_receiver_decoder_id(codeset_id)
    handlers = _handlers_for_decoder(decoder_id)
    if not handlers:
        return sorted(event_types)

    event_types.update(handler.protocol_id for handler in handlers)
    event_types.update(_repeat_event_types_for_decoder(decoder_id))

    enum_cls = _load_codeset_enum(codeset_id)
    if enum_cls is not None:
        event_types.update(_event_type(member.name) for member in enum_cls)

    return sorted(event_types)


def _decode_signal_event(
    codeset_id: str,
    signal: InfraredReceivedSignal,
    *,
    previous_decoded_event: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Decode a received signal into a Home Assistant event type and data."""
    decoder_id = infrared_library_codeset_receiver_decoder_id(codeset_id)
    handlers = _handlers_for_decoder(decoder_id)
    event_data: dict[str, Any] = {
        "codeset": codeset_id,
        "decoder": decoder_id,
        "protocol": PROTOCOL_UNKNOWN,
        "decoded": False,
        "matched": False,
        "repeat": False,
    }

    if not is_infrared_library_codeset_selected(codeset_id) or not handlers:
        return EVENT_UNKNOWN, _with_timing_metadata(
            event_data,
            signal,
            handlers=handlers,
        )

    for handler in handlers:
        normalized_command = _decode_protocol_signal(handler, signal)
        if normalized_command is None:
            continue

        return _match_decoded_signal_event(
            codeset_id,
            event_data,
            normalized_command,
            handler,
        )

    repeat_event = _decode_repeat_signal_event(
        handlers,
        signal,
        event_data,
        previous_decoded_event=previous_decoded_event,
    )
    if repeat_event is not None:
        return repeat_event

    return EVENT_UNKNOWN, _with_timing_metadata(
        event_data,
        signal,
        handlers=handlers,
    )


def _decode_protocol_signal(
    handler: ReceiveProtocolHandler,
    signal: InfraredReceivedSignal,
) -> NormalizedInfraredCommand | None:
    """Decode a received signal using one registered protocol handler."""
    result = handler.decode(signal)
    if result is None:
        return None

    return result.normalized


def _match_decoded_signal_event(
    codeset_id: str,
    event_data: dict[str, Any],
    normalized_command: NormalizedInfraredCommand,
    handler: ReceiveProtocolHandler,
) -> tuple[str, dict[str, Any]]:
    """Match a normalized command against the selected library codeset."""
    event_data.update(
        {
            "protocol": normalized_command.protocol_id,
            "decoded": True,
            **normalized_command.event_data,
        }
    )

    command_name = _codeset_match_map(
        codeset_id,
        handler.protocol_id,
    ).get(normalized_command.match_key)
    if command_name is None:
        return handler.protocol_id, event_data

    event_data.update(
        {
            "matched": True,
            "command_name": command_name,
        }
    )
    return _event_type(command_name), event_data


def _decode_repeat_signal_event(
    handlers: tuple[ReceiveProtocolHandler, ...],
    signal: InfraredReceivedSignal,
    event_data: dict[str, Any],
    *,
    previous_decoded_event: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    """Decode a repeat frame through registered protocol handlers."""
    for handler in handlers:
        if handler.decode_repeat is None:
            continue

        repeat_result = handler.decode_repeat(
            signal,
            previous_decoded_event,
        )
        if repeat_result is None:
            continue

        repeat_data = {
            **event_data,
            "protocol": repeat_result.protocol_id,
            **repeat_result.event_data,
        }
        return repeat_result.event_type, _with_timing_metadata(
            repeat_data,
            signal,
            handlers=handlers,
        )

    return None


def _handlers_for_decoder(
    decoder_id: str | None,
) -> tuple[ReceiveProtocolHandler, ...]:
    """Return handlers in the registered decoder-family order."""
    return PROTOCOL_REGISTRY.handlers_for_family(decoder_id)


def _repeat_event_types_for_decoder(decoder_id: str | None) -> set[str]:
    """Return repeat event types exposed by a receiver decoder."""
    return {
        handler.repeat_event_type
        for handler in _handlers_for_decoder(decoder_id)
        if handler.repeat_event_type is not None
    }


@lru_cache(maxsize=None)
def _codeset_match_map(
    codeset_id: str,
    protocol_id: str,
) -> dict[CommandMatchKey, str]:
    """Return a protocol-aware match map for a receiver codeset."""
    handler = PROTOCOL_REGISTRY.handler_for_protocol(protocol_id)
    enum_cls = _load_codeset_enum(codeset_id)
    if handler is None or enum_cls is None:
        return {}

    match_map: dict[CommandMatchKey, str] = {}
    for member in enum_cls:
        library_command = _library_member_to_command(member)
        if library_command is None:
            continue

        normalized_command = handler.normalize(library_command)
        if normalized_command is None:
            continue

        match_map.setdefault(normalized_command.match_key, member.name)

    return match_map


def _with_timing_metadata(
    event_data: dict[str, Any],
    signal: InfraredReceivedSignal,
    *,
    handlers: tuple[ReceiveProtocolHandler, ...] = (),
) -> dict[str, Any]:
    """Return event data with timing and registered diagnostic metadata."""
    timings = list(signal.timings)
    timing_metadata: dict[str, Any] = {
        **event_data,
        "timings_count": len(timings),
        "timings_preview": timings[:TIMINGS_PREVIEW_LENGTH],
        "modulation": signal.modulation,
    }

    for key, value in _diagnostic_data_for_handlers(handlers, signal).items():
        if key in _DIAGNOSTIC_RESERVED_EVENT_KEYS or key in timing_metadata:
            continue
        timing_metadata[key] = value

    return timing_metadata


def _diagnostic_data_for_handlers(
    handlers: tuple[ReceiveProtocolHandler, ...],
    signal: InfraredReceivedSignal,
) -> dict[str, Any]:
    """Return merged diagnostics without executing shared callbacks twice."""
    diagnostic_data: dict[str, Any] = {}
    seen_callbacks: set[int] = set()

    for handler in handlers:
        builder = handler.diagnostic_data
        if builder is None or id(builder) in seen_callbacks:
            continue

        seen_callbacks.add(id(builder))
        diagnostic_data.update(builder(signal))

    return diagnostic_data


def _command_match_key(
    command: Command,
    *,
    protocol: str | None = None,
) -> CommandMatchKey | None:
    """Return a protocol-aware command matching key when possible."""
    if protocol is not None:
        handler = PROTOCOL_REGISTRY.handler_for_protocol(protocol)
        if handler is None:
            return None

        normalized_command = handler.normalize(command)
        return normalized_command.match_key if normalized_command is not None else None

    for handler in PROTOCOL_REGISTRY.handlers.values():
        normalized_command = handler.normalize(command)
        if normalized_command is not None:
            return normalized_command.match_key

    return None


def _library_member_to_command(member: Enum) -> Command | None:
    """Return the infrared command generated by a library enum member."""
    to_command = getattr(member, "to_command", None)
    if not callable(to_command):
        return None

    try:
        return cast(Command, to_command())
    except TypeError:
        try:
            return cast(Command, to_command(repeat_count=0))
        except TypeError:
            _LOGGER.debug(
                "Infrared library command %s does not expose a usable to_command",
                member.name,
            )
            return None


def _load_codeset_enum(codeset_id: str) -> type[Enum] | None:
    """Load the enum class for an infrared library codeset."""
    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    if codeset is None:
        return None

    try:
        enum_cls = getattr(import_module(codeset.module), codeset.enum_class)
    except (ImportError, AttributeError):
        return None

    if not isinstance(enum_cls, type) or not issubclass(enum_cls, Enum):
        return None

    return enum_cls


def _event_type(command_name: str) -> str:
    """Return the event type for a decoded command name."""
    return command_name.lower()
