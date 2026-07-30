"""Television device profile."""

from ..const import DEVICE_TYPE_TV
from .base import CommandRole, DeviceProfile, SourceRule

PROFILE_TV = DEVICE_TYPE_TV

TV_PROFILE = DeviceProfile(
    profile_id=PROFILE_TV,
    device_type=DEVICE_TYPE_TV,
    device_type_label="TV",
    entity_domains=frozenset({"media_player"}),
    roles=(
        CommandRole("turn_on", ("POWER_ON",)),
        CommandRole("turn_off", ("POWER_OFF",)),
        CommandRole("volume_up", ("VOLUME_UP", "VOL_UP")),
        CommandRole("volume_down", ("VOLUME_DOWN", "VOL_DOWN")),
        CommandRole("mute", ("MUTE", "VOLUME_MUTE")),
        CommandRole("channel_up", ("CHANNEL_UP", "CH_UP")),
        CommandRole("channel_down", ("CHANNEL_DOWN", "CH_DOWN")),
        CommandRole("play", ("PLAY",)),
        CommandRole("pause", ("PAUSE",)),
        CommandRole("stop", ("STOP",)),
    ),
    sources=(
        SourceRule("TV", ("TV",)),
        SourceRule("TV input", ("TV_INPUT",)),
        SourceRule("DTV", ("DTV",)),
        SourceRule("BS", ("BS",)),
        SourceRule("BS4K", ("BS4K",)),
        SourceRule("CS1", ("CS1",)),
        SourceRule("CS2", ("CS2",)),
        SourceRule("CS4K", ("CS4K",)),
        SourceRule("Input", ("INPUT",)),
        SourceRule("Source", ("SOURCE",)),
        SourceRule("Next HDMI input", ("NEXT_HDMI_INPUT",)),
        SourceRule("HDMI 1", ("HDMI_1",)),
        SourceRule("HDMI 2", ("HDMI_2",)),
        SourceRule("HDMI 3", ("HDMI_3",)),
        SourceRule("HDMI 4", ("HDMI_4",)),
        SourceRule("HDMI 5", ("HDMI_5",)),
        SourceRule("Component", ("COMPONENT_INPUT",)),
        SourceRule("Component alt", ("COMPONENT_INPUT_ALT",)),
        SourceRule("Amazon", ("AMAZON",)),
        SourceRule("Amazon Prime", ("AMAZON_PRIME",)),
        SourceRule("Netflix", ("NETFLIX",)),
        SourceRule("Hulu", ("HULU",)),
        SourceRule("Vudu", ("VUDU",)),
        SourceRule("Xumo", ("XUMO",)),
        SourceRule("WatchFree", ("WATCHFREE",)),
        SourceRule("Crackle", ("CRACKLE",)),
        SourceRule("iHeartRadio", ("IHEARTRADIO",)),
        SourceRule("M-GO", ("MGO",)),
        SourceRule("Browser", ("BROWSER",)),
    ),
)
