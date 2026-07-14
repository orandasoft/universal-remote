"""Repairs support for the Universal Remote integration."""

from typing import Any

import voluptuous as vol

from homeassistant.components import repairs
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
    ISSUE_LINKED_INFRARED_EMITTER_MISSING,
    ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
)
from .helpers import (
    available_infrared_emitters,
    available_infrared_receivers,
    infrared_emitter_field,
    infrared_emitter_selector,
    infrared_receiver_field,
    infrared_receiver_selector,
    universal_remote_from_config_entry_data,
)

CONF_DISABLE_EMITTER = "disable_emitter"
CONF_DISABLE_RECEIVER = "disable_receiver"


def _linked_infrared_emitter_issue_id(remote_id: str) -> str:
    """Return the repair issue id for a missing linked infrared emitter."""
    return f"{ISSUE_LINKED_INFRARED_EMITTER_MISSING}_{remote_id}"


def _linked_infrared_receiver_issue_id(remote_id: str) -> str:
    """Return the repair issue id for a missing linked infrared receiver."""
    return f"{ISSUE_LINKED_INFRARED_RECEIVER_MISSING}_{remote_id}"


def async_create_linked_infrared_emitter_missing_issue(
    hass: HomeAssistant,
    *,
    remote_id: str,
    remote_name: str,
    infrared_emitter_id: str,
) -> None:
    """Create a repair issue for a missing linked infrared emitter."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _linked_infrared_emitter_issue_id(remote_id),
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LINKED_INFRARED_EMITTER_MISSING,
        translation_placeholders={
            "remote_name": remote_name,
            "infrared_emitter_id": infrared_emitter_id,
        },
    )


def async_create_linked_infrared_receiver_missing_issue(
    hass: HomeAssistant,
    *,
    remote_id: str,
    remote_name: str,
    infrared_receiver_id: str,
) -> None:
    """Create a repair issue for a missing linked infrared receiver."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        _linked_infrared_receiver_issue_id(remote_id),
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
        translation_placeholders={
            "remote_name": remote_name,
            "infrared_receiver_id": infrared_receiver_id,
        },
    )


def async_delete_linked_infrared_emitter_missing_issue(
    hass: HomeAssistant,
    *,
    remote_id: str,
) -> None:
    """Delete the repair issue for a restored linked infrared emitter."""
    ir.async_delete_issue(
        hass,
        DOMAIN,
        _linked_infrared_emitter_issue_id(remote_id),
    )


def async_delete_linked_infrared_receiver_missing_issue(
    hass: HomeAssistant,
    *,
    remote_id: str,
) -> None:
    """Delete the repair issue for a restored linked infrared receiver."""
    ir.async_delete_issue(
        hass,
        DOMAIN,
        _linked_infrared_receiver_issue_id(remote_id),
    )


def async_delete_stale_linked_infrared_emitter_missing_issues(
    hass: HomeAssistant,
    *,
    configured_remote_ids: set[str],
) -> None:
    """Delete missing-infrared-emitter repair issues for removed universal remotes."""
    _async_delete_stale_linked_infrared_missing_issues(
        hass,
        configured_remote_ids=configured_remote_ids,
        issue_type=ISSUE_LINKED_INFRARED_EMITTER_MISSING,
    )


def async_delete_stale_linked_infrared_receiver_missing_issues(
    hass: HomeAssistant,
    *,
    configured_remote_ids: set[str],
) -> None:
    """Delete missing-infrared-receiver repair issues for removed universal remotes."""
    _async_delete_stale_linked_infrared_missing_issues(
        hass,
        configured_remote_ids=configured_remote_ids,
        issue_type=ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
    )


