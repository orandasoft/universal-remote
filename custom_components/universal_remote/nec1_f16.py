"""NEC1-f16 IR command encoder and decoder."""

from typing import Self, override

from infrared_protocols.commands import Command

LEADER_HIGH = 9000
LEADER_LOW = 4500
BIT_HIGH = 562
ZERO_LOW = 562
ONE_LOW = 1687
REPEAT_LOW = 2250
INITIAL_FRAME_GAP = 41000  # Gap to make total frame ~108ms
FRAME_GAP = 96000  # Gap to make total frame ~108ms
TOLERANCE = 0.4
DATA_BIT_COUNT = 32
MIN_TIMING_COUNT = 67


class NEC1F16Command(Command):
    """NEC1-f16 IR command.

    NEC1-f16 uses NEC leader/repeat timings with two address bytes and two
    function bytes. The address uses the same packed representation as
    ``NECCommand``: address ``0xFB04`` is transmitted as bytes ``04 FB``.

    Data format, LSB first:
    - address low byte
    - address high byte, usually the inverse of the address low byte
    - function byte
    - subfunction byte
    """

    address: int
    function: int
    subfunction: int

    def __init__(
        self,
        *,
        address: int,
        function: int,
        subfunction: int,
        modulation: int = 38000,
        repeat_count: int = 0,
    ) -> None:
        """Initialize the NEC1-f16 IR command."""
        super().__init__(modulation=modulation, repeat_count=repeat_count)
        self.address = address
        self.function = function
        self.subfunction = subfunction

    @override
    def get_raw_timings(self) -> list[int]:
        """Get raw timings for the NEC1-f16 command."""
        timings: list[int] = [LEADER_HIGH, -LEADER_LOW]

        if self.address <= 0xFF:
            address_low = self.address & 0xFF
            address_high = (~self.address) & 0xFF
        else:
            address_low = self.address & 0xFF
            address_high = (self.address >> 8) & 0xFF

        data = (
            address_low
            | (address_high << 8)
            | ((self.function & 0xFF) << 16)
            | ((self.subfunction & 0xFF) << 24)
        )

        for _ in range(DATA_BIT_COUNT):
            bit = data & 1
            timings.append(BIT_HIGH)
            timings.append(-ONE_LOW if bit else -ZERO_LOW)
            data >>= 1

        timings.append(BIT_HIGH)

        gap = INITIAL_FRAME_GAP
        for _ in range(self.repeat_count):
            timings.extend([-gap, LEADER_HIGH, -REPEAT_LOW, BIT_HIGH])
            gap = FRAME_GAP

        return timings

    @classmethod
    def from_raw_timings(
        cls,
        timings: list[int],
        *,
        modulation: int = 38000,
    ) -> Self | None:
        """Decode raw IR timings into an NEC1F16Command."""
        if len(timings) < MIN_TIMING_COUNT:
            return None

        if not cls._is_close(timings[0], LEADER_HIGH) or not cls._is_close(
            -timings[1], LEADER_LOW
        ):
            return None

        data = 0
        for index in range(DATA_BIT_COUNT):
            bit = cls._decode_bit(timings[2 + 2 * index], -timings[3 + 2 * index])
            if bit is None:
                return None
            data |= bit << index

        if not cls._is_close(timings[66], BIT_HIGH):
            return None

        address_low = data & 0xFF
        address_high = (data >> 8) & 0xFF
        function = (data >> 16) & 0xFF
        subfunction = (data >> 24) & 0xFF

        address = address_low | (address_high << 8)
        repeat_count = cls._count_repeat_codes(timings, MIN_TIMING_COUNT)
        return cls(
            address=address,
            function=function,
            subfunction=subfunction,
            modulation=modulation,
            repeat_count=repeat_count,
        )

    @staticmethod
    def _is_close(actual: int, expected: int) -> bool:
        """Check if an actual timing value is within tolerance."""
        margin = expected * TOLERANCE
        return expected - margin <= actual <= expected + margin

    @staticmethod
    def _decode_bit(high_us: int, low_us: int) -> int | None:
        """Decode a single NEC bit from high and low timings."""
        if not NEC1F16Command._is_close(high_us, BIT_HIGH):
            return None
        if NEC1F16Command._is_close(low_us, ZERO_LOW):
            return 0
        if NEC1F16Command._is_close(low_us, ONE_LOW):
            return 1
        return None

    @staticmethod
    def _count_repeat_codes(timings: list[int], start_index: int) -> int:
        """Count NEC repeat codes starting from the given index."""
        count = 0
        index = start_index
        gap = INITIAL_FRAME_GAP
        while (index + 3) < len(timings):
            if (
                NEC1F16Command._is_close(-timings[index], gap)
                and NEC1F16Command._is_close(timings[index + 1], LEADER_HIGH)
                and NEC1F16Command._is_close(-timings[index + 2], REPEAT_LOW)
                and NEC1F16Command._is_close(timings[index + 3], BIT_HIGH)
            ):
                count += 1
                index += 4
                gap = FRAME_GAP
            else:
                return count
        return count
