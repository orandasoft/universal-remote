"""Stable codeset definitions and setup-time bindings."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from .profiles import (
    CAPABILITY_JAPANESE_TUNER,
    PROFILE_REGISTRY,
    PROFILE_TV,
    DeviceProfile,
    ProfileCapability,
    ProfileRegistry,
)
from .protocols.nec import PROTOCOL_NEC
from .protocols.registry import PROTOCOL_REGISTRY, ProtocolRegistry


@dataclass(frozen=True, slots=True)
class CodesetDefinition:
    """Stable metadata binding one infrared-library codeset."""

    codeset_id: str
    label: str
    module: str
    enum_class: str
    profile_id: str
    decoder_family_id: str | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedCodesetDefinition:
    """Validated setup-time codeset bindings."""

    definition: CodesetDefinition
    profile: DeviceProfile
    capabilities: tuple[ProfileCapability, ...]


class CodesetRegistryError(ValueError):
    """Raised when codeset registration is invalid."""


@dataclass(frozen=True, slots=True)
class CodesetRegistry:
    """Validated immutable codeset definitions and bindings."""

    definitions: Mapping[str, CodesetDefinition]
    resolved_definitions: Mapping[str, ResolvedCodesetDefinition]

    def definition_for_id(
        self,
        codeset_id: str,
    ) -> CodesetDefinition | None:
        """Return one codeset definition by stable ID."""
        return self.definitions.get(codeset_id)

    def resolved_for_id(
        self,
        codeset_id: str,
    ) -> ResolvedCodesetDefinition | None:
        """Return validated bindings for one codeset."""
        return self.resolved_definitions.get(codeset_id)


def build_codeset_registry(
    definitions: Iterable[CodesetDefinition],
    *,
    profile_registry: ProfileRegistry = PROFILE_REGISTRY,
    protocol_registry: ProtocolRegistry = PROTOCOL_REGISTRY,
) -> CodesetRegistry:
    """Validate and build an explicit codeset registry."""
    definitions_by_id: dict[str, CodesetDefinition] = {}
    resolved_by_id: dict[str, ResolvedCodesetDefinition] = {}

    for definition in definitions:
        _validate_definition(definition)

        if definition.codeset_id in definitions_by_id:
            raise CodesetRegistryError(f"Duplicate codeset id: {definition.codeset_id}")

        profile = profile_registry.profile_for_id(definition.profile_id)
        if profile is None:
            raise CodesetRegistryError(
                f"Codeset {definition.codeset_id} references "
                f"missing profile: {definition.profile_id}"
            )

        if (
            definition.decoder_family_id is not None
            and definition.decoder_family_id not in protocol_registry.decoder_families
        ):
            raise CodesetRegistryError(
                f"Codeset {definition.codeset_id} references "
                f"missing decoder family: {definition.decoder_family_id}"
            )

        capability_ids = tuple(
            dict.fromkeys(
                (
                    *profile.capabilities,
                    *definition.capabilities,
                )
            )
        )
        missing_capability_ids = tuple(
            capability_id
            for capability_id in capability_ids
            if profile_registry.capability_for_id(capability_id) is None
        )
        if missing_capability_ids:
            missing = ", ".join(missing_capability_ids)
            raise CodesetRegistryError(
                f"Codeset {definition.codeset_id} references "
                f"missing capabilities: {missing}"
            )

        capabilities = tuple(
            profile_registry.capabilities[capability_id]
            for capability_id in capability_ids
        )

        definitions_by_id[definition.codeset_id] = definition
        resolved_by_id[definition.codeset_id] = ResolvedCodesetDefinition(
            definition=definition,
            profile=profile,
            capabilities=capabilities,
        )

    return CodesetRegistry(
        definitions=MappingProxyType(definitions_by_id),
        resolved_definitions=MappingProxyType(resolved_by_id),
    )


def _validate_definition(definition: CodesetDefinition) -> None:
    """Validate one codeset definition."""
    required_fields = {
        "codeset id": definition.codeset_id,
        "label": definition.label,
        "module": definition.module,
        "enum class": definition.enum_class,
        "profile id": definition.profile_id,
    }

    for field_name, value in required_fields.items():
        if not value:
            raise CodesetRegistryError(f"Codeset {field_name} must not be empty")

    if len(definition.capabilities) != len(set(definition.capabilities)):
        raise CodesetRegistryError(
            f"Codeset {definition.codeset_id} contains duplicate capability ids"
        )


LG_TV_CODESET: Final = CodesetDefinition(
    codeset_id="lg_tv",
    label="LG TV",
    module="infrared_protocols.codes.lg.tv",
    enum_class="LGTVCode",
    profile_id=PROFILE_TV,
    decoder_family_id=PROTOCOL_NEC,
)

LG_TV_JP_CODESET: Final = CodesetDefinition(
    codeset_id="lg_tv_jp",
    label="LG TV Japan",
    module="infrared_protocols.codes.lg.tv",
    enum_class="LGTVCodeJP",
    profile_id=PROFILE_TV,
    decoder_family_id=PROTOCOL_NEC,
    capabilities=(CAPABILITY_JAPANESE_TUNER,),
)

SAMSUNG_TV_CODESET: Final = CodesetDefinition(
    codeset_id="samsung_tv",
    label="Samsung TV",
    module="infrared_protocols.codes.samsung.tv",
    enum_class="SamsungTVCode",
    profile_id=PROFILE_TV,
)

SHARP_AQUOS_TV_CODESET: Final = CodesetDefinition(
    codeset_id="sharp_aquos_tv",
    label="Sharp AQUOS TV",
    module="infrared_protocols.codes.sharp.aquos_tv",
    enum_class="SharpAquosTVCode",
    profile_id=PROFILE_TV,
)

VIZIO_TV_CODESET: Final = CodesetDefinition(
    codeset_id="vizio_tv",
    label="Vizio TV",
    module="infrared_protocols.codes.vizio.tv",
    enum_class="VizioTVCode",
    profile_id=PROFILE_TV,
    decoder_family_id=PROTOCOL_NEC,
)

CODESET_DEFINITIONS: Final = (
    LG_TV_CODESET,
    LG_TV_JP_CODESET,
    SAMSUNG_TV_CODESET,
    SHARP_AQUOS_TV_CODESET,
    VIZIO_TV_CODESET,
)

CODESET_REGISTRY: Final = build_codeset_registry(CODESET_DEFINITIONS)
