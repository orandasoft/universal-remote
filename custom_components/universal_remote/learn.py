"""IR learning session helpers for Universal Remote."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from homeassistant.components import infrared
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from infrared_protocols.commands import Command

from .const import DOMAIN
from .helpers import linked_entity_is_available
from .learn_candidates import (
    DEFAULT_LEARN_MODULATION,
    LearnCandidate,
    build_learn_candidates,
)
from .protocols.base import ReceiveProtocolHandler
from .protocols.registry import PROTOCOL_REGISTRY

MIN_CAPTURE_TIMING_COUNT = 4
MIN_CAPTURE_TOTAL_DURATION_US = 1_000
DEFAULT_LEARN_TIMEOUT = 30.0
LEARN_DECODER_AUTO = "auto"
LEARN_DECODER_NONE = "none"

# Compatibility aliases retained for stored flow state and external imports.
# Concrete learning support is discovered from PROTOCOL_REGISTRY.
LEARN_DECODER_NEC = "nec"
LEARN_DECODER_NEC1_F16 = "nec1_f16"


@dataclass(frozen=True, slots=True)
class LearnDecoderDefinition:
    """One user-facing learning decoder option."""

    key: str
    label_key: str
    fallback_label: str


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
        if not self._receiver_is_available(receiver_entity_id):
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

            if _repeat_event_type(signal) is not None:
                return

            try:
                capture = _capture_from_signal(signal)
            except LearnSessionInvalidCaptureError:
                return

            capture_future.set_result(capture)

        try:
            if not self._receiver_is_available(receiver_entity_id):
                raise LearnSessionReceiverUnavailableError

            unsubscribe = infrared.async_subscribe_receiver(
                self._hass,
                receiver_entity_id,
                _handle_received_signal,
            )
            return await asyncio.wait_for(capture_future, timeout=timeout)
        except HomeAssistantError as err:
            raise LearnSessionReceiverUnavailableError from err
        except TimeoutError as err:
            raise LearnSessionTimeoutError from err
        finally:
            if tokens.get(receiver_entity_id) is token:
                tokens.pop(receiver_entity_id, None)

            if unsubscribe is not None:
                unsubscribe()

            if not capture_future.done():
                capture_future.cancel()

    def _receiver_is_available(self, receiver_entity_id: str) -> bool:
        """Return whether a receiver exists and is currently available."""
        return receiver_entity_id in infrared.async_get_receivers(
            self._hass
        ) and linked_entity_is_available(self._hass, receiver_entity_id)

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
    if decoder == LEARN_DECODER_NONE:
        return None, None

    signal = InfraredReceivedSignal(
        capture.timings,
        modulation=capture.modulation,
    )

    if decoder != LEARN_DECODER_AUTO:
        handler = _learning_handler_for_decoder(decoder)
        if handler is None:
            raise LearnSessionInvalidDecoderError

        result = _decode_learning_handler(handler, signal)
        if result is None:
            return None, None

        return result

    successful_results: list[
        tuple[
            int,
            ReceiveProtocolHandler,
            Command,
            dict[str, Any],
        ]
    ] = []

    for registry_index, handler in enumerate(_learning_handlers()):
        result = _decode_learning_handler(handler, signal)
        if result is None:
            continue

        command, metadata = result
        successful_results.append(
            (
                registry_index,
                handler,
                command,
                metadata,
            )
        )

    if not successful_results:
        return None, None

    _, _, command, metadata = max(
        successful_results,
        key=lambda item: (
            item[1].learning_confidence,
            -item[0],
        ),
    )
    return command, metadata


def _decode_learning_handler(
    handler: ReceiveProtocolHandler,
    signal: InfraredReceivedSignal,
) -> tuple[Command, dict[str, Any]] | None:
    """Decode one signal and build protocol-owned learning metadata."""
    metadata_builder = handler.learning_metadata
    if metadata_builder is None:
        return None

    result = handler.decode(signal)
    if result is None:
        return None

    protocol_metadata = dict(metadata_builder(result.normalized))
    metadata = {
        **protocol_metadata,
        "decoder": handler.protocol_id,
        "protocol": result.normalized.protocol_id,
    }
    return result.command, metadata


def _learning_handlers() -> tuple[ReceiveProtocolHandler, ...]:
    """Return learning-capable handlers in deterministic registry order."""
    return tuple(
        handler
        for handler in PROTOCOL_REGISTRY.handlers.values()
        if handler.learning_metadata is not None
    )


def _learning_handler_for_decoder(
    decoder: str,
) -> ReceiveProtocolHandler | None:
    """Return one learning-capable concrete protocol handler."""
    handler = PROTOCOL_REGISTRY.handler_for_protocol(decoder)
    if handler is None or handler.learning_metadata is None:
        return None
    return handler


def learn_decoder_definitions() -> tuple[LearnDecoderDefinition, ...]:
    """Return user-facing decoder options derived from the protocol registry."""
    return (
        LearnDecoderDefinition(
            LEARN_DECODER_AUTO,
            "auto",
            "Auto (recommended)",
        ),
        LearnDecoderDefinition(
            LEARN_DECODER_NONE,
            "none",
            "None / captured only",
        ),
        *(
            LearnDecoderDefinition(
                handler.protocol_id,
                handler.label_key,
                handler.learning_label or handler.protocol_id,
            )
            for handler in _learning_handlers()
        ),
    )


LEARN_DECODERS = tuple(definition.key for definition in learn_decoder_definitions())


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


def _repeat_event_type(signal: InfraredReceivedSignal) -> str | None:
    """Return the first registered repeat event type matching a signal."""
    for handler in PROTOCOL_REGISTRY.handlers.values():
        decode_repeat = handler.decode_repeat
        if decode_repeat is None:
            continue

        result = decode_repeat(signal, None)
        if result is not None:
            return result.event_type

    return None


def _likely_protocol(timings: list[int]) -> str | None:
    """Return an informational protocol guess for captured timings."""
    return _repeat_event_type(InfraredReceivedSignal(timings, modulation=None))
