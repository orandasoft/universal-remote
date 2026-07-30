"""Setup-time resolution of remote profiles, codesets, and capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .codesets import (
    CODESET_REGISTRY,
    CodesetDefinition,
    CodesetRegistry,
)
from .const import DEVICE_TYPE_GENERIC
from .profiles.base import (
    CommandPresentation,
    DeviceProfile,
    ProfileCapability,
)
from .profiles.registry import PROFILE_REGISTRY, ProfileRegistry
from .protocols.base import CommandMatchKey, ReceiveProtocolHandler


@dataclass(frozen=True, slots=True)
class ResolvedReceiverModel:
    """Immutable receive-side bindings for one configured remote."""

    codeset_id: str
    decoder_family_id: str | None
    handlers: tuple[ReceiveProtocolHandler, ...]
    match_maps: Mapping[str, Mapping[CommandMatchKey, str]]
    event_types: tuple[str, ...]

    def __post_init__(self) -> None:
        """Freeze protocol match maps supplied through mutable mappings."""
        object.__setattr__(
            self,
            "match_maps",
            MappingProxyType(
                {
                    protocol_id: MappingProxyType(dict(match_map))
                    for protocol_id, match_map in self.match_maps.items()
                }
            ),
        )

    def match_map_for_protocol(
        self,
        protocol_id: str,
    ) -> Mapping[CommandMatchKey, str]:
        """Return the immutable command-name match map for one protocol."""
        return self.match_maps.get(protocol_id, MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class ResolvedRemoteProfile:
    """Resolved semantic model for one configured remote."""

    profile: DeviceProfile
    codeset: CodesetDefinition | None
    capabilities: tuple[ProfileCapability, ...]

    def capability_for_id(
        self,
        capability_id: str,
    ) -> ProfileCapability | None:
        """Return one resolved capability by stable ID."""
        return next(
            (
                capability
                for capability in self.capabilities
                if capability.capability_id == capability_id
            ),
            None,
        )

    def presentation(
        self,
        command_name: str,
    ) -> CommandPresentation | None:
        """Return merged profile and capability presentation."""
        presentations = (
            self.profile.presentation(command_name),
            *(
                capability.presentation(command_name)
                for capability in self.capabilities
            ),
        )

        label: str | None = None
        icon: str | None = None
        category: str | None = None
        matched = False

        for presentation in presentations:
            if presentation is None:
                continue

            matched = True

            if label is None:
                label = presentation.label
            if icon is None:
                icon = presentation.icon
            if category is None:
                category = presentation.category

        if not matched:
            return None

        return CommandPresentation(
            label=label,
            icon=icon,
            category=category,
        )


def resolve_remote_profile(
    device_type: str | None,
    codeset_id: str | None = None,
    *,
    profile_registry: ProfileRegistry = PROFILE_REGISTRY,
    codeset_registry: CodesetRegistry = CODESET_REGISTRY,
) -> ResolvedRemoteProfile | None:
    """Resolve one stored device type and optional codeset.

    Existing configuration precedence is preserved:

    - a valid codeset supplies its profile when the stored type is absent,
      invalid, or generic;
    - a matching explicit profile retains the codeset;
    - a conflicting explicit non-generic profile discards the codeset;
    - an unknown codeset is ignored;
    - an absent or invalid profile falls back to the generic profile.
    """
    stored_profile = (
        profile_registry.profile_for_device_type(device_type)
        if isinstance(device_type, str) and device_type
        else None
    )
    resolved_codeset = (
        codeset_registry.resolved_for_id(codeset_id)
        if isinstance(codeset_id, str) and codeset_id
        else None
    )

    if resolved_codeset is not None and (
        stored_profile is None
        or stored_profile.device_type == DEVICE_TYPE_GENERIC
        or stored_profile.profile_id == resolved_codeset.profile.profile_id
    ):
        return ResolvedRemoteProfile(
            profile=resolved_codeset.profile,
            codeset=resolved_codeset.definition,
            capabilities=resolved_codeset.capabilities,
        )

    profile = stored_profile or profile_registry.profile_for_device_type(
        DEVICE_TYPE_GENERIC
    )
    if profile is None:
        return None

    return ResolvedRemoteProfile(
        profile=profile,
        codeset=None,
        capabilities=profile_registry.capabilities_for_profile(profile),
    )
