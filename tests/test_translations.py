"""Tests for Universal Remote translation integrity."""

import json
from pathlib import Path
from typing import Any

from custom_components.universal_remote.options_flow import (
    LEARN_REVIEW_ACTION_CONTINUE_SAVE,
    LEARN_REVIEW_ACTION_DISCARD,
    LEARN_REVIEW_ACTION_RETRY_CAPTURE,
    LEARN_REVIEW_ACTION_SAVE_ANYWAY,
    LEARN_REVIEW_ACTION_TEST_CAPTURED,
    LEARN_REVIEW_ACTION_TEST_NORMALIZED,
)

_INTEGRATION_DIR = Path(__file__).parents[1] / "custom_components" / "universal_remote"


def _translation(filename: str) -> dict[str, Any]:
    """Load one integration translation file."""
    return json.loads((_INTEGRATION_DIR / filename).read_text(encoding="utf-8"))


def test_english_translation_matches_strings() -> None:
    """Test the checked-in English translation matches strings.json."""
    assert _translation("translations/en.json") == _translation("strings.json")


def test_selector_translations_are_top_level() -> None:
    """Test selector translations use the Home Assistant schema."""
    required_selector_keys = {
        "command_source",
        "import_commands",
        "learn_candidate",
        "learn_decoder",
        "learn_failure_action",
        "learn_overwrite_action",
    }

    for filename in ("strings.json", "translations/en.json"):
        data = _translation(filename)

        assert "selector" not in data["options"]
        assert required_selector_keys <= data["selector"].keys()


def test_learn_command_translation_explains_capture_start() -> None:
    """Test receiver selection explains that Submit starts learning."""
    step = _translation("strings.json")["options"]["step"]["learn_command"]

    assert step["title"] == "Learn Command"
    assert step["description"] == (
        "Select the infrared receiver to use, then click Submit to start learning."
    )
    assert step["data_description"]["infrared_receiver_id"] == (
        "Receiver that will listen for the command."
    )


def test_learn_review_menu_translations_are_complete() -> None:
    """Test every learned-command review action has menu text and help text."""
    step = _translation("strings.json")["options"]["step"]["learn_review"]
    expected_actions = {
        LEARN_REVIEW_ACTION_TEST_CAPTURED,
        LEARN_REVIEW_ACTION_TEST_NORMALIZED,
        LEARN_REVIEW_ACTION_CONTINUE_SAVE,
        LEARN_REVIEW_ACTION_SAVE_ANYWAY,
        LEARN_REVIEW_ACTION_RETRY_CAPTURE,
        LEARN_REVIEW_ACTION_DISCARD,
    }

    assert step["title"] == "Review Learned Command"
    assert step["description"]
    assert set(step["menu_options"]) == expected_actions
    assert set(step["menu_option_descriptions"]) == expected_actions
    assert all(step["menu_options"][action] for action in expected_actions)
    assert all(step["menu_option_descriptions"][action] for action in expected_actions)
