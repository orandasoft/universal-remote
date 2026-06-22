"""Tests for shared Universal Remote infrared send helpers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.universal_remote.send import async_send_infrared_command
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import RAW_COMMAND


async def test_async_send_infrared_command_sends_parsed_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test sending a stored infrared command parses and forwards it."""
    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await async_send_infrared_command(
            hass,
            infrared_emitter,
            "9000,4500,560,560",
            parse_kwargs={"carrier_frequency": 40_000},
        )

    mock_send.assert_awaited_once()
    await_args = mock_send.await_args
    assert await_args is not None
    sent_hass, sent_entity_id, sent_command = await_args.args
    assert sent_hass is hass
    assert sent_entity_id == infrared_emitter
    assert sent_command.modulation == 40_000
    assert sent_command.get_raw_timings()[0].high_us == 9000
    assert sent_command.get_raw_timings()[0].low_us == 4500


@pytest.mark.parametrize("entity_id", ["infrared.missing"])
async def test_async_send_infrared_command_raises_for_missing_entity(
    hass: HomeAssistant,
    entity_id: str,
) -> None:
    """Test sending checks that the infrared entity exists."""
    with pytest.raises(HomeAssistantError) as err:
        await async_send_infrared_command(hass, entity_id, RAW_COMMAND)

    assert err.value.translation_key == "remote_infrared_missing"
    assert err.value.translation_placeholders == {"entity_id": entity_id}


async def test_async_send_infrared_command_raises_for_unavailable_entity(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test sending checks that the infrared emitter is available."""
    hass.states.async_set(infrared_emitter, STATE_UNAVAILABLE)

    with pytest.raises(HomeAssistantError) as err:
        await async_send_infrared_command(hass, infrared_emitter, RAW_COMMAND)

    assert err.value.translation_key == "remote_infrared_missing"
    assert err.value.translation_placeholders == {"entity_id": infrared_emitter}


async def test_async_send_infrared_command_can_skip_availability_check(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test callers can skip the infrared emitter availability check."""
    emitter_id = "infrared.missing"

    with patch(
        "custom_components.universal_remote.send.infrared.async_send_command",
        AsyncMock(),
    ) as mock_send:
        await async_send_infrared_command(
            hass,
            emitter_id,
            RAW_COMMAND,
            check_available=False,
        )

    await_args = mock_send.await_args
    assert await_args is not None
    assert await_args.args[1] == emitter_id


async def test_async_send_infrared_command_preserves_home_assistant_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test HomeAssistantError raised by infrared send is preserved."""
    expected = HomeAssistantError("boom")

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(side_effect=expected),
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await async_send_infrared_command(hass, infrared_emitter, RAW_COMMAND)

    assert err.value is expected


async def test_async_send_infrared_command_wraps_unexpected_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test unexpected infrared send errors are wrapped."""
    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await async_send_infrared_command(hass, infrared_emitter, RAW_COMMAND)

    assert err.value.translation_key == "remote_send_failed"
    assert err.value.translation_placeholders == {"error": "boom"}


async def test_async_send_infrared_command_reraises_cancelled_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test cancellation is not wrapped as a send failure."""
    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            side_effect=asyncio.CancelledError,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await async_send_infrared_command(hass, infrared_emitter, RAW_COMMAND)
