"""Tests for Universal Remote event entities."""

from collections.abc import Iterable
from enum import Enum
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from custom_components.universal_remote import event as event_platform
from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_INFRARED_RECEIVER_ID,
    CONF_REMOTE_CODESET,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_TV,
    DOMAIN,
    ISSUE_LINKED_INFRARED_RECEIVER_MISSING,
)
from homeassistant.components.infrared import InfraredReceivedSignal
from infrared_protocols.commands.nec import NECCommand
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from pytest_homeassistant_custom_component.common import MockConfigEntry

INFRARED_RECEIVER_ID = "infrared.test_receiver"
REMOTE_ID = "living_room_receiver"
REMOTE_NAME = "Living Room Receiver"


class FakeCommand:
    """Fake infrared protocol command."""

    def __init__(self, address: int, command: int) -> None:
        """Initialize a fake command."""
        self.address = address
        self.command = command


class FakeCode(Enum):
    """Fake infrared library enum."""

    POWER = (1, 2)
    VOLUME_UP = (1, 3)

    def to_command(self) -> FakeCommand:
        """Return the fake protocol command for this enum member."""
        return FakeCommand(*self.value)


class RepeatCode(Enum):
    """Fake enum whose to_command requires a repeat_count."""

    POWER = (1, 2)

    def to_command(self, repeat_count: int) -> FakeCommand:
        """Return the fake protocol command for this enum member."""
        return FakeCommand(*self.value)


class TypeErrorCode(Enum):
    """Fake enum whose to_command is not usable."""

    BROKEN = "broken"

    def to_command(self, repeat_count: int | None = None) -> FakeCommand:
        """Raise TypeError for every call style."""
        raise TypeError


class BrokenCode(Enum):
    """Fake enum without a to_command method."""

    BROKEN = "broken"


def _receiver_entry(*, codeset_id: str = "lg_tv") -> MockConfigEntry:
    """Create a receiver-only config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_INFRARED_RECEIVER_ID: INFRARED_RECEIVER_ID,
            CONF_REMOTE_CODESET: codeset_id,
        },
        options={},
        unique_id=REMOTE_ID,
    )


def _register_receiver_entity(hass: HomeAssistant) -> None:
    """Register the linked infrared receiver entity."""
    entity_registry = er.async_get(hass)
    receiver_entry = entity_registry.async_get_or_create(
        "infrared",
        "test",
        "test_receiver",
        suggested_object_id="test_receiver",
    )
    assert receiver_entry.entity_id == INFRARED_RECEIVER_ID


def test_cleanup_stale_received_command_event_entities(
    hass: HomeAssistant,
) -> None:
    """Test stale received-command event registry entries are removed."""
    entry = _receiver_entry()
    entry.add_to_hass(hass)
    entity_registry = er.async_get(hass)
    stale_entry = entity_registry.async_get_or_create(
        "event",
        DOMAIN,
        event_platform.event_unique_id("stale_receiver"),
        suggested_object_id="stale_received_command",
        config_entry=entry,
    )

    event_platform.cleanup_stale_received_command_event_entities(
        hass,
        cast(ConfigEntry, entry),
        {event_platform.event_unique_id(REMOTE_ID)},
    )

    assert entity_registry.async_get(stale_entry.entity_id) is None


async def test_async_setup_entry_adds_event_entity(
    hass: HomeAssistant,
) -> None:
    """Test setup adds a received command event entity."""
    entry = _receiver_entry()
    _register_receiver_entity(hass)
    added_entities: list[Entity] = []

    def add_entities(
        entities: Iterable[Entity],
        update_before_add: bool = False,
    ) -> None:
        """Add entities to the test list."""
        added_entities.extend(entities)

    with (
        patch.object(
            event_platform,
            "_event_types_for_codeset",
            return_value=["power", "unknown", "volume_up"],
        ),
        patch(
            "custom_components.universal_remote.event."
            "infrared.async_get_receivers",
            return_value=[INFRARED_RECEIVER_ID],
        ),
    ):
        await event_platform.async_setup_entry(
            hass,
            cast(ConfigEntry, entry),
            cast(AddEntitiesCallback, add_entities),
        )

    assert len(added_entities) == 1
    entity = added_entities[0]
    assert isinstance(entity, event_platform.UniversalRemoteReceivedCommandEventEntity)
    assert entity.unique_id == f"{REMOTE_ID}_received_command"
    assert entity.event_types == ["power", "unknown", "volume_up"]


async def test_async_setup_entry_creates_repair_issue_when_receiver_missing(
    hass: HomeAssistant,
) -> None:
    """Test setup creates a repair issue when the receiver is missing."""
    entry = _receiver_entry()
    added_entities: list[Entity] = []

    def add_entities(
        entities: Iterable[Entity],
        update_before_add: bool = False,
    ) -> None:
        """Add entities to the test list."""
        added_entities.extend(entities)

    await event_platform.async_setup_entry(
        hass,
        cast(ConfigEntry, entry),
        cast(AddEntitiesCallback, add_entities),
    )

    assert not added_entities

    issue_registry = ir.async_get(hass)
    issue = issue_registry.async_get_issue(
        DOMAIN,
        f"{ISSUE_LINKED_INFRARED_RECEIVER_MISSING}_{REMOTE_ID}",
    )
    assert issue is not None
    assert issue.translation_key == ISSUE_LINKED_INFRARED_RECEIVER_MISSING
    assert issue.translation_placeholders == {
        "remote_name": REMOTE_NAME,
        "infrared_receiver_id": INFRARED_RECEIVER_ID,
    }


async def test_async_setup_entry_ignores_entry_without_receiver(
    hass: HomeAssistant,
) -> None:
    """Test setup does not add event entities when no receiver is configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={},
        unique_id=REMOTE_ID,
    )
    added_entities: list[Entity] = []

    def add_entities(
        entities: Iterable[Entity],
        update_before_add: bool = False,
    ) -> None:
        """Add entities to the test list."""
        added_entities.extend(entities)

    await event_platform.async_setup_entry(
        hass,
        cast(ConfigEntry, entry),
        cast(AddEntitiesCallback, add_entities),
    )

    assert not added_entities


