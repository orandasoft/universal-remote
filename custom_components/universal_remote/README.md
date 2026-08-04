# Universal Remote

The Universal Remote integration creates logical infrared remote devices backed by existing Home Assistant `infrared` emitters and receivers.

It does not communicate with infrared hardware directly. Instead, it uses `infrared` emitter and receiver entities provided by other Home Assistant integrations. Universal Remote stores named infrared commands, asks the linked infrared emitter to transmit them, and can listen to a linked infrared receiver to expose matched received commands as Home Assistant events.

This makes it possible to use one infrared transmitter or receiver for multiple logical remotes, such as TVs, projectors, HDMI switches, or other infrared-controlled devices.


---

## What's New in v0.6.0

- Learn infrared commands directly from a linked infrared receiver.
- Review both the captured signal and a normalized (recommended) command when supported.
- Store learned commands as Pronto Hex.
- Test learned commands before saving.
- Import commands from supported infrared library codesets.
- Improved NEC / NEC1-F16 decoding and Japanese TV tuner support.

---

## Requirements

Universal Remote requires:

- Home Assistant 2026.6.0 or newer
- Another Home Assistant integration that provides one or more `infrared` emitter or receiver entities

The linked infrared emitter is responsible for the actual infrared transmission. Universal Remote only manages the logical remote, command names, optional buttons, optional TV media player entity, and optional received-command event entity.

Universal Remote can be configured with an infrared emitter, an infrared receiver, or both. Sending commands requires an infrared emitter. Receiving command events requires an infrared receiver. A supported codeset enables friendly named events such as `power` or `volume_up`. When its decoder family recognizes a command that does not match a named codeset member, the event uses the protocol type, such as `nec` or `nec1_f16`. Without a supported codeset, received signals are reported as `unknown` events with timing metadata.

---

## Entities

Depending on the configured infrared targets, Universal Remote can create:

- a `remote` entity when an infrared emitter is configured
- `button` entities for commands where button creation is enabled, when an infrared emitter is configured
- a `media_player` entity for TV remotes when an infrared emitter is configured
- a `select` entity for tuner selection when the resolved remote has an available tuner capability
- an `event` entity for received commands when an infrared receiver is configured

The TV media player is assumed-state. It does not know the real power, volume, channel, source, or playback state of the physical device, although it may update assumed power and source state after commands are sent through Universal Remote.

The received-command event entity emits events when the linked infrared receiver receives a signal. Matched codeset commands use friendly event types such as `power` or `volume_up`. Decoded NEC commands that do not match the selected codeset are reported as `nec` with decoded address and command data. Signals that cannot be decoded are reported as `unknown`.

---

## Device types and codesets

Universal remotes can be configured as a generic remote or as a supported device type such as TV.

Device type controls which device-oriented entities can be created. For example, TV remotes with an infrared emitter create a TV `media_player` entity.

A codeset identifies a supported infrared command library and may also supply the integration's semantic binding for the remote, including its device profile, receive decoder family, and optional capabilities. A codeset is optional for sending and receiving, but a supported codeset is required for friendly named receiver-event matching and protocol-level decoding. Without one, received signals are reported as `unknown` events with timing metadata. Codesets are filtered by device type and can be used to import commands during setup or later from the options flow.

Supported TV codesets include:

- LG TV
- LG TV Japan
- Samsung TV
- Sharp AQUOS TV
- Vizio TV

The **LG TV Japan** codeset (`lg_tv_jp`) resolves to the TV profile and adds the regional `japanese_tuner` capability. Other TV codesets and manually configured TV remotes do not gain Japanese tuner behavior merely from commands with similar names.

Protocol decoding currently supports NEC-family protocols. Friendly named receiver events and command matching are currently available for supported NEC-based codesets such as LG TV, LG TV Japan, and Vizio TV. Other codesets may still be used for command import and sending, but may not yet support named receiver events.

---

## Commands

Commands are named infrared payloads. Command names are normalized to uppercase with underscores.

Supported command payload formats include:

- Pronto Hex
- raw timing lists
- raw timing objects
- text-based timing formats

Commands may also be imported from a supported infrared library codeset.

Imported library commands are converted to Pronto Hex and stored with the Universal Remote configuration. Updating Universal Remote or the `infrared-protocols` dependency does not automatically regenerate commands that were imported previously. Import the codeset again when you intentionally want to replace stored commands with the current library definitions.

---

## Learning commands

Universal Remote can learn infrared commands when a compatible infrared receiver is configured.

The learning workflow captures a received infrared signal, validates it, and presents one or two candidates:

- **Captured** — the original received signal stored as Pronto Hex.
- **Normalized (recommended)** — a protocol-aware reconstruction generated when the captured signal can be decoded by a supported decoder (currently NEC or NEC1-F16).

You can test either candidate before saving. Learned commands become regular Universal Remote commands and can optionally create button entities.

Learning is separate from receiver events. Learning saves new commands; receiver events report received commands for automations.

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

Receiving commands requires a configured infrared receiver.

