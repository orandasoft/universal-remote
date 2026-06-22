"""Repairs support for the Universal Remote integration."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN, ISSUE_LINKED_INFRARED_EMITTER_MISSING


def _linked_infrared_emitter_issue_id(remote_id: str) -> str:
    """Return the repair issue id for a missing linked infrared emitter."""
    return f"{ISSUE_LINKED_INFRARED_EMITTER_MISSING}_{remote_id}"


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
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LINKED_INFRARED_EMITTER_MISSING,
        translation_placeholders={
            "remote_name": remote_name,
            "infrared_emitter_id": infrared_emitter_id,
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


def async_delete_stale_linked_infrared_emitter_missing_issues(
    hass: HomeAssistant,
    *,
    configured_remote_ids: set[str],
) -> None:
    """Delete missing-infrared repair issues for removed universal remotes."""
    issue_registry = ir.async_get(hass)
    issue_id_prefix = f"{ISSUE_LINKED_INFRARED_EMITTER_MISSING}_"

    for issue in list(issue_registry.issues.values()):
        if issue.domain != DOMAIN or not issue.issue_id.startswith(issue_id_prefix):
            continue

        remote_id = issue.issue_id.removeprefix(issue_id_prefix)
        if remote_id not in configured_remote_ids:
            ir.async_delete_issue(hass, DOMAIN, issue.issue_id)
