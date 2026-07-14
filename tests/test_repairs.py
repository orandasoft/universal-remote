"""Tests for Universal Remote repair helpers."""

from typing import cast
from unittest.mock import AsyncMock, patch

from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
    ISSUE_LINKED_INFRARED_EMITTER_MISSING,
    ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
)
from custom_components.universal_remote import repairs as repairs_platform
from custom_components.universal_remote.repairs import (
    CONF_DISABLE_EMITTER,
    CONF_DISABLE_RECEIVER,
    LinkedInfraredRepairFlow,
    _linked_infrared_emitter_issue_id,
    _linked_infrared_receiver_issue_id,
    async_create_linked_infrared_emitter_missing_issue,
    async_create_linked_infrared_receiver_missing_issue,
    async_delete_linked_infrared_emitter_missing_issue,
    async_delete_linked_infrared_receiver_missing_issue,
    async_delete_stale_linked_infrared_emitter_missing_issues,
    async_delete_stale_linked_infrared_receiver_missing_issues,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir, selector
from pytest_homeassistant_custom_component.common import MockConfigEntry


def _emitter_option(entity_id: str) -> selector.SelectOptionDict:
    """Return an emitter select option."""
    return selector.SelectOptionDict(value=entity_id, label=entity_id)


def _receiver_option(entity_id: str) -> selector.SelectOptionDict:
    """Return a receiver select option."""
    return selector.SelectOptionDict(value=entity_id, label=entity_id)


def _add_emitter_config_entry(
    hass: HomeAssistant,
    *,
    include_receiver: bool = True,
) -> MockConfigEntry:
    """Add a config entry with a linked infrared emitter."""
    data = {
        CONF_REMOTE_ID: "living_room_tv",
        CONF_REMOTE_NAME: "Living Room TV",
        CONF_INFRARED_EMITTER_ID: "infrared.old_emitter",
    }
    if include_receiver:
        data[CONF_INFRARED_RECEIVER_ID] = "infrared.receiver"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data=data,
        options={},
    )
    entry.add_to_hass(hass)
    return entry


def _add_receiver_config_entry(
    hass: HomeAssistant,
    *,
    include_emitter: bool = True,
) -> MockConfigEntry:
    """Add a config entry with a linked infrared receiver."""
    data = {
        CONF_REMOTE_ID: "living_room_tv",
        CONF_REMOTE_NAME: "Living Room TV",
        CONF_INFRARED_RECEIVER_ID: "infrared.old_receiver",
    }
    if include_emitter:
        data[CONF_INFRARED_EMITTER_ID] = "infrared.emitter"

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living Room TV",
        data=data,
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def _create_repair_flow(
    hass: HomeAssistant,
    issue_id: str,
) -> LinkedInfraredRepairFlow:
    """Create a typed linked infrared repair flow."""
    return cast(
        LinkedInfraredRepairFlow,
        await repairs_platform.async_create_fix_flow(hass, issue_id, None),
    )


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
    assert issue.is_fixable is True
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
    assert issue.is_fixable is True
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


