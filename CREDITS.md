# Credits and provenance

Moto G4 Linux is an integration project. The working port depends on years of
upstream kernel, mobile-Linux and terminal work. Credit follows the actual use
below; a project listed as inspiration is not claimed as bundled implementation.

## Foundation and reused components

| Project / contributors | What this repository builds on | Reference |
| --- | --- | --- |
| **postmarketOS contributors / archived athene port** | Device research, ARM64 kernel configuration, GCC 6 recipe, shared patches and early userspace patterns | [pinned athene recipe](https://gitlab.postmarketos.org/postmarketOS/pmaports/-/tree/767b10462fb3f0cb591e2e04c20dd2ed4d6e2568/device/archived/linux-motorola-athene), [device documentation](https://wiki.nura.eco/wiki/Motorola_Moto_G4_(motorola-athene)) |
| **Linux contributors, Motorola, Qualcomm / The Linux Foundation, fengjiongmax and downstream contributors** | MSM8952/athene 3.10.108 kernel tree; the reference kernel is reproduced and patched, not written here | [exact kernel revision](https://github.com/fengjiongmax/android_kernel_motorola_msm8952/tree/4f6c8d2e1507595b5ef404d076128874176f1219), [kernel COPYING](https://github.com/fengjiongmax/android_kernel_motorola_msm8952/blob/4f6c8d2e1507595b5ef404d076128874176f1219/COPYING) |
| **lk2nd / msm8916-mainline contributors**, including **Stephan Gerhold and Nikita Travkin** | Secondary bootloader, Fastboot, hardware database and device-tree update mechanism | [lk2nd](https://github.com/msm8916-mainline/lk2nd), [pinned revision](https://github.com/msm8916-mainline/lk2nd/tree/fd11905d61f220daf9ad69b1b26144cbc6020169), [preserved notices](LICENSES/lk2nd-specific.txt) |
| **Little Kernel / Travis Geiselbrecht, Qualcomm and The Linux Foundation** | Underlying lk2nd bootloader foundation | [lk2nd upstream notice](LICENSES/lk2nd-upstream.txt) |
| **AsteroidOS / Florent Revest** | `msm-fb-refresher` v0.2, compiled as a separate native framebuffer refresh helper | [source and copyright](https://github.com/AsteroidOS/msm-fb-refresher/blob/v0.2/refresher.c) |
| **Alpine Linux and package maintainers** | ARM64 userspace and signed package ecosystem | [Alpine](https://alpinelinux.org/), [package metadata](https://pkgs.alpinelinux.org/) |
| **BusyBox and OpenRC contributors** | PID 1, basic utilities and startup/shutdown dependency ordering | [BusyBox](https://busybox.net/), [OpenRC](https://github.com/OpenRC/openrc) |
| **X.Org, xterm and Openbox contributors** | Display/input stack, mature terminal emulation and window management | [X.Org](https://www.x.org/), [xterm](https://invisible-island.net/xterm/), [Openbox](https://openbox.org/) |
| **Python and Tcl/Tk contributors** | Native control UI, text editing, focus/caret and Python service code | [Python](https://www.python.org/), [Tcl/Tk](https://www.tcl-lang.org/) |
| **Rust and companion crate contributors** | Optional client runtime; reqwest, tungstenite, rustls/ring, serde, URL/cookie handling and OS RNG | [Rust](https://www.rust-lang.org/), [locked dependencies](companion/Cargo.lock), [license scope](LICENSES/README.md) |
| **Silero Team and whisper.cpp contributors** | Local neural speech verification with pinned Silero v6.2.0 ggml weights; no speech model is authored here | [Silero VAD](https://github.com/snakers4/silero-vad), [preserved model license](LICENSES/silero-vad-MIT.txt), [build pins](companion/wake/pins.json) |
| **Nous Research / Hermes Agent and Umbrel contributors** | Existing remote agent, voice routes and app authentication protocols used by the optional companion | [Hermes](https://github.com/NousResearch/hermes-agent), [Umbrel](https://github.com/getumbrel/umbrel), [integration research](docs/hermes-assistant.md) |
| **Nicholas Marriott and tmux contributors** | Terminal sessions independent of GUI lifetime; stable pane/window IDs | [tmux](https://github.com/tmux/tmux) |
| **wpa_supplicant, iw, dnsmasq and Dropbear contributors** | Wi-Fi control, DHCP and project-key USB maintenance | [wpa_supplicant control API](https://w1.fi/wpa_supplicant/devel/ctrl_iface_page.html), [iw](https://wireless.docs.kernel.org/en/latest/en/users/documentation/iw.html), [dnsmasq](https://thekelleys.org.uk/dnsmasq/doc.html), [Dropbear](https://matt.ucc.asn.au/dropbear/dropbear.html) |
| **ALSA contributors** | PCM capture/playback, routing and soft-volume control | [ALSA](https://www.alsa-project.org/) |
| **OpenSSH / OpenBSD contributors** | SSH authentication, host verification and askpass mechanism | [OpenSSH](https://www.openssh.com/), [readpass.c](https://github.com/openssh/openssh-portable/blob/master/readpass.c) |
| **Tailscale contributors** | Device VPN identity, SSH authorization and official ARM64 client | [Tailscale source](https://github.com/tailscale/tailscale), [Linux setup](https://tailscale.com/docs/install/linux) |
| **libqrencode contributors** | Local rendering of official authorization links as QR codes | [libqrencode](https://fukuchi.org/works/qrencode/) |
| **osm0sis and mkbootimg contributors; Loïc Poulain / skales contributors** | Legacy Android boot-image and QCDT packaging tools, with archived postmarketOS dtbTool patches | [mkbootimg](https://github.com/osm0sis/mkbootimg), [skales](https://github.com/loicpoulain/skales) |

Versions and full source/artifact hashes are in [sources.lock.json](sources.lock.json).
This is a provenance list, not a declaration that all these upstream components
share one license. Package/file licenses remain authoritative.

## Research and UX inspiration

| Source | Relationship |
| --- | --- |
| [Omarchy Mobile / Derek Ross and contributors](https://github.com/derekross/omarchy-mobile) | Initial inspiration for giving old phones a Linux desktop. Its Pixel-oriented work is not the athene implementation or a bundled Omarchy distribution. |
| [Sxmo](https://sxmo.org/) | Researched mobile Linux interaction, keyboard visibility and hardware-button ideas. No Sxmo UI code is bundled here. |
| [Moshi connections documentation](https://getmoshi.app/docs/connections) | Inspired separating network/VPN/SSH concerns and saved destinations. No proprietary Moshi code, artwork or layouts were copied. |
| [okias / athene mainline work](https://github.com/okias/linux/commits/b4/motorola-athene/) | Investigated as a future kernel direction. It is not the currently validated kernel. |
| [Sony open fingerprint work](https://github.com/sonyxperiadev/vendor-sony-oss-fingerprint) | Architecture/reference research for a deferred sensor experiment; no claim that it makes this unit's sensor work. |

## Contributions made here

Henrique directed and physically tested the prototype, with AI-assisted
development/research using Codex and focused Astra reviews. Contributions in this
repository include:

- Motorola `/chosen` hardware-property forwarding for the lk2nd/athene boot path.
- Integration of the archived kernel with the native framebuffer/RNG fixes and
  DSP playback-gain patch needed without the Android audio HAL.
- ADSP/WCNSS startup ordering, OpenRC integration, native audio routes and softvol.
- Touch input adaptation, terminal-oriented keyboard, tab UX and native form focus.
- Saved Wi-Fi behavior/rollback, distinct Tailscale and SSH panels, QR handling,
  saved destinations and optional endpoint-bound SSH passwords.
- Groq capture/transcription/review and keyboard dictation that pastes without Enter.
- Fullscreen Hermes companion, original vector face, Rust conversation/auth/audio
  client, Groq activation integration and separate-context voice commands.
- Isolated regressions, real PTY/OpenSSH fixture checks and agent-facing documentation.

Groq is an external optional transcription service, not a locally implemented
speech model. Users bring their own account/key and accept its service terms.
Codex/Claude Code are tools readers may use, not runtime dependencies or project
sponsors. No endorsement by Motorola, postmarketOS or the other projects is implied.

## Hermes voice companion references

[Xiaozhi ESP32](https://github.com/78/xiaozhi-esp32) and
[RoboEyes](https://github.com/fluxgarage/RoboEyes) informed the animated-device
interaction. The fullscreen vector character is original; no GPL RoboEyes
code/art is included. The local speech detector separately builds MIT-licensed
[whisper.cpp](https://github.com/ggml-org/whisper.cpp) for its Silero VAD API and
obtains pinned Silero weights. It does not run Whisper ASR or require its weights. WebRTC VAD uses the pinned Rust wrapper/libfvad
with their individual notices. Downloads/weights and build tools remain outside
Git. See [research](docs/hermes-assistant.md) and [license scope](LICENSES/README.md).