async def test_async_setup_entry_ignores_entry_without_receiver_but_with_emitter(
    hass: HomeAssistant,
) -> None:
    """Test setup does not add event entities for emitter-only entries."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=REMOTE_NAME,
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
            CONF_INFRARED_EMITTER_ID: "infrared.test_emitter",
        },
        options={},
        unique_id=REMOTE_ID,
    )
    added_entities: list[Entity] = []

    def add_entities(
        entities: Iterable[Entity],
        update_before_add: bool = False,
    ) -> None:
        """Add entities to the test list."""
        added_entities.extend(entities)

    await event_platform.async_setup_entry(
        hass,
        cast(ConfigEntry, entry),
        cast(AddEntitiesCallback, add_entities),
    )

    assert not added_entities


def test_event_entity_handles_received_signal() -> None:
    """Test received infrared signals trigger event entity events."""
    entity = event_platform.UniversalRemoteReceivedCommandEventEntity(
        remote_id=REMOTE_ID,
        remote_name=REMOTE_NAME,
        receiver_entity_id=INFRARED_RECEIVER_ID,
        codeset_id="lg_tv",
    )
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with (
        patch.object(
            event_platform,
            "_decode_signal_event_type",
            return_value="power",
        ),
        patch.object(entity, "_trigger_event") as mock_trigger_event,
        patch.object(entity, "async_write_ha_state") as mock_write_state,
    ):
        entity._handle_signal(signal)

    mock_trigger_event.assert_called_once_with("power")
    mock_write_state.assert_called_once_with()


def test_event_types_for_codeset() -> None:
    """Test event types are generated from the selected codeset."""
    with patch.object(event_platform, "_load_codeset_enum", return_value=FakeCode):
        assert event_platform._event_types_for_codeset("lg_tv") == [
            "power",
            "unknown",
            "volume_up",
        ]


def test_event_types_for_unknown_codeset() -> None:
    """Test unknown is exposed when the codeset cannot be loaded."""
    assert event_platform._event_types_for_codeset("missing") == ["unknown"]


def test_decode_signal_event_type_matches_library_command() -> None:
    """Test a decoded NEC command is matched to the library command name."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with (
        patch.object(
            event_platform,
            "_decode_nec_signal",
            return_value=FakeCommand(1, 2),
        ),
        patch.object(event_platform, "_load_codeset_enum", return_value=FakeCode),
    ):
        assert event_platform._decode_signal_event_type("lg_tv", signal) == "power"


def test_decode_signal_event_type_returns_unknown_for_unmatched_command() -> None:
    """Test unmatched received commands return the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with (
        patch.object(
            event_platform,
            "_decode_nec_signal",
            return_value=FakeCommand(9, 9),
        ),
        patch.object(event_platform, "_load_codeset_enum", return_value=FakeCode),
    ):
        assert event_platform._decode_signal_event_type("lg_tv", signal) == "unknown"


def test_decode_signal_event_type_returns_unknown_for_unsupported_codeset() -> None:
    """Test unsupported receiver codesets return the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    assert event_platform._decode_signal_event_type("samsung_tv", signal) == "unknown"


def test_decode_signal_event_type_returns_unknown_without_codeset() -> None:
    """Test missing library codesets return the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    assert event_platform._decode_signal_event_type("none", signal) == "unknown"


def test_library_member_to_command_handles_missing_to_command() -> None:
    """Test invalid library members are ignored."""
    assert event_platform._library_member_to_command(BrokenCode.BROKEN) is None


def test_nec_command_key_handles_invalid_command() -> None:
    """Test invalid NEC-like commands do not produce a match key."""
    assert event_platform._nec_command_key(object()) is None


def test_decode_signal_event_type_returns_unknown_for_no_library_codeset() -> None:
    """Test the no-library sentinel returns the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    assert (
        event_platform._decode_signal_event_type(
            event_platform.NO_INFRARED_LIBRARY_CODESET,
            signal,
        )
        == "unknown"
    )


