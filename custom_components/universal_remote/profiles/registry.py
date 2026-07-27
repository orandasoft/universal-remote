"""Explicit device-profile registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .base import DeviceProfile
from .generic import GENERIC_PROFILE
from .tv import TV_PROFILE


class ProfileRegistryError(ValueError):
    """Raised when device-profile registration is invalid."""


@dataclass(frozen=True, slots=True)
class ProfileRegistry:
    """Validated immutable device-profile lookup registry."""

    profiles: Mapping[str, DeviceProfile]
    profiles_by_device_type: Mapping[str, DeviceProfile]

    def profile_for_id(self, profile_id: str) -> DeviceProfile | None:
        """Return one profile by stable profile ID."""
        return self.profiles.get(profile_id)

    def profile_for_device_type(
        self,
        device_type: str,
    ) -> DeviceProfile | None:
        """Return the base profile for one stored device type."""
        return self.profiles_by_device_type.get(device_type)


def build_profile_registry(
    profiles: Iterable[DeviceProfile],
) -> ProfileRegistry:
    """Build and validate one explicit profile registry."""
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

        profiles_by_id[profile.profile_id] = profile
        profiles_by_device_type[profile.device_type] = profile

    return ProfileRegistry(
        profiles=MappingProxyType(profiles_by_id),
        profiles_by_device_type=MappingProxyType(profiles_by_device_type),
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

PROFILE_REGISTRY = build_profile_registry(PROFILE_DEFINITIONS)
