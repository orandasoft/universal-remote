"""Tests for the Universal Remote infrared library helpers."""

from enum import Enum
from unittest.mock import patch

import pytest

from custom_components.universal_remote.const import (
    DEVICE_TYPE_GENERIC,
    DEVICE_TYPE_TV,
)
from custom_components.universal_remote.infrared_library import (
    NO_INFRARED_LIBRARY_CODESET,
    InfraredLibraryCodeset,
    InfraredLibraryCommandError,
    _load_infrared_library_enum,
    _timings_to_pronto_hex,
    generate_commands_from_library_codeset,
    generate_pronto_from_library_command,
    generate_selected_commands_from_library_codeset,
    infrared_library_codeset_available,
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


class _LibraryCommand:
    """Fake infrared library command."""

    modulation = 38000

    def get_raw_timings(self) -> list[int]:
        """Return raw timings."""
        return [9000, -4500, 560, -560]


class _EmptyTimingsCommand:
    """Fake command with no raw timings."""

    modulation = 38000

    def get_raw_timings(self) -> list[int]:
        """Return empty timings."""
        return []


class _NoRawTimingsCommand:
    """Fake command without raw timings."""

    modulation = 38000


class _BadModulationCommand:
    """Fake command with invalid modulation."""

    modulation = 0

    def get_raw_timings(self) -> list[int]:
        """Return raw timings."""
        return [1, 1]


class _BadTimingsCommand:
    """Fake command with invalid timings."""

    modulation = 38000

    def get_raw_timings(self) -> list[str]:
        """Return invalid raw timings."""
        return ["bad"]


class _LibraryEnum(Enum):
    """Fake infrared library enum."""

    POWER = 1
    VOLUME_UP = 2

    def to_command(self, repeat_count: int = 0) -> _LibraryCommand:
        """Return a fake command."""
        return _LibraryCommand()


class _FakeLibraryCode(Enum):
    """Fake infrared library enum for tests."""

    POWER = "power"


class _EmptyTimingsEnum(Enum):
    """Fake infrared library enum that generates empty timings."""

    POWER = 1

    def to_command(self, repeat_count: int = 0) -> _EmptyTimingsCommand:
        """Return a fake command with no timings."""
        return _EmptyTimingsCommand()


class _FallbackLibraryMember:
    """Fake infrared library enum member requiring fallback call style."""

    def to_command(self, **kwargs: object) -> _LibraryCommand:
        """Return a fake command only when called without keyword arguments."""
        if kwargs:
            raise TypeError
        return _LibraryCommand()


class _TypeErrorLibraryMember:
    """Fake infrared library enum member raising TypeError."""

    def to_command(self, **kwargs: object) -> _LibraryCommand:
        """Raise TypeError."""
        raise TypeError


class _NoRawTimingsMember:
    """Fake enum member returning a command without raw timings."""

    def to_command(self, repeat_count: int = 0) -> _NoRawTimingsCommand:
        """Return a command without raw timings."""
        return _NoRawTimingsCommand()


class _BadModulationMember:
    """Fake enum member returning a bad modulation command."""

    def to_command(self, repeat_count: int = 0) -> _BadModulationCommand:
        """Return a command with bad modulation."""
        return _BadModulationCommand()


class _BadTimingsMember:
    """Fake enum member returning bad timings."""

    def to_command(self, repeat_count: int = 0) -> _BadTimingsCommand:
        """Return a command with bad timings."""
        return _BadTimingsCommand()


def _fake_enum(member: object) -> type:
    """Return a fake enum-like object."""
    return type("FakeEnum", (), {"__members__": {"POWER": member}})


def test_infrared_library_codeset_available_handles_load_errors() -> None:
    """Test codeset availability returns false when loading fails."""
    with patch(
        "custom_components.universal_remote.infrared_library."
        "_load_infrared_library_enum",
        side_effect=InfraredLibraryCommandError,
    ):
        assert not infrared_library_codeset_available("lg_tv")


def test_infrared_library_codeset_options_and_device_types() -> None:
    """Test codeset and device type options."""
    codeset_options = infrared_library_codeset_options(
        device_type=DEVICE_TYPE_TV,
        include_none=True,
    )
    all_codeset_options = infrared_library_codeset_options()
    device_type_options = infrared_library_device_type_options(
        include_generic=False,
    )

    expected_codeset_values = {
        "lg_tv",
        "lg_tv_jp",
        "samsung_tv",
        "sharp_aquos_tv",
        "vizio_tv",
    }
    expected_codeset_labels = {
        "LG TV",
        "LG TV Japan",
        "Samsung TV",
        "Sharp AQUOS TV",
        "Vizio TV",
    }

    assert codeset_options[0] == {"value": NO_INFRARED_LIBRARY_CODESET, "label": "None"}
    assert {
        option["value"] for option in codeset_options[1:]
    } == expected_codeset_values
    assert {
        option["label"] for option in codeset_options[1:]
    } == expected_codeset_labels
    assert {
        option["value"] for option in all_codeset_options
    } == expected_codeset_values
    assert device_type_options == [{"value": DEVICE_TYPE_TV, "label": "TV"}]


def test_infrared_library_device_type_options_include_generic() -> None:
    """Test device type options can include Generic."""
    options = infrared_library_device_type_options(include_generic=True)

    assert options[0] == {"value": DEVICE_TYPE_GENERIC, "label": "Generic remote"}
    assert {"value": DEVICE_TYPE_TV, "label": "TV"} in options


def test_infrared_library_codeset_available_returns_true() -> None:
    """Test codeset availability returns true when loading succeeds."""
    with patch(
        "custom_components.universal_remote.infrared_library."
        "_load_infrared_library_enum",
        return_value=_LibraryEnum,
    ):
        assert infrared_library_codeset_available("lg_tv")


def test_infrared_library_codeset_options_include_none() -> None:
    """Test infrared library codeset options can include None."""
    options = infrared_library_codeset_options(include_none=True)

    assert options[0]["value"] == NO_INFRARED_LIBRARY_CODESET
    assert options[0]["label"] == "None"


def test_infrared_library_labels_and_selection_helpers() -> None:
    """Test labels, selected-codeset checks, and device type lookups."""
    assert infrared_library_codeset_label(NO_INFRARED_LIBRARY_CODESET) == "None"
    assert infrared_library_codeset_label("missing") == "missing"
    assert infrared_library_codeset_device_type("lg_tv") == DEVICE_TYPE_TV
    assert infrared_library_codeset_device_type("missing") is None
    assert infrared_library_device_type_label("av_receiver") == "Av Receiver"
    assert is_infrared_library_codeset_selected("lg_tv")
    assert not is_infrared_library_codeset_selected(NO_INFRARED_LIBRARY_CODESET)


def test_validate_infrared_library_device_type() -> None:
    """Test device type validation."""
    assert validate_infrared_library_device_type(DEVICE_TYPE_GENERIC)
    assert validate_infrared_library_device_type(DEVICE_TYPE_TV)
    assert not validate_infrared_library_device_type("av_receiver")


@pytest.mark.parametrize(
    ("codeset_id", "device_type", "expected"),
    [
        (NO_INFRARED_LIBRARY_CODESET, None, True),
        ("lg_tv", None, True),
        ("lg_tv", DEVICE_TYPE_TV, True),
        ("lg_tv", "av_receiver", False),
        ("missing", None, False),
    ],
)
def test_validate_infrared_library_codeset(
    codeset_id: str,
    device_type: str | None,
    expected: bool,
) -> None:
    """Test infrared library codeset validation."""
    assert (
        validate_infrared_library_codeset(
            codeset_id,
            device_type=device_type,
        )
        is expected
    )


def test_infrared_library_command_options() -> None:
    """Test command options generated from a library enum."""
    with patch(
        "custom_components.universal_remote.infrared_library."
        "_load_infrared_library_enum",
        return_value=_LibraryEnum,
    ):
        assert infrared_library_command_options("lg_tv") == [
            {"value": "POWER", "label": "POWER"},
            {"value": "VOLUME_UP", "label": "VOLUME_UP"},
        ]


def test_load_infrared_library_enum_success() -> None:
    """Test successful infrared library enum loading."""
    codesets = {
        "test": InfraredLibraryCodeset(
            label="Test",
            module="test.module",
            enum_class="TestEnum",
        )
    }
    module = type("TestModule", (), {"TestEnum": _FakeLibraryCode})

    with (
        patch(
            "custom_components.universal_remote.infrared_library."
            "INFRARED_LIBRARY_CODESETS",
            codesets,
        ),
        patch(
            "custom_components.universal_remote.infrared_library.import_module",
            return_value=module,
        ),
    ):
        assert _load_infrared_library_enum("test") is _FakeLibraryCode


def test_load_infrared_library_enum_errors() -> None:
    """Test infrared library enum loading error paths."""
    with pytest.raises(InfraredLibraryCommandError):
        _load_infrared_library_enum("missing")

    bad_codesets = {
        "bad": InfraredLibraryCodeset(
            label="Bad",
            module="bad.module",
            enum_class="BadEnum",
        )
    }

    with (
        patch(
            "custom_components.universal_remote.infrared_library."
            "INFRARED_LIBRARY_CODESETS",
            bad_codesets,
        ),
        patch(
            "custom_components.universal_remote.infrared_library.import_module",
            side_effect=ImportError,
        ),
        pytest.raises(InfraredLibraryCommandError),
    ):
        _load_infrared_library_enum("bad")

    module = type("BadModule", (), {"BadEnum": object()})

    with (
        patch(
            "custom_components.universal_remote.infrared_library."
            "INFRARED_LIBRARY_CODESETS",
            bad_codesets,
        ),
        patch(
            "custom_components.universal_remote.infrared_library.import_module",
            return_value=module,
        ),
        pytest.raises(InfraredLibraryCommandError),
    ):
        _load_infrared_library_enum("bad")


def test_generate_pronto_from_library_command() -> None:
    """Test generating Pronto HEX from an infrared library command."""
    with patch(
        "custom_components.universal_remote.infrared_library."
        "_load_infrared_library_enum",
        return_value=_LibraryEnum,
    ):
        result = generate_pronto_from_library_command("lg_tv", "POWER", 1)

    assert result.startswith("0000")
    assert result.split()[2] == "0002"


@pytest.mark.parametrize(
    "enum_member",
    [
        _FallbackLibraryMember(),
        _TypeErrorLibraryMember(),
        object(),
        _NoRawTimingsMember(),
        _BadModulationMember(),
        _BadTimingsMember(),
    ],
)
def test_generate_pronto_from_library_command_errors(enum_member: object) -> None:
    """Test error paths when generating library commands."""
    repeat_count = 0 if isinstance(enum_member, _FallbackLibraryMember) else 1

    with patch(
        "custom_components.universal_remote.infrared_library."
        "_load_infrared_library_enum",
        return_value=_fake_enum(enum_member),
    ):
        if isinstance(enum_member, _FallbackLibraryMember):
            assert generate_pronto_from_library_command("lg_tv", "POWER", 0).startswith(
                "0000"
            )
        else:
            with pytest.raises(InfraredLibraryCommandError):
                generate_pronto_from_library_command("lg_tv", "POWER", repeat_count)

    with (
        patch(
            "custom_components.universal_remote.infrared_library."
            "_load_infrared_library_enum",
            return_value=type("FakeEnum", (), {"__members__": {}}),
        ),
        pytest.raises(InfraredLibraryCommandError),
    ):
        generate_pronto_from_library_command("lg_tv", "MISSING", 0)


def test_generate_pronto_from_library_command_handles_pronto_conversion_error() -> None:
    """Test generated commands that cannot be converted to Pronto HEX."""
    with (
        patch(
            "custom_components.universal_remote.infrared_library."
            "_load_infrared_library_enum",
            return_value=_EmptyTimingsEnum,
        ),
        pytest.raises(InfraredLibraryCommandError),
    ):
        generate_pronto_from_library_command("lg_tv", "POWER", 0)


def test_generate_commands_from_library_codeset() -> None:
    """Test generating all commands from a library codeset."""
    with patch(
        "custom_components.universal_remote.infrared_library."
        "_load_infrared_library_enum",
        return_value=_LibraryEnum,
    ):
        commands = generate_commands_from_library_codeset("lg_tv", repeat_count=1)

    assert set(commands) == {"POWER", "VOLUME_UP"}
    assert all(command.startswith("0000") for command in commands.values())


def test_generate_selected_commands_from_library_codeset() -> None:
    """Test generating selected commands from a library codeset."""
    with patch(
        "custom_components.universal_remote.infrared_library."
        "generate_pronto_from_library_command",
        return_value="0000 006D 0001 0000 0001 0001",
    ) as generate_pronto:
        commands = generate_selected_commands_from_library_codeset(
            "lg_tv",
            ["POWER", "VOLUME_UP"],
            repeat_count=2,
        )

    assert commands == {
        "POWER": "0000 006D 0001 0000 0001 0001",
        "VOLUME_UP": "0000 006D 0001 0000 0001 0001",
    }
    assert [call.args for call in generate_pronto.mock_calls] == [
        ("lg_tv", "POWER", 2),
        ("lg_tv", "VOLUME_UP", 2),
    ]


def test_validate_generated_command_payload_error() -> None:
    """Test invalid generated command data raises an infrared library error."""
    with pytest.raises(InfraredLibraryCommandError):
        validate_generated_command_payload("POWER", "bad")


@pytest.mark.parametrize(
    ("timings", "modulation"),
    [
        ([], 38000),
        ([1, 1], 10**20),
    ],
)
def test_timings_to_pronto_hex_errors(timings: list[int], modulation: int) -> None:
    """Test Pronto conversion errors."""
    with pytest.raises(InfraredLibraryCommandError):
        _timings_to_pronto_hex(timings, modulation)


def test_timings_to_pronto_hex_appends_final_gap_for_odd_timings() -> None:
    """Test Pronto conversion adds a final gap for odd timing counts."""
    result = _timings_to_pronto_hex([9000, 4500, 560], 38000)

    parts = result.split()
    assert parts[:4] == ["0000", "006D", "0002", "0000"]
    assert len(parts) == 8