async def test_missing_emitter_repair_flow_selects_replacement_emitter(
    hass: HomeAssistant,
) -> None:
    """Test missing emitter repair flow selects a replacement emitter."""
    entry = _add_emitter_config_entry(hass)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")
    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_emitter_id="infrared.old_emitter",
    )

    with (
        patch.object(
            repairs_platform,
            "available_infrared_emitters",
            return_value={
                "infrared.new_emitter": _emitter_option("infrared.new_emitter")
            },
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            AsyncMock(return_value=None),
        ) as async_reload,
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init(
            {
                CONF_INFRARED_EMITTER_ID: "infrared.new_emitter",
                CONF_DISABLE_EMITTER: False,
            }
        )

    assert result["type"] == "create_entry"
    assert entry.data[CONF_INFRARED_EMITTER_ID] == "infrared.new_emitter"
    async_reload.assert_not_awaited()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_repair_update_listener_requests_exactly_one_reload(
    hass: HomeAssistant,
) -> None:
    """Test repair persistence relies on one config-entry listener reload."""
    entry = _add_emitter_config_entry(hass)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")
    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_emitter_id="infrared.old_emitter",
    )

    async def update_listener(
        listener_hass: HomeAssistant,
        listener_entry: ConfigEntry,
    ) -> None:
        await listener_hass.config_entries.async_reload(listener_entry.entry_id)

    entry.add_update_listener(update_listener)

    with (
        patch.object(
            repairs_platform,
            "available_infrared_emitters",
            return_value={
                "infrared.new_emitter": _emitter_option("infrared.new_emitter")
            },
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            AsyncMock(return_value=None),
        ) as async_reload,
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init(
            {
                CONF_INFRARED_EMITTER_ID: "infrared.new_emitter",
                CONF_DISABLE_EMITTER: False,
            }
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    async_reload.assert_awaited_once_with(entry.entry_id)


async def test_missing_emitter_repair_flow_disables_send_support(
    hass: HomeAssistant,
) -> None:
    """Test missing emitter repair flow can disable send support."""
    entry = _add_emitter_config_entry(hass)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")
    async_create_linked_infrared_emitter_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_emitter_id="infrared.old_emitter",
    )

    with (
        patch.object(
            repairs_platform,
            "available_infrared_emitters",
            return_value={},
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            AsyncMock(return_value=None),
        ) as async_reload,
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init({CONF_DISABLE_EMITTER: True})

    assert result["type"] == "create_entry"
    assert CONF_INFRARED_EMITTER_ID not in entry.data
    assert entry.data[CONF_INFRARED_RECEIVER_ID] == "infrared.receiver"
    async_reload.assert_not_awaited()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_missing_emitter_repair_flow_requires_emitter_or_disable(
    hass: HomeAssistant,
) -> None:
    """Test repair flow requires an emitter when send support stays enabled."""
    _add_emitter_config_entry(hass)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_emitters",
        return_value={"infrared.new_emitter": _emitter_option("infrared.new_emitter")},
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init({CONF_DISABLE_EMITTER: False})

    assert result["type"] == "form"
    assert result["errors"] == {
        CONF_INFRARED_EMITTER_ID: "infrared_emitter_required",
    }


async def test_missing_emitter_repair_flow_rejects_unavailable_emitter(
    hass: HomeAssistant,
) -> None:
    """Test repair flow rejects unavailable replacement emitters."""
    _add_emitter_config_entry(hass)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_emitters",
        return_value={"infrared.new_emitter": _emitter_option("infrared.new_emitter")},
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init(
            {
                CONF_INFRARED_EMITTER_ID: "infrared.missing_emitter",
                CONF_DISABLE_EMITTER: False,
            }
        )

    assert result["type"] == "form"
    assert result["errors"] == {
        CONF_INFRARED_EMITTER_ID: "infrared_emitter_unavailable",
    }


async def test_missing_emitter_repair_flow_shows_form(
    hass: HomeAssistant,
) -> None:
    """Test repair flow shows a form with emitter placeholders."""
    _add_emitter_config_entry(hass)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_emitters",
        return_value={"infrared.new_emitter": _emitter_option("infrared.new_emitter")},
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["description_placeholders"] == {
        "remote_name": "Living Room TV",
        "infrared_emitter_id": "infrared.old_emitter",
    }


async def test_missing_emitter_repair_flow_keeps_at_least_one_infrared_target(
    hass: HomeAssistant,
) -> None:
    """Test repair flow rejects disabling the only configured infrared target."""
    _add_emitter_config_entry(hass, include_receiver=False)
    issue_id = _linked_infrared_emitter_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_emitters",
        return_value={},
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init({CONF_DISABLE_EMITTER: True})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "infrared_target_required"}


async def test_missing_receiver_repair_flow_selects_replacement_receiver(
    hass: HomeAssistant,
) -> None:
    """Test missing receiver repair flow selects a replacement receiver."""
    entry = _add_receiver_config_entry(hass)
    issue_id = _linked_infrared_receiver_issue_id("living_room_tv")
    async_create_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_receiver_id="infrared.old_receiver",
    )

    with (
        patch.object(
            repairs_platform,
            "available_infrared_receivers",
            return_value={
                "infrared.new_receiver": _receiver_option("infrared.new_receiver")
            },
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            AsyncMock(return_value=None),
        ) as async_reload,
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init(
            {
                CONF_INFRARED_RECEIVER_ID: "infrared.new_receiver",
                CONF_DISABLE_RECEIVER: False,
            }
        )

    assert result["type"] == "create_entry"
    assert entry.data[CONF_INFRARED_RECEIVER_ID] == "infrared.new_receiver"
    async_reload.assert_not_awaited()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_missing_receiver_repair_flow_disables_receive_support(
    hass: HomeAssistant,
) -> None:
    """Test missing receiver repair flow can disable receive support."""
    entry = _add_receiver_config_entry(hass)
    issue_id = _linked_infrared_receiver_issue_id("living_room_tv")
    async_create_linked_infrared_receiver_missing_issue(
        hass,
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        infrared_receiver_id="infrared.old_receiver",
    )

    with (
        patch.object(
            repairs_platform,
            "available_infrared_receivers",
            return_value={},
        ),
        patch.object(
            hass.config_entries,
            "async_reload",
            AsyncMock(return_value=None),
        ) as async_reload,
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init({CONF_DISABLE_RECEIVER: True})

    assert result["type"] == "create_entry"
    assert CONF_INFRARED_RECEIVER_ID not in entry.data
    assert entry.data[CONF_INFRARED_EMITTER_ID] == "infrared.emitter"
    async_reload.assert_not_awaited()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_missing_receiver_repair_flow_requires_receiver_or_disable(
    hass: HomeAssistant,
) -> None:
    """Test repair flow requires a receiver when receive support stays enabled."""
    _add_receiver_config_entry(hass)
    issue_id = _linked_infrared_receiver_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_receivers",
        return_value={
            "infrared.new_receiver": _receiver_option("infrared.new_receiver")
        },
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init({CONF_DISABLE_RECEIVER: False})

    assert result["type"] == "form"
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_required",
    }


async def test_missing_receiver_repair_flow_rejects_unavailable_receiver(
    hass: HomeAssistant,
) -> None:
    """Test repair flow rejects unavailable replacement receivers."""
    _add_receiver_config_entry(hass)
    issue_id = _linked_infrared_receiver_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_receivers",
        return_value={
            "infrared.new_receiver": _receiver_option("infrared.new_receiver")
        },
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init(
            {
                CONF_INFRARED_RECEIVER_ID: "infrared.missing_receiver",
                CONF_DISABLE_RECEIVER: False,
            }
        )

    assert result["type"] == "form"
    assert result["errors"] == {
        CONF_INFRARED_RECEIVER_ID: "infrared_receiver_unavailable",
    }


async def test_missing_receiver_repair_flow_shows_form(
    hass: HomeAssistant,
) -> None:
    """Test repair flow shows a form with receiver placeholders."""
    _add_receiver_config_entry(hass)
    issue_id = _linked_infrared_receiver_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_receivers",
        return_value={
            "infrared.new_receiver": _receiver_option("infrared.new_receiver")
        },
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init()

    assert result["type"] == "form"
    assert result["step_id"] == "init"
    assert result["description_placeholders"] == {
        "remote_name": "Living Room TV",
        "infrared_receiver_id": "infrared.old_receiver",
    }


async def test_missing_receiver_repair_flow_keeps_at_least_one_infrared_target(
    hass: HomeAssistant,
) -> None:
    """Test repair flow rejects disabling the only configured infrared target."""
    _add_receiver_config_entry(hass, include_emitter=False)
    issue_id = _linked_infrared_receiver_issue_id("living_room_tv")

    with patch.object(
        repairs_platform,
        "available_infrared_receivers",
        return_value={},
    ):
        flow = await _create_repair_flow(hass, issue_id)
        result = await flow.async_step_init({CONF_DISABLE_RECEIVER: True})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "infrared_target_required"}


async def test_missing_emitter_repair_flow_aborts_for_missing_remote(
    hass: HomeAssistant,
) -> None:
    """Test emitter repair flow aborts when the linked remote no longer exists."""
    flow = await _create_repair_flow(
        hass,
        _linked_infrared_emitter_issue_id("missing"),
    )
    result = await flow.async_step_init()

    assert result["type"] == "abort"
    assert result["reason"] == "remote_not_found"


async def test_missing_receiver_repair_flow_aborts_for_missing_remote(
    hass: HomeAssistant,
) -> None:
    """Test repair flow aborts when the linked remote no longer exists."""
    flow = await _create_repair_flow(
        hass,
        _linked_infrared_receiver_issue_id("missing"),
    )
    result = await flow.async_step_init()

    assert result["type"] == "abort"
    assert result["reason"] == "remote_not_found"


async def test_repair_flow_aborts_for_unfixable_issue(hass: HomeAssistant) -> None:
    """Test repair flow aborts for issue types it cannot fix."""
    flow = await _create_repair_flow(
        hass,
        "unsupported_issue",
    )
    result = await flow.async_step_init()

    assert result["type"] == "abort"
    assert result["reason"] == "not_fixable"


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
