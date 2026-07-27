"""Tests for IR learning session helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from typing import Any, cast

import pytest
from homeassistant.components.infrared import InfraredReceivedSignal
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from infrared_protocols.commands import Command

from custom_components.universal_remote import learn as learn_module
from custom_components.universal_remote.learn import (
    DEFAULT_LEARN_MODULATION,
    LEARN_DECODER_AUTO,
    LEARN_DECODER_NEC,
    LEARN_DECODER_NEC1_F16,
    LEARN_DECODER_NONE,
    LEARN_DECODERS,
    LearnCapture,
    LearnResult,
    LearnSessionInvalidCaptureError,
    LearnSessionInvalidDecoderError,
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
)
from custom_components.universal_remote.protocols.base import (
    NormalizedInfraredCommand,
    ProtocolDecodeResult,
    ReceiveProtocolHandler,
)
from custom_components.universal_remote.protocols.registry import (
    build_protocol_registry,
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
    monkeypatch.setattr(
        learn_module,
        "linked_entity_is_available",
        lambda _hass, receiver_entity_id: receiver_entity_id in receiver_ids,
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
    task = asyncio.create_task(manager.async_capture_once(RECEIVER_ID, timeout=timeout))
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


async def test_async_capture_once_rejects_receiver_with_unavailable_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture fails when a registered receiver state is unavailable."""
    _patch_receivers(monkeypatch)
    monkeypatch.setattr(
        learn_module,
        "linked_entity_is_available",
        lambda _hass, _receiver_entity_id: False,
    )
    manager = LearnSessionManager(hass)

    with pytest.raises(LearnSessionReceiverUnavailableError):
        await manager.async_capture_once(RECEIVER_ID, timeout=0.01)


