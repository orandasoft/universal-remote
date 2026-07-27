"""Protocol helpers for Universal Remote infrared receiving and learning."""

from collections.abc import Callable

from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.commands import Command
from infrared_protocols.commands.nec import NECCommand as NECCommand

from .base import (
    CommandMatchKey as CommandMatchKey,
    DecodedInfraredCommand as DecodedInfraredCommand,
)
from .nec import (
    NEC_BIT_HIGH as NEC_BIT_HIGH,
    NEC_DATA_BIT_COUNT as NEC_DATA_BIT_COUNT,
    NEC_FULL_FRAME_TIMING_COUNT as NEC_FULL_FRAME_TIMING_COUNT,
    NEC_LEADER_HIGH as NEC_LEADER_HIGH,
    NEC_LEADER_LOW as NEC_LEADER_LOW,
    NEC_ONE_LOW as NEC_ONE_LOW,
    NEC_REPEAT_LOW as NEC_REPEAT_LOW,
    NEC_REPEAT_TOLERANCE as NEC_REPEAT_TOLERANCE,
    NEC_ZERO_LOW as NEC_ZERO_LOW,
    PROTOCOL_NEC as PROTOCOL_NEC,
    PROTOCOL_NEC1_F16 as PROTOCOL_NEC1_F16,
    _bits_to_lsb_byte as _bits_to_lsb_byte,
    _decode_nec1_f16_signal as _decode_nec1_f16_signal,
    _decode_nec_full_frame_debug_data as _decode_nec_full_frame_debug_data,
    _decode_nec_signal as _decode_nec_signal,
    _format_hex as _format_hex,
    _is_nec_repeat_frame as _is_nec_repeat_frame,
    _nec_bit_from_space as _nec_bit_from_space,
    _nec_command_key as _nec_command_key,
    _nec_full_frame_debug_data as _nec_full_frame_debug_data,
    _normalize_nec1_f16_command as _normalize_nec1_f16_command,
    _normalize_nec_command as _normalize_nec_command,
    _timing_is_close as _timing_is_close,
)

PROTOCOL_UNKNOWN = "unknown"

type SignalDecoder = Callable[[InfraredReceivedSignal], Command | None]
