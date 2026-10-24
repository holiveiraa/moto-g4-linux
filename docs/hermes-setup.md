# Set up the Hermes companion

The optional **Hermes** app opens as a fullscreen animated companion and closes
back to the existing terminal. After first connection setup, say **Olá Hermes**,
wait for its spoken acknowledgment, and converse entirely by voice. **Nova
conversa** starts a fresh context; **Fechar aplicativo** returns to the terminal.
The main screen has a face and short state captions, with a discreet options
menu. Rust owns hearing/network/speech/animation; Tk hosts the native canvas and
setup/password fields.

**Status: experimental app on the reference Moto.** Current verification includes
57 Rust fixtures, 124 offline Python regressions and isolated native GUI reviews.
The real Groq/Hermes/Edge chain also passed with a known question played through
the physical speaker and microphone, followed by 60 seconds of rearmed listening
without an extra transcription or agent request. Local speech verification now
uses Silero before either wake recognition or Groq. This bounded observation is
not a guarantee for every room or voice. Owner-voice wake acceptance and
heat/battery remain open gates. Real Umbrel login and Moto-session creation are
confirmed on the reference installation.
See [status](status.md) and [research/design](hermes-assistant.md).
There is no universal installer.

**23 October compatibility correction:** the current source selects the announced
canonical or legacy Hermes `/api/ws` contract and supports verified HTTP over Tailscale.
It passes **52 host Rust tests** and **119 Python regressions**. The reference
Moto has this update. Other older installations need matching userspace files
before an HTTP Tailscale URL works. See the current
[live-service evidence and physical limits](status.md#hermes-voice-recovery-and-live-service-chain--installed).

![Fullscreen companion rendered with synthetic services](assets/hermes.png)

This is actual Rust/Tk output under an isolated Xvfb display **on the reference
Moto**. Account and connection events are synthetic; the image does not prove
microphone recognition or cloud behavior.

## First connection checklist

If Linux and the companion components already work on your Moto, start here;
you do not need to rebuild or reinstall the phone to configure an account.
For a complete Portuguese walkthrough, see
[Hermes no Moto: do setup à primeira conversa](hermes-quickstart.pt-BR.md).

1. **Give your running Hermes the [server-agent instructions](hermes-server-agent.md).**
   Use the copyable prompt there. Hermes checks its version and built-in APIs,
   backs up its own profile configuration and prepares Edge TTS inside its own
   runtime. Get the agreed profile and available pt-BR voice from its report.
   No additional plugin is needed when the documented API contracts match.
2. **On the Moto, configure your Groq key** under **Painel → Voz e áudio → Groq**.
   This is the existing dictation key for this installation, not a shared key
   from the developer or a key to put in the Hermes chat.
3. **Open Painel → Hermes → ··· → Configurar.** Enter the origin of your
   existing Hermes app: HTTPS, or HTTP using its numeric Tailscale IP with the
   Moto's existing VPN connected. Enter the Umbrel account ID and agreed profile. Normally leave
   the auth-origin field blank; select a separately verified CA PEM only if
   your server uses a private CA. Enable spoken replies. See
   [field-by-field connection setup](#configure-your-own-connection).
4. **Save and connect.** Enter your Umbrel password in the phone's masked
   field. Without 2FA, that is all. If the account requires it, enter the code
   when asked. Do not change account security or export browser cookies.
5. **Say “Olá Hermes”, wait for acknowledgment, then ask a simple question.**
   Check an audible answer and automatic listening afterward. Say **Nova
   conversa** to verify a fresh context, then **Voltar ao terminal** to close.
   Follow [the conversation walkthrough](#talk-and-return-to-the-terminal).

The phone goes through **Umbrel's existing app gateway/login** to reach
**Hermes's chat/audio APIs**. The companion uses a dedicated Moto conversation
in the chosen profile; it does not attach to or reset Telegram. Wi-Fi/Tailscale
provides reachability, while Umbrel provides authentication. This workflow
never administers the Umbrel host.

### If Hermes refuses an operation after login

The current source appends the fixed RPC method and numeric error code to that
message. Its private `hermes-diagnostic.json`, beside `hermes.json`, keeps only
those identifiers, the optional canonical-authority flag and explicitly allowed
reason/field names. It never stores the raw error message/detail, URL, profile,
parameters, result, credentials or transcript. The file has mode 0600. Do not
publish the surrounding private configuration directory.

Give the method/code to the agent investigating compatibility. A blank profile
uses the default authority; changing it at random is not a diagnosis. Confirm
the actual dashboard's `gateway.ready` authority flag using the
[server contract guide](hermes-server-agent.md#contracts-the-moto-expects).
The client waits for that announcement and selects the matching canonical or
legacy contract before creating a session. Both can exist in one Hermes version.
See [current acceptance](status.md#hermes-gateway-compatibility-and-rpc-diagnostics--installed).

If the launcher reports a missing binary/model, continue with the requirements,
build and userspace installation below. For a new phone, install/validate the
base Linux port first. A source checkout is not a ready flashable image.

## Requirements

**Server ownership:** never administer the Umbrel host for this feature.
The owner gives the published repository to Hermes, which performs its own
app-local setup using [these agent instructions](hermes-server-agent.md).
The Moto/client agent handles the phone only. SSH to the Umbrel host, Docker
control, host package/service changes and gateway changes are outside this
workflow, including for diagnostics.

- A compatible, independently verified native Moto G4 Linux installation.
  This port's reference is XT1640 / athene P2A, 2 GB / 32 GB.
- Existing Xorg/Tk shell, working microphone/speaker, `alsa-utils`, normal
  `default`/`moto_speaker` playback and a populated CA certificate store.
- Your own running Hermes Agent and Umbrel account. The implemented protocol
  targets **Hermes v0.22.4 and umbrelOS 2.0**; older/newer releases need their
  contracts checked. No second agent, Telegram bot or Tailscale account is needed.
- For an HTTP-only Umbrel, use the existing Tailscale installation on the Moto
  and the server's numeric Tailscale IP. The standard `tailscale0` interface and
  root-owned `/run/tailscale/tailscaled.sock` LocalAPI are required. No Umbrel
  HTTPS proxy, Serve/Funnel, port exposure or host configuration is needed.
- A Groq account/key, configured privately through **Voz e áudio → Groq** on
  this installation. The app reuses that installation's `groq.json` schema.
- Hermes's selected profile configured for **Edge TTS**, with its supported
  runtime dependencies already installed. The inspected `/api/audio/voice-config`
  must identify Edge; leave `voice.client_direct` enabled (default in v0.22.4)
  so the endpoint exposes the provider verdict. No direct-provider key is used
  by this client. Configure a pt-BR voice available in
  your provider. Do not change shared Telegram settings without reviewing the
  impact; a profile dedicated to the Moto is an option, not an automatic change.
- OpenSSL command-line tools for fresh synthetic TLS certificates in host tests.
- Linux/WSL for builds, with source/build outputs on the Linux filesystem.
  Windows can continue owning USB. Normal builds never contact a device.

Groq recognizes both **Olá Hermes** and subsequent requests, using the same
private key as dictation. While the app is open and connected, voiced clips are
sent to Groq even before activation. Silence and rejected noise stay local:
WebRTC endpointing and a pinned Silero model detect speech, not words. The phone
does not run Whisper transcription or load an ASR model. Wake text is checked
for the complete phrase and never sent to Hermes as a request. Internet/Groq
quota are required from standby onward; Edge synthesis also requires internet.
Closing or blanking stops capture. Explicit app-open activation skips the wake
utterance and proceeds directly to the spoken acknowledgment.

## Build from public source

Clone the published source into a Linux directory, then install the tool versions
listed in [toolchain pins](../companion/toolchains.json). With rustup, for example:

```sh
rustup toolchain install 1.99.1 --profile minimal --component rustfmt --component clippy
rustup default 1.99.1
python3 scripts/check-repository.py
python3 scripts/run-tests.py
python3 scripts/build-companion.py --target host
```

Use a dedicated shell/toolchain override if other projects need a different
default. The helper verifies the Rust version, exports public candidate files
to a fresh directory under `~/moto-g4-work/companion-builds`, runs formatting,
Rust tests and Clippy, and builds with the committed Cargo lockfile. It leaves
the source checkout, owner accounts and phone untouched. Initial dependency
downloads require internet; tests themselves use loopback fixtures.

For the phone target, install Zig **0.15.2** from its official distribution,
verify its published checksum, place `zig` on PATH, and prepare the cross tools:

```sh
rustup target add aarch64-unknown-linux-musl
cargo install cargo-zigbuild --version 0.24.0 --locked
python3 scripts/build-companion.py --target aarch64-unknown-linux-musl
```

The tool pins record the x86_64 Linux Zig archive checksum used for validation;
other build-host architectures need their matching official archive/checksum.
The [cargo-zigbuild upstream guide](https://github.com/rust-cross/cargo-zigbuild)
explains supported hosts and cross-linking. Do not use `target-cpu=native` for a
binary intended for another computer.

Each build writes an `artifact/` folder containing `moto-hermes`, `build.json`
with its target/size/SHA256, public-source and lockfile hashes, the project
license, dependency lockfile, declared license inventory
and discovered upstream license/notice files. Review this provenance before
redistributing a binary. Build artifacts, cached sources and personal files
remain outside Git. There is no automatic release or upload step.

For development, run `cargo test --locked` inside `companion/`; the real
HTTP/WebSocket fixture exercises password-only login, a 2FA challenge, the
one-use handoff, authenticated WS, session isolation, cancellation, fake ALSA
PCM playback and a lost response across a client restart. Separate real HTTPS/WSS fixtures
verify custom-CA trust, rejection of unknown CAs and hostname mismatches. They
use fresh test-only certificates and no real key.

## Build the local speech detector

On the Linux build host, install CMake >=3.20 and make, and use the same pinned
Zig 0.15.2 as the Rust cross build:

```sh
python3 scripts/build-hearing.py --target host
python3 scripts/build-hearing.py --target aarch64-linux-musl
```

The helper verifies the upstream source and `ggml-silero-v6.2.0.bin` against
[pinned hashes](../companion/wake/pins.json), builds static CPU-only `moto-vad`
and collects project/upstream/model notices. The detector model is 885,098 bytes.
The C++ bridge uses whisper.cpp's VAD API only: it does not transcribe words,
download Whisper ASR weights or build `moto-wake`. `scripts/build-wake.py` is a
compatibility entry point to this same detector build. Downloads/build outputs
stay in a separate Linux work folder; nothing downloads when the app starts.

## Prepare a userspace installation

First follow [agent installation](agent-installation.md) for a new phone. Do not
copy another person's configured root filesystem. Build/validate for that exact
device and retain its own recovery route.

The optional companion's file layout is:

| Destination | Source |
| --- | --- |
| `/usr/local/bin/moto-hermes` | Verified ARM64 Rust artifact, 0755 |
| `/usr/local/bin/moto-vad` | Matching static ARM64 Silero verifier, 0755 |
| `/usr/local/share/moto-hermes/ggml-silero-v6.2.0.bin` | Pinned 885,098-byte speech model, 0644 |
| `/usr/sbin/moto-hermes-pet.py` | Original fullscreen canvas |
| `/usr/sbin/moto-hermes.py` | Private configuration / process boundary |
| `/usr/sbin/moto-hermes-panel.py` | Existing panel's app host |
| `/usr/sbin/moto-capture.py` | Shared capture ownership |
| `/usr/sbin/moto-voice.py`, `/usr/sbin/moto-panel.py` | Matching sources from the same revision |
| `/usr/sbin/moto-shell` | Executable copy of matching `moto-shell.py` |

For an upgrade from the former local-ASR version, back up and verify all changed
files first. Install matching Rust/native modules and the Silero detector/model;
restart only the GUI with the app closed, preserving tmux/configuration. After
verifying the replacement, remove the obsolete `moto-wake`,
`ggml-base-q5_1.bin` and `ggml-tiny-q5_1.bin` if installed. These are not required
by the Groq path. Keep the verified userspace backup for rollback. Do not change
firmware, audio services, network policy or the Hermes server for this update.

The regular [clean userspace assembler](../scripts/assemble-userspace.py)
automatically includes the Python modules. The Rust binary is optional and is
installed separately, mode 0755. Do not mix the updated recorder with a source
set missing `moto-capture.py`, or the panel with missing companion modules.

Before updating an existing phone, prepare a private userspace backup and hash
manifest, identify every destination, verify the rollback archive and review
the GUI restart impact. Preserve the tmux server/session and its immutable IDs.
An update is a separate owner-approved deployment action; this guide is not an
unchecked remote installer. No boot image, partition, firmware, SSH policy or
Tailscale identity needs to change for this app.

Before launching the GUI on real hardware, run the ARM64 binary's `--smoke`
check from an isolated maintenance session. Then separately verify certificate
validation/TLS, audio and UI on the actual old kernel. QEMU user-mode and host
tests do not substitute for these checks.

## Configure your own connection

Open **Painel → Hermes → ··· → Configurar** (or hold the face). The app remains
optional; the terminal works even before the Rust binary or server is configured.

1. Copy your actual Hermes application URL from Umbrel. Use its existing
   HTTPS origin, or HTTP with its numeric Tailscale IP and correct app port;
   the internal Docker dashboard port is not proof
   of the public application URL. Examples use `server.example`, never an
   owner's address. Do not include a password, path, token or query string.
   For example, `http://100.64.0.10:18790` is a synthetic Tailscale example.
   Convert a browser URL such as `/chat?profile=default` by removing the path/
   query and putting `default` in the separate profile field. Ordinary LAN or
   public HTTP and HTTP DNS names are refused; the app verifies the encrypted
   route before using HTTP, rather than merely trusting a `100.x` prefix.
2. Enter your Umbrel account ID (`0` for the owner account), and your Hermes
   profile if needed. Use an account that already has access to this app.
3. Normally leave **Origem do login Umbrel** blank: umbrelOS 2.0's app-auth
   service uses the same hostname on port 2000. If your verified deployment
   exposes a different auth origin, enter that exact permitted origin explicitly.
   The app refuses a login redirect to any other origin/port.
4. If Umbrel uses a private CA, obtain and independently verify its CA
   certificate, store its PEM on this installation and select its path. System
   roots and this extra CA are used for both HTTPS and WSS. Do not turn off
   certificate checks to get past an error or blindly trust a downloaded cert.
5. Choose spoken replies and whether to remember the app session. Save, then
   connect. Passwords and 2FA codes are entered only on the phone's private
   fields, never in chat, terminal arguments, examples or diagnostic logs.

For conversation immediately after launching, enable **Começar a conversa ao
abrir** (`start_on_open: true`). Opening the fullscreen app then counts as the
activation gesture: after authentication and a check for unfinished work, it
says **Olá! Estou ouvindo.** and captures the next utterance for Groq. No local
wake inference is needed to start this mode. Old/unspecified settings remain
`false`; an update never silently opts an existing installation into cloud
transcription on launch. Reconnecting alone does not activate it.

The [example JSON](../companion/hermes.example.json) documents the schema for
agent-assisted setup. The GUI saves `/root/.config/moto-linux/hermes.json`
atomically with file mode 0600 and parent mode 0700. The example is not an
installation input containing another owner's credentials.

### HTTP over your existing Tailscale

Keep Tailscale connected on the Moto and use the **server's numeric Tailscale
IP**, with the app's existing port. The same address works at home or through
another phone's Wi-Fi hotspot when both nodes have internet and tailnet access.
Do not use `umbrel.local` remotely; this HTTP mode deliberately accepts numeric
peer IPs rather than DNS names. HTTPS hostnames keep their normal certificate
verification and can use Wi-Fi or Tailscale.

The Rust client checks the local root-owned Tailscale daemon and its peer
credentials, then requires `Running`, TUN mode and the destination in an online
peer's actual `TailscaleIPs`. It binds HTTP **and WS** sockets to `tailscale0`
before connecting. Login and handoff are checked separately before any request;
redirect origins remain exact. There is no proxy or LAN-route fallback when
the VPN/interface is missing. The existing plaintext HTTP inside the VPN is
protected by Tailscale, not by TLS. Merely being in the CGNAT IP range is
insufficient. Userspace-only Tailscale and subnet-routed LAN HTTP are not supported.

Normally leave the auth-origin field empty: the same scheme/IP on port 2000
is used. If the gateway returns a different origin, inspect the actual app
login contract and configure only a separately verified permitted origin.
Do not remove Umbrel login or change the host. No CA PEM is needed for HTTP;
HTTPS still enforces CA/hostname checks, including WSS.

### Password-only and optional two-factor login

**If your account has no 2FA, enter just your Umbrel password.** The app does
not require or enable two-factor authentication. It completes the existing
Umbrel app login and one-use handoff, then opens the protected Hermes session.

If the server responds that 2FA is required, the app opens the code field and
reuses the password in memory for that same attempt. Enter your current
authenticator code. Wrong/expired codes can be retried; a wrong password returns
a password error. Leaving the app/login flow clears the retained password.
Account security settings remain entirely with Umbrel.

An optionally remembered session is stored in `hermes-auth.json`, bound to the
server/auth origin/account/profile. It contains a revocable app-access cookie,
not the password. That cookie can authorize other apps shared with the account;
it is not a Hermes-only grant. Files are permission protected, not encrypted.
**Esquecer sessão salva** removes the local cookie; use Umbrel's session controls
to revoke the server session. Never clone this file to another installation.

Wi-Fi and Tailscale are alternative network routes, not different login systems.
Use a hostname whose certificate is valid on the route you configured. Switching
to a new URL/account creates a different local binding and requires that target's
own authentication. The app does not copy VPN state or change SSH users.

## Talk and return to the terminal

1. Open **Painel → Hermes**. With **Começar a conversa ao abrir** enabled, it
   connects and speaks **Olá! Estou ouvindo.** automatically. Wait for that
   acknowledgment, then ask your question.
2. With that option disabled, the face instead waits for **Olá Hermes**.
   Say the phrase alone and wait for the acknowledgment. That activation clip
   goes to Groq for recognition, then is discarded; the actual request must
   follow the acknowledgment. It is never an agent request.
3. Speak normally. After approximately 700 ms of detected silence, the app
   transcribes the bounded utterance (up to 45 seconds), asks your Hermes and
   speaks its reply. It automatically listens again, with no button or repeated
   wake word needed for each turn.
4. Say **Nova conversa** (or **Hermes, nova conversa**) as a complete utterance
   to create a fresh Moto conversation in the same profile. The previous one is
   kept on the server. Switching is blocked while a task is running/uncertain;
   failed creation keeps the previous context. An interrupted creation can leave
   an empty server conversation; the app never guesses a successful new ID.
5. Say **Voltar a dormir** to return to waiting for activation, or **Fechar aplicativo**
   / **Voltar ao terminal** to close the app. The × also exits. Long press or ···
   opens secondary controls, setup and text/history. Exact commands are handled
   before the LLM; a sentence merely mentioning “nova conversa” stays a request.

After **Voltar a dormir**, opening activation is not repeated just because the
face redraws or reconnects. Close and explicitly reopen the app to start by
launch again. No activity continues after closing it.

Capture pauses while transcribing, waiting for Hermes and speaking. Listening
resumes 400 ms after playback completion; interruption over the speaker/AEC is
not established. Closing, opening setup and screen blanking stop local capture;
closed apps do not keep hearing. Screen-off remains backlight blanking, not
suspend/locking. Activation and voice commands use Groq, so network failures
can prevent those commands; ×/hardware screen controls remain available.

Blanking pauses the microphone, playback and animation, while keeping the
network conversation alive to receive an in-flight answer. Waking redraws the
face from current state instead of leaving a frozen “thinking” caption. A reply
that completed while blank is retained, not automatically spoken on waking.
Use **··· → Ouvir última resposta** to hear a known completed answer without
submitting another agent turn. Legacy reconnect history uses `text` rows;
canonical `content` rows are supported too. An uncertain task still requires
the owner's explicit reconciliation before replaying history.

The app retains its dedicated conversation between opens in the chosen profile.
It does not attach to Telegram. **Nova conversa** intentionally replaces that
current ID after server confirmation. Authentication persistence is a separate
option: remembering a conversation does not save your password. A fresh
conversation clears chat context, not the profile's durable memory or tools. Old replies
are restored silently after reconnect. Approvals and uncertain tasks use the
existing Hermes UI/secondary recovery menu in this preview. Closing local UI
cannot guarantee cancellation of already accepted tools on the server.

## Session lifetime and reply delivery

One open app keeps one authenticated chat WebSocket. Questions and explicit
**Nova conversa** use that connection; normal turns do not open another chat
socket. The stored conversation is resumed on reopening. A failed resume does
not silently fall back to creating a conversation. The first setup creates one
conversation; subsequent creation requires the explicit new-conversation action.
Closing releases the socket and local workers, preserving the journal.

For the legacy contract, each turn records an event watermark before submission.
While awaiting completion, a two-second read-only event replay backstop recovers
missing notifications from that execution. It checks the runtime ID, sequence
and replay epoch; truncation/epoch change requires reconciliation. It never
resubmits a prompt, creates a session or selects a historical answer by position.

The Rust worker also retains the completed reply in memory until the UI
acknowledges its local turn tag. A pending UI checks that cache after one second,
then every two seconds. Duplicate/stale deliveries cannot trigger repeated
speech. This cache is not persisted and never repeats an agent operation.

Private, volatile `/run/moto-hermes-diagnostics/delivery.json` keeps the last 16
delivery stages, monotonic timings, state flags and character counts. It contains
no words, server address, token or conversation ID. The separate speech diagnostic
records PCM completion; a delivered reply is not itself proof of audible output.

## Disconnects and troubleshooting

`hermes-task.json` keeps the server binding, owned conversation ID and an
in-flight marker. It never stores the prompt, password, Groq key or recordings.
The marker is saved before submitting work. A lost connection/response or app
restart can make the outcome **unknown**; the app blocks another submission
and does not replay the old prompt. Check the conversation in Hermes, reconnect
if needed, then use **Já conferi a tarefa** to acknowledge uncertainty. That
acknowledgment does not rerun or undo the operation.

| Symptom | Check |
| --- | --- |
| Rust component missing | Build for the correct target and review the userspace file set; confirm executable mode and exact path. |
| TLS/certificate error | Confirm hostname, current device time, CA provenance and both app/auth origins. Do not disable verification. |
| Login redirect refused | Check umbrelOS version and the explicitly allowed auth origin, app ID and public URL. |
| Password works in browser but not app | Confirm account ID and version. The preview supports the inspected Umbrel 2.0 protocol, not arbitrary SSO/older proxy cookies. |
| Code field appears | This account's server requires 2FA; supply the current code for that account. |
| Speech detector/model missing | Install matching `moto-vad` and Silero model; missing/corrupt assets fail closed before upload. |
| Wake slow or misses speech | Check Groq connectivity/quota and the sanitized wake verdict. Measure the real microphone and owner voice; synthetic checks do not establish physical usability. |
| Microphone busy | Finish another dictation/recording. Both use the same inherited capture lease. Do not kill unrelated ALSA processes. |
| Groq failure | Check that this phone has its own valid Groq key, internet and quota. Record again; no automatic upload retry occurs. |
| Text works but voice fails | Check Edge provider/dependencies and pt-BR voice on the selected Hermes profile, then the existing ALSA speaker route. An unknown/non-Edge verdict stops speech before opening the speech socket. Keep server profile settings fixed while speaking; this preflight is not an atomic server-side provider lock. |
| Unknown task result | Inspect the owned Hermes conversation before acknowledging. Never assume that disconnect rolled back server actions. |

Do not attach credentials, cookie/task files, recordings or owner diagnostics to
GitHub issues. Share versions, sanitized error text, target/build hashes and a
synthetic reproduction instead.

### Local activation stays at three dots

Current clients keep **Diga “Olá Hermes”** while checking speech candidates.
Only the spoken **Olá! Estou ouvindo.** confirms activation. Older clients
displayed dots during checks, and one version left them there after rejection.
Update the matching Rust runtime and native host modules. Connecting already
creates/resumes a conversation; an empty chat before accepted activation does
not establish a server fault.

The private `hermes-voice-diagnostic.json`, next to `hermes.json`, retains only
the latest Groq decision: `recognizer: "groq"`, `accepted` and `characters`.
No recognized words, audio, address or session identity are retained. A rejected
wake transcript returns to standby without speaking or contacting the agent.
Groq errors stay visible while local listening rearms; uploads are not retried
automatically. Check the key, connection and quota before repeating the phrase.

The listener uses a low-pass/downsampling step only for the Silero speech
detector. It passes a private WAV to the network worker for Groq interpretation,
then pauses capture during that request. It holds no HTTP client or Groq key.
There is no local-ASR model, local transcript or ASR fallback.

### Unsolicited replies or a conversation loop

Install matching Rust/native modules, `moto-vad` and its pinned Silero model.
The listener now verifies every WebRTC candidate locally before either wake
recognition or Groq. Quiet input previously produced WebRTC false positives;
Groq then returned words even with misleadingly confident metadata. Raising
the energy threshold alone failed the longer physical idle test.

The near-silence/DC floor is 32 signed-16 RMS units (about -60 dBFS); it is only
a prefilter. Silero uses its standard 0.5 speech threshold and requires eight
32 ms windows (256 ms), alongside the existing endpointing. Rejected candidates
stay local and silently return to listening. Missing/corrupt model/helper fails
closed with a visible local error. It must never fall back to uploading noise.

Private `/run/moto-hermes-diagnostics/capture.json` and `speech.json` retain only
the latest counters, energy floor/maximum RMS, accept/reject decision and timing.
The capture snapshot updates every five seconds of active capture; these files
are volatile, owner-only and contain no audio, words, endpoint or conversation
identity. Do not publish owner diagnostics. For isolated native reviews only,
`MOTO_HERMES_VAD_BINARY` and `MOTO_HERMES_VAD_MODEL` select staged assets; the model
hash remains mandatory. Normal launches use the fixed installed locations.

Keep **Começar a conversa ao abrir** off to open quietly and wait for **Olá
Hermes**. After acknowledgment, normal turns need no repeated wake word. During
Hermes's speech the microphone is paused until playback drains; silence is not
a request and must not cause another greeting or agent submission.

### Speech transport and safe diagnostics

Speech has **no client cutoff for total duration or total PCM bytes**. The
client receives PCM/control messages concurrently with ALSA playback. It
does not retain the whole answer. The first text piece targets 100 Unicode
characters to start synthesis sooner; subsequent pieces target 400 characters
at word boundaries. An unbroken token is kept intact. No text
is omitted. Each piece gets its own synthesis socket, with one player retained
across pieces. There can be a synthesis pause at those boundaries; next-piece
prefetch has not been implemented. The actual mono signed-16 sample rate comes
from the server's start metadata (supported: 8–48 kHz).

The inspected [Hermes relay implementation](https://github.com/NousResearch/hermes-agent/blob/4d04303818b61bf3aa09278af48356315515965b/hermes_cli/web_routers/audio.py)
can send a whole sentence's PCM in one message; it promises no 256 KiB or 1 MiB
packet size. Speech therefore has its own transport policy, separate from chat:

- **32 MiB per assembled message and synthesis piece** is a client memory budget, not a
  limit on the whole response or a guarantee about future Hermes versions.
  That payload is 1.56% of the reference phone's 2 GiB RAM. A bounded PCM queue,
  the parser's current message and other overhead can temporarily use more than
  that payload budget. A piece exceeding the budget reports `VOICE_SEGMENT_MEMORY`;
  an oversized message header reports `VOICE_MESSAGE_MEMORY` before its body is read.
- **60 seconds without a complete audio message or successful playback write**
  reports `VOICE_IDLE_TIMEOUT`. Keepalive pings do not extend that deadline.
  Active playback/reception can continue beyond three minutes. Closing/stopping
  still interrupts it. A separate socket reader answers Ping during paced
  playback; cancellation shuts down an independent TCP handle to interrupt even
  an unfinished fragmented message. The final ALSA wait covers the measured pipe capacity at
  the actual sample rate plus two seconds of scheduling/buffer headroom.
- PCM alignment, metadata, early disconnect and playback completion have
  distinct errors. Text remains available, failed speech is not automatically
  repeated, and its error stays visible when listening resumes.

These are explicit supported-client resource policies. Receiving an arbitrarily
large single message with constant memory would require a streaming-message
receiver or bounded framing from the server; increasing a number alone does
not establish that capability. See the pinned
[WebSocket library contract](https://docs.rs/tungstenite/0.28.0/tungstenite/protocol/struct.WebSocketConfig.html).

The private `hermes-speech-diagnostic.json`, next to `hermes.json`, records only
the latest outcome/code, phase, sample rate, accepted PCM bytes, chunk count,
largest chunk, piece count and active memory/idle policies. It contains no reply text, audio,
token, cookie, address or session ID. Share only sanitized findings. Regression
fixtures cover multi-megabyte messages, fragmentation through sample boundaries,
over-eleven-minute equivalent output with a fast sink, oversized headers,
unfinished-message cancellation and Ping/Pong during paced playback.

## Acceptance before calling an installation ready

Check the exact hardware and artifact hashes; real-kernel runtime/TLS; login
with the owner's enabled authentication mode; microphone/speaker/volume;
Portuguese wake accuracy, false activations under TV/music/silence, wake latency,
CPU/memory/heat, transcription and speech; new-conversation context isolation,
automatic listening after answers, failure/reconnect/cancellation; audio
release on exit/screen blank; and the original SSH/tmux session surviving
repeated app opens/closes. Use isolated Xvfb/tmux fixtures for destructive typing
and closing tests. Record physical acceptance separately from CI/build results.
