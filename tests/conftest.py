"""Fixtures for the Universal Remote integration tests."""

from collections.abc import Generator
from unittest.mock import patch

import pytest

from custom_components.universal_remote.const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_DEVICE_TYPE,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DEVICE_TYPE_TV,
    DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from pytest_homeassistant_custom_component.common import MockConfigEntry

INFRARED_EMITTER_ID = "infrared.test_ir"
REMOTE_ID = "living_room_tv"
REMOTE_NAME = "Living Room TV"
RAW_COMMAND = "38000:9000,4500,560,560"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield

    
@pytest.fixture
def mock_setup_entry() -> Generator:
    """Mock config entry platform setup."""
    with patch(
        "custom_components.universal_remote.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_reload() -> Generator:
    """Mock config entry reload."""
    with patch(
        "custom_components.universal_remote.config_entries.ConfigEntries.async_reload",
        return_value=None,
    ) as mock_reload:
        yield mock_reload


@pytest.fixture
def infrared_emitter(hass: HomeAssistant) -> str:
    """Register an infrared emitter."""
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "infrared",
        "test",
        "ir",
        suggested_object_id="test_ir",
        original_name="Test IR",
    )
    hass.states.async_set(INFRARED_EMITTER_ID, "on")
    return INFRARED_EMITTER_ID


@pytest.fixture
def config_entry(hass: HomeAssistant, infrared_emitter: str) -> MockConfigEntry:
    """Create a universal remote config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Universal Remote",
        data={
            CONF_REMOTE_ID: REMOTE_ID,
            CONF_REMOTE_NAME: REMOTE_NAME,
            CONF_INFRARED_EMITTER_ID: infrared_emitter,
            CONF_REMOTE_DEVICE_TYPE: DEVICE_TYPE_TV,
        },
        options={
            CONF_REMOTE_COMMANDS: {
                "POWER_ON": RAW_COMMAND,
                "POWER_OFF": RAW_COMMAND,
                "TOGGLE": RAW_COMMAND,
            },
        },
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    return entry
