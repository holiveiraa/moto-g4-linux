# Tests and evidence

## Offline suite

Use Python 3.10+ on Linux/WSL:

```sh
python3 scripts/check-repository.py
python3 scripts/run-tests.py
```

The curated runner executes only offline regressions: contact lifetime, saved
Wi-Fi transactions, audio-start ordering, voice/transcription/paste contracts,
saved SSH metadata/password binding, Tailscale states, the local configuration
form, clean-userspace staging and Wiki export. API responses and hardware paths
are synthetic. The local credential-form test binds only loopback and uses a
fake SSH sink. No real account, cloud request or connected phone is needed.

The tests have hyphenated filenames and are run explicitly; do not assume a
default unittest filename-discovery command includes them all. POSIX file locks,
termios and symlinks are intentional; use WSL rather than native Windows Python.

## Rust companion fixtures

With the pinned Rust toolchain and OpenSSL CLI installed, run `cargo test
--locked` inside `companion/`. Tests exercise real loopback HTTP/WS for
password-only and challenged 2FA login, handoff/cookies, event scoping, lost
responses/restart, interrupt finalization and fake ALSA PCM/failure. Fresh
TLS fixtures exercise HTTPS/WSS CA trust and hostname rejection. No owner
server, Groq or Edge service is contacted. Python `test-hermes.py` also checks
capture ownership, private IPC, stale results, deferred credential deletion
and half-duplex behavior. See [setup](../docs/hermes-setup.md).

For a native ARM64 review, cross-build the fixture executables with the pinned
`cargo zigbuild --release --tests --locked --target aarch64-unknown-linux-musl`.
Inside a private review directory on that device, `MOTO_HERMES_BINARY` selects
the matching staged companion binary for gateway tests. If the device lacks an
OpenSSL CLI, `MOTO_HERMES_TLS_FIXTURE` can point to a private directory containing
fresh synthetic `ca.pem`, `leaf.pem` and `leaf.key` generated for that review,
with a localhost DNS SAN and short validity. Never supply a production CA/key.
Record which suites actually ran; a cross-build alone is not a native result.

Speech fixtures include 4 MiB messages, WebSocket fragmentation in the middle
of an int16 sample and 32 MiB of cumulative PCM at 24 kHz (>11 minutes of media,
consumed by a fast synthetic sink). They check every output byte and safe
diagnostics. A header claiming more than the message memory budget is refused
without sending/reading its payload. These tests establish transport behavior;
they do not play eleven minutes through the physical speaker.
Additional fixtures cancel during a continuously trickling unfinished message,
require a Pong while a paced output is still playing and check that all text
pieces reach one persistent player.

## Isolated UI / PTY reviews

`review-*.py` files are **not** in the default runner. They require a native
Linux environment with Tk/Xorg tools (some are Moto-specific) (and sometimes a private tmux server).
Read each file before running. Stage current modules and tests together in a
private temporary directory, set `MOTO_UI_REVIEW_DIR` to that module directory
and provide an isolated `Xvfb :9 -screen 0 1080x1920x24` session. Keep
`test_support.py` alongside reviews that import fixtures.

| Review | What it checks |
| --- | --- |
| `review-panel-v2.py` | Brightness, scrolling, masked forms, pending-auth protection and stale tasks |
| `review-connections.py` | Separate Wi-Fi/VPN/SSH pages, favorite CRUD, optional secret UI and direct ID launcher |
| `review-input-focus.py` | Actual XTest field/keyboard taps, native focus/caret blinking and no input leak |
| `review-terminal-tabs.py` | Stable IDs, close/cancel, limits and last-tab replacement |
| `review-voice-panel.py` | Fake-key forms, review editing and real UTF-8 PTY paste without Enter |
| `review-quick-voice.py` | Keyboard microphone lifecycle/cancellation and paste without Enter |
| `review-tailscale-panel.py` | First-use no-URL/QR state, completion, degraded state and separate SSH check |
| `review-hermes.py` | Fullscreen face, native Text/caret, login/2FA, blank/wake with network retained, long reply after wake, no unsolicited historical speech, close cleanup and preserved tmux |
| `review-experience.py` | Themes/preview/revert, direct panel access, native field isolation, accented UTF-8 PTY input and event-driven wake/idle error paths |

