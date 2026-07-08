"""Tests for the Universal Remote config flow."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.helpers import selector
from custom_components.universal_remote.config_flow import (
    CONF_CREATE_BUTTON,
    CONF_IMPORT_COMMANDS,
    CONF_LIBRARY_COMMANDS,
    CONF_REPEAT_COUNT,
    IMPORT_COMMANDS_ALL,
    IMPORT_COMMANDS_NO,
    IMPORT_COMMANDS_SELECT,
    UniversalRemoteConfigFlow,
    _command_objects,
    _validate_generated_commands,
)
from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
    InfraredLibraryCommandError,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import INFRARED_EMITTER_ID, RAW_COMMAND

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _emitter_options(entity_id: str) -> dict[str, selector.SelectOptionDict]:
    """Return infrared emitter selector options for tests."""
    return {
        entity_id: selector.SelectOptionDict(
            value=entity_id,
            label="Test IR",
        )
    }


def _receiver_options(entity_id: str) -> dict[str, selector.SelectOptionDict]:
    """Return infrared receiver selector options for tests."""
    return {
        entity_id: selector.SelectOptionDict(
            value=entity_id,
            label="Test IR Receiver",
        )
    }


async def test_user_flow_no_infrared_entities(hass: HomeAssistant) -> None:
    """Test abort when no infrared entities exist."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_available_infrared_devices"


async def test_user_flow_success(hass: HomeAssistant, infrared_emitter: str) -> None:
    """Test successful setup."""
    with (
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.async_setup_entry",
            return_value=True,
        ) as mock_setup,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room TV"
    assert result["data"] == {
        CONF_REMOTE_ID: "living_room_tv",
        CONF_REMOTE_NAME: "Living Room TV",
        CONF_INFRARED_EMITTER_ID: infrared_emitter,
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
    }
    assert result["options"] == {}
    assert len(mock_setup.mock_calls) == 1


async def test_user_flow_receiver_only_generic_creates_entry(
    hass: HomeAssistant,
) -> None:
    """Test setup allows receiver-only generic remotes for learning."""
    receiver_id = "infrared.receiver"

    with (
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={},
        ),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_receivers",
            return_value=_receiver_options(receiver_id),
        ),
        patch(
            "custom_components.universal_remote.async_setup_entry",
            return_value=True,
        ) as mock_setup,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REMOTE_NAME: "Learning Remote",
                CONF_INFRARED_RECEIVER_ID: receiver_id,
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Learning Remote"
    assert result["data"] == {
        CONF_REMOTE_ID: "learning_remote",
        CONF_REMOTE_NAME: "Learning Remote",
        CONF_INFRARED_RECEIVER_ID: receiver_id,
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
    }
    assert result["options"] == {}
    assert len(mock_setup.mock_calls) == 1


async def test_user_flow_receiver_tv_without_codeset_creates_entry(
    hass: HomeAssistant,
) -> None:
    """Test setup allows receiver remotes to skip library codesets."""
    receiver_id = "infrared.receiver"

    with (
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={},
        ),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_receivers",
            return_value=_receiver_options(receiver_id),
        ),
        patch(
            "custom_components.universal_remote.async_setup_entry",
            return_value=True,
        ) as mock_setup,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REMOTE_NAME: "Learning TV",
                CONF_INFRARED_RECEIVER_ID: receiver_id,
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            },
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "select_codeset"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_REMOTE_CODESET: NO_INFRARED_LIBRARY_CODESET},
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Learning TV"
    assert result["data"] == {
        CONF_REMOTE_ID: "learning_tv",
        CONF_REMOTE_NAME: "Learning TV",
        CONF_INFRARED_RECEIVER_ID: receiver_id,
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
    }
    assert result["options"] == {}
    assert len(mock_setup.mock_calls) == 1


@pytest.mark.parametrize(
    ("user_input", "errors"),
    [
        (
            {
                CONF_REMOTE_NAME: "",
                CONF_INFRARED_EMITTER_ID: INFRARED_EMITTER_ID,
            },
            {CONF_REMOTE_NAME: "remote_name_required"},
        ),
    ],
)
async def test_user_flow_validation_errors(
    hass: HomeAssistant,
    infrared_emitter: str,
    user_input: dict[str, str],
    errors: dict[str, str],
) -> None:
    """Test setup validation errors."""
    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value=_emitter_options(infrared_emitter),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


