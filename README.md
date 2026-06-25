# Universal Remote

Universal Remote is a Home Assistant custom integration that creates logical infrared remote devices backed by existing Home Assistant `infrared` emitters and receivers.

It does not communicate with infrared hardware directly. Instead, it stores named infrared commands and asks the linked infrared emitter to transmit them. It can also listen to a linked infrared receiver and expose matched received commands as Home Assistant events.

This makes it possible to use one infrared transmitter or receiver for multiple logical remotes, such as TVs, projectors, HDMI switches, or other infrared-controlled devices.

> This is a Home Assistant integration for HACS. It is not the Universal Remote Card dashboard plugin.

---

## Requirements

- Home Assistant 2026.6.0 or newer
- HACS
- At least one Home Assistant infrared emitter or infrared receiver from another integration
- Compatible infrared transmitter or receiver hardware supported by that infrared integration

The linked infrared emitter is responsible for the actual infrared transmission. Universal Remote only manages the logical remote, command names, optional buttons, optional TV media player entity, and optional received-command event entity.

Universal Remote can be configured with an infrared emitter, an infrared receiver, or both. Sending commands requires an infrared emitter. Receiving and matching infrared commands requires an infrared receiver and a supported codeset.

---

## Installation

### Install with HACS

1. Open HACS in Home Assistant.
2. Open the three-dot menu.
3. Select **Custom repositories**.
4. Add this repository URL:

   ```text
   https://github.com/orandasoft/hacs-universal-remote
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

Receiver support requires a supported codeset so received infrared signals can be decoded and matched to known command names.

Multiple Universal Remote config entries may use the same infrared emitter or receiver. This allows one physical IR blaster or receiver to be shared by multiple logical devices.

---

## Entities

Depending on the configured infrared targets, Universal Remote can create the following entities:

- a `remote` entity when an infrared emitter is configured
- `button` entities for selected commands when an infrared emitter is configured
- a `media_player` entity for TV remotes when an infrared emitter is configured
- an `event` entity for received commands when an infrared receiver is configured

The TV media player is assumed-state. It does not know the real power, volume, channel, source, or playback state of the physical device, although it may update assumed power and source state after commands are sent through Universal Remote.

The received-command event entity emits events when the linked infrared receiver receives a supported and matched command. Unknown or unmatched signals may be reported as `unknown`.

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

Receiver command matching is currently supported for NEC-based codesets such as LG TV, LG TV Japan, and Vizio TV. Other codesets may still be used for command import and sending, but may not support received-command matching yet.

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

## Sending commands

Sending commands requires a configured infrared emitter.

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

Receiving commands requires a configured infrared receiver and a supported codeset.

When a supported received signal matches a known codeset command, Universal Remote exposes it through a Home Assistant `event` entity. The event type is the normalized command name in lowercase, for example:

```text
power
volume_up
hdmi_1
```

Signals that cannot be decoded or matched may be reported as:

```text
unknown
```

Universal Remote does not learn and save new commands from received infrared signals. Received signals are used only for event reporting.

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

Commands such as `TV`, `TV_INPUT`, `DTV`, `BS`, `BS4K`, `CS1`, `CS2`, `INPUT`, `SOURCE`, `HDMI_1`, `HDMI_2`, `HDMI_3`, `HDMI_4`, and `HDMI_5` may appear as selectable sources when they are configured for the remote. Component inputs and app shortcuts such as `NETFLIX` or `AMAZON_PRIME` may also appear when supported by the selected codeset.

Because the media player is assumed-state, it sends commands but does not receive real state feedback from the physical device. Source selection updates the assumed source in Home Assistant after Universal Remote sends the selected source command.

---

## Availability and repairs

Universal Remote send entities are available when the linked infrared emitter exists and is available.

If the linked infrared emitter is missing or unavailable, the integration creates a repair issue to help update the configuration.

If a configured infrared receiver is missing, the integration creates a repair issue for the missing receiver. The received-command event entity is only created when the linked receiver exists.

---

## Diagnostics

Diagnostics are available from the Home Assistant device/integration diagnostics UI.

Diagnostics are intended to help troubleshoot configuration issues without exposing full infrared command payloads.

---

## Known limitations

- Universal Remote does not learn or store new infrared commands from received signals.
- Universal Remote does not transmit infrared commands directly.
- The linked `infrared` integration is responsible for hardware communication.
- Sending commands requires a linked infrared emitter.
- Receiving command events requires a linked infrared receiver and a supported codeset.
- Receiver decoding is currently limited to supported codesets.
- The TV media player is assumed-state and does not reflect real device state.
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
https://github.com/orandasoft/hacs-universal-remote
```

Issues:

```text
https://github.com/orandasoft/hacs-universal-remote/issues
```
