"""Tests for universal remote entities."""

from collections.abc import Iterable, Mapping
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from custom_components.universal_remote.runtime import (
    UniversalRemoteData,
    UniversalRemoteRuntime,
)
from custom_components.universal_remote.remote import (
    COMMAND_POWER_OFF,
    COMMAND_POWER_ON,
    COMMAND_POWER_TOGGLE,
    COMMAND_TOGGLE,
    InfraredRemoteEntity,
    _as_str_mapping,
    _create_missing_issue,
    _delete_missing_issue,
    _runtime_by_remote_id_from_config_entry,
    _universal_remote_device_info,
    async_setup_universal_remote_entities,
    cleanup_stale_missing_infrared_issues,
    cleanup_stale_remote_entities,
    cleanup_stale_universal_remote_devices,
    remote_unique_id,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .conftest import INFRARED_EMITTER_ID, RAW_COMMAND, REMOTE_ID, REMOTE_NAME

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _command_object(
    command_data: str, *, create_button: bool = False
) -> dict[str, object]:
    """Return the stored command-object shape."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: create_button,
    }


def _device_info_factory(
    remote_id: str,
    name: str,
    remote_config: Mapping[str, object],
) -> DeviceInfo:
    """Return device info for tests."""
    return DeviceInfo(identifiers={(DOMAIN, remote_id)}, name=name)


def _entity_name_factory(
    remote_id: str,
    name: str,
    remote_config: Mapping[str, object],
) -> str:
    """Return entity name for tests."""
    return name


def _add_remote_entities_callback(
    entities: list[InfraredRemoteEntity],
) -> AddConfigEntryEntitiesCallback:
    """Return an add-entities callback that captures remote entities."""

    def _add_entities(
        new_entities: Iterable[Entity],
        update_before_add: bool = False,
        *,
        config_subentry_id: str | None = None,
    ) -> None:
        entities.extend(cast(Iterable[InfraredRemoteEntity], new_entities))

    return _add_entities


def _make_entity(
    hass: HomeAssistant,
    *,
    commands: dict[str, str] | None = None,
    infrared_emitter_id: str = INFRARED_EMITTER_ID,
    missing_handler=None,
    restored_handler=None,
    runtime: UniversalRemoteRuntime | None = None,
) -> InfraredRemoteEntity:
    """Create a remote entity for direct tests."""
    entity = InfraredRemoteEntity(
        remote_id=REMOTE_ID,
        name=REMOTE_NAME,
        infrared_emitter_id=infrared_emitter_id,
        commands=commands or {},
        runtime=runtime,
        unique_id_prefix="entry",
        device_info=DeviceInfo(identifiers={(DOMAIN, REMOTE_ID)}, name=REMOTE_NAME),
        entity_name=REMOTE_NAME,
        has_entity_name=False,
        translation_domain=DOMAIN,
        missing_infrared_issue_handler=missing_handler,
        restored_infrared_issue_handler=restored_handler,
    )
    entity.hass = hass
    return entity


def test_remote_unique_id() -> None:
    """Test remote unique id helper."""
    assert remote_unique_id("entry", "remote") == "entry_remote_remote"


def test_as_str_mapping_filters_invalid_entries() -> None:
    """Test invalid command entries are dropped without rejecting the mapping."""
    assert _as_str_mapping("bad") is None
    assert _as_str_mapping({"POWER": RAW_COMMAND, "BAD": 1, 2: RAW_COMMAND}) == {
        "POWER": RAW_COMMAND
    }


def test_standalone_repair_issue_helpers(hass: HomeAssistant) -> None:
    """Test standalone repair issue helper boundaries."""
    with patch(
        "custom_components.universal_remote.remote."
        "async_create_linked_infrared_emitter_missing_issue"
    ) as create_issue:
        _create_missing_issue(hass, REMOTE_ID, REMOTE_NAME, INFRARED_EMITTER_ID)

    create_issue.assert_called_once_with(
        hass,
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        infrared_emitter_id=INFRARED_EMITTER_ID,
    )

    with patch(
        "custom_components.universal_remote.remote."
        "async_delete_linked_infrared_emitter_missing_issue"
    ) as delete_issue:
        _delete_missing_issue(hass, REMOTE_ID)

    delete_issue.assert_called_once_with(hass, remote_id=REMOTE_ID)


async def test_async_setup_entry_adds_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test standalone platform setup creates entities."""
    entities: list[InfraredRemoteEntity] = []

    await async_setup_universal_remote_entities(
        hass,
        config_entry,
        _add_remote_entities_callback(entities),
        device_info_factory=_device_info_factory,
    )

    assert len(entities) == 1
    entity = entities[0]
    assert entity.unique_id == f"{config_entry.entry_id}_remote_{REMOTE_ID}"
    assert entity.name is None
    assert entity.device_info == DeviceInfo(
        identifiers={(DOMAIN, REMOTE_ID)},
        name=REMOTE_NAME,
    )


async def test_async_setup_universal_remote_entities_shared_options(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test shared setup helper supports custom integration boundary."""
    entities: list[InfraredRemoteEntity] = []
    missing_handler = Mock()
    restored_handler = Mock()

    await async_setup_universal_remote_entities(
        hass,
        config_entry,
        _add_remote_entities_callback(entities),
        device_info_factory=_device_info_factory,
        entity_name_factory=_entity_name_factory,
        has_entity_name=False,
        cleanup_devices=False,
        translation_domain="itachip2ir",
        missing_infrared_issue_handler=missing_handler,
        restored_infrared_issue_handler=restored_handler,
    )

    assert len(entities) == 1
    entity = entities[0]
    assert entity.name == REMOTE_NAME
    assert entity._translation_domain == "itachip2ir"


async def test_cleanup_stale_remote_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test stale remote entity cleanup."""
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "remote",
        DOMAIN,
        f"{config_entry.entry_id}_remote_stale",
        suggested_object_id="stale",
        config_entry=config_entry,
    )
    keep = registry.async_get_or_create(
        "remote",
        DOMAIN,
        f"{config_entry.entry_id}_remote_keep",
        suggested_object_id="keep",
        config_entry=config_entry,
    )

    cleanup_stale_remote_entities(hass, config_entry, {"keep"})

    assert registry.async_get(stale.entity_id) is None
    assert registry.async_get(keep.entity_id) is not None


async def test_cleanup_stale_universal_remote_devices(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test stale universal remote device cleanup."""
    registry = dr.async_get(hass)
    stale = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "stale")},
    )
    keep = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, "keep")},
    )
    physical = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("itachip2ir", "physical")},
    )

    cleanup_stale_universal_remote_devices(hass, config_entry, {"keep"})

    assert registry.async_get(stale.id) is None
    assert registry.async_get(keep.id) is not None
    assert registry.async_get(physical.id) is not None


async def test_cleanup_stale_remote_entities_ignores_other_domains(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test stale remote cleanup ignores non-remote entity registry entries."""
    registry = er.async_get(hass)
    sensor = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{config_entry.entry_id}_remote_stale",
        suggested_object_id="stale_sensor",
        config_entry=config_entry,
    )

    cleanup_stale_remote_entities(hass, config_entry, set())

    assert registry.async_get(sensor.entity_id) is not None


async def test_cleanup_stale_universal_remote_devices_ignores_other_config_entries(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test device cleanup ignores devices from other config entries."""
    registry = dr.async_get(hass)

    other_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="other_entry",
    )
    other_entry.add_to_hass(hass)

    other = registry.async_get_or_create(
        config_entry_id=other_entry.entry_id,
        identifiers={(DOMAIN, "stale")},
    )

    cleanup_stale_universal_remote_devices(hass, config_entry, set())

    assert registry.async_get(other.id) is not None


def test_available_property(hass: HomeAssistant, infrared_emitter: str) -> None:
    """Test availability follows backing infrared emitter."""
    entity = _make_entity(hass)

    assert entity.available is True

    hass.states.async_set(INFRARED_EMITTER_ID, STATE_UNAVAILABLE)
    assert entity.available is False

    hass.states.async_remove(INFRARED_EMITTER_ID)
    assert entity.available is False


def test_available_without_hass_returns_true() -> None:
    """Test entity is considered available before being added to Home Assistant."""
    entity = InfraredRemoteEntity(
        remote_id=REMOTE_ID,
        name=REMOTE_NAME,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands={},
        unique_id_prefix="entry",
        device_info=DeviceInfo(identifiers={(DOMAIN, REMOTE_ID)}, name=REMOTE_NAME),
        entity_name=REMOTE_NAME,
        has_entity_name=False,
    )

    assert entity.available is True
    assert entity._resolve_infrared_emitter_id() == INFRARED_EMITTER_ID
    entity._update_missing_infrared_repair_issue()


async def test_infrared_state_change_updates_repair_issue_and_state(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test linked infrared state changes update repairs and entity state."""
    missing_handler = Mock()
    restored_handler = Mock()
    entity = _make_entity(
        hass,
        missing_handler=missing_handler,
        restored_handler=restored_handler,
    )

    with patch.object(entity, "async_write_ha_state") as write_state:
        await entity.async_added_to_hass()
        hass.states.async_set(INFRARED_EMITTER_ID, STATE_UNAVAILABLE)
        await hass.async_block_till_done()

    restored_handler.assert_called_once_with(hass, REMOTE_ID)
    missing_handler.assert_called_once_with(
        hass,
        REMOTE_ID,
        REMOTE_NAME,
        INFRARED_EMITTER_ID,
    )
    write_state.assert_called_once()


async def test_async_update_refreshes_repair_issue(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test async update refreshes repair issue state."""
    restored_handler = Mock()
    entity = _make_entity(hass, restored_handler=restored_handler)

    await entity.async_update()

    restored_handler.assert_called_once_with(hass, REMOTE_ID)


async def test_power_methods_send_configured_commands(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test turn on/off/toggle services."""
    entity = _make_entity(
        hass,
        commands={
            COMMAND_POWER_ON: RAW_COMMAND,
            COMMAND_POWER_OFF: RAW_COMMAND,
            COMMAND_TOGGLE: RAW_COMMAND,
        },
    )

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(),
        ) as mock_send,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_on()
        await entity.async_turn_off()
        await entity.async_toggle()

    assert len(mock_send.mock_calls) == 3
    assert entity.is_on is True


async def test_toggle_uses_power_toggle_fallback(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test toggle falls back to POWER_TOGGLE."""
    entity = _make_entity(hass, commands={COMMAND_POWER_TOGGLE: RAW_COMMAND})

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(),
        ) as mock_send,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_toggle()

    assert len(mock_send.mock_calls) == 1
    assert entity.is_on is False


async def test_power_methods_no_configured_command_noop(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test power methods no-op without configured commands."""
    entity = _make_entity(hass)

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(),
        ) as mock_send,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_on()
        await entity.async_turn_off()
        await entity.async_toggle()

    assert len(mock_send.mock_calls) == 0
    assert entity.is_on is True


async def test_send_command_named_raw_repeat_and_delay(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test send command supports named/raw, repeat, and delay."""
    entity = _make_entity(hass, commands={"POWER": RAW_COMMAND})

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(),
        ) as mock_send,
        patch(
            "custom_components.universal_remote.remote.asyncio.sleep", AsyncMock()
        ) as mock_sleep,
    ):
        await entity.async_send_command(
            ["power", RAW_COMMAND],
            num_repeats=2,
            delay_secs=0.5,
        )

    assert len(mock_send.mock_calls) == 4
    assert len(mock_sleep.mock_calls) == 3


async def test_send_command_runtime_overlay(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test remote.send_command uses runtime tuner overlay."""
    commands = {
        "BS": RAW_COMMAND,
        "NUM_1": "38000:9000,2250,560,560",
        "BS_NUM_1": "38000:4500,4500,560,560",
    }
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands=commands,
    )
    entity = _make_entity(hass, commands=commands, runtime=runtime)

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await entity.async_send_command(["bs", "num_1"])

    assert [call.args[2] for call in mock_send.await_args_list] == [
        RAW_COMMAND,
        "38000:4500,4500,560,560",
    ]


async def test_send_command_runtime_empty_commands_allows_raw(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test runtime-backed remote.send_command keeps raw-only support."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands={},
    )
    entity = _make_entity(hass, commands={}, runtime=runtime)

    with patch(
        "custom_components.universal_remote.runtime.async_send_infrared_command",
        AsyncMock(),
    ) as mock_send:
        await entity.async_send_command([RAW_COMMAND])

    assert mock_send.await_args is not None
    assert mock_send.await_args.args == (hass, INFRARED_EMITTER_ID, RAW_COMMAND)
    assert mock_send.await_args.kwargs["check_available"] is False


async def test_send_command_runtime_missing_emitter_not_wrapped(
    hass: HomeAssistant,
) -> None:
    """Test runtime-backed raw send preserves missing-emitter error."""
    missing_emitter_id = "infrared.missing_ir"
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=missing_emitter_id,
        commands={},
    )
    entity = _make_entity(
        hass,
        infrared_emitter_id=missing_emitter_id,
        commands={},
        runtime=runtime,
    )

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command([RAW_COMMAND])

    assert err.value.translation_key == "remote_infrared_missing"
    assert err.value.translation_placeholders == {"entity_id": missing_emitter_id}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"num_repeats": 0}, "num_repeats"),
        ({"num_repeats": True}, "num_repeats"),
        ({"num_repeats": "bad"}, "num_repeats"),
        ({"delay_secs": -1}, "delay_secs"),
        ({"delay_secs": True}, "delay_secs"),
        ({"delay_secs": "bad"}, "delay_secs"),
    ],
)
async def test_send_command_invalid_service_parameters(
    hass: HomeAssistant,
    infrared_emitter: str,
    kwargs: dict[str, Any],
    message: str,
) -> None:
    """Test invalid remote.send_command parameters."""
    entity = _make_entity(hass)

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command([RAW_COMMAND], **kwargs)

    assert err.value.translation_key == "remote_invalid_service_parameter"
    assert err.value.translation_placeholders is not None
    assert message in err.value.translation_placeholders["error"]


