"""Explicit device-profile and capability registry."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .base import DeviceProfile, ProfileCapability
from .capabilities import JAPANESE_TUNER_CAPABILITY
from .generic import GENERIC_PROFILE
from .tv import TV_PROFILE


class ProfileRegistryError(ValueError):
    """Raised when profile or capability registration is invalid."""


@dataclass(frozen=True, slots=True)
class ProfileRegistry:
    """Validated immutable profile and capability lookup registry."""

    profiles: Mapping[str, DeviceProfile]
    profiles_by_device_type: Mapping[str, DeviceProfile]
    capabilities: Mapping[str, ProfileCapability]

    def profile_for_id(self, profile_id: str) -> DeviceProfile | None:
        """Return one profile by stable profile ID."""
        return self.profiles.get(profile_id)

    def profile_for_device_type(
        self,
        device_type: str,
    ) -> DeviceProfile | None:
        """Return the base profile for one stored device type."""
        return self.profiles_by_device_type.get(device_type)

    def capability_for_id(
        self,
        capability_id: str,
    ) -> ProfileCapability | None:
        """Return one capability by stable capability ID."""
        return self.capabilities.get(capability_id)

    def capabilities_for_profile(
        self,
        profile: DeviceProfile,
    ) -> tuple[ProfileCapability, ...]:
        """Return capabilities declared directly by one profile."""
        return tuple(
            self.capabilities[capability_id] for capability_id in profile.capabilities
        )


def build_profile_registry(
    profiles: Iterable[DeviceProfile],
    capabilities: Iterable[ProfileCapability] = (),
) -> ProfileRegistry:
    """Build and validate one explicit profile and capability registry."""
    capabilities_by_id: dict[str, ProfileCapability] = {}

    for capability in capabilities:
        if not capability.capability_id:
            raise ProfileRegistryError("Capability id must not be empty")

        if capability.capability_id in capabilities_by_id:
            raise ProfileRegistryError(
                f"Duplicate capability id: {capability.capability_id}"
            )

        try:
            capability.validate()
        except ValueError as err:
            raise ProfileRegistryError(str(err)) from err

        capabilities_by_id[capability.capability_id] = capability

    profiles_by_id: dict[str, DeviceProfile] = {}
    profiles_by_device_type: dict[str, DeviceProfile] = {}

    for profile in profiles:
        _validate_profile(profile)

        if profile.profile_id in profiles_by_id:
            raise ProfileRegistryError(f"Duplicate profile id: {profile.profile_id}")

        if profile.device_type in profiles_by_device_type:
            raise ProfileRegistryError(
                f"Duplicate profile device type: {profile.device_type}"
            )

        for capability_id in profile.capabilities:
            if capability_id not in capabilities_by_id:
                raise ProfileRegistryError(
                    f"Profile {profile.profile_id} references "
                    f"missing capability: {capability_id}"
                )

        profiles_by_id[profile.profile_id] = profile
        profiles_by_device_type[profile.device_type] = profile

    return ProfileRegistry(
        profiles=MappingProxyType(profiles_by_id),
        profiles_by_device_type=MappingProxyType(profiles_by_device_type),
        capabilities=MappingProxyType(capabilities_by_id),
    )


def _validate_profile(profile: DeviceProfile) -> None:
    """Validate one profile definition."""
    if not profile.profile_id:
        raise ProfileRegistryError("Profile id must not be empty")
    if not profile.device_type:
        raise ProfileRegistryError(
            f"Profile {profile.profile_id} device type must not be empty"
        )

    _reject_duplicates(
        profile.profile_id,
        "role ids",
        tuple(role.role_id for role in profile.roles),
    )
    _reject_duplicates(
        profile.profile_id,
        "source labels",
        tuple(source.label for source in profile.sources),
    )
    _reject_duplicates(
        profile.profile_id,
        "capability ids",
        profile.capabilities,
    )

    for role in profile.roles:
        if not role.role_id or not role.candidates:
            raise ProfileRegistryError(
                f"Profile {profile.profile_id} contains an invalid role"
            )

    for source in profile.sources:
        if not source.label or not source.candidates:
            raise ProfileRegistryError(
                f"Profile {profile.profile_id} contains an invalid source"
            )


def _reject_duplicates(
    profile_id: str,
    field_name: str,
    values: tuple[str, ...],
) -> None:
    """Reject duplicate values in one ordered profile field."""
    if len(values) != len(set(values)):
        raise ProfileRegistryError(
            f"Profile {profile_id} contains duplicate {field_name}"
        )


PROFILE_DEFINITIONS = (
    GENERIC_PROFILE,
    TV_PROFILE,
)

CAPABILITY_DEFINITIONS = (JAPANESE_TUNER_CAPABILITY,)

PROFILE_REGISTRY = build_profile_registry(
    PROFILE_DEFINITIONS,
    CAPABILITY_DEFINITIONS,
)
