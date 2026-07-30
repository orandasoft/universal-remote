"""Device-profile contracts for Universal Remote."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CommandRole:
    """Ordered command-name candidates for one functional role."""

    role_id: str
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceRule:
    """Ordered command-name candidates for one source label."""

    label: str
    candidates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommandPresentation:
    """Optional presentation overrides for one named command."""

    label: str | None = None
    icon: str | None = None
    category: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileCapability:
    """Immutable composable device-profile capability."""

    capability_id: str

    def validate(self) -> None:
        """Validate capability-specific configuration."""

    def presentation(
        self,
        command_name: str,
    ) -> CommandPresentation | None:
        """Return capability-specific presentation for one command."""
        return None


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """Immutable Home Assistant semantics for one device type."""

    profile_id: str
    device_type: str
    device_type_label: str | None = None
    entity_domains: frozenset[str] = frozenset()
    roles: tuple[CommandRole, ...] = ()
    sources: tuple[SourceRule, ...] = ()
    capabilities: tuple[str, ...] = ()
    presentation_overrides: Mapping[str, CommandPresentation] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Freeze presentation overrides supplied through mutable mappings."""
        object.__setattr__(
            self,
            "presentation_overrides",
            MappingProxyType(dict(self.presentation_overrides)),
        )

    @property
    def display_name(self) -> str:
        """Return the user-facing device-type name."""
        return self.device_type_label or self.device_type.replace("_", " ").title()

    def role(self, role_id: str) -> CommandRole | None:
        """Return one role definition by ID."""
        return next(
            (role for role in self.roles if role.role_id == role_id),
            None,
        )

    def presentation(self, command_name: str) -> CommandPresentation | None:
        """Return a command-specific presentation override."""
        return self.presentation_overrides.get(command_name.upper())

    def supports_entity(self, domain: str) -> bool:
        """Return whether this profile enables an entity domain."""
        return domain in self.entity_domains
