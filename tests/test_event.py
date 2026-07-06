"""Tests for Universal Remote received-command event helpers."""

from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from infrared_protocols.commands import Command

from custom_components.universal_remote import event as event_platform
from custom_components.universal_remote import protocols as protocol_helpers
from custom_components.universal_remote.runtime import UniversalRemoteRuntime
from custom_components.universal_remote.const import (
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from custom_components.universal_remote.infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
)
from custom_components.universal_remote.nec1_f16 import NEC1F16Command


class FakeCommand:
    """Fake NEC command object."""

    def __init__(self, address: int, command: int) -> None:
        """Initialize fake command."""
        self.address = address
        self.command = command


class FakeCode(Enum):
    """Fake library codeset enum."""

    POWER = (1, 2)
    VOLUME_UP = (3, 4)

    def to_command(self) -> Command:
        """Return a fake command object."""
        address, command = self.value
        return cast(Command, FakeCommand(address, command))


class FakeNEC1F16Code(Enum):
    """Fake library codeset enum with NEC1-f16 commands."""

    DTV_NUM_2 = (0xFB04, 0xDB, 0x32)

    def to_command(self) -> Command:
        """Return an NEC1-f16 command object."""
        address, function, subfunction = self.value
        return cast(
            Command,
            NEC1F16Command(
                address=address,
                function=function,
                subfunction=subfunction,
            ),
        )


class BrokenCode(Enum):
    """Fake library codeset enum with unusable members."""

    BROKEN = "broken"


class RepeatOnlyCode(Enum):
    """Fake library code whose to_command requires repeat_count."""

    POWER = (1, 2)

    def to_command(self, *, repeat_count: int) -> Command:
        """Return a fake command object."""
        assert repeat_count == 0
        address, command = self.value
        return cast(Command, FakeCommand(address, command))


class BadToCommandCode(Enum):
    """Fake library code whose to_command cannot be called by the matcher."""

    POWER = (1, 2)

    def to_command(self, *, required: int) -> Command:
        """Return a fake command object."""
        address, command = self.value
        return cast(Command, FakeCommand(address + required, command))


class NotEnum:
    """Object used to test invalid loaded codeset classes."""


class FakeEntityRegistry:
    """Fake entity registry."""

    def __init__(self) -> None:
        """Initialize the fake registry."""
        self.removed_entity_ids: list[str] = []

    def async_remove(self, entity_id: str) -> None:
        """Record a removed entity id."""
        self.removed_entity_ids.append(entity_id)


def _signal(
    timings: list[int] | None = None,
    *,
    modulation: int | None = None,
) -> Any:
    """Return a fake InfraredReceivedSignal-like object."""
    return SimpleNamespace(
        timings=timings or [243, -10000],
        modulation=modulation,
    )


