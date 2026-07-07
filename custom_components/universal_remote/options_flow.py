"""Options flow for Universal Remote."""

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .command import CommandParseError, validate_remote_command_payload
from .const import (
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
    LEARN_DECODER_NEC,
    LEARN_DECODER_NEC1_F16,
    LEARN_DECODER_NONE,
    LEARN_DECODERS,
    LearnCapture,
    LearnResult,
    LearnSessionManager,
    LearnSessionReceiverBusyError,
    LearnSessionReceiverUnavailableError,
    LearnSessionTimeoutError,
    build_learn_result,
)
from .learn_candidates import LearnCandidate, candidate_by_key
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

COMMAND_NAME = "command_name"
COMMAND_DATA = "command_data"
COMMAND_CREATE_BUTTON = "create_button"

COMMAND_SOURCE = "command_source"
COMMAND_SOURCE_RAW = "raw"
COMMAND_SOURCE_INFRARED_LIBRARY = "infrared_library"

COMMAND_LIBRARY_CODESET = "library_codeset"
COMMAND_LIBRARY_COMMAND = "library_command"
COMMAND_LIBRARY_COMMANDS = "library_commands"
COMMAND_REPEAT_COUNT = "repeat_count"
COMMAND_LEARN_CANDIDATE = "learn_candidate"
COMMAND_LEARN_DECODER = "learn_decoder"

SOURCE_MANAGE_COMMANDS = "manage_commands"
SOURCE_ADD_RAW_COMMAND = "add_raw_command"
SOURCE_LEARN_COMMAND = "learn_command"
SOURCE_LEARN_CAPTURE = "learn_capture"
SOURCE_LEARN_SELECT_DECODER = "learn_select_decoder"
SOURCE_LEARN_SELECT_CANDIDATE = "learn_select_candidate"
SOURCE_IMPORT_LIBRARY_COMMANDS = "import_library_commands"
SOURCE_IMPORT_LIBRARY_COMMAND_SELECT = "import_library_command_select"
SOURCE_EDIT_COMMAND = "edit_command"
SOURCE_REMOVE_COMMAND = "remove_command"

SOURCE_EDIT_RAW_COMMAND = "edit_raw_command"
SOURCE_EDIT_LIBRARY_CODESET = "edit_library_codeset"
SOURCE_EDIT_LIBRARY_COMMAND = "edit_library_command"


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


def learn_decoder_options() -> list[selector.SelectOptionDict]:
    """Return selector options for learned-command decoders."""
    return [
        selector.SelectOptionDict(value=LEARN_DECODER_AUTO, label="Auto (recommended)"),
        selector.SelectOptionDict(value=LEARN_DECODER_NONE, label="None / captured only"),
        selector.SelectOptionDict(value=LEARN_DECODER_NEC, label="NEC"),
        selector.SelectOptionDict(value=LEARN_DECODER_NEC1_F16, label="NEC1-F16"),
    ]


def learn_capture_details(capture: LearnCapture) -> str:
    """Return user-facing details for a captured signal."""
    details = [f"{capture.timing_count} timings", f"{capture.modulation} Hz"]
    if capture.modulation_assumed:
        details[-1] = f"{details[-1]} assumed"
    if capture.likely_protocol is not None:
        details.append(f"likely {capture.likely_protocol.replace('_', '-')}")

    return ", ".join(details)


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
        self._learn_capture: LearnCapture | None = None
        self._learn_result: LearnResult | None = None

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
                self._learn_capture = None
                self._learn_result = None
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
        errors: dict[str, str] = {}

        if self._remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if self._learn_receiver_id is None:
            return await self.async_step_learn_command()

        if user_input is not None:
            try:
                self._learn_capture = await LearnSessionManager(
                    self.hass
                ).async_capture_once(self._learn_receiver_id)
                self._learn_result = None
            except LearnSessionReceiverUnavailableError:
                errors["base"] = "infrared_receiver_unavailable"
            except LearnSessionReceiverBusyError:
                errors["base"] = "learn_receiver_busy"
            except LearnSessionTimeoutError:
                errors["base"] = "learn_timeout"

            if not errors:
                return await self.async_step_learn_select_decoder()

        return self.async_show_form(
            step_id=SOURCE_LEARN_CAPTURE,
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={
                "receiver": self._learn_receiver_label or self._learn_receiver_id,
            },
        )

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
                self._learn_result = build_learn_result(
                    self._learn_capture,
                    decoder=decoder,
                )
                return await self.async_step_learn_select_candidate()

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
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "capture_details": learn_capture_details(self._learn_capture),
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

            if not command_name:
                errors[COMMAND_NAME] = "command_name_required"

            if (
                not errors
                and find_command_key(self._commands, command_name) is not None
            ):
                errors[COMMAND_NAME] = "command_name_exists"

            if selected_candidate is None:
                errors[COMMAND_LEARN_CANDIDATE] = "invalid_learn_candidate"

            if not errors and selected_candidate is not None:
                command_objects = self._command_objects
                command_objects[command_name] = command_object(
                    selected_candidate.payload,
                    create_button=bool(user_input.get(COMMAND_CREATE_BUTTON, False)),
                )
                remote[CONF_REMOTE_COMMANDS] = command_objects
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
