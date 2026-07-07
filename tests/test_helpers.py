"""Tests for Universal Remote helper functions."""

from collections.abc import Mapping
from typing import Any, cast
from unittest.mock import patch

import voluptuous as vol

from custom_components.universal_remote.const import (
    CONF_COMMAND_CREATE_BUTTON,
    CONF_COMMAND_DATA,
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from custom_components.universal_remote.helpers import (
    available_infrared_emitters,
    available_infrared_receivers,
    command_create_button,
    command_object,
    command_options,
    command_payload,
    find_command_key,
    find_configured_command,
    infrared_emitter_field,
    infrared_emitter_field_with_current,
    infrared_emitter_selector,
    infrared_receiver_field,
    infrared_receiver_field_with_current,
    infrared_receiver_selector,
    _infrared_area_name,
    _infrared_device_context_label,
    _infrared_entity_label,
    linked_entity_is_available,
    normalize_command_mapping,
    normalize_command_name,
    normalize_command_objects,
    normalize_remote_id,
    unique_remote_id,
    universal_remote_device_info,
    universal_remote_from_config_entry_data,
    universal_remotes_from_config_entry,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, selector

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _field_default(field: Any) -> Any:
    """Return a voluptuous field default for typing-friendly tests."""
    default = cast(Any, field.default)
    try:
        return default()
    except TypeError:
        return None


def test_available_infrared_emitters(hass: HomeAssistant) -> None:
    """Test available infrared emitter selector options."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "infrared",
        "test",
        "ir_b",
        suggested_object_id="ir_b",
        original_name="IR B",
    )
    registry.async_get_or_create(
        "infrared",
        "test",
        "ir_a",
        suggested_object_id="ir_a",
        original_name="IR A",
    )
    registry.async_get_or_create(
        "infrared",
        "test",
        "ir_disabled",
        suggested_object_id="ir_disabled",
        original_name="Disabled IR",
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    registry.async_get_or_create(
        "light",
        "test",
        "light",
        suggested_object_id="ignored",
        original_name="Ignored",
    )

    with patch(
        "custom_components.universal_remote.helpers.infrared.async_get_emitters",
        return_value=[
            "infrared.ir_b",
            "infrared.ir_a",
            "infrared.ir_disabled",
        ],
    ):
        options = available_infrared_emitters(hass)

    assert list(options) == ["infrared.ir_a", "infrared.ir_b"]
    assert options["infrared.ir_a"]["value"] == "infrared.ir_a"
    assert options["infrared.ir_a"]["label"] == "IR A (infrared.ir_a)"
    assert options["infrared.ir_b"]["value"] == "infrared.ir_b"
    assert options["infrared.ir_b"]["label"] == "IR B (infrared.ir_b)"
    assert "infrared.ir_disabled" not in options
    assert "light.ignored" not in options


def test_available_infrared_receivers(hass: HomeAssistant) -> None:
    """Test available infrared receiver selector options."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "infrared",
        "test",
        "receiver_b",
        suggested_object_id="receiver_b",
        original_name="Receiver B",
    )
    registry.async_get_or_create(
        "infrared",
        "test",
        "receiver_a",
        suggested_object_id="receiver_a",
        original_name="Receiver A",
    )
    registry.async_get_or_create(
        "infrared",
        "test",
        "receiver_disabled",
        suggested_object_id="receiver_disabled",
        original_name="Disabled Receiver",
        disabled_by=er.RegistryEntryDisabler.USER,
    )

    with patch(
        "custom_components.universal_remote.helpers.infrared.async_get_receivers",
        return_value=[
            "infrared.receiver_b",
            "infrared.receiver_a",
            "infrared.receiver_disabled",
        ],
    ):
        options = available_infrared_receivers(hass)

    assert list(options) == ["infrared.receiver_a", "infrared.receiver_b"]
    assert options["infrared.receiver_a"]["value"] == "infrared.receiver_a"
    assert (
        options["infrared.receiver_a"]["label"]
        == "Receiver A (infrared.receiver_a)"
    )
    assert options["infrared.receiver_b"]["value"] == "infrared.receiver_b"
    assert (
        options["infrared.receiver_b"]["label"]
        == "Receiver B (infrared.receiver_b)"
    )
    assert "infrared.receiver_disabled" not in options


class _FakeRegistryEntry:
    """Fake entity registry entry for label tests."""

    def __init__(
        self,
        *,
        entity_id: str = "infrared.receiver",
        name: str | None = "IR Receiver",
        original_name: str | None = None,
        device_id: str | None = "device-id",
        area_id: str | None = None,
    ) -> None:
        """Initialize fake registry entry."""
        self.entity_id = entity_id
        self.name = name
        self.original_name = original_name
        self.device_id = device_id
        self.area_id = area_id


class _FakeDevice:
    """Fake device registry entry for label tests."""

    def __init__(
        self,
        *,
        name_by_user: str | None = "BroadLink RM4 Pro",
        name: str | None = None,
        model: str | None = None,
        area_id: str | None = "area-id",
    ) -> None:
        """Initialize fake device."""
        self.name_by_user = name_by_user
        self.name = name
        self.model = model
        self.area_id = area_id


class _FakeDeviceRegistry:
    """Fake device registry for label tests."""

    def __init__(self, device: _FakeDevice | None) -> None:
        """Initialize fake device registry."""
        self._device = device

    def async_get(self, _device_id: str) -> _FakeDevice | None:
        """Return a fake device."""
        return self._device


class _FakeArea:
    """Fake area registry entry for label tests."""

    name = "Living Room"


class _FakeAreaRegistry:
    """Fake area registry for label tests."""

    def __init__(self, area: _FakeArea | None) -> None:
        """Initialize fake area registry."""
        self._area = area

    def async_get_area(self, _area_id: str) -> _FakeArea | None:
        """Return a fake area."""
        return self._area


def test_infrared_entity_label_includes_area_device_and_entity_id(
    hass: HomeAssistant,
) -> None:
    """Test infrared labels include area, device, and entity id context."""
    entry = _FakeRegistryEntry()

    with (
        patch(
            "custom_components.universal_remote.helpers.dr.async_get",
            return_value=_FakeDeviceRegistry(_FakeDevice()),
        ),
        patch(
            "custom_components.universal_remote.helpers.ar.async_get",
            return_value=_FakeAreaRegistry(_FakeArea()),
        ),
    ):
        label = _infrared_entity_label(hass, "infrared.receiver", entry)

    assert label == (
        "IR Receiver — Living Room BroadLink RM4 Pro (infrared.receiver)"
    )


def test_infrared_entity_label_uses_entity_id_without_registry_entry(
    hass: HomeAssistant,
) -> None:
    """Test infrared labels fall back to entity id without a registry entry."""
    assert (
        _infrared_entity_label(hass, "infrared.receiver", None)
        == "infrared.receiver"
    )


def test_infrared_entity_label_uses_entity_id_without_names_or_context(
    hass: HomeAssistant,
) -> None:
    """Test infrared labels fall back to entity id without names or context."""
    entry = _FakeRegistryEntry(
        entity_id="infrared.receiver",
        name=None,
        original_name=None,
        device_id=None,
    )

    assert (
        _infrared_entity_label(hass, "infrared.receiver", entry)
        == "infrared.receiver"
    )


def test_infrared_device_context_label_handles_missing_device(
    hass: HomeAssistant,
) -> None:
    """Test context labels handle missing devices."""
    entry = _FakeRegistryEntry()

    with patch(
        "custom_components.universal_remote.helpers.dr.async_get",
        return_value=_FakeDeviceRegistry(None),
    ):
        assert _infrared_device_context_label(hass, entry) is None


def test_infrared_device_context_label_uses_device_without_area(
    hass: HomeAssistant,
) -> None:
    """Test context labels use the device name when no area is available."""
    entry = _FakeRegistryEntry(area_id=None)
    device = _FakeDevice(area_id=None)

    with (
        patch(
            "custom_components.universal_remote.helpers.dr.async_get",
            return_value=_FakeDeviceRegistry(device),
        ),
        patch(
            "custom_components.universal_remote.helpers.ar.async_get",
            return_value=_FakeAreaRegistry(None),
        ),
    ):
        assert _infrared_device_context_label(hass, entry) == "BroadLink RM4 Pro"


def test_infrared_area_name_handles_missing_area(
    hass: HomeAssistant,
) -> None:
    """Test area labels handle stale area ids."""
    entry = _FakeRegistryEntry(area_id="area-id")
    device = _FakeDevice(area_id=None)

    with patch(
        "custom_components.universal_remote.helpers.ar.async_get",
        return_value=_FakeAreaRegistry(None),
    ):
        assert _infrared_area_name(hass, entry, device) is None


def test_infrared_emitter_selector_includes_current_missing_emitter() -> None:
    """Test selector includes stale current emitter."""
    available: dict[str, selector.SelectOptionDict] = {
        "infrared.valid": selector.SelectOptionDict(
            value="infrared.valid",
            label="Valid",
        )
    }

    selector_obj = infrared_emitter_selector(
        available,
        current_emitter_id="infrared.missing",
    )

    options = cast(list[selector.SelectOptionDict], selector_obj.config["options"])
    values = [option["value"] for option in options]
    assert values == ["infrared.valid", "infrared.missing"]


def test_infrared_receiver_selector_includes_current_missing_receiver() -> None:
    """Test selector includes stale current receiver."""
    available: dict[str, selector.SelectOptionDict] = {
        "infrared.valid": selector.SelectOptionDict(
            value="infrared.valid",
            label="Valid",
        )
    }

    selector_obj = infrared_receiver_selector(
        available,
        current_receiver_id="infrared.missing",
    )

    options = cast(list[selector.SelectOptionDict], selector_obj.config["options"])
    values = [option["value"] for option in options]
    assert values == ["infrared.valid", "infrared.missing"]



def test_infrared_emitter_field_defaults() -> None:
    """Test selector field defaults."""
    available: dict[str, selector.SelectOptionDict] = {
        "infrared.valid": selector.SelectOptionDict(
            value="infrared.valid",
            label="Valid",
        )
    }

    assert (
        _field_default(infrared_emitter_field("infrared.valid", available))
        == "infrared.valid"
    )
    assert _field_default(infrared_emitter_field("infrared.missing", available)) is None
    assert (
        _field_default(
            infrared_emitter_field_with_current(
                "infrared.missing",
                available,
            )
        )
        == "infrared.missing"
    )


def test_infrared_receiver_field_defaults() -> None:
    """Test receiver selector field defaults."""
    available: dict[str, selector.SelectOptionDict] = {
        "infrared.valid": selector.SelectOptionDict(
            value="infrared.valid",
            label="Valid",
        )
    }

    assert (
        _field_default(infrared_receiver_field("infrared.valid", available))
        == "infrared.valid"
    )
    assert _field_default(infrared_receiver_field("infrared.missing", available)) is None
    assert (
        _field_default(
            infrared_receiver_field_with_current(
                "infrared.missing",
                available,
            )
        )
        == "infrared.missing"
    )



def test_normalize_ids_and_command_names() -> None:
    """Test id and command normalization."""
    assert normalize_remote_id(" Living Room TV! ") == "living_room_tv"
    assert normalize_remote_id("!!!") == "remote"
    assert normalize_command_name(" power on! ") == "POWER_ON"


def test_unique_remote_id() -> None:
    """Test remote id collision handling."""
    remotes = [
        {CONF_REMOTE_ID: "living_room_tv"},
        {CONF_REMOTE_ID: "living_room_tv_2"},
    ]

    assert unique_remote_id("Living Room TV", remotes) == "living_room_tv_3"
    assert (
        unique_remote_id(
            "Living Room TV",
            remotes,
            current_remote_id="living_room_tv",
        )
        == "living_room_tv"
    )


def test_find_command_key_case_insensitive() -> None:
    """Test command key lookup."""
    commands = {"Power_On": "payload"}

    assert find_command_key(commands, "POWER_ON") == "Power_On"
    assert find_command_key(commands, "MISSING") is None


def test_find_configured_command_exact_match_wins() -> None:
    """Test configured command lookup prefers exact command names."""
    commands = {
        "Power": "exact-payload",
        "POWER": "normalized-payload",
    }

    assert find_configured_command(commands, "Power") == ("Power", "exact-payload")


def test_find_configured_command_normalized_match() -> None:
    """Test configured command lookup falls back to normalized command names."""
    commands = {
        "Power On": "payload",
    }

    assert find_configured_command(commands, "power_on") == ("Power On", "payload")


def test_find_configured_command_returns_none_for_missing_command() -> None:
    """Test configured command lookup returns none when missing."""
    assert find_configured_command({"POWER": "payload"}, "MUTE") is None


def test_find_configured_command_preserves_stored_value() -> None:
    """Test configured command lookup returns stored values unchanged."""
    commands = {
        "BROKEN": "",
    }

    assert find_configured_command(commands, "broken") == ("BROKEN", "")

    
def test_command_payload_helpers() -> None:
    """Test command payload and button helper branches."""
    assert command_payload("38000:1,2") == "38000:1,2"
    assert command_payload(123) is None
    assert command_payload({CONF_COMMAND_DATA: "38000:3,4"}) == "38000:3,4"
    assert command_payload({CONF_COMMAND_DATA: ""}) is None

    assert command_create_button({CONF_COMMAND_CREATE_BUTTON: True}) is True
    assert command_create_button({CONF_COMMAND_CREATE_BUTTON: False}) is False
    assert command_create_button("38000:1,2") is False

    assert command_object("38000:1,2", create_button=True) == {
        CONF_COMMAND_DATA: "38000:1,2",
        CONF_COMMAND_CREATE_BUTTON: True,
    }


def test_normalize_command_objects_and_mapping() -> None:
    """Test command object and payload normalization."""
    commands = {
        "POWER_ON": "38000:1,2",
        "POWER_OFF": {
            CONF_COMMAND_DATA: "38000:3,4",
            CONF_COMMAND_CREATE_BUTTON: True,
        },
        "EMPTY_STRING": "",
        "EMPTY_DATA": {CONF_COMMAND_DATA: ""},
        "NOT_MAPPING": 123,
        "NO_DATA": {CONF_COMMAND_CREATE_BUTTON: True},
        1: "ignored",
        "": "ignored",
    }

    assert normalize_command_objects(commands) == {
        "POWER_ON": {
            CONF_COMMAND_DATA: "38000:1,2",
            CONF_COMMAND_CREATE_BUTTON: False,
        },
        "POWER_OFF": {
            CONF_COMMAND_DATA: "38000:3,4",
            CONF_COMMAND_CREATE_BUTTON: True,
        },
    }
    assert normalize_command_mapping(commands) == {
        "POWER_ON": "38000:1,2",
        "POWER_OFF": "38000:3,4",
    }


def test_universal_remote_device_info() -> None:
    """Test universal remote device info preserves existing identifiers."""
    device_info = universal_remote_device_info(
        "living_room_tv",
        "Living Room TV",
    )

    assert device_info["identifiers"] == {(DOMAIN, "living_room_tv")}
    assert device_info["name"] == "Living Room TV"


def test_universal_remote_infers_device_type_from_codeset() -> None:
    """Test codeset device type is inferred for generic remotes."""
    assert universal_remote_from_config_entry_data(
        {
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
            CONF_REMOTE_CODESET: "lg_tv",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        }
    ) == {
        CONF_REMOTE_ID: "tv",
        CONF_REMOTE_NAME: "TV",
        CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
        CONF_REMOTE_CODESET: "lg_tv",
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
    }


def test_universal_remote_preserves_matching_codeset_device_type() -> None:
    """Test matching stored device type and codeset are preserved."""
    assert universal_remote_from_config_entry_data(
        {
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
            CONF_REMOTE_CODESET: "lg_tv",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        }
    ) == {
        CONF_REMOTE_ID: "tv",
        CONF_REMOTE_NAME: "TV",
        CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
        CONF_REMOTE_CODESET: "lg_tv",
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
    }


def test_universal_remote_drops_codeset_when_device_type_conflicts() -> None:
    """Test conflicting stored device type drops the codeset."""
    with patch(
        "custom_components.universal_remote.helpers."
        "validate_infrared_library_device_type",
        return_value=True,
    ):
        assert universal_remote_from_config_entry_data(
            {
                CONF_REMOTE_ID: "projector",
                CONF_REMOTE_NAME: "Projector",
                CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
                CONF_REMOTE_CODESET: "lg_tv",
                CONF_REMOTE_DEVICE_TYPE: "projector",
            }
        ) == {
            CONF_REMOTE_ID: "projector",
            CONF_REMOTE_NAME: "Projector",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
            CONF_REMOTE_DEVICE_TYPE: "projector",
        }


def test_infrared_emitter_field_omits_unavailable_default() -> None:
    """Test infrared field omits defaults that are not available."""
    field = infrared_emitter_field(
        "infrared.missing",
        {
            "infrared.available": selector.SelectOptionDict(
                value="infrared.available",
                label="Available",
            )
        },
    )

    assert field.default is vol.UNDEFINED


def test_command_options_ignores_malformed_command_mapping() -> None:
    """Test command options ignores malformed command mappings."""
    assert command_options(cast(Mapping[str, Any], "not-a-mapping")) == []


def test_infrared_emitter_field_without_default_uses_required_field() -> None:
    """Test infrared emitter field has no default when no valid default is provided."""
    field = infrared_emitter_field(
        "",
        {
            "infrared.available": selector.SelectOptionDict(
                value="infrared.available",
                label="Available",
            )
        },
    )

    assert field.default is vol.UNDEFINED


def test_infrared_emitter_field_with_current_without_default_uses_required_field() -> (
    None
):
    """Test current infrared emitter field has no default when no current value exists."""
    field = infrared_emitter_field_with_current(
        "",
        {
            "infrared.available": selector.SelectOptionDict(
                value="infrared.available",
                label="Available",
            )
        },
    )

    assert field.default is vol.UNDEFINED


def test_infrared_receiver_field_omits_unavailable_default() -> None:
    """Test receiver field omits defaults that are not available."""
    field = infrared_receiver_field(
        "infrared.missing",
        {
            "infrared.available": selector.SelectOptionDict(
                value="infrared.available",
                label="Available",
            )
        },
    )

    assert field.default is vol.UNDEFINED


def test_infrared_receiver_field_without_default_uses_optional_field() -> None:
    """Test receiver field has no default when no valid default is provided."""
    field = infrared_receiver_field(
        "",
        {
            "infrared.available": selector.SelectOptionDict(
                value="infrared.available",
                label="Available",
            )
        },
    )

    assert field.default is vol.UNDEFINED


def test_infrared_receiver_field_with_current_without_default_uses_optional_field() -> (
    None
):
    """Test current receiver field has no default when no current value exists."""
    field = infrared_receiver_field_with_current(
        "",
        {
            "infrared.available": selector.SelectOptionDict(
                value="infrared.available",
                label="Available",
            )
        },
    )

    assert field.default is vol.UNDEFINED



def test_universal_remote_from_config_entry_data() -> None:
    """Test normalizing a single universal remote from config entry data."""
    assert universal_remote_from_config_entry_data(
        {
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            CONF_REMOTE_COMMANDS: {"POWER_ON": "38000:1,2", 1: "bad"},
        }
    ) == {
        CONF_REMOTE_ID: "tv",
        CONF_REMOTE_NAME: "TV",
        CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        CONF_REMOTE_COMMANDS: {
            "POWER_ON": {
                CONF_COMMAND_DATA: "38000:1,2",
                CONF_COMMAND_CREATE_BUTTON: False,
            }
        },
    }


def test_universal_remote_from_config_entry_data_supports_receiver_only() -> None:
    """Test normalizing a receiver-only universal remote."""
    assert universal_remote_from_config_entry_data(
        {
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
            CONF_REMOTE_CODESET: "lg_tv",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        }
    ) == {
        CONF_REMOTE_ID: "tv",
        CONF_REMOTE_NAME: "TV",
        CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
        CONF_REMOTE_CODESET: "lg_tv",
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
    }


def test_universal_remote_from_config_entry_data_supports_emitter_and_receiver() -> None:
    """Test normalizing a universal remote with emitter and receiver."""
    assert universal_remote_from_config_entry_data(
        {
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: "infrared.emitter",
            CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
        }
    ) == {
        CONF_REMOTE_ID: "tv",
        CONF_REMOTE_NAME: "TV",
        CONF_INFRARED_EMITTER_ID: "infrared.emitter",
        CONF_INFRARED_RECEIVER_ID: "infrared.receiver",
        CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
    }


def test_universal_remote_from_config_entry_data_rejects_missing_ir_target() -> None:
    """Test normalizing rejects remotes without an emitter or receiver."""
    assert (
        universal_remote_from_config_entry_data(
            {
                CONF_REMOTE_ID: "tv",
                CONF_REMOTE_NAME: "TV",
                CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            }
        )
        is None
    )



def test_universal_remote_from_config_entry_data_rejects_malformed_data() -> None:
    """Test malformed single universal remote config entry data is rejected."""
    assert (
        universal_remote_from_config_entry_data(
            {
                CONF_REMOTE_ID: "tv",
                CONF_REMOTE_NAME: "",
                CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
            }
        )
        is None
    )


def test_universal_remotes_from_config_entry_supports_single_entry_data() -> None:
    """Test config entry remote normalization supports one-remote entry data."""
    entry = MockConfigEntry(
        domain="universal_remote",
        data={
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
        },
        options={CONF_REMOTE_COMMANDS: {"POWER_ON": "38000:1,2"}},
    )

    assert universal_remotes_from_config_entry(entry) == [
        {
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "TV",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_GENERIC,
            CONF_REMOTE_COMMANDS: {
                "POWER_ON": {
                    CONF_COMMAND_DATA: "38000:1,2",
                    CONF_COMMAND_CREATE_BUTTON: False,
                }
            },
        }
    ]


def test_universal_remotes_from_config_entry_rejects_malformed_single_entry_data() -> (
    None
):
    """Test config entry remote normalization rejects malformed one-remote data."""
    entry = MockConfigEntry(
        domain="universal_remote",
        data={
            CONF_REMOTE_ID: "tv",
            CONF_REMOTE_NAME: "",
            CONF_INFRARED_EMITTER_ID: "infrared.test_ir",
        },
        options={},
    )

    assert universal_remotes_from_config_entry(entry) == []


def test_linked_entity_is_available_when_entity_exists(
    hass: HomeAssistant,
) -> None:
    """Test linked entity availability returns true for an existing available entity."""
    hass.states.async_set("infrared.test_emitter", "on")

    assert linked_entity_is_available(hass, "infrared.test_emitter")


def test_linked_entity_is_available_when_entity_missing(
    hass: HomeAssistant,
) -> None:
    """Test linked entity availability returns false for a missing entity."""
    assert not linked_entity_is_available(hass, "infrared.missing_emitter")


def test_linked_entity_is_available_when_entity_unavailable(
    hass: HomeAssistant,
) -> None:
    """Test linked entity availability returns false for an unavailable entity."""
    hass.states.async_set("infrared.test_emitter", STATE_UNAVAILABLE)

    assert not linked_entity_is_available(hass, "infrared.test_emitter")


def test_linked_entity_is_available_preserves_unknown_behavior(
    hass: HomeAssistant,
) -> None:
    """Test unknown linked entities are treated as available for compatibility."""
    hass.states.async_set("infrared.test_emitter", "unknown")

    assert linked_entity_is_available(hass, "infrared.test_emitter")