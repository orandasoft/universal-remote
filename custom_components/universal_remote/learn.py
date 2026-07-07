"""IR learning session helpers for Universal Remote."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from homeassistant.components import infrared
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback

from .const import DOMAIN
from .learn_candidates import DEFAULT_LEARN_MODULATION
from .protocols import _is_nec_repeat_frame

MIN_CAPTURE_TIMING_COUNT = 4
MIN_CAPTURE_TOTAL_DURATION_US = 1_000
DEFAULT_LEARN_TIMEOUT = 30.0
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


class LearnSessionManager:
    """Manage one-shot IR learning capture sessions."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the learning session manager."""
        self._hass = hass

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
