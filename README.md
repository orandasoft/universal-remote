# Universal Remote

Universal Remote is a Home Assistant custom integration that creates logical infrared remote devices backed by existing Home Assistant `infrared` entities.

It does not communicate with infrared hardware directly. Instead, it stores named infrared commands and asks the linked `infrared` entity to transmit them.

This makes it possible to use one infrared transmitter for multiple logical devices, such as TVs, receivers, projectors, HDMI switches, or other infrared-controlled equipment.

> This is a Home Assistant integration for HACS. It is not the Universal Remote Card dashboard plugin.

---

## Requirements

- Home Assistant 2026.4.0 or newer
- HACS
- At least one Home Assistant `infrared` entity from another integration
- Compatible infrared transmitter hardware supported by that infrared integration

The linked `infrared` entity is responsible for the actual infrared transmission. Universal Remote only manages the logical remote, command names, optional buttons, and optional TV media player entity.

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
- the linked `infrared` entity
- the device type
- optional commands or library codeset commands

Multiple Universal Remote config entries may use the same infrared entity. This allows one physical IR blaster to control multiple logical devices.

---

## Entities

Each configured universal remote creates a `remote` entity.

Depending on the configured options, it can also create:

- `button` entities for selected commands
- a `media_player` entity for TV remotes

The TV media player is assumed-state. It does not know the real power, volume, channel, source, or playback state of the physical device. Its supported controls are derived from the commands configured for the remote.

---

## Device types and codesets

Universal remotes can be configured as a generic remote or as a supported device type such as TV.

The device type controls which device-oriented entities can be created. For example, TV remotes can create a TV `media_player` entity.

A codeset is an optional infrared command library profile. Codesets are filtered by device type and can be used to import commands during setup or later from the options flow.

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

## Button entities

Command button entities are optional.

When adding or importing commands, the flow can create Home Assistant `button` entities for selected commands. Pressing a button sends the stored infrared command through the linked infrared entity.

---

## TV media player

TV remotes create a `media_player` entity.

The media player exposes supported features based on configured command names.

Examples:

- `POWER_ON` enables turn on.
- `POWER_OFF` enables turn off.
- `VOLUME_UP` and `VOLUME_DOWN` enable volume step.
- `MUTE` enables mute.
- `CHANNEL_UP` and `CHANNEL_DOWN` enable channel controls.
- `PLAY`, `PAUSE`, and `STOP` enable playback controls.
- Source commands such as `HDMI_1`, `TV`, `DTV`, `BS`, or app shortcuts can appear in the source list.

Because the media player is assumed-state, it sends commands but does not receive real state feedback from the physical device.

---

## Availability and repairs

Universal Remote entities are available when the linked infrared entity exists and is available.

If the linked infrared entity is missing or unavailable, the integration creates a repair issue to help update the configuration.

---

## Diagnostics

Diagnostics are available from the Home Assistant device/integration diagnostics UI.

Diagnostics are intended to help troubleshoot configuration issues without exposing full infrared command payloads.

---

## Known limitations

- Universal Remote does not learn infrared commands.
- Universal Remote does not transmit infrared commands directly.
- The linked `infrared` integration is responsible for hardware communication.
- The TV media player is assumed-state and does not reflect real device state.
- Existing commands are not deleted automatically when changing device type or codeset.
- Availability depends on the linked infrared entity.

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
python3 -m compileall custom_components/universal_remote
```

Run Ruff:

```bash
ruff check custom_components/universal_remote tests
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
