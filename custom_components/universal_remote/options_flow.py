"""Options flow for Universal Remote."""

import asyncio
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .command import CommandParseError, validate_remote_command_payload
from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
)
from .helpers import (
    available_infrared_receivers,
    command_create_button,
    command_object,
    command_options,
    find_command_key,
    normalize_command_mapping,
    normalize_command_name,
    normalize_command_objects,
    universal_remotes_from_config_entry,
)
from .learn import (
    LEARN_DECODER_AUTO,
    LEARN_DECODER_REGISTRY,
    LEARN_DECODERS,
    LearnCapture,
    LearnResult,
    LearnSessionManager,
    LearnSessionReceiverBusyError,
    LearnSessionReceiverUnavailableError,
    LearnSessionTimeoutError,
    build_learn_result,
)
from .learn_candidates import (
    CANDIDATE_CAPTURED,
    CANDIDATE_NORMALIZED,
    LearnCandidate,
    LearnCandidateError,
    candidate_by_key,
)
from .infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
    InfraredLibraryCommandError,
    generate_pronto_from_library_command,
    generate_selected_commands_from_library_codeset,
    infrared_library_codeset_label,
    infrared_library_codeset_options,
    infrared_library_command_options,
    is_infrared_library_codeset_selected,
    validate_generated_command_payload,
)
from .send import async_send_infrared_command

COMMAND_NAME = "command_name"
COMMAND_DATA = "command_data"
COMMAND_CREATE_BUTTON = "create_button"
COMMAND_OVERWRITE_ACTION = "learn_overwrite_action"

COMMAND_SOURCE = "command_source"
COMMAND_SOURCE_RAW = "raw"
COMMAND_SOURCE_INFRARED_LIBRARY = "infrared_library"

COMMAND_LIBRARY_CODESET = "library_codeset"
COMMAND_LIBRARY_COMMAND = "library_command"
COMMAND_LIBRARY_COMMANDS = "library_commands"
COMMAND_REPEAT_COUNT = "repeat_count"
COMMAND_LEARN_CANDIDATE = "learn_candidate"
COMMAND_LEARN_DECODER = "learn_decoder"
COMMAND_LEARN_REVIEW_ACTION = "learn_review_action"
COMMAND_LEARN_FAILURE_ACTION = "learn_failure_action"

LEARN_REVIEW_ACTION_CONTINUE_SAVE = "continue_save"
LEARN_REVIEW_ACTION_TEST_CAPTURED = "test_captured"
LEARN_REVIEW_ACTION_TEST_NORMALIZED = "test_normalized"
LEARN_REVIEW_ACTION_SAVE_ANYWAY = "save_anyway"
LEARN_REVIEW_ACTION_RETRY_CAPTURE = "retry_capture"
LEARN_REVIEW_ACTION_DISCARD = "discard"

LEARN_TEST_SEND_RESULT_CAPTURED_SUCCEEDED = "captured_succeeded"
LEARN_TEST_SEND_RESULT_NORMALIZED_SUCCEEDED = "normalized_succeeded"
LEARN_TEST_SEND_RESULT_FAILED = "failed"

LEARN_OVERWRITE_ACTION_CONFIRM = "confirm"
LEARN_OVERWRITE_ACTION_BACK = "back"
LEARN_OVERWRITE_ACTION_DISCARD = "discard"

SOURCE_MANAGE_COMMANDS = "manage_commands"
SOURCE_ADD_RAW_COMMAND = "add_raw_command"
SOURCE_LEARN_COMMAND = "learn_command"
SOURCE_LEARN_CAPTURE = "learn_capture"
SOURCE_LEARN_CAPTURE_PROGRESS_DONE = "learn_capture_progress_done"
SOURCE_LEARN_SELECT_DECODER = "learn_select_decoder"
SOURCE_LEARN_REVIEW = "learn_review"
SOURCE_LEARN_CONVERSION_FAILED = "learn_conversion_failed"
SOURCE_LEARN_SELECT_CANDIDATE = "learn_select_candidate"
SOURCE_LEARN_CONFIRM_OVERWRITE = "learn_confirm_overwrite"
SOURCE_IMPORT_LIBRARY_COMMANDS = "import_library_commands"
SOURCE_IMPORT_LIBRARY_COMMAND_SELECT = "import_library_command_select"
SOURCE_EDIT_COMMAND = "edit_command"
SOURCE_REMOVE_COMMAND = "remove_command"

SOURCE_EDIT_RAW_COMMAND = "edit_raw_command"
SOURCE_EDIT_LIBRARY_CODESET = "edit_library_codeset"
SOURCE_EDIT_LIBRARY_COMMAND = "edit_library_command"

LearnCaptureTaskResult = (
    LearnCapture
    | LearnSessionReceiverUnavailableError
    | LearnSessionReceiverBusyError
    | LearnSessionTimeoutError
)


def library_command_default(
    library_command_options: list[selector.SelectOptionDict],
    command_name: str | None,
) -> str:
    """Return the best default library command for a command name."""
    option_values = {str(option["value"]) for option in library_command_options}

    if command_name is not None:
        if command_name in option_values:
            return command_name

        normalized_command_name = normalize_command_name(command_name)
        if normalized_command_name in option_values:
            return normalized_command_name

    return str(library_command_options[0]["value"])


_LEARN_REVIEW_ACTION_OPTION_LABELS: Mapping[str, str] = {
    LEARN_REVIEW_ACTION_TEST_CAPTURED: "Test captured candidate",
    LEARN_REVIEW_ACTION_TEST_NORMALIZED: "Test normalized candidate",
    LEARN_REVIEW_ACTION_CONTINUE_SAVE: "Continue to save",
    LEARN_REVIEW_ACTION_SAVE_ANYWAY: "Save anyway",
    LEARN_REVIEW_ACTION_RETRY_CAPTURE: "Retry capture",
    LEARN_REVIEW_ACTION_DISCARD: "Discard",
}
_LEARN_OVERWRITE_ACTION_OPTION_LABELS: Mapping[str, str] = {
    LEARN_OVERWRITE_ACTION_CONFIRM: "Replace existing command",
    LEARN_OVERWRITE_ACTION_BACK: "Go back",
    LEARN_OVERWRITE_ACTION_DISCARD: "Discard learned command",
}
_LEARN_FAILURE_ACTION_OPTION_LABELS: Mapping[str, str] = {
    LEARN_REVIEW_ACTION_RETRY_CAPTURE: "Retry capture",
    LEARN_REVIEW_ACTION_DISCARD: "Discard learned command",
}
_LEARN_TEST_SEND_RESULT_MESSAGES: Mapping[str, str] = {
    LEARN_TEST_SEND_RESULT_CAPTURED_SUCCEEDED: (
        "Last test send: captured candidate sent successfully."
    ),
    LEARN_TEST_SEND_RESULT_NORMALIZED_SUCCEEDED: (
        "Last test send: normalized candidate sent successfully."
    ),
    LEARN_TEST_SEND_RESULT_FAILED: "Last test send failed.",
}