def _assert_event_subset(
    event_data: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """Assert the event data includes expected values."""
    for key, value in expected.items():
        assert event_data[key] == value


def _nec1_f16_timings() -> list[int]:
    """Return valid NEC1-f16 timings for LG Japan DTV digit 2."""
    return NEC1F16Command(
        address=0xFB04,
        function=0xDB,
        subfunction=0x32,
    ).get_raw_timings()


@pytest.fixture(autouse=True)
def clear_codeset_match_map_cache() -> Generator[None, None, None]:
    """Clear cached codeset match maps between tests."""
    event_platform._codeset_match_map.cache_clear()
    yield
    event_platform._codeset_match_map.cache_clear()


@contextmanager
def _patched_nec_protocol_specs(
    *,
    nec_decode_result: Any,
    nec1_f16_decode_result: Any = None,
) -> Generator[None, None, None]:
    """Temporarily replace NEC-family protocol decoders for event tests."""

    def decode_nec(_signal_value: Any) -> Command | None:
        return cast(Command | None, nec_decode_result)

    def decode_nec1_f16(_signal_value: Any) -> Command | None:
        return cast(Command | None, nec1_f16_decode_result)

    nec_spec = event_platform.ProtocolSpec(
        protocol=protocol_helpers.PROTOCOL_NEC,
        event_type=event_platform.EVENT_NEC,
        decode=decode_nec,
        normalize=protocol_helpers._normalize_nec_command,
        event_data_builder=event_platform._nec_command_event_data,
        decode_repeat=event_platform._decode_nec_repeat_signal_event,
        repeat_event_type=event_platform.EVENT_NEC_REPEAT,
    )
    nec1_f16_spec = event_platform.ProtocolSpec(
        protocol=protocol_helpers.PROTOCOL_NEC1_F16,
        event_type=event_platform.EVENT_NEC1_F16,
        decode=decode_nec1_f16,
        normalize=protocol_helpers._normalize_nec1_f16_command,
        event_data_builder=event_platform._nec1_f16_command_event_data,
    )
    decoder_specs = {
        protocol_helpers.PROTOCOL_NEC: (nec_spec, nec1_f16_spec),
    }
    protocol_specs = {
        spec.protocol: spec
        for specs in decoder_specs.values()
        for spec in specs
    }

    with (
        patch.object(event_platform, "_DECODER_PROTOCOL_SPECS", decoder_specs),
        patch.object(event_platform, "_PROTOCOL_SPECS_BY_PROTOCOL", protocol_specs),
    ):
        event_platform._codeset_match_map.cache_clear()
        yield
        event_platform._codeset_match_map.cache_clear()


def test_event_unique_id() -> None:
    """Test event unique id generation."""
    assert event_platform.event_unique_id("living_room_tv") == (
        "living_room_tv_received_command"
    )


def test_cleanup_stale_received_command_events_remove_only_stale() -> None:
    """Test stale received-command event entities are removed from the registry."""
    registry = FakeEntityRegistry()
    entry = SimpleNamespace(entry_id="entry-id")
    entries = [
        SimpleNamespace(
            domain="sensor",
            unique_id="stale_received_command",
            entity_id="sensor.stale",
        ),
        SimpleNamespace(
            domain="event",
            unique_id=event_platform.event_unique_id("keep"),
            entity_id="event.keep",
        ),
        SimpleNamespace(
            domain="event",
            unique_id="old_received_command",
            entity_id="event.old",
        ),
        SimpleNamespace(
            domain="event",
            unique_id=None,
            entity_id="event.none",
        ),
    ]

    with (
        patch.object(event_platform.er, "async_get", return_value=registry),
        patch.object(
            event_platform.er,
            "async_entries_for_config_entry",
            return_value=entries,
        ),
    ):
        event_platform.cleanup_stale_received_command_event_entities(
            cast(Any, object()),
            cast(Any, entry),
            {event_platform.event_unique_id("keep")},
        )

    assert registry.removed_entity_ids == ["event.old"]


async def test_async_setup_entry_adds_event_entity_for_available_receiver(
    hass: Any,
) -> None:
    """Test setup creates an event entity when the receiver is available."""
    entry: Any = SimpleNamespace(data={}, options={}, entry_id="entry-id")
    remote = {
        CONF_REMOTE_ID: "living_room_tv",
        CONF_REMOTE_NAME: "Living room TV",
        CONF_INFRARED_RECEIVER_ID: "infrared.xiao_receiver",
        CONF_REMOTE_CODESET: "lg_tv",
    }
    added_entities: list[Any] = []

    def async_add_entities(entities: list[Any]) -> None:
        added_entities.extend(entities)

    delete_missing_issue = Mock()
    delete_stale_issues = Mock()
    cleanup_entities = Mock()

    with (
        patch.object(
            event_platform,
            "universal_remote_from_config_entry_data",
            return_value=remote,
        ),
        patch.object(
            event_platform.infrared,
            "async_get_receivers",
            return_value={"infrared.xiao_receiver"},
        ),
        patch.object(
            event_platform,
            "async_delete_linked_infrared_receiver_missing_issue",
            delete_missing_issue,
        ),
        patch.object(
            event_platform,
            "async_delete_stale_linked_infrared_receiver_missing_issues",
            delete_stale_issues,
        ),
        patch.object(
            event_platform,
            "cleanup_stale_received_command_event_entities",
            cleanup_entities,
        ),
    ):
        await event_platform.async_setup_entry(
            hass,
            entry,
            cast(Any, async_add_entities),
        )

    assert len(added_entities) == 1
    entity = added_entities[0]
    assert entity._attr_unique_id == "living_room_tv_received_command"
    assert entity._infrared_receiver_entity_id == "infrared.xiao_receiver"
    assert entity._codeset_id == "lg_tv"
    assert entity._attr_event_types == event_platform._event_types_for_codeset("lg_tv")
    delete_missing_issue.assert_called_once_with(
        hass,
        remote_id="living_room_tv",
    )
    delete_stale_issues.assert_called_once_with(
        hass,
        configured_remote_ids={"living_room_tv"},
    )
    cleanup_entities.assert_called_once_with(
        hass,
        entry,
        {"living_room_tv_received_command"},
    )


async def test_async_setup_entry_creates_missing_receiver_issue(hass: Any) -> None:
    """Test setup creates a repair issue when the receiver is unavailable."""
    entry: Any = SimpleNamespace(data={}, options={}, entry_id="entry-id")
    remote = {
        CONF_REMOTE_ID: "living_room_tv",
        CONF_REMOTE_NAME: "Living room TV",
        CONF_INFRARED_RECEIVER_ID: "infrared.missing_receiver",
        CONF_REMOTE_CODESET: "lg_tv",
    }
    added_entities: list[Any] = []

    create_issue = Mock()
    delete_stale_issues = Mock()
    cleanup_entities = Mock()

    with (
        patch.object(
            event_platform,
            "universal_remote_from_config_entry_data",
            return_value=remote,
        ),
        patch.object(
            event_platform.infrared,
            "async_get_receivers",
            return_value=set(),
        ),
        patch.object(
            event_platform,
            "async_create_linked_infrared_receiver_missing_issue",
            create_issue,
        ),
        patch.object(
            event_platform,
            "async_delete_stale_linked_infrared_receiver_missing_issues",
            delete_stale_issues,
        ),
        patch.object(
            event_platform,
            "cleanup_stale_received_command_event_entities",
            cleanup_entities,
        ),
    ):
        await event_platform.async_setup_entry(
            hass,
            entry,
            cast(Any, added_entities.extend),
        )

    assert len(added_entities) == 1
    entity = added_entities[0]
    assert entity._attr_unique_id == "living_room_tv_received_command"
    assert entity._infrared_receiver_entity_id == "infrared.missing_receiver"
    assert entity._codeset_id == "lg_tv"
    create_issue.assert_called_once_with(
        hass,
        remote_id="living_room_tv",
        remote_name="Living room TV",
        infrared_receiver_id="infrared.missing_receiver",
    )
    delete_stale_issues.assert_called_once_with(
        hass,
        configured_remote_ids={"living_room_tv"},
    )
    cleanup_entities.assert_called_once_with(
        hass,
        entry,
        {"living_room_tv_received_command"},
    )


def test_received_command_event_entity_handles_decoded_signal() -> None:
    """Test the received-command entity triggers and stores decoded events."""
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="living_room_tv",
        remote_name="Living room TV",
        receiver_entity_id="infrared.xiao_receiver",
        codeset_id="lg_tv",
    )
    event_data = {
        "protocol": event_platform.PROTOCOL_NEC,
        "decoded": True,
        "matched": False,
        "repeat": False,
        "address": "0xFB04",
        "command": "0x09",
    }

    with (
        patch.object(
            event_platform,
            "_decode_signal_event",
            return_value=("nec", event_data),
        ),
        patch.object(entity, "_trigger_event") as trigger_event,
        patch.object(entity, "async_write_ha_state") as write_state,
    ):
        entity._handle_signal(_signal())

    assert entity._attr_device_info == DeviceInfo(
        identifiers={(DOMAIN, "living_room_tv")},
        name="Living room TV",
    )
    assert entity._last_decoded_event == {"event_type": "nec", **event_data}
    trigger_event.assert_called_once()
    call_args = trigger_event.call_args
    assert call_args is not None
    event_type, triggered_data = call_args.args
    assert event_type == "nec"
    assert triggered_data["recent_events"] == [{"event_type": "nec", **event_data}]
    write_state.assert_called_once_with()


