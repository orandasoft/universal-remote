"""Tests for the Universal Remote options flow."""

import asyncio
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

import pytest

from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
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
from custom_components.universal_remote.learn import (
    LEARN_DECODER_AUTO,
    LEARN_DECODER_NEC,
    LEARN_DECODER_NEC1_F16,
    LEARN_DECODER_NONE,
    LearnCapture,
    LearnResult,
)
from custom_components.universal_remote.learn_candidates import (
    CANDIDATE_CAPTURED,
    CANDIDATE_NORMALIZED,
    LearnCandidate,
)
from custom_components.universal_remote.options_flow import (
    COMMAND_DATA,
    COMMAND_LIBRARY_CODESET,
    COMMAND_LIBRARY_COMMAND,
    COMMAND_LIBRARY_COMMANDS,
    COMMAND_LEARN_CANDIDATE,
    COMMAND_LEARN_DECODER,
    COMMAND_LEARN_REVIEW_ACTION,
    COMMAND_NAME,
    COMMAND_OVERWRITE_EXISTING,
    COMMAND_REPEAT_COUNT,
    COMMAND_SOURCE,
    COMMAND_SOURCE_INFRARED_LIBRARY,
    COMMAND_SOURCE_RAW,
    LEARN_REVIEW_ACTION_CONTINUE_SAVE,
    LEARN_REVIEW_ACTION_DISCARD,
    LEARN_REVIEW_ACTION_RETRY_CAPTURE,
    LEARN_REVIEW_ACTION_SAVE_ANYWAY,
    LEARN_REVIEW_ACTION_TEST_CAPTURED,
    LEARN_REVIEW_ACTION_TEST_NORMALIZED,
    SOURCE_ADD_RAW_COMMAND,
    SOURCE_EDIT_COMMAND,
    SOURCE_EDIT_LIBRARY_CODESET,
    SOURCE_EDIT_LIBRARY_COMMAND,
    SOURCE_EDIT_RAW_COMMAND,
    SOURCE_IMPORT_LIBRARY_COMMAND_SELECT,
    SOURCE_IMPORT_LIBRARY_COMMANDS,
    SOURCE_LEARN_CAPTURE,
    SOURCE_LEARN_COMMAND,
    SOURCE_LEARN_REVIEW,
    SOURCE_LEARN_SELECT_CANDIDATE,
    SOURCE_LEARN_SELECT_DECODER,
    SOURCE_MANAGE_COMMANDS,
    SOURCE_REMOVE_COMMAND,
    UniversalRemoteOptionsFlow,
    learn_capture_details,
    learn_capture_receiver_label,
    learn_decoder_options,
    learn_review_action_options,
    learned_candidate_details,
    learned_candidate_options,
    library_command_default,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

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


def _learn_result(
    candidates: tuple[LearnCandidate, ...] | None = None,
) -> LearnResult:
    """Return a learned command result."""
    return LearnResult(
        capture=LearnCapture(
            timings=[9000, -4500, 560, -560],
            modulation=38_000,
            modulation_assumed=False,
            timing_count=4,
        ),
        candidates=candidates
        or (
            LearnCandidate(
                key=CANDIDATE_CAPTURED,
                payload=LEARNED_COMMAND,
                label_key=CANDIDATE_CAPTURED,
                recommended=True,
                metadata={"timing_count": 4},
            ),
        ),
    )


def _receiver_options() -> dict[str, dict[str, str]]:
    """Return available receiver options."""
    return {
        "infrared.test_receiver": {
            "value": "infrared.test_receiver",
            "label": "Test Receiver",
        }
    }


SELECT_COMMAND_FOR_EDIT = "select_command_for_edit"

SOURCE_ADD_COMMAND = SOURCE_ADD_RAW_COMMAND
LEARNED_COMMAND = "0000 006D 0002 0000 0156 00AB 0015 0015"


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




def _receiver_only_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a receiver-only one-remote config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Receiver TV",
        data={
            CONF_REMOTE_ID: "receiver_tv",
            CONF_REMOTE_NAME: "Receiver TV",
            CONF_INFRARED_RECEIVER_ID: "infrared.test_receiver",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={CONF_REMOTE_COMMANDS: {"POWER_ON": RAW_COMMAND}},
        unique_id="receiver_tv",
    )
    entry.add_to_hass(hass)
    return entry


def _receiver_and_emitter_entry(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> MockConfigEntry:
    """Create a one-remote config entry with receiver and emitter."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Learning TV",
        data={
            CONF_REMOTE_ID: "learning_tv",
            CONF_REMOTE_NAME: "Learning TV",
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_INFRARED_RECEIVER_ID: "infrared.test_receiver",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={CONF_REMOTE_COMMANDS: {"POWER_ON": RAW_COMMAND}},
        unique_id="learning_tv",
    )
    entry.add_to_hass(hass)
    return entry


def _learn_result_with_captured_and_normalized() -> LearnResult:
    """Return a learned result with captured and normalized candidates."""
    return _learn_result(
        (
            LearnCandidate(
                key=CANDIDATE_CAPTURED,
                payload="captured-payload",
                label_key=CANDIDATE_CAPTURED,
                recommended=False,
                metadata={"timing_count": 67, "modulation": 38_000},
            ),
            LearnCandidate(
                key=CANDIDATE_NORMALIZED,
                payload=LEARNED_COMMAND,
                label_key=CANDIDATE_NORMALIZED,
                recommended=True,
                metadata={
                    "decoder": "nec1_f16",
                    "protocol": "nec1_f16",
                    "address": "0xFB04",
                    "primary": "0xDB",
                    "secondary": "0x32",
                },
            ),
        )
    )


def _learn_review_action_values(result: Mapping[str, Any]) -> list[str]:
    """Return configured learn-review action values from a form result."""
    schema = result["data_schema"].schema
    for field, field_selector in schema.items():
        if getattr(field, "schema", None) == COMMAND_LEARN_REVIEW_ACTION:
            return [
                str(option["value"])
                for option in field_selector.config["options"]
            ]
    raise AssertionError("Learn review action selector was not found")


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




async def test_receiver_only_entry_options_flow_manages_commands(
    hass: HomeAssistant,
) -> None:
    """Test receiver-only entries can use command options."""
    entry = _receiver_only_entry(hass)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == SOURCE_MANAGE_COMMANDS
    assert result["menu_options"] == [
        SOURCE_ADD_RAW_COMMAND,
        SOURCE_LEARN_COMMAND,
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


async def test_learn_command_success(
    hass: HomeAssistant,
) -> None:
    """Test learning and saving a command from an infrared receiver."""
    entry = _receiver_only_entry(hass)

    result = await _init_options_flow(hass, entry, SOURCE_MANAGE_COMMANDS)
    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value=_receiver_options(),
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"next_step_id": SOURCE_LEARN_COMMAND},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == SOURCE_LEARN_COMMAND

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_INFRARED_RECEIVER_ID: "infrared.test_receiver"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_CAPTURE
    assert result["description_placeholders"] == {"receiver": "Test Receiver"}

    with patch(
        "custom_components.universal_remote.options_flow."
        "LearnSessionManager.async_capture_once",
        return_value=_learn_result().capture,
    ) as capture_once:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_DECODER
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    assert "4 timings" in description_placeholders["capture_details"]
    capture_once.assert_called_once_with("infrared.test_receiver")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_LEARN_DECODER: LEARN_DECODER_NONE},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    assert "4 timings" in description_placeholders["candidate_details"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_CONTINUE_SAVE},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_CANDIDATE

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            COMMAND_NAME: "Mute",
            COMMAND_LEARN_CANDIDATE: CANDIDATE_CAPTURED,
            CONF_COMMAND_CREATE_BUTTON: True,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS]["MUTE"] == _command_object(
        LEARNED_COMMAND,
        create_button=True,
    )


async def test_learn_command_without_available_receivers_aborts(
    hass: HomeAssistant,
) -> None:
    """Test learn command aborts when no receiver is available."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value={},
    ):
        result = await flow.async_step_learn_command()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_available_infrared_receivers"


async def test_learn_command_rejects_unavailable_receiver(
    hass: HomeAssistant,
) -> None:
    """Test learn command validates selected receiver."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value=_receiver_options(),
    ):
        result = await flow.async_step_learn_command(
            {CONF_INFRARED_RECEIVER_ID: "infrared.missing_receiver"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_COMMAND
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_unavailable"
    }


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (
            "custom_components.universal_remote.options_flow."
            "LearnSessionReceiverUnavailableError",
            "infrared_receiver_unavailable",
        ),
        (
            "custom_components.universal_remote.options_flow."
            "LearnSessionReceiverBusyError",
            "learn_receiver_busy",
        ),
        (
            "custom_components.universal_remote.options_flow."
            "LearnSessionTimeoutError",
            "learn_timeout",
        ),
    ],
)
async def test_learn_capture_errors(
    hass: HomeAssistant,
    side_effect: str,
    error: str,
) -> None:
    """Test learn capture error handling."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_receiver_id = "infrared.test_receiver"

    error_type = _import_from_string(side_effect)
    with patch(
        "custom_components.universal_remote.options_flow."
        "LearnSessionManager.async_capture_once",
        side_effect=error_type,
    ):
        result = await flow.async_step_learn_capture({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_CAPTURE
    assert result["errors"] == {"base": error}


async def test_learn_select_decoder_builds_candidates(
    hass: HomeAssistant,
) -> None:
    """Test selecting a decoder builds learned command candidates."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_capture = _learn_result().capture

    result = await flow.async_step_learn_select_decoder(
        {COMMAND_LEARN_DECODER: LEARN_DECODER_NONE}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    assert flow._learn_result is not None
    assert [candidate.key for candidate in flow._learn_result.candidates] == [
        CANDIDATE_CAPTURED
    ]


async def test_learn_select_decoder_rejects_invalid_decoder(
    hass: HomeAssistant,
) -> None:
    """Test decoder selection validates selected decoder."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_capture = _learn_result().capture

    result = await flow.async_step_learn_select_decoder(
        {COMMAND_LEARN_DECODER: "unsupported"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_DECODER
    assert result["errors"] == {COMMAND_LEARN_DECODER: "invalid_learn_decoder"}


async def test_learn_select_decoder_without_pending_capture_returns_learn_command_form(
    hass: HomeAssistant,
) -> None:
    """Test decoder selection redirects when pending capture is missing."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value=_receiver_options(),
    ):
        result = await flow.async_step_learn_select_decoder({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_COMMAND


async def test_learn_review_continue_to_save(
    hass: HomeAssistant,
) -> None:
    """Test continuing from review opens the save step."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review(
        {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_CONTINUE_SAVE}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_CANDIDATE


async def test_learn_review_retry_capture(
    hass: HomeAssistant,
) -> None:
    """Test retrying from review returns to the capture step."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_receiver_id = "infrared.test_receiver"
    flow._learn_capture = _learn_result().capture
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review(
        {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_RETRY_CAPTURE}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_CAPTURE
    assert flow._learn_capture is None
    assert flow._learn_result is None


async def test_learn_review_discard_leaves_options_unchanged(
    hass: HomeAssistant,
) -> None:
    """Test discarding from review saves no learned command."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_capture = _learn_result().capture
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review(
        {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_DISCARD}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == dict(entry.options)
    assert flow._learn_capture is None
    assert flow._learn_result is None


async def test_learn_review_rejects_invalid_action(
    hass: HomeAssistant,
) -> None:
    """Test review action validation."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review(
        {COMMAND_LEARN_REVIEW_ACTION: "missing"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    assert result["errors"] == {
        COMMAND_LEARN_REVIEW_ACTION: "invalid_learn_review_action"
    }


async def test_learn_review_rejects_hidden_test_action_without_emitter(
    hass: HomeAssistant,
) -> None:
    """Test hidden learned-candidate test actions cannot be submitted."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review(
        {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_TEST_CAPTURED}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    assert result["errors"] == {
        COMMAND_LEARN_REVIEW_ACTION: "invalid_learn_review_action"
    }


async def test_learn_review_test_captured_candidate(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test review can test-send the captured learned candidate."""
    entry = _receiver_and_emitter_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result_with_captured_and_normalized()

    with patch(
        "custom_components.universal_remote.options_flow.async_send_infrared_command",
        return_value=None,
    ) as send_command:
        result = await flow.async_step_learn_review(
            {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_TEST_CAPTURED}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    assert result["errors"] == {}
    send_command.assert_awaited_once_with(
        hass,
        infrared_emitter,
        "captured-payload",
    )


async def test_learn_review_test_normalized_candidate(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test review can test-send the normalized learned candidate."""
    entry = _receiver_and_emitter_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result_with_captured_and_normalized()

    with patch(
        "custom_components.universal_remote.options_flow.async_send_infrared_command",
        return_value=None,
    ) as send_command:
        result = await flow.async_step_learn_review(
            {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_TEST_NORMALIZED}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    assert result["errors"] == {}
    send_command.assert_awaited_once_with(
        hass,
        infrared_emitter,
        LEARNED_COMMAND,
    )


async def test_learn_review_test_send_failure_allows_save_anyway(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test failed learned-candidate test send allows save anyway."""
    entry = _receiver_and_emitter_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result_with_captured_and_normalized()

    with patch(
        "custom_components.universal_remote.options_flow.async_send_infrared_command",
        side_effect=HomeAssistantError("send failed"),
    ):
        result = await flow.async_step_learn_review(
            {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_TEST_CAPTURED}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    assert result["errors"] == {"base": "learn_test_send_failed"}
    assert flow._learn_test_send_failed is True
    assert LEARN_REVIEW_ACTION_SAVE_ANYWAY in _learn_review_action_values(result)
    assert LEARN_REVIEW_ACTION_CONTINUE_SAVE not in _learn_review_action_values(result)

    result = await flow.async_step_learn_review(
        {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_SAVE_ANYWAY}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_CANDIDATE


async def test_learn_review_hides_test_actions_without_emitter(
    hass: HomeAssistant,
) -> None:
    """Test review hides learned-candidate test actions without an emitter."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result_with_captured_and_normalized()

    result = await flow.async_step_learn_review()

    assert LEARN_REVIEW_ACTION_TEST_CAPTURED not in _learn_review_action_values(result)
    assert (
        LEARN_REVIEW_ACTION_TEST_NORMALIZED
        not in _learn_review_action_values(result)
    )


async def test_learn_review_hides_missing_normalized_test_action(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test review hides normalized test action without a normalized candidate."""
    entry = _receiver_and_emitter_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review()

    assert LEARN_REVIEW_ACTION_TEST_CAPTURED in _learn_review_action_values(result)
    assert (
        LEARN_REVIEW_ACTION_TEST_NORMALIZED
        not in _learn_review_action_values(result)
    )


async def test_learn_review_test_candidate_returns_false_without_emitter(
    hass: HomeAssistant,
) -> None:
    """Test learned-candidate test send is skipped without an emitter."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow._async_test_learned_candidate(
        LEARN_REVIEW_ACTION_TEST_CAPTURED,
        _learn_result().candidates,
    )

    assert result is False


async def test_learn_review_test_candidate_returns_false_without_candidate(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test learned-candidate test send is skipped without that candidate."""
    entry = _receiver_and_emitter_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow._async_test_learned_candidate(
        LEARN_REVIEW_ACTION_TEST_NORMALIZED,
        _learn_result().candidates,
    )

    assert result is False


async def test_learn_review_test_send_preserves_cancellation(
    hass: HomeAssistant,
    infrared_emitter: str,
) -> None:
    """Test learned-candidate test send does not swallow cancellation."""
    entry = _receiver_and_emitter_entry(hass, infrared_emitter)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    with (
        patch(
            "custom_components.universal_remote.options_flow."
            "async_send_infrared_command",
            side_effect=asyncio.CancelledError,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await flow.async_step_learn_review(
            {COMMAND_LEARN_REVIEW_ACTION: LEARN_REVIEW_ACTION_TEST_CAPTURED}
        )


def test_learn_test_send_emitter_id_returns_none_without_remote(
    hass: HomeAssistant,
) -> None:
    """Test learned-candidate test send is unavailable without a remote."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Empty",
        data={},
        options={},
        unique_id="empty",
    )
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    assert flow._learn_test_send_emitter_id is None


def test_learn_test_send_emitter_id_returns_none_for_missing_state(
    hass: HomeAssistant,
) -> None:
    """Test learned-candidate test send is unavailable when emitter state is missing."""
    entry = _receiver_and_emitter_entry(hass, "infrared.missing_emitter")
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    assert flow._learn_test_send_emitter_id is None


async def test_learn_review_form_shows_candidate_details(
    hass: HomeAssistant,
) -> None:
    """Test review form summarizes learned candidates."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_review()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_REVIEW
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    assert "4 timings" in description_placeholders["candidate_details"]


async def test_learn_review_without_candidates_aborts(
    hass: HomeAssistant,
) -> None:
    """Test review aborts when no learned candidates exist."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = LearnResult(
        capture=_learn_result().capture,
        candidates=(),
    )

    result = await flow.async_step_learn_review()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "learn_failed"


async def test_learn_review_without_result_returns_decoder_form(
    hass: HomeAssistant,
) -> None:
    """Test review redirects to decoder when capture exists but result is missing."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_capture = _learn_result().capture

    result = await flow.async_step_learn_review({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_DECODER


async def test_learn_review_without_pending_state_returns_learn_command_form(
    hass: HomeAssistant,
) -> None:
    """Test review redirects when no learned capture or result exists."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value=_receiver_options(),
    ):
        result = await flow.async_step_learn_review({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_COMMAND


async def test_learn_select_candidate_selects_normalized_candidate(
    hass: HomeAssistant,
) -> None:
    """Test saving a selected normalized learned candidate."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result(
        (
            LearnCandidate(
                key=CANDIDATE_CAPTURED,
                payload="captured-payload",
                label_key=CANDIDATE_CAPTURED,
                recommended=False,
                metadata={"timing_count": 67, "modulation": 38_000},
            ),
            LearnCandidate(
                key=CANDIDATE_NORMALIZED,
                payload=LEARNED_COMMAND,
                label_key=CANDIDATE_NORMALIZED,
                recommended=True,
                metadata={
                    "decoder": "nec1_f16",
                    "protocol": "nec1_f16",
                    "address": "0xFB04",
                    "primary": "0xDB",
                    "secondary": "0x32",
                },
            ),
        )
    )

    result = await flow.async_step_learn_select_candidate(
        {
            COMMAND_NAME: "Mute",
            COMMAND_LEARN_CANDIDATE: CANDIDATE_NORMALIZED,
            CONF_COMMAND_CREATE_BUTTON: True,
        }
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS]["MUTE"] == _command_object(
        LEARNED_COMMAND,
        create_button=True,
    )


async def test_learn_select_candidate_rejects_empty_command_name(
    hass: HomeAssistant,
) -> None:
    """Test learned command name is required when saving a candidate."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_select_candidate(
        {
            COMMAND_NAME: "   ",
            COMMAND_LEARN_CANDIDATE: CANDIDATE_CAPTURED,
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_CANDIDATE
    assert result["errors"] == {COMMAND_NAME: "command_name_required"}


async def test_learn_select_candidate_rejects_duplicate_command_name(
    hass: HomeAssistant,
) -> None:
    """Test learned commands cannot replace an existing command accidentally."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_select_candidate(
        {
            COMMAND_NAME: "Power On",
            COMMAND_LEARN_CANDIDATE: CANDIDATE_CAPTURED,
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_CANDIDATE
    assert result["errors"] == {COMMAND_NAME: "command_name_exists"}


async def test_learn_select_candidate_overwrites_existing_command_when_confirmed(
    hass: HomeAssistant,
) -> None:
    """Test learned commands can replace an existing command when confirmed."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_select_candidate(
        {
            COMMAND_NAME: "Power On",
            COMMAND_LEARN_CANDIDATE: CANDIDATE_CAPTURED,
            COMMAND_OVERWRITE_EXISTING: True,
        }
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_REMOTE_COMMANDS]["POWER_ON"] == _command_object(
        LEARNED_COMMAND
    )


async def test_learn_select_candidate_rejects_invalid_candidate(
    hass: HomeAssistant,
) -> None:
    """Test learned candidate selection validation."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result()

    result = await flow.async_step_learn_select_candidate(
        {
            COMMAND_NAME: "Mute",
            COMMAND_LEARN_CANDIDATE: "missing",
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_CANDIDATE
    assert result["errors"] == {COMMAND_LEARN_CANDIDATE: "invalid_learn_candidate"}


async def test_learn_select_candidate_form_shows_candidate_details(
    hass: HomeAssistant,
) -> None:
    """Test learned candidate form shows decoded and captured details."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = _learn_result(
        (
            LearnCandidate(
                key=CANDIDATE_CAPTURED,
                payload="captured-payload",
                label_key=CANDIDATE_CAPTURED,
                recommended=False,
                metadata={
                    "timing_count": 67,
                    "modulation": 38_000,
                    "modulation_assumed": True,
                },
            ),
            LearnCandidate(
                key=CANDIDATE_NORMALIZED,
                payload=LEARNED_COMMAND,
                label_key=CANDIDATE_NORMALIZED,
                recommended=True,
                metadata={
                    "protocol": "nec1_f16",
                    "address": "0xFB04",
                    "primary": "0xDB",
                    "secondary": "0x32",
                },
            ),
        )
    )

    result = await flow.async_step_learn_select_candidate()

    assert result["type"] is FlowResultType.FORM
    description_placeholders = result["description_placeholders"]
    assert description_placeholders is not None
    details = description_placeholders["candidate_details"]
    assert "Captured — 67 timings, 38000 Hz assumed" in details
    assert (
        "Normalized (recommended) — NEC1-F16, address 0xFB04, "
        "function 0xDB, subfunction 0x32"
    ) in details


async def test_learn_select_candidate_without_candidates_aborts(
    hass: HomeAssistant,
) -> None:
    """Test learn candidate selection aborts when no candidates exist."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_result = LearnResult(
        capture=LearnCapture(
            timings=[9000, -4500, 560, -560],
            modulation=38_000,
            modulation_assumed=False,
            timing_count=4,
        ),
        candidates=(),
    )

    result = await flow.async_step_learn_select_candidate({})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "learn_failed"


async def test_learn_capture_without_pending_state_returns_learn_command_form(
    hass: HomeAssistant,
) -> None:
    """Test learn capture redirects when pending learn state is missing."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value=_receiver_options(),
    ):
        result = await flow.async_step_learn_capture({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_COMMAND


async def test_learn_select_candidate_without_result_returns_decoder_form(
    hass: HomeAssistant,
) -> None:
    """Test candidate selection redirects to decoder when capture exists."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass
    flow._learn_capture = _learn_result().capture

    result = await flow.async_step_learn_select_candidate({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_SELECT_DECODER


async def test_learn_select_candidate_without_pending_state_returns_learn_command_form(
    hass: HomeAssistant,
) -> None:
    """Test learn candidate selection redirects when pending state is missing."""
    entry = _receiver_only_entry(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    with patch(
        "custom_components.universal_remote.options_flow.available_infrared_receivers",
        return_value=_receiver_options(),
    ):
        result = await flow.async_step_learn_select_candidate({})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == SOURCE_LEARN_COMMAND


async def test_learn_steps_without_remote_abort(hass: HomeAssistant) -> None:
    """Test learn steps abort when the entry has no remote."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    flow = UniversalRemoteOptionsFlow(entry)
    flow.hass = hass

    result = await flow.async_step_learn_command()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"

    result = await flow.async_step_learn_capture({})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"

    result = await flow.async_step_learn_select_decoder({})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"

    result = await flow.async_step_learn_review({})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"

    result = await flow.async_step_learn_select_candidate({})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_universal_remotes"


def test_learned_candidate_options_include_metadata() -> None:
    """Test learned candidate labels include safe metadata."""
    options = learned_candidate_options(
        (
            LearnCandidate(
                key=CANDIDATE_CAPTURED,
                payload="captured-payload",
                label_key=CANDIDATE_CAPTURED,
                recommended=False,
                metadata={
                    "timing_count": 67,
                    "modulation": 38_000,
                    "modulation_assumed": True,
                },
            ),
            LearnCandidate(
                key=CANDIDATE_NORMALIZED,
                payload=LEARNED_COMMAND,
                label_key=CANDIDATE_NORMALIZED,
                recommended=True,
                metadata={
                    "protocol": "nec",
                    "address": "0x00FB",
                    "primary": "0xDB",
                },
            ),
        )
    )

    assert options == [
        {
            "value": CANDIDATE_CAPTURED,
            "label": "Captured — 67 timings, 38000 Hz assumed",
        },
        {
            "value": CANDIDATE_NORMALIZED,
            "label": "Normalized (recommended) — NEC, address 0x00FB, command 0xDB",
        },
    ]


def test_learned_candidate_details_handles_minimal_metadata() -> None:
    """Test learned candidate details handles candidates without metadata."""
    details = learned_candidate_details(
        (
            LearnCandidate(
                key=CANDIDATE_CAPTURED,
                payload="captured-payload",
                label_key=CANDIDATE_CAPTURED,
                recommended=False,
                metadata={},
            ),
        )
    )

    assert details == "- Captured"


def test_learn_decoder_options() -> None:
    """Test decoder selector options."""
    assert learn_decoder_options() == [
        {"value": LEARN_DECODER_AUTO, "label": "Auto (recommended)"},
        {"value": LEARN_DECODER_NONE, "label": "None / captured only"},
        {"value": LEARN_DECODER_NEC, "label": "NEC"},
        {"value": LEARN_DECODER_NEC1_F16, "label": "NEC1-F16"},
    ]


def test_learn_review_action_options() -> None:
    """Test learned-command review action selector options."""
    assert learn_review_action_options() == [
        {"value": LEARN_REVIEW_ACTION_CONTINUE_SAVE, "label": "Continue to save"},
        {"value": LEARN_REVIEW_ACTION_RETRY_CAPTURE, "label": "Retry capture"},
        {"value": LEARN_REVIEW_ACTION_DISCARD, "label": "Discard"},
    ]


def test_learn_review_action_options_include_test_send_actions() -> None:
    """Test learned-command review actions include available test sends."""
    assert learn_review_action_options(
        _learn_result_with_captured_and_normalized().candidates,
        can_test_send=True,
    ) == [
        {
            "value": LEARN_REVIEW_ACTION_TEST_CAPTURED,
            "label": "Test captured candidate",
        },
        {
            "value": LEARN_REVIEW_ACTION_TEST_NORMALIZED,
            "label": "Test normalized candidate",
        },
        {"value": LEARN_REVIEW_ACTION_CONTINUE_SAVE, "label": "Continue to save"},
        {"value": LEARN_REVIEW_ACTION_RETRY_CAPTURE, "label": "Retry capture"},
        {"value": LEARN_REVIEW_ACTION_DISCARD, "label": "Discard"},
    ]


def test_learn_review_action_options_show_save_anyway_after_test_send_failure() -> None:
    """Test failed test-send review actions include save anyway."""
    assert learn_review_action_options(
        _learn_result().candidates,
        can_test_send=True,
        test_send_failed=True,
    ) == [
        {
            "value": LEARN_REVIEW_ACTION_TEST_CAPTURED,
            "label": "Test captured candidate",
        },
        {"value": LEARN_REVIEW_ACTION_SAVE_ANYWAY, "label": "Save anyway"},
        {"value": LEARN_REVIEW_ACTION_RETRY_CAPTURE, "label": "Retry capture"},
        {"value": LEARN_REVIEW_ACTION_DISCARD, "label": "Discard"},
    ]


def test_learn_capture_details() -> None:
    """Test capture details include timing count and modulation."""
    assert (
        learn_capture_details(
            LearnCapture(
                timings=[9000, -4500, 560, -560],
                modulation=38_000,
                modulation_assumed=True,
                timing_count=4,
                likely_protocol="nec_repeat",
            )
        )
        == "4 timings, 38000 Hz assumed, likely nec-repeat"
    )


def _import_from_string(path: str) -> type[Exception]:
    """Import an exception type from a dotted path."""
    module_name, _, attribute = path.rpartition(".")
    module = __import__(module_name, fromlist=[attribute])
    return getattr(module, attribute)


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



def test_learn_capture_receiver_label_removes_entity_suffix() -> None:
    """Test capture receiver label omits parenthesized entity id."""
    assert (
        learn_capture_receiver_label(
            "IR Proxy Receiver — Living Room XIAO Smart IR Mate "
            "(infrared.living_room_xiao_smart_ir_mate_ir_proxy_receiver)",
            "infrared.living_room_xiao_smart_ir_mate_ir_proxy_receiver",
        )
        == "IR Proxy Receiver — Living Room XIAO Smart IR Mate"
    )


def test_learn_capture_receiver_label_falls_back_to_entity_id() -> None:
    """Test capture receiver label falls back to entity id."""
    assert (
        learn_capture_receiver_label(None, "infrared.test_receiver")
        == "infrared.test_receiver"
    )


def test_learn_capture_receiver_label_keeps_label_without_entity_id() -> None:
    """Test capture receiver label keeps label when entity id is unavailable."""
    assert learn_capture_receiver_label("Test Receiver", None) == "Test Receiver"
