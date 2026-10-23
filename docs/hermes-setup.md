# Set up the Hermes companion

The optional **Hermes** app opens as a fullscreen animated companion and closes
back to the existing terminal. After first connection setup, say **Olá Hermes**,
wait for its spoken acknowledgment, and converse entirely by voice. **Nova
conversa** starts a fresh context; **Fechar aplicativo** returns to the terminal.
The main screen has a face and short state captions, with a discreet options
menu. Rust owns hearing/network/speech/animation; Tk hosts the native canvas and
setup/password fields.

**Status: experimental app installed on the reference Moto.** All **28 Rust
fixtures**, **14 companion Python regressions** and the fullscreen Tk/XTest/tmux
review passed directly on that Moto, in addition to host checks. The seven-file
userspace update was installed transactionally, then independently checked by
hash/size/mode; model startup passed and tmux `@0` survived the GUI restart.
Synthetic local recognition took 1.326–1.906 seconds per sample, with roughly
78 MB resident memory. Actual-owner wake accuracy, heat/battery, server login
and live Groq/Edge remain open gates. This phone still needs its first connection
setup. See [status](status.md) and [research/design](hermes-assistant.md).
There is no universal installer.

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
3. **Open Painel → Hermes → ··· → Configurar.** Enter the HTTPS origin of your
   existing Hermes app, Umbrel account ID and agreed profile. Normally leave
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

Standby activation runs locally using WebRTC VAD and a pinned multilingual
Whisper tiny model. The activation clip is discarded, never uploaded. After
acknowledgment, each utterance is sent to Groq when speech ends automatically.
Replies reach the server's online Edge service after its provider verdict is
confirmed. Both normal transcription and speech synthesis require internet.
Missing local components produce an explicit error, with no cloud wake fallback.

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

## Build the local activation component

On the Linux build host, install CMake >=3.20 and make, and use the same pinned
Zig 0.15.2 as the Rust cross build:

```sh
python3 scripts/build-wake.py --target host
python3 scripts/build-wake.py --target aarch64-linux-musl
```

The helper verifies the source archive and multilingual `ggml-tiny-q5_1.bin`
against [pinned hashes](../companion/wake/pins.json), builds a static CPU-only
`moto-wake`, and collects project/upstream notices. Downloads/builds remain in a
separate Linux work folder. The model is 32,152,673 bytes; budget additional
runtime memory and measure actual heat/latency before accepting wake behavior.
No Python speech framework or model download runs on the phone at app startup.
The small C++ bridge uses maintained whisper.cpp; the coordinator, voice state,
VAD endpointing and activation policy remain Rust.

## Prepare a userspace installation

First follow [agent installation](agent-installation.md) for a new phone. Do not
copy another person's configured root filesystem. Build/validate for that exact
device and retain its own recovery route.

The optional companion's file layout is:

| Destination | Source |
| --- | --- |
| `/usr/local/bin/moto-hermes` | Verified ARM64 Rust artifact, 0755 |
| `/usr/local/bin/moto-wake` | Verified static ARM64 recognizer artifact, 0755 |
| `/usr/local/share/moto-hermes/ggml-tiny-q5_1.bin` | Hash-verified model, 0644 |
| `/usr/sbin/moto-hermes-pet.py` | Original fullscreen canvas |
| `/usr/sbin/moto-hermes.py` | Private configuration / process boundary |
| `/usr/sbin/moto-hermes-panel.py` | Existing panel's app host |
| `/usr/sbin/moto-capture.py` | Shared capture ownership |
| `/usr/sbin/moto-voice.py`, `/usr/sbin/moto-panel.py` | Matching sources from the same revision |
| `/usr/sbin/moto-shell` | Executable copy of matching `moto-shell.py` |

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

1. Copy your actual Hermes application URL from Umbrel. Use HTTPS and the
   correct application port; the internal Docker dashboard port is not proof
   of the public application URL. Examples use `server.example`, never an
   owner's address. Do not include a password, path, token or query string.
   This client currently requires HTTPS. If your only existing app entry is
   HTTP, report that compatibility blocker; do not open an internal port,
   change the Umbrel gateway or disable TLS checks to work around it.
2. Enter your Umbrel account ID (`0` for the owner account), and your Hermes
   profile if needed. Use an account that already has access to this app.
3. Normally leave **Origem do login Umbrel** blank: umbrelOS 2.0's app-auth
   service uses the same hostname on port 2000. If your verified deployment
   exposes a different auth origin, enter that exact HTTPS origin explicitly.
   The app refuses a login redirect to any other origin/port.
