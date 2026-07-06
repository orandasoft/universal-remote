"""Tests for IR learning candidate helpers."""

from typing import Any, cast

import pytest
from infrared_protocols.commands import Command

from custom_components.universal_remote.command import (
    CommandParseError,
    parse_remote_command,
)
from custom_components.universal_remote.learn_candidates import (
    CANDIDATE_CAPTURED,
    CANDIDATE_NORMALIZED,
    DEFAULT_LEARN_MODULATION,
    LearnCandidateError,
    build_captured_candidate,
    build_learn_candidates,
    build_normalized_candidate,
    candidate_by_key,
    normalize_learning_modulation,
)


class FakeCommand:
    """Fake decoded command object."""

    def __init__(
        self,
        timings: list[int],
        *,
        modulation: Any = 38_000,
    ) -> None:
        """Initialize fake command."""
        self.modulation = modulation
        self._timings = timings

    def get_raw_timings(self) -> list[int]:
        """Return fake raw timings."""
        return self._timings


class MissingTimingsCommand:
    """Fake decoded command without get_raw_timings."""


class InvalidTimingsCommand:
    """Fake decoded command with invalid timing output."""

    modulation = 38_000

    def get_raw_timings(self) -> object:
        """Return invalid timings."""
        return object()


def test_normalize_learning_modulation_uses_valid_modulation() -> None:
    """Test valid receiver modulation is used."""
    assert normalize_learning_modulation(40_000) == (40_000, False)


@pytest.mark.parametrize("modulation", [None, 0, -1, True])
def test_normalize_learning_modulation_uses_default_when_missing_or_invalid(
    modulation: object,
) -> None:
    """Test missing or invalid modulation falls back to the learning default."""
    assert normalize_learning_modulation(cast(int | None, modulation)) == (
        DEFAULT_LEARN_MODULATION,
        True,
    )


def test_build_captured_candidate() -> None:
    """Test captured candidate generation."""
    candidate = build_captured_candidate(
        [9000, -4500, 560, -560],
        38_000,
        modulation_assumed=True,
    )

    assert candidate.key == CANDIDATE_CAPTURED
    assert candidate.label_key == CANDIDATE_CAPTURED
    assert candidate.recommended is True
    assert candidate.payload == "0000 006D 0002 0000 0156 00AB 0015 0015"
    assert candidate.metadata["timing_count"] == 4
    assert candidate.metadata["modulation"] == 38_000
    assert candidate.metadata["modulation_assumed"] is True
    assert "timings" not in candidate.metadata
    assert "raw_timings" not in candidate.metadata
    assert "payload" not in candidate.metadata

    parsed = parse_remote_command(candidate.payload)
    assert parsed.modulation == pytest.approx(38_000, abs=100)


def test_build_captured_candidate_rejects_invalid_pronto() -> None:
    """Test invalid captured timings are rejected."""
    with pytest.raises(LearnCandidateError, match="timings must be greater than zero"):
        build_captured_candidate([9000, 0], 38_000)


def test_build_captured_candidate_rejects_invalid_validated_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test payload validation failure is surfaced as candidate failure."""

    def validate_payload(_payload: str) -> None:
        raise CommandParseError("invalid generated payload")

    monkeypatch.setattr(
        "custom_components.universal_remote.learn_candidates."
        "validate_remote_command_payload",
        validate_payload,
    )

    with pytest.raises(LearnCandidateError, match="invalid generated payload"):
        build_captured_candidate([9000, -4500, 560, -560], 38_000)


def test_build_normalized_candidate() -> None:
    """Test normalized candidate generation from a decoded command."""
    candidate = build_normalized_candidate(
        cast(Command, FakeCommand([9000, -4500, 560, -560], modulation=40_000)),
        38_000,
        metadata={"decoder": "nec", "protocol": "nec"},
    )

    assert candidate.key == CANDIDATE_NORMALIZED
    assert candidate.label_key == CANDIDATE_NORMALIZED
    assert candidate.recommended is True
    assert candidate.metadata["timing_count"] == 4
    assert candidate.metadata["modulation"] == 40_000
    assert candidate.metadata["decoder"] == "nec"
    assert candidate.metadata["protocol"] == "nec"
    assert "timings" not in candidate.metadata
    assert "raw_timings" not in candidate.metadata
    assert "payload" not in candidate.metadata

    parsed = parse_remote_command(candidate.payload)
    assert parsed.modulation == pytest.approx(40_000, abs=200)


def test_build_normalized_candidate_uses_fallback_modulation() -> None:
    """Test normalized candidate uses fallback modulation when command has none."""
    candidate = build_normalized_candidate(
        cast(Command, FakeCommand([9000, -4500, 560, -560], modulation=None)),
        38_000,
    )

    parsed = parse_remote_command(candidate.payload)
    assert parsed.modulation == pytest.approx(38_000, abs=100)


def test_build_normalized_candidate_rejects_missing_timings() -> None:
    """Test normalized commands must expose get_raw_timings."""
    with pytest.raises(
        LearnCandidateError,
        match="Decoded command does not expose raw timings",
    ):
        build_normalized_candidate(cast(Command, MissingTimingsCommand()), 38_000)


def test_build_normalized_candidate_rejects_invalid_timings() -> None:
    """Test normalized commands must return iterable timings."""
    with pytest.raises(
        LearnCandidateError,
        match="Decoded command generated invalid raw timings",
    ):
        build_normalized_candidate(cast(Command, InvalidTimingsCommand()), 38_000)


def test_build_learn_candidates_decoder_none_path() -> None:
    """Test candidate generation without normalized command creates captured only."""
    candidates = build_learn_candidates([9000, -4500, 560, -560], 38_000)

    assert len(candidates) == 1
    assert candidates[0].key == CANDIDATE_CAPTURED
    assert candidates[0].recommended is True


def test_build_learn_candidates_with_normalized_candidate() -> None:
    """Test candidate generation with captured and normalized candidates."""
    candidates = build_learn_candidates(
        [9000, -4500, 560, -560],
        38_000,
        normalized_command=cast(
            Command,
            FakeCommand([9000, -4500, 560, -560], modulation=40_000),
        ),
        normalized_metadata={"decoder": "nec"},
    )

    assert [candidate.key for candidate in candidates] == [
        CANDIDATE_CAPTURED,
        CANDIDATE_NORMALIZED,
    ]
    assert candidates[0].recommended is False
    assert candidates[1].recommended is True
    assert candidates[1].metadata["decoder"] == "nec"


def test_build_learn_candidates_keeps_captured_when_normalized_fails() -> None:
    """Test normalized candidate failure does not remove captured candidate."""
    candidates = build_learn_candidates(
        [9000, -4500, 560, -560],
        38_000,
        normalized_command=cast(Command, FakeCommand([0, 560])),
    )

    assert len(candidates) == 1
    assert candidates[0].key == CANDIDATE_CAPTURED
    assert candidates[0].recommended is True


def test_candidate_by_key() -> None:
    """Test looking up candidates by key."""
    candidates = build_learn_candidates(
        [9000, -4500, 560, -560],
        38_000,
        normalized_command=cast(
            Command,
            FakeCommand([9000, -4500, 560, -560], modulation=40_000),
        ),
    )

    assert candidate_by_key(candidates, CANDIDATE_CAPTURED) is candidates[0]
    assert candidate_by_key(candidates, CANDIDATE_NORMALIZED) is candidates[1]
    assert candidate_by_key(candidates, "missing") is None
