"""Select entities for Universal Remote tuner state."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_REMOTE_ID, CONF_REMOTE_NAME, DOMAIN
from .helpers import (
    linked_entity_is_available,
    universal_remote_device_info,
    universal_remotes_from_config_entry,
)
from .runtime import UniversalRemoteData, UniversalRemoteRuntime

PARALLEL_UPDATES = 0


def select_unique_id(entry_id: str, remote_id: str) -> str:
    """Return the unique id for a configured tuner select entity."""
    return f"{entry_id}_select_{remote_id}_tuner"


@callback
def cleanup_stale_select_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    expected_unique_ids: set[str],
) -> None:
    """Remove stale tuner select entity registry entries."""
    entity_registry = er.async_get(hass)
    unique_id_prefix = f"{entry.entry_id}_select_"

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != SELECT_DOMAIN:
            continue

        unique_id = entity_entry.unique_id
        if (
            isinstance(unique_id, str)
            and unique_id.startswith(unique_id_prefix)
            and unique_id not in expected_unique_ids
        ):
            entity_registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Universal Remote tuner select entities from a config entry."""
    entities: list[UniversalRemoteTunerSelect] = []
    expected_unique_ids: set[str] = set()

    runtime_data = getattr(entry, "runtime_data", None)
    runtime = (
        runtime_data.runtime if isinstance(runtime_data, UniversalRemoteData) else None
    )

    if runtime is not None and runtime.available_tuners:
        for remote in universal_remotes_from_config_entry(entry):
            remote_id = remote.get(CONF_REMOTE_ID)
            remote_name = remote.get(CONF_REMOTE_NAME)
            if (
                not isinstance(remote_id, str)
                or not remote_id
                or not isinstance(remote_name, str)
                or not remote_name
            ):
                continue

            unique_id = select_unique_id(entry.entry_id, remote_id)
            expected_unique_ids.add(unique_id)
            entities.append(
                UniversalRemoteTunerSelect(
                    runtime=runtime,
                    remote_id=remote_id,
                    remote_name=remote_name,
                    unique_id=unique_id,
                )
            )

    cleanup_stale_select_entities(hass, entry, expected_unique_ids)
    async_add_entities(entities)


class UniversalRemoteTunerSelect(SelectEntity):
    """Select entity exposing assumed tuner state."""

    _attr_has_entity_name = True
    _attr_name = "Tuner"
    _attr_should_poll = False

    def __init__(
        self,
        *,
        runtime: UniversalRemoteRuntime,
        remote_id: str,
        remote_name: str,
        unique_id: str,
    ) -> None:
        """Initialize the tuner select entity."""
        self._runtime = runtime
        self._attr_unique_id = unique_id
        self._attr_device_info = universal_remote_device_info(remote_id, remote_name)

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""

        @callback
        def _handle_tuner_state_change() -> None:
            """Handle runtime tuner state changes."""
            self.async_write_ha_state()

        @callback
        def _handle_infrared_state_change(event: Any) -> None:
            """Handle linked infrared emitter state changes."""
            self.async_write_ha_state()

        self.async_on_remove(
            self._runtime.async_add_tuner_listener(_handle_tuner_state_change)
        )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._runtime.infrared_emitter_id],
                _handle_infrared_state_change,
            )
        )

    @property
    def options(self) -> list[str]:
        """Return selectable tuner options."""
        return list(self._runtime.available_tuners)

    @property
    def current_option(self) -> str | None:
        """Return the current selected tuner."""
        selected = self._runtime.selected_tuner
        return selected if selected in self._runtime.available_tuners else None

    @property
    def available(self) -> bool:
        """Return whether the backing infrared emitter is available."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return True

        return linked_entity_is_available(hass, self._runtime.infrared_emitter_id)

    async def async_select_option(self, option: str) -> None:
        """Select a tuner option."""
        if option not in self._runtime.available_tuners:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="select_tuner_unavailable",
                translation_placeholders={"option": option},
            )

        await self._runtime.async_send_command_name(option)
        self.async_write_ha_state()