async def test_send_command_non_string_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test non-string command raises before sending anything."""
    entity = _make_entity(hass)

    with (
        patch(
            "custom_components.universal_remote.send.infrared.async_send_command",
            AsyncMock(),
        ) as mock_send,
        pytest.raises(HomeAssistantError) as err,
    ):
        await entity.async_send_command([RAW_COMMAND, 1])  # type: ignore[list-item]

    assert err.value.translation_key == "remote_invalid_service_parameter"
    assert err.value.translation_placeholders == {
        "error": "command must be a string or list of strings"
    }
    assert len(mock_send.mock_calls) == 0


async def test_send_command_non_iterable_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test non-iterable command raises a translated error."""
    entity = _make_entity(hass)

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command(1)  # type: ignore[arg-type]

    assert err.value.translation_key == "remote_invalid_service_parameter"


async def test_missing_named_command_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test missing named command error."""
    entity = _make_entity(hass)

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command(["POWER"])

    assert err.value.translation_key == "remote_unknown_or_invalid_command"
    assert err.value.translation_placeholders == {"command": "POWER"}


async def test_invalid_raw_command_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test invalid raw command preserves parser error."""
    entity = _make_entity(hass)

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command([""])

    assert err.value.translation_key == "remote_unknown_or_invalid_command"


