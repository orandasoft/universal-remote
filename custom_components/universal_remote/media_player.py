"""Media player entities for Universal Remote devices."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_INFRARED_EMITTER_ID,
    CONF_REMOTE_COMMANDS,
    CONF_REMOTE_ID,
    CONF_REMOTE_NAME,
    DOMAIN,
)
from .helpers import (
    linked_entity_is_available,
    normalize_command_name,
    normalize_command_objects,
    universal_remote_device_info,
    universal_remotes_from_config_entry,
)
from .profiles import (
    DeviceProfile,
    profile_role_commands,
    profile_source_commands,
)
from .runtime import UniversalRemoteConfigEntry, UniversalRemoteRuntime

PARALLEL_UPDATES = 1


def media_player_unique_id(entry_id: str, remote_id: str) -> str:
    """Return the unique id for a universal remote media player."""
    return f"{entry_id}_media_player_{remote_id}"


@callback
def cleanup_stale_media_player_entities(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
    expected_unique_ids: set[str],
) -> None:
    """Remove stale Universal Remote media player entity registry entries."""
    entity_registry = er.async_get(hass)
    unique_id_prefix = f"{entry.entry_id}_media_player_"

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry,
        entry.entry_id,
    ):
        if entity_entry.domain != "media_player":
            continue

        unique_id = entity_entry.unique_id
        if (
            isinstance(unique_id, str)
            and unique_id.startswith(unique_id_prefix)
            and unique_id not in expected_unique_ids
        ):
            entity_registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UniversalRemoteConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Universal Remote media players from a config entry."""
    entities: list[UniversalRemoteTvMediaPlayer] = []
    expected_unique_ids: set[str] = set()

    runtime_data = entry.runtime_data
    runtime = runtime_data.runtime
    resolved_profile = runtime_data.resolved_profile
    profile = resolved_profile.profile if resolved_profile is not None else None

    for remote in universal_remotes_from_config_entry(entry):
        if profile is None or not profile.supports_entity(MEDIA_PLAYER_DOMAIN):
            continue

        remote_id = remote.get(CONF_REMOTE_ID)
        remote_name = remote.get(CONF_REMOTE_NAME)
        infrared_emitter_id = remote.get(CONF_INFRARED_EMITTER_ID)

        if (
            not isinstance(remote_id, str)
            or not remote_id
            or not isinstance(remote_name, str)
            or not remote_name
            or not isinstance(infrared_emitter_id, str)
            or not infrared_emitter_id
        ):
            continue

        assert runtime is not None

        unique_id = media_player_unique_id(entry.entry_id, remote_id)
        expected_unique_ids.add(unique_id)
        entities.append(
            UniversalRemoteTvMediaPlayer(
                remote_id=remote_id,
                remote_name=remote_name,
                infrared_emitter_id=infrared_emitter_id,
                commands=normalize_command_objects(
                    remote.get(CONF_REMOTE_COMMANDS, {})
                ),
                unique_id=unique_id,
                profile=profile,
                runtime=runtime,
            )
        )

    cleanup_stale_media_player_entities(hass, entry, expected_unique_ids)
    async_add_entities(entities)


