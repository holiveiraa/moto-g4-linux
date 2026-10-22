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

## Isolated UI / PTY reviews

`review-*.py` files are **not** in the default runner. They require a native
ARM64 Moto environment with Tk/Xorg tools (and sometimes a private tmux server).
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

Never use a person's live tmux session for destructive close/typing tests.
Start/stop only the Xvfb/tmux processes created by the review. Do not overwrite a
real Groq configuration or Tailscale identity to create a screenshot.

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

## Hardware acceptance

Only the owner can confirm physical feel, audio output and unplugged Power-on.
Use [status](../docs/status.md) and the final phase of
[agent installation](../docs/agent-installation.md). A simulated API response,
source test or successful compilation must not be reported as a hardware result.
