# Hardware and project status

Evidence reviewed: **21 October 2026**. The working prototype has been exercised
on one **Motorola Moto G4 Plus XT1640, athene P2A, 2 GB RAM / 32 GB storage**,
with its original **Athene_16MP** hardware description. No other variant is
certified by this project. Product-family similarity does not establish matching
panel, touch, amplifier, memory layout or partition geometry.

## Working prototype

| Component | Result | Evidence / boundary |
| --- | --- | --- |
| Persistent native boot | Working | Linux returns after unlocked-bootloader warning |
| Shutdown and Power-on | Working | Owner tested without USB |
| Power short press | Working | Backlight off/on; not suspend or lock |
| Recovery | Working on tested unit | Adapted lk2nd Fastboot menu |
| Display / backlight | Working | Xorg/framebuffer refresh; wide brightness control |
| Single-finger touch / keyboard | Working | Physical use, input regressions and XTest |
| Terminal tabs | Working | Open/switch/close, stable tmux IDs; four-tab UI limit |
| Form focus / caret | Working | Owner-confirmed; native cursor pixels observed blinking |
| Wi-Fi / saved profiles | Working | Physical reconnect without re-entering password |
| Tailscale / SSH | Working | Persistent identity and real Tailscale SSH use |
| First Tailscale enrollment UI | Working in isolated review | No-URL → QR → connected; clean-device reproduction remains |
| Optional SSH password | Working in fixture integration | Real phone OpenSSH, correct/wrong/empty/manual authentication and host checks |
| Native microphone | Working | Physical speech recording and transcription |
| Speaker / volume buttons | Working | Owner-confirmed after unplugged power cycle |
| Groq dictation / keyboard mic | Working | Real transcription; inserts without Enter |

## Not established

- Suspend/resume, screen locking and controlled idle-battery/thermal results.
- Headphones, Bluetooth audio, cellular calls/data, camera and fingerprint reader.
- Landscape/rotation, general multitouch, complete accented-language keyboard
  and screen-reader accessibility.
- GPU acceleration or a maintained mainline-kernel desktop.
- Installation on a second device, including a clean first-use/reboot acceptance
  run and a complete rootfs built independently of the prototype's private state.

## Public-source validation — 21 October 2026

- **94 offline tests passed**, including a copy containing only public source,
  with no developer `.private/` directory.
- The current public modules passed **five isolated reviews on the Moto**:
  connections, native input focus/caret, terminal tabs, Tailscale first-use/SSH
  authorization states, and microphone-key literal PTY paste without Enter.
  These used a private Xvfb display, separate tmux servers and synthetic external
  services. They did not replace the owner's installed interface or identities.
- lk2nd compiled from a new checkout of the pinned upstream source with the
  Motorola adaptation. That new artifact was not flashed or boot-certified.
- Shell syntax, public-source privacy/link checks and the 14-file local Wiki
  export passed. At that local checkpoint GitHub-hosted CI had not run yet.
  The source repository is now public; current hosted results are available in
  [GitHub Actions](https://github.com/holiveiraa/moto-g4-linux/actions).

These are source/integration checks. They do not establish a clean rootfs install
on a second phone, long-term reliability or compatibility with other variants.

## Distribution maturity

The repository is an **experimental source port with an agent-assisted workflow**.
It includes build components, native services, UI, tests and integration notes.
It does not include OEM firmware, personal images or an automatic partition writer.

Public-source preparation removes personal defaults and fixes source acquisition.
The installed prototype was not reflashed just to prepare this repository.
CI tests software contracts; it does not prove boot compatibility or a new
handset's installation. A reproducible end-to-end binary release remains separate
work, tracked in [release preparation](releasing.md).

The 3.10.108 downstream kernel and root desktop do not constitute a maintained
mobile security boundary. Read [security](../SECURITY.md) before evaluating use.
