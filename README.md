# Universal Remote

Universal Remote is a Home Assistant custom integration that creates logical infrared remote devices backed by existing Home Assistant `infrared` emitters and receivers.

It does not communicate with infrared hardware directly. Instead, it uses `infrared` emitter and receiver entities provided by other Home Assistant integrations. Universal Remote stores named infrared commands, asks the linked infrared emitter to transmit them, and can listen to a linked infrared receiver to expose matched received commands as Home Assistant events.

This makes it possible to use one infrared transmitter or receiver for multiple logical remotes, such as TVs, projectors, HDMI switches, or other infrared-controlled devices.

> This is a Home Assistant integration for HACS. It is not the Universal Remote Card dashboard plugin.


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

- Home Assistant 2026.6.0 or newer
- HACS
- Another Home Assistant integration that provides one or more `infrared` emitter or receiver entities

The linked infrared emitter is responsible for the actual infrared transmission. Universal Remote only manages the logical remote, command names, optional buttons, optional TV media player entity, and optional received-command event entity.

Universal Remote can be configured with an infrared emitter, an infrared receiver, or both. Sending commands requires an infrared emitter. Receiving command events requires an infrared receiver. A supported codeset enables friendly named events such as `power` or `volume_up`; otherwise, decoded NEC-family commands are exposed as `nec` events with decoded address and command data.

---

## Installation

### Install with HACS

1. Open HACS in Home Assistant.
2. Open the three-dot menu.
3. Select **Custom repositories**.
4. Add this repository URL:

   ```text
   https://github.com/orandasoft/universal-remote
   ```

5. Select category **Integration**.
6. Click **Add**.
7. Search for **Universal Remote** in HACS.
8. Download the integration.
9. Restart Home Assistant.

After restarting, add the integration from:

```text
Settings → Devices & services → Add integration → Universal Remote
```

### Manual installation

Copy the integration folder:

```text
custom_components/universal_remote
```

to your Home Assistant configuration directory:

```text
/config/custom_components/universal_remote
```

Then restart Home Assistant.

---

## Configuration

After installation, add a new Universal Remote from the Home Assistant integrations page.

During setup, select:

- a remote name
- an infrared emitter, an infrared receiver, or both
- the device type
- optional commands or library codeset commands

At least one infrared target must be selected. Select an infrared emitter when you want Universal Remote to send commands. Select an infrared receiver when you want Universal Remote to expose received command events.

A supported codeset is required for named receiver events. Without one, decoded NEC-family commands are still available as `nec` events with decoded address and command data.

Multiple Universal Remote config entries may use the same infrared emitter or receiver. This allows one physical IR blaster or receiver to be shared by multiple logical devices.

---

## Entities

Depending on the configured infrared targets, Universal Remote can create the following entities:

- a `remote` entity when an infrared emitter is configured
- `button` entities for selected commands when an infrared emitter is configured
- a `media_player` entity for TV remotes when an infrared emitter is configured
- a `select` entity for tuner selection when TV tuner support is detected
- an `event` entity for received commands when an infrared receiver is configured

The TV media player is assumed-state. It does not know the real power, volume, channel, source, or playback state of the physical device, although it may update assumed power and source state after commands are sent through Universal Remote.

The received-command event entity emits events when the linked infrared receiver receives a signal. Matched codeset commands use friendly event types such as `power` or `volume_up`. Decoded NEC commands that do not match the selected codeset are reported as `nec` with decoded address and command data. Signals that cannot be decoded are reported as `unknown`.

---

## Device types and codesets

Universal remotes can be configured as a generic remote or as a supported device type such as TV.

The device type controls which device-oriented entities can be created. For example, TV remotes with an infrared emitter can create a TV `media_player` entity.

A codeset is an optional infrared command library profile for sending, but it is required when configuring an infrared receiver. Codesets are filtered by device type and can be used to import commands during setup or later from the options flow.

Supported TV codesets include:

- LG TV
- LG TV Japan
- Samsung TV
- Sharp AQUOS TV
- Vizio TV

Protocol decoding currently supports NEC-family protocols. Friendly named receiver events and command matching are currently available for supported NEC-based codesets such as LG TV, LG TV Japan, and Vizio TV. Other codesets may still be used for command import and sending, but may not yet support named receiver events.

---

## Commands

Commands are named infrared payloads. Command names are normalized to uppercase with underscores.

Examples:

```text
POWER_ON
POWER_OFF
VOLUME_UP
VOLUME_DOWN
MUTE
HDMI_1
```

Supported command payload formats include:

- Pronto Hex
- raw timing lists
- raw timing objects
- text-based timing formats

Commands may also be imported from a supported Home Assistant infrared protocols library codeset.

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

You can send a command through the normal Home Assistant `remote.send_command` service.

Example:

```yaml
action: remote.send_command
target:
  entity_id: remote.living_room_tv
data:
  command: POWER_ON
```