A supported codeset enables friendly named events such as `power` or `volume_up`. When the selected codeset's decoder family recognizes a command that does not match a named codeset member, the event uses the protocol type, such as `nec` or `nec1_f16`, with decoded protocol data. Without a supported codeset, received signals are reported as `unknown` events with timing metadata.

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

Signals that cannot be decoded by the selected codeset's decoder family, and signals received without a supported codeset, are reported as:

```text
unknown
```

The event entity also exposes a small `recent_events` history attribute with the most recent received event summaries. This is intended for debugging receiver behavior, repeat frames, and unmatched decoded commands. Raw timings are not stored in this history.

Receiving infrared signals does not automatically create or update commands. New commands are added only through the Learn Command workflow, where the captured signal can be reviewed, tested, and explicitly saved.

---

## Buttons

Command button entities are optional and require a configured infrared emitter.

When adding or importing commands, the flow can create button entities for those commands.

Buttons are regular Home Assistant `button` entities. Pressing a button sends the stored infrared command through the linked infrared emitter.

When the resolved device profile or capability supplies command presentation information, button labels and icons use it before falling back to generic command-name formatting.

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

Source support is resolved from the TV profile and the commands configured for the remote.

Commands such as `TV`, `TV_INPUT`, `DTV`, `BS`, `BS4K`, `CS1`, `CS2`, `CS4K`, `INPUT`, `SOURCE`, `HDMI_1`, `HDMI_2`, `HDMI_3`, `HDMI_4`, and `HDMI_5` may appear as selectable sources when they are configured for the remote. Component inputs and app shortcuts such as `NETFLIX` or `AMAZON_PRIME` may also appear when supported by the selected codeset.

Because the media player is assumed-state, it sends commands but does not receive real state feedback from the physical device. Source selection updates the assumed source in Home Assistant after Universal Remote sends the selected source command.

---

## Japanese TV tuner support

Japanese tuner behavior is enabled by the resolved `japanese_tuner` capability. The supported **LG TV Japan** codeset (`lg_tv_jp`) resolves the remote to the TV profile and attaches this capability.

Selecting TV as the device type and manually adding commands named `DTV`, `BS`, `CS1`, `CS2`, `BS4K`, `CS4K`, or `BS_NUM_1` does not enable Japanese tuner behavior by itself. Other TV codesets do not receive this regional capability.

The Japanese tuner capability declares these tuner families:

- `DTV`
- `BS`
- `CS1`
- `CS2`
- `BS4K`
- `CS4K`

It also declares numeric values 1 through 12.

The tuner `select` entity is created only when at least one capability-declared tuner is available. A tuner is considered available when both of the following commands are configured:

- its selector command, such as `BS`
- at least one same-tuner numeric command, such as `BS_NUM_1`

A generic numeric command such as `NUM_1` does not make a tuner available. For example, `BS` plus `NUM_1` is not enough to expose `BS`; `BS` plus `BS_NUM_1` is enough.

When a tuner is selected, a generic numeric command is routed to the corresponding tuner-specific command when the number is declared by the capability and that command is configured. For example, after selecting `BS`, sending `NUM_1` sends `BS_NUM_1` when `BS_NUM_1` exists.

The same capability-driven runtime is shared by the `remote`, `button`, TV `media_player`, and tuner `select` entities. This keeps selected tuner state and command routing synchronized across those entities. Raw infrared payload fallback remains limited to `remote.send_command`.

When a configured infrared receiver and supported codeset are used, matched non-repeat tuner selector or tuner-number commands can update the selected tuner state according to the capability's receive-update policy. Repeat frames do not update tuner state. When the selected tuner is also exposed as a TV media-player source, the assumed source is synchronized.

## Availability and repairs

Universal Remote send entities are available when the linked infrared emitter exists and is available.

If the linked infrared emitter is missing or unavailable, the integration creates a repair issue to help the user update the configuration.

If a configured infrared receiver is missing, the integration creates a repair issue for the missing receiver. The received-command event entity remains registered with its existing entity identity, but it cannot receive events until the linked receiver is restored.

---

## Diagnostics

Diagnostics are available from the Home Assistant device/integration diagnostics UI.

Diagnostics are intended to help troubleshoot configuration issues without exposing full infrared command payloads. Receiver diagnostics include whether a receiver event entity is expected, whether the selected codeset supports receiver decoding, the receiver decoder id, and the number of exposed receiver event types.

---

## Notes

- Multiple universal remote config entries may share the same infrared emitter or receiver.
- Existing commands are not deleted automatically when changing device type or codeset.
- Infrared transmission and receiving are handled by the linked infrared integration.
- Received infrared signals are not learned or stored automatically. New commands can be created only through the explicit Learn Command workflow.
- Received command history is capped and stores decoded summaries only, not raw timings.
- Sending commands requires a linked infrared emitter.
- Receiving command events requires a linked infrared receiver. A supported codeset enables named events and protocol-level decoding; without one, received signals are reported as `unknown` events with timing metadata.
- The tuner select entity is created only when the resolved tuner capability has at least one available tuner.
- Friendly named receiver events are limited to supported codesets. Commands decoded by the selected codeset's NEC-family decoder but not matched to a named member are exposed as `nec` or `nec1_f16` events.
