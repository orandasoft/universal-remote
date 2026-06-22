"""Tests for Universal Remote command buttons."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

from custom_components.universal_remote.button import (
    UniversalRemoteButton,
    UniversalRemoteButtonEntityDescription,
    button_unique_id,
    cleanup_stale_button_entities,
)
from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import RAW_COMMAND, REMOTE_ID, REMOTE_NAME

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _command_object(command_data: str, *, create_button: bool) -> dict[str, object]:
    """Return a stored command object."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: create_button,
    }


def _button_entry(hass: HomeAssistant, infrared_emitter: str) -> MockConfigEntry:
    """Create a config entry with one command button enabled."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER_ON": _command_object(
                    RAW_COMMAND,
                    create_button=True,
                ),
                "POWER_OFF": _command_object(
                    RAW_COMMAND,
                    create_button=False,
                ),
            },
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_async_setup_entry_adds_enabled_command_buttons(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup creates buttons only for commands with create_button enabled."""
    entry = _button_entry(hass, infrared_emitter)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    power_on_entity_id = entity_registry.async_get_entity_id(
        "button",
        DOMAIN,
        button_unique_id(entry.entry_id, REMOTE_ID, "POWER_ON"),
    )
    power_off_entity_id = entity_registry.async_get_entity_id(
        "button",
        DOMAIN,
        button_unique_id(entry.entry_id, REMOTE_ID, "POWER_OFF"),
    )

    assert power_on_entity_id is not None
    assert hass.states.get(power_on_entity_id) is not None
    assert power_off_entity_id is None


async def test_button_press_sends_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test pressing a command button sends the stored command."""
    entity = UniversalRemoteButton(
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        infrared_emitter_id=infrared_emitter,
        unique_id="entry_button_living_room_tv_power_on",
        description=UniversalRemoteButtonEntityDescription(
            key="power_on",
            name="Power On",
            icon="mdi:power-on",
            command_name="POWER_ON",
            command_data=RAW_COMMAND,
        ),
    )
    entity.hass = hass

    with patch(
        "custom_components.universal_remote.button.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await entity.async_press()

    mock_send.assert_awaited_once_with(hass, infrared_emitter, RAW_COMMAND)


async def test_button_availability_tracks_infrared_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test command button availability follows the linked infrared entity."""
    entity = UniversalRemoteButton(
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        infrared_emitter_id=infrared_emitter,
        unique_id="entry_button_living_room_tv_power_on",
        description=UniversalRemoteButtonEntityDescription(
            key="power_on",
            name="Power On",
            icon="mdi:power-on",
            command_name="POWER_ON",
            command_data=RAW_COMMAND,
        ),
    )
    entity.hass = hass
    assert entity.available

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        hass.states.async_set(infrared_emitter, STATE_UNAVAILABLE)
        await hass.async_block_till_done()

    assert not entity.available
    write_state.assert_called_once()


def test_cleanup_stale_button_entities_removes_only_matching_stale_entries(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test stale command button registry entries are removed."""
    entry = _button_entry(hass, infrared_emitter)
    expected_unique_id = button_unique_id(entry.entry_id, REMOTE_ID, "POWER_ON")
    stale_unique_id = button_unique_id(entry.entry_id, REMOTE_ID, "OLD_COMMAND")
    registry = MagicMock()
    stale_button = Mock(
        domain="button",
        unique_id=stale_unique_id,
        entity_id="button.old_command",
    )
    expected_button = Mock(
        domain="button",
        unique_id=expected_unique_id,
        entity_id="button.power_on",
    )
    other_domain = Mock(
        domain="sensor",
        unique_id=button_unique_id(entry.entry_id, REMOTE_ID, "SENSOR"),
        entity_id="sensor.old_command",
    )
    other_unique_id = Mock(
        domain="button",
        unique_id="other_integration_button_old_command",
        entity_id="button.other",
    )

    with (
        patch(
            "custom_components.universal_remote.button.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.universal_remote.button.er.async_entries_for_config_entry",
            return_value=[
                stale_button,
                expected_button,
                other_domain,
                other_unique_id,
            ],
        ),
    ):
        cleanup_stale_button_entities(hass, entry, {expected_unique_id})

    registry.async_remove.assert_called_once_with("button.old_command")


async def test_async_setup_entry_skips_button_command_without_payload(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup skips button-enabled commands with no command payload."""
    entry = _button_entry(hass, infrared_emitter)

    with patch(
        "custom_components.universal_remote.button.normalize_command_objects",
        return_value={"BROKEN": {CONF_COMMAND_CREATE_BUTTON: True}},
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    assert (
        entity_registry.async_get_entity_id(
            "button",
            DOMAIN,
            button_unique_id(entry.entry_id, REMOTE_ID, "BROKEN"),
        )
        is None
    )


def test_button_available_without_hass_returns_true(infrared_emitter: str) -> None:
    """Test a button is available before Home Assistant is attached."""
    entity = UniversalRemoteButton(
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        infrared_emitter_id=infrared_emitter,
        unique_id="entry_button_living_room_tv_power_on",
        description=UniversalRemoteButtonEntityDescription(
            key="power_on",
            name="Power On",
            icon="mdi:power-on",
            command_name="POWER_ON",
            command_data=RAW_COMMAND,
        ),
    )

    assert entity.available
