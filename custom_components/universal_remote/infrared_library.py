"""Helpers for generating Universal Remote commands from the infrared library."""

from dataclasses import dataclass
from enum import Enum
from importlib import import_module
import logging
from typing import Final

from homeassistant.helpers import selector

from .command import CommandParseError, validate_remote_command_payload
from .const import DEVICE_TYPE_GENERIC, DEVICE_TYPE_TV
from .pronto import ProntoError, encode_learned_pronto


NO_INFRARED_LIBRARY_CODESET: Final = "__none__"

_LOGGER = logging.getLogger(__name__)
DEVICE_TYPE_LABELS: Final[dict[str, str]] = {
    DEVICE_TYPE_GENERIC: "Generic remote",
    DEVICE_TYPE_TV: "TV",
}


@dataclass(frozen=True)
class InfraredLibraryCodeset:
    """Description of an allowed infrared library codeset."""

    label: str
    module: str
    enum_class: str
    device_type: str | None = None
    receiver_decoder_id: str | None = None


INFRARED_LIBRARY_CODESETS: Final[dict[str, InfraredLibraryCodeset]] = {
    "lg_tv": InfraredLibraryCodeset(
        label="LG TV",
        module="infrared_protocols.codes.lg.tv",
        enum_class="LGTVCode",
        device_type=DEVICE_TYPE_TV,
        receiver_decoder_id="nec",
    ),
    "lg_tv_jp": InfraredLibraryCodeset(
        label="LG TV Japan",
        module="custom_components.universal_remote.lg_tv_jp",
        enum_class="LGTVCodeJP",
        device_type=DEVICE_TYPE_TV,
        receiver_decoder_id="nec",
    ),
    "samsung_tv": InfraredLibraryCodeset(
        label="Samsung TV",
        module="infrared_protocols.codes.samsung.tv",
        enum_class="SamsungTVCode",
        device_type=DEVICE_TYPE_TV,
    ),
    "sharp_aquos_tv": InfraredLibraryCodeset(
        label="Sharp AQUOS TV",
        module="infrared_protocols.codes.sharp.aquos_tv",
        enum_class="SharpAquosTVCode",
        device_type=DEVICE_TYPE_TV,
    ),
    "vizio_tv": InfraredLibraryCodeset(
        label="Vizio TV",
        module="infrared_protocols.codes.vizio.tv",
        enum_class="VizioTVCode",
        device_type=DEVICE_TYPE_TV,
        receiver_decoder_id="nec",
    ),
}


class InfraredLibraryCommandError(Exception):
    """Raised when an infrared library command cannot be generated."""


def infrared_library_codeset_available(codeset_id: str) -> bool:
    """Return whether the infrared library codeset can be loaded."""
    try:
        _load_infrared_library_enum(codeset_id)
    except InfraredLibraryCommandError:
        return False
    return True


def infrared_library_codeset_options(
    *,
    device_type: str | None = None,
    include_none: bool = False,
) -> list[selector.SelectOptionDict]:
    """Build the dropdown list of supported infrared library codesets."""
    options: list[selector.SelectOptionDict] = []
    if include_none:
        options.append(
            selector.SelectOptionDict(
                value=NO_INFRARED_LIBRARY_CODESET,
                label="None",
            )
        )

    options.extend(
        selector.SelectOptionDict(value=codeset_id, label=codeset.label)
        for codeset_id, codeset in INFRARED_LIBRARY_CODESETS.items()
        if device_type is None or codeset.device_type == device_type
    )
    return options


def infrared_library_device_type_options(
    *,
    include_generic: bool = True,
) -> list[selector.SelectOptionDict]:
    """Build the dropdown list of available device types."""
    device_types = sorted(
        {
            codeset.device_type
            for codeset in INFRARED_LIBRARY_CODESETS.values()
            if codeset.device_type is not None
        }
    )

    options: list[selector.SelectOptionDict] = []
    if include_generic:
        options.append(
            selector.SelectOptionDict(
                value=DEVICE_TYPE_GENERIC,
                label=DEVICE_TYPE_LABELS[DEVICE_TYPE_GENERIC],
            )
        )

    options.extend(
        selector.SelectOptionDict(
            value=device_type,
            label=DEVICE_TYPE_LABELS.get(
                device_type,
                device_type.replace("_", " ").title(),
            ),
        )
        for device_type in device_types
    )
    return options


def infrared_library_device_type_label(device_type: str) -> str:
    """Return a user-facing device type label."""
    return DEVICE_TYPE_LABELS.get(device_type, device_type.replace("_", " ").title())


def validate_infrared_library_device_type(device_type: str) -> bool:
    """Return whether a device type is supported."""
    return device_type == DEVICE_TYPE_GENERIC or any(
        codeset.device_type == device_type
        for codeset in INFRARED_LIBRARY_CODESETS.values()
    )


def infrared_library_command_options(
    codeset_id: str,
) -> list[selector.SelectOptionDict]:
    """Build the dropdown list of commands from the library enum."""
    enum_cls = _load_infrared_library_enum(codeset_id)

    return [
        selector.SelectOptionDict(value=member.name, label=member.name)
        for member in enum_cls
    ]


def infrared_library_codeset_label(codeset_id: str) -> str:
    """Return the label for an infrared library codeset."""
    if codeset_id == NO_INFRARED_LIBRARY_CODESET:
        return "None"

    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    return codeset.label if codeset is not None else codeset_id


def infrared_library_codeset_device_type(codeset_id: str) -> str | None:
    """Return the device type for an infrared library codeset."""
    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    return codeset.device_type if codeset is not None else None


