![Moto G4 Linux — Hermes with a face and a voice, plus a real Linux terminal](assets/banner.svg)

# Moto G4 Linux handbook

Give a retired phone a second life as a **fullscreen Hermes voice companion**
and a **native Linux terminal**. Open the animated face, say **Olá Hermes**,
converse hands-free and return to persistent terminal tabs, SSH and Tailscale.

[Comece em português](../README.pt-BR.md) · [Source and screenshots](../README.md) ·
[Contribute](../CONTRIBUTING.md)

> **Experimental source port.** The reference is a Moto G4 Plus **XT1640 /
> athene P2A, 2 GB / 32 GB**. There is no universal installer or public flashable
> image. Check the hardware and recovery path before any device writes.

## Start here

| You want to… | Start with… |
| --- | --- |
| Connect your existing Hermes to the Moto | [First connection checklist](hermes-setup.md#first-connection-checklist) / [tutorial em português](hermes-quickstart.pt-BR.md) |
| Tell Hermes what to prepare on its server side | **[Instructions to send your Hermes agent](hermes-server-agent.md)** — includes ready-to-copy prompts |
| See the face, terminal and controls | [Screenshot gallery](screenshots.md) |
| Install Linux on another handset | [Hardware compatibility](status.md), [agent workflow](agent-installation.md), [installation/recovery](installation.md) |

## Connect your Hermes

The **Moto app** handles voice activation through Groq, microphone capture,
transcription, the face and playback. **Your existing Hermes** handles the
chosen agent profile, conversation/tools and Edge speech synthesis. The phone
uses a separate conversation in that profile; **Nova conversa** changes context
without resetting Telegram. Closing the app releases audio and restores Linux.

For Umbrel, the existing app gateway/login stays in front of Hermes's built-in
chat/audio APIs. Password-only and challenged 2FA accounts are supported. No
extra server plugin is required for the documented contract. The owner gives
the [server guide](hermes-server-agent.md) to Hermes itself; the client agent
does not administer the Umbrel host or configure Hermes remotely.

The app is installed on the reference phone with native fixture tests passing.
Real wake/noise, thermal/battery and complete live conversation acceptance
remain open. [Current evidence](status.md#fullscreen-hermes-voice-pet-revision--installed-live-voice-pending).

## Use your phone

The [user guide](user-guide.md) covers Hermes voice commands, terminal tabs, keyboard shortcuts, saved
Wi-Fi, first Tailscale enrollment, SSH favorites, dictation, audio and power.
For failures, start with [troubleshooting](troubleshooting.md) and preserve logs
privately before changing the system.

## Build and contribute

| Goal | Guide |
| --- | --- |
| Build the kernel, boot components and clean userspace | [Building](building.md) |
| Understand boot, services, UI and integration contracts | [Architecture](architecture.md) |
| Review the Alpine UI update and its validation | [Interface refresh](interface-refresh.md) |
| Review the Rust voice companion and Umbrel integration | [Hermes research and implementation](hermes-assistant.md) |
| Build and configure the optional voice companion with your own account | [Hermes setup](hermes-setup.md) |
| Let Hermes prepare its own app side, without Umbrel host access | [Hermes-side agent instructions](hermes-server-agent.md) |
| Verify changes without disturbing live sessions | [Testing](../tests/README.md) |
| Propose fixes and contribute | [Contributing](../CONTRIBUTING.md) |
| Understand security limits and report vulnerabilities | [Security](../SECURITY.md) |
| Prepare source or future binary releases | [Release preparation](releasing.md) |
| Maintain this handbook and its Wiki export | [Wiki maintenance](wiki.md) |

## Built on the community

The port builds on postmarketOS research, the Motorola/Qualcomm Linux kernel,
lk2nd, Alpine, AsteroidOS and the terminal/network/audio ecosystems. Read the
[credits](../CREDITS.md), [notices](../NOTICE.md),
[license scope](../LICENSES/README.md) and [source pins](../sources.lock.json).

These public guides are maintained in the source repository and exported to the
Wiki. Private development journals, device identifiers, credentials and backups
stay outside both repositories.
