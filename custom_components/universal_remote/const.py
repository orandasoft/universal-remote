"""Constants for the Universal Remote integration."""

DOMAIN = "universal_remote"

CONF_INFRARED_EMITTER_ID = "infrared_emitter_id"
CONF_INFRARED_RECEIVER_ID = "infrared_receiver_id"
CONF_REMOTE_CODESET = "codeset"
CONF_REMOTE_DEVICE_TYPE = "device_type"
CONF_REMOTE_COMMANDS = "commands"
CONF_REMOTE_ID = "id"
CONF_REMOTE_NAME = "name"

CONF_COMMAND_DATA = "data"
CONF_COMMAND_CREATE_BUTTON = "create_button"

DEVICE_TYPE_GENERIC = "generic"
DEVICE_TYPE_TV = "tv"

DEFAULT_DELAY_SECS = 0.4
DEFAULT_NUM_REPEATS = 1

ISSUE_LINKED_INFRARED_EMITTER_MISSING = "linked_infrared_emitter_missing"
ISSUE_LINKED_INFRARED_RECEIVER_MISSING = "linked_infrared_receiver_missing"

TV_SOURCE_COMMAND_MAP = {
    "TV": "TV",
    "TV input": "TV_INPUT",
    "DTV": "DTV",
    "BS": "BS",
    "BS4K": "BS4K",
    "CS1": "CS1",
    "CS2": "CS2",
    "CS4K": "CS4K",
    "Input": "INPUT",
    "Source": "SOURCE",
    "Next HDMI input": "NEXT_HDMI_INPUT",
    "HDMI 1": "HDMI_1",
    "HDMI 2": "HDMI_2",
    "HDMI 3": "HDMI_3",
    "HDMI 4": "HDMI_4",
    "HDMI 5": "HDMI_5",
    "Component": "COMPONENT_INPUT",
    "Component alt": "COMPONENT_INPUT_ALT",
    "Amazon": "AMAZON",
    "Amazon Prime": "AMAZON_PRIME",
    "Netflix": "NETFLIX",
    "Hulu": "HULU",
    "Vudu": "VUDU",
    "Xumo": "XUMO",
    "WatchFree": "WATCHFREE",
    "Crackle": "CRACKLE",
    "iHeartRadio": "IHEARTRADIO",
    "M-GO": "MGO",
    "Browser": "BROWSER",
}

SOURCE_COMMAND_MAPS = {
    DEVICE_TYPE_TV: TV_SOURCE_COMMAND_MAP,
}