def is_infrared_library_codeset_selected(codeset_id: str) -> bool:
    """Return whether a real infrared library codeset is selected."""
    return codeset_id != NO_INFRARED_LIBRARY_CODESET


def validate_infrared_library_codeset(
    codeset_id: str,
    *,
    device_type: str | None = None,
) -> bool:
    """Return whether the codeset is none or a supported infrared library codeset."""
    if codeset_id == NO_INFRARED_LIBRARY_CODESET:
        return True

    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    return codeset is not None and (
        device_type is None or codeset.device_type == device_type
    )


def infrared_library_codeset_supports_receiver(codeset_id: str) -> bool:
    """Return whether a codeset supports received signal decoding."""
    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    return codeset is not None and codeset.receiver_decoder_id is not None


def infrared_library_codeset_receiver_decoder_id(codeset_id: str) -> str | None:
    """Return the receiver decoder id for an infrared library codeset."""
    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    return codeset.receiver_decoder_id if codeset is not None else None


def _load_infrared_library_enum(codeset_id: str) -> type[Enum]:
    """Load an allowed infrared library enum."""
    codeset = INFRARED_LIBRARY_CODESETS.get(codeset_id)
    if codeset is None:
        raise InfraredLibraryCommandError

    try:
        module = import_module(codeset.module)
        enum_cls = getattr(module, codeset.enum_class)
    except (ImportError, AttributeError) as err:
        raise InfraredLibraryCommandError from err

    if not isinstance(enum_cls, type) or not issubclass(enum_cls, Enum):
        raise InfraredLibraryCommandError

    return enum_cls


def generate_pronto_from_library_command(
    codeset_id: str,
    command_name: str,
    repeat_count: int,
) -> str:
    """Generate a Pronto HEX payload from an infrared library command."""
    enum_cls = _load_infrared_library_enum(codeset_id)

    try:
        member = enum_cls.__members__[command_name]
    except KeyError as err:
        _LOGGER.debug(
            "Infrared library command %s was not found in codeset %s",
            command_name,
            codeset_id,
        )
        raise InfraredLibraryCommandError from err

    to_command = getattr(member, "to_command", None)
    if not callable(to_command):
        _LOGGER.debug(
            "Infrared library command %s from codeset %s does not expose to_command",
            command_name,
            codeset_id,
        )
        raise InfraredLibraryCommandError

    try:
        command = to_command(repeat_count=repeat_count)
    except TypeError as err:
        if repeat_count:
            _LOGGER.debug(
                "Infrared library command %s from codeset %s does not support "
                "repeat_count=%s",
                command_name,
                codeset_id,
                repeat_count,
            )
            raise InfraredLibraryCommandError from err
        command = to_command()

    get_raw_timings = getattr(command, "get_raw_timings", None)
    if not callable(get_raw_timings):
        _LOGGER.debug(
            "Infrared library command %s from codeset %s generated %s, which "
            "does not expose get_raw_timings",
            command_name,
            codeset_id,
            type(command).__name__,
        )
        raise InfraredLibraryCommandError

    modulation = getattr(command, "modulation", None)
    if not isinstance(modulation, int) or modulation <= 0:
        _LOGGER.debug(
            "Infrared library command %s from codeset %s generated invalid "
            "modulation: %r",
            command_name,
            codeset_id,
            modulation,
        )
        raise InfraredLibraryCommandError

    try:
        timings = [abs(int(timing)) for timing in get_raw_timings()]
    except (TypeError, ValueError) as err:
        _LOGGER.debug(
            "Infrared library command %s from codeset %s generated invalid raw timings",
            command_name,
            codeset_id,
        )
        raise InfraredLibraryCommandError from err

    try:
        return _timings_to_pronto_hex(timings, modulation)
    except InfraredLibraryCommandError:
        _LOGGER.debug(
            "Infrared library command %s from codeset %s generated timings that "
            "could not be converted to Pronto HEX: modulation=%s, timing_count=%s",
            command_name,
            codeset_id,
            modulation,
            len(timings),
        )
        raise


def generate_commands_from_library_codeset(
    codeset_id: str,
    repeat_count: int = 0,
) -> dict[str, str]:
    """Generate all commands from an infrared library codeset."""
    enum_cls = _load_infrared_library_enum(codeset_id)
    return {
        member.name: generate_pronto_from_library_command(
            codeset_id,
            member.name,
            repeat_count,
        )
        for member in enum_cls
    }


def generate_selected_commands_from_library_codeset(
    codeset_id: str,
    command_names: list[str],
    repeat_count: int = 0,
) -> dict[str, str]:
    """Generate selected commands from an infrared library codeset."""
    return {
        command_name: generate_pronto_from_library_command(
            codeset_id,
            command_name,
            repeat_count,
        )
        for command_name in command_names
    }


def validate_generated_command_payload(command_name: str, command_data: str) -> None:
    """Validate generated infrared command data."""
    try:
        validate_remote_command_payload(command_data)
    except CommandParseError as err:
        _LOGGER.debug(
            "Infrared library command %s generated an unsupported command payload",
            command_name,
            exc_info=True,
        )
        raise InfraredLibraryCommandError from err


def _timings_to_pronto_hex(timings: list[int], modulation: int) -> str:
    """Convert raw timings in microseconds to Pronto HEX."""
    try:
        return encode_learned_pronto(timings, modulation)
    except ProntoError as err:
        raise InfraredLibraryCommandError from err
