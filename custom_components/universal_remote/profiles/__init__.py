"""Device profiles for Universal Remote."""

from .base import (
    CommandPresentation,
    CommandRole,
    DeviceProfile,
    ProfileCapability,
    SourceRule,
)
from .capabilities import (
    CAPABILITY_JAPANESE_TUNER,
    JAPANESE_TUNER_CAPABILITY,
    TunerCapability,
    TunerRule,
)
from .generic import GENERIC_PROFILE, PROFILE_GENERIC
from .registry import (
    CAPABILITY_DEFINITIONS,
    PROFILE_DEFINITIONS,
    PROFILE_REGISTRY,
    ProfileRegistry,
    ProfileRegistryError,
    build_profile_registry,
)
from .resolver import (
    command_is_profile_source,
    profile_role_commands,
    profile_source_commands,
)
from .tv import PROFILE_TV, TV_PROFILE

__all__ = [
    "CAPABILITY_DEFINITIONS",
    "CAPABILITY_JAPANESE_TUNER",
    "GENERIC_PROFILE",
    "JAPANESE_TUNER_CAPABILITY",
    "PROFILE_DEFINITIONS",
    "PROFILE_GENERIC",
    "PROFILE_REGISTRY",
    "PROFILE_TV",
    "TV_PROFILE",
    "CommandPresentation",
    "CommandRole",
    "DeviceProfile",
    "ProfileCapability",
    "ProfileRegistry",
    "ProfileRegistryError",
    "SourceRule",
    "TunerCapability",
    "TunerRule",
    "build_profile_registry",
    "command_is_profile_source",
    "profile_role_commands",
    "profile_source_commands",
]
