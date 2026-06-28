"""Tests for Universal Remote command parsing and infrared API calls."""

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.universal_remote.command import (
    DEFAULT_CARRIER_FREQUENCY,
    CommandParseError,
    RawInfraredCommand,
    _parse_json_command,
    _parse_pronto_command,
    parse_remote_command,
    validate_remote_command_payload,
)
from custom_components.universal_remote.send import async_send_infrared_command


INFRARED_ENTITY_ID = "infrared.xiao_ir_blaster"


def assert_infrared_command_contract(
    command: RawInfraredCommand,
    *,
    modulation: int,
    timings: list[int],
) -> None:
    """Assert a command object matches the Home Assistant infrared API."""
    assert command.modulation == modulation
    assert command.get_raw_timings() == timings
    assert all(type(timing) is int for timing in command.get_raw_timings())


def test_raw_infrared_command_matches_infrared_command_contract() -> None:
    """Test raw commands expose the command API expected by infrared emitters."""
    command = RawInfraredCommand(
        modulation=38_000,
        timings=[9000, 4500, 560, 560],
    )

    assert_infrared_command_contract(
        command,
        modulation=38_000,
        timings=[9000, -4500, 560, -560],
    )


def test_raw_infrared_command_copies_timings() -> None:
    """Test raw commands do not expose the caller's mutable timing list."""
    timings = [9000, 4500, 560, 560]
    command = RawInfraredCommand(modulation=38_000, timings=timings)

    timings[0] = 1

    assert command.get_raw_timings() == [9000, -4500, 560, -560]


def test_parse_text_command_returns_infrared_command_contract() -> None:
    """Test text timing payloads return an infrared command-compatible object."""
    command = parse_remote_command("40000:9000,4500,560,560")

    assert_infrared_command_contract(
        command,
        modulation=40_000,
        timings=[9000, -4500, 560, -560],
    )


def test_parse_json_command_returns_infrared_command_contract() -> None:
    """Test JSON timing payloads return an infrared command-compatible object."""
    command = parse_remote_command(
        '{"modulation": 38000, "timings": [9000, 4500, 560, 560]}'
    )

    assert_infrared_command_contract(
        command,
        modulation=DEFAULT_CARRIER_FREQUENCY,
        timings=[9000, -4500, 560, -560],
    )


def test_parse_json_array_command_returns_infrared_command_contract() -> None:
    """Test bare JSON timing arrays use the default modulation."""
    command = parse_remote_command("[9000, 4500, 560, 560]")

    assert_infrared_command_contract(
        command,
        modulation=DEFAULT_CARRIER_FREQUENCY,
        timings=[9000, -4500, 560, -560],
    )


def test_parse_json_command_uses_carrier_frequency_alias() -> None:
    """Test JSON commands accept the carrier_frequency alias."""
    command = parse_remote_command(
        '{"carrier_frequency": "40000", "timings": ["9000", "4500", "560", "560"]}'
    )

    assert_infrared_command_contract(
        command,
        modulation=40_000,
        timings=[9000, -4500, 560, -560],
    )


def test_parse_json_command_uses_default_modulation() -> None:
    """Test JSON object commands use the default modulation when omitted."""
    command = parse_remote_command('{"timings": [9000, 4500, 560, 560]}')

    assert_infrared_command_contract(
        command,
        modulation=DEFAULT_CARRIER_FREQUENCY,
        timings=[9000, -4500, 560, -560],
    )


def test_parse_pronto_command_returns_infrared_command_contract() -> None:
    """Test learned Pronto payloads return an infrared command-compatible object."""
    command = parse_remote_command(
        "0000 006D 0002 0000 0152 00AA 0014 0017"
    )

    assert_infrared_command_contract(
        command,
        modulation=38_029,
        timings=[8888, -4470, 526, -605],
    )


def test_validate_remote_command_payload_accepts_valid_command() -> None:
    """Test valid persisted command payloads can be validated."""
    validate_remote_command_payload("9000,4500,560,560")


@pytest.mark.parametrize(
    "raw_command",
    [
        "",
        "{",
        '{"modulation": true, "timings": [9000, 4500, 560, 560]}',
        '{"modulation": "bad", "timings": [9000, 4500, 560, 560]}',
        '{"modulation": 38.0, "timings": [9000, 4500, 560, 560]}',
        '{"timings": "9000,4500,560,560"}',
        '[9000, "", 560, 560]',
        '[9000, "bad", 560, 560]',
        "abc:9000,4500,560,560",
        "0000 006D 002 0000 0152 00AA",
        "0000 006D ZZZZ 0000 0152 00AA",
        "0000 006D 0000 0000",
        "0000 0000 0001 0000 0001 0001",
        "0000 006D 0000 0000 0001 0001",
        "0000 006D 0002 0000 0152 00AA",
        "0000 006D 0001 0000 0000 0001",
        "0:9000,4500,560,560",
        "[]",
        "9000,0,560,560",
        "9000,4500,560",
    ],
)
def test_parse_remote_command_rejects_invalid_payloads(raw_command: str) -> None:
    """Test invalid command payloads raise a Home Assistant error."""
    with pytest.raises(HomeAssistantError):
        parse_remote_command(raw_command)


def test_parse_json_command_rejects_non_sequence_payload() -> None:
    """Test the JSON parser rejects payloads that are not arrays or objects."""
    with pytest.raises(CommandParseError):
        _parse_json_command("123", DEFAULT_CARRIER_FREQUENCY)  # noqa: SLF001


def test_parse_pronto_command_rejects_unsupported_pronto_type() -> None:
    """Test the Pronto parser rejects non-learned Pronto commands."""
    with pytest.raises(CommandParseError):
        _parse_pronto_command(  # noqa: SLF001
            "0100 006D 0001 0000 0152 00AA"
        )


async def test_async_send_infrared_command_calls_infrared_api_with_command_contract(
    hass: HomeAssistant,
) -> None:
    """Test the HA infrared API is called with a compatible command object."""
    hass.states.async_set(INFRARED_ENTITY_ID, "on")
    await hass.async_block_till_done()

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        new_callable=AsyncMock,
    ) as mock_send_command:
        await async_send_infrared_command(
            hass,
            INFRARED_ENTITY_ID,
            "38000:9000,4500,560,560",
        )

    mock_send_command.assert_awaited_once()

    await_args = mock_send_command.await_args
    assert await_args is not None
    assert await_args.kwargs == {}

    sent_hass, sent_entity_id, sent_command = await_args.args
    assert sent_hass is hass
    assert sent_entity_id == INFRARED_ENTITY_ID
    assert_infrared_command_contract(
        sent_command,
        modulation=DEFAULT_CARRIER_FREQUENCY,
        timings=[9000, -4500, 560, -560],
    )


async def test_async_send_infrared_command_checks_infrared_entity_availability(
    hass: HomeAssistant,
) -> None:
    """Test the send helper does not call the infrared API for missing emitters."""
    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        new_callable=AsyncMock,
    ) as mock_send_command:
        with pytest.raises(HomeAssistantError):
            await async_send_infrared_command(
                hass,
                INFRARED_ENTITY_ID,
                "38000:9000,4500,560,560",
            )

    mock_send_command.assert_not_awaited()
