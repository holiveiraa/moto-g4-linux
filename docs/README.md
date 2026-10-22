![Moto G4 Linux — a terminal-first second life](assets/banner.svg)

# Moto G4 Linux handbook

Give a retired phone a second life as a native Linux terminal: touch-friendly
keys, persistent terminal tabs, saved Wi-Fi, Tailscale, SSH and optional dictation.

[Comece em português](../README.pt-BR.md) · [Source and screenshots](../README.md) ·
[Contribute](../CONTRIBUTING.md)

> **Experimental source port.** The reference is a Moto G4 Plus **XT1640 /
> athene P2A, 2 GB / 32 GB**. There is no universal installer or public flashable
> image. Check the hardware and recovery path before any device writes.

## Start here

1. **Check your phone:** read the [hardware/status matrix](status.md).
2. **Bring your coding agent:** use the [agent installation workflow](agent-installation.md),
   with prompts in English and Portuguese.
3. **Plan before installing:** review [installation and recovery](installation.md).

## Use your phone

The [user guide](user-guide.md) covers terminal tabs, keyboard shortcuts, saved
Wi-Fi, first Tailscale enrollment, SSH favorites, dictation, audio and power.
For failures, start with [troubleshooting](troubleshooting.md) and preserve logs
privately before changing the system.

## Build and contribute

| Goal | Guide |
| --- | --- |
| Build the kernel, boot components and clean userspace | [Building](building.md) |
| Understand boot, services, UI and integration contracts | [Architecture](architecture.md) |
| Review the Alpine UI update and its validation | [Interface refresh](interface-refresh.md) |
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
