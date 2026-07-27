"""Explicit receive-protocol and decoder-family registry."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .base import ReceiveProtocolHandler
from .nec import (
    NEC1_F16_HANDLER,
    NEC_HANDLER,
    PROTOCOL_NEC,
    PROTOCOL_NEC1_F16,
)


class ProtocolRegistryError(ValueError):
    """Raised when protocol registry definitions are invalid."""


@dataclass(frozen=True, slots=True)
class ProtocolRegistry:
    """Immutable protocol handlers and decoder-family ordering."""

    handlers: Mapping[str, ReceiveProtocolHandler]
    decoder_families: Mapping[str, tuple[str, ...]]

    def handler_for_protocol(
        self,
        protocol_id: str,
    ) -> ReceiveProtocolHandler | None:
        """Return the handler registered for one concrete protocol."""
        return self.handlers.get(protocol_id)

    def handlers_for_family(
        self,
        family_id: str | None,
    ) -> tuple[ReceiveProtocolHandler, ...]:
        """Return handlers in deterministic decoder-family order."""
        if family_id is None:
            return ()

        protocol_ids = self.decoder_families.get(family_id)
        if protocol_ids is None:
            return ()

        return tuple(self.handlers[protocol_id] for protocol_id in protocol_ids)


def build_protocol_registry(
    handlers: Iterable[ReceiveProtocolHandler],
    decoder_families: Mapping[str, tuple[str, ...]],
) -> ProtocolRegistry:
    """Validate and build an immutable protocol registry."""
    handler_map: dict[str, ReceiveProtocolHandler] = {}

    for handler in handlers:
        if handler.protocol_id in handler_map:
            raise ProtocolRegistryError(f"Duplicate protocol id: {handler.protocol_id}")
        handler_map[handler.protocol_id] = handler

    family_map: dict[str, tuple[str, ...]] = {}

    for family_id, protocol_ids in decoder_families.items():
        ordered_ids = tuple(protocol_ids)

        if len(set(ordered_ids)) != len(ordered_ids):
            raise ProtocolRegistryError(
                f"Decoder family {family_id} contains duplicate protocols"
            )

        missing_ids = [
            protocol_id for protocol_id in ordered_ids if protocol_id not in handler_map
        ]
        if missing_ids:
            missing = ", ".join(missing_ids)
            raise ProtocolRegistryError(
                f"Decoder family {family_id} references missing protocols: {missing}"
            )

        family_map[family_id] = ordered_ids

    return ProtocolRegistry(
        handlers=MappingProxyType(handler_map),
        decoder_families=MappingProxyType(family_map),
    )


PROTOCOL_HANDLERS: Mapping[str, ReceiveProtocolHandler] = MappingProxyType(
    {
        PROTOCOL_NEC: NEC_HANDLER,
        PROTOCOL_NEC1_F16: NEC1_F16_HANDLER,
    }
)

DECODER_FAMILIES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        PROTOCOL_NEC: (
            PROTOCOL_NEC,
            PROTOCOL_NEC1_F16,
        ),
    }
)

PROTOCOL_REGISTRY = build_protocol_registry(
    PROTOCOL_HANDLERS.values(),
    DECODER_FAMILIES,
)