class UniversalRemoteTvMediaPlayer(MediaPlayerEntity):
    """Assumed-state TV media player backed by Universal Remote commands."""

    _attr_assumed_state = True
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_state = MediaPlayerState.ON
    _attr_is_volume_muted = False

    def __init__(
        self,
        *,
        remote_id: str,
        remote_name: str,
        infrared_emitter_id: str,
        commands: Mapping[str, Mapping[str, Any]],
        unique_id: str,
        profile: DeviceProfile,
        runtime: UniversalRemoteRuntime,
    ) -> None:
        """Initialize the Universal Remote TV media player."""
        self._remote_id = remote_id
        self._infrared_emitter_id = infrared_emitter_id
        self._runtime = runtime
        self._commands = normalize_command_objects(commands)
        self._source_commands = profile_source_commands(
            profile,
            self._commands,
        )
        self._role_commands = profile_role_commands(
            profile,
            self._commands,
        )
        self._tuner_sources: dict[str, str] = {}
        for source, command_name in self._source_commands.items():
            tuner_id = runtime.tuner_id_for_command_name(command_name)
            if tuner_id is None:
                tuner_id = normalize_command_name(command_name)
            self._tuner_sources.setdefault(tuner_id, source)

        self._attr_unique_id = unique_id
        self._attr_device_info = universal_remote_device_info(remote_id, remote_name)
        self._attr_source_list = list(self._source_commands) or None
        self._attr_source = None
        self._attr_supported_features = _supported_features(
            self._role_commands,
            self._source_commands,
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity added to Home Assistant."""

        @callback
        def _handle_infrared_state_change(event: Any) -> None:
            """Handle linked infrared entity state changes."""
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._infrared_emitter_id],
                _handle_infrared_state_change,
            )
        )

        runtime = self._runtime

        @callback
        def _handle_tuner_state_change() -> None:
            """Handle runtime tuner state changes."""
            selected_tuner = runtime.selected_tuner
            if selected_tuner is None:
                return

            source = self._tuner_sources.get(selected_tuner)
            if source is None or self._attr_source == source:
                return

            self._attr_source = source
            self.async_write_ha_state()

        self.async_on_remove(
            runtime.async_add_tuner_listener(_handle_tuner_state_change)
        )

    @property
    def available(self) -> bool:
        """Return whether the backing infrared emitter is available."""
        hass = getattr(self, "hass", None)
        if hass is None:
            return True

        return linked_entity_is_available(hass, self._infrared_emitter_id)

    async def async_turn_on(self) -> None:
        """Turn on the TV."""
        await self._send_role("turn_on")
        self._attr_state = MediaPlayerState.ON
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn off the TV."""
        await self._send_role("turn_off")
        self._attr_state = MediaPlayerState.OFF
        self.async_write_ha_state()

    async def async_volume_up(self) -> None:
        """Send volume up command."""
        await self._send_role("volume_up")

    async def async_volume_down(self) -> None:
        """Send volume down command."""
        await self._send_role("volume_down")

    async def async_mute_volume(self, mute: bool) -> None:
        """Set the assumed mute state."""
        if self._attr_is_volume_muted == mute:
            return

        await self._send_role("mute")
        self._attr_is_volume_muted = mute
        self.async_write_ha_state()

    async def async_media_next_track(self) -> None:
        """Send channel up command."""
        await self._send_role("channel_up")

    async def async_media_previous_track(self) -> None:
        """Send channel down command."""
        await self._send_role("channel_down")

    async def async_media_play(self) -> None:
        """Send play command."""
        await self._send_role("play")

    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self._send_role("pause")

    async def async_media_stop(self) -> None:
        """Send stop command."""
        await self._send_role("stop")

    async def async_select_source(self, source: str) -> None:
        """Select a source by sending the matching command."""
        if (command_name := self._source_commands.get(source)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="media_player_source_unavailable",
                translation_placeholders={"source": source},
            )

        await self._send_command_name(command_name)
        self._attr_source = source
        self.async_write_ha_state()

    async def _send_role(self, role: str) -> None:
        """Send the command mapped to a media-player role."""
        if (command_name := self._role_commands.get(role)) is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="media_player_role_unavailable",
                translation_placeholders={"role": role},
            )
        await self._send_command_name(command_name)

    async def _send_command_name(self, command_name: str) -> None:
        """Send a configured command by name."""
        await self._runtime.async_send_command_name(command_name)


def _supported_features(
    roles: Mapping[str, str],
    sources: Mapping[str, str],
) -> MediaPlayerEntityFeature:
    """Return supported media-player features for configured commands."""
    features = MediaPlayerEntityFeature(0)

    if "turn_on" in roles:
        features |= MediaPlayerEntityFeature.TURN_ON
    if "turn_off" in roles:
        features |= MediaPlayerEntityFeature.TURN_OFF
    if "volume_up" in roles and "volume_down" in roles:
        features |= MediaPlayerEntityFeature.VOLUME_STEP
    if "mute" in roles:
        features |= MediaPlayerEntityFeature.VOLUME_MUTE
    if "channel_up" in roles:
        features |= MediaPlayerEntityFeature.NEXT_TRACK
    if "channel_down" in roles:
        features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
    if "play" in roles:
        features |= MediaPlayerEntityFeature.PLAY
    if "pause" in roles:
        features |= MediaPlayerEntityFeature.PAUSE
    if "stop" in roles:
        features |= MediaPlayerEntityFeature.STOP
    if sources:
        features |= MediaPlayerEntityFeature.SELECT_SOURCE

    return features
