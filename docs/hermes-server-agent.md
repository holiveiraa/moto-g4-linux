# Hermes-side setup: instructions for the agent

This guide is for **Hermes running inside its own app environment** after the
owner supplies the published repository URL. The Moto/client agent prepares the
phone and repository. Hermes configures its own side. Neither workflow
administers the Umbrel host.

## Hard boundary

Never SSH to the Umbrel host, open a host shell, run host-management commands,
use Docker/Podman APIs or sockets, enter another container, or write through a
host bind mount outside Hermes's own application data. Do not use `sudo`,
`nsenter`, host package managers, host service managers or privileged containers.
Do not inspect/change Umbrel services, app manifests, proxy rules, published
ports, authentication, TLS, firewall, VPN or SSH policy. Do not restart Umbrel
or its application services as a troubleshooting step.

Operate only on the current Hermes runtime and its own profile/application
configuration using the installed version's supported interfaces. A filesystem
being visible does not make it part of that scope. If a required change needs
host access, stop that step and report the missing capability. Do not propose
host commands as a workaround.

## Owner prompt

After the companion changes have been published, send Hermes the repository
URL and this prompt. Replace the placeholder with the real published URL or
commit; never invent a release that has not been pushed.

> Prepare your Hermes side for my Moto companion from REPOSITORY_URL. Read
> AGENTS.md, docs/hermes-server-agent.md and docs/hermes-setup.md. Work only
> inside your own Hermes app/runtime and profile data. Never access or change
> the Umbrel host, Docker, gateway, authentication, ports or services. Inspect
> your version and supported configuration, reuse existing APIs and configure
> Edge TTS for the agreed profile without disturbing my existing Telegram
> setup. Use my own credentials only through private fields. Back up any
> profile configuration you change, test a harmless response and report what
> passed, what needs a phone test and anything blocked by this boundary.

Em português:

> Prepare sua parte do Hermes para meu app do Moto a partir de REPOSITORY_URL.
> Leia AGENTS.md, docs/hermes-server-agent.md e docs/hermes-setup.md. Trabalhe
> somente dentro do seu próprio app/runtime e dos dados do perfil Hermes.
> Nunca acesse nem altere o host do Umbrel, Docker, gateway, autenticação,
> portas ou serviços. Confira sua versão e configuração, reutilize as APIs
> existentes e prepare o Edge TTS no perfil combinado, preservando o Telegram.
> Faça backup da configuração que mudar, teste uma resposta inofensiva e
> informe os resultados e qualquer impedimento sem recorrer ao host.

## Inspect before changing configuration

1. Read the installed Hermes version and its supported config/profile help
   from inside this app. The current client targets **v0.22.4**; another version
   needs contract verification, not an automatic app/image upgrade.
2. Identify the current Hermes profile and its actual configuration location.
   Do not print `.env`, keys, cookies, config secrets or complete diagnostic
   dumps. Report only version, non-secret provider/profile information and
   boolean capability results.
3. Confirm the built-in chat, voice-config and speech routes below exist in
   this installed version. The current implementation needs **no new plugin**
   when those contracts match. Do not install a community plugin merely because
   the repository research mentions it.
4. Prefer the already working profile if its settings fit. If changing it would
   affect Telegram/other clients, arrange a dedicated profile using supported
   Hermes facilities and agree on the profile name with the owner. Do not clone
   credentials or assume all profiles have the same tools/settings.
5. Before edits, make a private backup of that profile's configuration within
   Hermes-owned app data and record a checksum and restoration procedure. Keep
   backups, generated audio and diagnostics out of the public checkout.

## Configure speech within Hermes

Use the installed version's supported configuration interface; inspect its help
before choosing commands. Merge only the needed settings, preserving all other
profile configuration. For the inspected v0.22.4 schema the relevant shape is:

```yaml
tts:
  provider: edge
  edge:
    voice: pt-BR-VOICE-CONFIRMED-BY-INSTALLED-PROVIDER
voice:
  client_direct: true
```

