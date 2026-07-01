"""Tests for Universal Remote runtime command resolution."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.universal_remote.const import DOMAIN
from custom_components.universal_remote.runtime import UniversalRemoteRuntime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import INFRARED_EMITTER_ID, RAW_COMMAND

RAW_COMMAND_ALT = "38000:9000,2250,560,560"
RAW_COMMAND_THIRD = "38000:4500,4500,560,560"


def _runtime(
    hass: HomeAssistant,
    commands: dict[str, str],
) -> UniversalRemoteRuntime:
    """Create a runtime for tests."""
    return UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands=commands,
    )


async def test_available_tuners_require_selector_and_tuner_number(
    hass: HomeAssistant,
) -> None:
    """Test available tuners are detected from command names."""
    runtime = _runtime(
        hass,
        {
            "BS": RAW_COMMAND,
            "DTV": RAW_COMMAND,
            "DTV_NUM_1": RAW_COMMAND,
            "CS4K": RAW_COMMAND,
            "CS4K_NUM_12": RAW_COMMAND,
        },
    )

    assert runtime.available_tuners == ("DTV", "CS4K")


async def test_tuner_not_available_when_only_selector_exists(
    hass: HomeAssistant,
) -> None:
    """Test a selector without tuner-specific numbers is not exposed."""
    runtime = _runtime(hass, {"BS": RAW_COMMAND})

    assert runtime.available_tuners == ()


async def test_num_without_selected_tuner_sends_num(
    hass: HomeAssistant,
) -> None:
    """Test NUM command sends as-is before a tuner is selected."""
    runtime = _runtime(hass, {"NUM_1": RAW_COMMAND})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name("NUM_1")

    await_args = mock_send.await_args

    assert await_args is not None

    assert await_args.args == (hass, INFRARED_EMITTER_ID, RAW_COMMAND)
    assert await_args.kwargs == {
        "parse_kwargs": {},
        "translation_domain": DOMAIN,
        "check_available": True,
    }
    assert runtime.selected_tuner is None


async def test_tuner_send_updates_after_success(
    hass: HomeAssistant,
) -> None:
    """Test tuner selector updates selected tuner after successful send."""
    runtime = _runtime(
        hass,
        {
            "BS": RAW_COMMAND,
            "BS_NUM_1": RAW_COMMAND_ALT,
        },
    )

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name("bs")

    await_args = mock_send.await_args

    assert await_args is not None

    assert await_args.args == (hass, INFRARED_EMITTER_ID, RAW_COMMAND)
    assert runtime.selected_tuner == "BS"


async def test_tuner_send_does_not_update_after_failed_send(
    hass: HomeAssistant,
) -> None:
    """Test tuner selector does not update selected tuner when send fails."""
    runtime = _runtime(hass, {"BS": RAW_COMMAND})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(
            side_effect=HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="remote_send_failed",
                translation_placeholders={"error": "boom"},
            )
        ),
    ):
        with pytest.raises(HomeAssistantError) as err:
            await runtime.async_send_command_name("BS")

    assert err.value.translation_key == "remote_send_failed"
    assert runtime.selected_tuner is None


async def test_num_overlays_after_selected_tuner(
    hass: HomeAssistant,
) -> None:
    """Test NUM command resolves through selected tuner when available."""
    runtime = _runtime(
        hass,
        {
            "BS": RAW_COMMAND,
            "NUM_1": RAW_COMMAND_ALT,
            "BS_NUM_1": RAW_COMMAND_THIRD,
        },
    )

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name("BS")
        await runtime.async_send_command_name("NUM_1")

    assert [call.args[2] for call in mock_send.await_args_list] == [
        RAW_COMMAND,
        RAW_COMMAND_THIRD,
    ]
    assert runtime.selected_tuner == "BS"


async def test_num_falls_back_when_tuner_specific_command_missing(
    hass: HomeAssistant,
) -> None:
    """Test NUM command falls back when tuner-specific command is missing."""
    runtime = _runtime(
        hass,
        {
            "BS": RAW_COMMAND,
            "NUM_1": RAW_COMMAND_ALT,
        },
    )

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name("BS")
        await runtime.async_send_command_name("NUM_1")

    assert [call.args[2] for call in mock_send.await_args_list] == [
        RAW_COMMAND,
        RAW_COMMAND_ALT,
    ]
    assert runtime.selected_tuner == "BS"


async def test_direct_tuner_number_updates_selected_tuner(
    hass: HomeAssistant,
) -> None:
    """Test direct tuner-specific number command updates selected tuner."""
    runtime = _runtime(hass, {"BS_NUM_1": RAW_COMMAND})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ):
        await runtime.async_send_command_name("BS_NUM_1")

    assert runtime.selected_tuner == "BS"


async def test_received_command_updates_selected_tuner(
    hass: HomeAssistant,
) -> None:
    """Test received command updates selected tuner."""
    runtime = _runtime(hass, {})

    runtime.async_note_received_command("BS_NUM_1")

    assert runtime.selected_tuner == "BS"


async def test_received_unknown_command_does_not_update_selected_tuner(
    hass: HomeAssistant,
) -> None:
    """Test received unknown command does not update selected tuner."""
    runtime = _runtime(hass, {})

    runtime.async_note_received_command("POWER")

    assert runtime.selected_tuner is None


async def test_raw_fallback_does_not_update_selected_tuner(
    hass: HomeAssistant,
) -> None:
    """Test raw fallback sends payload and does not update tuner state."""
    runtime = _runtime(hass, {})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name(RAW_COMMAND, allow_raw=True)

    await_args = mock_send.await_args

    assert await_args is not None

    assert await_args.args == (hass, INFRARED_EMITTER_ID, RAW_COMMAND)
    assert runtime.selected_tuner is None


async def test_allow_raw_false_rejects_unknown_command(
    hass: HomeAssistant,
) -> None:
    """Test unknown command is rejected when raw fallback is disabled."""
    runtime = _runtime(hass, {})

    with pytest.raises(HomeAssistantError) as err:
        await runtime.async_send_command_name("UNKNOWN")

    assert err.value.translation_key == "remote_command_missing"
    assert err.value.translation_placeholders == {"command": "UNKNOWN"}


async def test_invalid_raw_fallback_uses_unknown_or_invalid_error(
    hass: HomeAssistant,
) -> None:
    """Test invalid raw fallback preserves remote service error style."""
    runtime = _runtime(hass, {})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(
            side_effect=HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="remote_invalid_command",
                translation_placeholders={"error": "bad command"},
            )
        ),
    ):
        with pytest.raises(HomeAssistantError) as err:
            await runtime.async_send_command_name("UNKNOWN", allow_raw=True)

    assert err.value.translation_key == "remote_unknown_or_invalid_command"
    assert err.value.translation_placeholders == {"command": "UNKNOWN"}


async def test_configured_invalid_payload_preserves_parser_error(
    hass: HomeAssistant,
) -> None:
    """Test configured invalid payload does not fall back to raw input."""
    runtime = _runtime(hass, {"BROKEN": ""})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(
            side_effect=HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="remote_invalid_command",
                translation_placeholders={"error": "Command cannot be empty"},
            )
        ),
    ):
        with pytest.raises(HomeAssistantError) as err:
            await runtime.async_send_command_name("BROKEN", allow_raw=True)

    assert err.value.translation_key == "remote_invalid_command"


async def test_missing_emitter_error_is_not_wrapped_as_unknown_raw_command(
    hass: HomeAssistant,
) -> None:
    """Test missing emitter error is not wrapped for raw fallback."""
    runtime = _runtime(hass, {})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(
            side_effect=HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="remote_infrared_missing",
                translation_placeholders={"entity_id": INFRARED_EMITTER_ID},
            )
        ),
    ):
        with pytest.raises(HomeAssistantError) as err:
            await runtime.async_send_command_name(RAW_COMMAND, allow_raw=True)

    assert err.value.translation_key == "remote_infrared_missing"


async def test_listener_called_only_when_selected_tuner_changes(
    hass: HomeAssistant,
) -> None:
    """Test tuner listeners are called only when tuner changes."""
    runtime = _runtime(hass, {})
    listener = Mock()
    remove_listener = runtime.async_add_tuner_listener(listener)

    runtime.async_note_received_command("BS")
    runtime.async_note_received_command("BS")
    runtime.async_note_received_command("DTV")

    assert listener.call_count == 2

    remove_listener()
    runtime.async_note_received_command("CS1")

    assert listener.call_count == 2


async def test_command_sequence_repeats_delay_and_overlay_order(
    hass: HomeAssistant,
) -> None:
    """Test command sequence order, repeat handling, delay, and overlay."""
    runtime = _runtime(
        hass,
        {
            "BS": RAW_COMMAND,
            "NUM_1": RAW_COMMAND_ALT,
            "BS_NUM_1": RAW_COMMAND_THIRD,
        },
    )

    with (
        patch(
            "custom_components.universal_remote.runtime.async_send_infrared_command",
            AsyncMock(),
        ) as mock_send,
        patch("custom_components.universal_remote.runtime.asyncio.sleep", AsyncMock())
        as mock_sleep,
    ):
        await runtime.async_send_command_sequence(
            ["BS", "NUM_1"],
            num_repeats=2,
            delay_secs=0.5,
        )

    assert [call.args[2] for call in mock_send.await_args_list] == [
        RAW_COMMAND,
        RAW_COMMAND_THIRD,
        RAW_COMMAND,
        RAW_COMMAND_THIRD,
    ]
    assert mock_sleep.await_count == 3
    assert runtime.selected_tuner == "BS"


async def test_duplicate_normalized_commands_preserve_lookup_behavior(
    hass: HomeAssistant,
) -> None:
    """Test exact key wins and first normalized key wins."""
    runtime = _runtime(
        hass,
        {
            "Power On": RAW_COMMAND,
            "POWER_ON": RAW_COMMAND_ALT,
        },
    )

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name("POWER_ON")
        await runtime.async_send_command_name("power on")

    assert [call.args[2] for call in mock_send.await_args_list] == [
        RAW_COMMAND_ALT,
        RAW_COMMAND,
    ]


async def test_runtime_supports_empty_command_map_for_raw_remote_send(
    hass: HomeAssistant,
) -> None:
    """Test runtime works with empty commands for raw remote service usage."""
    runtime = _runtime(hass, {})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_name(
            RAW_COMMAND,
            allow_raw=True,
            check_available=False,
        )

    await_args = mock_send.await_args

    assert await_args is not None

    assert await_args.args == (hass, INFRARED_EMITTER_ID, RAW_COMMAND)
    assert await_args.kwargs["check_available"] is False


async def test_empty_command_sequence_does_nothing(
    hass: HomeAssistant,
) -> None:
    """Test empty command sequence does not send anything."""
    runtime = _runtime(hass, {"BS": RAW_COMMAND})

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await runtime.async_send_command_sequence(
            [],
            num_repeats=1,
            delay_secs=0,
        )

    mock_send.assert_not_awaited()
    assert runtime.selected_tuner is None


async def test_remove_tuner_listener_is_idempotent(
    hass: HomeAssistant,
) -> None:
    """Test removing a tuner listener twice is safe."""
    runtime = _runtime(hass, {})
    listener = Mock()

    remove_listener = runtime.async_add_tuner_listener(listener)

    remove_listener()
    remove_listener()

    runtime.async_note_received_command("BS")

    listener.assert_not_called()
