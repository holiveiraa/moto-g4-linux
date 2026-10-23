# Using the phone

## Hermes: open a voice companion, return to your terminal

After [first connection setup](hermes-setup.md#first-connection-checklist), open
**Painel → Hermes**. A fullscreen animated face replaces the terminal view.
Say **Olá Hermes**, wait for **Olá! Estou ouvindo.**, then ask your question.
The app detects the end of your speech, transcribes with Groq, asks your
existing Hermes and speaks through its Edge TTS service. It then listens again
without another tap or wake phrase.

- **Nova conversa** starts a fresh Moto context in the same profile. Earlier
  chats remain on the server; Telegram and permanent profile memory are separate.
- **Voltar a dormir** returns to local activation.
- **Voltar ao terminal**, **Fechar aplicativo** or **×** closes the app,
  releases its audio and restores the existing terminal sessions.
- **···** or holding the face opens setup, text/history and recovery controls.

The selected Moto conversation persists when reopening the app. Initial setup
uses private touch fields; normal conversation is by voice. Capture pauses
while transcribing, waiting for a reply and speaking. Voice interruption during
playback is not established. Closing or blanking stops listening.

The app is experimental; live voice/noise/heat acceptance is still required.
See [tutorial em português](hermes-quickstart.pt-BR.md),
[instructions to give your Hermes server](hermes-server-agent.md) and
[interface images](screenshots.md). The following terminal features work
independently of configuring Hermes.

## Power and everyday controls

Short Power toggles the screen. Hold for about 1.2 seconds and release to open
the menu. Use **Energy → Shut down** for a real shutdown, then hold Power for a
few seconds to turn on. The unlocked-bootloader warning is expected on this
prototype. A plugged-in USB cable can affect the observed power-on behavior;
test independence without it. Screen off does not lock or suspend Linux.

Volume buttons control speaker volume; zero mutes. Brightness uses the wide
slider or −/+ buttons. Text size is under **System → Terminal and keyboard**.

## Appearance

**Panel → Appearance** offers Jade, Midnight and Paper. A tap previews the theme
across the panel, keyboard and terminal. **Save theme** keeps it; Back or returning
to the terminal cancels an unsaved preview. Changing brightness preserves the
chosen theme and keyboard.

## First Wi-Fi and Tailscale login

1. **Panel → Wi-Fi:** choose a network, enter the owner's password and save.
2. **VPN / Tailscale:** generate the authorization QR.
3. Scan with another phone and authorize the owner's Tailscale account in its
   browser. The alternate URL can also be opened in another trusted browser.
4. Leave the Moto page open; status updates after enrollment. A network that
   requires administrator approval displays that state rather than claiming success.
5. Create destinations in the separate **SSH** page.

No maintenance PC or auth-key entry is required for this UI flow. A browser on
another device is still needed for the QR authorization; there is no integrated
browser for doing the entire identity-provider login on the Moto itself.

Known Wi-Fi networks offer **Connect with saved details**. Updating a password
and forgetting one profile are separate actions. Multiple same-name profiles
are not deleted automatically. A failed join should preserve the previous one.

## SSH destinations and tabs

Save name, address, user, port and **SSH**/**Tailscale SSH** mode. Every new install
starts empty. Tailscale SSH uses its network authorization and port 22. Ordinary
SSH can travel over the VPN and still require a password or key.

Password is optional. A new empty field uses normal authentication; filling it
saves locally. Editing with an empty field preserves an existing saved password.
Remove that password explicitly from the destination details. Changing endpoint
requires a new password. **Open with manual entry** bypasses saved-password
autofill and supports interactive password/2FA. Unknown host keys still require
confirmation; changed keys are not accepted automatically.

Open a destination in a new terminal tab. Use **+ New**, tap a tab to switch and
**× → Close this tab** to close. Removing a favorite does not close a session.
Restarting the GUI keeps tmux sessions; shutting down the phone ends processes.

## Optional maintenance SSH into the Moto over Tailscale

VPN enrollment and permission to log into the phone are separate. To enable
incoming maintenance access, the owner runs this in the Moto's local terminal:

```sh
tailscale set --ssh
```

From a trusted PC already in that tailnet, use `tailscale ssh root@<Moto-name>`
with the phone's own MagicDNS name. The wrapper verifies the server host key
advertised through Tailscale. Follow any identity-check URL required by the
existing tailnet SSH policy. Do not replace that policy to bypass a refusal.
This uses the existing local root account and the tailnet's device/user identity;
no shared password or copied private maintenance key is needed.

Tailscale SSH handles port 22 only for incoming tailnet traffic. The separate
USB Dropbear rescue service keeps its binding and keys; LAN SSH is not opened.
Enrollment alone does not enable this feature, and fresh installs keep it opt-in.
To revoke it locally, run `tailscale set --ssh=false`. See the official
[Tailscale SSH documentation](https://tailscale.com/docs/features/tailscale-ssh).

## Keyboard and forms

Esc, Tab, Ctrl, Alt, Shift and arrows have dedicated keys. Tap a modifier, then
the next key; hold Backspace/arrows to repeat. **#+=** opens symbols. Active form
fields have a green border/title and a native blinking caret. Tab/Shift-Tab move
between enabled fields, and keyboard taps retain the field's input destination.

The keyboard toolbar switches between **Term**, **Code** and **PT**. Code brings
brackets and operators forward; PT adds Portuguese accented letters and ç.
Shift also uppercases accented letters. The symbol page supplies digits when
the current layout uses its first row for accents or operators. Layout changes
retain the active field and do not submit it.

## Dictation and audio

Configure the owner's Groq API key in **Voice and audio** on the phone. Do not
send it in chat. Recording is local; transcription uploads that selected audio
to Groq and may consume API quota. Internet is needed for transcription, not
for the microphone itself.

Tap the keyboard microphone beside Enter, speak and tap again. The transcription
is inserted in the active terminal, including an SSH/Codex session, **without
Enter**. Review before submitting. The recording indicator is explicit; **×**
cancels, and leaving/blanking the screen cancels active quick capture. A changed
destination keeps the result for review instead of pasting blindly.

The panel also supports record/stop/transcribe/review and a speaker test. Headset,
Bluetooth and call audio are not established; see [status](status.md).
