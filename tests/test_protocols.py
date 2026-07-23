"""Tests for Universal Remote infrared protocol helpers."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.codes.lg.tv import LGTVCodeJP
from infrared_protocols.commands import Command
from infrared_protocols.commands.nec import NECCommand

from custom_components.universal_remote import protocols as protocol_helpers


def _signal(
    timings: list[int] | None = None,
    *,
    modulation: int | None = None,
) -> InfraredReceivedSignal:
    """Return a fake InfraredReceivedSignal-like object."""
    return cast(
        InfraredReceivedSignal,
        SimpleNamespace(
            timings=timings or [243, -10000],
            modulation=modulation,
        ),
    )


def _nec1_f16_timings() -> list[int]:
    """Return valid NEC1-f16 timings for LG Japan DTV digit 2."""
    return LGTVCodeJP.DTV_NUM_2.to_command().get_raw_timings()


def test_nec_full_frame_debug_data_finds_leader_after_idle_timing() -> None:
    """Test NEC debug parsing can skip one leading idle timing."""
    event_data = protocol_helpers._nec_full_frame_debug_data(
        [100, *_nec1_f16_timings()]
    )

    assert event_data["nec_frame_candidate"] is True
    assert event_data["nec_leader_start_index"] == 1


def test_nec_full_frame_debug_data_reports_missing_leader() -> None:
    """Test NEC debug parsing reports a missing leader."""
    event_data = protocol_helpers._nec_full_frame_debug_data([100] * 67)

    assert event_data == {
        "nec_frame_candidate": False,
        "nec_parse_error": "leader",
    }


def test_nec_full_frame_debug_data_reports_invalid_bit_mark() -> None:
    """Test NEC debug parsing reports an invalid bit mark."""
    timings = _nec1_f16_timings()
    timings[2] = 100

    event_data = protocol_helpers._nec_full_frame_debug_data(timings)

    assert event_data["nec_frame_candidate"] is True
    assert event_data["nec_parse_error"] == "bit_0_mark"
    assert event_data["nec_parse_timing_index"] == 2
    assert event_data["nec_parse_timing_value"] == 100


def test_nec_full_frame_debug_data_reports_invalid_bit_space() -> None:
    """Test NEC debug parsing reports an invalid bit space."""
    timings = _nec1_f16_timings()
    timings[3] = -100

    event_data = protocol_helpers._nec_full_frame_debug_data(timings)

    assert event_data["nec_frame_candidate"] is True
    assert event_data["nec_parse_error"] == "bit_0_space"
    assert event_data["nec_parse_timing_index"] == 3
    assert event_data["nec_parse_timing_value"] == -100


def test_nec_bit_from_space_returns_none_for_invalid_space() -> None:
    """Test invalid NEC spaces are not decoded as bits."""
    assert protocol_helpers._nec_bit_from_space(100) is None


def test_is_nec_repeat_frame_rejects_long_or_invalid_frames() -> None:
    """Test invalid repeat candidates are rejected."""
    assert protocol_helpers._is_nec_repeat_frame([8894, -2250, 529, -10000, 1]) is False
    assert protocol_helpers._is_nec_repeat_frame([1, 2]) is False
    assert protocol_helpers._is_nec_repeat_frame([8894, -4500, 529]) is False


def test_decode_nec_signal_calls_library_decoder() -> None:
    """Test NEC decoding uses the infrared-protocols decoder."""
    signal = _signal()
    expected = NECCommand(address=0x01, command=0x02)

    with patch.object(
        protocol_helpers.NECCommand,
        "from_raw_timings",
        return_value=expected,
    ) as from_raw_timings:
        command = protocol_helpers._decode_nec_signal(signal)

    assert command is expected
    from_raw_timings.assert_called_once_with(signal.timings)


def test_decode_nec_signal_returns_none_on_decoder_errors() -> None:
    """Test NEC decoder errors are converted to no decoded command."""
    for error in (TypeError, ValueError):
        with patch.object(
            protocol_helpers.NECCommand,
            "from_raw_timings",
            side_effect=error,
        ):
            assert protocol_helpers._decode_nec_signal(_signal()) is None


def test_decode_nec1_f16_signal_enables_subfunction_decoding() -> None:
    """Test NEC1-f16 decoding enables NEC subfunction decoding."""
    signal = _signal()
    expected = NECCommand(
        address=0xFB04,
        command=0xDB,
        subfunction=0x32,
    )

    with patch.object(
        protocol_helpers.NECCommand,
        "from_raw_timings",
        return_value=expected,
    ) as from_raw_timings:
        command = protocol_helpers._decode_nec1_f16_signal(signal)

    assert command is expected
    from_raw_timings.assert_called_once_with(
        signal.timings,
        decode_subfunction=True,
    )


def test_decode_nec1_f16_signal_returns_none_on_decoder_errors() -> None:
    """Test NEC1-f16 decoder errors are converted to no decoded command."""
    for error in (TypeError, ValueError):
        with patch.object(
            protocol_helpers.NECCommand,
            "from_raw_timings",
            side_effect=error,
        ):
            assert protocol_helpers._decode_nec1_f16_signal(_signal()) is None


def test_nec_command_key_rejects_nec1_f16_command() -> None:
    """Test NEC1-f16 commands are not indexed as ordinary NEC commands."""
    command = NECCommand(
        address=0xFB04,
        command=0xDB,
        subfunction=0x32,
    )

    assert protocol_helpers._nec_command_key(command) is None


def test_nec_command_key_rejects_invalid_command_object() -> None:
    """Test NEC lookup keys are only built from integer address and command values."""
    assert protocol_helpers._nec_command_key(cast(Command, object())) is None
    assert (
        protocol_helpers._nec_command_key(
            cast(Command, SimpleNamespace(address="1", command=2))
        )
        is None
    )
    assert (
        protocol_helpers._nec_command_key(
            cast(Command, SimpleNamespace(address=1, command="2"))
        )
        is None
    )
