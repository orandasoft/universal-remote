"""Tests for NEC1-f16 command encoding and decoding."""

from __future__ import annotations

from custom_components.universal_remote.nec1_f16 import NEC1F16Command


def test_nec1_f16_command_encodes_lg_jp_dtv_digit_2_bytes() -> None:
    """Test LG Japan DTV digit 2 encodes as NEC1-f16 bytes 04 FB DB 32."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )

    decoded = NEC1F16Command.from_raw_timings(command.get_raw_timings())

    assert decoded is not None
    assert decoded.address == 0xFB04
    assert decoded.function == 0xDB
    assert decoded.subfunction == 0x32
    assert decoded.modulation == 38_000
    assert decoded.repeat_count == 0


def test_nec1_f16_command_accepts_8_bit_device_address() -> None:
    """Test 8-bit NEC device addresses are encoded with an inverse address byte."""
    command = NEC1F16Command(
        address=0x04,
        function=0xDB,
        subfunction=0x32,
    )

    decoded = NEC1F16Command.from_raw_timings(command.get_raw_timings())

    assert decoded is not None
    assert decoded.address == 0xFB04
    assert decoded.function == 0xDB
    assert decoded.subfunction == 0x32


def test_nec1_f16_command_preserves_modulation_when_decoding() -> None:
    """Test decoded NEC1-f16 commands preserve the supplied modulation."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )

    decoded = NEC1F16Command.from_raw_timings(
        command.get_raw_timings(),
        modulation=40_000,
    )

    assert decoded is not None
    assert decoded.modulation == 40_000


def test_nec1_f16_command_counts_repeat_frames() -> None:
    """Test NEC1-f16 repeat frames are counted when present."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
        repeat_count=2,
    )

    decoded = NEC1F16Command.from_raw_timings(command.get_raw_timings())

    assert decoded is not None
    assert decoded.repeat_count == 2


def test_nec1_f16_decoder_ignores_malformed_repeat_tail() -> None:
    """Test malformed trailing repeat data does not increase repeat count."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )
    timings = command.get_raw_timings()
    timings.extend([-41_000, 9000, -2250, 100])

    decoded = NEC1F16Command.from_raw_timings(timings)

    assert decoded is not None
    assert decoded.repeat_count == 0


def test_nec1_f16_decoder_rejects_short_timing_list() -> None:
    """Test incomplete timing lists are rejected."""
    assert NEC1F16Command.from_raw_timings([9000, -4500]) is None


def test_nec1_f16_decoder_rejects_invalid_leader() -> None:
    """Test signals without an NEC leader are rejected."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )
    timings = command.get_raw_timings()
    timings[0] = 100

    assert NEC1F16Command.from_raw_timings(timings) is None


def test_nec1_f16_decoder_rejects_invalid_bit_mark() -> None:
    """Test data bits with invalid mark timings are rejected."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )
    timings = command.get_raw_timings()
    timings[2] = 100

    assert NEC1F16Command.from_raw_timings(timings) is None


def test_nec1_f16_decoder_rejects_invalid_bit_space() -> None:
    """Test data bits with invalid space timings are rejected."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )
    timings = command.get_raw_timings()
    timings[3] = -999

    assert NEC1F16Command.from_raw_timings(timings) is None


def test_nec1_f16_decoder_rejects_invalid_stop_bit() -> None:
    """Test signals with an invalid trailing stop mark are rejected."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    )
    timings = command.get_raw_timings()
    timings[66] = 100

    assert NEC1F16Command.from_raw_timings(timings) is None


def test_nec1_f16_command_accepts_explicit_16_bit_address() -> None:
    """Test explicit 16-bit addresses round-trip without checksum validation."""
    command = NEC1F16Command(
        address=0xFA04,
        function=0xDB,
        subfunction=0x32,
    )

    decoded = NEC1F16Command.from_raw_timings(command.get_raw_timings())

    assert decoded is not None
    assert decoded.address == 0xFA04
    assert decoded.function == 0xDB
    assert decoded.subfunction == 0x32


def test_nec1_f16_command_accepts_inverse_function_pair() -> None:
    """Test function/subfunction pairs are payload bytes, not a checksum."""
    command = NEC1F16Command(
        address=0xFB04,
        function=0x09,
        subfunction=0xF6,
    )

    decoded = NEC1F16Command.from_raw_timings(command.get_raw_timings())

    assert decoded is not None
    assert decoded.address == 0xFB04
    assert decoded.function == 0x09
    assert decoded.subfunction == 0xF6