4. If Umbrel uses a private CA, obtain and independently verify its CA
   certificate, store its PEM on this installation and select its path. System
   roots and this extra CA are used for both HTTPS and WSS. Do not turn off
   certificate checks to get past an error or blindly trust a downloaded cert.
5. Choose spoken replies and whether to remember the app session. Save, then
   connect. Passwords and 2FA codes are entered only on the phone's private
   fields, never in chat, terminal arguments, examples or diagnostic logs.

The [example JSON](../companion/hermes.example.json) documents the schema for
agent-assisted setup. The GUI saves `/root/.config/moto-linux/hermes.json`
atomically with file mode 0600 and parent mode 0700. The example is not an
installation input containing another owner's credentials.

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

1. Open **Painel → Hermes**. Once connected, the face waits for **Olá Hermes**.
2. Say the phrase alone, then wait for **Olá! Estou ouvindo.** The entire
   activation clip is discarded; say your actual request after acknowledgment.
3. Speak normally. After approximately 700 ms of detected silence, the app
   transcribes the bounded utterance (up to 45 seconds), asks your Hermes and
   speaks its reply. It automatically listens again, with no button or repeated
   wake word needed for each turn.
4. Say **Nova conversa** (or **Hermes, nova conversa**) as a complete utterance
   to create a fresh Moto conversation in the same profile. The previous one is
   kept on the server. Switching is blocked while a task is running/uncertain;
   failed creation keeps the previous context. An interrupted creation can leave
   an empty server conversation; the app never guesses a successful new ID.
5. Say **Voltar a dormir** to return to local activation, or **Fechar aplicativo**
   / **Voltar ao terminal** to close the app. The × also exits. Long press or ···
   opens secondary controls, setup and text/history. Exact commands are handled
   before the LLM; a sentence merely mentioning “nova conversa” stays a request.

Capture pauses while transcribing, waiting for Hermes and speaking. Listening
resumes 400 ms after playback completion; interruption over the speaker/AEC is
not established. Closing, opening setup and screen blanking stop local capture;
closed apps do not keep hearing. Screen-off remains backlight blanking, not
suspend/locking. Voice commands after activation use Groq, so network failures
can prevent those commands; ×/hardware screen controls remain available.

The app retains its dedicated conversation between opens in the chosen profile.
It does not attach to Telegram. **Nova conversa** intentionally replaces that
current ID after server confirmation. Authentication persistence is a separate
option: remembering a conversation does not save your password. A fresh
conversation clears chat context, not the profile's durable memory or tools. Old replies
are restored silently after reconnect. Approvals and uncertain tasks use the
existing Hermes UI/secondary recovery menu in this preview. Closing local UI
cannot guarantee cancellation of already accepted tools on the server.

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
| Wake component/model missing | Build/install both verified artifacts; the listener refuses corrupt models and does not upload standby audio. |
| Wake slow or misses speech | Measure actual pt-BR pronunciation/distance and CPU/heat. This general recognition model is experimental; host synthetic results do not prove device usability. |
| Microphone busy | Finish another dictation/recording. Both use the same inherited capture lease. Do not kill unrelated ALSA processes. |
| Groq failure | Check that this phone has its own valid Groq key, internet and quota. Record again; no automatic upload retry occurs. |
| Text works but voice fails | Check Edge provider/dependencies and pt-BR voice on the selected Hermes profile, then the existing ALSA speaker route. An unknown/non-Edge verdict stops speech before opening the speech socket. Keep server profile settings fixed while speaking; this preflight is not an atomic server-side provider lock. |
| Unknown task result | Inspect the owned Hermes conversation before acknowledging. Never assume that disconnect rolled back server actions. |

Do not attach credentials, cookie/task files, recordings or owner diagnostics to
GitHub issues. Share versions, sanitized error text, target/build hashes and a
synthetic reproduction instead.

## Acceptance before calling an installation ready

Check the exact hardware and artifact hashes; real-kernel runtime/TLS; login
with the owner's enabled authentication mode; microphone/speaker/volume;
Portuguese wake accuracy, false activations under TV/music/silence, wake latency,
CPU/memory/heat, transcription and speech; new-conversation context isolation,
automatic listening after answers, failure/reconnect/cancellation; audio
release on exit/screen blank; and the original SSH/tmux session surviving
repeated app opens/closes. Use isolated Xvfb/tmux fixtures for destructive typing
and closing tests. Record physical acceptance separately from CI/build results.
