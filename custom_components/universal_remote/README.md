# Universal Remote

The Universal Remote integration creates logical infrared remote devices backed by existing Home Assistant infrared emitters and receivers.

A universal remote does not communicate with infrared hardware directly. It stores named infrared commands and asks the linked infrared emitter to transmit them. It can also listen to a linked infrared receiver and expose matched received commands as Home Assistant events.

This makes it possible to use one infrared transmitter or receiver for multiple logical remotes, such as TVs, projectors, HDMI switches, or other infrared-controlled devices.

---

## Requirements

Universal Remote requires:

- Home Assistant 2026.6.0 or newer
- At least one Home Assistant infrared emitter or infrared receiver from another integration
- Compatible infrared transmitter or receiver hardware supported by that infrared integration

The linked infrared emitter is responsible for transmitting infrared commands through compatible hardware such as IR blasters or infrared emitters. The linked infrared receiver is responsible for receiving infrared signals from compatible receiver hardware.

Universal Remote can be configured with an infrared emitter, an infrared receiver, or both. Sending commands requires an infrared emitter. Receiving and matching infrared commands requires an infrared receiver and a supported codeset.

---

## Entities

Depending on the configured infrared targets, Universal Remote can create:

- a `remote` entity when an infrared emitter is configured
- `button` entities for commands where button creation is enabled, when an infrared emitter is configured
- a `media_player` entity for TV remotes when an infrared emitter is configured
- a `select` entity for tuner selection when TV tuner support is detected
- an `event` entity for received commands when an infrared receiver is configured

The TV media player is assumed-state. It does not know the real power, volume, channel, source, or playback state of the physical device, although it may update assumed power and source state after commands are sent through Universal Remote.

The received-command event entity emits events when the linked infrared receiver receives a signal. Matched codeset commands use friendly event types such as `power` or `volume_up`. Decoded NEC commands that do not match the selected codeset are reported as `nec` with decoded address and command data. Signals that cannot be decoded are reported as `unknown`.

---

## Device types and codesets

Universal remotes can be configured as a generic remote or as a supported device type such as TV.

Device type controls which device-oriented entities can be created. For example, TV remotes with an infrared emitter create a TV `media_player` entity.

A codeset is an optional infrared command library profile for sending, but it is required when configuring an infrared receiver. Codesets are filtered by device type and can be used to import commands during setup or later from the options flow.

Supported TV codesets include:

- LG TV
- LG TV Japan
- Samsung TV
- Sharp AQUOS TV
- Vizio TV

Receiver command matching is currently supported for NEC-based codesets such as LG TV, LG TV Japan, and Vizio TV. Other codesets may still be used for command import and sending, but may not support received-command matching yet.

---

## Commands

Commands are named infrared payloads. Command names are normalized to uppercase with underscores.

Supported command payload formats include:

- Pronto Hex
- raw timing lists
- raw timing objects
- text-based timing formats

Commands may also be imported from a supported infrared library codeset.

---

## Sending commands

Sending commands requires a configured infrared emitter.

The `remote.send_command` service can send configured command names or a raw infrared payload supported by the linked infrared emitter. Raw payload fallback is intentionally limited to `remote.send_command`.

Button entities and TV media player controls send configured commands only. A button sends its stored command. Media player controls send the configured command mapped to the selected role or source.

Use the standard Home Assistant `remote.send_command` service:

```yaml
action: remote.send_command
target:
  entity_id: remote.living_room_tv
data:
  command: POWER_ON
```

---

## Receiving commands

Receiving commands requires a configured infrared receiver and a supported codeset.

When a supported received signal matches a known codeset command, Universal Remote exposes it through a Home Assistant `event` entity. The event type is the normalized command name in lowercase, for example:

```text
power
volume_up
hdmi_1
```

Matched events also include decoded receiver data such as protocol, decoder, address, command, matched status, and command name.

Decoded NEC commands that do not match the selected codeset are reported with the stable event type:

```text
nec
```

The `nec` event type includes decoded address and command data. This allows automations to react to NEC commands from a physical universal remote even when those commands are not part of the selected TV codeset.