async def test_invalid_configured_command_preserves_parser_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test invalid configured command preserves parser error."""
    entity = _make_entity(hass, commands={"BROKEN": ""})

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command(["BROKEN"])

    assert err.value.translation_key == "remote_invalid_command"


async def test_missing_infrared_emitter_error_and_repair_issue(
    hass: HomeAssistant,
) -> None:
    """Test missing backing infrared emitter creates repair issue."""
    missing_handler = Mock()
    restored_handler = Mock()
    missing_emitter_id = "infrared.missing_ir"

    entity = _make_entity(
        hass,
        infrared_emitter_id=missing_emitter_id,
        commands={"POWER": RAW_COMMAND},
        missing_handler=missing_handler,
        restored_handler=restored_handler,
    )

    await entity.async_added_to_hass()

    missing_handler.assert_called_once_with(
        hass,
        REMOTE_ID,
        REMOTE_NAME,
        missing_emitter_id,
    )
    restored_handler.assert_not_called()


async def test_send_command_missing_infrared_emitter_raises_and_updates_repair_issue(
    hass: HomeAssistant,
) -> None:
    """Test sending with a missing backing infrared emitter raises and creates repair issue."""
    missing_handler = Mock()
    restored_handler = Mock()
    missing_emitter_id = "infrared.missing_ir"

    entity = _make_entity(
        hass,
        infrared_emitter_id=missing_emitter_id,
        commands={"POWER": RAW_COMMAND},
        missing_handler=missing_handler,
        restored_handler=restored_handler,
    )

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command(["POWER"])

    assert err.value.translation_key == "remote_infrared_missing"
    assert err.value.translation_placeholders == {"entity_id": missing_emitter_id}
    missing_handler.assert_called_once_with(
        hass,
        REMOTE_ID,
        REMOTE_NAME,
        missing_emitter_id,
    )
    restored_handler.assert_not_called()


async def test_repair_issue_cleared_when_entity_restored(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test repair issue cleared when backing entity is restored."""
    missing_handler = Mock()
    restored_handler = Mock()
    entity = _make_entity(
        hass,
        missing_handler=missing_handler,
        restored_handler=restored_handler,
    )

    await entity.async_added_to_hass()

    restored_handler.assert_called_once_with(hass, REMOTE_ID)
    missing_handler.assert_not_called()