async def test_user_flow_aborts_duplicate_remote_id(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup aborts when a remote with the same normalized name exists."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data={
            CONF_REMOTE_ID: "living_room_tv",
            CONF_REMOTE_NAME: "Living Room TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={},
        unique_id="living_room_tv",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value=_emitter_options(infrared_emitter),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_success_single_entry_storage(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test reconfiguring a single-remote config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data={
            CONF_REMOTE_ID: "living_room_tv",
            CONF_REMOTE_NAME: "Living Room TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        },
        options={},
        unique_id="living_room_tv",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value=_emitter_options(infrared_emitter),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": entry.entry_id,
            },
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REMOTE_NAME: "Bedroom TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data == {
        CONF_REMOTE_ID: "living_room_tv",
        CONF_REMOTE_NAME: "Bedroom TV",
        CONF_INFRARED_EMITTER_ID: infrared_emitter,
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
    }


async def test_reconfigure_validation_errors(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test reconfigure validation errors."""
    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value=_emitter_options(INFRARED_EMITTER_ID),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_RECONFIGURE,
                "entry_id": config_entry.entry_id,
            },
        )

        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_REMOTE_NAME: "",
                CONF_INFRARED_EMITTER_ID: INFRARED_EMITTER_ID,
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REMOTE_NAME: "remote_name_required"}


async def test_direct_user_step_rejects_unavailable_infrared_emitter(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test user step handles unavailable selected infrared entity."""
    flow = UniversalRemoteConfigFlow()
    flow.hass = hass

    with (
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={"infrared.test_ir": "Test IR"},
        ),
        patch.object(flow, "async_set_unique_id", AsyncMock(return_value=None)),
        patch.object(flow, "_abort_if_unique_id_configured", return_value=None),
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: "infrared.missing",
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_INFRARED_EMITTER_ID: "infrared_emitter_unavailable"}


async def test_direct_reconfigure_step_rejects_unavailable_infrared_emitter(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure step handles unavailable selected infrared emitter."""
    config_entry.add_to_hass(hass)

    flow = UniversalRemoteConfigFlow()
    flow.hass = hass

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={"infrared.test_ir": "Test IR"},
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Bedroom TV",
                CONF_INFRARED_EMITTER_ID: "infrared.missing",
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_INFRARED_EMITTER_ID: "infrared_emitter_unavailable"}


def _direct_flow(hass: HomeAssistant) -> UniversalRemoteConfigFlow:
    """Return a config flow instance for direct step tests."""
    flow = UniversalRemoteConfigFlow()
    flow.hass = hass
    return flow


def _prepared_flow(hass: HomeAssistant) -> UniversalRemoteConfigFlow:
    """Return a direct flow with pending base entry data."""
    flow = _direct_flow(hass)
    flow._name = "Living Room TV"
    flow._infrared_emitter_id = INFRARED_EMITTER_ID
    flow._device_type = DEVICE_TYPE_TV
    flow._codeset_id = "lg_tv"
    return flow


async def test_user_flow_rejects_invalid_device_type(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test setup handles an invalid selected device type."""
    flow = _direct_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value={infrared_emitter: "Test IR"},
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_REMOTE_DEVICE_TYPE: "invalid",
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REMOTE_DEVICE_TYPE: "invalid_device_type"}


async def test_user_flow_tv_device_type_shows_codeset_step(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test selecting a TV device type continues to codeset selection."""
    flow = _direct_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={infrared_emitter: "Test IR"},
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "validate_infrared_library_device_type",
            return_value=True,
        ),
        patch.object(flow, "async_set_unique_id", AsyncMock(return_value=None)),
        patch.object(flow, "_abort_if_unique_id_configured", return_value=None),
        patch(
            "custom_components.universal_remote.config_flow."
            "infrared_library_codeset_options",
            return_value=[
                {"value": NO_INFRARED_LIBRARY_CODESET, "label": "None"},
                {"value": "lg_tv", "label": "LG TV"},
            ],
        ),
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_codeset"


async def test_select_codeset_without_pending_data_returns_user_step(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test codeset selection restarts when setup state is incomplete."""
    flow = _direct_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value={infrared_emitter: "Test IR"},
    ):
        result = await flow.async_step_select_codeset()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_select_codeset_generic_creates_entry(hass: HomeAssistant) -> None:
    """Test codeset selection is skipped for generic remotes."""
    flow = _prepared_flow(hass)
    flow._device_type = DEVICE_TYPE_GENERIC
    flow._codeset_id = NO_INFRARED_LIBRARY_CODESET

    result = await flow.async_step_select_codeset()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_REMOTE_CODESET not in result["data"]


async def test_select_codeset_rejects_invalid_codeset(hass: HomeAssistant) -> None:
    """Test codeset selection handles invalid codesets."""
    flow = _prepared_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow."
        "validate_infrared_library_codeset",
        return_value=False,
    ):
        result = await flow.async_step_select_codeset({CONF_REMOTE_CODESET: "bad"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REMOTE_CODESET: "invalid_library_codeset"}


async def test_select_codeset_none_creates_entry(hass: HomeAssistant) -> None:
    """Test selecting no library codeset creates the entry."""
    flow = _prepared_flow(hass)

    result = await flow.async_step_select_codeset(
        {CONF_REMOTE_CODESET: NO_INFRARED_LIBRARY_CODESET}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_REMOTE_CODESET not in result["data"]


async def test_select_codeset_valid_codeset_shows_import_step(
    hass: HomeAssistant,
) -> None:
    """Test selecting a real library codeset asks about command import."""
    flow = _prepared_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow."
        "validate_infrared_library_codeset",
        return_value=True,
    ):
        result = await flow.async_step_select_codeset({CONF_REMOTE_CODESET: "lg_tv"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "import_commands"


async def test_import_commands_without_pending_data_returns_user_step(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test import step restarts when setup state is incomplete."""
    flow = _direct_flow(hass)
    flow._codeset_id = "lg_tv"

    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value={infrared_emitter: "Test IR"},
    ):
        result = await flow.async_step_import_commands()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_import_commands_no_codeset_creates_entry(hass: HomeAssistant) -> None:
    """Test import step creates the entry when no real codeset is selected."""
    flow = _prepared_flow(hass)
    flow._codeset_id = NO_INFRARED_LIBRARY_CODESET

    result = await flow.async_step_import_commands()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {}


@pytest.mark.parametrize("import_mode", [IMPORT_COMMANDS_NO, "invalid"])
async def test_import_commands_no_or_invalid_mode(
    hass: HomeAssistant,
    import_mode: str,
) -> None:
    """Test import command mode handling."""
    flow = _prepared_flow(hass)

    result = await flow.async_step_import_commands({CONF_IMPORT_COMMANDS: import_mode})

    if import_mode == IMPORT_COMMANDS_NO:
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["options"] == {}
    else:
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {CONF_IMPORT_COMMANDS: "invalid_import_mode"}


async def test_import_all_commands_success(hass: HomeAssistant) -> None:
    """Test importing all commands from a library codeset."""
    flow = _prepared_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow."
        "generate_commands_from_library_codeset",
        return_value={"POWER": RAW_COMMAND},
    ) as generate_commands:
        result = await flow.async_step_import_commands(
            {
                CONF_IMPORT_COMMANDS: IMPORT_COMMANDS_ALL,
                CONF_CREATE_BUTTON: True,
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_REMOTE_COMMANDS]["POWER"] == {
        "data": RAW_COMMAND,
        "create_button": True,
    }
    generate_commands.assert_called_once_with("lg_tv")


async def test_import_all_commands_handles_generation_error(
    hass: HomeAssistant,
) -> None:
    """Test importing all commands handles library generation errors."""
    flow = _prepared_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow."
        "generate_commands_from_library_codeset",
        side_effect=InfraredLibraryCommandError,
    ):
        result = await flow.async_step_import_commands(
            {CONF_IMPORT_COMMANDS: IMPORT_COMMANDS_ALL}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_IMPORT_COMMANDS: "invalid_library_command"}


async def test_import_select_commands_shows_selection_step(
    hass: HomeAssistant,
) -> None:
    """Test choosing selected import mode shows library command selection."""
    flow = _prepared_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow."
        "infrared_library_command_options",
        return_value=[{"value": "POWER", "label": "POWER"}],
    ):
        result = await flow.async_step_import_commands(
            {
                CONF_IMPORT_COMMANDS: IMPORT_COMMANDS_SELECT,
                CONF_CREATE_BUTTON: True,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_library_commands"
    assert flow._create_button is True


async def test_select_library_commands_without_pending_data_returns_user_step(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test command selection restarts when setup state is incomplete."""
    flow = _direct_flow(hass)
    flow._codeset_id = "lg_tv"

    with patch(
        "custom_components.universal_remote.config_flow.available_infrared_emitters",
        return_value={infrared_emitter: "Test IR"},
    ):
        result = await flow.async_step_select_library_commands()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_select_library_commands_no_codeset_creates_entry(
    hass: HomeAssistant,
) -> None:
    """Test command selection creates an entry when no real codeset is selected."""
    flow = _prepared_flow(hass)
    flow._codeset_id = NO_INFRARED_LIBRARY_CODESET

    result = await flow.async_step_select_library_commands()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {}


@pytest.mark.parametrize("options", [None, []])
async def test_select_library_commands_invalid_codeset_aborts(
    hass: HomeAssistant,
    options: list[dict[str, str]] | None,
) -> None:
    """Test command selection aborts when the library cannot provide commands."""
    flow = _prepared_flow(hass)
    side_effect = InfraredLibraryCommandError if options is None else None

    with patch(
        "custom_components.universal_remote.config_flow."
        "infrared_library_command_options",
        side_effect=side_effect,
        return_value=options,
    ):
        result = await flow.async_step_select_library_commands()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_library_codeset"


@pytest.mark.parametrize(
    ("user_input", "errors"),
    [
        (
            {CONF_LIBRARY_COMMANDS: [], CONF_REPEAT_COUNT: 0},
            {CONF_LIBRARY_COMMANDS: "library_commands_required"},
        ),
        (
            {CONF_LIBRARY_COMMANDS: ["POWER"], CONF_REPEAT_COUNT: -1},
            {CONF_REPEAT_COUNT: "invalid_repeat_count"},
        ),
    ],
)
async def test_select_library_commands_validation_errors(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    errors: dict[str, str],
) -> None:
    """Test selected command import validation errors."""
    flow = _prepared_flow(hass)

    with patch(
        "custom_components.universal_remote.config_flow."
        "infrared_library_command_options",
        return_value=[{"value": "POWER", "label": "POWER"}],
    ):
        result = await flow.async_step_select_library_commands(user_input)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


async def test_select_library_commands_success_with_string_selection(
    hass: HomeAssistant,
) -> None:
    """Test selected command import handles string command selection."""
    flow = _prepared_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow."
            "infrared_library_command_options",
            return_value=[{"value": "POWER", "label": "POWER"}],
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "generate_selected_commands_from_library_codeset",
            return_value={"POWER": RAW_COMMAND},
        ) as generate_commands,
    ):
        result = await flow.async_step_select_library_commands(
            {
                CONF_LIBRARY_COMMANDS: "POWER",
                CONF_REPEAT_COUNT: 2,
                CONF_CREATE_BUTTON: True,
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_REMOTE_COMMANDS]["POWER"] == {
        "data": RAW_COMMAND,
        "create_button": True,
    }
    generate_commands.assert_called_once_with("lg_tv", ["POWER"], 2)


async def test_select_library_commands_handles_generation_error(
    hass: HomeAssistant,
) -> None:
    """Test selected command import handles library generation errors."""
    flow = _prepared_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow."
            "infrared_library_command_options",
            return_value=[{"value": "POWER", "label": "POWER"}],
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "generate_selected_commands_from_library_codeset",
            side_effect=InfraredLibraryCommandError,
        ),
    ):
        result = await flow.async_step_select_library_commands(
            {CONF_LIBRARY_COMMANDS: ["POWER"], CONF_REPEAT_COUNT: 0}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_LIBRARY_COMMANDS: "invalid_library_command"}


async def test_reconfigure_without_remote_aborts(
    hass: HomeAssistant,
) -> None:
    """Test reconfigure aborts when no remote is stored."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    flow = _direct_flow(hass)

    with patch.object(flow, "_get_reconfigure_entry", return_value=entry):
        result = await flow.async_step_reconfigure()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_reconfigure_without_infrared_entities_aborts(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test reconfigure aborts when no infrared entities are available."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={},
        ),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_receivers",
            return_value={},
        ),
    ):
        result = await flow.async_step_reconfigure()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_available_infrared_devices"


async def test_reconfigure_rejects_invalid_device_type(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure validates the selected device type."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={infrared_emitter: "Test IR"},
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "validate_infrared_library_device_type",
            return_value=False,
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_REMOTE_DEVICE_TYPE: "invalid",
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REMOTE_DEVICE_TYPE: "invalid_device_type"}


async def test_reconfigure_tv_device_type_shows_codeset_step(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure continues to codeset selection for TV remotes."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={infrared_emitter: "Test IR"},
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "validate_infrared_library_device_type",
            return_value=True,
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "infrared_library_codeset_options",
            return_value=[
                {"value": NO_INFRARED_LIBRARY_CODESET, "label": "None"},
                {"value": "lg_tv", "label": "LG TV"},
            ],
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_codeset"


async def test_reconfigure_codeset_without_remote_aborts(
    hass: HomeAssistant,
) -> None:
    """Test reconfigure codeset step aborts when no remote is stored."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    flow = _direct_flow(hass)

    with patch.object(flow, "_get_reconfigure_entry", return_value=entry):
        result = await flow.async_step_reconfigure_codeset()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


async def test_reconfigure_codeset_generic_updates_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test reconfigure codeset step clears codeset for generic remotes."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }
    remote = dict(config_entry.data)
    remote[CONF_REMOTE_CODESET] = "lg_tv"
    remote[CONF_REMOTE_DEVICE_TYPE] = DEVICE_TYPE_GENERIC
    flow._reconfigure_remote = remote

    with patch.object(flow, "_get_reconfigure_entry", return_value=config_entry):
        result = await flow.async_step_reconfigure_codeset()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert CONF_REMOTE_CODESET not in config_entry.data


async def test_reconfigure_codeset_rejects_invalid_codeset(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test reconfigure codeset step validates selected codeset."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }
    flow._reconfigure_remote = dict(config_entry.data)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow."
            "validate_infrared_library_codeset",
            return_value=False,
        ),
    ):
        result = await flow.async_step_reconfigure_codeset({CONF_REMOTE_CODESET: "bad"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_REMOTE_CODESET: "invalid_library_codeset"}


@pytest.mark.parametrize("codeset", [NO_INFRARED_LIBRARY_CODESET, "lg_tv"])
async def test_reconfigure_codeset_updates_entry(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    codeset: str,
) -> None:
    """Test reconfigure codeset step updates or clears the stored codeset."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }
    flow._reconfigure_remote = dict(config_entry.data)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow."
            "validate_infrared_library_codeset",
            return_value=True,
        ),
    ):
        result = await flow.async_step_reconfigure_codeset(
            {CONF_REMOTE_CODESET: codeset}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    if codeset == NO_INFRARED_LIBRARY_CODESET:
        assert CONF_REMOTE_CODESET not in config_entry.data
    else:
        assert config_entry.data[CONF_REMOTE_CODESET] == codeset


def test_create_entry_without_pending_data_aborts(hass: HomeAssistant) -> None:
    """Test create entry aborts when pending data is incomplete."""
    flow = _direct_flow(hass)

    result = flow._create_entry({})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


def test_create_entry_with_codeset_infers_device_type(hass: HomeAssistant) -> None:
    """Test create entry stores selected codeset and inferred device type."""
    flow = _prepared_flow(hass)
    flow._device_type = DEVICE_TYPE_GENERIC
    flow._codeset_id = "lg_tv"

    with patch(
        "custom_components.universal_remote.config_flow."
        "infrared_library_codeset_device_type",
        return_value=DEVICE_TYPE_TV,
    ):
        result = flow._create_entry({"POWER": {"data": RAW_COMMAND}})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_DEVICE_TYPE] == DEVICE_TYPE_TV
    assert result["data"][CONF_REMOTE_CODESET] == "lg_tv"
    assert result["options"][CONF_REMOTE_COMMANDS] == {"POWER": {"data": RAW_COMMAND}}


def test_options_flow_factory(config_entry: MockConfigEntry) -> None:
    """Test the config flow creates the options flow."""
    options_flow = UniversalRemoteConfigFlow.async_get_options_flow(config_entry)

    assert options_flow is not None


async def test_direct_user_step_rejects_unavailable_infrared_receiver(
    hass: HomeAssistant,
) -> None:
    """Test user step handles unavailable selected infrared receiver."""
    flow = _direct_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value={},
        ),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_RECEIVER_ID: "infrared.missing",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_unavailable"
    }


async def test_reconfigure_requires_infrared_target(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure requires at least one infrared target."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_receivers",
            return_value={},
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: "",
                CONF_INFRARED_RECEIVER_ID: "",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "infrared_target_required"}


async def test_reconfigure_rejects_unavailable_infrared_receiver(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure handles unavailable selected infrared receiver."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.config_flow.available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Bedroom TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_INFRARED_RECEIVER_ID: "infrared.missing",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_unavailable"
    }


def test_update_reconfigure_entry_supports_receiver_only(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test reconfigure update stores receiver-only target data."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }
    remote = dict(config_entry.data)
    remote.pop(CONF_INFRARED_EMITTER_ID, None)
    remote[CONF_INFRARED_RECEIVER_ID] = "infrared.receiver"

    with patch.object(flow, "_get_reconfigure_entry", return_value=config_entry):
        result = flow._update_reconfigure_entry(remote)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert CONF_INFRARED_EMITTER_ID not in config_entry.data
    assert config_entry.data[CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"


async def test_reconfigure_codeset_receiver_allows_no_codeset(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test receiver reconfigure can clear the codeset for learning-only use."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }
    remote = dict(config_entry.data)
    remote[CONF_INFRARED_RECEIVER_ID] = "infrared.receiver"
    remote[CONF_REMOTE_DEVICE_TYPE] = DEVICE_TYPE_TV
    flow._reconfigure_remote = remote

    with patch.object(flow, "_get_reconfigure_entry", return_value=config_entry):
        result = await flow.async_step_reconfigure_codeset(
            {CONF_REMOTE_CODESET: NO_INFRARED_LIBRARY_CODESET}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"
    assert CONF_REMOTE_CODESET not in config_entry.data


async def test_reconfigure_codeset_receiver_allows_unsupported_codeset(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
) -> None:
    """Test receiver reconfigure allows codesets used for commands only."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }
    remote = dict(config_entry.data)
    remote[CONF_INFRARED_RECEIVER_ID] = "infrared.receiver"
    remote[CONF_REMOTE_DEVICE_TYPE] = DEVICE_TYPE_TV
    flow._reconfigure_remote = remote

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow."
            "validate_infrared_library_codeset",
            return_value=True,
        ),
    ):
        result = await flow.async_step_reconfigure_codeset(
            {CONF_REMOTE_CODESET: "samsung_tv"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"
    assert config_entry.data[CONF_REMOTE_CODESET] == "samsung_tv"



async def test_user_flow_rejects_missing_infrared_target_direct(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test user flow requires at least one infrared target."""
    flow = _direct_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "infrared_target_required"}


async def test_user_flow_rejects_unavailable_receiver_direct(
    hass: HomeAssistant,
) -> None:
    """Test user flow rejects an unavailable selected receiver."""
    flow = _direct_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_emitters",
            return_value={},
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_RECEIVER_ID: "infrared.missing",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_unavailable"
    }


async def test_select_codeset_receiver_allows_no_codeset_direct(
    hass: HomeAssistant,
) -> None:
    """Test receiver setup can continue without a library codeset."""
    flow = _direct_flow(hass)
    flow._name = "Living Room TV"
    flow._infrared_receiver_id = "infrared.receiver"
    flow._device_type = DEVICE_TYPE_TV

    result = await flow.async_step_select_codeset(
        {CONF_REMOTE_CODESET: NO_INFRARED_LIBRARY_CODESET}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"
    assert CONF_REMOTE_CODESET not in result["data"]


async def test_select_codeset_receiver_allows_unsupported_codeset_direct(
    hass: HomeAssistant,
) -> None:
    """Test receiver setup allows codesets used for commands only."""
    flow = _direct_flow(hass)
    flow._name = "Living Room TV"
    flow._infrared_receiver_id = "infrared.receiver"
    flow._device_type = DEVICE_TYPE_TV

    with patch(
        "custom_components.universal_remote.config_flow."
        "validate_infrared_library_codeset",
        return_value=True,
    ):
        result = await flow.async_step_select_codeset(
            {CONF_REMOTE_CODESET: "samsung_tv"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "import_commands"
    assert flow._codeset_id == "samsung_tv"


async def test_reconfigure_rejects_unavailable_receiver_direct(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure rejects an unavailable selected receiver."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: infrared_emitter,
                CONF_INFRARED_RECEIVER_ID: "infrared.missing",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_unavailable"
    }


async def test_reconfigure_can_replace_emitter_with_receiver_direct(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test reconfigure can remove an emitter and store a receiver."""
    flow = _direct_flow(hass)

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Living Room TV",
                CONF_INFRARED_EMITTER_ID: "",
                CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            }
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure_codeset"
    assert flow._reconfigure_remote is not None
    assert CONF_INFRARED_EMITTER_ID not in flow._reconfigure_remote
    assert flow._reconfigure_remote[CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"


def test_create_entry_receiver_only_stores_receiver_direct(
    hass: HomeAssistant,
) -> None:
    """Test create entry stores a receiver-only setup."""
    flow = _direct_flow(hass)
    flow._name = "Living Room TV"
    flow._infrared_receiver_id = "infrared.receiver"
    flow._device_type = DEVICE_TYPE_TV
    flow._codeset_id = "lg_tv"

    result = flow._create_entry({})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert CONF_INFRARED_EMITTER_ID not in result["data"]
    assert result["data"][CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"


def test_validate_generated_commands_raises_for_invalid_payload() -> None:
    """Test generated command validation raises library errors."""
    with pytest.raises(InfraredLibraryCommandError):
        _validate_generated_commands({"BAD": "not a command"})


def test_command_objects_sets_create_button_flag() -> None:
    """Test generated command data is stored as command objects."""
    assert _command_objects({"POWER": RAW_COMMAND}, create_button=True) == {
        "POWER": {"data": RAW_COMMAND, "create_button": True}
    }


async def test_user_flow_allows_receiver_with_generic_device_type_direct(
    hass: HomeAssistant,
) -> None:
    """Test receiver setup allows generic learning-only remotes."""
    flow = _direct_flow(hass)

    with (
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_emitters",
            return_value={},
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
        patch.object(flow, "async_set_unique_id", AsyncMock(return_value=None)),
        patch.object(flow, "_abort_if_unique_id_configured", return_value=None),
    ):
        result = await flow.async_step_user(
            {
                CONF_REMOTE_NAME: "Learning Remote",
                CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            }
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_REMOTE_ID: "learning_remote",
        CONF_REMOTE_NAME: "Learning Remote",
        CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
    }
    assert result["options"] == {}


async def test_reconfigure_allows_receiver_with_generic_device_type_direct(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    infrared_emitter: str,
) -> None:
    """Test receiver reconfigure allows generic learning-only remotes."""
    flow = _direct_flow(hass)
    flow.context = {
        "source": config_entries.SOURCE_RECONFIGURE,
        "entry_id": config_entry.entry_id,
    }

    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=config_entry),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_emitters",
            return_value=_emitter_options(infrared_emitter),
        ),
        patch(
            "custom_components.universal_remote.config_flow."
            "available_infrared_receivers",
            return_value=_receiver_options("infrared.receiver"),
        ),
    ):
        result = await flow.async_step_reconfigure(
            {
                CONF_REMOTE_NAME: "Learning Remote",
                CONF_INFRARED_EMITTER_ID: "",
                CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            }
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert CONF_INFRARED_EMITTER_ID not in config_entry.data
    assert config_entry.data[CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"
    assert config_entry.data[CONF_REMOTE_DEVICE_TYPE] == DEVICE_TYPE_GENERIC
    assert CONF_REMOTE_CODESET not in config_entry.data
