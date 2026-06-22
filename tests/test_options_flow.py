"""Tests for the Universal Remote options flow."""

from unittest.mock import patch

import pytest

from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.infrared_library import (
    InfraredLibraryCommandError,
)
from custom_components.universal_remote.options_flow import (
    COMMAND_DATA,
    COMMAND_LIBRARY_CODESET,
    COMMAND_LIBRARY_COMMAND,
    COMMAND_LIBRARY_COMMANDS,
    COMMAND_NAME,
    COMMAND_REPEAT_COUNT,
    COMMAND_SOURCE,
    COMMAND_SOURCE_INFRARED_LIBRARY,
    COMMAND_SOURCE_RAW,
    SOURCE_ADD_RAW_COMMAND,
    SOURCE_EDIT_COMMAND,
    SOURCE_EDIT_LIBRARY_CODESET,
    SOURCE_EDIT_LIBRARY_COMMAND,
    SOURCE_EDIT_RAW_COMMAND,
    SOURCE_IMPORT_LIBRARY_COMMAND_SELECT,
    SOURCE_IMPORT_LIBRARY_COMMANDS,
    SOURCE_MANAGE_COMMANDS,
    SOURCE_REMOVE_COMMAND,
    UniversalRemoteOptionsFlow,
    library_command_default,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import RAW_COMMAND

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _command_object(
    command_data: str, *, create_button: bool = False
) -> dict[str, object]:
    """Return the stored command-object shape."""
    return {
        CONF_COMMAND_DATA: command_data,
        CONF_COMMAND_CREATE_BUTTON: create_button,
    }


SELECT_COMMAND_FOR_EDIT = "select_command_for_edit"

SOURCE_ADD_COMMAND = SOURCE_ADD_RAW_COMMAND


async def _init_options_flow(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    source: str | None = None,
):
    """Initialize the options flow."""
    result = await hass.config_entries.options.async_init(
        entry.entry_id,
        context={
            "source": "init",
            "entry_id": entry.entry_id,
        },
    )
    if source is None:
        return result

    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": source},
    )


def _single_entry(hass: HomeAssistant, infrared_emitter: str) -> MockConfigEntry:
    """Create a one-remote config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data={
            CONF_REMOTE_ID: "living_room_tv",
            CONF_REMOTE_NAME: "Living Room TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={CONF_REMOTE_COMMANDS: {"POWER_ON": RAW_COMMAND}},
        unique_id="living_room_tv",
    )
    entry.add_to_hass(hass)
    return entry


def _single_entry_without_commands(
    hass: HomeAssistant, infrared_emitter: str
) -> MockConfigEntry:
    """Create a one-remote config entry without commands."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data={
            CONF_REMOTE_ID: "living_room_tv",
            CONF_REMOTE_NAME: "Living Room TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={},
        unique_id="living_room_tv",
    )
    entry.add_to_hass(hass)
    return entry


async def _start_add_command(
    hass: HomeAssistant,
    entry: MockConfigEntry,
):
    """Start the add command flow."""
    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": SOURCE_ADD_COMMAND},
    )


async def _start_edit_command(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    command_name: str = "POWER_ON",
):
    """Start the edit command flow."""
    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": SOURCE_EDIT_COMMAND},
    )
    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_NAME: command_name},
    )


