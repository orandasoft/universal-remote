"""Config flow for the Universal Remote integration."""

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DOMAIN,
)
from .helpers import (
    available_infrared_emitters,
    command_object,
    infrared_emitter_field,
    infrared_emitter_field_with_current,
    infrared_emitter_selector,
    unique_remote_id,
    universal_remote_from_config_entry_data,
)
from .infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
    InfraredLibraryCommandError,
    generate_commands_from_library_codeset,
    generate_selected_commands_from_library_codeset,
    infrared_library_codeset_device_type,
    infrared_library_codeset_label,
    infrared_library_codeset_options,
    infrared_library_command_options,
    infrared_library_device_type_label,
    infrared_library_device_type_options,
    is_infrared_library_codeset_selected,
    validate_generated_command_payload,
    validate_infrared_library_codeset,
    validate_infrared_library_device_type,
)
from .options_flow import UniversalRemoteOptionsFlow

CONF_IMPORT_COMMANDS = "import_commands"
CONF_CREATE_BUTTON = "create_button"
CONF_LIBRARY_COMMANDS = "library_commands"
CONF_REPEAT_COUNT = "repeat_count"

IMPORT_COMMANDS_NO = "no"
IMPORT_COMMANDS_ALL = "all"
IMPORT_COMMANDS_SELECT = "select"


class UniversalRemoteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Universal Remote."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._name: str | None = None
        self._infrared_emitter_id: str | None = None
        self._device_type: str = DEVICE_TYPE_GENERIC
        self._codeset_id: str = NO_INFRARED_LIBRARY_CODESET
        self._create_button = False
        self._reconfigure_remote: dict[str, Any] | None = None

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> UniversalRemoteOptionsFlow:
        """Create the options flow."""
        return UniversalRemoteOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle manual setup."""
        errors: dict[str, str] = {}
        infrared_emitters = available_infrared_emitters(self.hass)

        if not infrared_emitters:
            return self.async_abort(reason="no_available_infrared_emitters")

        if user_input is not None:
            name = str(user_input[CONF_REMOTE_NAME]).strip()
            infrared_emitter_id = str(user_input[CONF_INFRARED_EMITTER_ID]).strip()
            device_type = str(
                user_input.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC)
            )

            if not name:
                errors[CONF_REMOTE_NAME] = "remote_name_required"

            if infrared_emitter_id not in infrared_emitters:
                errors[CONF_INFRARED_EMITTER_ID] = "infrared_emitter_unavailable"

            if not validate_infrared_library_device_type(device_type):
                errors[CONF_REMOTE_DEVICE_TYPE] = "invalid_device_type"

            remote_id = unique_remote_id(name, [])

            if not errors:
                await self.async_set_unique_id(remote_id)
                self._abort_if_unique_id_configured()

                self._name = name
                self._infrared_emitter_id = infrared_emitter_id
                self._device_type = device_type

                if device_type == DEVICE_TYPE_GENERIC:
                    return self._create_entry({})

                return await self.async_step_select_codeset()

        remote_name_default = (
            str(user_input.get(CONF_REMOTE_NAME, "")) if user_input else ""
        )
        infrared_emitter_default = (
            str(user_input.get(CONF_INFRARED_EMITTER_ID, "")) if user_input else ""
        )
        device_type_default = (
            str(user_input.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC))
            if user_input
            else DEVICE_TYPE_GENERIC
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REMOTE_NAME,
                        default=remote_name_default,
                    ): str,
                    infrared_emitter_field(
                        infrared_emitter_default,
                        infrared_emitters,
                    ): infrared_emitter_selector(infrared_emitters),
                    vol.Required(
                        CONF_REMOTE_DEVICE_TYPE,
                        default=device_type_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=infrared_library_device_type_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_codeset(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select an infrared library codeset for the selected device type."""
        errors: dict[str, str] = {}
        device_type = self._device_type

        if self._name is None or self._infrared_emitter_id is None:
            return await self.async_step_user()

        if device_type == DEVICE_TYPE_GENERIC:
            return self._create_entry({})

        if user_input is not None:
            codeset_id = str(
                user_input.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET)
            )
            if not validate_infrared_library_codeset(
                codeset_id,
                device_type=device_type,
            ):
                errors[CONF_REMOTE_CODESET] = "invalid_library_codeset"

            if not errors:
                self._codeset_id = codeset_id
                if not is_infrared_library_codeset_selected(codeset_id):
                    return self._create_entry({})

                return await self.async_step_import_commands()

        codeset_default = (
            str(user_input.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET))
            if user_input
            else NO_INFRARED_LIBRARY_CODESET
        )

        return self.async_show_form(
            step_id="select_codeset",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_REMOTE_CODESET,
                        default=codeset_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=infrared_library_codeset_options(
                                device_type=device_type,
                                include_none=True,
                            ),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "device_type": infrared_library_device_type_label(device_type),
            },
        )

    async def async_step_import_commands(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Ask whether commands should be imported from the selected codeset."""
        errors: dict[str, str] = {}
        codeset_id = self._codeset_id

        if self._name is None or self._infrared_emitter_id is None:
            return await self.async_step_user()

        if not is_infrared_library_codeset_selected(codeset_id):
            return self._create_entry({})

        if user_input is not None:
            import_mode = str(user_input[CONF_IMPORT_COMMANDS])
            create_button = bool(user_input.get(CONF_CREATE_BUTTON, False))

            if import_mode == IMPORT_COMMANDS_NO:
                return self._create_entry({})

            if import_mode == IMPORT_COMMANDS_ALL:
                try:
                    commands = await self.hass.async_add_executor_job(
                        generate_commands_from_library_codeset,
                        codeset_id,
                    )
                    _validate_generated_commands(commands)
                except InfraredLibraryCommandError:
                    errors[CONF_IMPORT_COMMANDS] = "invalid_library_command"
                else:
                    return self._create_entry(
                        _command_objects(commands, create_button=create_button)
                    )

            elif import_mode == IMPORT_COMMANDS_SELECT:
                self._create_button = create_button
                return await self.async_step_select_library_commands()

            else:
                errors[CONF_IMPORT_COMMANDS] = "invalid_import_mode"

        import_mode_default = (
            str(user_input.get(CONF_IMPORT_COMMANDS, IMPORT_COMMANDS_ALL))
            if user_input
            else IMPORT_COMMANDS_ALL
        )

        return self.async_show_form(
            step_id="import_commands",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IMPORT_COMMANDS,
                        default=import_mode_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                IMPORT_COMMANDS_NO,
                                IMPORT_COMMANDS_ALL,
                                IMPORT_COMMANDS_SELECT,
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key=CONF_IMPORT_COMMANDS,
                        )
                    ),
                    vol.Optional(
                        CONF_CREATE_BUTTON,
                        default=bool(
                            user_input.get(CONF_CREATE_BUTTON, self._create_button)
                        )
                        if user_input
                        else self._create_button,
                    ): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "codeset": infrared_library_codeset_label(codeset_id),
            },
        )

    async def async_step_select_library_commands(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Select commands to import from the selected infrared library codeset."""
        errors: dict[str, str] = {}
        codeset_id = self._codeset_id

        if self._name is None or self._infrared_emitter_id is None:
            return await self.async_step_user()

        if not is_infrared_library_codeset_selected(codeset_id):
            return self._create_entry({})

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

        if user_input is not None:
            selected_commands = user_input.get(CONF_LIBRARY_COMMANDS, [])
            if isinstance(selected_commands, str):
                library_commands = [selected_commands]
            else:
                library_commands = [str(command) for command in selected_commands]
            library_commands_default = library_commands
            repeat_count = int(user_input.get(CONF_REPEAT_COUNT, 0))
            create_button = bool(
                user_input.get(CONF_CREATE_BUTTON, self._create_button)
            )

            if not library_commands:
                errors[CONF_LIBRARY_COMMANDS] = "library_commands_required"

            if repeat_count < 0:
                errors[CONF_REPEAT_COUNT] = "invalid_repeat_count"

            if not errors:
                try:
                    commands = await self.hass.async_add_executor_job(
                        generate_selected_commands_from_library_codeset,
                        codeset_id,
                        library_commands,
                        repeat_count,
                    )
                    _validate_generated_commands(commands)
                except InfraredLibraryCommandError:
                    errors[CONF_LIBRARY_COMMANDS] = "invalid_library_command"
                else:
                    return self._create_entry(
                        _command_objects(commands, create_button=create_button)
                    )

        repeat_count_default = (
            int(user_input.get(CONF_REPEAT_COUNT, 0)) if user_input else 0
        )

        return self.async_show_form(
            step_id="select_library_commands",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LIBRARY_COMMANDS,
                        default=library_commands_default,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=library_command_options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        CONF_REPEAT_COUNT,
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
                        CONF_CREATE_BUTTON,
                        default=bool(
                            user_input.get(CONF_CREATE_BUTTON, self._create_button)
                        )
                        if user_input
                        else self._create_button,
                    ): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "codeset": infrared_library_codeset_label(codeset_id),
            },
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the universal remote."""
        entry = self._get_reconfigure_entry()
        remote = universal_remote_from_config_entry_data({**entry.data, **entry.options})
        infrared_emitters = available_infrared_emitters(self.hass)

        if remote is None:
            return self.async_abort(reason="no_universal_remotes")

        if not infrared_emitters:
            return self.async_abort(reason="no_available_infrared_emitters")

        errors: dict[str, str] = {}
        current_name = str(remote[CONF_REMOTE_NAME])
        current_emitter_id = str(remote[CONF_INFRARED_EMITTER_ID])
        current_device_type = str(
            remote.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC)
        )

        if user_input is not None:
            name = str(user_input[CONF_REMOTE_NAME]).strip()
            infrared_emitter_id = str(user_input[CONF_INFRARED_EMITTER_ID]).strip()
            device_type = str(
                user_input.get(CONF_REMOTE_DEVICE_TYPE, current_device_type)
            )

            if not name:
                errors[CONF_REMOTE_NAME] = "remote_name_required"

            if (
                infrared_emitter_id not in infrared_emitters
                and infrared_emitter_id != current_emitter_id
            ):
                errors[CONF_INFRARED_EMITTER_ID] = "infrared_emitter_unavailable"

            if not validate_infrared_library_device_type(device_type):
                errors[CONF_REMOTE_DEVICE_TYPE] = "invalid_device_type"

            if not errors:
                remote[CONF_REMOTE_NAME] = name
                remote[CONF_INFRARED_EMITTER_ID] = infrared_emitter_id
                remote[CONF_REMOTE_DEVICE_TYPE] = device_type
                self._device_type = device_type
                self._codeset_id = str(
                    remote.get(
                        CONF_REMOTE_CODESET,
                        NO_INFRARED_LIBRARY_CODESET,
                    )
                )

                if device_type == DEVICE_TYPE_GENERIC:
                    remote.pop(CONF_REMOTE_CODESET, None)
                    return self._update_reconfigure_entry(remote)

                self._reconfigure_remote = remote
                return await self.async_step_reconfigure_codeset()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REMOTE_NAME,
                        default=str(user_input.get(CONF_REMOTE_NAME, current_name))
                        if user_input
                        else current_name,
                    ): str,
                    infrared_emitter_field_with_current(
                        str(user_input.get(CONF_INFRARED_EMITTER_ID, current_emitter_id))
                        if user_input
                        else current_emitter_id,
                        infrared_emitters,
                    ): infrared_emitter_selector(
                        infrared_emitters,
                        current_emitter_id=current_emitter_id,
                    ),
                    vol.Required(
                        CONF_REMOTE_DEVICE_TYPE,
                        default=str(
                            user_input.get(
                                CONF_REMOTE_DEVICE_TYPE,
                                current_device_type,
                            )
                        )
                        if user_input
                        else current_device_type,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=infrared_library_device_type_options(),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure_codeset(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle reconfiguration codeset selection."""
        remote = getattr(self, "_reconfigure_remote", None)
        if remote is None:
            entry = self._get_reconfigure_entry()
            remote = universal_remote_from_config_entry_data(
                {**entry.data, **entry.options}
            )

        if remote is None:
            return self.async_abort(reason="no_universal_remotes")

        device_type = str(remote.get(CONF_REMOTE_DEVICE_TYPE, DEVICE_TYPE_GENERIC))
        errors: dict[str, str] = {}

        if device_type == DEVICE_TYPE_GENERIC:
            remote.pop(CONF_REMOTE_CODESET, None)
            return self._update_reconfigure_entry(remote)

        current_codeset = str(remote.get(CONF_REMOTE_CODESET, self._codeset_id))
        if user_input is not None:
            codeset_id = str(
                user_input.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET)
            )
            if not validate_infrared_library_codeset(
                codeset_id,
                device_type=device_type,
            ):
                errors[CONF_REMOTE_CODESET] = "invalid_library_codeset"
            if not errors:
                if is_infrared_library_codeset_selected(codeset_id):
                    remote[CONF_REMOTE_CODESET] = codeset_id
                else:
                    remote.pop(CONF_REMOTE_CODESET, None)
                return self._update_reconfigure_entry(remote)

        return self.async_show_form(
            step_id="reconfigure_codeset",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_REMOTE_CODESET,
                        default=str(
                            user_input.get(CONF_REMOTE_CODESET, current_codeset)
                        )
                        if user_input
                        else current_codeset,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=infrared_library_codeset_options(
                                device_type=device_type,
                                include_none=True,
                            ),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "device_type": infrared_library_device_type_label(device_type),
            },
        )

    def _update_reconfigure_entry(self, remote: dict[str, Any]) -> ConfigFlowResult:
        """Update the reconfigured entry."""
        entry = self._get_reconfigure_entry()
        data = dict(entry.data)
        data[CONF_REMOTE_NAME] = remote[CONF_REMOTE_NAME]
        data[CONF_INFRARED_EMITTER_ID] = remote[CONF_INFRARED_EMITTER_ID]
        data[CONF_REMOTE_DEVICE_TYPE] = remote.get(
            CONF_REMOTE_DEVICE_TYPE,
            DEVICE_TYPE_GENERIC,
        )
        if is_infrared_library_codeset_selected(
            codeset_id := str(
                remote.get(CONF_REMOTE_CODESET, NO_INFRARED_LIBRARY_CODESET)
            )
        ):
            data[CONF_REMOTE_CODESET] = codeset_id
        else:
            data.pop(CONF_REMOTE_CODESET, None)

        return self.async_update_and_abort(
            entry,
            title=str(remote[CONF_REMOTE_NAME]),
            data=data,
        )

    def _create_entry(self, commands: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry from pending user input."""
        if self._name is None or self._infrared_emitter_id is None:
            return self.async_abort(reason="no_universal_remotes")

        codeset_device_type = infrared_library_codeset_device_type(self._codeset_id)
        if (
            is_infrared_library_codeset_selected(self._codeset_id)
            and codeset_device_type
        ):
            self._device_type = codeset_device_type

        remote_id = self.unique_id or unique_remote_id(self._name, [])
        data: dict[str, Any] = {
            CONF_REMOTE_ID: remote_id,
            CONF_REMOTE_NAME: self._name,
            CONF_INFRARED_EMITTER_ID: self._infrared_emitter_id,
            CONF_REMOTE_DEVICE_TYPE: self._device_type,
        }
        if is_infrared_library_codeset_selected(self._codeset_id):
            data[CONF_REMOTE_CODESET] = self._codeset_id

        options: dict[str, Any] = {}
        if commands:
            options[CONF_REMOTE_COMMANDS] = commands

        return self.async_create_entry(title=self._name, data=data, options=options)


def _validate_generated_commands(commands: dict[str, str]) -> None:
    """Validate generated infrared command payloads."""
    for command_name, command_data in commands.items():
        validate_generated_command_payload(command_name, command_data)


def _command_objects(
    commands: dict[str, str],
    *,
    create_button: bool,
) -> dict[str, dict[str, Any]]:
    """Return stored command objects from generated command data."""
    return {
        command_name: command_object(command_data, create_button=create_button)
        for command_name, command_data in commands.items()
    }