The voice value is deliberately a placeholder. Enumerate voices with the
installed Edge provider and choose an available pt-BR voice with the owner.
Do not paste the placeholder into a working config. Edge synthesis uses an
online service; absence of a per-request API key does not guarantee availability.

Check Edge's Python dependency inside **this Hermes environment**. Install a
missing optional feature only through Hermes's supported app-local dependency
mechanism, within the owner's requested setup. Do not use the host's Python or
package manager. Check that this runtime can perform the PCM conversion needed
by its existing speech route. If a converter is unavailable and cannot be
provided inside this app's supported runtime, report it and keep text usable.
Never install a host package, alter an app image or restart a host service.

The schema above follows the pinned [TTS configuration loader and provider
dispatch](https://github.com/NousResearch/hermes-agent/blob/4d04303818b61bf3aa09278af48356315515965b/tools/tts_tool.py)
and [Edge backend](https://github.com/NousResearch/hermes-agent/blob/4d04303818b61bf3aa09278af48356315515965b/tools/tts_tool_providers.py).
Verify the installed version rather than blindly applying an upstream example.

## Contracts the Moto expects

| Interface | Required behavior |
| --- | --- |
| Protected application entry | Existing Umbrel app login remains in front of Hermes; password-only and challenged 2FA accounts both remain supported. |
| `/api/ws` | Existing authenticated JSON-RPC: create/resume a dedicated conversation, submit a prompt and interrupt that runtime session. |
| Chat events | `method: event`, `params.type: message.complete`, matching runtime `session_id`, final text in `params.payload.text`. |
| `/api/audio/voice-config` | Authenticated, profile-scoped response with `ok: true`, `tts.mode: relay`, `tts.reason: provider 'edge' has no client wire` for v0.22.4. |
| `/api/audio/speak-stream` | Existing authenticated WS accepts text and returns JSON start/end metadata plus mono S16_LE PCM. |
| Profile selection | The same named profile applies to chat and audio; the client passes it as configured. |

`voice-config` can contain **other providers' API keys**. Inspect only the
non-secret Edge verdict in memory; never print, save, attach or forward the
complete response. The Moto refuses speech if it cannot confirm that verdict.
`voice.client_direct` enables this existing provider-resolution report; the
Moto still uses server relay for Edge and never receives/uses a paid-provider
key. Keep profile provider settings fixed during a conversation.

Microphone capture and Groq STT happen on the Moto with that installation's
private Groq key. No extra Groq key, Telegram bot, voice daemon, wake-word server
or always-listening process needs to be installed in Hermes for this client.

The Moto keeps its own conversation ID in the selected profile across app
opens. The spoken **Nova conversa** action creates a fresh conversation only
after checking that the old turn is settled; it does not delete previous chats
or reset Telegram. Do not merge/broadcast other clients' sessions into it.

## Validate and hand back

Use an innocuous fixed phrase to test Edge synthesis inside Hermes; do not
replay private conversations. Remove only the generated test audio afterward.
Check the installed chat/audio schemas against the expected contracts with
app-local fixtures or supported inspection. App-local success does not prove
that the public Umbrel login/WS path or the Moto speaker works.

The owner supplies the actual application URL to the phone and enters the
Umbrel password there. If the account has no 2FA, enter only the password; if
Umbrel challenges for a code, the phone asks for it. Do not enable/disable 2FA,
extract Umbrel account secrets or export browser cookies to make onboarding work.

Return a short report: installed Hermes version, agreed profile, confirmed Edge
voice, which app-local checks passed, backup/rollback location, any app-runtime
dependency limit, and what still needs an end-to-end Moto test. Do not call the
integration complete until a fresh phone utterance produces a visible and
audible answer through the protected public path.

If the current built-in APIs differ, describe the smallest app-local adapter
needed, its authentication/session scope and tests before implementing it.
Never solve a mismatch by exposing an internal port or weakening Umbrel access.