async def test_options_menu(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test options menu for a single remote entry."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry)

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [SOURCE_MANAGE_COMMANDS]


async def test_options_menu_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test options flow aborts when the config entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    result = await _init_options_flow(hass, entry)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_manage_commands_menu_with_commands(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test manage commands menu includes edit/remove when commands exist."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == SOURCE_MANAGE_COMMANDS
    assert result["menu_options"] == [
        SOURCE_ADD_RAW_COMMAND,
        SOURCE_IMPORT_LIBRARY_COMMANDS,
        SOURCE_EDIT_COMMAND,
        SOURCE_REMOVE_COMMAND,
    ]


async def test_manage_commands_menu_without_commands(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test manage commands menu only includes add when no commands exist."""
    entry = _single_entry_without_commands(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [
        SOURCE_ADD_RAW_COMMAND,
        SOURCE_IMPORT_LIBRARY_COMMANDS,
    ]


async def test_manage_commands_menu_generic_remote_hides_library_import(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test generic remotes do not show library import in normal options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Generic Remote",
        data={
            CONF_REMOTE_ID: "generic_remote",
            CONF_REMOTE_NAME: "Generic Remote",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={},
        unique_id="generic_remote",
    )
    entry.add_to_hass(hass)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == [SOURCE_ADD_RAW_COMMAND]


async def test_manage_commands_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test manage commands aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_manage_commands()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_add_command_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test adding a raw command."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _start_add_command(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_ADD_RAW_COMMAND

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            COMMAND_NAME: "HDMI 1",
            COMMAND_DATA: RAW_COMMAND,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS]["HDMI_1"] == _command_object(
        RAW_COMMAND
    )


@pytest.mark.parametrize(
    ("user_input", "errors"),
    [
        (
            {COMMAND_NAME: "", COMMAND_DATA: RAW_COMMAND},
            {COMMAND_NAME: "command_name_required"},
        ),
        (
            {COMMAND_NAME: "Power On", COMMAND_DATA: RAW_COMMAND},
            {COMMAND_NAME: "command_name_exists"},
        ),
    ],
)
async def test_add_command_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    user_input: dict[str, str],
    errors: dict[str, str],
) -> None:
    """Test adding raw command validation errors."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _start_add_command(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input,
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_ADD_RAW_COMMAND
    assert result["errors"] == errors


@pytest.mark.parametrize(
    ("command_data", "errors"),
    [
        ("", {COMMAND_DATA: "command_data_required"}),
        ("bad", {COMMAND_DATA: "invalid_command"}),
    ],
)
async def test_add_raw_command_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    command_data: str,
    errors: dict[str, str],
) -> None:
    """Test adding raw command validation errors."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _start_add_command(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_NAME: "HDMI", COMMAND_DATA: command_data},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_ADD_RAW_COMMAND
    assert result["errors"] == errors


async def test_import_library_command_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test importing commands using an infrared library codeset."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": SOURCE_IMPORT_LIBRARY_COMMANDS},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMANDS

    with (
        patch(
            "custom_components.universal_remote.options_flow."
            "infrared_library_command_options",
            return_value=[{"value": "POWER", "label": "POWER"}],
        ),
        patch(
            "custom_components.universal_remote.options_flow."
            "generate_selected_commands_from_library_codeset",
            return_value={"POWER": RAW_COMMAND},
        ) as generate_commands,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {COMMAND_LIBRARY_CODESET: "lg_tv_jp"},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMAND_SELECT

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                COMMAND_LIBRARY_COMMANDS: ["POWER"],
                COMMAND_REPEAT_COUNT: 0,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS]["POWER"] == _command_object(RAW_COMMAND)
    generate_commands.assert_called_once_with("lg_tv_jp", ["POWER"], 0)


async def test_import_library_command_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test importing infrared library commands handles generation errors."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": SOURCE_IMPORT_LIBRARY_COMMANDS},
    )

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_command_options",
        return_value=[{"value": "POWER", "label": "POWER"}],
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {COMMAND_LIBRARY_CODESET: "lg_tv_jp"},
        )

    with patch(
        "custom_components.universal_remote.options_flow."
        "generate_selected_commands_from_library_codeset",
        side_effect=InfraredLibraryCommandError,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                COMMAND_LIBRARY_COMMANDS: ["POWER"],
                COMMAND_REPEAT_COUNT: 0,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMAND_SELECT
    assert result["errors"] == {COMMAND_LIBRARY_COMMANDS: "invalid_library_command"}


async def test_add_raw_command_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test add raw command aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_add_raw_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_select_command_for_edit_form(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selecting a command for edit."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": SOURCE_EDIT_COMMAND},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SELECT_COMMAND_FOR_EDIT


async def test_select_command_for_edit_without_commands_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selecting command for edit aborts without commands."""
    entry = _single_entry_without_commands(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_select_command_for_edit()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_remote_commands"


async def test_edit_command_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test editing a command with raw command data."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _start_edit_command(hass, entry)
    assert result["step_id"] == SOURCE_EDIT_COMMAND

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_SOURCE: COMMAND_SOURCE_RAW},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_RAW_COMMAND

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_NAME: "HDMI 1", COMMAND_DATA: RAW_COMMAND},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "POWER_ON" not in result["data"][CONF_REMOTE_COMMANDS]
    assert result["data"][CONF_REMOTE_COMMANDS]["HDMI_1"] == _command_object(
        RAW_COMMAND
    )


@pytest.mark.parametrize(
    ("user_input", "errors"),
    [
        (
            {COMMAND_NAME: "", COMMAND_DATA: RAW_COMMAND},
            {COMMAND_NAME: "command_name_required"},
        ),
    ],
)
async def test_edit_raw_command_name_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    user_input: dict[str, str],
    errors: dict[str, str],
) -> None:
    """Test editing raw command validation errors for command name."""
    entry = _single_entry(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_raw_command(user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_RAW_COMMAND
    assert result["errors"] == errors


async def test_edit_command_invalid_source_direct(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit command rejects an invalid source when called directly."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_command({COMMAND_SOURCE: "invalid"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_COMMAND
    assert result["errors"] == {COMMAND_SOURCE: "invalid_command_source"}


@pytest.mark.parametrize(
    ("command_data", "errors"),
    [
        ("", {COMMAND_DATA: "command_data_required"}),
        ("bad", {COMMAND_DATA: "invalid_command"}),
    ],
)
async def test_edit_raw_command_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    command_data: str,
    errors: dict[str, str],
) -> None:
    """Test editing raw command validation errors."""
    entry = _single_entry(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_command({COMMAND_SOURCE: COMMAND_SOURCE_RAW})
    assert result["step_id"] == SOURCE_EDIT_RAW_COMMAND

    result = await flow.async_step_edit_raw_command(
        {COMMAND_NAME: "Power", COMMAND_DATA: command_data}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_RAW_COMMAND
    assert result["errors"] == errors


async def test_edit_command_duplicate_name(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test editing command rejects another existing command name."""
    entry = _single_entry(hass, infrared_emitter)
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_REMOTE_COMMANDS: {
                **entry.options[CONF_REMOTE_COMMANDS],
                "POWER_OFF": RAW_COMMAND,
            },
        },
    )

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_raw_command(
        {COMMAND_NAME: "POWER_OFF", COMMAND_DATA: RAW_COMMAND}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_RAW_COMMAND
    assert result["errors"] == {COMMAND_NAME: "command_name_exists"}


async def test_edit_library_command_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test editing a command using an infrared library command."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _start_edit_command(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_SOURCE: COMMAND_SOURCE_INFRARED_LIBRARY},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_CODESET

    with (
        patch(
            "custom_components.universal_remote.options_flow."
            "infrared_library_command_options",
            return_value=[{"value": "POWER", "label": "POWER"}],
        ),
        patch(
            "custom_components.universal_remote.options_flow."
            "generate_pronto_from_library_command",
            return_value=RAW_COMMAND,
        ) as generate_pronto,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {COMMAND_LIBRARY_CODESET: "lg_tv_jp"},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == SOURCE_EDIT_LIBRARY_COMMAND

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                COMMAND_LIBRARY_COMMAND: "POWER",
                COMMAND_REPEAT_COUNT: 0,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "POWER_ON" not in result["data"][CONF_REMOTE_COMMANDS]
    assert result["data"][CONF_REMOTE_COMMANDS]["POWER"] == _command_object(RAW_COMMAND)
    generate_pronto.assert_called_once_with("lg_tv_jp", "POWER", 0)


async def test_edit_library_command_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test editing an infrared library command handles generation errors."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_command(
        {COMMAND_SOURCE: COMMAND_SOURCE_INFRARED_LIBRARY}
    )
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_CODESET

    result = await flow.async_step_edit_library_codeset(
        {COMMAND_LIBRARY_CODESET: "lg_tv_jp"}
    )
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_COMMAND

    with (
        patch(
            "custom_components.universal_remote.options_flow."
            "infrared_library_command_options",
            return_value=[{"value": "POWER", "label": "POWER"}],
        ),
        patch(
            "custom_components.universal_remote.options_flow."
            "generate_pronto_from_library_command",
            side_effect=InfraredLibraryCommandError,
        ),
    ):
        result = await flow.async_step_edit_library_command(
            {
                COMMAND_LIBRARY_COMMAND: "POWER",
                COMMAND_REPEAT_COUNT: 0,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_COMMAND
    assert result["errors"] == {COMMAND_LIBRARY_COMMAND: "invalid_library_command"}


async def test_edit_library_codeset_without_pending_name_returns_edit_form(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library codeset returns edit form without pending command name."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_library_codeset()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_CODESET


async def test_edit_command_missing_selection_shows_select_form(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit command redirects to selection form when no command is selected."""
    entry = _single_entry(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_edit_command()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SELECT_COMMAND_FOR_EDIT


async def test_edit_command_missing_selection_submit_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit command aborts when submitted selected command is gone."""
    entry = _single_entry(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "MISSING"

    result = await flow.async_step_edit_command(
        {
            COMMAND_NAME: "HDMI",
            COMMAND_SOURCE: COMMAND_SOURCE_RAW,
        }
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "command_not_found"


async def test_edit_command_without_remote_or_commands_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit command abort conditions."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_edit_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"

    entry = _single_entry_without_commands(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_edit_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_remote_commands"


async def test_edit_raw_command_without_pending_name_returns_edit_form(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit raw command returns edit form without pending command name."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_raw_command()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_RAW_COMMAND


async def test_remove_command_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test removing a command."""
    entry = _single_entry(hass, infrared_emitter)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": SOURCE_REMOVE_COMMAND},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_REMOVE_COMMAND

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_NAME: ["POWER_ON"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_REMOTE_COMMANDS not in result["data"]


async def test_remove_command_without_commands_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test removing command aborts without commands."""
    entry = _single_entry_without_commands(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_remove_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_remote_commands"


async def test_remove_command_missing_command_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test removing stale command aborts."""
    entry = _single_entry(hass, infrared_emitter)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_remove_command({COMMAND_NAME: ["MISSING"]})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "command_not_found"


async def test_remove_command_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test remove command aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_remove_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_select_command_for_edit_without_remote_aborts(
    hass: HomeAssistant,
) -> None:
    """Test selecting command to edit aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_select_command_for_edit()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_remove_command_keeps_remaining_commands(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test removing one command keeps the remaining commands."""
    entry = _single_entry(hass, infrared_emitter)
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_REMOTE_COMMANDS: {
                **entry.options[CONF_REMOTE_COMMANDS],
                "POWER_OFF": RAW_COMMAND,
            },
        },
    )

    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_remove_command({COMMAND_NAME: ["POWER_ON"]})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS] == {
        "POWER_OFF": _command_object(RAW_COMMAND)
    }


def test_commands_returns_empty_without_remote(hass: HomeAssistant) -> None:
    """Test command helper returns empty when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)

    assert flow._commands == {}


def test_create_options_entry_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test create options entry aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)

    result = flow._create_options_entry()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


def test_library_command_default_uses_normalized_command_name() -> None:
    """Test library command defaults to a normalized matching command name."""
    assert (
        library_command_default(
            [
                {"value": "POWER_ON", "label": "Power On"},
                {"value": "VOLUME_UP", "label": "Volume Up"},
            ],
            "Power On",
        )
        == "POWER_ON"
    )


async def test_import_library_commands_without_remote_aborts(
    hass: HomeAssistant,
) -> None:
    """Test library import aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_import_library_commands()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_import_library_commands_generic_remote_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test library import aborts for generic remotes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Generic Remote",
        data={
            CONF_REMOTE_ID: "generic_remote",
            CONF_REMOTE_NAME: "Generic Remote",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={},
        unique_id="generic_remote",
    )
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_import_library_commands()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


async def test_import_library_commands_without_codesets_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test library import aborts when no codesets are available."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_codeset_options",
        return_value=[],
    ):
        result = await flow.async_step_import_library_commands()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


async def test_import_library_commands_rejects_invalid_codeset(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test library import rejects a codeset that is not offered."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_codeset_options",
        return_value=[{"value": "lg_tv", "label": "LG TV"}],
    ):
        result = await flow.async_step_import_library_commands(
            {COMMAND_LIBRARY_CODESET: "missing"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMANDS
    assert result["errors"] == {COMMAND_LIBRARY_CODESET: "invalid_library_codeset"}


async def test_import_library_command_select_without_remote_aborts(
    hass: HomeAssistant,
) -> None:
    """Test selected library import aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_library_codeset = "lg_tv"

    result = await flow.async_step_import_library_command_select()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_import_library_command_select_without_codeset_returns_codeset_step(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selected library import returns to codeset selection without a codeset."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_codeset_options",
        return_value=[{"value": "lg_tv", "label": "LG TV"}],
    ):
        result = await flow.async_step_import_library_command_select()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMANDS


@pytest.mark.parametrize("options", [None, []])
async def test_import_library_command_select_invalid_codeset_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
    options: list[dict[str, str]] | None,
) -> None:
    """Test selected library import aborts for invalid command options."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_library_codeset = "lg_tv"
    side_effect = InfraredLibraryCommandError if options is None else None

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_command_options",
        side_effect=side_effect,
        return_value=options,
    ):
        result = await flow.async_step_import_library_command_select()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


async def test_import_library_command_select_string_selection_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selected library import accepts a single string command selection."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_library_codeset = "lg_tv"

    with (
        patch(
            "custom_components.universal_remote.options_flow."
            "infrared_library_command_options",
            return_value=[{"value": "VOLUME_UP", "label": "Volume Up"}],
        ),
        patch(
            "custom_components.universal_remote.options_flow."
            "generate_selected_commands_from_library_codeset",
            return_value={"VOLUME_UP": RAW_COMMAND},
        ) as generate_commands,
    ):
        result = await flow.async_step_import_library_command_select(
            {
                COMMAND_LIBRARY_COMMANDS: "VOLUME_UP",
                COMMAND_REPEAT_COUNT: 1,
                CONF_COMMAND_CREATE_BUTTON: True,
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS]["VOLUME_UP"] == _command_object(
        RAW_COMMAND,
        create_button=True,
    )
    generate_commands.assert_called_once_with("lg_tv", ["VOLUME_UP"], 1)


@pytest.mark.parametrize(
    ("user_input", "errors"),
    [
        (
            {COMMAND_LIBRARY_COMMANDS: [], COMMAND_REPEAT_COUNT: 0},
            {COMMAND_LIBRARY_COMMANDS: "library_commands_required"},
        ),
        (
            {COMMAND_LIBRARY_COMMANDS: ["VOLUME_UP"], COMMAND_REPEAT_COUNT: -1},
            {COMMAND_REPEAT_COUNT: "invalid_repeat_count"},
        ),
    ],
)
async def test_import_library_command_select_validation_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    user_input: dict[str, object],
    errors: dict[str, str],
) -> None:
    """Test selected library import validation errors."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_library_codeset = "lg_tv"

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_command_options",
        return_value=[{"value": "VOLUME_UP", "label": "Volume Up"}],
    ):
        result = await flow.async_step_import_library_command_select(user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMAND_SELECT
    assert result["errors"] == errors


async def test_import_library_command_select_existing_command_error(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selected library import rejects existing command names."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_library_codeset = "lg_tv"

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_command_options",
        return_value=[{"value": "POWER_ON", "label": "Power On"}],
    ):
        result = await flow.async_step_import_library_command_select(
            {COMMAND_LIBRARY_COMMANDS: ["POWER_ON"], COMMAND_REPEAT_COUNT: 0}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_IMPORT_LIBRARY_COMMAND_SELECT
    assert result["errors"] == {COMMAND_LIBRARY_COMMANDS: "library_commands_exist"}
    description_placeholders = result.get("description_placeholders")
    assert description_placeholders is not None
    assert description_placeholders["existing_commands"] == "POWER_ON"


async def test_edit_raw_command_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test edit raw command aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_raw_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_edit_raw_command_missing_selected_command_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit raw command aborts when the selected command is gone."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "MISSING"

    result = await flow.async_step_edit_raw_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "command_not_found"


async def test_edit_library_codeset_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test edit library codeset aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_library_codeset()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_edit_library_codeset_without_selected_command_returns_select_form(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library codeset returns command selection without selected command."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_edit_library_codeset()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SELECT_COMMAND_FOR_EDIT


async def test_edit_library_codeset_generic_remote_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library codeset aborts for generic remotes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Generic Remote",
        data={
            CONF_REMOTE_ID: "generic_remote",
            CONF_REMOTE_NAME: "Generic Remote",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={CONF_REMOTE_COMMANDS: {"POWER_ON": RAW_COMMAND}},
        unique_id="generic_remote",
    )
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    result = await flow.async_step_edit_library_codeset()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


async def test_edit_library_codeset_without_codesets_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library codeset aborts when no codesets are available."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_codeset_options",
        return_value=[],
    ):
        result = await flow.async_step_edit_library_codeset()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


async def test_edit_library_codeset_rejects_invalid_codeset(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library codeset rejects a codeset that is not offered."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_codeset_options",
        return_value=[{"value": "lg_tv", "label": "LG TV"}],
    ):
        result = await flow.async_step_edit_library_codeset(
            {COMMAND_LIBRARY_CODESET: "missing"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_CODESET
    assert result["errors"] == {COMMAND_LIBRARY_CODESET: "invalid_library_codeset"}


async def test_edit_library_command_without_remote_aborts(hass: HomeAssistant) -> None:
    """Test edit library command aborts when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"
    flow._selected_library_codeset = "lg_tv"

    result = await flow.async_step_edit_library_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_edit_library_command_missing_selected_command_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library command aborts when the selected command is gone."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "MISSING"
    flow._selected_library_codeset = "lg_tv"

    result = await flow.async_step_edit_library_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "command_not_found"


async def test_edit_library_command_without_codeset_returns_codeset_step(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test edit library command returns to codeset selection without a codeset."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_codeset_options",
        return_value=[{"value": "lg_tv", "label": "LG TV"}],
    ):
        result = await flow.async_step_edit_library_command()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_CODESET


@pytest.mark.parametrize("options", [None, []])
async def test_edit_library_command_invalid_codeset_aborts(
    hass: HomeAssistant,
    infrared_emitter: str,
    options: list[dict[str, str]] | None,
) -> None:
    """Test edit library command aborts for invalid command options."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"
    flow._selected_library_codeset = "lg_tv"
    side_effect = InfraredLibraryCommandError if options is None else None

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_command_options",
        side_effect=side_effect,
        return_value=options,
    ):
        result = await flow.async_step_edit_library_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


@pytest.mark.parametrize(
    ("user_input", "errors"),
    [
        (
            {COMMAND_LIBRARY_COMMAND: "VOLUME_UP", COMMAND_REPEAT_COUNT: -1},
            {COMMAND_REPEAT_COUNT: "invalid_repeat_count"},
        ),
        (
            {COMMAND_LIBRARY_COMMAND: "POWER_OFF", COMMAND_REPEAT_COUNT: 0},
            {COMMAND_LIBRARY_COMMAND: "command_name_exists"},
        ),
    ],
)
async def test_edit_library_command_validation_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    user_input: dict[str, object],
    errors: dict[str, str],
) -> None:
    """Test edit library command validation errors."""
    entry = _single_entry(hass, infrared_emitter)
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_REMOTE_COMMANDS: {
                **entry.options[CONF_REMOTE_COMMANDS],
                "POWER_OFF": RAW_COMMAND,
            },
        },
    )
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._selected_command_name = "POWER_ON"
    flow._selected_library_codeset = "lg_tv"

    with patch(
        "custom_components.universal_remote.options_flow."
        "infrared_library_command_options",
        return_value=[
            {"value": "VOLUME_UP", "label": "Volume Up"},
            {"value": "POWER_OFF", "label": "Power Off"},
        ],
    ):
        result = await flow.async_step_edit_library_command(user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_EDIT_LIBRARY_COMMAND
    assert result["errors"] == errors


async def test_remove_command_string_selection_success(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test removing a command accepts a single string selection."""
    entry = _single_entry(hass, infrared_emitter)
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_REMOTE_COMMANDS: {
                **entry.options[CONF_REMOTE_COMMANDS],
                "POWER_OFF": RAW_COMMAND,
            },
        },
    )
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_remove_command({COMMAND_NAME: "POWER_ON"})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS] == {
        "POWER_OFF": _command_object(RAW_COMMAND)
    }


async def test_remove_command_requires_selection(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test removing commands requires at least one selection."""
    entry = _single_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_remove_command({COMMAND_NAME: []})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_REMOVE_COMMAND
    assert result["errors"] == {COMMAND_NAME: "command_name_required"}


def test_command_objects_returns_empty_without_remote(hass: HomeAssistant) -> None:
    """Test command-object helper returns empty when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)

    assert flow._command_objects == {}
