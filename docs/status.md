# Hardware and project status

Evidence reviewed: **23 October 2026**. The working prototype has been exercised
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
| Hermes fullscreen companion | Installed; native fixtures pass | Real wake/noise, heat/battery and complete live conversation still pending |

For the Hermes app, start with the [first connection checklist](hermes-setup.md#first-connection-checklist),
[Portuguese tutorial](hermes-quickstart.pt-BR.md) and
[instructions to give Hermes itself](hermes-server-agent.md).

## Not established

- Suspend/resume, screen locking and controlled idle-battery/thermal results.
- Headphones, Bluetooth audio, cellular calls/data, camera and fingerprint reader.
- Landscape/rotation, general multitouch, broader language layouts and
  screen-reader accessibility. The keyboard now includes Portuguese accents/ç;
  physical typing ergonomics still need owner acceptance.
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

## Alpine interface refresh — 22 October 2026

The existing XT1640 installation received a userspace-only interface update:
Jade/Midnight/Paper themes with live preview and revert, terminal/code/Portuguese
keyboard pages and reduced idle work. Appearance opens directly from the panel;
tab and keyboard controls remain on the terminal. fzf/ripgrep remain installed
as optional CLI tools on this prototype, without GUI integration or background
services; they are not required by fresh installations. The GUI restart preserved
the existing tmux window ID. Boot images, partitions, firmware and personal network/SSH
configuration were not changed. Input file hashes and a verified rollback archive
were retained privately for the owner.

- **101 offline tests passed** in an isolated public-source copy on Linux/WSL.
- Isolated real-Tk reviews on the Moto covered focus/caret, terminal tabs,
  connections, voice review, quick dictation, Tailscale states and the new
  appearance and keyboard paths. Synthetic configuration, a separate Xvfb display and
  private tmux servers kept the owner's session out of typing/close tests.
- Current checks cover native accented input, literal UTF-8 without Enter, theme
  output staying out of terminal stdin, direct panel appearance access, absence
  of redundant menu entries, immediate control/worker wake and tmux failure
  during screen wake.
- In two sequential **20-second isolated idle samples** on this Moto, with the
  same synthetic awake screen and the network worker disabled in both, Python
  shell CPU was **11.55% → 1.70% of one core**; PSS was **22,632 → 21,997 KiB**.
  These short samples measure the shell, not total-device power or an autonomy
  improvement. They are not evidence of suspend, unplugged battery life or a
  guaranteed performance result under other workloads.

The owner observed the updated interface. Theme and keyboard ergonomics still
require normal physical use/acceptance; Xvfb checks alone do not establish them.

## Optional Hermes companion source preview — 22 October 2026

The repository now contains an optional Rust companion app with a native Tk
host, original CPU-rendered face, private Umbrel login (password-only or
challenged 2FA), scoped Hermes conversation and Groq/Edge audio path. It opens
from the panel and closes back to the terminal. See [setup](hermes-setup.md)
and [research/design](hermes-assistant.md). No server plugin or authentication
change was needed for the inspected API contract.

- **110 Python offline tests** and **19 Rust tests** passed in a public-source
  Linux copy. These include password-only/2FA handoff/cookies, HTTP/WS session
  scoping, uncertain-turn restart without replay, scoped interruption, fake ALSA
  success/failure and real HTTPS/WSS CA/hostname validation with fresh fixtures.
- The isolated **host** Tk/XTest/Xvfb review exercised actual Rust face pixels,
  native text/caret and masked password/2FA forms, screen blank/close, no terminal
  input leak and the same tmux window ID. Its account/reply data were synthetic;
  this is not a physical Moto companion test.
- After USB reconnection, the **ARM64 binary ran on the reference Moto** with
  kernel `3.10.108-Frostbitten-R19-64Bitch`, Alpine 3.24.3, MSM8952 and
  `Athene_16MP`. Its native thread/RNG/clock/runtime smoke passed. The same
  isolated Rust/Tk review then passed **on the Moto**, with synthetic account
  data, a private Xvfb display/tmux server and the production window `@0` retained.
- After a second USB reconnection, **all 19 Rust fixtures passed directly on
  this Moto**, including real loopback HTTPS/WSS, custom CA/hostname checks,
  password-only/2FA handoff, scoped chat/cancellation and fake ALSA playback.
  The TLS certificates, accounts, prompts and audio sink were synthetic.
- The seven-file frontend update was then installed with verified input hashes
  and a checked three-file rollback tar. The existing GUI restart helper ran
  successfully, the new shell was observed running, and production tmux window
  `@0` remained present. No boot/partition, personal config or server change
  was involved. The launcher is **Painel → Hermes**.
- Live Umbrel/Hermes login, the owner's CA/endpoint, physical conversation and
  real Groq/Edge remain unverified. Those require the Hermes app-local setup
  and owner acceptance; fake ALSA output is not evidence of audible speech.
- Umbrel host access is forbidden for this workflow. After publication, the
  owner gives the repository to Hermes for its own app-local setup using the
  [server-agent guide](hermes-server-agent.md). No Umbrel host connection or
  server-side change was made by this client agent.
- Source checks and local Wiki export passed. Builds carry a lockfile, toolchain
  pins, hashes and dependency notices; no new release was published.

## Fullscreen Hermes voice-pet revision — installed, live voice pending

The earlier panel UI was rejected in owner review. The replacement opens a
fullscreen animated face, locally checks **Olá Hermes**, acknowledges in speech,
and automatically alternates listening/replies. **Nova conversa** creates a new
Moto-owned context; closing restores the terminal. No push-to-talk main flow.

- **115 Python regressions**, **28 Rust tests**, Rustfmt/Clippy and ARM64 build
  pass on the Linux host. An isolated 1080×1920 Tk/XTest/tmux review passes with
  real Rust vector animation, hidden shell keyboard/header and preserved tmux.
- **All 28 Rust tests**, **14 companion Python tests** and the same fullscreen
  review also passed directly on the reference Moto, including fresh synthetic
  HTTPS/WSS fixtures, automatic voice events and new-conversation behavior.
  Production tmux `@0` remained present. No live account/real speech was used.
- The native persistent recognition helper processed eight synthetic pt-BR
  samples: startup 0.261 s; decode **1.326–1.906 s**; resident memory about
  **78 MB**, observed peak about **81.5 MB**. This is not complete interaction
  latency or an idle heat/battery measurement. The measured “Ula Hermes” spelling
  is explicitly accepted along with the exact normal phrase, using experimental
  thresholds fitted to this tiny corpus; no broad fuzzy matching is used.
- Local activation uses WebRTC VAD and pinned multilingual Whisper tiny q5_1;
  no standby audio event is eligible for Groq. Astra's static reviews prompted
  fixes for RMS-only noise detection, inference capture gaps, read-buffer loss,
  stalled-pipe shutdown and temporary-file cleanup. These are software checks,
  not proof against acoustic false wakes.
- A fresh seven-existing-file userspace backup was hash checked. Initial
  uploads lost their USB link. Windows event **NDIS 10400** reported that the
  RNDIS device stopped responding to driver commands. A scoped **PnP restart of
  only this Moto USB composite device** restored SSH, without changing driver,
  network-account or power-policy configuration. This is recovery evidence,
  not a claim that the underlying USB issue has been permanently fixed. A later
  NDIS reset recurred; see [USB troubleshooting](troubleshooting.md#rndis-stays-present-but-stops-answering).
- The complete package was then hash verified and installed by a detached
  transactional process with rollback. **Seven userspace runtime files/model
  were installed and independently reverified** (hash, size and mode). The final
  core SHA256 is `8d5a65feb5fa2d17395d6118c7881a1c3f34717be0346c9b3d7aa428df167b7a`,
  identical to the clean public-source ARM64 build. Model startup passed, the
  restarted GUI was running and original tmux `@0` was preserved. No partition,
  credential, SSH/VPN policy or server was changed. Open **Painel → Hermes**.
- This reference installation has no Hermes connection configuration yet.
  Actual-owner wake/noise acceptance, CPU/heat/battery, live account/CA and
  Groq/Edge remain unverified. The first-use connection setup and a fresh second
  installation remain open. The app source was published in commit
  [`6b1014e`](https://github.com/holiveiraa/moto-g4-linux/commit/6b1014ead2e8f8f69d8c0a2b001c7d07dc106512),
  with both GitHub Actions jobs passing. Hermes itself
  handles only its own app/profile setup using the
  [server-agent instructions](hermes-server-agent.md).

## Hermes canonical API and HTTP through Tailscale — 23 October 2026

The server-side diagnosis exposed a gap in the original permissive fixtures:
the native `/api/ws` authority uses **canonical** session contracts, while the
earlier client sent fields from the standalone gateway. Creation now sends
`source: gui`, a title and a stable `request_id`; resume sends the persistent
session ID and optional profile. Replies are correlated to the acknowledged
admission and execution generation, including events arriving before the submit
receipt. Cancellation covers queued work, the queue-to-running race and external
queue cancellation. No failed or uncertain submission is automatically replayed.

HTTP-only Umbrel installations can now use an existing numeric Tailscale peer
IP and app port. The Rust client checks the protected local Tailscale API,
peer membership and interface state before requests, and binds HTTP/WS sockets
to `tailscale0`. HTTPS verification and the separate HTTPS Groq client remain
in place. See [connection setup](hermes-setup.md#http-over-your-existing-tailscale).

- **116 Python regressions** and **37 Rust tests** pass on Linux/WSL;
  Rustfmt and Clippy also pass. Strict fixtures reject legacy session fields
  and exercise same-session foreign admissions, pre-receipt completion, queue
  transitions, cancellation and the explicit server `voice_stopped` result.
- A clean public-source snapshot builds a static **ARM64 musl** core (3,511,848
  bytes), SHA256
  `fb561293e1eb152ef4d7a2d1b4da88482514be3fcf250730e371424eec5a94f7`.
  Compilation does not establish native runtime acceptance.
- The isolated host Tk/XTest review also passes: fullscreen face, native setup
  fields, password/optional 2FA, blank/close cleanup and preserved tmux/input.
- An isolated disposable network namespace exercises actual HTTP and WS Upgrade
  requests to a synthetic peer. The same worker and HTTP connection pool refuse
  stopped VPN, unknown peer, down interface and a still-reachable destination
  after the trusted interface disappears. This does not measure an established
  WebSocket across a physical VPN outage or prove the old Moto kernel's behavior.
- These latest corrections still require installation/native acceptance on the
  reference Moto. Its USB maintenance link currently times out. The previous
  installed revision's native fixture results above do not validate this build.
  The owner reports Edge TTS is already prepared in Hermes; this client agent
  did not install or change anything on that server.
- Complete owner login and an audible Groq → Hermes → Edge turn remain pending.

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
