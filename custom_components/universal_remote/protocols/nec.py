"""NEC-family infrared protocol helpers."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.commands import Command
from infrared_protocols.commands.nec import NECCommand

from .base import (
    DecodedInfraredCommand,
    NormalizedInfraredCommand,
    ProtocolDecodeResult,
    ProtocolRepeatResult,
    ReceiveProtocolHandler,
)

PROTOCOL_NEC = "nec"
PROTOCOL_NEC1_F16 = "nec1_f16"
NEC_LEADER_HIGH = 9000
NEC_LEADER_LOW = 4500
NEC_REPEAT_LOW = 2250
NEC_BIT_HIGH = 562
NEC_ONE_LOW = 1687
NEC_ZERO_LOW = 562
NEC_REPEAT_TOLERANCE = 0.4
NEC_FULL_FRAME_TIMING_COUNT = 67
NEC_DATA_BIT_COUNT = 32


def _nec_full_frame_debug_data(timings: list[int]) -> dict[str, Any]:
    """Return best-effort NEC full-frame debug data.

    The infrared-protocols NEC decoder is authoritative for producing real
    commands. This helper only exposes timing-derived bytes when the decoder
    rejected a signal that still looks like a full NEC frame. That makes it
    easier to debug variants such as NEC2-f16 without treating them as matched
    commands.
    """
    if len(timings) < NEC_FULL_FRAME_TIMING_COUNT:
        return {}

    timing_values = list(timings)
    for start in range(min(3, len(timing_values) - NEC_FULL_FRAME_TIMING_COUNT + 1)):
        if not (
            _timing_is_close(abs(timing_values[start]), NEC_LEADER_HIGH)
            and _timing_is_close(abs(timing_values[start + 1]), NEC_LEADER_LOW)
        ):
            continue

        return _decode_nec_full_frame_debug_data(timing_values, start)

    return {
        "nec_frame_candidate": False,
        "nec_parse_error": "leader",
    }


def _decode_nec_full_frame_debug_data(
    timings: list[int],
    start: int,
) -> dict[str, Any]:
    """Decode NEC-like bytes from a full timing frame for diagnostics only."""
    bits: list[int] = []
    for bit_index in range(NEC_DATA_BIT_COUNT):
        timing_index = start + 2 + bit_index * 2
        mark = abs(timings[timing_index])
        space = abs(timings[timing_index + 1])

        if not _timing_is_close(mark, NEC_BIT_HIGH):
            return {
                "nec_frame_candidate": True,
                "nec_parse_error": f"bit_{bit_index}_mark",
                "nec_parse_timing_index": timing_index,
                "nec_parse_timing_value": timings[timing_index],
            }

        bit_value = _nec_bit_from_space(space)
        if bit_value is None:
            return {
                "nec_frame_candidate": True,
                "nec_parse_error": f"bit_{bit_index}_space",
                "nec_parse_timing_index": timing_index + 1,
                "nec_parse_timing_value": timings[timing_index + 1],
            }

        bits.append(bit_value)

    data_bytes = [
        _bits_to_lsb_byte(bits[index : index + 8])
        for index in range(0, NEC_DATA_BIT_COUNT, 8)
    ]
    address_low, address_high, command, command_inverse = data_bytes
    command_checksum_valid = command ^ command_inverse == 0xFF

    address_checksum_valid = address_low ^ address_high == 0xFF

    return {
        "nec_frame_candidate": True,
        "nec_leader_start_index": start,
        "nec_bytes": [_format_hex(value, 2) for value in data_bytes],
        "nec_address_checksum_valid": address_checksum_valid,
        "nec_command_checksum_valid": command_checksum_valid,
        "nec_decoder_address": _format_hex((address_high << 8) | address_low, 4),
        "nec_decoder_command": _format_hex(command, 2),
        "nec_decoder_command_inverse": _format_hex(command_inverse, 2),
        "nec1_f16_address": _format_hex((address_high << 8) | address_low, 4),
        "nec1_f16_function": _format_hex(command, 2),
        "nec1_f16_subfunction": _format_hex(command_inverse, 2),
    }


def _nec_bit_from_space(space: int) -> int | None:
    """Return the NEC bit represented by a space timing."""
    if _timing_is_close(space, NEC_ZERO_LOW):
        return 0
    if _timing_is_close(space, NEC_ONE_LOW):
        return 1
    return None


def _bits_to_lsb_byte(bits: list[int]) -> int:
    """Return a byte from eight least-significant-bit-first NEC bits."""
    value = 0
    for bit_index, bit in enumerate(bits):
        value |= bit << bit_index
    return value


def _format_hex(value: int, width: int) -> str:
    """Format an integer as an uppercase hexadecimal string."""
    return f"0x{value:0{width}X}"


def _is_nec_repeat_frame(timings: list[int]) -> bool:
    """Return true if timings look like a standalone NEC repeat frame."""
    timing_values = list(timings)
    if len(timing_values) < 3:
        return False

    for start in range(min(3, len(timing_values) - 2)):
        # Standalone NEC repeat frames are short. Allow one optional leading
        # idle timing and one optional trailing gap around the three timings.
        if len(timing_values) - start > 4:
            continue

        leader_high, repeat_low, final_high = timing_values[start : start + 3]
        if (
            _timing_is_close(abs(leader_high), NEC_LEADER_HIGH)
            and _timing_is_close(abs(repeat_low), NEC_REPEAT_LOW)
            and _timing_is_close(abs(final_high), NEC_BIT_HIGH)
        ):
            return True

    return False


def _timing_is_close(actual: int, expected: int) -> bool:
    """Return true if a received timing is close enough to expected."""
    margin = expected * NEC_REPEAT_TOLERANCE
    return expected - margin <= actual <= expected + margin


def _decode_nec_signal(signal: InfraredReceivedSignal) -> NECCommand | None:
    """Decode received timings as an NEC command."""
    try:
        return NECCommand.from_raw_timings(signal.timings)
    except (TypeError, ValueError):
        return None


def _decode_nec1_f16_signal(
    signal: InfraredReceivedSignal,
) -> NECCommand | None:
    """Decode received timings as an NEC1-f16 command."""
    try:
        return NECCommand.from_raw_timings(
            signal.timings,
            decode_subfunction=True,
        )
    except (TypeError, ValueError):
        return None


def _normalize_nec_command(command: Command) -> DecodedInfraredCommand | None:
    """Normalize a decoded NEC command for matching."""
    nec_key = _nec_command_key(command)
    if nec_key is None:
        return None

    address, command_value = nec_key
    return DecodedInfraredCommand(
        protocol=PROTOCOL_NEC,
        address=address,
        primary=command_value,
    )


def _normalize_nec1_f16_command(command: Command) -> DecodedInfraredCommand | None:
    """Normalize a decoded NEC1-f16 command for matching."""
    address = getattr(command, "address", None)
    function = getattr(command, "command", None)
    subfunction = getattr(command, "subfunction", None)

    if (
        isinstance(address, int)
        and isinstance(function, int)
        and isinstance(subfunction, int)
    ):
        return DecodedInfraredCommand(
            protocol=PROTOCOL_NEC1_F16,
            address=address,
            primary=function,
            secondary=subfunction,
        )

    return None


def _nec_command_key(command: Command) -> tuple[int, int] | None:
    """Return a comparable NEC command key."""
    address = getattr(command, "address", None)
    command_value = getattr(command, "command", None)
    subfunction = getattr(command, "subfunction", None)

    if (
        isinstance(address, int)
        and isinstance(command_value, int)
        and subfunction is None
    ):
        return (address, command_value)

    return None


def _normalize_nec_identity(
    command: Command,
) -> NormalizedInfraredCommand | None:
    """Normalize an NEC command through the protocol-neutral contract."""
    decoded = _normalize_nec_command(command)
    if decoded is None:
        return None

    return NormalizedInfraredCommand(
        protocol_id=PROTOCOL_NEC,
        identity=(decoded.address, decoded.primary, decoded.secondary),
        event_data={
            "address": _format_hex(decoded.address, 4),
            "command": _format_hex(decoded.primary, 2),
        },
    )


def _normalize_nec1_f16_identity(
    command: Command,
) -> NormalizedInfraredCommand | None:
    """Normalize an NEC1-F16 command through the protocol-neutral contract."""
    decoded = _normalize_nec1_f16_command(command)
    if decoded is None or decoded.secondary is None:
        return None

    return NormalizedInfraredCommand(
        protocol_id=PROTOCOL_NEC1_F16,
        identity=(decoded.address, decoded.primary, decoded.secondary),
        event_data={
            "address": _format_hex(decoded.address, 4),
            "function": _format_hex(decoded.primary, 2),
            "subfunction": _format_hex(decoded.secondary, 2),
        },
    )


def _decode_nec_result(
    signal: InfraredReceivedSignal,
) -> ProtocolDecodeResult | None:
    """Decode and normalize one NEC signal."""
    command = _decode_nec_signal(signal)
    if command is None:
        return None

    normalized = _normalize_nec_identity(command)
    assert normalized is not None

    return ProtocolDecodeResult(
        command=command,
        normalized=normalized,
    )


def _decode_nec1_f16_result(
    signal: InfraredReceivedSignal,
) -> ProtocolDecodeResult | None:
    """Decode and normalize one NEC1-F16 signal."""
    command = _decode_nec1_f16_signal(signal)
    if command is None:
        return None

    normalized = _normalize_nec1_f16_identity(command)
    assert normalized is not None

    return ProtocolDecodeResult(
        command=command,
        normalized=normalized,
    )


def _nec_learning_metadata(
    normalized: NormalizedInfraredCommand,
) -> dict[str, Any]:
    """Return learning metadata for a normalized NEC command."""
    address, primary, secondary = normalized.identity
    assert isinstance(address, int)
    assert isinstance(primary, int)
    assert secondary is None

    return {
        "address": _format_hex(address, 4),
        "primary": _format_hex(primary, 2),
    }


def _nec1_f16_learning_metadata(
    normalized: NormalizedInfraredCommand,
) -> dict[str, Any]:
    """Return learning metadata for a normalized NEC1-F16 command."""
    address, primary, secondary = normalized.identity
    assert isinstance(address, int)
    assert isinstance(primary, int)
    assert isinstance(secondary, int)

    return {
        "address": _format_hex(address, 4),
        "primary": _format_hex(primary, 2),
        "secondary": _format_hex(secondary, 2),
    }


def _decode_nec_repeat_result(
    signal: InfraredReceivedSignal,
    previous_event: Mapping[str, Any] | None,
) -> ProtocolRepeatResult | None:
    """Decode a standalone NEC repeat frame and its association metadata."""
    if not _is_nec_repeat_frame(signal.timings):
        return None

    protocol_id = (
        previous_event.get("protocol", PROTOCOL_NEC)
        if previous_event is not None
        else PROTOCOL_NEC
    )
    event_data: dict[str, Any] = {"repeat": True}

    if previous_event is not None:
        event_data.update(
            {
                "previous_event_type": previous_event.get("event_type"),
                "previous_protocol": previous_event.get("protocol"),
                "previous_address": previous_event.get("address"),
                "previous_command": previous_event.get("command"),
                "previous_function": previous_event.get("function"),
                "previous_subfunction": previous_event.get("subfunction"),
                "previous_command_name": previous_event.get("command_name"),
            }
        )

    return ProtocolRepeatResult(
        event_type="nec_repeat",
        protocol_id=protocol_id,
        event_data=event_data,
    )


def _nec_diagnostic_data(
    signal: InfraredReceivedSignal,
) -> dict[str, Any]:
    """Return privacy-safe NEC timing diagnostic data."""
    return _nec_full_frame_debug_data(list(signal.timings))


NEC_HANDLER = ReceiveProtocolHandler(
    protocol_id=PROTOCOL_NEC,
    label_key="nec",
    learning_confidence=200,
    decode=_decode_nec_result,
    normalize=_normalize_nec_identity,
    learning_label="NEC",
    learning_metadata=_nec_learning_metadata,
    repeat_event_type="nec_repeat",
    decode_repeat=_decode_nec_repeat_result,
    diagnostic_data=_nec_diagnostic_data,
)

NEC1_F16_HANDLER = ReceiveProtocolHandler(
    protocol_id=PROTOCOL_NEC1_F16,
    label_key="nec1_f16",
    learning_confidence=100,
    decode=_decode_nec1_f16_result,
    normalize=_normalize_nec1_f16_identity,
    learning_label="NEC1-F16",
    learning_metadata=_nec1_f16_learning_metadata,
    diagnostic_data=_nec_diagnostic_data,
)
