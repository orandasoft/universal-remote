"""Tests for IR learning session helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import cast

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import HomeAssistant

from custom_components.universal_remote import learn as learn_module
from custom_components.universal_remote.learn import (
    DEFAULT_LEARN_MODULATION,
    LearnCapture,
    LearnResult,
    LearnSessionInvalidCaptureError,
    LearnSessionManager,
    LearnSessionReceiverBusyError,
    LearnSessionReceiverUnavailableError,
    LearnSessionTimeoutError,
)
from custom_components.universal_remote.learn_candidates import (
    CANDIDATE_CAPTURED,
    CANDIDATE_NORMALIZED,
)
from custom_components.universal_remote.protocols import (
    PROTOCOL_NEC,
    PROTOCOL_NEC1_F16,
    DecodedInfraredCommand,
)

RECEIVER_ID = "infrared.test_receiver"
OTHER_RECEIVER_ID = "infrared.other_receiver"
VALID_TIMINGS = [9000, -4500, 560, -560]
VALID_OTHER_TIMINGS = [4500, -4500, 560, -560]
NEC_REPEAT_TIMINGS = [9000, -2250, 560]



class FakeDecodedCommand:
    """Fake decoded command used for normalized learning candidates."""

    modulation = 38_000

    def __init__(self, timings: list[int] | None = None) -> None:
        """Initialize the fake command."""
        self._timings = timings or VALID_TIMINGS

    def get_raw_timings(self) -> list[int]:
        """Return normalized raw timings."""
        return self._timings


class FakeReceiverSubscription:
    """Fake receiver subscription helper."""

    def __init__(self) -> None:
        """Initialize the fake subscription."""
        self.callback: Callable[[InfraredReceivedSignal], None] | None = None
        self.receiver_entity_id: str | None = None
        self.unsubscribe_calls = 0

    def subscribe(
        self,
        _hass: HomeAssistant,
        receiver_entity_id: str,
        callback: Callable[[InfraredReceivedSignal], None],
    ) -> Callable[[], None]:
        """Store the callback and return an unsubscribe callback."""
        self.receiver_entity_id = receiver_entity_id
        self.callback = callback
        return self.unsubscribe

    def unsubscribe(self) -> None:
        """Record an unsubscribe call."""
        self.unsubscribe_calls += 1


@pytest.fixture(autouse=True)
def clear_learn_data(hass: HomeAssistant) -> None:
    """Clear learning data between tests."""
    hass.data.pop(learn_module.DOMAIN, None)


def _patch_receivers(
    monkeypatch: pytest.MonkeyPatch,
    receivers: Iterable[str] = (RECEIVER_ID,),
) -> None:
    """Patch available infrared receivers."""
    receiver_ids = list(receivers)

    def async_get_receivers(_hass: HomeAssistant) -> list[str]:
        return receiver_ids

    monkeypatch.setattr(
        learn_module.infrared,
        "async_get_receivers",
        async_get_receivers,
    )


def _patch_subscription(
    monkeypatch: pytest.MonkeyPatch,
    subscription: FakeReceiverSubscription,
) -> None:
    """Patch receiver subscription."""
    monkeypatch.setattr(
        learn_module.infrared,
        "async_subscribe_receiver",
        subscription.subscribe,
    )


def _signal(
    timings: list[int] | None = None,
    *,
    modulation: int | None = 38_000,
) -> InfraredReceivedSignal:
    """Return a received infrared signal."""
    return InfraredReceivedSignal(
        timings=timings or VALID_TIMINGS,
        modulation=modulation,
    )


async def _start_capture(
    manager: LearnSessionManager,
    *,
    timeout: float = 1.0,
) -> asyncio.Task[LearnCapture]:
    """Start a capture task and allow it to subscribe."""
    task = asyncio.create_task(
        manager.async_capture_once(RECEIVER_ID, timeout=timeout)
    )
    await asyncio.sleep(0)
    return task


def test_capture_from_signal_uses_receiver_modulation() -> None:
    """Test capture conversion with receiver modulation."""
    capture = learn_module._capture_from_signal(_signal())

    assert capture.timings == VALID_TIMINGS
    assert capture.modulation == 38_000
    assert capture.modulation_assumed is False
    assert capture.timing_count == len(VALID_TIMINGS)
    assert capture.likely_protocol is None


def test_capture_from_signal_assumes_default_modulation() -> None:
    """Test capture conversion assumes default modulation when missing."""
    capture = learn_module._capture_from_signal(_signal(modulation=None))

    assert capture.modulation == DEFAULT_LEARN_MODULATION
    assert capture.modulation_assumed is True


@pytest.mark.parametrize(
    "timings",
    [
        [9000, -4500, 560],
        [9000, -4500, 0, -560],
        [1, -1, 1, -1],
        cast(list[int], [9000, -4500, "560", -560]),
    ],
)
def test_capture_from_signal_rejects_invalid_timings(timings: list[int]) -> None:
    """Test capture conversion rejects structurally invalid timings."""
    with pytest.raises(LearnSessionInvalidCaptureError):
        learn_module._capture_from_signal(_signal(timings))


def test_likely_protocol_returns_repeat_hint() -> None:
    """Test likely protocol hint for NEC repeat frames."""
    assert learn_module._likely_protocol(NEC_REPEAT_TIMINGS) == "nec_repeat"
    assert learn_module._likely_protocol(VALID_TIMINGS) is None


async def test_async_capture_once_rejects_unavailable_receiver(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture fails when the receiver is unavailable."""
    _patch_receivers(monkeypatch, [])
    manager = LearnSessionManager(hass)

    with pytest.raises(LearnSessionReceiverUnavailableError):
        await manager.async_capture_once(RECEIVER_ID, timeout=0.01)


