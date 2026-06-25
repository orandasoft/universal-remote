"""Event entities for Universal Remote infrared receivers."""

from enum import Enum
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
from infrared_protocols.commands.nec import NECCommand

from .const import (
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from .helpers import universal_remote_from_config_entry_data
from .infrared_library import (
    INFRARED_LIBRARY_CODESETS,
    NO_INFRARED_LIBRARY_CODESET,
    infrared_library_codeset_receiver_decoder_id,
    is_infrared_library_codeset_selected,
)
from .repairs import (
    async_create_linked_infrared_receiver_missing_issue,
    async_delete_linked_infrared_receiver_missing_issue,
    async_delete_stale_linked_infrared_receiver_missing_issues,
)

EVENT_UNKNOWN = "unknown"

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
    ) -> None:
        """Initialize the received command event entity."""
        self._attr_unique_id = event_unique_id(remote_id)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, remote_id)},
            "name": remote_name,
        }
        self._infrared_receiver_entity_id = receiver_entity_id
        self._codeset_id = codeset_id
        self._attr_event_types = _event_types_for_codeset(codeset_id)

    @override
    @callback
    def _handle_signal(self, signal: InfraredReceivedSignal) -> None:
        """Handle an infrared signal received by the linked receiver."""
        event_type = _decode_signal_event_type(self._codeset_id, signal)
        self._trigger_event(event_type)
        self.async_write_ha_state()


def _event_types_for_codeset(codeset_id: str) -> list[str]:
    """Return event types exposed by a receiver codeset."""
    event_types = {EVENT_UNKNOWN}

    enum_cls = _load_codeset_enum(codeset_id)
    if enum_cls is not None:
        event_types.update(_event_type(member.name) for member in enum_cls)

    return sorted(event_types)


def _decode_signal_event_type(
    codeset_id: str,
    signal: InfraredReceivedSignal,
) -> str:
    """Decode a received signal into a Home Assistant event type."""
    if not is_infrared_library_codeset_selected(codeset_id):
        return EVENT_UNKNOWN

    if infrared_library_codeset_receiver_decoder_id(codeset_id) != "nec":
        return EVENT_UNKNOWN

    received_command = _decode_nec_signal(signal)
    if received_command is None:
        return EVENT_UNKNOWN

    received_key = _nec_command_key(received_command)
    if received_key is None:
        return EVENT_UNKNOWN

    enum_cls = _load_codeset_enum(codeset_id)
    if enum_cls is None:
        return EVENT_UNKNOWN

    for member in enum_cls:
        library_command = _library_member_to_command(member)
        if library_command is None:
            continue

        if _nec_command_key(library_command) == received_key:
            return _event_type(member.name)

    return EVENT_UNKNOWN


def _decode_nec_signal(signal: InfraredReceivedSignal) -> NECCommand | None:
    """Decode received timings as an NEC command."""
    try:
        return cast(
            NECCommand,
            NECCommand.from_raw_timings(
                signal.timings,
                modulation=signal.modulation,
            ),
        )
    except TypeError:
        try:
            return cast(NECCommand, NECCommand.from_raw_timings(signal.timings))
        except (TypeError, ValueError):
            return None
    except ValueError:
        return None


def _library_member_to_command(member: Enum) -> Any | None:
    """Return the infrared command generated by a library enum member."""
    to_command = getattr(member, "to_command", None)
    if not callable(to_command):
        return None

    try:
        return to_command()
    except TypeError:
        try:
            return to_command(repeat_count=0)
        except TypeError:
            _LOGGER.debug(
                "Infrared library command %s does not expose a usable to_command",
                member.name,
            )
            return None


def _nec_command_key(command: Any) -> tuple[int, int] | None:
    """Return a comparable NEC command key."""
    address = getattr(command, "address", None)
    command_value = getattr(command, "command", None)

    if isinstance(address, int) and isinstance(command_value, int):
        return (address, command_value)

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
