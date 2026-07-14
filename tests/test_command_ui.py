"""Tests for Universal Remote command UI helpers."""

import pytest

from custom_components.universal_remote.command_ui import (
    COMMAND_CATEGORY_APP,
    COMMAND_CATEGORY_AUDIO,
    COMMAND_CATEGORY_CHANNEL,
    COMMAND_CATEGORY_COLOR,
    COMMAND_CATEGORY_INFO,
    COMMAND_CATEGORY_INPUT,
    COMMAND_CATEGORY_NAVIGATION,
    COMMAND_CATEGORY_NUMERIC,
    COMMAND_CATEGORY_OTHER,
    COMMAND_CATEGORY_PLAYBACK,
    COMMAND_CATEGORY_VOLUME,
    command_category,
    command_icon,
    command_is_media_player_source,
    command_label,
    tv_media_player_source_commands,
)
from custom_components.universal_remote.const import TV_SOURCE_COMMAND_MAP


@pytest.mark.parametrize(
    ("command_name", "expected_label"),
    [
        ("HDMI_1", "HDMI 1"),
        ("NUM_1", "Number 1"),
        ("NUM_10", "Number 10"),
        ("BS_NUM_1", "BS Number 1"),
        ("BS4K_NUM_10", "BS4K Number 10"),
        ("CS4K", "CS4K"),
        ("CS4K_NUM_10", "CS4K Number 10"),
        ("DTV_NUM_1", "DTV Number 1"),
        ("SAP", "SAP"),
        ("THREE_DIGIT_INPUT", "Three Digit Input"),
        ("7", "Number 7"),
    ],
)
def test_command_label(command_name: str, expected_label: str) -> None:
    """Test user-facing command labels."""
    assert command_label(command_name) == expected_label


@pytest.mark.parametrize(
    ("command_name", "expected_icon"),
    [
        ("POWER_ON", "mdi:power-on"),
        ("ASPECT", "mdi:aspect-ratio"),
        ("BACK", "mdi:keyboard-backspace"),
        ("OK", "mdi:check"),
        ("HDMI_1", "mdi:video-input-hdmi"),
        ("NUM_1", "mdi:numeric-1"),
        ("NUM_10", "mdi:numeric-0"),
        ("BS_NUM_10", "mdi:numeric-0"),
        ("DTV", "mdi:import"),
        ("DTV_NUM_1", "mdi:numeric-1"),
        ("CS4K", "mdi:import"),
        ("CS4K_NUM_1", "mdi:numeric-1"),
        ("THREE_DIGIT_INPUT", "mdi:import"),
        ("SAP", "mdi:translate"),
        ("SUBTITLE", "mdi:subtitles-outline"),
        ("TEXT", "mdi:text-box-outline"),
        ("DATA", "mdi:database-outline"),
        ("RECORD", "mdi:record"),
        ("REC_LIST", "mdi:playlist-play"),
        ("SETTINGS", "mdi:cog"),
        ("NETFLIX", "mdi:netflix"),
        ("AMAZON", "mdi:movie-open-play-outline"),
        ("HDMI_5", "mdi:import"),
        ("UNKNOWN", "mdi:remote"),
    ],
)
def test_command_icon(command_name: str, expected_icon: str) -> None:
    """Test command icon mapping."""
    assert command_icon(command_name) == expected_icon


@pytest.mark.parametrize(
    ("command_name", "expected_category"),
    [
        ("POWER_ON", "power"),
        ("VOLUME_UP", COMMAND_CATEGORY_VOLUME),
        ("CHANNEL_UP", COMMAND_CATEGORY_CHANNEL),
        ("DTV", COMMAND_CATEGORY_INPUT),
        ("DTV_NUM_1", COMMAND_CATEGORY_NUMERIC),
        ("CS4K", COMMAND_CATEGORY_INPUT),
        ("CS4K_NUM_1", COMMAND_CATEGORY_NUMERIC),
        ("SETTINGS", COMMAND_CATEGORY_NAVIGATION),
        ("RECORD", COMMAND_CATEGORY_PLAYBACK),
        ("RED", COMMAND_CATEGORY_COLOR),
        ("DATA", COMMAND_CATEGORY_INFO),
        ("SAP", COMMAND_CATEGORY_AUDIO),
        ("NETFLIX", COMMAND_CATEGORY_APP),
        ("7", COMMAND_CATEGORY_NUMERIC),
        ("UNKNOWN", COMMAND_CATEGORY_OTHER),
    ],
)
def test_command_category(command_name: str, expected_category: str) -> None:
    """Test command category mapping."""
    assert command_category(command_name) == expected_category


@pytest.mark.parametrize(
    ("command_name", "expected"),
    [
        ("HDMI_1", True),
        ("TV", True),
        ("TV_INPUT", True),
        ("DTV", True),
        ("BS4K", True),
        ("CS4K", True),
        ("INPUT", True),
        ("SOURCE", True),
        ("NEXT_HDMI_INPUT", True),
        ("COMPONENT_INPUT", True),
        ("NETFLIX", True),
        ("AMAZON_PRIME", True),
        ("HULU", True),
        ("BROWSER", True),
        (" input ", True),
        ("hdmi 1", True),
        ("amazon-prime", True),
        ("next hdmi input", True),
        ("THREE_DIGIT_INPUT", False),
        ("VOLUME_UP", False),
    ],
)
def test_command_is_media_player_source(command_name: str, expected: bool) -> None:
    """Test media-player source command detection."""
    assert command_is_media_player_source(command_name) is expected


@pytest.mark.parametrize("command_name", TV_SOURCE_COMMAND_MAP.values())
def test_all_tv_source_map_commands_are_media_player_sources(
    command_name: str,
) -> None:
    """Test every configured TV source-map command is classified as a source."""
    assert command_is_media_player_source(command_name) is True


def test_tv_media_player_source_commands_uses_normalized_command_names() -> None:
    """Test source mapping uses the same normalized lookup as the media player."""
    assert tv_media_player_source_commands(
        {
            "hdmi 1": "first",
            "amazon-prime": "second",
            "next hdmi input": "third",
            "VOLUME_UP": "ignored",
        }
    ) == {
        "Next HDMI input": "next hdmi input",
        "HDMI 1": "hdmi 1",
        "Amazon Prime": "amazon-prime",
    }
