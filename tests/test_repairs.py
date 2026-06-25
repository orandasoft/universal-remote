"""Tests for Universal Remote repair helpers."""

from custom_components.universal_remote.const import (
    DOMAIN,
    ISSUE_LINKED_INFRARED_EMITTER_MISSING,
    ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
)
from custom_components.universal_remote.repairs import (
    _linked_infrared_emitter_issue_id,
    _linked_infrared_receiver_issue_id,
    async_create_linked_infrared_emitter_missing_issue,
    async_create_linked_infrared_receiver_missing_issue,
    async_delete_linked_infrared_emitter_missing_issue,
    async_delete_linked_infrared_receiver_missing_issue,
    async_delete_stale_linked_infrared_emitter_missing_issues,
    async_delete_stale_linked_infrared_receiver_missing_issues,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir


def test_create_and_delete_missing_infrared_emitter_issue(
    hass: HomeAssistant,
) -> None:
    """Test missing linked infrared emitter repair issue lifecycle."""
    issue_registry = ir.async_get(hass)

    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_emitter_id="infrared.missing",
    )

    issue = issue_registry.async_get_issue(
        DOMAIN,
        _linked_infrared_emitter_issue_id("living_room_tv"),
    )
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == ISSUE_LINKED_INFRARED_EMITTER_MISSING
    assert issue.translation_placeholders == {
        "remote_name": "Living Room TV",
        "infrared_emitter_id": "infrared.missing",
    }

    async_delete_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="living_room_tv",
    )

    assert (
        issue_registry.async_get_issue(
            DOMAIN,
            _linked_infrared_emitter_issue_id("living_room_tv"),
        )
        is None
    )


def test_create_and_delete_missing_infrared_receiver_issue(
    hass: HomeAssistant,
) -> None:
    """Test missing linked infrared receiver repair issue lifecycle."""
    issue_registry = ir.async_get(hass)

    async_create_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_receiver_id="infrared.receiver_missing",
    )

    issue = issue_registry.async_get_issue(
        DOMAIN,
        _linked_infrared_receiver_issue_id("living_room_tv"),
    )
    assert issue is not None
    assert issue.is_fixable is False
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == ISSUE_LINKED_INFRARED_RECEIVER_MISSING
    assert issue.translation_placeholders == {
        "remote_name": "Living Room TV",
        "infrared_receiver_id": "infrared.receiver_missing",
    }

    async_delete_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="living_room_tv",
    )

    assert (
        issue_registry.async_get_issue(
            DOMAIN,
            _linked_infrared_receiver_issue_id("living_room_tv"),
        )
        is None
    )


def test_delete_stale_missing_infrared_emitter_issues(
    hass: HomeAssistant,
) -> None:
    """Test stale missing linked infrared emitter repair issues are deleted."""
    issue_registry = ir.async_get(hass)

    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="keep",
        remote_name="Keep",
        infrared_emitter_id="infrared.keep",
    )
    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="stale",
        remote_name="Stale",
        infrared_emitter_id="infrared.stale",
    )

    async_delete_stale_linked_infrared_emitter_missing_issues(
        hass, configured_remote_ids={"keep"}
    )

    assert (
        issue_registry.async_get_issue(
            DOMAIN, _linked_infrared_emitter_issue_id("keep")
        )
        is not None
    )
    assert (
        issue_registry.async_get_issue(
            DOMAIN, _linked_infrared_emitter_issue_id("stale")
        )
        is None
    )


def test_delete_stale_missing_infrared_receiver_issues(
    hass: HomeAssistant,
) -> None:
    """Test stale missing linked infrared receiver repair issues are deleted."""
    issue_registry = ir.async_get(hass)

    async_create_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="keep",
        remote_name="Keep",
        infrared_receiver_id="infrared.keep_receiver",
    )
    async_create_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="stale",
        remote_name="Stale",
        infrared_receiver_id="infrared.stale_receiver",
    )

    async_delete_stale_linked_infrared_receiver_missing_issues(
        hass, configured_remote_ids={"keep"}
    )

    assert (
        issue_registry.async_get_issue(
            DOMAIN, _linked_infrared_receiver_issue_id("keep")
        )
        is not None
    )
    assert (
        issue_registry.async_get_issue(
            DOMAIN, _linked_infrared_receiver_issue_id("stale")
        )
        is None
    )


def test_delete_stale_missing_infrared_issues_ignores_unrelated_issues(
    hass: HomeAssistant,
) -> None:
    """Test stale cleanup ignores unrelated repair issues."""
    issue_registry = ir.async_get(hass)

    ir.async_create_issue(
        hass,
        DOMAIN,
        "unrelated_issue",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LINKED_INFRARED_EMITTER_MISSING,
        translation_placeholders={
            "remote_name": "Unrelated",
            "infrared_emitter_id": "infrared.unrelated",
        },
    )
    ir.async_create_issue(
        hass,
        "other_domain",
        f"{ISSUE_LINKED_INFRARED_RECEIVER_MISSING}_stale",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
        translation_placeholders={
            "remote_name": "Other",
            "infrared_receiver_id": "infrared.other",
        },
    )

    async_delete_stale_linked_infrared_emitter_missing_issues(
        hass,
        configured_remote_ids=set(),
    )
    async_delete_stale_linked_infrared_receiver_missing_issues(
        hass,
        configured_remote_ids=set(),
    )

    assert issue_registry.async_get_issue(DOMAIN, "unrelated_issue") is not None
    assert (
        issue_registry.async_get_issue(
            "other_domain", f"{ISSUE_LINKED_INFRARED_RECEIVER_MISSING}_stale"
        )
        is not None
    )


def test_delete_stale_linked_infrared_issues_keeps_configured_issues(
    hass: HomeAssistant,
) -> None:
    """Test stale issue cleanup keeps issues for configured remotes."""
    issue_registry = ir.async_get(hass)

    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="living_room",
        remote_name="Living Room",
        infrared_emitter_id="infrared.living_room",
    )
    async_create_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="living_room",
        remote_name="Living Room",
        infrared_receiver_id="infrared.living_room_receiver",
    )

    async_delete_stale_linked_infrared_emitter_missing_issues(
        hass,
        configured_remote_ids={"living_room"},
    )
    async_delete_stale_linked_infrared_receiver_missing_issues(
        hass,
        configured_remote_ids={"living_room"},
    )

    assert (
        DOMAIN,
        _linked_infrared_emitter_issue_id("living_room"),
    ) in issue_registry.issues
    assert (
        DOMAIN,
        _linked_infrared_receiver_issue_id("living_room"),
    ) in issue_registry.issues
