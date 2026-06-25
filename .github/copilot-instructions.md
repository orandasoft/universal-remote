# Copilot review instructions

This repository is a Home Assistant custom integration named Universal Remote.

Universal Remote creates logical infrared remotes backed by Home Assistant `infrared` entities. It must not communicate with infrared hardware directly.

Reference docs:
- Home Assistant infrared entity docs: https://developers.home-assistant.io/docs/core/entity/infrared/
- Home Assistant remote entity docs: https://developers.home-assistant.io/docs/core/entity/remote/
- Home Assistant entity docs: https://developers.home-assistant.io/docs/core/entity/

Architecture rules:
- Emitter-backed entities:
  - `remote`
  - `button`
  - `media_player`
- Receiver-backed entity:
  - `event`
- `remote.py`, `button.py`, and `media_player.py` must require a valid infrared emitter and must safely skip receiver-only entries.
- `event.py` must require a valid infrared receiver and must safely skip emitter-only entries.
- Config entries may have:
  - emitter only
  - receiver only
  - both emitter and receiver
- Receiver-only entries must not create emitter-backed entities.
- Emitter-only entries must not create receiver-backed entities.
- Entries with both emitter and receiver may create all applicable entities.

Review focus:
- Home Assistant config entry lifecycle correctness.
- Platform setup/unload behavior.
- Entity registry cleanup for stale entities.
- Device registry cleanup without deleting receiver-only devices.
- Repairs behavior for missing linked emitters and receivers.
- Diagnostics safety and redaction.
- Async correctness.
- Config flow validation for emitter-only, receiver-only, and emitter+receiver entries.
- Options flow must remain command-focused and must not require an emitter.
- Tests should cover all changed behavior and defensive skip branches.

Important design constraints:
- Do not add direct hardware communication to Universal Remote.
- Do not compare received raw timings to stored Pronto strings.
- Received infrared matching should use protocol-level decoding where supported.
- Keep send-side and receive-side behavior separate.
