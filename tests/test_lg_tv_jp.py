"""Tests for the LG TV Japan infrared codeset override."""

from __future__ import annotations

from typing import Any, cast

import pytest
from infrared_protocols.commands.nec import NECCommand

from custom_components.universal_remote.lg_tv_jp import (
    LGTVCodeJP,
    NEC1F16Code,
    NECCode,
)
from custom_components.universal_remote.nec1_f16 import NEC1F16Command


class _BrokenLGTVCodeJPMember:
    """Invalid enum-like member used to test defensive error handling."""

    value = object()


def test_nec_code_builds_nec_command() -> None:
    """Test normal NEC code specs build NEC commands."""
    command = NECCode(0xFB04, 0x08).to_command(repeat_count=2)

    assert isinstance(command, NECCommand)
    assert command.address == 0xFB04
    assert command.command == 0x08
    assert command.repeat_count == 2


def test_nec1_f16_code_builds_nec1_f16_command() -> None:
    """Test NEC1-f16 code specs build NEC1-f16 commands."""
    command = NEC1F16Code(0xFB04, 0xDB, 0x32).to_command(repeat_count=1)

    assert isinstance(command, NEC1F16Command)
    assert command.address == 0xFB04
    assert command.function == 0xDB
    assert command.subfunction == 0x32
    assert command.repeat_count == 1


def test_lg_tv_jp_normal_command_uses_nec_command() -> None:
    """Test normal LG TV Japan commands use NEC encoding."""
    command = LGTVCodeJP.POWER.to_command()

    assert isinstance(command, NECCommand)
    assert command.address == 0xFB04
    assert command.command == 0x08


def test_lg_tv_jp_tuner_command_uses_nec1_f16_command() -> None:
    """Test Japan tuner selector commands use NEC1-f16 encoding."""
    command = LGTVCodeJP.DTV_NUM_2.to_command()

    assert isinstance(command, NEC1F16Command)
    assert command.address == 0xFB04
    assert command.function == 0xDB
    assert command.subfunction == 0x32

    decoded = NEC1F16Command.from_raw_timings(command.get_raw_timings())
    assert decoded is not None
    assert decoded.address == 0xFB04
    assert decoded.function == 0xDB
    assert decoded.subfunction == 0x32


def test_lg_tv_jp_rejects_invalid_member_value() -> None:
    """Test LG TV Japan enum rejects unsupported member value shapes."""
    invalid_member = cast(Any, _BrokenLGTVCodeJPMember())

    with pytest.raises(TypeError, match="not a supported code spec"):
        LGTVCodeJP.to_command(invalid_member)