def test_decode_signal_event_type_returns_unknown_when_decode_fails() -> None:
    """Test undecodable NEC signals return the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with patch.object(event_platform, "_decode_nec_signal", return_value=None):
        assert event_platform._decode_signal_event_type("lg_tv", signal) == "unknown"


def test_decode_signal_event_type_returns_unknown_without_nec_key() -> None:
    """Test decoded commands without NEC keys return the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with patch.object(event_platform, "_decode_nec_signal", return_value=object()):
        assert event_platform._decode_signal_event_type("lg_tv", signal) == "unknown"


def test_decode_signal_event_type_returns_unknown_without_enum() -> None:
    """Test missing library enums return the unknown event type."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with (
        patch.object(
            event_platform,
            "_decode_nec_signal",
            return_value=FakeCommand(1, 2),
        ),
        patch.object(event_platform, "_load_codeset_enum", return_value=None),
    ):
        assert event_platform._decode_signal_event_type("lg_tv", signal) == "unknown"


def test_decode_signal_event_type_skips_invalid_library_command() -> None:
    """Test enum members without usable commands are ignored."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with (
        patch.object(
            event_platform,
            "_decode_nec_signal",
            return_value=FakeCommand(1, 2),
        ),
        patch.object(event_platform, "_load_codeset_enum", return_value=BrokenCode),
    ):
        assert event_platform._decode_signal_event_type("lg_tv", signal) == "unknown"


def test_decode_nec_signal_uses_modulation() -> None:
    """Test NEC signals are decoded with modulation when available."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )
    command = cast(NECCommand, FakeCommand(1, 2))

    with patch.object(
        event_platform.NECCommand,
        "from_raw_timings",
        return_value=command,
    ) as mock_from_raw_timings:
        assert event_platform._decode_nec_signal(signal) is command

    mock_from_raw_timings.assert_called_once_with([1, 2, 3], modulation=38000)


def test_decode_nec_signal_falls_back_without_modulation() -> None:
    """Test NEC decode falls back when modulation is unsupported."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )
    command = cast(NECCommand, FakeCommand(1, 2))

    with patch.object(
        event_platform.NECCommand,
        "from_raw_timings",
        side_effect=[TypeError, command],
    ) as mock_from_raw_timings:
        assert event_platform._decode_nec_signal(signal) is command

    mock_from_raw_timings.assert_any_call([1, 2, 3], modulation=38000)
    mock_from_raw_timings.assert_any_call([1, 2, 3])


def test_decode_nec_signal_returns_none_when_fallback_fails() -> None:
    """Test failed NEC decode fallback returns None."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with patch.object(
        event_platform.NECCommand,
        "from_raw_timings",
        side_effect=[TypeError, ValueError],
    ):
        assert event_platform._decode_nec_signal(signal) is None


def test_decode_nec_signal_returns_none_for_value_error() -> None:
    """Test failed NEC decode returns None."""
    signal = cast(
        InfraredReceivedSignal,
        SimpleNamespace(timings=[1, 2, 3], modulation=38000),
    )

    with patch.object(
        event_platform.NECCommand,
        "from_raw_timings",
        side_effect=ValueError,
    ):
        assert event_platform._decode_nec_signal(signal) is None


def test_library_member_to_command_retries_with_repeat_count() -> None:
    """Test library members that require repeat_count are supported."""
    command = event_platform._library_member_to_command(RepeatCode.POWER)

    assert event_platform._nec_command_key(command) == (1, 2)


def test_library_member_to_command_handles_unusable_to_command() -> None:
    """Test unusable to_command methods are ignored."""
    assert event_platform._library_member_to_command(TypeErrorCode.BROKEN) is None


def test_load_codeset_enum_handles_import_error() -> None:
    """Test import failures return None."""
    with patch.object(event_platform, "import_module", side_effect=ImportError):
        assert event_platform._load_codeset_enum("lg_tv") is None


def test_load_codeset_enum_handles_missing_enum_class() -> None:
    """Test missing enum classes return None."""
    with patch.object(event_platform, "import_module", return_value=SimpleNamespace()):
        assert event_platform._load_codeset_enum("lg_tv") is None


def test_load_codeset_enum_handles_non_enum_class() -> None:
    """Test non-enum classes return None."""

    class NotEnum:
        """Fake class that is not an enum."""

    with patch.object(
        event_platform,
        "import_module",
        return_value=SimpleNamespace(LGTVCode=NotEnum),
    ):
        assert event_platform._load_codeset_enum("lg_tv") is None
