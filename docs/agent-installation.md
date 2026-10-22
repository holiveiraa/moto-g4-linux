# Install with your coding agent

This guide is intended to be executed by a local Codex, Claude Code or similar
agent with terminal access. The owner supplies physical actions and account
authorization; the agent handles research, inspection, builds, evidence and
adaptation. It must not invent a universal flashing recipe.

## Owner prompt

Open the repository, connect the handset and give the agent this instruction:

> Install Moto G4 Linux on my USB-connected handset. Read AGENTS.md and this
> guide. First inspect my host and exact hardware without changing the phone.
> Explain compatibility, prepare my private workspace and verified backups,
> fetch pinned sources and build/test in RAM. Before unlocking, formatting or
> writing partitions, show the exact device, target sizes, image hashes and
> recovery plan and wait for my approval. Use my own keys and firmware, start
> personal configuration empty and do not publish anything.

Em português:

> Instale o Moto G4 Linux no meu celular conectado por USB. Leia AGENTS.md e este
> guia. Primeiro inspecione o PC e o hardware exato sem alterar o aparelho.
> Confirme compatibilidade, prepare minha pasta privada e backups conferidos,
> obtenha as fontes fixadas e faça build/teste em RAM. Antes de desbloquear,
> formatar ou gravar partições, mostre aparelho, alvos, tamanhos, hashes e plano
> de recuperação; aguarde minha autorização. Use minhas próprias chaves e
> firmware, comece as configurações pessoais vazias e não publique nada.

## Phase 1 — establish identity and scope

Read [status](status.md), [installation](installation.md), [building](building.md)
and [architecture](architecture.md). Determine host OS, USB ownership, tools,
device mode and number of connected devices. ADB and Fastboot enumerate
different modes; USB Linux networking is different again.

Collect read-only model/product/codename, hardware revision, RAM/storage,
bootloader lock state and available recovery. `adb devices -l`, selected-device
`adb shell getprop`, and selected-device `fastboot getvar product` /
`fastboot getvar unlocked` are inspection tools, not proof that all other models
are compatible. Put identifiers and command output in `.private/`, not public docs.
Never auto-select among several phones.

**Gate:** XT1640/P2A is the reference, not a wildcard for Moto G4/G4 Play. If
hardware differs, produce a compatibility investigation and stop before writes.
The owner should not have to discover this after an erase.

## Phase 2 — private work area and recovery

Prepare `.private/device-profile.json`, `.private/install-plan.md` and
`.private/progress.md`. Record exact model, boot/recovery/userdata/system names,
resolved block devices, sizes, stock filesystem/UUID, stock image hashes and a
recovery route. Keep a second verified backup on the host before any destructive
step. Do not copy the original developer's hashes or images.

Generate fresh project maintenance keys; never reuse a cloud SSH private key.
Establish how stock boot/DT and required firmware will be obtained legally from
this owner's device. A locked bootloader may require the owner to use Motorola's
official account/terms flow. Unlocking erases data; approval and backup come first.

**Gate:** an official stock boot/recovery source or verified backup and a route
back to bootloader/rescue must exist. Unknown recovery is not an acceptable
tradeoff for moving quickly.

## Phase 3 — reproduce sources and test in RAM

Run the offline repository/tests first. Fetch the exact upstream revisions in
`sources.lock.json` and build components on Linux/WSL. `out/` artifacts are private.
Read each script's inputs; several boot stages require firmware/DT and a small
boot-root archive generated for this device. Missing private inputs are not a
reason to request the developer's personal rootfs.

Use a size-checked RAM boot before installation. The full diagnostic RAM image
can exceed the boot partition and must never be flashed there. Prove USB rescue,
display, input and firmware ordering. If it stalls, inspect bounded logs and
upstream sources before proposing the next experiment. Never repeat resets or
loads without a hypothesis.

**Gate:** a controlled RAM session and reliable maintenance channel. A build log
or Motorola logo alone does not prove a Linux boot.

## Phase 4 — produce a concrete per-device install plan

The repository deliberately excludes the original one-unit partition writers.
They contained that unit's UUIDs/stock hashes and are not portable installers.
Prepare owner-specific guarded steps based on the validated geometry and
[installation](installation.md), not a blind `dd`/`fastboot flash` sequence.

For every proposed write, record target PARTNAME/resolved path, capacity,
verified old backup/hash, new image length/hash, full padding policy and readback
verification. Preserve primary loader, GPT, modem, persist/calibration and
security partitions. The old kernel needs a compatible ext4 feature set.
Do not erase Android system just to make a RAM experiment work.

Show this exact plan to the owner and obtain authorization at this gate. Then
perform only those writes, with guards that re-check the currently connected
device and refuse mismatches. A refused guard is evidence, not an obstacle to remove.

## Phase 5 — clean personal configuration

Build/install native OpenRC services and current userspace, preserving ADSP before
WCNSS. New installations start with no Wi-Fi credentials, Tailscale identity,
SSH favorites/passwords, Groq keys or recordings. Use per-install maintenance keys.

First use must work through the phone: Wi-Fi → VPN/Tailscale → generate QR →
owner authorizes in an external browser → status updates automatically. Add the
owner's SSH destinations, optional passwords and Groq key through the UI.
VPN registration is separate from an SSH session's authorization QR.

If the owner wants the optional Hermes face/voice app, follow the separate
[companion setup](hermes-setup.md) after the base terminal/audio work. Build the
Rust component for this exact target and verify its old-kernel runtime before
claiming it works. Use this installation's own Hermes/Umbrel account, CA trust
and Groq key. Password-only and optional 2FA login are supported; no preconfigured
cookie, conversation ID or API key belongs in a fresh image. The companion is a
source preview and has not yet passed physical Moto acceptance.

## Phase 6 — owner acceptance, unplugged

Prove shutdown and Power-on without USB first. Then verify screen off/on, touch,
visible form focus, saved Wi-Fi after a network switch/reboot, Tailscale identity
after reboot, SSH open/switch/close, speaker/volume, microphone and optional
dictation insertion **without Enter**. A QR-only simulation does not satisfy a
new-install enrollment test. Do not claim a feature that the owner could not test.

Finish with `.private/progress.md`: artifacts/hashes, backup locations, installed
state, passing tests, remaining limits and exact next action. Share a redacted
compatibility report upstream; never share identity files or rootfs snapshots.