You can also send multiple commands:

```yaml
action: remote.send_command
target:
  entity_id: remote.living_room_tv
data:
  command:
    - POWER_ON
    - HDMI_1
```

---

## Receiving commands

Receiving commands requires a configured infrared receiver.

A supported codeset enables friendly named events such as `power` or `volume_up`. Without one, decoded NEC-family commands are still available as `nec` events with decoded address and command data.

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

The `nec` event type includes decoded address and command data. This allows automations to react to NEC commands from a physical universal remote even when those commands are not part of the selected codeset.

Signals that cannot be decoded are reported as:

```text
unknown
```

The event entity also exposes a small `recent_events` history attribute with the most recent received event summaries. This is intended for debugging receiver behavior, repeat frames, and unmatched decoded commands. Raw timings are not stored in this history.

Example automation for an unmatched decoded NEC command:

```yaml
trigger:
  - platform: state
    entity_id: event.lg_tv_received_command

condition:
  - condition: template
    value_template: >
      {{ trigger.to_state.attributes.event_type == 'nec'
         and trigger.to_state.attributes.address == 4
         and trigger.to_state.attributes.command == 99 }}

action:
  - action: light.toggle
    target:
      entity_id: light.living_room
```

Receiving infrared signals does not automatically create or update commands. New commands are added only through the Learn Command workflow, where the captured signal can be reviewed, tested, and explicitly saved.

---

## Button entities

Command button entities are optional and require a configured infrared emitter.

When adding or importing commands, the flow can create Home Assistant `button` entities for selected commands. Pressing a button sends the stored infrared command through the linked infrared emitter.

---

## TV media player

TV remotes with an infrared emitter create a `media_player` entity.

The media player exposes supported features based on the commands configured for the remote.

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

The tuner select entity is created only when tuner support is detected from configured commands. A tuner is considered available only when both of the following exist:

- the tuner selector command, such as `BS`
- at least one same-tuner numeric command, such as `BS_NUM_1`

Generic numeric commands such as `NUM_1` do not make a tuner available by themselves. For example, `BS` plus `NUM_1` is not enough to expose `BS` as an available tuner. `BS` plus `BS_NUM_1` is enough.

When a tuner is selected, generic numeric commands `NUM_1` through `NUM_12` are resolved to the selected tuner-specific command when one exists. For example, after selecting `BS`, sending `NUM_1` sends `BS_NUM_1` if that command is configured.

This tuner-aware command resolution is shared by the `remote`, `button`, TV `media_player`, and tuner `select` entities. Raw infrared payload fallback remains limited to `remote.send_command`.

When a configured infrared receiver and supported codeset are used, matched non-repeat received tuner commands can update the selected tuner state. Repeat frames do not update tuner state.

## Availability and repairs

Universal Remote send entities are available when the linked infrared emitter exists and is available.

If the linked infrared emitter is missing or unavailable, the integration creates a repair issue to help update the configuration.

If a configured infrared receiver is missing, the integration creates a repair issue for the missing receiver. The received-command event entity is only created when the linked receiver exists.

---

## Diagnostics

Diagnostics are available from the Home Assistant device/integration diagnostics UI.

Diagnostics are intended to help troubleshoot configuration issues without exposing full infrared command payloads. Receiver diagnostics include whether a receiver event entity is expected, whether the selected codeset supports receiver decoding, the receiver decoder id, and the number of exposed receiver event types.

---

## Known limitations

- Received infrared signals are not learned or stored automatically. New commands can be created only through the explicit Learn Command workflow.
- Received command history is capped and stores decoded summaries only, not raw timings.
- Universal Remote does not transmit infrared commands directly.
- The linked `infrared` integration is responsible for hardware communication.
- Sending commands requires a linked infrared emitter.
- Receiving command events requires a linked infrared receiver. A supported codeset enables named command events such as `power` or `volume_up`; otherwise, decoded NEC-family commands are exposed as `nec` events with decoded address and command data.
- Friendly named receiver events are currently limited to supported codesets; unmatched NEC-family commands are exposed as `nec` events.
- The TV media player is assumed-state and does not reflect real device state.
- The tuner select entity is created only when tuner-specific command support is detected.
- Existing commands are not deleted automatically when changing device type or codeset.
- Availability depends on the linked infrared emitter or receiver.

---

## Development

Create a Python virtual environment and install development dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run tests:

```bash
pytest
```

Run a syntax check:

```bash
python3 -m compileall -f custom_components/universal_remote tests
```

Run Ruff:

```bash
ruff check custom_components/universal_remote tests
```

Run mypy:

```bash
mypy custom_components/universal_remote tests
```

---

## Repository

GitHub:

```text
https://github.com/orandasoft/universal-remote
```

Issues:

```text
https://github.com/orandasoft/universal-remote/issues
```
