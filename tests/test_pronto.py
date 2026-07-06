"""Tests for learned raw Pronto HEX helpers."""

import pytest

from custom_components.universal_remote.pronto import (
    LearnedProntoCode,
    ProntoError,
    decode_learned_pronto,
    encode_learned_pronto,
)


def test_public_api_surface() -> None:
    """Test that pronto.py exposes only the approved public API."""
    from custom_components.universal_remote import pronto

    assert set(pronto.__all__) == {
        "LearnedProntoCode",
        "ProntoError",
        "decode_learned_pronto",
        "encode_learned_pronto",
    }


def test_decode_valid_learned_pronto() -> None:
    """Test decoding learned raw Pronto HEX."""
    decoded = decode_learned_pronto(
        "0000 006D 0002 0000 0152 00AA 0014 0017"
    )

    assert decoded == LearnedProntoCode(
        modulation=38029,
        timings=(8888, 4470, 526, 605),
    )


def test_decode_repeat_only_learned_pronto() -> None:
    """Test decoding a learned Pronto payload with only repeat pairs."""
    decoded = decode_learned_pronto("0000 006D 0000 0001 0014 0017")

    assert decoded.modulation == 38029
    assert decoded.timings == (526, 605)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ("", "Command cannot be empty"),
        (
            "0100 006D 0001 0000 0014 0017",
            "Only learned raw Pronto commands beginning with 0000 are supported",
        ),
        (
            "0000 006D 0001 0000",
            "Pronto command is too short",
        ),
        (
            "0000 0000 0001 0000 0014 0017",
            "Pronto frequency word must be greater than zero",
        ),
        (
            "0000 006D 0001 0000 0014 0000",
            "Pronto timing words must be greater than zero",
        ),
        (
            "0000 006D 0001 0000 0014 ZZZZ",
            "Only learned raw Pronto commands beginning with 0000 are supported",
        ),
    ],
)
def test_decode_rejects_invalid_pronto(payload: str, match: str) -> None:
    """Test invalid learned raw Pronto HEX validation."""
    with pytest.raises(ProntoError, match=match):
        decode_learned_pronto(payload)


def test_decode_rejects_wrong_declared_timing_count() -> None:
    """Test declared timing count validation."""
    with pytest.raises(
        ProntoError,
        match="Pronto command timing word count does not match the declared lengths",
    ):
        decode_learned_pronto("0000 006D 0002 0000 0014 0017")


def test_decode_rejects_zero_declared_pair_count() -> None:
    """Test zero declared pair count validation."""
    with pytest.raises(
        ProntoError,
        match="Pronto command must declare at least one timing pair",
    ):
        decode_learned_pronto("0000 006D 0000 0000 0014 0017")


def test_encode_unsigned_timings() -> None:
    """Test encoding unsigned timings."""
    assert (
        encode_learned_pronto([9000, 4500, 560, 560], 38000)
        == "0000 006D 0002 0000 0156 00AB 0015 0015"
    )


def test_encode_signed_timings() -> None:
    """Test encoding signed timings by converting to absolute durations."""
    assert (
        encode_learned_pronto([9000, -4500, 560, -560], 38000)
        == "0000 006D 0002 0000 0156 00AB 0015 0015"
    )


def test_encode_accepts_iterable_timings() -> None:
    """Test encoding materializes iterable timing input."""
    assert (
        encode_learned_pronto(iter([9000, -4500, 560, -560]), 38000)
        == "0000 006D 0002 0000 0156 00AB 0015 0015"
    )


@pytest.mark.parametrize(
    "timings",
    [
        [],
        [0, 560],
        [True, 560],
        [560.0, 560],
        ["560", 560],
    ],
)
def test_encode_rejects_invalid_timings(timings: list[object]) -> None:
    """Test invalid timing validation."""
    with pytest.raises(ProntoError):
        encode_learned_pronto(timings, 38000)  # type: ignore[arg-type]


