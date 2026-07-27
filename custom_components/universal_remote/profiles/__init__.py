"""Device profiles for Universal Remote."""

from .base import (
    CommandPresentation,
    CommandRole,
    DeviceProfile,
    SourceRule,
)
from .generic import GENERIC_PROFILE, PROFILE_GENERIC
from .registry import (
    PROFILE_DEFINITIONS,
    PROFILE_REGISTRY,
    ProfileRegistry,
    ProfileRegistryError,
    build_profile_registry,
)
from .tv import PROFILE_TV, TV_PROFILE

__all__ = [
    "GENERIC_PROFILE",
    "PROFILE_DEFINITIONS",
    "PROFILE_GENERIC",
    "PROFILE_REGISTRY",
    "PROFILE_TV",
    "TV_PROFILE",
    "CommandPresentation",
    "CommandRole",
    "DeviceProfile",
    "ProfileRegistry",
    "ProfileRegistryError",
    "SourceRule",
    "build_profile_registry",
]
