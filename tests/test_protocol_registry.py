"""Tests for protocol-neutral contracts and registry validation."""

from typing import cast

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.commands import Command

from custom_components.universal_remote.protocols.base import (
    NormalizedInfraredCommand,
    ProtocolDecodeResult,
    ReceiveProtocolHandler,
)
from custom_components.universal_remote.protocols.registry import (
    ProtocolRegistryError,
    build_protocol_registry,
)


def _decode(
    _signal: InfraredReceivedSignal,
) -> ProtocolDecodeResult | None:
    """Return no decoded command for registry contract tests."""
    return None


def _normalize(
    _command: Command,
) -> NormalizedInfraredCommand | None:
    """Return no normalized command for registry contract tests."""
    return None


def _handler(protocol_id: str) -> ReceiveProtocolHandler:
    """Return a minimal fake receive protocol handler."""
    return ReceiveProtocolHandler(
        protocol_id=protocol_id,
        label_key=protocol_id,
        learning_confidence=100,
        decode=_decode,
        normalize=_normalize,
    )


def test_normalized_command_supports_non_nec_identity() -> None:
    """Test normalized identities do not assume NEC address fields."""
    normalized = NormalizedInfraredCommand(
        protocol_id="fake",
        identity=("device-a", 7, b"\x01\x02"),
        event_data={"device": "device-a", "function": 7},
    )
    command = cast(Command, object())
    result = ProtocolDecodeResult(
        command=command,
        normalized=normalized,
    )
    handler = _handler("fake")

    assert normalized.match_key == (
        "fake",
        "device-a",
        7,
        b"\x01\x02",
    )
    assert result.command is command
    assert result.normalized is normalized
    assert handler.protocol_id == "fake"
    assert handler.recognizes_repeat is None
    assert handler.diagnostic_data is None


def test_protocol_registry_preserves_family_order() -> None:
    """Test decoder families return handlers in declared order."""
    first = _handler("first")
    second = _handler("second")

    registry = build_protocol_registry(
        (first, second),
        {"family": ("second", "first")},
    )

    assert registry.handler_for_protocol("first") is first
    assert registry.handler_for_protocol("missing") is None
    assert registry.handlers_for_family("family") == (second, first)
    assert registry.handlers_for_family("missing") == ()
    assert registry.handlers_for_family(None) == ()
    assert registry.decoder_families["family"] == ("second", "first")


def test_protocol_registry_rejects_duplicate_protocol_ids() -> None:
    """Test duplicate concrete protocol IDs are rejected."""
    with pytest.raises(
        ProtocolRegistryError,
        match="Duplicate protocol id: duplicate",
    ):
        build_protocol_registry(
            (_handler("duplicate"), _handler("duplicate")),
            {},
        )


def test_protocol_registry_rejects_duplicate_family_members() -> None:
    """Test one protocol cannot occur twice in a decoder family."""
    with pytest.raises(
        ProtocolRegistryError,
        match="Decoder family family contains duplicate protocols",
    ):
        build_protocol_registry(
            (_handler("protocol"),),
            {"family": ("protocol", "protocol")},
        )


def test_protocol_registry_rejects_missing_family_members() -> None:
    """Test decoder families cannot reference unregistered protocols."""
    with pytest.raises(
        ProtocolRegistryError,
        match=(
            "Decoder family family references missing protocols: missing, also_missing"
        ),
    ):
        build_protocol_registry(
            (_handler("registered"),),
            {"family": ("registered", "missing", "also_missing")},
        )
