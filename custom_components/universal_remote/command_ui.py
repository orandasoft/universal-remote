"""UI helpers for Universal Remote commands."""

import re
from typing import Final

from .const import TV_SOURCE_COMMAND_MAP

COMMAND_CATEGORY_POWER: Final = "power"
COMMAND_CATEGORY_VOLUME: Final = "volume"
COMMAND_CATEGORY_CHANNEL: Final = "channel"
COMMAND_CATEGORY_NAVIGATION: Final = "navigation"
COMMAND_CATEGORY_INPUT: Final = "input"
COMMAND_CATEGORY_NUMERIC: Final = "numeric"
COMMAND_CATEGORY_PLAYBACK: Final = "playback"
COMMAND_CATEGORY_COLOR: Final = "color"
COMMAND_CATEGORY_INFO: Final = "info"
COMMAND_CATEGORY_AUDIO: Final = "audio"
COMMAND_CATEGORY_APP: Final = "app"
COMMAND_CATEGORY_OTHER: Final = "other"

_NUMBER_COMMAND_RE: Final = re.compile(r"^(?:NUM|NUMBER)_(\d+)$")
_PREFIXED_NUMBER_COMMAND_RE: Final = re.compile(
    r"^(DTV|BS|CS1|CS2|BS4K|CS4K)_(?:NUM|NUMBER)_(\d+)$"
)
_HDMI_COMMAND_RE: Final = re.compile(r"^HDMI_(\d+)$")

_COMMAND_ICONS: Final[dict[str, str]] = {
    "POWER": "mdi:power",
    "POWER_ON": "mdi:power-on",
    "POWER_OFF": "mdi:power-off",
    "POWER_TOGGLE": "mdi:power-cycle",
    "TOGGLE": "mdi:power-cycle",
    "VOLUME_UP": "mdi:volume-plus",
    "VOL_UP": "mdi:volume-plus",
    "VOLUME_DOWN": "mdi:volume-minus",
    "VOL_DOWN": "mdi:volume-minus",
    "MUTE": "mdi:volume-mute",
    "VOLUME_MUTE": "mdi:volume-mute",
    "CHANNEL_UP": "mdi:chevron-up-box",
    "CH_UP": "mdi:chevron-up-box",
    "CHANNEL_DOWN": "mdi:chevron-down-box",
    "CH_DOWN": "mdi:chevron-down-box",
    "NAV_UP": "mdi:arrow-up",
    "UP": "mdi:arrow-up",
    "NAV_DOWN": "mdi:arrow-down",
    "DOWN": "mdi:arrow-down",
    "NAV_LEFT": "mdi:arrow-left",
    "LEFT": "mdi:arrow-left",
    "NAV_RIGHT": "mdi:arrow-right",
    "RIGHT": "mdi:arrow-right",
    "OK": "mdi:check",
    "ENTER": "mdi:keyboard-return",
    "SELECT": "mdi:check",
    "BACK": "mdi:keyboard-backspace",
    "EXIT": "mdi:exit-to-app",
    "HOME": "mdi:home",
    "MENU": "mdi:menu",
    "SETTINGS": "mdi:cog",
    "SETTING": "mdi:cog",
    "SETUP": "mdi:cog",
    "OPTIONS": "mdi:cog",
    "INPUT": "mdi:import",
    "SOURCE": "mdi:import",
    "TV": "mdi:import",
    "DTV": "mdi:import",
    "BS": "mdi:import",
    "CS1": "mdi:import",
    "CS2": "mdi:import",
    "BS4K": "mdi:import",
    "CS4K": "mdi:import",
    "THREE_DIGIT_INPUT": "mdi:import",
    "HDMI_1": "mdi:video-input-hdmi",
    "HDMI_2": "mdi:video-input-hdmi",
    "HDMI_3": "mdi:video-input-hdmi",
    "HDMI_4": "mdi:video-input-hdmi",
    "PLAY": "mdi:play",
    "PAUSE": "mdi:pause",
    "STOP": "mdi:stop",
    "RECORD": "mdi:record",
    "REC": "mdi:record",
    "REC_LIST": "mdi:playlist-play",
    "RECORDING_LIST": "mdi:playlist-play",
    "REWIND": "mdi:rewind",
    "FAST_FORWARD": "mdi:fast-forward",
    "RED": "mdi:alpha-r-circle",
    "GREEN": "mdi:alpha-g-circle",
    "YELLOW": "mdi:alpha-y-circle",
    "BLUE": "mdi:alpha-b-circle",
    "INFO": "mdi:information-outline",
    "DISPLAY": "mdi:information-outline",
    "GUIDE": "mdi:television-guide",
    "EPG": "mdi:television-guide",
    "LIST": "mdi:format-list-bulleted",
    "SAP": "mdi:translate",
    "MTS": "mdi:translate",
    "AUDIO_LANGUAGE": "mdi:translate",
    "LANGUAGE": "mdi:translate",
    "SUBTITLE": "mdi:subtitles-outline",
    "TEXT": "mdi:text-box-outline",
    "DATA": "mdi:database-outline",
    "D_BUTTON": "mdi:database-outline",
    "AMAZON": "mdi:movie-open-play-outline",
    "ASPECT": "mdi:aspect-ratio",
    "PRIME_VIDEO": "mdi:movie-open-play-outline",
    "NETFLIX": "mdi:netflix",
    "STREAMING": "mdi:cast",
}

