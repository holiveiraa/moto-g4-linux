# Troubleshooting

Work from evidence: identify boot stage, read bounded logs, formulate a hypothesis
and change one relevant thing. Do not turn repeated resets/firmware loads into
the diagnostic method. Store raw results privately and redact reports.

| Symptom | Check first | Boundary |
| --- | --- | --- |
| Motorola logo / black screen | Boot stage, USB enumeration, root/rescue and logs | A logo is not a kernel boot result |
| Unlocked-device warning | Expected vendor warning and what happens afterward | Do not relock custom images to hide it |
| RAM boot works; installed boot fails | Full container length/padding, stock footer, DT/chosen fields | Re-check exact device/partition before writing |
| USB vanished | Cable/data port, power state, gadget enumeration and the current mode | ADB, vendor Fastboot, lk2nd Fastboot and USB SSH differ |
| Key-auth USB SSH stalls early | Kernel RNG configuration and hardware feeder | Do not weaken SSH algorithms to mask missing entropy |
| Linux root fails | Label, ext4 features and early boot/rescue log | Rescue never formats the root automatically |
| No saved Wi-Fi reconnect | Profile list/current ID and SAVE_CONFIG result | Association and persistence failures are separate |
| VPN looks offline | Wi-Fi, daemon state, coordination health and key expiry | A transient control-plane failure need not require recadastro |
| SSH requests another QR | Pending per-session Tailscale SSH verification | Separate from enrolling the Moto in the VPN |
| SSH password wrong / OTP needed | Endpoint, user and manual-entry path | Do not silently change server policy |
| No microphone/speaker | ADSP-before-WCNSS order, ALSA cards/routes, playback gain and softvol | No second ADSP load in the same failed boot |
| Form types but has no caret | Shared input registration and actual Tk focus | Keep logical destination/native focus together |
| GUI service says started but no UI | Real process, X windows and shell log; LF shebang | OpenRC success alone is insufficient |

## Windows detects USB but maintenance networking is missing

Inspect the current composite device and network adapter in Device Manager.
The reference gadget may be named **Remote NDIS based Internet Sharing Device**;
filtering only for the word "Motorola" can miss it. A present USB device does not
establish that its network driver started or received a DHCP address.

If the adapter reports **Code 10**, Windows could not start that device. Keep
the phone running, disconnect USB for five seconds and reconnect to a direct
data port. Re-check the adapter, its IPv4 address and the maintenance SSH port;
DHCP can take about a minute. Avoid repeatedly rebooting/flashing the phone for
a host driver failure. An administrator can instead restart the **exact**
affected device instance with `pnputil /restart-device "<instance ID>"`.
An access-denied response means that operation did not repair it.

If Windows instead shows **Unknown USB Device / Device Descriptor Request
Failed (Code 43)**, enumeration failed before maintenance networking was ready.
Try a known data-capable cable and a direct port while the phone remains running.
This symptom does not by itself identify a bad cable, kernel or host driver.
Separate it from DHCP/SSH failures; Microsoft's [USB enumeration case study](https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/case-study--troubleshooting-an-unknown-usb-device-by-using-etw-and-netmon)
explains the distinction.

See Microsoft's [Code 10 description](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/cm-prob-failed-start)
and [PnPUtil command reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil-command-syntax).
Do not reset all network adapters, replace drivers from random downloads or
disable host-key checking as a shortcut.

## Useful local evidence

Read, do not automatically publish: `/tmp/moto-shell.log`, `/tmp/inputd.log`,
`/tmp/Xorg.0.log`, `/tmp/terminal.log`, `/tmp/tailscaled.log`, `/tmp/network.log`,
`/var/log/moto-audio-start.log` and `/run/early-boot.log`. Availability depends on
the boot path. Logs may contain addresses, SSIDs or authorization links.

Use the new install's pinned maintenance key/host identity. Do not disable SSH
host verification to get around a connection failure. If normal Linux access is
gone, use the previously tested RAM/rescue/bootloader route for that same device.

`moto-ui-control` restarts UI/input without a reboot and preserves tmux processes,
but it should only be invoked as an intentional maintenance action. Never use
the owner's open SSH session as a target for automated close/input tests.