def _async_delete_stale_linked_infrared_missing_issues(
    hass: HomeAssistant,
    *,
    configured_remote_ids: set[str],
    issue_type: str,
) -> None:
    """Delete stale missing-infrared repair issues for removed universal remotes."""
    issue_registry = ir.async_get(hass)
    issue_id_prefix = f"{issue_type}_"

    for issue in list(issue_registry.issues.values()):
        if issue.domain != DOMAIN or not issue.issue_id.startswith(issue_id_prefix):
            continue

        remote_id = issue.issue_id.removeprefix(issue_id_prefix)
        if remote_id not in configured_remote_ids:
            ir.async_delete_issue(hass, DOMAIN, issue.issue_id)


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    _data: dict[str, Any] | None,
) -> repairs.RepairsFlow:
    """Create a repair flow for a Universal Remote repair issue."""
    return LinkedInfraredRepairFlow(hass, issue_id)


class LinkedInfraredRepairFlow(repairs.RepairsFlow):
    """Repair flow for a missing linked infrared entity."""

    def __init__(self, hass: HomeAssistant, issue_id: str) -> None:
        """Initialize the repair flow."""
        self._hass = hass
        self._issue_id = issue_id

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Handle the missing linked-infrared repair flow."""
        if self._issue_id.startswith(f"{ISSUE_LINKED_INFRARED_EMITTER_MISSING}_"):
            return await self._async_step_emitter(user_input)

        if self._issue_id.startswith(f"{ISSUE_LINKED_INFRARED_RECEIVER_MISSING}_"):
            return await self._async_step_receiver(user_input)

        return self.async_abort(reason="not_fixable")

    async def _async_step_emitter(
        self,
        user_input: dict[str, Any] | None,
    ) -> FlowResult:
        """Handle a missing linked infrared emitter."""
        entry, remote = _config_entry_and_remote_for_issue(
            self._hass,
            self._issue_id,
            issue_type=ISSUE_LINKED_INFRARED_EMITTER_MISSING,
        )
        if entry is None or remote is None:
            return self.async_abort(reason="remote_not_found")

        available_emitters = available_infrared_emitters(self._hass)
        current_receiver_id = str(remote.get(CONF_INFRARED_RECEIVER_ID, "")).strip()
        errors: dict[str, str] = {}

        if user_input is not None:
            disable_emitter = bool(user_input.get(CONF_DISABLE_EMITTER, False))
            emitter_id = str(user_input.get(CONF_INFRARED_EMITTER_ID, "")).strip()

            if disable_emitter:
                if not current_receiver_id:
                    errors["base"] = "infrared_target_required"
                else:
                    return await self._async_update_infrared_entity(
                        entry,
                        remote_id=str(remote[CONF_REMOTE_ID]),
                        conf_key=CONF_INFRARED_EMITTER_ID,
                        entity_id=None,
                    )
            elif not emitter_id:
                errors[CONF_INFRARED_EMITTER_ID] = "infrared_emitter_required"
            elif emitter_id not in available_emitters:
                errors[CONF_INFRARED_EMITTER_ID] = "infrared_emitter_unavailable"

            if not errors:
                return await self._async_update_infrared_entity(
                    entry,
                    remote_id=str(remote[CONF_REMOTE_ID]),
                    conf_key=CONF_INFRARED_EMITTER_ID,
                    entity_id=emitter_id,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_missing_emitter_repair_schema(available_emitters),
            errors=errors,
            description_placeholders={
                "remote_name": str(remote[CONF_REMOTE_NAME]),
                "infrared_emitter_id": str(remote.get(CONF_INFRARED_EMITTER_ID, "")),
            },
        )

    async def _async_step_receiver(
        self,
        user_input: dict[str, Any] | None,
    ) -> FlowResult:
        """Handle a missing linked infrared receiver."""
        entry, remote = _config_entry_and_remote_for_issue(
            self._hass,
            self._issue_id,
            issue_type=ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
        )
        if entry is None or remote is None:
            return self.async_abort(reason="remote_not_found")

        available_receivers = available_infrared_receivers(self._hass)
        current_emitter_id = str(remote.get(CONF_INFRARED_EMITTER_ID, "")).strip()
        errors: dict[str, str] = {}

        if user_input is not None:
            disable_receiver = bool(user_input.get(CONF_DISABLE_RECEIVER, False))
            receiver_id = str(user_input.get(CONF_INFRARED_RECEIVER_ID, "")).strip()

            if disable_receiver:
                if not current_emitter_id:
                    errors["base"] = "infrared_target_required"
                else:
                    return await self._async_update_infrared_entity(
                        entry,
                        remote_id=str(remote[CONF_REMOTE_ID]),
                        conf_key=CONF_INFRARED_RECEIVER_ID,
                        entity_id=None,
                    )
            elif not receiver_id:
                errors[CONF_INFRARED_RECEIVER_ID] = "infrared_receiver_required"
            elif receiver_id not in available_receivers:
                errors[CONF_INFRARED_RECEIVER_ID] = "infrared_receiver_unavailable"

            if not errors:
                return await self._async_update_infrared_entity(
                    entry,
                    remote_id=str(remote[CONF_REMOTE_ID]),
                    conf_key=CONF_INFRARED_RECEIVER_ID,
                    entity_id=receiver_id,
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_missing_receiver_repair_schema(available_receivers),
            errors=errors,
            description_placeholders={
                "remote_name": str(remote[CONF_REMOTE_NAME]),
                "infrared_receiver_id": str(remote.get(CONF_INFRARED_RECEIVER_ID, "")),
            },
        )

    async def _async_update_infrared_entity(
        self,
        entry: ConfigEntry,
        *,
        remote_id: str,
        conf_key: str,
        entity_id: str | None,
    ) -> FlowResult:
        """Update a linked infrared entity and finish the repair."""
        data = dict(entry.data)
        options = dict(entry.options)

        if entity_id is None:
            data.pop(conf_key, None)
            options.pop(conf_key, None)
        else:
            data[conf_key] = entity_id
            options.pop(conf_key, None)

        self._hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
        )
        if conf_key == CONF_INFRARED_EMITTER_ID:
            async_delete_linked_infrared_emitter_missing_issue(
                self._hass,
                remote_id=remote_id,
            )
        else:
            async_delete_linked_infrared_receiver_missing_issue(
                self._hass,
                remote_id=remote_id,
            )

        return self.async_create_entry(title="", data={})


def _missing_emitter_repair_schema(
    available_emitters: dict[str, Any],
) -> vol.Schema:
    """Return the missing emitter repair form schema."""
    fields: dict[vol.Marker, Any] = {}

    if available_emitters:
        default_emitter_id = next(iter(available_emitters))
        fields[infrared_emitter_field(default_emitter_id, available_emitters)] = (
            infrared_emitter_selector(available_emitters)
        )

    fields[vol.Optional(CONF_DISABLE_EMITTER, default=not available_emitters)] = bool

    return vol.Schema(fields)


def _missing_receiver_repair_schema(
    available_receivers: dict[str, Any],
) -> vol.Schema:
    """Return the missing receiver repair form schema."""
    fields: dict[vol.Marker, Any] = {}

    if available_receivers:
        default_receiver_id = next(iter(available_receivers))
        fields[infrared_receiver_field(default_receiver_id, available_receivers)] = (
            infrared_receiver_selector(available_receivers)
        )

    fields[vol.Optional(CONF_DISABLE_RECEIVER, default=not available_receivers)] = bool

    return vol.Schema(fields)


def _config_entry_and_remote_for_issue(
    hass: HomeAssistant,
    issue_id: str,
    *,
    issue_type: str,
) -> tuple[ConfigEntry | None, dict[str, Any] | None]:
    """Return the config entry and remote for a missing infrared repair issue."""
    remote_id = issue_id.removeprefix(f"{issue_type}_")

    for entry in hass.config_entries.async_entries(DOMAIN):
        remote = universal_remote_from_config_entry_data(
            {**entry.data, **entry.options}
        )
        if remote is not None and str(remote.get(CONF_REMOTE_ID)) == remote_id:
            return entry, remote

    return None, None
