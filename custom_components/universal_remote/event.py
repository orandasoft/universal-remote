"""Event entities for Universal Remote infrared receivers."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from importlib import import_module
import logging
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
from .helpers import universal_remote_from_config_entry_data, universal_remote_device_info
from .infrared_library import (
    INFRARED_LIBRARY_CODESETS,
    NO_INFRARED_LIBRARY_CODESET,
    infrared_library_codeset_receiver_decoder_id,
    is_infrared_library_codeset_selected,
)
from .protocols import (
    PROTOCOL_NEC,
    PROTOCOL_NEC1_F16,
    PROTOCOL_UNKNOWN,
    CommandMatchKey,
    DecodedInfraredCommand,
    _decode_nec_signal,
    _decode_nec1_f16_signal,
    _format_hex,
    _is_nec_repeat_frame,
    _nec_full_frame_debug_data,
    _normalize_nec_command,
    _normalize_nec1_f16_command,
)
from .runtime import UniversalRemoteData, UniversalRemoteRuntime
from .repairs import (
    async_create_linked_infrared_receiver_missing_issue,
    async_delete_linked_infrared_receiver_missing_issue,
    async_delete_stale_linked_infrared_receiver_missing_issues,
)

EVENT_UNKNOWN = "unknown"
EVENT_NEC = "nec"
EVENT_NEC_REPEAT = "nec_repeat"
EVENT_NEC1_F16 = "nec1_f16"

MAX_RECEIVED_EVENT_HISTORY = 30
TIMINGS_PREVIEW_LENGTH = 12

_LOGGER = logging.getLogger(__name__)


type UniversalRemoteConfigEntry = ConfigEntry

type SignalDecoder = Callable[[InfraredReceivedSignal], Command | None]


type CommandNormalizer = Callable[[Command], DecodedInfraredCommand | None]
type CommandEventDataBuilder = Callable[[DecodedInfraredCommand], dict[str, Any]]
type RepeatDecoder = Callable[
    [InfraredReceivedSignal, dict[str, Any], dict[str, Any] | None],
    tuple[str, dict[str, Any]] | None,
]


@dataclass(frozen=True, slots=True)
class ProtocolSpec:
    """Infrared protocol decoding and matching behavior."""

    protocol: str
    event_type: str
    decode: SignalDecoder
    normalize: CommandNormalizer
    event_data_builder: CommandEventDataBuilder
    decode_repeat: RepeatDecoder | None = None
    repeat_event_type: str | None = None


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
        runtime_data.runtime
        if isinstance(runtime_data, UniversalRemoteData)
        else None
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

    @override
    @callback
    def _handle_signal(self, signal: InfraredReceivedSignal) -> None:
        """Handle an infrared signal received by the linked receiver."""
        event_type, event_data = _decode_signal_event(
            self._codeset_id,
            signal,
            previous_decoded_event=self._last_decoded_event,
        )
        if event_data.get("decoded") and event_data.get("protocol") != PROTOCOL_UNKNOWN:
            self._last_decoded_event = {"event_type": event_type, **event_data}
        elif not event_data.get("repeat"):
            self._last_decoded_event = None

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
    protocol_specs = _protocol_specs_for_decoder(decoder_id)
    if not protocol_specs:
        return sorted(event_types)

    event_types.update(spec.event_type for spec in protocol_specs)
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
    event_data: dict[str, Any] = {
        "codeset": codeset_id,
        "decoder": decoder_id,
        "protocol": PROTOCOL_UNKNOWN,
        "decoded": False,
        "matched": False,
        "repeat": False,
    }

    if not is_infrared_library_codeset_selected(codeset_id):
        return EVENT_UNKNOWN, _with_timing_metadata(
            event_data,
            signal,
            include_nec_debug=_decoder_supports_nec_debug(decoder_id),
        )

    protocol_specs = _protocol_specs_for_decoder(decoder_id)
    if not protocol_specs:
        return EVENT_UNKNOWN, _with_timing_metadata(
            event_data,
            signal,
            include_nec_debug=_decoder_supports_nec_debug(decoder_id),
        )

    for spec in protocol_specs:
        decoded_command = _decode_protocol_signal(spec, signal)
        if decoded_command is None:
            continue

        return _match_decoded_signal_event(
            codeset_id,
            event_data,
            decoded_command,
            spec,
        )

    repeat_event = _decode_repeat_signal_event(
        decoder_id,
        signal,
        event_data,
        previous_decoded_event=previous_decoded_event,
    )
    if repeat_event is not None:
        return repeat_event

    return EVENT_UNKNOWN, _with_timing_metadata(
        event_data,
        signal,
        include_nec_debug=_decoder_supports_nec_debug(decoder_id),
    )


def _decode_protocol_signal(
    spec: ProtocolSpec,
    signal: InfraredReceivedSignal,
) -> DecodedInfraredCommand | None:
    """Decode a received signal using one protocol spec."""
    command = spec.decode(signal)
    if command is None:
        return None

    decoded_command = spec.normalize(command)
    if decoded_command is None:
        return None

    return decoded_command


def _match_decoded_signal_event(
    codeset_id: str,
    event_data: dict[str, Any],
    decoded_command: DecodedInfraredCommand,
    spec: ProtocolSpec,
) -> tuple[str, dict[str, Any]]:
    """Match a decoded command against the selected library codeset."""
    event_data.update(
        {
            "protocol": decoded_command.protocol,
            "decoded": True,
            **spec.event_data_builder(decoded_command),
        }
    )

    command_name = _codeset_match_map(codeset_id, spec.protocol).get(
        decoded_command.match_key
    )
    if command_name is None:
        return spec.event_type, event_data

    event_data.update(
        {
            "matched": True,
            "command_name": command_name,
        }
    )
    return _event_type(command_name), event_data


def _decode_repeat_signal_event(
    decoder_id: str | None,
    signal: InfraredReceivedSignal,
    event_data: dict[str, Any],
    *,
    previous_decoded_event: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    """Decode protocol-specific repeat frames."""
    for spec in _protocol_specs_for_decoder(decoder_id):
        if spec.decode_repeat is None:
            continue

        repeat_event = spec.decode_repeat(signal, event_data, previous_decoded_event)
        if repeat_event is not None:
            return repeat_event

    return None


def _decode_nec_repeat_signal_event(
    signal: InfraredReceivedSignal,
    event_data: dict[str, Any],
    previous_decoded_event: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]] | None:
    """Decode a standalone NEC repeat frame."""
    if not _is_nec_repeat_frame(signal.timings):
        return None

    repeat_data = {
        **event_data,
        "protocol": previous_decoded_event.get("protocol", PROTOCOL_NEC)
        if previous_decoded_event is not None
        else PROTOCOL_NEC,
        "repeat": True,
    }
    if previous_decoded_event is not None:
        repeat_data.update(
            {
                "previous_event_type": previous_decoded_event.get("event_type"),
                "previous_protocol": previous_decoded_event.get("protocol"),
                "previous_address": previous_decoded_event.get("address"),
                "previous_command": previous_decoded_event.get("command"),
                "previous_function": previous_decoded_event.get("function"),
                "previous_subfunction": previous_decoded_event.get("subfunction"),
                "previous_command_name": previous_decoded_event.get("command_name"),
            }
        )

    return EVENT_NEC_REPEAT, _with_timing_metadata(repeat_data, signal)


def _protocol_specs_for_decoder(decoder_id: str | None) -> tuple[ProtocolSpec, ...]:
    """Return protocol specs to try for a receiver decoder id."""
    if decoder_id is None:
        return ()

    return _DECODER_PROTOCOL_SPECS.get(decoder_id, ())


def _protocol_spec_for_protocol(protocol: str) -> ProtocolSpec | None:
    """Return the protocol spec for a concrete protocol id."""
    return _PROTOCOL_SPECS_BY_PROTOCOL.get(protocol)


def _repeat_event_types_for_decoder(decoder_id: str | None) -> set[str]:
    """Return repeat event types exposed by a receiver decoder id."""
    return {
        spec.repeat_event_type
        for spec in _protocol_specs_for_decoder(decoder_id)
        if spec.repeat_event_type is not None
    }


def _decoder_supports_nec_debug(decoder_id: str | None) -> bool:
    """Return true if a receiver decoder should expose NEC timing debug data."""
    return any(
        spec.protocol in {PROTOCOL_NEC, PROTOCOL_NEC1_F16}
        for spec in _protocol_specs_for_decoder(decoder_id)
    )


@lru_cache(maxsize=None)
def _codeset_match_map(codeset_id: str, protocol: str) -> dict[CommandMatchKey, str]:
    """Return a protocol-aware match map for a receiver codeset."""
    spec = _protocol_spec_for_protocol(protocol)
    enum_cls = _load_codeset_enum(codeset_id)
    if spec is None or enum_cls is None:
        return {}

    match_map: dict[CommandMatchKey, str] = {}
    for member in enum_cls:
        library_command = _library_member_to_command(member)
        if library_command is None:
            continue

        match_key = _command_match_key(library_command, protocol=protocol)
        if match_key is None:
            continue

        match_map.setdefault(match_key, member.name)

    return match_map


def _with_timing_metadata(
    event_data: dict[str, Any],
    signal: InfraredReceivedSignal,
    *,
    include_nec_debug: bool = True,
) -> dict[str, Any]:
    """Return event data with a small received-timing summary."""
    timings = list(signal.timings)
    timing_metadata: dict[str, Any] = {
        **event_data,
        "timings_count": len(timings),
        "timings_preview": timings[:TIMINGS_PREVIEW_LENGTH],
        "modulation": signal.modulation,
    }
    if include_nec_debug:
        timing_metadata.update(_nec_full_frame_debug_data(timings))

    return timing_metadata


def _nec_command_event_data(decoded_command: DecodedInfraredCommand) -> dict[str, Any]:
    """Return event attributes for a decoded NEC command."""
    return {
        "address": _format_hex(decoded_command.address, 4),
        "command": _format_hex(decoded_command.primary, 2),
    }


def _nec1_f16_command_event_data(
    decoded_command: DecodedInfraredCommand,
) -> dict[str, Any]:
    """Return event attributes for a decoded NEC1-f16 command."""
    if decoded_command.secondary is None:
        raise ValueError("NEC1-f16 decoded command is missing subfunction")

    return {
        "address": _format_hex(decoded_command.address, 4),
        "function": _format_hex(decoded_command.primary, 2),
        "subfunction": _format_hex(decoded_command.secondary, 2),
    }


def _command_match_key(
    command: Command,
    *,
    protocol: str | None = None,
) -> CommandMatchKey | None:
    """Return a protocol-aware command matching key when possible."""
    if protocol is not None:
        spec = _protocol_spec_for_protocol(protocol)
        if spec is None:
            return None

        decoded_command = spec.normalize(command)
        return decoded_command.match_key if decoded_command is not None else None

    for spec in _PROTOCOL_SPECS_BY_PROTOCOL.values():
        decoded_command = spec.normalize(command)
        if decoded_command is not None:
            return decoded_command.match_key

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


NEC_PROTOCOL_SPEC = ProtocolSpec(
    protocol=PROTOCOL_NEC,
    event_type=EVENT_NEC,
    decode=_decode_nec_signal,
    normalize=_normalize_nec_command,
    event_data_builder=_nec_command_event_data,
    decode_repeat=_decode_nec_repeat_signal_event,
    repeat_event_type=EVENT_NEC_REPEAT,
)

NEC1_F16_PROTOCOL_SPEC = ProtocolSpec(
    protocol=PROTOCOL_NEC1_F16,
    event_type=EVENT_NEC1_F16,
    decode=_decode_nec1_f16_signal,
    normalize=_normalize_nec1_f16_command,
    event_data_builder=_nec1_f16_command_event_data,
)

_DECODER_PROTOCOL_SPECS: dict[str, tuple[ProtocolSpec, ...]] = {
    PROTOCOL_NEC: (NEC_PROTOCOL_SPEC, NEC1_F16_PROTOCOL_SPEC),
}

_PROTOCOL_SPECS_BY_PROTOCOL: dict[str, ProtocolSpec] = {
    spec.protocol: spec
    for protocol_specs in _DECODER_PROTOCOL_SPECS.values()
    for spec in protocol_specs
}
