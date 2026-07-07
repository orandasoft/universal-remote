"""IR learning session helpers for Universal Remote."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from homeassistant.components import infrared
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from infrared_protocols.commands import Command

from .const import DOMAIN
from .learn_candidates import (
    DEFAULT_LEARN_MODULATION,
    LearnCandidate,
    build_learn_candidates,
)
from .protocols import (
    PROTOCOL_NEC,
    PROTOCOL_NEC1_F16,
    DecodedInfraredCommand,
    _decode_nec_signal,
    _decode_nec1_f16_signal,
    _format_hex,
    _is_nec_repeat_frame,
    _normalize_nec_command,
    _normalize_nec1_f16_command,
)

MIN_CAPTURE_TIMING_COUNT = 4
MIN_CAPTURE_TOTAL_DURATION_US = 1_000
DEFAULT_LEARN_TIMEOUT = 30.0
LEARN_DECODER_AUTO = "auto"
LEARN_DECODER_NONE = "none"
LEARN_DECODER_NEC = PROTOCOL_NEC
LEARN_DECODER_NEC1_F16 = PROTOCOL_NEC1_F16
LEARN_DECODERS = (
    LEARN_DECODER_AUTO,
    LEARN_DECODER_NONE,
    LEARN_DECODER_NEC,
    LEARN_DECODER_NEC1_F16,
)
_LEARN_RECEIVER_LOCKS = "learn_receiver_locks"
_LEARN_CAPTURE_TOKENS = "learn_capture_tokens"


@dataclass(frozen=True, slots=True)
class LearnCapture:
    """A structurally valid IR signal captured during learning."""

    timings: list[int]
    modulation: int
    modulation_assumed: bool
    timing_count: int
    likely_protocol: str | None = None


@dataclass(frozen=True, slots=True)
class LearnResult:
    """A completed IR learning result with generated Pronto HEX candidates."""

    capture: LearnCapture
    candidates: tuple[LearnCandidate, ...]


class LearnSessionError(Exception):
    """Base class for learning-session failures."""


class LearnSessionReceiverUnavailableError(LearnSessionError):
    """Raised when the selected receiver is unavailable."""


class LearnSessionReceiverBusyError(LearnSessionError):
    """Raised when another learn session is using the receiver."""


class LearnSessionTimeoutError(LearnSessionError):
    """Raised when learning times out before a valid signal is captured."""


class LearnSessionInvalidCaptureError(LearnSessionError):
    """Raised when a received signal is not structurally valid."""


class LearnSessionInvalidDecoderError(LearnSessionError):
    """Raised when an unsupported learning decoder is requested."""


class LearnSessionManager:
    """Manage one-shot IR learning capture sessions."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the learning session manager."""
        self._hass = hass

    async def async_learn_once(
        self,
        receiver_entity_id: str,
        *,
        timeout: float = DEFAULT_LEARN_TIMEOUT,
        decoder: str = LEARN_DECODER_AUTO,
    ) -> LearnResult:
        """Capture one signal and generate learned command candidates."""
        capture = await self.async_capture_once(receiver_entity_id, timeout=timeout)
        return build_learn_result(capture, decoder=decoder)

    async def async_capture_once(
        self,
        receiver_entity_id: str,
        *,
        timeout: float = DEFAULT_LEARN_TIMEOUT,
    ) -> LearnCapture:
        """Capture one structurally valid non-repeat signal from a receiver."""
        if receiver_entity_id not in infrared.async_get_receivers(self._hass):
            raise LearnSessionReceiverUnavailableError

        lock = self._receiver_lock(receiver_entity_id)
        if lock.locked():
            raise LearnSessionReceiverBusyError

        async with lock:
            return await self._async_capture_locked(
                receiver_entity_id,
                timeout=timeout,
            )

    async def _async_capture_locked(
        self,
        receiver_entity_id: str,
        *,
        timeout: float,
    ) -> LearnCapture:
        """Capture one signal while holding the receiver lock."""
        loop = self._hass.loop
        capture_future: asyncio.Future[LearnCapture] = loop.create_future()
        token = object()
        tokens = self._capture_tokens()
        tokens[receiver_entity_id] = token
        unsubscribe: CALLBACK_TYPE | None = None

        @callback
        def _handle_received_signal(signal: InfraredReceivedSignal) -> None:
            """Handle one received signal during the active capture attempt."""
            if tokens.get(receiver_entity_id) is not token:
                return

            if capture_future.done():
                return

            if _is_nec_repeat_frame(signal.timings):
                return

            try:
                capture = _capture_from_signal(signal)
            except LearnSessionInvalidCaptureError:
                return

            capture_future.set_result(capture)

        try:
            unsubscribe = infrared.async_subscribe_receiver(
                self._hass,
                receiver_entity_id,
                _handle_received_signal,
            )
            return await asyncio.wait_for(capture_future, timeout=timeout)
        except TimeoutError as err:
            raise LearnSessionTimeoutError from err
        finally:
            if tokens.get(receiver_entity_id) is token:
                tokens.pop(receiver_entity_id, None)

            if unsubscribe is not None:
                unsubscribe()

            if not capture_future.done():
                capture_future.cancel()

    def _receiver_lock(self, receiver_entity_id: str) -> asyncio.Lock:
        """Return the shared lock for a receiver."""
        locks = self._receiver_locks()
        lock = locks.get(receiver_entity_id)
        if lock is None:
            lock = asyncio.Lock()
            locks[receiver_entity_id] = lock

        return lock

    def _receiver_locks(self) -> dict[str, asyncio.Lock]:
        """Return the shared receiver lock registry."""
        domain_data = self._domain_data()
        locks = domain_data.setdefault(_LEARN_RECEIVER_LOCKS, {})
        return locks

    def _capture_tokens(self) -> dict[str, object]:
        """Return the shared active capture token registry."""
        domain_data = self._domain_data()
        tokens = domain_data.setdefault(_LEARN_CAPTURE_TOKENS, {})
        return tokens

    def _domain_data(self) -> dict[str, Any]:
        """Return Universal Remote hass data."""
        return self._hass.data.setdefault(DOMAIN, {})