async def test_send_command_without_hass_raises_missing_infrared() -> None:
    """Test sending before entity is added raises a translated error."""
    entity = InfraredRemoteEntity(
        remote_id=REMOTE_ID,
        name=REMOTE_NAME,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands={"POWER": RAW_COMMAND},
        unique_id_prefix="entry",
        device_info=DeviceInfo(identifiers={(DOMAIN, REMOTE_ID)}, name=REMOTE_NAME),
        entity_name=REMOTE_NAME,
        has_entity_name=False,
    )

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_send_command(["POWER"])

    assert err.value.translation_key == "remote_infrared_missing"


async def test_async_setup_entry_supports_single_entry_remote_data(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test standalone setup supports one universal remote per config entry storage."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="single_entry",
        data={
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
        },
        options={CONF_REMOTE_COMMANDS: {COMMAND_POWER_ON: "38000:1,2"}},
    )
    entry.add_to_hass(hass)
    async_add_entities = Mock()

    await async_setup_universal_remote_entities(
        hass,
        entry,
        async_add_entities,
        device_info_factory=_device_info_factory,
    )

    entities = async_add_entities.call_args.args[0]
    assert len(entities) == 1
    assert entities[0].unique_id == remote_unique_id(entry.entry_id, "tv")


async def test_async_setup_entry_ignores_malformed_single_entry_remote_data(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test standalone setup ignores malformed one-remote entry data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="single_entry",
        data={
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
        },
        options={},
    )
    entry.add_to_hass(hass)
    async_add_entities = Mock()

    await async_setup_universal_remote_entities(
        hass,
        entry,
        async_add_entities,
        device_info_factory=_device_info_factory,
    )

    assert async_add_entities.call_args.args[0] == []


