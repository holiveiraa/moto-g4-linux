# Hardware and project status

Evidence reviewed: **24 October 2026**. The working prototype has been exercised
on one **Motorola Moto G4 Plus XT1640, athene P2A, 2 GB RAM / 32 GB storage**,
with its original **Athene_16MP** hardware description. No other variant is
certified by this project. Product-family similarity does not establish matching
panel, touch, amplifier, memory layout or partition geometry.

Current Hermes activation uses **Groq for wake phrases and requests**; the
phone runs only speech detection. See [the latest delivery/session correction](#conversation-reuse-and-completed-reply-recovery--24-october).
Earlier local-ASR sections below are dated history, not installation guidance.

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
| Hermes fullscreen companion | Installed; native fixtures and real-service chain pass with synthetic audio | Owner wake/noise, physical conversation and heat/battery pending |

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

This is the first correction checkpoint; the later dispatcher-selection section
below supersedes its assumption about the actual dashboard entry.

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
- The USB SSH link later became reachable without a PnP restart. A fresh backup
  was verified, then **three userspace files** were installed transactionally:
  the Rust core and two Python host modules. Independent hash/size/mode checks
  passed; native runtime smoke and the GUI restart passed, personal configuration
  was unchanged and tmux `@0` remained present. This does not establish a USB fix.
- **All 37 Rust tests**, **15 companion Python tests** and the fullscreen
  Tk/XTest review then passed **directly on the Moto**, using isolated local
  services, a separate Xvfb/tmux environment and fresh synthetic TLS credentials.
  The fixture core is byte-identical to the installed clean-source artifact.
- A fresh temporary configuration on the Moto reached the real existing Umbrel
  application over the numeric Tailscale IP using HTTP and returned the expected
  login-required state. No owner credentials were supplied; this verifies the
  native LocalAPI/interface-bound discovery path, not authenticated chat/audio.
  The owner reports Edge TTS is already prepared in Hermes; this client agent
  did not install or change anything on that server.
- Complete owner login and an audible Groq → Hermes → Edge turn remain pending.

## Hermes gateway compatibility and RPC diagnostics — installed

After successful Umbrel login, the owner reported a generic Hermes RPC refusal.
Safe diagnostics identified **`session.create`, code `4000`, with
`session_authority: false`** on the real app entry. That dashboard was serving
the legacy contract, while earlier app-local inspection had found canonical
contracts. The same Hermes version can expose both; version matching alone did
not validate the actual client path. The follow-up records
only the client method, numeric RPC code, optional `gateway.ready` canonical
authority flag and allowlisted reason/field identifiers in a private 0600 file;
the UI shows method/code. Raw server errors, credentials and conversation data
are excluded. This distinguishes a live protocol/profile failure without
guessing or trying alternate mutating requests.

The source also omits `title` from creation. The canonical server resolves an
existing title before considering `request_id`; a fixed title could therefore
make **Nova conversa** return an old conversation. Strict fixtures now reject
titled creation from this client.

- **42 Rust tests**, Rustfmt/Clippy, **117 Python regressions** and a clean-source
  ARM64 build pass on Linux/WSL. Privacy tests inject secret error text/details
  and verify that neither the report nor UI includes them.
- The client now waits for `gateway.ready`, selects canonical or legacy before
  mutations, and uses that contract's create/resume, submit receipt, reply and
  cancellation rules. It never retries a failed mutation with another adapter.
  Legacy queue/steer/redirect receipts cannot prove a unique current execution;
  they remain uncertain without replay or speaking a preceding completion.
- The follow-up was installed with fresh verified rollback backups, independent
  input checks, native runtime smoke, preserved personal configuration and tmux
  `@0`. The final core is 3,523,160 bytes, SHA256
  `57a0533842d359e39254510b0318e5cb0f0d1c485d496b26b78484a5c86239a6`.
- **All 42 Rust tests**, **16 companion Python tests** and the isolated
  fullscreen Tk/XTest review passed directly on the reference Moto. Both
  canonical and legacy network fixtures run against the byte-identical core;
  synthetic data and separate Xvfb/tmux servers preserve the owner's session.
- During the update, one authorized targeted Windows PnP recovery returned
  `3010` (restart required). SSH later became available; no automatic Windows
  reboot or repeated device reset was performed. USB stability is not proven.
- After the update, the phone's private state confirmed a real persistent
  Moto-session identity and saved Umbrel app access, with no new RPC failure.
  Protected login and session creation now work on the actual legacy entry.
  No session IDs, cookies or endpoint addresses were published. Real prompt/
  response and the complete spoken conversation still need owner acceptance.

## Hermes voice recovery and live-service chain — installed

On 23 October, the owner reported that activation left the face at three dots
and no message appeared in the new Hermes conversation. A rejected local wake
candidate had no event restoring standby. The matching Rust/native update now
restores listening and retains only one private decision's safe metrics. No
standby audio is sent to Groq and activation thresholds were not loosened.

The linked review then found a separate real speech defect: the relay sent valid
PCM batches of 320,256 and 343,296 bytes beyond the client's 256 KiB assumption.
Speech now has separate reception/playback, bounded per-piece memory, explicit
stage/error diagnostics and no total-duration/total-byte cutoff. The reader
answers WebSocket Ping during paced playback; cancellation shuts down an
independent socket handle to interrupt unfinished messages. All response text
pieces reach a persistent player. Synthesis pauses between pieces remain a
documented limitation. See [speech policy](hermes-setup.md#speech-transport-and-safe-diagnostics).

- **52 Rust tests**, Rustfmt/Clippy and **119 Python offline regressions** pass.
  All **52 Rust tests**, **18 companion Python tests** and the isolated
  fullscreen Tk/XTest/tmux review also passed directly on the Moto. Fixtures
  cover multi-megabyte PCM, sample-boundary fragmentation, >11 minutes of media
  consumed by a fast sink, bounded headers, trickling-message cancellation and
  heartbeat handling during paced playback.
- The **entire linked real-service chain passed on the Moto**: synthetic
  non-wake rejection → local synthetic activation → real Edge acknowledgment →
  post-wake capture → real Groq transcript → isolated real Hermes conversation →
  real Edge reply → automatic listening. A synthetic PCM sink received 153,216
  bytes for acknowledgment and 451,584 for the reply; the reply rate was 24 kHz
  and its largest batch 327,168 bytes. No transcript, reply, credentials,
  endpoint or conversation identity is published. This does not verify the
  owner's voice, acoustic conditions or physical speaker path.
- The userspace update was staged and hash-checked with a fresh private rollback
  archive, preserving owner settings and tmux `@0`. The core is 3,543,584 bytes,
  SHA256 `330ef1476687d362ef7c7ec89d00b2dd2d93f663cdd08736c90cf0bba6eac356`.
- The owner explicitly enabled incoming Tailscale SSH on the Moto and confirmed
  the existing identity-check challenge. A verified root session worked over
  the VPN while LAN port 22 refused connections. USB Dropbear was preserved;
  its earlier connectivity problem remains unresolved. No boot/partition,
  account enrollment or Umbrel host change was made. A subsequent boot was
  observed with incoming VPN SSH still available; the reboot cause is unknown.

## Physical wake diagnosis and capture filtering — 23 October

The owner correctly rejected simulated audio as proof of a real conversation.
Three deliberate, labelled activation attempts were rejected locally, before
any agent message. **Owner-voice activation remains unaccepted.** Increasing
model size/context alone did not resolve those samples. No speculative model,
prompt or threshold change was installed.

The following userspace correction adds antialias filtering before 48-to-16 kHz
wake conversion and safe capture-duration/RMS/peak/clipping metrics. A spectral
regression fails with the old box average and passes with the new filter.
Candidate checks retain the standby caption, so checking does not imply that
activation succeeded. A temporary calibration window was removed and the normal
desktop restored. Deliberate calibration must start PCM before its cue and
automatically close its screen.

- **53 Rust tests**, formatting/Clippy and **119 Python offline regressions**
  passed; **53 native Rust tests**, **18 companion Python tests** and the
  isolated Tk/tmux review passed on the reference Moto.
- The linked Groq/Hermes/Edge chain passed again with synthetic input/output.
  An additional isolated run used a synthetic wake candidate, then the **real
  microphone and speaker**: a known synthetic question was played acoustically,
  transcribed by Groq, answered by the agent, spoken and followed by rearming.
  Acknowledgment/reply contained 153,216/464,256 PCM bytes at 24 kHz. This proves
  the post-wake hardware path in that run, not activation with the owner's voice.
- A test that inserted an additional playback bridge reported a drain timeout;
  the direct production player passed without that bridge. The failed bridged
  run is not counted as a production playback failure.
- Physical speaker-to-microphone loopback reached the local recognizer, but
  phrase spelling/confidence were unreliable. The filter corrects signal
  quality; it does not establish that activation accuracy is fixed.
- Three userspace files were installed with verified input/readback and fresh
  rollback backup. Owner settings and tmux `@0` were preserved. The core is
  3,548,680 bytes, SHA256
  `b7f0fb6389c8eba8ea4fabd63f53694d6092193c159a16c9e3cf69cb7dee793d`.
  No server-runtime or Umbrel host configuration was accessed or changed.

## Conversation activated by opening the app — 24 October

An explicit **Começar a conversa ao abrir** setting (`start_on_open: true`)
allows the owner to open the fullscreen companion, hear acknowledgment and
start talking without first passing the experimental local recognizer. The
reference Moto has this option enabled. Missing/old settings remain false;
the app never silently opts other installations into transcription on opening.
Reconnection and face redraw do not count as a new opening. Unfinished work
blocks activation. **Voltar a dormir** returns to local wake mode; closing and
reopening explicitly activates again.

- **54 Rust tests**, formatting/Clippy and **121 offline Python regressions**
  passed. All **54 Rust tests**, **20 companion Python tests** and the isolated
  native Tk/tmux review passed on the reference phone.
- Opening activation passed the linked real-service review. A separate run
  used the real capture/playback devices and a known question played
  acoustically: Groq recognized the expected sentence, Hermes answered, ALSA
  completed acknowledgment/reply and the app rearmed. The run consumed
  153,216/324,864 PCM bytes at 24 kHz, with largest reply message 200,448 bytes.
  The activation source was explicitly `app_open`, not simulated recognition.
- The three matching components and the opted-in configuration were installed
  with a fresh verified rollback archive and independent readback. Connection
  settings and tmux `@0`/`@1` were preserved. The core is 3,550,232 bytes, SHA256
  `7fae21faa43bde63aaf6bf9d2f135b6b785cc366e4db3c7f48f5b05ae3ec018c`.
- Local “Olá Hermes” accuracy remains unresolved. An owner calibration again
  produced a mismatched local transcript; the owner reported no audible phrase
  on local replay. No further owner repetitions were requested. Nominal ALSA
  completion/loopback is not proof that the owner heard speech. Complete
  conversation with that owner's voice and hearing still needs acceptance.
- Research was refreshed against primary Xiaozhi, StackChan and JARVIS sources;
  see [the concrete architectural comparison](hermes-assistant.md#esp32-reference-check--24-october).
  No new server deployment, Umbrel host access or new Astra review was needed.

## Answer delivery after display blanking — 24 October

The owner confirmed a spoken greeting and a real voice request reaching Hermes,
but the face stayed “thinking” after the answer was already visible elsewhere.
Read-only inspection found a completed owned conversation and no surviving
companion workers behind the frozen face. The answer and transcript were far
below the existing size budgets; no conversation contents or identifiers are
published here.

Screen blanking had called the full application-close path. Waking restored
the backlight without recreating that face, and reconnect history read only
canonical `content` despite legacy rows using `text`. Blanking now pauses local
audio/animation while retaining network completion delivery. Waking restores
the current face, without automatically replaying a historical answer. An
explicit **Ouvir última resposta** action plays a known completed answer without
another agent submission. The first TTS piece now targets 100 characters;
later pieces retain the 400-character target, with exact text preservation.

- **55 Rust tests**, formatting/Clippy and **123 offline Python regressions**
  passed. All **55 native Rust tests**, **22 companion Python tests** and the
  isolated Tk/tmux review passed on the Moto. The UI review covers completion
  both during blanking and after waking, including a long synthetic answer.
- The linked Groq/Hermes/Edge app-open chain passed with known synthetic speech
  and an exact transcript check. This is not a claim of a measured universal
  speech-latency bound; synthesis/network delays still apply.
- The four matching userspace components were installed with a fresh verified
  rollback archive and independent readback, preserving configuration and tmux
  `@0`/`@1`. The core is 3,550,936 bytes, SHA256
  `3ee2537f94b10c0dc432b81d2866c414257f5338d21bd19e8fcf642a669326ee`.
- The owner had already confirmed the stranded task was complete. After checking
  the matching current conversation, the local unknown state was acknowledged
  explicitly, with no prompt resubmission or server/host administration.

## Unsolicited voice-loop correction — 24 October

The owner reported replies continuing without interaction. The loop was stopped
by closing the client. A local probe reproduced WebRTC false positives from
low-level microphone noise (candidate RMS roughly 13-41 signed-16 units); Groq
returned short text for these clips. An energy-only correction passed a short
quiet test but failed the extended physical idle review, and was not installed.

Every candidate now passes a second, local Silero v6.2.0 speech verifier before
wake recognition or Groq. Its pinned model is 885,098 bytes. Missing/corrupt
assets stop listening with a local error instead of uploading unverified noise.
Only the latest counter/decision snapshots are kept in private volatile `/run`
files. The owner-requested opening mode waits for **Olá Hermes**; continuous
turns begin only after activation, with capture paused throughout playback.

- Host checks: **56 Rust tests**, format/Clippy and **124 offline Python tests**.
  The matching **56 native Rust**, **23 companion Python** tests and isolated
  fullscreen/tmux review passed on the reference Moto.
- A native verifier review rejected silence/noise, accepted known synthetic
  speech and confirmed state reset between packets, without network or audio I/O.
- The real-service chain passed with synthetic **Olá Hermes**, an exact known
  question, one transcription/agent submission and five seconds of rearmed
  low-level speech-shaped noise without another request.
- A separate physical speaker/microphone chain recognized its known acoustic
  question, completed Groq/Hermes/Edge playback, and stayed listening for **60
  seconds without another transcription or agent submission**. This verifies
  that bounded setup, not every possible room or the owner's wake accuracy.
- Six userspace files were installed with verified rollback and independent
  readback, preserving the current tmux session. The core is 3,558,344 bytes,
  SHA256 `2ac208ce48c63b01376376d071ae2e17b2d776758893a708d0c016e77ad1e5ee`.
  Only the owner's explicit app-opening preference was then changed to wait
  for local activation. No server deployment or Umbrel administration occurred.

## Acoustic wake-model correction — 24 October

After the noise-loop correction, the owner still could not activate the app.
The latest local decision showed a strong, unclipped capture but a phrase
mismatch from the tiny recognizer. An acoustic comparison reproduced the
mismatch; peak gain and full context alone did not fix tiny. Multilingual base
q5_1 with the proper-name hint `Hermes.` recognized the known acoustic wake
phrase at roughly 2.9 seconds of inference on the Moto. The continuous flow
also exposed low-amplitude speech rejected before recognition; the two local
model inputs now use bounded peak normalization, retaining raw WebRTC/noise-floor
measurements. No standby audio is uploaded.

Current files use the pinned 59,707,625-byte base model, release the wake
recognizer after activation, and accept repetitions of only the wake phrase
without accepting a substring of another request. The existing confidence and
no-speech thresholds were retained. This replaces the wake model, not the
Hermes conversation/profile or server setup.

- **57 host Rust tests**, format/Clippy and **124 offline Python regressions**
  passed, along with matching native fixtures and the isolated fullscreen review.
- Native Silero review covers ordinary and quiet known speech, silence/noise
  rejection, and reset between packets.
- The opt-in **physical wake-word chain** passed with the actual microphone and
  speaker: a supplied known wake phrase, spoken acknowledgment, an exact known
  question, one Groq transcription/agent turn, complete Edge playback, and
  **60 seconds of rearmed listening without an extra request**.
- This acoustic pass starts directly with the wake phrase. A separate
  negative-first acoustic stress sequence did not consistently activate in the
  observed room and is exposed as `--physical-negative-first`; the result must
  not be presented as a negative-first pass. A separate continuous-capture local
  probe rejected its non-wake phrase and accepted its wake phrase.
- Owner-voice acceptance and noise robustness remain physical acceptance gates;
  synthetic acoustic speech is not the owner's voice. Heat/battery remain unmeasured.

The installed Rust core is 3,559,368 bytes, SHA256
`a195dc062c88c53ccd02b4c4bc53ff9ac121b72ba209c174a3cefca120b631d0`.
The core, wake helper, speech verifier and base model form one guarded userspace
update. Configuration, current conversation and tmux were preserved; no Umbrel
host/runtime changes or new cloud wake fallback were made.

## Groq activation — 24 October

The owner still could not activate after the base-model update. Capture had
strong, unclipped voice but local ASR returned a phrase mismatch. A previous
synthetic acoustic pass did not establish owner-voice usability. Local word
decoding has now been removed: Groq recognizes both **Olá Hermes** and requests,
using the existing private dictation key. This is the requested Groq/Edge path.

WebRTC endpointing and pinned Silero speech detection remain local to filter
silence/noise. With the app open, voiced standby clips also go to Groq and
consume its quota. A rejected phrase returns silently to standby; an accepted
wake phrase is acknowledged, never submitted to Hermes. Capture pauses during
upload, agent work and speech, then rearms after the acoustic tail. Closing or
blanking stops capture. There is no local-ASR fallback or automatic upload retry.
Errors remain visible; diagnostics keep a Groq verdict/count, without words.

- **55 Rust tests** pass on host and on the reference Moto, with formatting and
  Clippy checks. **127 offline Python regressions** pass; the 26 Hermes cases
  also pass natively. The isolated fullscreen/input/tmux review passed.
- The real Groq → Hermes → Edge chain passed on the Moto with synthetic audio:
  two wake transcriptions (negative then accepted), one request transcription,
  exactly one agent turn and complete speech, followed by rearmed listening.
- The separate **physical microphone/speaker** chain also passed the negative
  phrase, wake phrase and exact known question, with complete Edge playback and
  **60 seconds without an extra transcription or agent turn**. The stimuli were
  synthetic speech played in the room; this is not owner-voice acceptance.
- Owner voice in the intended room, longer ambient-noise use, latency under
  service/network load and controlled heat/battery remain acceptance limits.

The installed core is 3,542,416 bytes, SHA256
`6f0c7122e03b2e2397192543d8f1ccada18b2a4d577e870d3d7cbe7422eec25b`.
Four userspace files were installed: the core, speech-detector binary and two
matching native integration modules. Independent hash/size/mode readback passed;
the obsolete local recognizer and tiny/base ASR weights were removed after
verified backup. Configuration, conversation journal and tmux survived the GUI
restart. The app reopened connected in wake standby. Silero's small detector
model remains. No Hermes server change was needed; no Umbrel host was accessed.

## Conversation reuse and completed-reply recovery — 24 October

The owner reported a completed server answer with a phone still showing thinking,
plus unwanted empty conversations. Earlier short real-service passes did not
cover those delivery losses. Repeated real-service reviews also created separate
test conversations; that behavior is now an explicit opt-in.

The client keeps one authenticated chat WebSocket for the open app instead of
opening one for each operation. Reopening resumes the stored conversation;
failure does not create a replacement. Legacy turns baseline the event sequence
before submission and read missing events every two seconds while pending,
checking runtime, epoch and sequence. This recovers a missing final notification
without submitting another prompt. A completed reply also remains in the Rust
worker's memory until the UI acknowledges its local turn tag. Duplicate/stale
deliveries cannot speak twice. Uncertain executions still require reconciliation.

- **58 Rust tests** and formatting/Clippy passed on the build host. The same
  Rust tests, **28 Hermes Python regressions** and isolated fullscreen/tmux
  review passed natively. The complete offline Python suite has **129 tests**.
- Fixtures deliberately lose a server terminal event and a local UI delivery;
  recovery preserves one submission. Two ordinary turns use one socket and one
  conversation; restart resumes it without another creation.
- The real **Groq → Hermes → Edge** acoustic chain passed with synthetic speech
  played through the physical speaker and received by the physical microphone:
  rejected non-wake phrase, accepted wake phrase, **two consecutive questions
  about sorveterias in Lavras**, two spoken replies and rearmed listening for
  **60 seconds without an extra request**. It reused the existing conversation;
  the stored ID and server conversation count stayed unchanged.
- That acoustic check required the complete normalized words `sorveteria` and
  `lavras`, not a verbatim transcript. An earlier strict full-sentence acoustic
  comparison failed before submitting its question; it is not reported as a pass.
- The first local reply delivery was deliberately discarded: cache recovery
  requested synthesis **929 ms** after the reply became available. The normal
  second delivery requested synthesis in **10 ms**. These measure client delivery
  to the synthesis request, not provider latency or first audible sound. Both
  actual PCM playbacks completed.
- Live reviews now require an existing idle test journal, or explicit permission
  to create one conversation. Reuse fails closed on a mismatched binding. The
  original journal stays unchanged; test prompts do add turns on the server.

The installed core is 3,557,440 bytes, SHA256
`b013a799ab321d2389ab93fa3bf82d3c41a0f717dd8a13c13ab03311b1753353`.
The core/native modules were installed with verified backup, guarded rollback
and independent hash/size/mode readback. Configuration, stored conversation and
tmux were preserved, and the app reopened connected in wake standby. Existing
server conversations were not deleted. No Umbrel host/runtime changes occurred.

The owner's natural voice in the intended room, long ambient-noise use and
controlled heat/battery remain acceptance limits; this controlled acoustic test
does not establish every room, connection or utterance.

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
