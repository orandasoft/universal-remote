"""Generic Universal Remote device profile."""

from ..const import DEVICE_TYPE_GENERIC
from .base import DeviceProfile

PROFILE_GENERIC = DEVICE_TYPE_GENERIC

GENERIC_PROFILE = DeviceProfile(
    profile_id=PROFILE_GENERIC,
    device_type=DEVICE_TYPE_GENERIC,
    device_type_label="Generic remote",
)