async def test_async_setup_universal_remote_entities_skips_malformed_and_duplicate_remotes(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup skips malformed and duplicate universal remote definitions."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    entities: list[InfraredRemoteEntity] = []

    with patch(
        "custom_components.universal_remote.remote.configured_remote_definitions",
        return_value=[
            {
                CONF_REMOTE_ID: "valid",
                CONF_REMOTE_NAME: "Valid",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_REMOTE_COMMANDS: {COMMAND_POWER_ON: RAW_COMMAND},
            },
            {
                CONF_REMOTE_ID: "malformed",
                CONF_REMOTE_NAME: "",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
            },
            {
                CONF_REMOTE_ID: "valid",
                CONF_REMOTE_NAME: "Duplicate",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
            },
        ],
    ):
        await async_setup_universal_remote_entities(
            hass,
            entry,
            _add_remote_entities_callback(entities),
            device_info_factory=_device_info_factory,
        )

    assert [entity.unique_id for entity in entities] == [
        f"{entry.entry_id}_remote_valid"
    ]


def test_universal_remote_device_info_factory() -> None:
    """Test standalone universal remote device info factory."""
    assert _universal_remote_device_info("tv", "TV", {}) == DeviceInfo(
        identifiers={(DOMAIN, "tv")},
        name="TV",
    )


def test_cleanup_stale_missing_infrared_issues_uses_standalone_cleanup(
    hass: HomeAssistant,
) -> None:
    """Test stale linked infrared repair issue cleanup for standalone remotes."""
    with patch(
        "custom_components.universal_remote.remote."
        "async_delete_stale_linked_infrared_emitter_missing_issues"
    ) as delete_stale_issues:
        cleanup_stale_missing_infrared_issues(
            hass,
            {"living_room_tv"},
            cleanup_stale_issues=True,
        )

    delete_stale_issues.assert_called_once_with(
        hass,
        configured_remote_ids={"living_room_tv"},
    )


def test_cleanup_stale_missing_infrared_issues_skips_when_disabled(
    hass: HomeAssistant,
) -> None:
    """Test stale linked infrared repair issue cleanup can be skipped."""
    with patch(
        "custom_components.universal_remote.remote."
        "async_delete_stale_linked_infrared_emitter_missing_issues"
    ) as delete_stale_issues:
        cleanup_stale_missing_infrared_issues(
            hass,
            {"living_room_tv"},
            cleanup_stale_issues=False,
        )

    delete_stale_issues.assert_not_called()


async def test_async_setup_universal_remote_entities_runs_device_cleanup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test setup runs device cleanup when requested."""
    entities: list[InfraredRemoteEntity] = []

    with patch(
        "custom_components.universal_remote.remote."
        "cleanup_stale_universal_remote_devices"
    ) as cleanup_devices:
        await async_setup_universal_remote_entities(
            hass,
            config_entry,
            _add_remote_entities_callback(entities),
            device_info_factory=_device_info_factory,
            cleanup_devices=True,
        )

    cleanup_devices.assert_called_once_with(
        hass,
        config_entry,
        {"living_room_tv"},
        identifier_domain=DOMAIN,
    )
    assert len(entities) == 1


async def test_config_entry_setup_covers_standalone_remote_platform_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test config entry setup reaches the standalone remote platform setup."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("remote.living_room_tv") is not None


async def test_async_setup_universal_remote_entities_ignores_receiver_only_entry(
    hass: HomeAssistant,
) -> None:
    """Test remote platform ignores receiver-only universal remote entries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="receiver_only",
        data={
            CONF_REMOTE_ID: "receiver_only",
            CONF_REMOTE_NAME: "Receiver Only",
            "infrared_receiver_id": "infrared.test_receiver",
        },
        options={CONF_REMOTE_COMMANDS: {COMMAND_POWER_ON: RAW_COMMAND}},
    )
    entry.add_to_hass(hass)
    entities: list[InfraredRemoteEntity] = []

    await async_setup_universal_remote_entities(
        hass,
        entry,
        _add_remote_entities_callback(entities),
        device_info_factory=_device_info_factory,
        cleanup_stale_issues=True,
    )

    assert entities == []