Signals that cannot be decoded are reported as:

```text
unknown
```

The event entity also exposes a small `recent_events` history attribute with the most recent received event summaries. This is intended for debugging receiver behavior, repeat frames, and unmatched decoded commands. Raw timings are not stored in this history.

Universal Remote does not learn and save new commands from received infrared signals. Received signals are used only for event reporting.

---

## Buttons

Command button entities are optional and require a configured infrared emitter.

When adding or importing commands, the flow can create button entities for those commands.

Buttons are regular Home Assistant `button` entities. Pressing a button sends the stored infrared command through the linked infrared emitter.

---

## TV media player

TV remotes with an infrared emitter create a `media_player` entity.

The media player exposes supported features based on the commands configured for the universal remote.

Examples:

- `POWER_ON` enables turn on.
- `POWER_OFF` enables turn off.
- `VOLUME_UP` and `VOLUME_DOWN` enable volume step.
- `MUTE` enables mute.
- `CHANNEL_UP` and `CHANNEL_DOWN` enable channel controls.
- `PLAY`, `PAUSE`, and `STOP` enable playback controls.
- Supported source commands can appear in the media player source list.

Source support is derived from configured command names.

Commands such as `TV`, `TV_INPUT`, `DTV`, `BS`, `BS4K`, `CS1`, `CS2`, `CS4K`, `INPUT`, `SOURCE`, `HDMI_1`, `HDMI_2`, `HDMI_3`, `HDMI_4`, and `HDMI_5` may appear as selectable sources when they are configured for the remote. Component inputs and app shortcuts such as `NETFLIX` or `AMAZON_PRIME` may also appear when supported by the selected codeset.

Because the media player is assumed-state, it sends commands but does not receive real state feedback from the physical device. Source selection updates the assumed source in Home Assistant after Universal Remote sends the selected source command.

---

## Japanese TV tuner support

Universal Remote can expose a tuner `select` entity for TV command sets that include Japanese tuner families such as `DTV`, `BS`, `CS1`, `CS2`, `BS4K`, or `CS4K`.

The tuner select entity is created only when tuner support is detected from configured commands. A tuner is considered available only when both the tuner selector command and at least one same-tuner numeric command are configured. For example, `BS` plus `BS_NUM_1` exposes `BS`; `BS` plus generic `NUM_1` does not.

When a tuner is selected, generic numeric commands `NUM_1` through `NUM_12` are resolved to the selected tuner-specific command when one exists. For example, after selecting `BS`, sending `NUM_1` sends `BS_NUM_1` if that command is configured.

This tuner-aware command resolution is shared by the `remote`, `button`, TV `media_player`, and tuner `select` entities. Raw infrared payload fallback remains limited to `remote.send_command`.

When a configured infrared receiver and supported codeset are used, matched non-repeat received tuner commands can update the selected tuner state. Repeat frames do not update tuner state.

## Availability and repairs

Universal Remote send entities are available when the linked infrared emitter exists and is available.

If the linked infrared emitter is missing or unavailable, the integration creates a repair issue to help the user update the configuration.

If a configured infrared receiver is missing, the integration creates a repair issue for the missing receiver. The received-command event entity is only created when the linked receiver exists.

---

## Diagnostics

Diagnostics are available from the Home Assistant device/integration diagnostics UI.

Diagnostics are intended to help troubleshoot configuration issues without exposing full infrared command payloads. Receiver diagnostics include whether a receiver event entity is expected, whether the selected codeset supports receiver decoding, the receiver decoder id, and the number of exposed receiver event types.

---

## Notes

- Multiple universal remote config entries may share the same infrared emitter or receiver.
- Existing commands are not deleted automatically when changing device type or codeset.
- Infrared transmission and receiving are handled by the linked infrared integration.
- Universal Remote does not learn or store new infrared commands from received signals.
- Received command history is capped and stores decoded summaries only, not raw timings.
- Sending commands requires a linked infrared emitter.
- Receiving command events requires a linked infrared receiver and a supported codeset.
- The tuner select entity is created only when tuner-specific command support is detected.
- Receiver decoding is currently limited to supported codesets.
