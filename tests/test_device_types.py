"""Tests for profile-backed device-type helpers."""

from custom_components.universal_remote.const import DEVICE_TYPE_GENERIC
from custom_components.universal_remote.device_types import (
    device_type_label,
    device_type_options,
    validate_device_type,
)
from custom_components.universal_remote.profiles import (
    GENERIC_PROFILE,
    DeviceProfile,
    build_profile_registry,
)


def test_fake_profile_without_codeset_is_a_supported_device_type() -> None:
    """Test the profile registry, not the codeset registry, owns device types."""
    climate_profile = DeviceProfile(
        profile_id="climate",
        device_type="climate",
        device_type_label="Climate",
        entity_domains=frozenset({"climate"}),
    )
    registry = build_profile_registry((GENERIC_PROFILE, climate_profile))

    assert device_type_options(profile_registry=registry) == [
        {"value": DEVICE_TYPE_GENERIC, "label": "Generic remote"},
        {"value": "climate", "label": "Climate"},
    ]
    assert device_type_options(
        include_generic=False,
        profile_registry=registry,
    ) == [{"value": "climate", "label": "Climate"}]
    assert device_type_label("climate", profile_registry=registry) == "Climate"
    assert device_type_label("av_receiver", profile_registry=registry) == "Av Receiver"
    assert validate_device_type("climate", profile_registry=registry)
    assert not validate_device_type("missing", profile_registry=registry)
