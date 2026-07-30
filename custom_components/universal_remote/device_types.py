"""Home Assistant device-type helpers backed by the profile registry."""

from homeassistant.helpers import selector

from .const import DEVICE_TYPE_GENERIC
from .profiles import PROFILE_REGISTRY, ProfileRegistry


def device_type_options(
    *,
    include_generic: bool = True,
    profile_registry: ProfileRegistry | None = None,
) -> list[selector.SelectOptionDict]:
    """Return device-type selector options in profile registration order."""
    registry = profile_registry or PROFILE_REGISTRY
    return [
        selector.SelectOptionDict(
            value=profile.device_type,
            label=profile.display_name,
        )
        for profile in registry.device_type_profiles
        if include_generic or profile.device_type != DEVICE_TYPE_GENERIC
    ]


def device_type_label(
    device_type: str,
    *,
    profile_registry: ProfileRegistry | None = None,
) -> str:
    """Return the profile-owned label for one device type."""
    registry = profile_registry or PROFILE_REGISTRY
    return (
        registry.device_type_label(device_type) or device_type.replace("_", " ").title()
    )


def validate_device_type(
    device_type: str,
    *,
    profile_registry: ProfileRegistry | None = None,
) -> bool:
    """Return whether one device type has a registered profile."""
    registry = profile_registry or PROFILE_REGISTRY
    return registry.supports_device_type(device_type)