async def test_async_capture_once_rechecks_availability_before_subscribing(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test capture handles a receiver becoming unavailable before subscribe."""
    _patch_receivers(monkeypatch)
    availability = iter((True, False))
    monkeypatch.setattr(
        learn_module,
        "linked_entity_is_available",
        lambda _hass, _receiver_entity_id: next(availability),
    )
    subscription = FakeReceiverSubscription()
    _patch_subscription(monkeypatch, subscription)
    manager = LearnSessionManager(hass)

    with pytest.raises(LearnSessionReceiverUnavailableError):
        await manager.async_capture_once(RECEIVER_ID, timeout=0.01)

    assert subscription.callback is None
    assert manager._capture_tokens() == {}
    assert not manager._receiver_lock(RECEIVER_ID).locked()


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


async def test_async_capture_once_converts_missing_subscription_receiver(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a receiver disappearing during subscription is reported unavailable."""
    _patch_receivers(monkeypatch)
    manager = LearnSessionManager(hass)

    def async_subscribe_receiver(
        _hass: HomeAssistant,
        _receiver_entity_id: str,
        _callback: Callable[[InfraredReceivedSignal], None],
    ) -> Callable[[], None]:
        raise HomeAssistantError("receiver disappeared")

    monkeypatch.setattr(
        learn_module.infrared,
        "async_subscribe_receiver",
        async_subscribe_receiver,
    )

    with pytest.raises(LearnSessionReceiverUnavailableError):
        await manager.async_capture_once(RECEIVER_ID, timeout=1.0)

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


def _fake_learning_handler(
    protocol_id: str,
    *,
    command: Command | None = None,
    confidence: int = 100,
    label: str | None = None,
    metadata: dict[str, Any] | None = None,
    matches: bool = True,
    calls: list[str] | None = None,
    learning: bool = True,
) -> ReceiveProtocolHandler:
    """Return a configurable fake learning-capable protocol handler."""
    command_value = (
        command
        if command is not None
        else cast(Command, FakeDecodedCommand(VALID_OTHER_TIMINGS))
    )
    normalized = NormalizedInfraredCommand(
        protocol_id=protocol_id,
        identity=(protocol_id, 1),
        event_data={"value": 1},
    )
    metadata_value = (
        metadata
        if metadata is not None
        else {
            "address": "0x0001",
            "primary": "0x02",
        }
    )

    def decode(
        _signal_value: InfraredReceivedSignal,
    ) -> ProtocolDecodeResult | None:
        if calls is not None:
            calls.append(protocol_id)
        if not matches:
            return None
        return ProtocolDecodeResult(
            command=command_value,
            normalized=normalized,
        )

    def normalize(
        _command: Command,
    ) -> NormalizedInfraredCommand:
        return normalized

    def build_metadata(
        _normalized: NormalizedInfraredCommand,
    ) -> dict[str, Any]:
        return dict(metadata_value)

    return ReceiveProtocolHandler(
        protocol_id=protocol_id,
        label_key=protocol_id,
        learning_confidence=confidence,
        decode=decode,
        normalize=normalize,
        learning_label=label,
        learning_metadata=build_metadata if learning else None,
    )


def _patch_learning_registry(
    monkeypatch: pytest.MonkeyPatch,
    *handlers: ReceiveProtocolHandler,
) -> None:
    """Patch learning to use one explicit temporary protocol registry."""
    monkeypatch.setattr(
        learn_module,
        "PROTOCOL_REGISTRY",
        build_protocol_registry(handlers, {}),
    )


def test_build_learn_result_uses_captured_candidate_without_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test learning uses captured data when no registered handler matches."""
    _patch_learning_registry(
        monkeypatch,
        _fake_learning_handler("unmatched", matches=False),
    )

    result = learn_module.build_learn_result(_capture(modulation_assumed=True))

    assert isinstance(result, LearnResult)
    assert result.capture.modulation_assumed is True
    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert result.candidates[0].recommended is True
    assert result.candidates[0].metadata["modulation_assumed"] is True


def test_learn_decoders_are_stable() -> None:
    """Test supported production learning decoder options."""
    assert LEARN_DECODERS == (
        LEARN_DECODER_AUTO,
        LEARN_DECODER_NONE,
        LEARN_DECODER_NEC,
        LEARN_DECODER_NEC1_F16,
    )

    definitions = learn_module.learn_decoder_definitions()
    assert [definition.key for definition in definitions] == list(LEARN_DECODERS)
    assert [definition.label_key for definition in definitions] == [
        "auto",
        "none",
        "nec",
        "nec1_f16",
    ]
    assert [definition.fallback_label for definition in definitions] == [
        "Auto (recommended)",
        "None / captured only",
        "NEC",
        "NEC1-F16",
    ]


def test_registered_handler_extends_explicit_and_auto_learning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a registered handler extends learning without orchestration edits."""
    calls: list[str] = []
    handler = _fake_learning_handler(
        "custom",
        label="Custom",
        metadata={
            "address": "0x0001",
            "primary": "0x02",
        },
        calls=calls,
    )
    _patch_learning_registry(monkeypatch, handler)

    explicit = learn_module.build_learn_result(
        _capture(),
        decoder="custom",
    )
    automatic = learn_module.build_learn_result(_capture())

    assert [candidate.key for candidate in explicit.candidates] == [
        CANDIDATE_CAPTURED,
        CANDIDATE_NORMALIZED,
    ]
    assert explicit.candidates[1].metadata["decoder"] == "custom"
    assert explicit.candidates[1].metadata["protocol"] == "custom"
    assert automatic.candidates[1].metadata["decoder"] == "custom"
    assert calls == ["custom", "custom"]


def test_auto_decoder_selects_highest_confidence_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Auto chooses the highest-confidence successful handler."""
    calls: list[str] = []
    low = _fake_learning_handler(
        "low",
        confidence=10,
        calls=calls,
    )
    high = _fake_learning_handler(
        "high",
        confidence=20,
        calls=calls,
    )
    _patch_learning_registry(monkeypatch, low, high)

    result = learn_module.build_learn_result(_capture())

    assert result.candidates[1].metadata["decoder"] == "high"
    assert calls == ["low", "high"]


def test_auto_decoder_uses_registry_order_for_equal_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test explicit registry order breaks equal-confidence ties."""
    first = _fake_learning_handler("first", confidence=10)
    second = _fake_learning_handler("second", confidence=10)
    _patch_learning_registry(monkeypatch, first, second)

    result = learn_module.build_learn_result(_capture())

    assert result.candidates[1].metadata["decoder"] == "first"


def test_auto_prefers_standard_nec_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Auto prefers standard NEC when both NEC handlers match."""
    calls: list[str] = []
    nec = _fake_learning_handler(
        PROTOCOL_NEC,
        confidence=200,
        label="NEC",
        metadata={
            "address": "0xFB04",
            "primary": "0x09",
        },
        calls=calls,
    )
    nec1_f16 = _fake_learning_handler(
        PROTOCOL_NEC1_F16,
        confidence=100,
        label="NEC1-F16",
        metadata={
            "address": "0xFB04",
            "primary": "0x09",
            "secondary": "0xF6",
        },
        calls=calls,
    )
    _patch_learning_registry(monkeypatch, nec, nec1_f16)

    result = learn_module.build_learn_result(_capture())

    metadata = result.candidates[1].metadata
    assert metadata["decoder"] == PROTOCOL_NEC
    assert metadata["protocol"] == PROTOCOL_NEC
    assert metadata["address"] == "0xFB04"
    assert metadata["primary"] == "0x09"
    assert "secondary" not in metadata
    assert calls == [PROTOCOL_NEC, PROTOCOL_NEC1_F16]


def test_auto_uses_nec1_f16_when_standard_nec_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Auto selects NEC1-F16 when standard NEC rejects the signal."""
    nec = _fake_learning_handler(
        PROTOCOL_NEC,
        confidence=200,
        label="NEC",
        matches=False,
    )
    nec1_f16 = _fake_learning_handler(
        PROTOCOL_NEC1_F16,
        confidence=100,
        label="NEC1-F16",
        metadata={
            "address": "0xFB04",
            "primary": "0xDB",
            "secondary": "0x00",
        },
    )
    _patch_learning_registry(monkeypatch, nec, nec1_f16)

    result = learn_module.build_learn_result(_capture())

    metadata = result.candidates[1].metadata
    assert metadata["decoder"] == PROTOCOL_NEC1_F16
    assert metadata["protocol"] == PROTOCOL_NEC1_F16
    assert metadata["address"] == "0xFB04"
    assert metadata["primary"] == "0xDB"
    assert metadata["secondary"] == "0x00"


def test_build_learn_result_decoder_none_skips_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test None returns captured-only without invoking handlers."""
    calls: list[str] = []
    _patch_learning_registry(
        monkeypatch,
        _fake_learning_handler("should_not_run", calls=calls),
    )

    result = learn_module.build_learn_result(
        _capture(),
        decoder=LEARN_DECODER_NONE,
    )

    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert result.candidates[0].recommended is True
    assert calls == []


def test_build_learn_result_rejects_invalid_decoder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test unknown explicit decoder names are rejected."""
    _patch_learning_registry(monkeypatch)

    with pytest.raises(LearnSessionInvalidDecoderError):
        learn_module.build_learn_result(
            _capture(),
            decoder="invalid",
        )


def test_explicit_decoder_only_invokes_selected_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test an explicit decoder does not try other handlers."""
    calls: list[str] = []
    nec = _fake_learning_handler(
        PROTOCOL_NEC,
        label="NEC",
        calls=calls,
    )
    nec1_f16 = _fake_learning_handler(
        PROTOCOL_NEC1_F16,
        label="NEC1-F16",
        calls=calls,
    )
    _patch_learning_registry(monkeypatch, nec, nec1_f16)

    result = learn_module.build_learn_result(
        _capture(),
        decoder=PROTOCOL_NEC,
    )

    assert result.candidates[1].metadata["decoder"] == PROTOCOL_NEC
    assert calls == [PROTOCOL_NEC]


def test_explicit_decoder_returns_captured_when_unmatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test an explicit handler may reject a captured signal."""
    handler = _fake_learning_handler(
        PROTOCOL_NEC,
        label="NEC",
        matches=False,
    )
    _patch_learning_registry(monkeypatch, handler)

    result = learn_module.build_learn_result(
        _capture(),
        decoder=PROTOCOL_NEC,
    )

    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert result.candidates[0].recommended is True


def test_non_learning_handler_is_not_exposed_or_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test receive-only handlers are excluded from learning."""
    handler = _fake_learning_handler(
        "receive_only",
        learning=False,
    )
    _patch_learning_registry(monkeypatch, handler)

    assert [
        definition.key for definition in learn_module.learn_decoder_definitions()
    ] == [
        LEARN_DECODER_AUTO,
        LEARN_DECODER_NONE,
    ]
    assert (
        learn_module._decode_learning_handler(
            handler,
            _signal(),
        )
        is None
    )

    with pytest.raises(LearnSessionInvalidDecoderError):
        learn_module.build_learn_result(
            _capture(),
            decoder="receive_only",
        )


def test_learning_definition_falls_back_to_protocol_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a handler without a display label uses its protocol id."""
    handler = _fake_learning_handler(
        "fallback_protocol",
        label=None,
    )
    _patch_learning_registry(monkeypatch, handler)

    definition = learn_module.learn_decoder_definitions()[-1]

    assert definition.key == "fallback_protocol"
    assert definition.label_key == "fallback_protocol"
    assert definition.fallback_label == "fallback_protocol"


def test_protocol_metadata_cannot_override_identity_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handler metadata cannot spoof decoder or protocol identity."""
    handler = _fake_learning_handler(
        "trusted",
        metadata={
            "decoder": "spoofed",
            "protocol": "spoofed",
            "custom": "value",
        },
    )
    _patch_learning_registry(monkeypatch, handler)

    result = learn_module.build_learn_result(_capture())

    metadata = result.candidates[1].metadata
    assert metadata["decoder"] == "trusted"
    assert metadata["protocol"] == "trusted"
    assert metadata["custom"] == "value"


async def test_async_learn_once_returns_learn_result(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test one-shot learning captures a signal and creates candidates."""
    _patch_receivers(monkeypatch)
    subscription = FakeReceiverSubscription()
    _patch_subscription(monkeypatch, subscription)
    manager = LearnSessionManager(hass)

    task = asyncio.create_task(
        manager.async_learn_once(
            RECEIVER_ID,
            timeout=1.0,
            decoder=LEARN_DECODER_NONE,
        )
    )
    await asyncio.sleep(0)

    assert subscription.callback is not None
    subscription.callback(_signal())
    result = await task

    assert isinstance(result, LearnResult)
    assert result.capture.timings == VALID_TIMINGS
    assert [candidate.key for candidate in result.candidates] == [CANDIDATE_CAPTURED]
    assert subscription.unsubscribe_calls == 1
