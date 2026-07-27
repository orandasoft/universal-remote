"""Tests for protocol-neutral contracts and registry validation."""

from typing import cast

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.codes.lg.tv import LGTVCodeJP
from infrared_protocols.commands import Command
from infrared_protocols.commands.nec import NECCommand

from custom_components.universal_remote.protocols import nec as nec_protocol
from custom_components.universal_remote.protocols.base import (
    NormalizedInfraredCommand,
    ProtocolDecodeResult,
    ReceiveProtocolHandler,
)
from custom_components.universal_remote.protocols.registry import (
    DECODER_FAMILIES,
    PROTOCOL_HANDLERS,
    PROTOCOL_REGISTRY,
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
    assert handler.decode_repeat is None
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


def _command_signal(command: Command) -> InfraredReceivedSignal:
    """Return a received signal generated from a library command."""
    return InfraredReceivedSignal(
        command.get_raw_timings(),
        modulation=38_000,
    )


def test_production_registry_contains_ordered_nec_family() -> None:
    """Test the production registry declares the NEC decoder family."""
    assert PROTOCOL_HANDLERS == {
        nec_protocol.PROTOCOL_NEC: nec_protocol.NEC_HANDLER,
        nec_protocol.PROTOCOL_NEC1_F16: nec_protocol.NEC1_F16_HANDLER,
    }
    assert DECODER_FAMILIES == {
        nec_protocol.PROTOCOL_NEC: (
            nec_protocol.PROTOCOL_NEC,
            nec_protocol.PROTOCOL_NEC1_F16,
        )
    }
    assert PROTOCOL_REGISTRY.handlers_for_family(nec_protocol.PROTOCOL_NEC) == (
        nec_protocol.NEC_HANDLER,
        nec_protocol.NEC1_F16_HANDLER,
    )


def test_nec_handler_decodes_normalized_identity() -> None:
    """Test the NEC handler returns the existing NEC identity and event data."""
    result = nec_protocol.NEC_HANDLER.decode(
        _command_signal(
            NECCommand(
                address=0xFB04,
                command=0x09,
            )
        )
    )

    assert result is not None
    assert result.normalized.protocol_id == nec_protocol.PROTOCOL_NEC
    assert result.normalized.match_key == (
        nec_protocol.PROTOCOL_NEC,
        0xFB04,
        0x09,
        None,
    )
    assert result.normalized.event_data == {
        "address": "0xFB04",
        "command": "0x09",
    }


def test_nec1_f16_handler_decodes_normalized_identity() -> None:
    """Test the NEC1-F16 handler preserves function and subfunction identity."""
    result = nec_protocol.NEC1_F16_HANDLER.decode(
        _command_signal(LGTVCodeJP.DTV_NUM_2.to_command())
    )

    assert result is not None
    assert result.normalized.protocol_id == nec_protocol.PROTOCOL_NEC1_F16
    assert result.normalized.match_key == (
        nec_protocol.PROTOCOL_NEC1_F16,
        0xFB04,
        0xDB,
        0x32,
    )
    assert result.normalized.event_data == {
        "address": "0xFB04",
        "function": "0xDB",
        "subfunction": "0x32",
    }


@pytest.mark.parametrize(
    "handler",
    (
        nec_protocol.NEC_HANDLER,
        nec_protocol.NEC1_F16_HANDLER,
    ),
)
def test_nec_handlers_reject_invalid_signals(
    handler: ReceiveProtocolHandler,
) -> None:
    """Test concrete NEC handlers reject undecodable timings."""
    assert (
        handler.decode(
            InfraredReceivedSignal(
                [1, 2],
                modulation=38_000,
            )
        )
        is None
    )


def test_nec_handler_normalizers_reject_unrelated_commands() -> None:
    """Test NEC normalizers reject commands without NEC identity fields."""
    command = cast(Command, object())

    assert nec_protocol._normalize_nec_identity(command) is None
    assert nec_protocol._normalize_nec1_f16_identity(command) is None


def test_nec_handler_optional_behaviors() -> None:
    """Test NEC repeat decoding and diagnostic callbacks."""
    repeat_signal = InfraredReceivedSignal(
        [9000, -2250, 562],
        modulation=38_000,
    )

    decode_repeat = nec_protocol.NEC_HANDLER.decode_repeat
    assert decode_repeat is not None

    repeat_without_previous = decode_repeat(repeat_signal, None)
    assert repeat_without_previous is not None
    assert repeat_without_previous.event_type == "nec_repeat"
    assert repeat_without_previous.protocol_id == nec_protocol.PROTOCOL_NEC
    assert repeat_without_previous.event_data == {"repeat": True}

    previous_event = {
        "event_type": "dtv_num_2",
        "protocol": nec_protocol.PROTOCOL_NEC1_F16,
        "address": "0xFB04",
        "function": "0xDB",
        "subfunction": "0x32",
        "command_name": "DTV_NUM_2",
    }
    repeat_with_previous = decode_repeat(
        repeat_signal,
        previous_event,
    )
    assert repeat_with_previous is not None
    assert repeat_with_previous.event_type == "nec_repeat"
    assert repeat_with_previous.protocol_id == nec_protocol.PROTOCOL_NEC1_F16
    assert repeat_with_previous.event_data == {
        "repeat": True,
        "previous_event_type": "dtv_num_2",
        "previous_protocol": nec_protocol.PROTOCOL_NEC1_F16,
        "previous_address": "0xFB04",
        "previous_command": None,
        "previous_function": "0xDB",
        "previous_subfunction": "0x32",
        "previous_command_name": "DTV_NUM_2",
    }

    assert (
        decode_repeat(
            InfraredReceivedSignal(
                [1, 2],
                modulation=38_000,
            ),
            None,
        )
        is None
    )
    assert nec_protocol.NEC1_F16_HANDLER.decode_repeat is None

    diagnostic_data = nec_protocol.NEC_HANDLER.diagnostic_data
    assert diagnostic_data is not None
    assert (
        diagnostic_data(
            InfraredReceivedSignal(
                [1, 2],
                modulation=38_000,
            )
        )
        == {}
    )

    assert (
        nec_protocol.NEC1_F16_HANDLER.diagnostic_data
        is nec_protocol.NEC_HANDLER.diagnostic_data
    )
