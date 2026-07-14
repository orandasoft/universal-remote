"""IR learning candidate helpers for Universal Remote."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from infrared_protocols.commands import Command

from .command import CommandParseError, validate_remote_command_payload
from .pronto import ProntoError, encode_pronto_hex

CANDIDATE_CAPTURED = "captured"
CANDIDATE_NORMALIZED = "normalized"
DEFAULT_LEARN_MODULATION = 38_000


@dataclass(frozen=True, slots=True)
class LearnCandidate:
    """A temporary Pronto HEX candidate produced during IR learning."""

    key: str
    payload: str
    label_key: str
    recommended: bool
    metadata: Mapping[str, Any]


class LearnCandidateError(ValueError):
    """Raised when a learned candidate cannot be generated or validated."""


def normalize_learning_modulation(modulation: int | None) -> tuple[int, bool]:
    """Return a valid modulation and whether it was assumed."""
    if type(modulation) is int and modulation > 0:
        return modulation, False

    return DEFAULT_LEARN_MODULATION, True


def build_captured_candidate(
    timings: Iterable[int],
    modulation: int,
    *,
    modulation_assumed: bool = False,
    recommended: bool = True,
) -> LearnCandidate:
    """Build a captured learned Pronto HEX candidate from received timings."""
    timing_values = list(timings)
    payload = _encode_and_validate_pronto(timing_values, modulation)

    return LearnCandidate(
        key=CANDIDATE_CAPTURED,
        payload=payload,
        label_key=CANDIDATE_CAPTURED,
        recommended=recommended,
        metadata=_candidate_metadata(
            timing_count=len(timing_values),
            modulation=modulation,
            modulation_assumed=modulation_assumed,
        ),
    )


def build_normalized_candidate(
    command: Command,
    fallback_modulation: int,
    *,
    metadata: Mapping[str, Any] | None = None,
    recommended: bool = True,
) -> LearnCandidate:
    """Build a normalized learned Pronto HEX candidate from a decoded command."""
    timing_values = _command_raw_timings(command)
    modulation = _command_modulation(command, fallback_modulation)
    payload = _encode_and_validate_pronto(timing_values, modulation)

    return LearnCandidate(
        key=CANDIDATE_NORMALIZED,
        payload=payload,
        label_key=CANDIDATE_NORMALIZED,
        recommended=recommended,
        metadata=_candidate_metadata(
            timing_count=len(timing_values),
            modulation=modulation,
            modulation_assumed=False,
            extra=metadata,
        ),
    )


def build_learn_candidates(
    timings: Iterable[int],
    modulation: int,
    *,
    modulation_assumed: bool = False,
    normalized_command: Command | None = None,
    normalized_metadata: Mapping[str, Any] | None = None,
) -> tuple[LearnCandidate, ...]:
    """Build captured and optional normalized learned candidates.

    Normalized candidate generation is best-effort. If normalized generation
    fails, the captured candidate remains available.
    """
    timing_values = list(timings)

    if normalized_command is None:
        return (
            build_captured_candidate(
                timing_values,
                modulation,
                modulation_assumed=modulation_assumed,
                recommended=True,
            ),
        )

    captured = build_captured_candidate(
        timing_values,
        modulation,
        modulation_assumed=modulation_assumed,
        recommended=False,
    )

    try:
        normalized = build_normalized_candidate(
            normalized_command,
            modulation,
            metadata=normalized_metadata,
            recommended=True,
        )
    except LearnCandidateError:
        return (
            build_captured_candidate(
                timing_values,
                modulation,
                modulation_assumed=modulation_assumed,
                recommended=True,
            ),
        )

    return captured, normalized


def candidate_by_key(
    candidates: Iterable[LearnCandidate],
    key: str,
) -> LearnCandidate | None:
    """Return a learned candidate by key."""
    for candidate in candidates:
        if candidate.key == key:
            return candidate

    return None


def _encode_and_validate_pronto(timings: Iterable[int], modulation: int) -> str:
    """Encode timings as Pronto HEX and validate with the existing parser."""
    try:
        payload = encode_pronto_hex(timings, modulation)
        validate_remote_command_payload(payload)
    except (ProntoError, CommandParseError) as err:
        raise LearnCandidateError(str(err)) from err

    return payload


def _command_raw_timings(command: Command) -> list[int]:
    """Return raw timings from a decoded command object."""
    get_raw_timings = getattr(command, "get_raw_timings", None)
    if not callable(get_raw_timings):
        raise LearnCandidateError("Decoded command does not expose raw timings")

    try:
        return list(get_raw_timings())
    except (TypeError, ValueError, OverflowError) as err:
        raise LearnCandidateError(
            "Decoded command generated invalid raw timings"
        ) from err


def _command_modulation(command: Command, fallback_modulation: int) -> int:
    """Return command modulation, falling back to capture modulation."""
    command_modulation = getattr(command, "modulation", None)
    if type(command_modulation) is int and command_modulation > 0:
        return command_modulation

    modulation, _assumed = normalize_learning_modulation(fallback_modulation)
    return modulation


def _candidate_metadata(
    *,
    timing_count: int,
    modulation: int,
    modulation_assumed: bool,
    extra: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Return candidate metadata without raw timings or payload data."""
    metadata: dict[str, Any] = {
        "timing_count": timing_count,
        "modulation": modulation,
        "modulation_assumed": modulation_assumed,
    }
    if extra is not None:
        metadata.update(extra)

    metadata.pop("payload", None)
    metadata.pop("timings", None)
    metadata.pop("raw_timings", None)

    return MappingProxyType(metadata)