def test_received_command_event_entity_clears_last_decoded_event_on_unknown() -> None:
    """Test unknown non-repeat frames clear the last decoded command."""
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="living_room_tv",
        remote_name="Living room TV",
        receiver_entity_id="infrared.xiao_receiver",
        codeset_id="lg_tv",
    )
    entity._last_decoded_event = {
        "event_type": "mute",
        "protocol": event_platform.PROTOCOL_NEC,
        "decoded": True,
        "repeat": False,
    }
    event_data = {
        "protocol": event_platform.PROTOCOL_UNKNOWN,
        "decoded": False,
        "matched": False,
        "repeat": False,
    }

    with (
        patch.object(
            event_platform,
            "_decode_signal_event",
            return_value=("unknown", event_data),
        ),
        patch.object(entity, "_trigger_event"),
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_signal(_signal())

    assert entity._last_decoded_event is None


def test_event_types_for_codeset() -> None:
    """Test event types are generated from the selected codeset."""
    with patch.object(event_platform, "_load_codeset_enum", return_value=FakeCode):
        assert event_platform._event_types_for_codeset("lg_tv") == [
            "nec",
            "nec1_f16",
            "nec_repeat",
            "power",
            "unknown",
            "volume_up",
        ]


def test_event_types_for_unknown_codeset() -> None:
    """Test only unknown is exposed when no decoder is available."""
    assert event_platform._event_types_for_codeset("missing") == ["unknown"]


def test_receiver_event_types_for_codeset() -> None:
    """Test public receiver event-type helper delegates to the private helper."""
    with patch.object(
        event_platform,
        "_event_types_for_codeset",
        return_value=["nec", "unknown"],
    ) as event_types_for_codeset:
        assert event_platform.receiver_event_types_for_codeset("lg_tv") == [
            "nec",
            "unknown",
        ]

    event_types_for_codeset.assert_called_once_with("lg_tv")


def test_decode_signal_event_matches_library_command() -> None:
    """Test a decoded NEC command is matched to the library command name."""
    with (
        _patched_nec_protocol_specs(nec_decode_result=FakeCommand(1, 2)),
        patch.object(event_platform, "_load_codeset_enum", return_value=FakeCode),
    ):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "power"
    _assert_event_subset(
        event_data,
        {
            "codeset": "lg_tv",
            "decoder": "nec",
            "protocol": "nec",
            "decoded": True,
            "matched": True,
            "repeat": False,
            "address": "0x0001",
            "command": "0x02",
            "command_name": "POWER",
        },
    )


def test_decode_signal_event_returns_nec_for_unmatched_command() -> None:
    """Test unmatched decoded NEC commands return the nec event type."""
    with (
        _patched_nec_protocol_specs(nec_decode_result=FakeCommand(9, 9)),
        patch.object(event_platform, "_load_codeset_enum", return_value=FakeCode),
    ):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "nec"
    _assert_event_subset(
        event_data,
        {
            "codeset": "lg_tv",
            "decoder": "nec",
            "protocol": "nec",
            "decoded": True,
            "matched": False,
            "repeat": False,
            "address": "0x0009",
            "command": "0x09",
        },
    )


def test_decode_signal_event_returns_nec_without_enum() -> None:
    """Test missing library enums return the nec event type for decoded commands."""
    with (
        _patched_nec_protocol_specs(nec_decode_result=FakeCommand(1, 2)),
        patch.object(event_platform, "_load_codeset_enum", return_value=None),
    ):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "nec"
    _assert_event_subset(
        event_data,
        {
            "codeset": "lg_tv",
            "decoder": "nec",
            "protocol": "nec",
            "decoded": True,
            "matched": False,
            "repeat": False,
            "address": "0x0001",
            "command": "0x02",
        },
    )


def test_decode_signal_event_skips_invalid_library_command() -> None:
    """Test enum members without usable commands are ignored."""
    with (
        _patched_nec_protocol_specs(nec_decode_result=FakeCommand(1, 2)),
        patch.object(event_platform, "_load_codeset_enum", return_value=BrokenCode),
    ):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "nec"
    assert event_data["protocol"] == "nec"
    assert event_data["decoded"] is True
    assert event_data["matched"] is False


def test_decode_signal_event_matches_repeat_count_only_library_command() -> None:
    """Test library commands can expose to_command(repeat_count=0)."""
    with (
        _patched_nec_protocol_specs(nec_decode_result=FakeCommand(1, 2)),
        patch.object(event_platform, "_load_codeset_enum", return_value=RepeatOnlyCode),
    ):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "power"
    assert event_data["matched"] is True
    assert event_data["command_name"] == "POWER"


def test_decode_signal_event_ignores_unusable_to_command() -> None:
    """Test library commands with unusable to_command methods are ignored."""
    with (
        _patched_nec_protocol_specs(nec_decode_result=FakeCommand(1, 2)),
        patch.object(
            event_platform,
            "_load_codeset_enum",
            return_value=BadToCommandCode,
        ),
    ):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "nec"
    assert event_data["matched"] is False


def test_decode_signal_event_returns_unknown_for_unsupported_codeset() -> None:
    """Test unsupported receiver codesets return the unknown event type."""
    event_type, event_data = event_platform._decode_signal_event(
        "samsung_tv",
        _signal(),
    )

    assert event_type == "unknown"
    _assert_event_subset(
        event_data,
        {
            "codeset": "samsung_tv",
            "decoder": None,
            "protocol": "unknown",
            "decoded": False,
            "matched": False,
            "repeat": False,
            "timings_count": 2,
            "timings_preview": [243, -10000],
            "modulation": None,
        },
    )


def test_decode_signal_event_returns_unknown_without_codeset() -> None:
    """Test missing library codesets return the unknown event type."""
    event_type, event_data = event_platform._decode_signal_event("none", _signal())

    assert event_type == "unknown"
    assert event_data["decoder"] is None
    assert event_data["protocol"] == "unknown"
    assert event_data["timings_count"] == 2


def test_decode_signal_event_returns_unknown_for_no_library_codeset() -> None:
    """Test the no-library sentinel returns the unknown event type."""
    event_type, event_data = event_platform._decode_signal_event(
        NO_INFRARED_LIBRARY_CODESET,
        _signal(),
    )

    assert event_type == "unknown"
    assert event_data["codeset"] == NO_INFRARED_LIBRARY_CODESET
    assert event_data["decoder"] is None
    assert event_data["protocol"] == "unknown"
    assert event_data["timings_count"] == 2


def test_decode_signal_event_returns_unknown_when_decode_fails() -> None:
    """Test undecodable NEC signals return the unknown event type."""
    with _patched_nec_protocol_specs(nec_decode_result=None):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "unknown"
    _assert_event_subset(
        event_data,
        {
            "codeset": "lg_tv",
            "decoder": "nec",
            "protocol": "unknown",
            "decoded": False,
            "matched": False,
            "repeat": False,
            "timings_count": 2,
        },
    )


def test_decode_signal_event_returns_unknown_without_nec_key() -> None:
    """Test decoded commands without NEC keys return the unknown event type."""
    with _patched_nec_protocol_specs(nec_decode_result=object()):
        event_type, event_data = event_platform._decode_signal_event("lg_tv", _signal())

    assert event_type == "unknown"
    assert event_data["decoder"] == "nec"
    assert event_data["protocol"] == "unknown"
    assert event_data["timings_count"] == 2


def test_decode_signal_event_decodes_nec1_f16_command() -> None:
    """Test an NEC1-f16 full frame is decoded before command matching is added."""
    command = NEC1F16Command(address=0xFB04, function=0xDB, subfunction=0x32)

    with _patched_nec_protocol_specs(
        nec_decode_result=None,
        nec1_f16_decode_result=command,
    ):
        event_type, event_data = event_platform._decode_signal_event(
            "lg_tv",
            _signal(command.get_raw_timings(), modulation=38_000),
        )

    assert event_type == "nec1_f16"
    _assert_event_subset(
        event_data,
        {
            "codeset": "lg_tv",
            "decoder": "nec",
            "protocol": "nec1_f16",
            "decoded": True,
            "matched": False,
            "repeat": False,
            "address": "0xFB04",
            "function": "0xDB",
            "subfunction": "0x32",
        },
    )


def test_decode_signal_event_matches_nec1_f16_library_command() -> None:
    """Test a decoded NEC1-f16 command is matched to the library command name."""
    command = NEC1F16Command(address=0xFB04, function=0xDB, subfunction=0x32)

    with (
        _patched_nec_protocol_specs(
            nec_decode_result=None,
            nec1_f16_decode_result=command,
        ),
        patch.object(
            event_platform,
            "_load_codeset_enum",
            return_value=FakeNEC1F16Code,
        ),
    ):
        event_type, event_data = event_platform._decode_signal_event(
            "lg_tv",
            _signal(),
        )

    assert event_type == "dtv_num_2"
    _assert_event_subset(
        event_data,
        {
            "codeset": "lg_tv",
            "decoder": "nec",
            "protocol": "nec1_f16",
            "decoded": True,
            "matched": True,
            "repeat": False,
            "address": "0xFB04",
            "function": "0xDB",
            "subfunction": "0x32",
            "command_name": "DTV_NUM_2",
        },
    )


def test_decode_signal_event_returns_nec_repeat_with_previous_event() -> None:
    """Test NEC repeat frames include previous decoded command metadata."""
    previous_event = {
        "event_type": "mute",
        "protocol": "nec",
        "address": "0xFB04",
        "command": "0x09",
        "command_name": "MUTE",
    }

    with _patched_nec_protocol_specs(nec_decode_result=None):
        event_type, event_data = event_platform._decode_signal_event(
            "lg_tv",
            _signal([8894, -2250, 529, -10000]),
            previous_decoded_event=previous_event,
        )

    assert event_type == "nec_repeat"
    _assert_event_subset(
        event_data,
        {
            "protocol": "nec",
            "repeat": True,
            "previous_event_type": "mute",
            "previous_protocol": "nec",
            "previous_address": "0xFB04",
            "previous_command": "0x09",
            "previous_command_name": "MUTE",
            "timings_count": 4,
        },
    )


def test_decode_signal_event_returns_nec_repeat_with_previous_nec1_f16_event() -> None:
    """Test NEC repeat frames include previous NEC1-f16 command metadata."""
    previous_event = {
        "event_type": "nec1_f16",
        "protocol": "nec1_f16",
        "address": "0xFB04",
        "function": "0xDB",
        "subfunction": "0x32",
    }

    with _patched_nec_protocol_specs(nec_decode_result=None):
        event_type, event_data = event_platform._decode_signal_event(
            "lg_tv",
            _signal([8894, -2250, 529, -10000]),
            previous_decoded_event=previous_event,
        )

    assert event_type == "nec_repeat"
    assert event_data["protocol"] == "nec1_f16"
    assert event_data["previous_function"] == "0xDB"
    assert event_data["previous_subfunction"] == "0x32"


def test_decode_signal_event_returns_nec_repeat_without_previous_event() -> None:
    """Test standalone NEC repeat frames decode without previous metadata."""
    with _patched_nec_protocol_specs(nec_decode_result=None):
        event_type, event_data = event_platform._decode_signal_event(
            "lg_tv",
            _signal([8894, -2250, 529, -10000]),
        )

    assert event_type == "nec_repeat"
    assert event_data["protocol"] == "nec"
    assert event_data["repeat"] is True
    assert "previous_event_type" not in event_data


def test_with_timing_metadata_includes_nec_debug_data() -> None:
    """Test unknown NEC-like full frames expose timing-derived debug fields."""
    timings = _nec1_f16_timings()
    event_data = event_platform._with_timing_metadata(
        {"protocol": "unknown"},
        _signal(timings),
    )

    assert event_data["timings_count"] == len(timings)
    assert event_data["timings_preview"] == timings[:12]
    assert event_data["nec_frame_candidate"] is True
    assert event_data["nec_bytes"] == ["0x04", "0xFB", "0xDB", "0x32"]
    assert event_data["nec_address_checksum_valid"] is True
    assert event_data["nec_command_checksum_valid"] is False
    assert event_data["nec1_f16_address"] == "0xFB04"
    assert event_data["nec1_f16_function"] == "0xDB"
    assert event_data["nec1_f16_subfunction"] == "0x32"


def test_with_timing_metadata_can_omit_nec_debug_data() -> None:
    """Test NEC timing debug fields can be omitted for non-NEC decoders."""
    event_data = event_platform._with_timing_metadata(
        {"protocol": "unknown"},
        _signal(_nec1_f16_timings()),
        include_nec_debug=False,
    )

    assert event_data["timings_count"] == len(_nec1_f16_timings())
    assert "nec_frame_candidate" not in event_data
    assert "nec_bytes" not in event_data


def test_nec1_f16_command_event_data_requires_subfunction() -> None:
    """Test NEC1-f16 event data requires a decoded subfunction."""
    decoded_command = event_platform.DecodedInfraredCommand(
        protocol=event_platform.PROTOCOL_NEC1_F16,
        address=0xFB04,
        primary=0xDB,
    )

    with pytest.raises(ValueError, match="missing subfunction"):
        event_platform._nec1_f16_command_event_data(decoded_command)


def test_command_match_key_returns_none_for_unknown_protocol() -> None:
    """Test command match keys fail closed for unknown explicit protocols."""
    assert (
        event_platform._command_match_key(
            cast(Command, FakeCommand(1, 2)),
            protocol="missing",
        )
        is None
    )


def test_command_match_key_detects_known_protocol() -> None:
    """Test command match keys can be detected without an explicit protocol."""
    assert event_platform._command_match_key(cast(Command, FakeCommand(1, 2))) == (
        event_platform.PROTOCOL_NEC,
        1,
        2,
        None,
    )


def test_command_match_key_returns_none_without_matching_protocol() -> None:
    """Test command match keys fail closed when no protocol normalizer matches."""
    assert event_platform._command_match_key(cast(Command, object())) is None


def test_load_codeset_enum_returns_none_for_unknown_codeset() -> None:
    """Test unknown codeset ids fail closed before importing modules."""
    assert event_platform._load_codeset_enum("missing") is None


def test_load_codeset_enum_returns_none_for_import_error() -> None:
    """Test missing codeset modules fail closed."""
    with patch.dict(
        event_platform.INFRARED_LIBRARY_CODESETS,
        {
            "broken": SimpleNamespace(
                module="custom_components.universal_remote.missing_codeset",
                enum_class="MissingCode",
            ),
        },
    ):
        assert event_platform._load_codeset_enum("broken") is None


def test_load_codeset_enum_returns_none_for_missing_enum_class() -> None:
    """Test missing enum classes fail closed."""
    with (
        patch.dict(
            event_platform.INFRARED_LIBRARY_CODESETS,
            {
                "broken": SimpleNamespace(
                    module="fake.module",
                    enum_class="MissingCode",
                ),
            },
        ),
        patch.object(event_platform, "import_module", return_value=SimpleNamespace()),
    ):
        assert event_platform._load_codeset_enum("broken") is None


def test_load_codeset_enum_returns_none_for_non_enum_class() -> None:
    """Test non-enum classes fail closed."""
    with (
        patch.dict(
            event_platform.INFRARED_LIBRARY_CODESETS,
            {
                "broken": SimpleNamespace(
                    module="fake.module",
                    enum_class="NotEnum",
                ),
            },
        ),
        patch.object(
            event_platform,
            "import_module",
            return_value=SimpleNamespace(NotEnum=NotEnum),
        ),
    ):
        assert event_platform._load_codeset_enum("broken") is None


def test_event_entity_matched_command_updates_runtime_tuner(hass: HomeAssistant) -> None:
    """Test matched non-repeat received command updates runtime tuner."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id="infrared.test_ir",
        commands={"BS": "38000:9000,4500", "BS_NUM_1": "38000:9000,2250"},
    )
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        receiver_entity_id="infrared.test_receiver",
        codeset_id="lg_tv",
        runtime=runtime,
    )

    with (
        patch(
            "custom_components.universal_remote.event._decode_signal_event",
            return_value=(
                "bs_num_1",
                {
                    "codeset": "lg_tv",
                    "decoder": "nec",
                    "protocol": "nec",
                    "decoded": True,
                    "matched": True,
                    "repeat": False,
                    "command_name": "BS_NUM_1",
                },
            ),
        ),
        patch.object(entity, "_trigger_event"),
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_signal(
            InfraredReceivedSignal(
                timings=[9000, -4500],
                modulation=38000,
            )
        )

    assert runtime.selected_tuner == "BS"


def test_event_entity_matched_cs4k_command_updates_runtime_tuner(
    hass: HomeAssistant,
) -> None:
    """Test matched CS4K received command updates runtime tuner."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id="infrared.test_ir",
        commands={"CS4K": "38000:9000,4500", "CS4K_NUM_2": "38000:9000,2250"},
    )
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        receiver_entity_id="infrared.test_receiver",
        codeset_id="lg_tv",
        runtime=runtime,
    )

    with (
        patch(
            "custom_components.universal_remote.event._decode_signal_event",
            return_value=(
                "cs4k_num_2",
                {
                    "codeset": "lg_tv",
                    "decoder": "nec",
                    "protocol": "nec",
                    "decoded": True,
                    "matched": True,
                    "repeat": False,
                    "command_name": "CS4K_NUM_2",
                },
            ),
        ),
        patch.object(entity, "_trigger_event"),
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_signal(
            InfraredReceivedSignal(
                timings=[9000, -4500],
                modulation=38000,
            )
        )

    assert runtime.selected_tuner == "CS4K"


def test_event_entity_repeat_does_not_update_runtime_tuner(
    hass: HomeAssistant,
) -> None:
    """Test repeat event does not update runtime tuner."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id="infrared.test_ir",
        commands={"BS": "38000:9000,4500", "BS_NUM_1": "38000:9000,2250"},
    )
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        receiver_entity_id="infrared.test_receiver",
        codeset_id="lg_tv",
        runtime=runtime,
    )

    with (
        patch(
            "custom_components.universal_remote.event._decode_signal_event",
            return_value=(
                "nec_repeat",
                {
                    "codeset": "lg_tv",
                    "decoder": "nec",
                    "protocol": "nec",
                    "decoded": False,
                    "matched": False,
                    "repeat": True,
                    "previous_command_name": "BS_NUM_1",
                },
            ),
        ),
        patch.object(entity, "_trigger_event"),
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_signal(
            InfraredReceivedSignal(
                timings=[9000, -2250, 560],
                modulation=38000,
            )
        )

    assert runtime.selected_tuner is None


def test_event_entity_unmatched_command_does_not_update_runtime_tuner(
    hass: HomeAssistant,
) -> None:
    """Test unmatched event does not update runtime tuner."""
    runtime = UniversalRemoteRuntime(
        hass=hass,
        infrared_emitter_id="infrared.test_ir",
        commands={"BS": "38000:9000,4500", "BS_NUM_1": "38000:9000,2250"},
    )
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="living_room_tv",
        remote_name="Living Room TV",
        receiver_entity_id="infrared.test_receiver",
        codeset_id="lg_tv",
        runtime=runtime,
    )

    with (
        patch(
            "custom_components.universal_remote.event._decode_signal_event",
            return_value=(
                "nec",
                {
                    "codeset": "lg_tv",
                    "decoder": "nec",
                    "protocol": "nec",
                    "decoded": True,
                    "matched": False,
                    "repeat": False,
                },
            ),
        ),
        patch.object(entity, "_trigger_event"),
        patch.object(entity, "async_write_ha_state"),
    ):
        entity._handle_signal(
            InfraredReceivedSignal(
                timings=[9000, -4500],
                modulation=38000,
            )
        )

    assert runtime.selected_tuner is None


def test_event_entity_receiver_only_runtime_none_still_triggers_event(
    hass: HomeAssistant,
) -> None:
    """Test event entity still works when no runtime is available."""
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id="receiver_remote",
        remote_name="Receiver Remote",
        receiver_entity_id="infrared.test_receiver",
        codeset_id="lg_tv",
        runtime=None,
    )

    with (
        patch(
            "custom_components.universal_remote.event._decode_signal_event",
            return_value=(
                "bs_num_1",
                {
                    "codeset": "lg_tv",
                    "decoder": "nec",
                    "protocol": "nec",
                    "decoded": True,
                    "matched": True,
                    "repeat": False,
                    "command_name": "BS_NUM_1",
                },
            ),
        ),
        patch.object(entity, "_trigger_event") as trigger_event,
        patch.object(entity, "async_write_ha_state") as write_state,
    ):
        entity._handle_signal(
            InfraredReceivedSignal(
                timings=[9000, -4500],
                modulation=38000,
            )
        )

    trigger_event.assert_called_once()
    write_state.assert_called_once()
