"""LG TV Japan infrared codeset with NEC and NEC1-f16 commands."""

from dataclasses import dataclass
from enum import Enum

from infrared_protocols.commands import Command
from infrared_protocols.commands.nec import NECCommand

from .nec1_f16 import NEC1F16Command


@dataclass(frozen=True, slots=True)
class NECCode:
    """Normal NEC command code spec."""

    address: int
    command: int

    def to_command(self, repeat_count: int = 0) -> Command:
        """Build an NEC command."""
        return NECCommand(
            address=self.address,
            command=self.command,
            repeat_count=repeat_count,
        )


@dataclass(frozen=True, slots=True)
class NEC1F16Code:
    """NEC1-f16 command code spec.

    ``address`` uses the same packed 16-bit representation as ``NECCommand``.
    For LG TV Japan, ``0xFB04`` transmits the first two bytes as ``04 FB``.
    """

    address: int
    function: int
    subfunction: int

    def to_command(self, repeat_count: int = 0) -> Command:
        """Build an NEC1-f16 command."""
        return NEC1F16Command(
            address=self.address,
            function=self.function,
            subfunction=self.subfunction,
            repeat_count=repeat_count,
        )


class LGTVCodeJP(Enum):
    """Japan-specific LG TV IR command codes.

    Normal commands are encoded as NEC commands. Japan tuner selectors and
    tuner numeric commands are encoded as NEC1-f16 commands using explicit
    ``address, function, subfunction`` values.
    """

    AMAZON = NECCode(0xFB04, 0x5C)
    ASPECT = NECCode(0xFB04, 0x79)
    BACK = NECCode(0xFB04, 0x28)
    BLUE = NECCode(0xFB04, 0x72)
    BS = NEC1F16Code(0xFB04, 0xDB, 0x00)
    BS_NUM_1 = NEC1F16Code(0xFB04, 0xDB, 0x01)
    BS_NUM_2 = NEC1F16Code(0xFB04, 0xDB, 0x02)
    BS_NUM_3 = NEC1F16Code(0xFB04, 0xDB, 0x03)
    BS_NUM_4 = NEC1F16Code(0xFB04, 0xDB, 0x04)
    BS_NUM_5 = NEC1F16Code(0xFB04, 0xDB, 0x05)
    BS_NUM_6 = NEC1F16Code(0xFB04, 0xDB, 0x06)
    BS_NUM_7 = NEC1F16Code(0xFB04, 0xDB, 0x07)
    BS_NUM_8 = NEC1F16Code(0xFB04, 0xDB, 0x08)
    BS_NUM_9 = NEC1F16Code(0xFB04, 0xDB, 0x09)
    BS_NUM_10 = NEC1F16Code(0xFB04, 0xDB, 0x0A)
    BS_NUM_11 = NEC1F16Code(0xFB04, 0xDB, 0x0B)
    BS_NUM_12 = NEC1F16Code(0xFB04, 0xDB, 0x0C)
    BS4K = NEC1F16Code(0xFB04, 0xDB, 0x40)
    BS4K_NUM_1 = NEC1F16Code(0xFB04, 0xDB, 0x41)
    BS4K_NUM_2 = NEC1F16Code(0xFB04, 0xDB, 0x42)
    BS4K_NUM_3 = NEC1F16Code(0xFB04, 0xDB, 0x43)
    BS4K_NUM_4 = NEC1F16Code(0xFB04, 0xDB, 0x44)
    BS4K_NUM_5 = NEC1F16Code(0xFB04, 0xDB, 0x45)
    BS4K_NUM_6 = NEC1F16Code(0xFB04, 0xDB, 0x46)
    BS4K_NUM_7 = NEC1F16Code(0xFB04, 0xDB, 0x47)
    BS4K_NUM_8 = NEC1F16Code(0xFB04, 0xDB, 0x48)
    BS4K_NUM_9 = NEC1F16Code(0xFB04, 0xDB, 0x49)
    BS4K_NUM_10 = NEC1F16Code(0xFB04, 0xDB, 0x4A)
    BS4K_NUM_11 = NEC1F16Code(0xFB04, 0xDB, 0x4B)
    BS4K_NUM_12 = NEC1F16Code(0xFB04, 0xDB, 0x4C)
    CS4K = NEC1F16Code(0xFB04, 0xDB, 0x50)
    CS4K_NUM_1 = NEC1F16Code(0xFB04, 0xDB, 0x51)
    CS4K_NUM_2 = NEC1F16Code(0xFB04, 0xDB, 0x52)
    CS4K_NUM_3 = NEC1F16Code(0xFB04, 0xDB, 0x53)
    CS4K_NUM_4 = NEC1F16Code(0xFB04, 0xDB, 0x54)
    CS4K_NUM_5 = NEC1F16Code(0xFB04, 0xDB, 0x55)
    CS4K_NUM_6 = NEC1F16Code(0xFB04, 0xDB, 0x56)
    CS4K_NUM_7 = NEC1F16Code(0xFB04, 0xDB, 0x57)
    CS4K_NUM_8 = NEC1F16Code(0xFB04, 0xDB, 0x58)
    CS4K_NUM_9 = NEC1F16Code(0xFB04, 0xDB, 0x59)
    CS4K_NUM_10 = NEC1F16Code(0xFB04, 0xDB, 0x5A)
    CS4K_NUM_11 = NEC1F16Code(0xFB04, 0xDB, 0x5B)
    CS4K_NUM_12 = NEC1F16Code(0xFB04, 0xDB, 0x5C)
    CHANNEL_DOWN = NECCode(0xFB04, 0x01)
    CHANNEL_UP = NECCode(0xFB04, 0x00)
    CS1 = NEC1F16Code(0xFB04, 0xDB, 0x10)
    CS1_NUM_1 = NEC1F16Code(0xFB04, 0xDB, 0x11)
    CS1_NUM_2 = NEC1F16Code(0xFB04, 0xDB, 0x12)
    CS1_NUM_3 = NEC1F16Code(0xFB04, 0xDB, 0x13)
    CS1_NUM_4 = NEC1F16Code(0xFB04, 0xDB, 0x14)
    CS1_NUM_5 = NEC1F16Code(0xFB04, 0xDB, 0x15)
    CS1_NUM_6 = NEC1F16Code(0xFB04, 0xDB, 0x16)
    CS1_NUM_7 = NEC1F16Code(0xFB04, 0xDB, 0x17)
    CS1_NUM_8 = NEC1F16Code(0xFB04, 0xDB, 0x18)
    CS1_NUM_9 = NEC1F16Code(0xFB04, 0xDB, 0x19)
    CS1_NUM_10 = NEC1F16Code(0xFB04, 0xDB, 0x1A)
    CS1_NUM_11 = NEC1F16Code(0xFB04, 0xDB, 0x1B)
    CS1_NUM_12 = NEC1F16Code(0xFB04, 0xDB, 0x1C)
    CS2 = NEC1F16Code(0xFB04, 0xDB, 0x20)
    CS2_NUM_1 = NEC1F16Code(0xFB04, 0xDB, 0x21)
    CS2_NUM_2 = NEC1F16Code(0xFB04, 0xDB, 0x22)
    CS2_NUM_3 = NEC1F16Code(0xFB04, 0xDB, 0x23)
    CS2_NUM_4 = NEC1F16Code(0xFB04, 0xDB, 0x24)
    CS2_NUM_5 = NEC1F16Code(0xFB04, 0xDB, 0x25)
    CS2_NUM_6 = NEC1F16Code(0xFB04, 0xDB, 0x26)
    CS2_NUM_7 = NEC1F16Code(0xFB04, 0xDB, 0x27)
    CS2_NUM_8 = NEC1F16Code(0xFB04, 0xDB, 0x28)
    CS2_NUM_9 = NEC1F16Code(0xFB04, 0xDB, 0x29)
    CS2_NUM_10 = NEC1F16Code(0xFB04, 0xDB, 0x2A)
    CS2_NUM_11 = NEC1F16Code(0xFB04, 0xDB, 0x2B)
    CS2_NUM_12 = NEC1F16Code(0xFB04, 0xDB, 0x2C)
    DATA = NECCode(0xFB04, 0xCC)
    DTV = NEC1F16Code(0xFB04, 0xDB, 0x30)
    DTV_NUM_1 = NEC1F16Code(0xFB04, 0xDB, 0x31)
    DTV_NUM_2 = NEC1F16Code(0xFB04, 0xDB, 0x32)
    DTV_NUM_3 = NEC1F16Code(0xFB04, 0xDB, 0x33)
    DTV_NUM_4 = NEC1F16Code(0xFB04, 0xDB, 0x34)
    DTV_NUM_5 = NEC1F16Code(0xFB04, 0xDB, 0x35)
    DTV_NUM_6 = NEC1F16Code(0xFB04, 0xDB, 0x36)
    DTV_NUM_7 = NEC1F16Code(0xFB04, 0xDB, 0x37)
    DTV_NUM_8 = NEC1F16Code(0xFB04, 0xDB, 0x38)
    DTV_NUM_9 = NEC1F16Code(0xFB04, 0xDB, 0x39)
    DTV_NUM_10 = NEC1F16Code(0xFB04, 0xDB, 0x3A)
    DTV_NUM_11 = NEC1F16Code(0xFB04, 0xDB, 0x3B)
    DTV_NUM_12 = NEC1F16Code(0xFB04, 0xDB, 0x3C)
    EXIT = NECCode(0xFB04, 0x5B)
    EZ_ADJUST = NECCode(0xFB04, 0xFF)
    FAST_FORWARD = NECCode(0xFB04, 0x8E)
    GREEN = NECCode(0xFB04, 0x63)
    GUIDE = NECCode(0xFB04, 0xA9)
    HDMI_1 = NECCode(0xFB04, 0xCE)
    HDMI_2 = NECCode(0xFB04, 0x91)
    HDMI_3 = NECCode(0xFB04, 0xD0)
    HDMI_4 = NECCode(0xFB04, 0xD1)
    HOME = NECCode(0xFB04, 0x7C)
    INFO = NECCode(0xFB04, 0xAA)
    INPUT = NECCode(0xFB04, 0x0B)
    IN_START = NECCode(0xFB04, 0xFB)
    LIST = NECCode(0xFB04, 0x53)
    MENU = NECCode(0xFB04, 0x43)
    MUTE = NECCode(0xFB04, 0x09)
    NAV_DOWN = NECCode(0xFB04, 0x05)
    NAV_LEFT = NECCode(0xFB04, 0x07)
    NAV_RIGHT = NECCode(0xFB04, 0x06)
    NAV_UP = NECCode(0xFB04, 0x04)
    NETFLIX = NECCode(0xFB04, 0x56)
    NUM_1 = NECCode(0xFB04, 0x11)
    NUM_2 = NECCode(0xFB04, 0x12)
    NUM_3 = NECCode(0xFB04, 0x13)
    NUM_4 = NECCode(0xFB04, 0x14)
    NUM_5 = NECCode(0xFB04, 0x15)
    NUM_6 = NECCode(0xFB04, 0x16)
    NUM_7 = NECCode(0xFB04, 0x17)
    NUM_8 = NECCode(0xFB04, 0x18)
    NUM_9 = NECCode(0xFB04, 0x19)
    NUM_10 = NECCode(0xFB04, 0x10)
    NUM_11 = NECCode(0xFB04, 0x40)
    NUM_12 = NECCode(0xFB04, 0x41)
    OK = NECCode(0xFB04, 0x44)
    PAUSE = NECCode(0xFB04, 0xBA)
    PLAY = NECCode(0xFB04, 0xB0)
    POWER = NECCode(0xFB04, 0x08)
    POWER_ON = NECCode(0xFB04, 0xC4)
    POWER_OFF = NECCode(0xFB04, 0xC5)
    REC_LIST = NECCode(0xFB04, 0x1E)
    RECORD = NECCode(0xFB04, 0xBD)
    RED = NECCode(0xFB04, 0x71)
    REWIND = NECCode(0xFB04, 0x8F)
    SAP = NECCode(0xFB04, 0x0A)
    SETTINGS = NECCode(0xFB04, 0x45)
    STOP = NECCode(0xFB04, 0xB1)
    SUBTITLE = NECCode(0xFB04, 0x39)
    THREE_DIGIT_INPUT = NECCode(0xFB04, 0x32)
    TV = NECCode(0xFB04, 0x5F)
    VOLUME_DOWN = NECCode(0xFB04, 0x03)
    VOLUME_UP = NECCode(0xFB04, 0x02)
    YELLOW = NECCode(0xFB04, 0x61)

    def to_command(self, repeat_count: int = 0) -> Command:
        """Build an infrared command for this LG TV Japan code."""
        spec = self.value
        if not isinstance(spec, (NECCode, NEC1F16Code)):
            raise TypeError("LGTVCodeJP member value is not a supported code spec")
        return spec.to_command(repeat_count=repeat_count)
