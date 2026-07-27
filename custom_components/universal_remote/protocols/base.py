"""Protocol-neutral infrared receive-handler contracts."""

from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.commands import Command


type CommandIdentity = tuple[Hashable, ...]
type CommandMatchKey = tuple[Hashable, ...]


@dataclass(frozen=True, slots=True)
class NormalizedInfraredCommand:
    """Protocol-neutral normalized command identity and safe event data."""

    protocol_id: str
    identity: CommandIdentity
    event_data: Mapping[str, Any]

    @property
    def match_key(self) -> CommandMatchKey:
        """Return the opaque protocol-aware matching key."""
        return (self.protocol_id, *self.identity)


@dataclass(frozen=True, slots=True)
class ProtocolDecodeResult:
    """Decoded infrared-protocols command and its normalized identity."""

    command: Command
    normalized: NormalizedInfraredCommand


type ProtocolSignalDecoder = Callable[
    [InfraredReceivedSignal],
    ProtocolDecodeResult | None,
]
type ProtocolCommandNormalizer = Callable[
    [Command],
    NormalizedInfraredCommand | None,
]


@dataclass(frozen=True, slots=True)
class ProtocolRepeatResult:
    """Protocol-specific repeat event identity and safe event data."""

    event_type: str
    protocol_id: str
    event_data: Mapping[str, Any]


type ProtocolRepeatDecoder = Callable[
    [
        InfraredReceivedSignal,
        Mapping[str, Any] | None,
    ],
    ProtocolRepeatResult | None,
]
type DiagnosticDataBuilder = Callable[
    [InfraredReceivedSignal],
    Mapping[str, Any],
]


@dataclass(frozen=True, slots=True)
class ReceiveProtocolHandler:
    """Receive-side behavior for one concrete infrared protocol."""

    protocol_id: str
    label_key: str
    learning_confidence: int
    decode: ProtocolSignalDecoder
    normalize: ProtocolCommandNormalizer
    repeat_event_type: str | None = None
    decode_repeat: ProtocolRepeatDecoder | None = None
    diagnostic_data: DiagnosticDataBuilder | None = None


@dataclass(frozen=True, slots=True)
class DecodedInfraredCommand:
    """Legacy NEC-shaped decoded command retained during migration."""

    protocol: str
    address: int
    primary: int
    secondary: int | None = None

    @property
    def match_key(self) -> CommandMatchKey:
        """Return the existing NEC-family matching key."""
        return (self.protocol, self.address, self.primary, self.secondary)