@pytest.mark.parametrize("modulation", [0, -1, True, 38000.0, "38000"])
def test_encode_rejects_invalid_modulation(modulation: object) -> None:
    """Test invalid modulation validation."""
    with pytest.raises(ProntoError, match="modulation must be greater than zero"):
        encode_learned_pronto([560, 560], modulation)  # type: ignore[arg-type]


def test_encode_appends_trailing_gap_for_odd_timing_count() -> None:
    """Test odd timing count appends the default trailing gap."""
    payload = encode_learned_pronto([9000, -4500, 560], 38000)
    decoded = decode_learned_pronto(payload)

    assert len(decoded.timings) == 4
    assert decoded.timings[-1] == pytest.approx(100_000, abs=100)


def test_encode_rejects_odd_timing_count_when_gap_disabled() -> None:
    """Test odd timing count without trailing gap is rejected."""
    with pytest.raises(ProntoError, match="timings must contain mark/space pairs"):
        encode_learned_pronto([9000, -4500, 560], 38000, trailing_gap_us=None)


def test_encode_rejects_timing_word_overflow() -> None:
    """Test generated Pronto timing words must fit in 16 bits."""
    with pytest.raises(
        ProntoError,
        match="Pronto timing word exceeds 16-bit Pronto limit",
    ):
        encode_learned_pronto([2_000_000, 560], 38000)


def test_encode_decode_round_trip() -> None:
    """Test encode/decode round trip is approximately equivalent."""
    payload = encode_learned_pronto([9000, 4500, 560, 560], 38000)
    decoded = decode_learned_pronto(payload)

    assert decoded.modulation == pytest.approx(38000, abs=100)
    assert decoded.timings == pytest.approx((9000, 4500, 560, 560), abs=10)


def test_encode_accepts_signed_trailing_gap() -> None:
    """Test custom signed trailing gap is normalized."""
    payload = encode_learned_pronto(
        [9000, -4500, 560],
        38000,
        trailing_gap_us=-50_000,
    )
    decoded = decode_learned_pronto(payload)

    assert len(decoded.timings) == 4
    assert decoded.timings[-1] == pytest.approx(50_000, abs=100)


@pytest.mark.parametrize("trailing_gap_us", [0, True, 50_000.0, "50000"])
def test_encode_rejects_invalid_trailing_gap(trailing_gap_us: object) -> None:
    """Test invalid trailing gap validation."""
    with pytest.raises(ProntoError):
        encode_learned_pronto(
            [9000, -4500, 560],
            38000,
            trailing_gap_us=trailing_gap_us,  # type: ignore[arg-type]
        )


def test_decode_rejects_too_few_pronto_words() -> None:
    """Test Pronto-like payloads with too few words are rejected."""
    with pytest.raises(
        ProntoError,
        match="Only learned raw Pronto commands beginning with 0000 are supported",
    ):
        decode_learned_pronto("0000 006D 0001")


def test_decode_rejects_malformed_hex_word_length() -> None:
    """Test malformed Pronto words are rejected."""
    with pytest.raises(
        ProntoError,
        match="Only learned raw Pronto commands beginning with 0000 are supported",
    ):
        decode_learned_pronto("0000 006D 001 0000 0014 0017")


def test_encode_rejects_frequency_word_overflow() -> None:
    """Test generated Pronto frequency word must fit in 16 bits."""
    with pytest.raises(
        ProntoError,
        match="Pronto frequency word exceeds 16-bit Pronto limit",
    ):
        encode_learned_pronto([560, 560], 1)


def test_encode_rejects_pair_count_overflow() -> None:
    """Test generated Pronto pair count must fit in 16 bits."""
    with pytest.raises(
        ProntoError,
        match="Pronto pair count exceeds 16-bit Pronto limit",
    ):
        encode_learned_pronto([1] * 131_072, 38_000)
