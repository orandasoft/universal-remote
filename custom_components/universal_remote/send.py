"""Shared infrared send helpers for Universal Remote."""

import asyncio
from typing import Any

from homeassistant.components import infrared
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .command import parse_remote_command
from .const import DOMAIN


async def async_send_infrared_command(
    hass: HomeAssistant,
    infrared_entity_id: str,
    command_data: str,
    *,
    parse_kwargs: dict[str, Any] | None = None,
    translation_domain: str = DOMAIN,
    check_available: bool = True,
) -> None:
    """Send a stored infrared command payload through an infrared entity."""
    if check_available:
        state = hass.states.get(infrared_entity_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            raise HomeAssistantError(
                translation_domain=translation_domain,
                translation_key="remote_infrared_missing",
                translation_placeholders={"entity_id": infrared_entity_id},
            )

    ir_command = parse_remote_command(
        command_data,
        parse_kwargs or {},
        translation_domain=translation_domain,
    )

    try:
        await infrared.async_send_command(hass, infrared_entity_id, ir_command)
    except (asyncio.CancelledError, HomeAssistantError):
        raise
    except Exception as err:
        raise HomeAssistantError(
            translation_domain=translation_domain,
            translation_key="remote_send_failed",
            translation_placeholders={"error": str(err)},
        ) from err