async def test_async_capture_once_rejects_busy_receiver(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture fails when the receiver lock is already held."""
    _patch_receivers(monkeypatch)
    manager = LearnSessionManager(hass)
    lock = manager._receiver_lock(RECEIVER_ID)
    await lock.acquire()

    try:
        with pytest.raises(LearnSessionReceiverBusyError):
            await manager.async_capture_once(RECEIVER_ID, timeout=0.01)
    finally:
        lock.release()


async def test_async_capture_once_captures_valid_signal(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture succeeds with the first structurally valid signal."""
    _patch_receivers(monkeypatch)
    subscription = FakeReceiverSubscription()
    _patch_subscription(monkeypatch, subscription)
    manager = LearnSessionManager(hass)

    task = await _start_capture(manager)

    assert subscription.receiver_entity_id == RECEIVER_ID
    assert subscription.callback is not None
    subscription.callback(_signal())
    subscription.callback(_signal(VALID_OTHER_TIMINGS))

    capture = await task

    assert capture.timings == VALID_TIMINGS
    assert capture.modulation == 38_000
    assert subscription.unsubscribe_calls == 1
    assert manager._capture_tokens() == {}
    assert not manager._receiver_lock(RECEIVER_ID).locked()

    subscription.callback(_signal(VALID_OTHER_TIMINGS))


async def test_async_capture_once_ignores_repeat_and_invalid_signals(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture waits for a valid non-repeat signal."""
    _patch_receivers(monkeypatch)
    subscription = FakeReceiverSubscription()
    _patch_subscription(monkeypatch, subscription)
    manager = LearnSessionManager(hass)

    task = await _start_capture(manager)

    assert subscription.callback is not None
    subscription.callback(_signal(NEC_REPEAT_TIMINGS))
    subscription.callback(_signal([1, -1, 1, -1]))
    assert not task.done()

    subscription.callback(_signal(VALID_OTHER_TIMINGS, modulation=None))
    capture = await task

    assert capture.timings == VALID_OTHER_TIMINGS
    assert capture.modulation == DEFAULT_LEARN_MODULATION
    assert capture.modulation_assumed is True
    assert subscription.unsubscribe_calls == 1


async def test_async_capture_once_times_out(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture timeout cleanup."""
    _patch_receivers(monkeypatch)
    subscription = FakeReceiverSubscription()
    _patch_subscription(monkeypatch, subscription)
    manager = LearnSessionManager(hass)

    with pytest.raises(LearnSessionTimeoutError):
        await manager.async_capture_once(RECEIVER_ID, timeout=0.001)

    assert subscription.unsubscribe_calls == 1
    assert manager._capture_tokens() == {}
    assert not manager._receiver_lock(RECEIVER_ID).locked()


async def test_async_capture_once_cleans_up_when_subscription_fails(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test cleanup when receiver subscription setup fails."""
    _patch_receivers(monkeypatch)
    manager = LearnSessionManager(hass)

    def async_subscribe_receiver(
        _hass: HomeAssistant,
        _receiver_entity_id: str,
        _callback: Callable[[InfraredReceivedSignal], None],
    ) -> Callable[[], None]:
        raise RuntimeError("subscribe failed")

    monkeypatch.setattr(
        learn_module.infrared,
        "async_subscribe_receiver",
        async_subscribe_receiver,
    )

    with pytest.raises(RuntimeError, match="subscribe failed"):
        await manager.async_capture_once(RECEIVER_ID, timeout=1.0)

    assert manager._capture_tokens() == {}
    assert not manager._receiver_lock(RECEIVER_ID).locked()


async def test_async_capture_once_uses_independent_receiver_locks(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test receiver locks are scoped per receiver."""
    _patch_receivers(monkeypatch, [RECEIVER_ID, OTHER_RECEIVER_ID])
    manager = LearnSessionManager(hass)
    lock = manager._receiver_lock(OTHER_RECEIVER_ID)
    await lock.acquire()

    try:
        receiver_lock = manager._receiver_lock(RECEIVER_ID)
        assert not receiver_lock.locked()
        assert lock.locked()
    finally:
        lock.release()


def _capture(
    timings: list[int] | None = None,
    *,
    modulation: int = 38_000,
    modulation_assumed: bool = False,
) -> LearnCapture:
    """Return a completed learning capture."""
    timing_values = timings or VALID_TIMINGS
    return LearnCapture(
        timings=timing_values,
        modulation=modulation,
        modulation_assumed=modulation_assumed,
        timing_count=len(timing_values),
    )


def test_build_learn_result_uses_captured_candidate_without_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test learn result uses captured candidate when no decoder matches."""
    monkeypatch.setattr(learn_module, "_decode_nec_signal", lambda _signal: None)
    monkeypatch.setattr(learn_module, "_decode_nec1_f16_signal", lambda _signal: None)

    result = learn_module.build_learn_result(_capture(modulation_assumed=True))

    assert isinstance(result, LearnResult)
    assert result.capture.modulation_assumed is True
    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert result.candidates[0].recommended is True
    assert result.candidates[0].metadata["modulation_assumed"] is True


def test_build_learn_result_adds_normalized_nec_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test learn result includes a normalized NEC candidate when decoded."""
    command = FakeDecodedCommand()
    monkeypatch.setattr(learn_module, "_decode_nec_signal", lambda _signal: command)
    monkeypatch.setattr(
        learn_module,
        "_normalize_nec_command",
        lambda _command: DecodedInfraredCommand(
            protocol=PROTOCOL_NEC,
            address=0x04,
            primary=0x08,
        ),
    )

    result = learn_module.build_learn_result(_capture())

    assert [candidate.key for candidate in result.candidates] == [
        CANDIDATE_CAPTURED,
        CANDIDATE_NORMALIZED,
    ]
    assert result.candidates[0].recommended is False
    assert result.candidates[1].recommended is True
    assert result.candidates[1].metadata["decoder"] == PROTOCOL_NEC
    assert result.candidates[1].metadata["protocol"] == PROTOCOL_NEC
    assert result.candidates[1].metadata["address"] == "0x0004"
    assert result.candidates[1].metadata["primary"] == "0x08"
    assert "secondary" not in result.candidates[1].metadata


def test_build_learn_result_falls_back_to_nec1_f16_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test NEC1-f16 decode is used when NEC decode does not match."""
    command = FakeDecodedCommand()
    monkeypatch.setattr(learn_module, "_decode_nec_signal", lambda _signal: None)
    monkeypatch.setattr(
        learn_module,
        "_decode_nec1_f16_signal",
        lambda _signal: command,
    )
    monkeypatch.setattr(
        learn_module,
        "_normalize_nec1_f16_command",
        lambda _command: DecodedInfraredCommand(
            protocol=PROTOCOL_NEC1_F16,
            address=0xFB04,
            primary=0xDB,
            secondary=0x32,
        ),
    )

    result = learn_module.build_learn_result(_capture())

    assert [candidate.key for candidate in result.candidates] == [
        CANDIDATE_CAPTURED,
        CANDIDATE_NORMALIZED,
    ]
    assert result.candidates[1].metadata["decoder"] == PROTOCOL_NEC1_F16
    assert result.candidates[1].metadata["protocol"] == PROTOCOL_NEC1_F16
    assert result.candidates[1].metadata["address"] == "0xFB04"
    assert result.candidates[1].metadata["primary"] == "0xDB"
    assert result.candidates[1].metadata["secondary"] == "0x32"


def test_build_learn_result_skips_candidate_when_normalization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test decoded commands without normalized metadata are ignored."""
    command = FakeDecodedCommand()
    monkeypatch.setattr(learn_module, "_decode_nec_signal", lambda _signal: command)
    monkeypatch.setattr(learn_module, "_normalize_nec_command", lambda _command: None)
    monkeypatch.setattr(learn_module, "_decode_nec1_f16_signal", lambda _signal: None)

    result = learn_module.build_learn_result(_capture())

    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert result.candidates[0].recommended is True


async def test_async_learn_once_returns_learn_result(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test one-shot learning captures a signal and creates candidates."""
    _patch_receivers(monkeypatch)
    subscription = FakeReceiverSubscription()
    _patch_subscription(monkeypatch, subscription)
    monkeypatch.setattr(learn_module, "_decode_nec_signal", lambda _signal: None)
    monkeypatch.setattr(learn_module, "_decode_nec1_f16_signal", lambda _signal: None)
    manager = LearnSessionManager(hass)

    task = asyncio.create_task(manager.async_learn_once(RECEIVER_ID, timeout=1.0))
    await asyncio.sleep(0)

    assert subscription.callback is not None
    subscription.callback(_signal())
    result = await task

    assert isinstance(result, LearnResult)
    assert result.capture.timings == VALID_TIMINGS
    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert subscription.unsubscribe_calls == 1