The experience review uses an isolated xterm and tmux server, synthetic UX/host
configuration and a fake backlight file. It checks that live theme output never
reaches the pane's stdin, and that the retained theme and keyboard paths do not
reintroduce redundant action/draft menus. It does not establish battery life. The offline suite also covers
preference merging/permissions, palette contrast and keyboard/launcher contracts.

The Hermes review also runs on a host with `xvfb-run`, `xterm`, `tmux`,
`xdotool`, `xwd` and Python/Tk. Set `MOTO_HERMES_BINARY` to the built host binary
and optionally `MOTO_HERMES_REVIEW_OUTPUT` to a private screenshot folder; its
account/network events are synthetic while Rust renders the actual face.

Never use a person's live tmux session for destructive close/typing tests.
Start/stop only the Xvfb/tmux processes created by the review. Do not overwrite a
real Groq configuration or Tailscale identity to create a screenshot.

## Opt-in live Hermes voice chain

`review-vad.py --binary /path/to/moto-vad --model /path/to/ggml-silero-v6.2.0.bin
--speech-wav /path/to/known-synthetic-16k.wav` is a separate native-only check.
It rejects silence/low noise, accepts the supplied known speech and checks
reset between packets. It uses no microphone, speaker, account or network.

Supply `--expected-transcript "your known synthetic question"` to verify
recognized content as well as event ordering. A mismatch fails before sending
it to the agent and reports no returned words. Without this option, a pass
establishes protocol flow, not recognition of the intended sentence. This review
replaces microphone and speaker; it does not prove physical activation.

