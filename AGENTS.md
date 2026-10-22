# Working on Moto G4 Linux

Read `README.md`, `docs/status.md` and `docs/installation.md` first. For installs,
follow `docs/agent-installation.md` in order. The tested device is **XT1640 /
athene P2A, 2 GB / 32 GB**. A family name does not establish hardware compatibility.

## Umbrel and Hermes boundary

- Never access, inspect or change the Umbrel host through SSH, a host shell,
  Docker/Podman control, host files, service managers or host-management tools.
  Do not attempt a host connection as a diagnostic or installation shortcut.
- The Moto/client agent handles this repository and the phone only. It does
  not install, configure or restart software on the Umbrel host or inside Hermes.
- The owner gives the published repository to Hermes. Hermes itself performs
  only its own app/runtime/profile setup, following
  `docs/hermes-server-agent.md`. No host credentials or Docker socket are needed.
- Preserve Umbrel's app gateway, login, TLS and optional 2FA. If app-local setup
  cannot solve a requirement, report the exact missing capability; never escape
  to host administration. Configuring Hermes alone does not authorize phone writes.

## Scope and device writes

- Follow the user's current request. Repository work and builds do not authorize
  flashing, formatting, unlocking or publishing.
- Complete inspection, research, builds and a concrete write plan before asking
  for destructive-action approval. Routine reads need no extra questions.
- Before writes, show device identity, exact partition/name/size, input hash,
  verified backups and recovery route. Never reuse another owner's approval.
- Preserve primary bootloader, GPT, modem, calibration, persist and security
  partitions. Do not remove guards to make unfamiliar hardware pass.
- Use Motorola's official unlock procedure. The owner handles login, terms and
  physical confirmation. Do not ask for credentials in chat.

## Secrets and fresh installations

- `.private/`, `.local-tools/`, `sources/`, `build/` and `out/` stay local. Never
  force-add them or publish an owner's personal rootfs backup.
- Generate fresh keys/device identities per installation. Never clone Wi-Fi
  passwords, Tailscale state, SSH favorites/passwords, Groq keys, recordings,
  OEM images or diagnostic logs. Examples use `server.example` and fixtures.
- Do not change Tailscale accounts, SSH policy or remote users as a side effect.
  VPN registration and SSH verification are distinct operations.

## Preserve these contracts

- ADSP before WCNSS; no blind retry in the same failed boot.
- Screen-off is backlight blanking, not suspend or locking. Fingerprint is deferred.
- tmux uses immutable IDs; GUI restart preserves the user's sessions.
- Dictation pastes UTF-8 **without Enter**. Preserve cancellation/changed-target
  protection. Form secrets never reach terminals or logs.
- Inputs use `DevicePanel.field/register_input`, including Text editors. Keep
  native caret, actual focus, active border, selection and fixed actions.
- Reuse saved Wi-Fi profiles; preserve them on failure. Never deduplicate by SSID.
- SSH uses argv, validated IDs and host-key checks. Optional passwords stay
  private and tied to the frozen endpoint. Preserve the manual/2FA path.

## Verification and provenance

- Linux/WSL is the build/test host; Windows may own USB. Build on the Linux
  filesystem. Executable Python/shell files require LF.
- Run `python3 scripts/check-repository.py` and `python3 scripts/run-tests.py`.
  Device reviews require isolated Xvfb/tmux and synthetic configuration; read
  `tests/README.md`. Never use a person's active session as a destructive test.
- Distinguish built, simulated and physically verified. Compilation is not boot
  validation. Record hardware, evidence and remaining limits without private data.
- `docs/` is canonical; `scripts/export-wiki.py` generates wiki pages from it.
- Local `.private/project-history/`, if present, is evidence for its owner, not
  installation input for someone else.
- Read `CREDITS.md`, `NOTICE.md` and `LICENSES/README.md`. Preserve upstream and
  per-file licenses. Do not claim authorship of upstream components.