def build_learn_result(
    capture: LearnCapture,
    *,
    decoder: str = LEARN_DECODER_AUTO,
) -> LearnResult:
    """Build learned command candidates from a completed capture."""
    normalized_command, normalized_metadata = _normalized_command_for_capture(
        capture,
        decoder=decoder,
    )

    return LearnResult(
        capture=capture,
        candidates=build_learn_candidates(
            capture.timings,
            capture.modulation,
            modulation_assumed=capture.modulation_assumed,
            normalized_command=normalized_command,
            normalized_metadata=normalized_metadata,
        ),
    )


def _normalized_command_for_capture(
    capture: LearnCapture,
    *,
    decoder: str = LEARN_DECODER_AUTO,
) -> tuple[Command | None, dict[str, Any] | None]:
    """Return a normalized decoded command and metadata for a capture."""
    if decoder not in LEARN_DECODERS:
        raise LearnSessionInvalidDecoderError

    if decoder == LEARN_DECODER_NONE:
        return None, None

    signal = InfraredReceivedSignal(capture.timings, modulation=capture.modulation)

    if decoder in (LEARN_DECODER_AUTO, LEARN_DECODER_NEC):
        normalized = _normalized_nec_command(signal)
        if normalized is not None or decoder == LEARN_DECODER_NEC:
            return normalized or (None, None)

    if decoder in (LEARN_DECODER_AUTO, LEARN_DECODER_NEC1_F16):
        normalized = _normalized_nec1_f16_command(signal)
        if normalized is not None or decoder == LEARN_DECODER_NEC1_F16:
            return normalized or (None, None)

    return None, None


def _normalized_nec_command(
    signal: InfraredReceivedSignal,
) -> tuple[Command, dict[str, Any]] | None:
    """Return a normalized NEC command and metadata for a signal."""
    nec_command = _decode_nec_signal(signal)
    if nec_command is None:
        return None

    decoded = _normalize_nec_command(nec_command)
    if decoded is None:
        return None

    return nec_command, _decoded_command_metadata(PROTOCOL_NEC, decoded)


def _normalized_nec1_f16_command(
    signal: InfraredReceivedSignal,
) -> tuple[Command, dict[str, Any]] | None:
    """Return a normalized NEC1-f16 command and metadata for a signal."""
    nec1_f16_command = _decode_nec1_f16_signal(signal)
    if nec1_f16_command is None:
        return None

    decoded = _normalize_nec1_f16_command(nec1_f16_command)
    if decoded is None:
        return None

    return nec1_f16_command, _decoded_command_metadata(PROTOCOL_NEC1_F16, decoded)


def _decoded_command_metadata(
    decoder: str,
    decoded: DecodedInfraredCommand,
) -> dict[str, Any]:
    """Return privacy-safe metadata for a normalized learned command."""
    metadata: dict[str, Any] = {
        "decoder": decoder,
        "protocol": decoded.protocol,
        "address": _format_hex(decoded.address, 4),
        "primary": _format_hex(decoded.primary, 2),
    }
    if decoded.secondary is not None:
        metadata["secondary"] = _format_hex(decoded.secondary, 2)

    return metadata


def _capture_from_signal(signal: InfraredReceivedSignal) -> LearnCapture:
    """Create a learn capture from a received signal after validation."""
    timings = list(signal.timings)
    _validate_capture_timings(timings)

    modulation, modulation_assumed = _capture_modulation(signal.modulation)

    return LearnCapture(
        timings=timings,
        modulation=modulation,
        modulation_assumed=modulation_assumed,
        timing_count=len(timings),
        likely_protocol=_likely_protocol(timings),
    )


def _validate_capture_timings(timings: list[int]) -> None:
    """Validate captured timings before creating a learned signal."""
    if len(timings) < MIN_CAPTURE_TIMING_COUNT:
        raise LearnSessionInvalidCaptureError

    total_duration = 0
    for timing in timings:
        if type(timing) is not int:
            raise LearnSessionInvalidCaptureError

        duration = abs(timing)
        if duration <= 0:
            raise LearnSessionInvalidCaptureError

        total_duration += duration

    if total_duration < MIN_CAPTURE_TOTAL_DURATION_US:
        raise LearnSessionInvalidCaptureError


def _capture_modulation(modulation: int | None) -> tuple[int, bool]:
    """Return capture modulation and whether it was assumed."""
    if type(modulation) is int and modulation > 0:
        return modulation, False

    return DEFAULT_LEARN_MODULATION, True


def _likely_protocol(timings: list[int]) -> str | None:
    """Return an informational protocol guess for captured timings."""
    if _is_nec_repeat_frame(timings):
        return "nec_repeat"

    return None
