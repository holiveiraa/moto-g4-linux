<p align="center">
  <img src="docs/assets/banner.svg" alt="Moto G4 Linux — a terminal-first second life" width="940">
</p>
<p align="center">
  <b>A small phone. A real Linux terminal. Your own network and servers.</b><br>
  Native Linux for the Moto G4 Plus, with a touch interface built for SSH.
</p>
<p align="center">
  <a href="docs/agent-installation.md">Install with your agent</a> ·
  <a href="docs/status.md">Hardware status</a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="CREDITS.md">Credits</a> ·
  <a href="README.pt-BR.md">Português</a>
</p>

## A second life for a retired phone

Boot directly into **Alpine Linux**, with Xorg, xterm/tmux and a Python/Tk touch
shell. The working prototype powers on and shuts down without a PC.

- **A keyboard for terminals:** Esc, Ctrl, Alt, Shift, arrows and repeat keys.
- **Real terminal tabs:** open, switch and close without losing other sessions.
- **Separate connections:** saved Wi-Fi, Tailscale VPN and saved SSH destinations.
- **Your credentials:** first Tailscale login by QR, optional SSH passwords,
  manual/2FA entry and normal host-key verification.
- **Voice into the terminal:** microphone → Groq transcription → active input,
  **without Enter**. Bring your own API key; transcription uses the cloud.
- **Touch-first controls:** visible field focus/carets, brightness, volume,
  native speaker/microphone and a power menu.

## A look at the interface

<p align="center">
  <img src="docs/assets/panel.png" alt="Home panel with brightness, volume and separate connections" width="240">
  <img src="docs/assets/wifi.png" alt="Wi-Fi page with a saved network and nearby networks" width="240">
  <img src="docs/assets/ssh.png" alt="SSH favorites with separate SSH and Tailscale SSH examples" width="240">
</p>

Actual Tk rendering captured on the Moto in an isolated virtual display, using
synthetic networks, servers and status values. The current UI is in Brazilian
Portuguese; the public guides are in English, with a Portuguese entry point.

## Start with an agent

Open this repository in Codex, Claude Code or another local coding agent:

> Help me install Moto G4 Linux on my USB-connected phone. Read AGENTS.md and
> docs/agent-installation.md first. Inspect my device and host, make a plan and
> verified private backups, then build for my exact hardware. Before unlocking,
> formatting or flashing, show me the exact write plan and await my approval.
> Use my own keys and firmware; never copy another person's device state.

The [agent guide](docs/agent-installation.md) contains the workflow and a Portuguese
prompt. The owner still handles account login, secrets and physical device prompts.

**Current distribution: experimental source port.** There is no universal
installer or public flashable image. The prototype was verified on **one XT1640,
athene P2A, 2 GB / 32 GB**; other variants need investigation. The agent must check
compatibility and prepare per-device installation steps. The repository does not
silently format a connected phone. [Installation and recovery](docs/installation.md).

## What is verified

| Area | Evidence | Current limit |
| --- | --- | --- |
| Native boot / shutdown / Power-on | Owner-tested without USB | XT1640 P2A only |
| Display / touch / keyboard / tabs | Physical use and isolated UI/PTY reviews | Portrait; terminal-focused input |
| Saved Wi-Fi / Tailscale / SSH | Physical Wi-Fi and Tailscale SSH use | QR login needs a browser on another device |
| Speaker / microphone / volume / dictation | Physical use after an unplugged power cycle | Headset/BT/calls not established |
| Optional SSH password / host checks | Real phone OpenSSH against an isolated fixture | Private files, not encrypted storage |
| Fresh install on another unit | Agent workflow documented | Independent reproduction still needed |

The [full matrix](docs/status.md) separates physical tests from simulations. The
old **3.10.108 downstream kernel** is an experimental basis. Suspend, screen
locking and a maintained kernel remain open work.

## Explore

| Goal | Guide |
| --- | --- |
| Install with an agent | [Agent workflow](docs/agent-installation.md) |
| Understand prerequisites/recovery | [Installation](docs/installation.md) |
| Use the phone | [User guide](docs/user-guide.md) |
| Build kernel/boot components | [Building](docs/building.md) |
| Understand the system | [Architecture](docs/architecture.md) |
| Diagnose a failure | [Troubleshooting](docs/troubleshooting.md) |
| Contribute / verify | [Contributing](CONTRIBUTING.md), [tests](tests/README.md) |
| Prepare the GitHub Wiki | [Wiki guide](docs/wiki.md) |

```text
native/       Touch shell, input, audio, network and boot adaptations
config/       OpenRC, Xorg, tmux and audio configuration
initramfs/    RAM/rescue and persistent-boot startup helpers
patches/      Downstream kernel changes
scripts/      Local builds, maintenance, source checks and wiki export
tests/        Offline regressions and isolated device reviews
docs/         Canonical public documentation and original artwork
wiki/         Page map and navigation templates
```

## Built on other people's work

The foundation is the archived **postmarketOS athene port**, the Motorola /
Qualcomm / Linux downstream kernel in **fengjiongmax's fork**, **lk2nd**, **Alpine**
and **AsteroidOS msm-fb-refresher**, alongside Xorg, Tk, xterm, tmux,
wpa_supplicant, ALSA, OpenSSH and Tailscale.

This project adds the phone integration, Motorola hardware-DT forwarding, audio
startup/playback fixes, touch shell, terminal keyboard/tabs, connection panels
and dictation UX. Omarchy Mobile, Sxmo and Moshi informed exploration and UX;
[CREDITS.md](CREDITS.md) distinguishes reused code from inspiration.

## License

Original userspace, tooling, documentation and artwork: **MIT**. Kernel
patches/module retain **GPL-2.0-only**; the lk2nd adaptation retains **BSD-3-Clause**.
Other components and firmware keep their own terms. See [LICENSE](LICENSE),
[license scope](LICENSES/README.md) and [NOTICE.md](NOTICE.md). No OEM firmware,
private keys, personal state or rootfs backups are included.