Add **`--physical-audio --activation wake-word --idle-seconds 60`** for the
explicit acoustic review. Close the production voice app first. In its private
Xvfb/tmux session, the review uses the real microphone/speaker, plays the supplied
wake phrase and requires
activation, then plays the known question after acknowledgment. It checks the
exact transcript, spoken reply and rearmed idle period. No recording is exported.
This plays synthetic stimuli in the room; it does not establish owner-voice
acceptance. `--physical-negative-first` separately exercises rejection followed
by activation; its result is reported explicitly. Staged wake helpers/models can be selected with the local review
overrides described in [setup](../docs/hermes-setup.md#local-activation-stays-at-three-dots).

Use `--activation app-open` to exercise the opted-in opening gesture instead
of the local wake recognizer. This verifies the actual GUI → listener activation,
spoken acknowledgment, question, reply and rearming. Its capture fixture starts
with the question and must not pretend a wake-word candidate was recognized.
The default `--activation wake-word` still checks local rejection/acceptance.
After rearming, the fixture feeds low-level speech-shaped noise and observes
five seconds with no extra transcription or agent submission. Use
`--idle-seconds 60` for a longer observation (allowed range 5-90 seconds).

`review-hermes-live.py` exercises the actual Tk controller, Rust network worker,
local VAD/recognizer/model and real Groq → Hermes → Edge services in one chain.
It replaces only ALSA capture/playback with generated speech and a PCM byte
sink. It verifies a rejected activation returning to standby, accepted activation,
spoken acknowledgment, one post-wake transcription, one agent turn, spoken
reply and automatic listening afterward. It does not establish recognition of
the owner's voice or physical microphone/speaker performance.

Run only with the owner's authorization to use those services. Close the
production Hermes app, stage reviewed modules and binary together, then start
a private Xvfb display. The local recognizer/model and matching Silero verifier
must already be installed, or selected through the staged VAD review overrides
documented in [setup](../docs/hermes-setup.md#unsolicited-replies-or-a-conversation-loop).
Supply three synthetic mono 16 kHz S16 WAVs: a non-wake phrase, “Olá Hermes”
and a harmless question. Do not use personal recordings in a published fixture.

```sh
xvfb-run -a -s '-screen 0 1080x1920x24 -nolisten tcp' \
  python3 tests/review-hermes-live.py \
  --live-config /root/.config/moto-linux/hermes.json \
  --binary /usr/local/bin/moto-hermes \
  --negative-wav /private/synthetic/negative.wav \
  --wake-wav /private/synthetic/wake.wav \
  --question-wav /private/synthetic/question.wav
```

This is deliberately excluded from offline CI. It uses the existing remembered
Umbrel cookie and Groq key locally in a temporary private directory, creates a
separate server conversation and leaves the production journal unchanged. That
test conversation remains on Hermes for inspection. Credentials, synthetic
recordings and PCM are not included in its result; temporary local copies are
removed after the workers stop. The source files are checked unchanged. If the
cookie needs a fresh login, log in through the normal phone UI first. Do not put
passwords or keys on this command line or in a report.

`review-wifi-saved-device.py` is explicitly a **live saved-profile persistence
check**, not an isolated mock: it saves the currently connected profile but
refuses ADD/SELECT/REMOVE and DHCP renewal. It is opt-in maintenance, not CI.

## Real SSH-password fixture

The Windows orchestrator `review-ssh-password-server.py` uses test-only Paramiko
3.5.1 under `.private/ssh-test-deps`, a loopback server with no real OS account
and a temporary USB-maintenance reverse tunnel. Stage its device review/modules
under `/tmp/moto-ui-review` first, with an executable askpass helper and private
maintenance key/known-host files. It exercises the Moto's actual OpenSSH client
and controlling PTY; it never authenticates to an owner's server.

It checks known/unknown/changed host keys, saved/correct/wrong/empty passwords and
manual override. The random fixture secret is removed on completion. This is an
integration test, not a production runtime dependency.

## Isolated HTTP-over-Tailscale confinement review

[`review-tailnet.py`](review-tailnet.py) runs only in a disposable root Linux
container with its own network namespace, `NET_ADMIN`, Python3 and iproute2.
Install those test dependencies first, then disconnect **that container** from
external networks; the script requires only `lo` to exist before starting.
Mount only public source and the built host Rust binary. Run inside it:

```sh
MOTO_TAILNET_REVIEW=1 MOTO_HERMES_BINARY=/path/to/moto-hermes \
  python3 tests/review-tailnet.py
```

It creates a synthetic LocalAPI Unix socket and a dummy `tailscale0` only in
that disposable namespace. It verifies actual HTTP and WS Upgrade delivery,
then stopped VPN, unknown peer, down interface and a missing trusted interface
while the destination remains assigned to an alternative interface. The latter
cases must send no HTTP/WS request, including reuse of the same worker and HTTP
connection pool. It removes only its own socket/interface.
No real VPN enrollment, route policy, credentials or remote server is used.
This verifies those request paths, not an established WebSocket across interface
removal, WireGuard encryption or phone-kernel acceptance.

Rust gateway fixtures enforce the **canonical** v0.22.4 session field set:
`source: gui`, `request_id`, minimal resume, generation-bound interruption and
owned queued-admission cancellation. They reject unknown fields with `4001`
instead of accepting a fabricated legacy request. See the pinned
[canonical contracts](https://github.com/NousResearch/hermes-agent/blob/4d04303818b61bf3aa09278af48356315515965b/tui_gateway/contracts/canonical_sessions.py).
Separate legacy fixtures omit the authority flag and reject canonical fields
with `4000`. They exercise its creation/resume, streaming replies, fresh context,
runtime-scoped interruption and ambiguous queue handling. Mode selection happens
before mutation; an error never triggers a retry with another contract.

## Physical acceptance

Only the owner can confirm physical feel, audio output and unplugged Power-on.
Use [status](../docs/status.md) and the final phase of
[agent installation](../docs/agent-installation.md). A simulated API response,
source test or successful compilation must not be reported as a hardware result.

The Hermes offline regressions also exercise local wake/upload gating at the UI
boundary, automatic rearming after speech, stale transcription epochs, exact
new-conversation handling, uncertain-turn guards and forced-child cleanup. Rust
fixtures cover speech endpoint bounds, constant background rejection via actual
WebRTC VAD and persistent/failing new-session creation. These do not establish
acoustic wake accuracy, CPU/heat/battery or audible speech on a handset.
