"""Button entities for Universal Remote commands."""

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .command_ui import command_icon, command_label
from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from .helpers import (
    command_create_button,
    command_payload,
    normalize_command_name,
    normalize_command_objects,
    universal_remotes_from_config_entry,
)
from .send import async_send_infrared_command

PARALLEL_UPDATES = 1


def button_unique_id(entry_id: str, remote_id: str, command_name: str) -> str:
    """Return the unique id for a configured command button."""
    return (
        f"{entry_id}_button_{remote_id}_{normalize_command_name(command_name).lower()}"
    )


@callback
def cleanup_stale_button_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    expected_unique_ids: set[str],
) -> None:
    """Remove stale command button entity registry entries."""
    entity_registry = er.async_get(hass)
    unique_id_prefix = f"{entry.entry_id}_button_"

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "button":
            continue

        unique_id = entity_entry.unique_id
        if (
            isinstance(unique_id, str)
            and unique_id.startswith(unique_id_prefix)
            and unique_id not in expected_unique_ids
        ):
            entity_registry.async_remove(entity_entry.entity_id)


@dataclass(frozen=True, kw_only=True)
class UniversalRemoteButtonEntityDescription(ButtonEntityDescription):
    """Description of a Universal Remote command button."""

    command_name: str
    command_data: str


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Universal Remote buttons from a config entry."""
    entities: list[UniversalRemoteButton] = []
    expected_unique_ids: set[str] = set()

    for remote in universal_remotes_from_config_entry(entry):
        remote_id = str(remote[CONF_REMOTE_ID])
        remote_name = str(remote[CONF_REMOTE_NAME])
        infrared_emitter_id = str(remote[CONF_INFRARED_EMITTER_ID])
        commands = normalize_command_objects(remote.get(CONF_REMOTE_COMMANDS, {}))

        for command_name, command in commands.items():
            if not command_create_button(command):
                continue

            command_data = command_payload(command)
            if command_data is None:
                continue

            unique_id = button_unique_id(entry.entry_id, remote_id, command_name)
            expected_unique_ids.add(unique_id)
            entities.append(
                UniversalRemoteButton(
                    remote_id=remote_id,
                    remote_name=remote_name,
                    infrared_emitter_id=infrared_emitter_id,
                    unique_id=unique_id,
                    description=UniversalRemoteButtonEntityDescription(
                        key=normalize_command_name(command_name).lower(),
                        name=command_label(command_name),
                        icon=command_icon(command_name),
                        command_name=command_name,
                        command_data=command_data,
                    ),
                )
            )

    cleanup_stale_button_entities(hass, entry, expected_unique_ids)
    async_add_entities(entities)


class UniversalRemoteButton(ButtonEntity):
    """A button which sends a configured Universal Remote command."""

    entity_description: UniversalRemoteButtonEntityDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        *,
        remote_id: str,
        remote_name: str,
        infrared_emitter_id: str,
        unique_id: str,
        description: UniversalRemoteButtonEntityDescription,
    ) -> None:
        """Initialize a Universal Remote button."""
        self.entity_description = description
        self._infrared_emitter_id = infrared_emitter_id
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, remote_id)},
            name=remote_name,
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""

        @callback
        def _handle_infrared_state_change(event: Any) -> None:
            """Handle linked infrared entity state changes."""
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._infrared_emitter_id],
                _handle_infrared_state_change,
            )
        )

    @property
    def available(self) -> bool:
        """Return whether the backing infrared emitter is available."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return True

        state = hass.states.get(self._infrared_emitter_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    async def async_press(self) -> None:
        """Send the configured command."""
        await async_send_infrared_command(
            self.hass,
            self._infrared_emitter_id,
            self.entity_description.command_data,
        )