def _translated_selector_option(
    value: str,
    labels: Mapping[str, str],
) -> selector.SelectOptionDict:
    """Return a translation-key based selector option with a required fallback label."""
    return selector.SelectOptionDict(value=value, label=labels[value])


def learn_decoder_options() -> list[selector.SelectOptionDict]:
    """Return selector options for learned-command decoders."""
    return [
        selector.SelectOptionDict(value=decoder.key, label=decoder.fallback_label)
        for decoder in LEARN_DECODER_REGISTRY
    ]


def learn_capture_details(capture: LearnCapture) -> str:
    """Return user-facing details for a captured signal."""
    details = [f"{capture.timing_count} timings", f"{capture.modulation} Hz"]
    if capture.modulation_assumed:
        details[-1] = f"{details[-1]} assumed"
    if capture.likely_protocol is not None:
        details.append(f"likely {capture.likely_protocol.replace('_', '-')}")

    return ", ".join(details)


def learn_test_send_result_details(test_send_result: str | None) -> str:
    """Return user-facing details for the last learned-command test send."""
    if test_send_result is None:
        return ""

    return _LEARN_TEST_SEND_RESULT_MESSAGES[test_send_result]


def learned_candidate_options(
    candidates: tuple[LearnCandidate, ...],
) -> list[selector.SelectOptionDict]:
    """Return selector options for learned command candidates."""
    return [
        selector.SelectOptionDict(
            value=candidate.key,
            label=_learned_candidate_label(candidate),
        )
        for candidate in candidates
    ]


def learned_candidate_details(candidates: tuple[LearnCandidate, ...]) -> str:
    """Return user-facing details for learned command candidates."""
    return "\n".join(
        f"- {_learned_candidate_label(candidate)}" for candidate in candidates
    )


def learn_review_action_options(
    candidates: tuple[LearnCandidate, ...] = (),
    *,
    can_test_send: bool = False,
    test_send_failed: bool = False,
) -> list[selector.SelectOptionDict]:
    """Return selector options for learned-command review actions."""
    options: list[selector.SelectOptionDict] = []

    if can_test_send:
        if candidate_by_key(candidates, CANDIDATE_CAPTURED) is not None:
            options.append(
                _translated_selector_option(
                    LEARN_REVIEW_ACTION_TEST_CAPTURED,
                    _LEARN_REVIEW_ACTION_OPTION_LABELS,
                )
            )

        if candidate_by_key(candidates, CANDIDATE_NORMALIZED) is not None:
            options.append(
                _translated_selector_option(
                    LEARN_REVIEW_ACTION_TEST_NORMALIZED,
                    _LEARN_REVIEW_ACTION_OPTION_LABELS,
                )
            )

    if test_send_failed:
        options.append(
            _translated_selector_option(
                LEARN_REVIEW_ACTION_SAVE_ANYWAY,
                _LEARN_REVIEW_ACTION_OPTION_LABELS,
            )
        )
    else:
        options.append(
            _translated_selector_option(
                LEARN_REVIEW_ACTION_CONTINUE_SAVE,
                _LEARN_REVIEW_ACTION_OPTION_LABELS,
            )
        )

    options.extend(
        [
            _translated_selector_option(
                LEARN_REVIEW_ACTION_RETRY_CAPTURE,
                _LEARN_REVIEW_ACTION_OPTION_LABELS,
            ),
            _translated_selector_option(
                LEARN_REVIEW_ACTION_DISCARD,
                _LEARN_REVIEW_ACTION_OPTION_LABELS,
            ),
        ]
    )
    return options


def learn_overwrite_action_options() -> list[selector.SelectOptionDict]:
    """Return selector options for learned-command overwrite confirmation."""
    return [
        _translated_selector_option(
            LEARN_OVERWRITE_ACTION_CONFIRM,
            _LEARN_OVERWRITE_ACTION_OPTION_LABELS,
        ),
        _translated_selector_option(
            LEARN_OVERWRITE_ACTION_BACK,
            _LEARN_OVERWRITE_ACTION_OPTION_LABELS,
        ),
        _translated_selector_option(
            LEARN_OVERWRITE_ACTION_DISCARD,
            _LEARN_OVERWRITE_ACTION_OPTION_LABELS,
        ),
    ]


def learn_failure_action_options() -> list[selector.SelectOptionDict]:
    """Return selector options for learned-command conversion failures."""
    return [
        _translated_selector_option(
            LEARN_REVIEW_ACTION_RETRY_CAPTURE,
            _LEARN_FAILURE_ACTION_OPTION_LABELS,
        ),
        _translated_selector_option(
            LEARN_REVIEW_ACTION_DISCARD,
            _LEARN_FAILURE_ACTION_OPTION_LABELS,
        ),
    ]


def learn_capture_receiver_label(
    receiver_label: str | None,
    receiver_id: str | None,
) -> str:
    """Return a readable receiver label for the capture step."""
    if receiver_label is None:
        return receiver_id or ""

    if receiver_id is None:
        return receiver_label

    entity_suffix = f" ({receiver_id})"
    if receiver_label.endswith(entity_suffix):
        return receiver_label.removesuffix(entity_suffix)

    return receiver_label


def _learned_candidate_label(candidate: LearnCandidate) -> str:
    """Return a readable learned-candidate label."""
    label = candidate.label_key.replace("_", " ").title()
    if candidate.recommended:
        label = f"{label} (recommended)"

    if summary := _learned_candidate_metadata_summary(candidate):
        return f"{label} — {summary}"

    return label