def test_runtime_by_remote_id_without_runtime_data(
    config_entry: MockConfigEntry,
) -> None:
    """Test runtime lookup returns empty without runtime data."""
    assert _runtime_by_remote_id_from_config_entry(config_entry) == {}


def test_runtime_by_remote_id_without_valid_remote(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test runtime lookup returns empty when entry data has no valid remote."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands={},
    )
    config_entry.runtime_data = UniversalRemoteData(runtime=runtime)

    with patch(
        "custom_components.universal_remote.remote."
        "universal_remote_from_config_entry_data",
        return_value=None,
    ):
        assert _runtime_by_remote_id_from_config_entry(config_entry) == {}


def test_runtime_by_remote_id_without_valid_remote_id(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test runtime lookup returns empty when remote id is invalid."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands={},
    )
    config_entry.runtime_data = UniversalRemoteData(runtime=runtime)

    with patch(
        "custom_components.universal_remote.remote."
        "universal_remote_from_config_entry_data",
        return_value={CONF_REMOTE_ID: ""},
    ):
        assert _runtime_by_remote_id_from_config_entry(config_entry) == {}


async def test_power_method_uses_runtime_send_path(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test power methods route configured commands through runtime."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id=INFRARED_EMITTER_ID,
        commands={COMMAND_POWER_ON: RAW_COMMAND},
    )
    entity = _make_entity(
        hass,
        commands={COMMAND_POWER_ON: RAW_COMMAND},
        runtime=runtime,
    )

    with (
        patch.object(
            runtime,
            "async_send_command_name",
            AsyncMock(),
        ) as mock_send,
        patch.object(entity, "async_write_ha_state"),
    ):
        await entity.async_turn_on()

    mock_send.assert_awaited_once_with(
        COMMAND_POWER_ON,
        parse_kwargs={},
        check_available=False,
        allow_raw=False,
    )


async def test_power_method_without_hass_raises_missing_infrared(
    hass: HomeAssistant,
) -> None:
    """Test configured power command fails cleanly when hass is not attached."""
    entity = _make_entity(hass, commands={COMMAND_POWER_ON: RAW_COMMAND})
    setattr(entity, "hass", None)

    with pytest.raises(HomeAssistantError) as err:
        await entity.async_turn_on()

    assert err.value.translation_key == "remote_infrared_missing"
    assert err.value.translation_placeholders == {"entity_id": INFRARED_EMITTER_ID}


async def test_private_send_without_runtime_and_raw_disabled_rejects_missing_command(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test direct non-raw send path rejects missing configured command."""
    entity = _make_entity(hass)

    with pytest.raises(HomeAssistantError) as err:
        await entity._async_send_named_command("UNKNOWN")

    assert err.value.translation_key == "remote_command_missing"
    assert err.value.translation_placeholders == {"command": "UNKNOWN"}
