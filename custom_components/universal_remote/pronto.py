"""Learned raw Pronto HEX helpers."""

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = [
    "LearnedProntoCode",
    "ProntoError",
    "decode_learned_pronto",
    "encode_learned_pronto",
]


# Pronto learned-code timing unit in microseconds.
_PRONTO_FREQUENCY_REFERENCE_US = 0.241246
_PRONTO_TYPE_LEARNED_RAW = 0x0000
_PRONTO_MAX_WORD = 0xFFFF
_DEFAULT_TRAILING_GAP_US = 100_000


@dataclass(frozen=True, slots=True)
class LearnedProntoCode:
    """Decoded learned raw Pronto HEX code."""

    modulation: int
    timings: tuple[int, ...]


class ProntoError(ValueError):
    """Raised when learned raw Pronto HEX cannot be parsed or generated."""


def decode_learned_pronto(pronto_hex: str) -> LearnedProntoCode:
    """Decode learned raw Pronto HEX into modulation and timings.

    Only learned raw Pronto codes beginning with 0000 are supported. Intro and
    repeat sections are flattened in declared order into one timing sequence.
    """
    command = pronto_hex.strip()
    if not command:
        raise ProntoError("Command cannot be empty")

    words = command.split()
    if not _looks_like_learned_pronto(words):
        raise ProntoError(
            "Only learned raw Pronto commands beginning with 0000 are supported"
        )

    values = [int(word, 16) for word in words]
    if len(values) < 6:
        raise ProntoError("Pronto command is too short")

    frequency_word = values[1]
    once_pairs = values[2]
    repeat_pairs = values[3]
    timing_words = values[4:]
    pair_count = once_pairs + repeat_pairs
    expected_timing_words = pair_count * 2


    if frequency_word <= 0:
        raise ProntoError("Pronto frequency word must be greater than zero")

    if pair_count <= 0:
        raise ProntoError("Pronto command must declare at least one timing pair")

    if len(timing_words) != expected_timing_words:
        raise ProntoError(
            "Pronto command timing word count does not match the declared lengths"
        )

    if any(word <= 0 for word in timing_words):
        raise ProntoError("Pronto timing words must be greater than zero")

    modulation = round(1_000_000 / (frequency_word * _PRONTO_FREQUENCY_REFERENCE_US))
    timings = tuple(
        round(word * frequency_word * _PRONTO_FREQUENCY_REFERENCE_US)
        for word in timing_words
    )

    return LearnedProntoCode(modulation=modulation, timings=timings)


def encode_learned_pronto(
    timings: Iterable[int],
    modulation: int,
    *,
    trailing_gap_us: int | None = _DEFAULT_TRAILING_GAP_US,
) -> str:
    """Encode modulation and raw timings as learned raw Pronto HEX."""
    if type(modulation) is not int or modulation <= 0:
        raise ProntoError("modulation must be greater than zero")

    timing_values = list(timings)
    if not timing_values:
        raise ProntoError("timings cannot be empty")

    normalized_timings = [_normalize_duration(timing) for timing in timing_values]

    if len(normalized_timings) % 2:
        if trailing_gap_us is None:
            raise ProntoError("timings must contain mark/space pairs")
        normalized_timings.append(_normalize_duration(trailing_gap_us))

    frequency_word = round(
        1_000_000 / (modulation * _PRONTO_FREQUENCY_REFERENCE_US)
    )
    if frequency_word <= 0:
        raise ProntoError("Pronto frequency word must be greater than zero")
    if frequency_word > _PRONTO_MAX_WORD:
        raise ProntoError("Pronto frequency word exceeds 16-bit Pronto limit")

    pair_count = len(normalized_timings) // 2
    if pair_count > _PRONTO_MAX_WORD:
        raise ProntoError("Pronto pair count exceeds 16-bit Pronto limit")

    timing_words = [
        _duration_to_pronto_word(duration, frequency_word)
        for duration in normalized_timings
    ]

    values = [
        _PRONTO_TYPE_LEARNED_RAW,
        frequency_word,
        pair_count,
        0x0000,
        *timing_words,
    ]
    return " ".join(f"{value:04X}" for value in values)


def _normalize_duration(duration: int) -> int:
    """Normalize a signed or unsigned timing duration."""
    if type(duration) is not int:
        raise ProntoError("timings must be integers")

    normalized = abs(duration)
    if normalized <= 0:
        raise ProntoError("timings must be greater than zero")

    return normalized


def _duration_to_pronto_word(duration_us: int, frequency_word: int) -> int:
    """Convert one microsecond duration to a Pronto timing word."""
    word = max(
        1,
        round(duration_us / (frequency_word * _PRONTO_FREQUENCY_REFERENCE_US)),
    )
    if word > _PRONTO_MAX_WORD:
        raise ProntoError("Pronto timing word exceeds 16-bit Pronto limit")
    return word


def _looks_like_learned_pronto(words: list[str]) -> bool:
    """Return whether words look like learned raw Pronto HEX."""
    if len(words) < 4:
        return False
    return all(_is_hex_word(word) for word in words) and words[0].lower() == "0000"


def _is_hex_word(word: str) -> bool:
    """Return whether a string is a 16-bit Pronto-style hex word."""
    if len(word) != 4:
        return False

    try:
        int(word, 16)
    except ValueError:
        return False

    return True