def _learned_candidate_metadata_summary(candidate: LearnCandidate) -> str:
    """Return a concise user-facing summary of learned candidate metadata."""
    metadata = candidate.metadata
    protocol = metadata.get("protocol")
    if protocol is not None:
        return _learned_protocol_summary(str(protocol), metadata)

    details: list[str] = []
    timing_count = metadata.get("timing_count")
    if isinstance(timing_count, int):
        details.append(f"{timing_count} timings")

    modulation = metadata.get("modulation")
    if isinstance(modulation, int):
        modulation_detail = f"{modulation} Hz"
        if metadata.get("modulation_assumed") is True:
            modulation_detail = f"{modulation_detail} assumed"
        details.append(modulation_detail)

    return ", ".join(details)


def _learned_protocol_summary(protocol: str, metadata: Mapping[str, Any]) -> str:
    """Return a concise summary of decoded learned protocol metadata."""
    protocol_label = protocol.replace("_", "-").upper()
    details = [protocol_label]

    if address := metadata.get("address"):
        details.append(f"address {address}")

    primary_label = "function" if protocol == "nec1_f16" else "command"
    if primary := metadata.get("primary"):
        details.append(f"{primary_label} {primary}")

    if secondary := metadata.get("secondary"):
        details.append(f"subfunction {secondary}")

    return ", ".join(details)


class UniversalRemoteOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Universal Remote."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._remote = self._configured_remote()
        self._selected_command_name: str | None = None
        self._selected_library_codeset: str | None = None
        self._learn_receiver_id: str | None = None
        self._learn_receiver_label: str | None = None
        self._learn_capture_task: asyncio.Task[LearnCaptureTaskResult] | None = None
        self._learn_capture: LearnCapture | None = None
        self._learn_result: LearnResult | None = None
        self._learn_test_send_failed = False
        self._learn_test_send_result: str | None = None
        self._learn_pending_command_name: str | None = None
        self._learn_pending_candidate_key: str | None = None
        self._learn_pending_create_button = False

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage the options menu."""
        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        return self.async_show_menu(
            step_id="init",
            menu_options=[SOURCE_MANAGE_COMMANDS],
        )

    async def async_step_manage_commands(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage command options."""
        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        menu_options = [SOURCE_ADD_RAW_COMMAND]
        if self._remote.get(CONF_INFRARED_RECEIVER_ID):
            menu_options.append(SOURCE_LEARN_COMMAND)

        device_type = str(
            self._remote.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC)
        )
        if device_type != DEVICE_TYPE_GENERIC:
            menu_options.append(SOURCE_IMPORT_LIBRARY_COMMANDS)
        if self._commands:
            menu_options.extend([SOURCE_EDIT_COMMAND, SOURCE_REMOVE_COMMAND])

        return self.async_show_menu(
            step_id=SOURCE_MANAGE_COMMANDS,
            menu_options=menu_options,
        )

    async def async_step_add_raw_command(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Add a raw named command for the remote."""
        errors: dict[str, str] = {}

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        if user_input is not None:
            command_name = normalize_command_name(str(user_input[COMMAND_NAME]))
            command_data = str(user_input[COMMAND_DATA]).strip()

            if not command_name:
                errors[COMMAND_NAME] = "command_name_required"

            if (
                not errors
                and find_command_key(self._commands, command_name) is not None
            ):
                errors[COMMAND_NAME] = "command_name_exists"

            if not command_data:
                errors[COMMAND_DATA] = "command_data_required"

            if not errors:
                try:
                    validate_remote_command_payload(command_data)
                except CommandParseError:
                    errors[COMMAND_DATA] = "invalid_command"

            if not errors:
                commands = self._command_objects
                commands[command_name] = command_object(
                    command_data,
                    create_button=bool(user_input.get(COMMAND_CREATE_BUTTON, False)),
                )
                remote[CONF_REMOTE_COMMANDS] = commands
                return self._create_options_entry()

        command_name_default = (
            str(user_input.get(COMMAND_NAME, "")) if user_input else ""
        )
        command_data_default = (
            str(user_input.get(COMMAND_DATA, "")) if user_input else ""
        )

        return self.async_show_form(
            step_id=SOURCE_ADD_RAW_COMMAND,
            data_schema=vol.Schema(
                {
                    vol.Required(COMMAND_NAME, default=command_name_default): str,
                    vol.Required(
                        COMMAND_DATA,
                        default=command_data_default,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiline=True,
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                    vol.Optional(
                        COMMAND_CREATE_BUTTON,
                        default=bool(user_input.get(COMMAND_CREATE_BUTTON, False))
                        if user_input
                        else False,
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_learn_command(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Select an infrared receiver before learning a command."""
        errors: dict[str, str] = {}

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        if not remote.get(CONF_INFRARED_RECEIVER_ID):
            return self.async_abort(reason="no_configured_infrared_receiver")

        receiver_options = available_infrared_receivers(self.hass)
        if not receiver_options:
            return self.async_abort(reason="no_available_infrared_receivers")

        if user_input is not None:
            receiver_id = str(user_input[CONF_INFRARED_RECEIVER_ID])

            if receiver_id not in receiver_options:
                errors[CONF_INFRARED_RECEIVER_ID] = "infrared_receiver_unavailable"

            if not errors:
                self._learn_receiver_id = receiver_id
                self._learn_receiver_label = str(
                    receiver_options[receiver_id].get("label", receiver_id)
                )
                await self._async_cancel_learn_capture_task()
                self._learn_capture = None
                self._learn_result = None
                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return await self.async_step_learn_capture()

        current_receiver_id = str(remote.get(CONF_INFRARED_RECEIVER_ID, ""))
        receiver_default = (
            str(user_input.get(CONF_INFRARED_RECEIVER_ID, current_receiver_id))
            if user_input
            else current_receiver_id
        )
        if receiver_default not in receiver_options:
            receiver_default = next(iter(receiver_options))

        return self.async_show_form(
            step_id=SOURCE_LEARN_COMMAND,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INFRARED_RECEIVER_ID,
                        default=receiver_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(receiver_options.values()),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_learn_capture(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Capture a command from the selected infrared receiver."""
        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_receiver_id is None:
            return await self.async_step_learn_command()

        if user_input is None and self._learn_capture_task is None:
            return self._show_learn_capture_form({})

        if self._learn_capture_task is None:
            self._learn_capture_task = self.hass.async_create_task(
                self._async_learn_capture_once(self._learn_receiver_id),
                "Learn Universal Remote infrared command",
            )
            return self.async_show_progress(
                step_id=SOURCE_LEARN_CAPTURE,
                progress_action=SOURCE_LEARN_CAPTURE,
                progress_task=self._learn_capture_task,
                description_placeholders=self._learn_capture_placeholders,
            )

        if not self._learn_capture_task.done():
            return self.async_show_progress(
                step_id=SOURCE_LEARN_CAPTURE,
                progress_action=SOURCE_LEARN_CAPTURE,
                progress_task=self._learn_capture_task,
                description_placeholders=self._learn_capture_placeholders,
            )

        return self.async_show_progress_done(
            next_step_id=SOURCE_LEARN_CAPTURE_PROGRESS_DONE
        )

    async def async_step_learn_capture_progress_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a completed learned-command capture progress task."""
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_receiver_id is None:
            return await self.async_step_learn_command()

        if self._learn_capture_task is None:
            return await self.async_step_learn_capture()

        try:
            capture_result = await self._learn_capture_task
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        finally:
            self._learn_capture_task = None

        if isinstance(capture_result, LearnSessionReceiverUnavailableError):
            errors["base"] = "infrared_receiver_unavailable"
        elif isinstance(capture_result, LearnSessionReceiverBusyError):
            errors["base"] = "learn_receiver_busy"
        elif isinstance(capture_result, LearnSessionTimeoutError):
            errors["base"] = "learn_timeout"
        else:
            self._learn_capture = capture_result
            self._learn_result = None
            self._clear_learn_pending_save()
            self._clear_learn_test_send_state()

        if errors:
            return self._show_learn_capture_form(errors)

        return await self.async_step_learn_select_decoder()

    async def async_step_learn_select_decoder(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Select how to decode a learned IR capture."""
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_capture is None:
            return await self.async_step_learn_command()

        if user_input is not None:
            decoder = str(user_input[COMMAND_LEARN_DECODER])

            if decoder not in LEARN_DECODERS:
                errors[COMMAND_LEARN_DECODER] = "invalid_learn_decoder"

            if not errors:
                try:
                    self._learn_result = build_learn_result(
                        self._learn_capture,
                        decoder=decoder,
                    )
                except LearnCandidateError:
                    self._learn_result = None
                    self._clear_learn_pending_save()
                    self._clear_learn_test_send_state()
                    return await self.async_step_learn_conversion_failed(
                        errors={"base": "learn_pronto_conversion_failed"}
                    )

                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return await self.async_step_learn_review()

        return self.async_show_form(
            step_id=SOURCE_LEARN_SELECT_DECODER,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_LEARN_DECODER,
                        default=LEARN_DECODER_AUTO,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=learn_decoder_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="learn_decoder",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "capture_details": learn_capture_details(self._learn_capture),
            },
        )

    async def async_step_learn_conversion_failed(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle a learned-command candidate conversion failure."""
        form_errors = dict(errors or {})

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_capture is None:
            return await self.async_step_learn_command()

        action_options = learn_failure_action_options()

        if user_input is not None:
            action = str(user_input[COMMAND_LEARN_FAILURE_ACTION])
            valid_actions = {str(option["value"]) for option in action_options}

            if action not in valid_actions:
                form_errors[COMMAND_LEARN_FAILURE_ACTION] = (
                    "invalid_learn_failure_action"
                )

            elif action == LEARN_REVIEW_ACTION_RETRY_CAPTURE:
                await self._async_cancel_learn_capture_task()
                self._learn_capture = None
                self._learn_result = None
                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return await self.async_step_learn_capture()

            elif action == LEARN_REVIEW_ACTION_DISCARD:
                await self._async_cancel_learn_capture_task()
                self._learn_capture = None
                self._learn_result = None
                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return self.async_create_entry(
                    title="",
                    data=dict(self._config_entry.options),
                )

        return self.async_show_form(
            step_id=SOURCE_LEARN_CONVERSION_FAILED,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_LEARN_FAILURE_ACTION,
                        default=LEARN_REVIEW_ACTION_RETRY_CAPTURE,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=action_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="learn_failure_action",
                        )
                    ),
                }
            ),
            errors=form_errors,
            description_placeholders={
                "capture_details": learn_capture_details(self._learn_capture),
            },
        )


    async def async_step_learn_review(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Review a learned command before choosing whether to save it."""
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_result is None:
            if self._learn_capture is not None:
                return await self.async_step_learn_select_decoder()
            return await self.async_step_learn_command()

        candidates = self._learn_result.candidates
        if not candidates:
            return self.async_abort(reason="learn_failed")

        can_test_send = self._learn_test_send_emitter_id is not None
        action_options = learn_review_action_options(
            candidates,
            can_test_send=can_test_send,
            test_send_failed=self._learn_test_send_failed,
        )

        if user_input is not None:
            action = str(user_input[COMMAND_LEARN_REVIEW_ACTION])
            valid_actions = {str(option["value"]) for option in action_options}

            if action not in valid_actions:
                errors[COMMAND_LEARN_REVIEW_ACTION] = "invalid_learn_review_action"

            elif action in (
                LEARN_REVIEW_ACTION_CONTINUE_SAVE,
                LEARN_REVIEW_ACTION_SAVE_ANYWAY,
            ):
                self._clear_learn_test_send_state()
                return await self.async_step_learn_select_candidate()

            elif action in (
                LEARN_REVIEW_ACTION_TEST_CAPTURED,
                LEARN_REVIEW_ACTION_TEST_NORMALIZED,
            ):
                if await self._async_test_learned_candidate(action, candidates):
                    self._learn_test_send_failed = False
                    self._learn_test_send_result = (
                        LEARN_TEST_SEND_RESULT_CAPTURED_SUCCEEDED
                        if action == LEARN_REVIEW_ACTION_TEST_CAPTURED
                        else LEARN_TEST_SEND_RESULT_NORMALIZED_SUCCEEDED
                    )
                else:
                    self._learn_test_send_failed = True
                    self._learn_test_send_result = LEARN_TEST_SEND_RESULT_FAILED
                    errors["base"] = "learn_test_send_failed"

            elif action == LEARN_REVIEW_ACTION_RETRY_CAPTURE:
                await self._async_cancel_learn_capture_task()
                self._learn_capture = None
                self._learn_result = None
                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return await self.async_step_learn_capture()

            elif action == LEARN_REVIEW_ACTION_DISCARD:
                await self._async_cancel_learn_capture_task()
                self._learn_capture = None
                self._learn_result = None
                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return self.async_create_entry(
                    title="",
                    data=dict(self._config_entry.options),
                )

            action_options = learn_review_action_options(
                candidates,
                can_test_send=can_test_send,
                test_send_failed=self._learn_test_send_failed,
            )

        default_action = str(action_options[0]["value"])

        return self.async_show_form(
            step_id=SOURCE_LEARN_REVIEW,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_LEARN_REVIEW_ACTION,
                        default=default_action,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=action_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="learn_review_action",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "candidate_details": learned_candidate_details(candidates),
                "test_send_result": learn_test_send_result_details(
                    self._learn_test_send_result
                ),
            },
        )

    async def async_step_learn_select_candidate(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Name and save one learned command candidate."""
        errors: dict[str, str] = {}

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_result is None:
            if self._learn_capture is not None:
                return await self.async_step_learn_select_decoder()
            return await self.async_step_learn_command()

        candidates = self._learn_result.candidates
        if not candidates:
            return self.async_abort(reason="learn_failed")

        if user_input is not None:
            command_name = normalize_command_name(str(user_input[COMMAND_NAME]))
            selected_candidate = candidate_by_key(
                candidates,
                str(user_input[COMMAND_LEARN_CANDIDATE]),
            )
            create_button = bool(user_input.get(COMMAND_CREATE_BUTTON, False))
            self._clear_learn_pending_save()

            if not command_name:
                errors[COMMAND_NAME] = "command_name_required"

            if selected_candidate is None:
                errors[COMMAND_LEARN_CANDIDATE] = "invalid_learn_candidate"

            if (
                not errors
                and find_command_key(self._commands, command_name) is not None
                and selected_candidate is not None
            ):
                self._learn_pending_command_name = command_name
                self._learn_pending_candidate_key = selected_candidate.key
                self._learn_pending_create_button = create_button
                return await self.async_step_learn_confirm_overwrite()

            if not errors and selected_candidate is not None:
                self._save_learned_command(
                    remote,
                    command_name,
                    selected_candidate,
                    create_button=create_button,
                )
                return self._create_options_entry()

        recommended_candidate = next(
            (candidate for candidate in candidates if candidate.recommended),
            candidates[0],
        )
        command_name_default = (
            str(user_input.get(COMMAND_NAME, "")) if user_input else ""
        )

        return self.async_show_form(
            step_id=SOURCE_LEARN_SELECT_CANDIDATE,
            data_schema=vol.Schema(
                {
                    vol.Required(COMMAND_NAME, default=command_name_default): str,
                    vol.Required(
                        COMMAND_LEARN_CANDIDATE,
                        default=recommended_candidate.key,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=learned_candidate_options(candidates),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="learn_candidate",
                        )
                    ),
                    vol.Optional(
                        COMMAND_CREATE_BUTTON,
                        default=bool(user_input.get(COMMAND_CREATE_BUTTON, False))
                        if user_input
                        else False,
                    ): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "candidate_details": learned_candidate_details(candidates),
            },
        )

    async def async_step_learn_confirm_overwrite(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Confirm replacing an existing command with a learned command."""
        errors: dict[str, str] = {}

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_result is None:
            if self._learn_capture is not None:
                return await self.async_step_learn_select_decoder()
            return await self.async_step_learn_command()

        command_name = self._learn_pending_command_name
        candidate_key = self._learn_pending_candidate_key
        if command_name is None or candidate_key is None:
            return await self.async_step_learn_select_candidate()

        selected_candidate = candidate_by_key(
            self._learn_result.candidates, candidate_key
        )
        if selected_candidate is None:
            self._clear_learn_pending_save()
            return await self.async_step_learn_select_candidate()

        if user_input is not None:
            action = str(user_input[COMMAND_OVERWRITE_ACTION])
            valid_actions = {
                str(option["value"]) for option in learn_overwrite_action_options()
            }

            if action not in valid_actions:
                errors[COMMAND_OVERWRITE_ACTION] = "invalid_learn_overwrite_action"

            elif action == LEARN_OVERWRITE_ACTION_CONFIRM:
                self._save_learned_command(
                    remote,
                    command_name,
                    selected_candidate,
                    create_button=self._learn_pending_create_button,
                )
                self._clear_learn_pending_save()
                return self._create_options_entry()

            elif action == LEARN_OVERWRITE_ACTION_BACK:
                self._clear_learn_pending_save()
                return await self.async_step_learn_select_candidate()

            elif action == LEARN_OVERWRITE_ACTION_DISCARD:
                await self._async_cancel_learn_capture_task()
                self._learn_capture = None
                self._learn_result = None
                self._clear_learn_pending_save()
                self._clear_learn_test_send_state()
                return self.async_create_entry(
                    title="",
                    data=dict(self._config_entry.options),
                )

        return self.async_show_form(
            step_id=SOURCE_LEARN_CONFIRM_OVERWRITE,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_OVERWRITE_ACTION,
                        default=LEARN_OVERWRITE_ACTION_CONFIRM,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=learn_overwrite_action_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="learn_overwrite_action",
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "command_name": command_name,
                "candidate_details": learned_candidate_details(
                    (selected_candidate,),
                ),
            },
        )

    async def async_step_import_library_commands(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Select an infrared library codeset for importing commands."""
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        current_codeset = str(
            self._remote.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET)
        )
        device_type = str(
            self._remote.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC)
        )
        if device_type == DEVICE_TYPE_GENERIC:
            return self.async_abort(reason="invalid_library_codeset")

        codeset_options = infrared_library_codeset_options(device_type=device_type)

        if not codeset_options:
            return self.async_abort(reason="invalid_library_codeset")

        if user_input is not None:
            codeset_id = str(user_input[COMMAND_LIBRARY_CODESET])

            if codeset_id not in [str(option["value"]) for option in codeset_options]:
                errors[COMMAND_LIBRARY_CODESET] = "invalid_library_codeset"

            if not errors:
                self._selected_library_codeset = codeset_id
                return await self.async_step_import_library_command_select()

        codeset_fallback = (
            current_codeset
            if is_infrared_library_codeset_selected(current_codeset)
            else str(codeset_options[0]["value"])
        )
        codeset_default = (
            str(user_input.get(COMMAND_LIBRARY_CODESET, codeset_fallback))
            if user_input
            else codeset_fallback
        )

        return self.async_show_form(
            step_id=SOURCE_IMPORT_LIBRARY_COMMANDS,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_LIBRARY_CODESET,
                        default=codeset_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=codeset_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_import_library_command_select(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Import commands generated from an infrared library codeset."""
        errors: dict[str, str] = {}
        codeset_id = self._selected_library_codeset

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        if codeset_id is None:
            return await self.async_step_import_library_commands()

        try:
            library_command_options = await self.hass.async_add_executor_job(
                infrared_library_command_options,
                codeset_id,
            )
        except InfraredLibraryCommandError:
            return self.async_abort(reason="invalid_library_codeset")

        if not library_command_options:
            return self.async_abort(reason="invalid_library_codeset")

        library_commands_default: list[str] = []
        existing_library_commands: list[str] = []

        if user_input is not None:
            selected_commands = user_input.get(COMMAND_LIBRARY_COMMANDS, [])
            if isinstance(selected_commands, str):
                library_commands = [selected_commands]
            else:
                library_commands = [str(command) for command in selected_commands]
            library_commands_default = library_commands
            repeat_count = int(user_input.get(COMMAND_REPEAT_COUNT, 0))

            if not library_commands:
                errors[COMMAND_LIBRARY_COMMANDS] = "library_commands_required"

            if repeat_count < 0:
                errors[COMMAND_REPEAT_COUNT] = "invalid_repeat_count"

            commands = self._commands
            existing_library_commands = [
                library_command
                for library_command in library_commands
                if find_command_key(commands, library_command) is not None
            ]
            if not errors and existing_library_commands:
                errors[COMMAND_LIBRARY_COMMANDS] = "library_commands_exist"

            generated_commands: dict[str, str] = {}
            if not errors:
                try:
                    generated_commands = await self.hass.async_add_executor_job(
                        generate_selected_commands_from_library_codeset,
                        codeset_id,
                        library_commands,
                        repeat_count,
                    )
                    for command_name, command_data in generated_commands.items():
                        validate_generated_command_payload(command_name, command_data)
                except InfraredLibraryCommandError:
                    errors[COMMAND_LIBRARY_COMMANDS] = "invalid_library_command"

            if not errors:
                command_objects = self._command_objects
                for command_name, command_data in generated_commands.items():
                    command_objects[command_name] = command_object(
                        command_data,
                        create_button=bool(
                            user_input.get(COMMAND_CREATE_BUTTON, False)
                        ),
                    )
                remote[CONF_REMOTE_COMMANDS] = command_objects
                return self._create_options_entry()

        repeat_count_default = (
            int(user_input.get(COMMAND_REPEAT_COUNT, 0)) if user_input else 0
        )

        return self.async_show_form(
            step_id=SOURCE_IMPORT_LIBRARY_COMMAND_SELECT,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        COMMAND_LIBRARY_COMMANDS,
                        default=library_commands_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=library_command_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        COMMAND_REPEAT_COUNT,
                        default=repeat_count_default,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=10,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        COMMAND_CREATE_BUTTON,
                        default=bool(user_input.get(COMMAND_CREATE_BUTTON, False))
                        if user_input
                        else False,
                    ): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "codeset": infrared_library_codeset_label(codeset_id),
                "existing_commands": ", ".join(existing_library_commands),
            },
        )

    async def async_step_select_command_for_edit(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Select a named command before editing it."""
        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        commands = self._commands
        if not commands:
            return self.async_abort(reason="no_remote_commands")

        if user_input is not None:
            self._selected_command_name = str(user_input[COMMAND_NAME])
            return await self.async_step_edit_command()

        return self.async_show_form(
            step_id="select_command_for_edit",
            data_schema=vol.Schema(
                {
                    vol.Required(COMMAND_NAME): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=command_options(commands),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

    async def async_step_edit_command(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Select how to edit a named command."""
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        commands = self._commands
        if not commands:
            return self.async_abort(reason="no_remote_commands")

        selected_command_name = self._selected_command_name
        if selected_command_name not in commands:
            if user_input is None:
                return await self.async_step_select_command_for_edit()
            return self.async_abort(reason="command_not_found")

        if user_input is not None:
            command_source = str(user_input[COMMAND_SOURCE])

            if command_source == COMMAND_SOURCE_RAW:
                return await self.async_step_edit_raw_command()

            if command_source == COMMAND_SOURCE_INFRARED_LIBRARY:
                return await self.async_step_edit_library_codeset()

            errors[COMMAND_SOURCE] = "invalid_command_source"

        return self.async_show_form(
            step_id=SOURCE_EDIT_COMMAND,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_SOURCE,
                        default=COMMAND_SOURCE_RAW,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                COMMAND_SOURCE_RAW,
                                COMMAND_SOURCE_INFRARED_LIBRARY,
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=COMMAND_SOURCE,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_raw_command(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Edit a command using raw command data."""
        errors: dict[str, str] = {}
        selected_command_name = self._selected_command_name

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        commands = self._commands
        command_objects = self._command_objects
        if selected_command_name not in commands:
            return self.async_abort(reason="command_not_found")

        if user_input is not None:
            command_name = normalize_command_name(str(user_input[COMMAND_NAME]))
            command_data = str(user_input[COMMAND_DATA]).strip()

            if not command_name:
                errors[COMMAND_NAME] = "command_name_required"

            existing_command_name = find_command_key(commands, command_name)
            if (
                not errors
                and existing_command_name is not None
                and existing_command_name != selected_command_name
            ):
                errors[COMMAND_NAME] = "command_name_exists"

            if not command_data:
                errors[COMMAND_DATA] = "command_data_required"

            if not errors:
                try:
                    validate_remote_command_payload(command_data)
                except CommandParseError:
                    errors[COMMAND_DATA] = "invalid_command"

            if not errors:
                command_objects.pop(selected_command_name, None)
                command_objects[command_name] = command_object(
                    command_data,
                    create_button=bool(user_input.get(COMMAND_CREATE_BUTTON, False)),
                )
                remote[CONF_REMOTE_COMMANDS] = command_objects
                return self._create_options_entry()

        command_name_default = (
            str(user_input.get(COMMAND_NAME, selected_command_name))
            if user_input
            else str(selected_command_name)
        )
        command_data_default = (
            str(user_input.get(COMMAND_DATA, commands[selected_command_name]))
            if user_input
            else str(commands[selected_command_name])
        )
        create_button_default = command_create_button(
            command_objects.get(str(selected_command_name), {})
        )

        return self.async_show_form(
            step_id=SOURCE_EDIT_RAW_COMMAND,
            data_schema=vol.Schema(
                {
                    vol.Required(COMMAND_NAME, default=command_name_default): str,
                    vol.Required(
                        COMMAND_DATA,
                        default=command_data_default,
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            multiline=True,
                            type=selector.TextSelectorType.TEXT,
                        )
                    ),
                    vol.Optional(
                        COMMAND_CREATE_BUTTON,
                        default=bool(
                            user_input.get(COMMAND_CREATE_BUTTON, create_button_default)
                        )
                        if user_input
                        else create_button_default,
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_edit_library_codeset(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Select an infrared library codeset for editing a command."""
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._selected_command_name is None:
            return await self.async_step_select_command_for_edit()

        current_codeset = str(
            self._remote.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET)
        )
        device_type = str(
            self._remote.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC)
        )
        if device_type == DEVICE_TYPE_GENERIC:
            return self.async_abort(reason="invalid_library_codeset")

        codeset_options = infrared_library_codeset_options(device_type=device_type)

        if not codeset_options:
            return self.async_abort(reason="invalid_library_codeset")

        if user_input is not None:
            codeset_id = str(user_input[COMMAND_LIBRARY_CODESET])

            if codeset_id not in [str(option["value"]) for option in codeset_options]:
                errors[COMMAND_LIBRARY_CODESET] = "invalid_library_codeset"

            if not errors:
                self._selected_library_codeset = codeset_id
                return await self.async_step_edit_library_command()

        codeset_fallback = (
            current_codeset
            if is_infrared_library_codeset_selected(current_codeset)
            else str(codeset_options[0]["value"])
        )
        codeset_default = (
            str(user_input.get(COMMAND_LIBRARY_CODESET, codeset_fallback))
            if user_input
            else codeset_fallback
        )

        return self.async_show_form(
            step_id=SOURCE_EDIT_LIBRARY_CODESET,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_LIBRARY_CODESET,
                        default=codeset_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=codeset_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_edit_library_command(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Edit a command using an infrared library command."""
        errors: dict[str, str] = {}
        selected_command_name = self._selected_command_name
        codeset_id = self._selected_library_codeset

        if (remote := self._remote) is None:
            return self.async_abort(reason="no_universal_remotes")

        commands = self._commands
        command_objects = self._command_objects
        if selected_command_name not in commands:
            return self.async_abort(reason="command_not_found")

        if codeset_id is None:
            return await self.async_step_edit_library_codeset()

        try:
            library_command_options = await self.hass.async_add_executor_job(
                infrared_library_command_options,
                codeset_id,
            )
        except InfraredLibraryCommandError:
            return self.async_abort(reason="invalid_library_codeset")

        if not library_command_options:
            return self.async_abort(reason="invalid_library_codeset")

        if user_input is not None:
            library_command = str(user_input[COMMAND_LIBRARY_COMMAND])
            repeat_count = int(user_input.get(COMMAND_REPEAT_COUNT, 0))

            if repeat_count < 0:
                errors[COMMAND_REPEAT_COUNT] = "invalid_repeat_count"

            existing_command_name = find_command_key(commands, library_command)
            if (
                not errors
                and existing_command_name is not None
                and existing_command_name != selected_command_name
            ):
                errors[COMMAND_LIBRARY_COMMAND] = "command_name_exists"

            if not errors:
                try:
                    command_data = await self.hass.async_add_executor_job(
                        generate_pronto_from_library_command,
                        codeset_id,
                        library_command,
                        repeat_count,
                    )
                    validate_generated_command_payload(library_command, command_data)
                except InfraredLibraryCommandError:
                    errors[COMMAND_LIBRARY_COMMAND] = "invalid_library_command"

            if not errors:
                command_objects.pop(selected_command_name, None)
                command_objects[library_command] = command_object(
                    command_data,
                    create_button=bool(user_input.get(COMMAND_CREATE_BUTTON, False)),
                )
                remote[CONF_REMOTE_COMMANDS] = command_objects
                return self._create_options_entry()

        default_library_command = library_command_default(
            library_command_options,
            selected_command_name,
        )
        command_default = (
            str(user_input.get(COMMAND_LIBRARY_COMMAND, default_library_command))
            if user_input
            else default_library_command
        )
        repeat_count_default = (
            int(user_input.get(COMMAND_REPEAT_COUNT, 0)) if user_input else 0
        )
        create_button_default = command_create_button(
            command_objects.get(str(selected_command_name), {})
        )

        return self.async_show_form(
            step_id=SOURCE_EDIT_LIBRARY_COMMAND,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        COMMAND_LIBRARY_COMMAND,
                        default=command_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=library_command_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        COMMAND_REPEAT_COUNT,
                        default=repeat_count_default,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=10,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Optional(
                        COMMAND_CREATE_BUTTON,
                        default=bool(
                            user_input.get(COMMAND_CREATE_BUTTON, create_button_default)
                        )
                        if user_input
                        else create_button_default,
                    ): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "codeset": infrared_library_codeset_label(codeset_id),
            },
        )

    async def async_step_remove_command(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Remove named commands from the remote."""
        remote = self._remote

        if remote is None:
            return self.async_abort(reason="no_universal_remotes")

        commands = self._commands
        if not commands:
            return self.async_abort(reason="no_remote_commands")

        selected_commands_default: list[str] = []

        if user_input is not None:
            selected_commands = user_input.get(COMMAND_NAME, [])
            if isinstance(selected_commands, str):
                command_names = [selected_commands]
            else:
                command_names = [str(command) for command in selected_commands]
            selected_commands_default = command_names

            if not command_names:
                return self._show_remove_command_form(
                    commands,
                    selected_commands_default,
                    {COMMAND_NAME: "command_name_required"},
                )

            if any(command_name not in commands for command_name in command_names):
                return self.async_abort(reason="command_not_found")

            command_objects = self._command_objects
            for command_name in command_names:
                command_objects.pop(command_name, None)

            if command_objects:
                remote[CONF_REMOTE_COMMANDS] = command_objects
            else:
                remote.pop(CONF_REMOTE_COMMANDS, None)
            return self._create_options_entry()

        return self._show_remove_command_form(commands, selected_commands_default, {})

    def _show_remove_command_form(
        self,
        commands: dict[str, str],
        selected_commands_default: list[str],
        errors: dict[str, str],
    ) -> config_entries.ConfigFlowResult:
        """Show the remove command form."""
        return self.async_show_form(
            step_id=SOURCE_REMOVE_COMMAND,
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        COMMAND_NAME,
                        default=selected_commands_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=command_options(commands),
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    def _show_learn_capture_form(
        self,
        errors: dict[str, str],
    ) -> config_entries.ConfigFlowResult:
        """Show the learn capture form."""
        return self.async_show_form(
            step_id=SOURCE_LEARN_CAPTURE,
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders=self._learn_capture_placeholders,
        )

    async def _async_learn_capture_once(
        self, receiver_id: str
    ) -> LearnCaptureTaskResult:
        """Capture one learned IR command after yielding to show progress first."""
        await asyncio.sleep(0)
        try:
            return await LearnSessionManager(self.hass).async_capture_once(receiver_id)
        except (
            LearnSessionReceiverUnavailableError,
            LearnSessionReceiverBusyError,
            LearnSessionTimeoutError,
        ) as err:
            return err

    async def _async_cancel_learn_capture_task(self) -> None:
        """Cancel any pending learned-command capture task."""
        task = self._learn_capture_task
        if task is None:
            return

        self._learn_capture_task = None
        if task.done():
            if not task.cancelled():
                task.exception()
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @property
    def _learn_capture_placeholders(self) -> dict[str, str]:
        """Return placeholders for the learn capture form/progress step."""
        return {
            "receiver": learn_capture_receiver_label(
                self._learn_receiver_label,
                self._learn_receiver_id,
            )
        }

    def _save_learned_command(
        self,
        remote: dict[str, Any],
        command_name: str,
        selected_candidate: LearnCandidate,
        *,
        create_button: bool,
    ) -> None:
        """Save a learned command candidate to the current remote."""
        command_objects = self._command_objects
        command_objects[command_name] = command_object(
            selected_candidate.payload,
            create_button=create_button,
        )
        remote[CONF_REMOTE_COMMANDS] = command_objects

    def _clear_learn_pending_save(self) -> None:
        """Clear pending learned-command save confirmation state."""
        self._learn_pending_command_name = None
        self._learn_pending_candidate_key = None
        self._learn_pending_create_button = False

    def _clear_learn_test_send_state(self) -> None:
        """Clear the learned-command test-send result state."""
        self._learn_test_send_failed = False
        self._learn_test_send_result = None

    async def _async_test_learned_candidate(
        self,
        action: str,
        candidates: tuple[LearnCandidate, ...],
    ) -> bool:
        """Test-send a learned candidate through the configured emitter."""
        emitter_id = self._learn_test_send_emitter_id
        if emitter_id is None:
            return False

        candidate_key = (
            CANDIDATE_CAPTURED
            if action == LEARN_REVIEW_ACTION_TEST_CAPTURED
            else CANDIDATE_NORMALIZED
        )
        candidate = candidate_by_key(candidates, candidate_key)
        if candidate is None:
            return False

        try:
            await async_send_infrared_command(
                self.hass,
                emitter_id,
                candidate.payload,
                check_available=True,
            )
        except (asyncio.CancelledError, KeyboardInterrupt):
            raise
        except HomeAssistantError:
            return False

        return True

    @property
    def _learn_test_send_emitter_id(self) -> str | None:
        """Return the emitter id when learned-candidate test send is available."""
        if self._remote is None:
            return None

        emitter_id = str(self._remote.get(CONF_INFRARED_EMITTER_ID, "")).strip()
        if not emitter_id:
            return None

        state = self.hass.states.get(emitter_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            return None

        return emitter_id

    @callback
    def _create_options_entry(self) -> config_entries.ConfigFlowResult:
        """Create the options entry preserving unrelated options."""
        remote = self._remote
        if remote is None:
            return self.async_abort(reason="no_universal_remotes")

        options = dict(self._config_entry.options)

        options.pop(CONF_REMOTE_NAME, None)
        options.pop(CONF_REMOTE_CODESET, None)
        options.pop(CONF_REMOTE_DEVICE_TYPE, None)

        if commands := remote.get(CONF_REMOTE_COMMANDS):
            options[CONF_REMOTE_COMMANDS] = commands
        else:
            options.pop(CONF_REMOTE_COMMANDS, None)

        return self.async_create_entry(title="", data=options)

    @property
    def _commands(self) -> dict[str, str]:
        """Return configured command payloads."""
        if self._remote is None:
            return {}
        return normalize_command_mapping(self._remote.get(CONF_REMOTE_COMMANDS, {}))

    @property
    def _command_objects(self) -> dict[str, dict[str, Any]]:
        """Return configured command objects."""
        if self._remote is None:
            return {}
        return normalize_command_objects(self._remote.get(CONF_REMOTE_COMMANDS, {}))

    def _configured_remote(self) -> dict[str, Any] | None:
        """Return the configured remote for this options flow."""
        remotes = universal_remotes_from_config_entry(self._config_entry)
        return remotes[0] if remotes else None
