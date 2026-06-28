"""Tests for Universal Remote infrared send helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.universal_remote.send import async_send_infrared_command


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
    assert await_args.kwargs == {}

    sent_hass, sent_entity_id, sent_command = await_args.args
    assert sent_hass is hass
    assert sent_entity_id == infrared_emitter
    assert sent_command.modulation == 40_000
    assert sent_command.get_raw_timings() == [9000, -4500, 560, -560]
    assert all(isinstance(timing, int) for timing in sent_command.get_raw_timings())


async def test_async_send_infrared_command_checks_infrared_entity_availability(
    hass: HomeAssistant,
) -> None:
    """Test sending fails before calling the infrared API if the emitter is missing."""
    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(),
        ) as mock_send,
        pytest.raises(HomeAssistantError) as exc,
    ):
        await async_send_infrared_command(
            hass,
            "infrared.missing",
            "9000,4500,560,560",
        )

    assert exc.value.translation_key == "remote_infrared_missing"
    mock_send.assert_not_awaited()


async def test_async_send_infrared_command_reraises_home_assistant_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test Home Assistant infrared API errors are not wrapped."""
    api_error = HomeAssistantError(
        translation_domain="universal_remote",
        translation_key="remote_infrared_missing",
        translation_placeholders={"entity_id": infrared_emitter},
    )

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(side_effect=api_error),
        ) as mock_send,
        pytest.raises(HomeAssistantError) as exc,
    ):
        await async_send_infrared_command(
            hass,
            infrared_emitter,
            "9000,4500,560,560",
        )

    assert exc.value is api_error
    mock_send.assert_awaited_once()


async def test_async_send_infrared_command_wraps_unexpected_api_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test unexpected infrared API errors are wrapped with translation metadata."""
    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(side_effect=RuntimeError("xiao failure")),
        ) as mock_send,
        pytest.raises(HomeAssistantError) as exc,
    ):
        await async_send_infrared_command(
            hass,
            infrared_emitter,
            "9000,4500,560,560",
        )

    assert exc.value.translation_key == "remote_send_failed"
    assert exc.value.translation_placeholders == {"error": "xiao failure"}
    mock_send.assert_awaited_once()
