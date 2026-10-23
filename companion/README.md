# Moto Hermes companion

Optional Rust voice companion for the existing Moto G4 Linux touch shell.
Rust handles private networking/authentication, conversation state, local hearing,
TTS playback and animated vector poses; Tk hosts the fullscreen character and
native setup inputs. Say **Olá Hermes**, wait for acknowledgment and converse
without push-to-talk. **Nova conversa** creates a fresh context; closing returns
to the existing terminal.

**Experimental, with reference-device fixtures; live voice acceptance pending.** Read the canonical
[first connection/setup guide](../docs/hermes-setup.md#first-connection-checklist),
[tutorial em português](../docs/hermes-quickstart.pt-BR.md),
[instructions to send your Hermes server](../docs/hermes-server-agent.md) and
[research/design](../docs/hermes-assistant.md). No personal account state,
configured rootfs or public flashable image is supplied.

The setup supports both **Umbrel password only** and **password + optional 2FA**.
Everyone uses their own server/account, CA trust and Groq key. The new app does
not replace the terminal, SSH or Tailscale setup.

Build on a Linux filesystem with the versions in
[toolchains.json](toolchains.json), then run:

```sh
cargo fmt --all --check
cargo test --locked
cargo clippy --all-targets --locked -- -D warnings
cargo build --release --locked
```

`--smoke` performs a small runtime test without an account or recording.
`--face-stdio` renders compact local poses without network/configuration.
`--listen --device hw:C,D` is a separate local-only capture/VAD/wake process.
It requires the pinned model and separately built whisper.cpp bridge; see
`scripts/build-wake.py` in the parent project. It never creates an HTTP client
or uploads activation audio. Capture stops when the app closes.
`--stdio --config <private-config.json>` is a private JSON-lines interface used
by the panel; credentials travel through stdin, never command arguments.
Do not run it in a terminal while manually entering secrets. See
[hermes.example.json](hermes.example.json) for the non-secret configuration schema.

`tests/contracts.rs` covers endpoint/handoff/input bounds and state invariants;
`tests/gateway.rs` runs the real executable against synthetic HTTP/WebSocket and
ALSA fixtures, including loss/restart without duplicate submission. The Python
suite and isolated UI review live in the parent repository's `tests/` directory.
Hearing tests cover exact activation/commands, real WebRTC VAD rejection of
constant background and bounded speech endpointing. New-session fixtures verify
context replacement, persistence and failure/uncertain-turn protection.
`tests/tls.rs` uses the OpenSSL CLI to generate a fresh test CA and verifies
HTTPS/WSS trust and hostname checks. It never loads a person's certificate.

Original companion code is MIT. Cargo dependencies retain their own licenses;
the build helper records dependency license metadata and discovered notices.