_ACRONYMS: Final[set[str]] = {
    "BS",
    "BS4K",
    "CS1",
    "CS2",
    "CS4K",
    "DTV",
    "EPG",
    "HDMI",
    "MTS",
    "OK",
    "REC",
    "SAP",
    "TV",
}

_INPUT_COMMANDS: Final[set[str]] = {
    "INPUT",
    "SOURCE",
    "TV",
    "DTV",
    "BS",
    "CS1",
    "CS2",
    "BS4K",
    "CS4K",
    "THREE_DIGIT_INPUT",
}

_APP_COMMANDS: Final[set[str]] = {
    "AMAZON",
    "PRIME_VIDEO",
    "NETFLIX",
    "STREAMING",
}


def command_is_media_player_source(command_name: str) -> bool:
    """Return whether a command should be exposed as a media-player source."""
    return command_name.strip().upper() in TV_SOURCE_COMMAND_MAP.values()


def command_icon(command_name: str) -> str:
    """Return the best icon for a command button."""
    normalized = command_name.upper()
    if normalized in _COMMAND_ICONS:
        return _COMMAND_ICONS[normalized]

    number = _command_number(normalized)
    if number is not None:
        if number == 10:
            return "mdi:numeric-0"
        return f"mdi:numeric-{number}" if 0 <= number <= 9 else "mdi:numeric"

    if _is_input_command(normalized):
        return "mdi:import"

    return "mdi:remote"


def command_label(command_name: str) -> str:
    """Return a user-facing command label."""
    normalized = command_name.strip().upper()

    if match := _PREFIXED_NUMBER_COMMAND_RE.fullmatch(normalized):
        return f"{match.group(1)} Number {match.group(2)}"

    if match := _NUMBER_COMMAND_RE.fullmatch(normalized):
        return f"Number {match.group(1)}"

    if normalized.isdecimal():
        return f"Number {normalized}"

    if match := _HDMI_COMMAND_RE.fullmatch(normalized):
        return f"HDMI {match.group(1)}"

    return " ".join(_label_part(part) for part in normalized.split("_") if part)


def command_category(command_name: str) -> str:
    """Return the UI category for a command name."""
    normalized = command_name.upper()

    if normalized.startswith("POWER") or normalized == "TOGGLE":
        return COMMAND_CATEGORY_POWER
    if normalized.startswith(("VOLUME", "VOL")) or normalized == "MUTE":
        return COMMAND_CATEGORY_VOLUME
    if normalized.startswith(("CHANNEL", "CH")):
        return COMMAND_CATEGORY_CHANNEL
    if _is_input_command(normalized):
        return COMMAND_CATEGORY_INPUT
    if _command_number(normalized) is not None:
        return COMMAND_CATEGORY_NUMERIC
    if normalized in {
        "NAV_UP",
        "NAV_DOWN",
        "NAV_LEFT",
        "NAV_RIGHT",
        "UP",
        "DOWN",
        "LEFT",
        "RIGHT",
        "OK",
        "ENTER",
        "SELECT",
        "BACK",
        "EXIT",
        "HOME",
        "MENU",
        "SETTINGS",
        "SETTING",
        "SETUP",
        "OPTIONS",
    }:
        return COMMAND_CATEGORY_NAVIGATION
    if normalized in {
        "PLAY",
        "PAUSE",
        "STOP",
        "RECORD",
        "REC",
        "REC_LIST",
        "RECORDING_LIST",
        "REWIND",
        "FAST_FORWARD",
    }:
        return COMMAND_CATEGORY_PLAYBACK
    if normalized in {"RED", "GREEN", "YELLOW", "BLUE"}:
        return COMMAND_CATEGORY_COLOR
    if normalized in {
        "INFO",
        "DISPLAY",
        "GUIDE",
        "EPG",
        "SUBTITLE",
        "TEXT",
        "DATA",
        "D_BUTTON",
    }:
        return COMMAND_CATEGORY_INFO
    if normalized in {"SAP", "MTS", "AUDIO_LANGUAGE", "LANGUAGE"}:
        return COMMAND_CATEGORY_AUDIO
    if normalized in _APP_COMMANDS:
        return COMMAND_CATEGORY_APP

    return COMMAND_CATEGORY_OTHER


def _command_number(normalized_command_name: str) -> int | None:
    """Return the number represented by a numeric command name."""
    if normalized_command_name.isdecimal():
        return int(normalized_command_name)

    if match := _NUMBER_COMMAND_RE.fullmatch(normalized_command_name):
        return int(match.group(1))

    if match := _PREFIXED_NUMBER_COMMAND_RE.fullmatch(normalized_command_name):
        return int(match.group(2))

    return None


def _is_input_command(normalized_command_name: str) -> bool:
    """Return whether the command should be treated as an input command."""
    return (
        normalized_command_name in _INPUT_COMMANDS
        or _HDMI_COMMAND_RE.fullmatch(normalized_command_name) is not None
    )


def _label_part(part: str) -> str:
    """Return a display label for one command-name component."""
    if part in _ACRONYMS:
        return part

    return part.capitalize()
