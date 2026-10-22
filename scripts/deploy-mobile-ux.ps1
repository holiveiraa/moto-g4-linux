# SPDX-License-Identifier: MIT
# Deploy source/config changes to the native Linux session already on the Moto.
# Does not flash partitions or restart the phone. tmux sessions survive a GUI restart.
param([switch]$InstallPackages)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
if ($InstallPackages) {
    & "$PSScriptRoot/device-upload.ps1" -Source "$project/initramfs/install-gui" -RemotePath /usr/sbin/moto-install-gui -Mode 755
    & "$PSScriptRoot/device-ssh.ps1" -Command 'moto-install-gui'
    if ($LASTEXITCODE -ne 0) { throw 'GUI package installation failed' }
}
$files = @(
    @('native/moto-inputd.py', '/usr/sbin/moto-inputd', '755'),
    @('native/moto-shell.py', '/usr/sbin/moto-shell', '755'),
    @('native/moto-panel.py', '/usr/sbin/moto-panel.py', '644'),
    @('native/moto-widgets.py', '/usr/sbin/moto-widgets.py', '644'),
    @('native/moto-experience.py', '/usr/sbin/moto-experience.py', '644'),
    @('native/moto-appearance.py', '/usr/sbin/moto-appearance.py', '644'),
    @('native/moto-wifi.py', '/usr/sbin/moto-wifi.py', '644'),
    @('native/moto-wifi-panel.py', '/usr/sbin/moto-wifi-panel.py', '644'),
    @('native/moto-hosts.py', '/usr/sbin/moto-hosts.py', '644'),
    @('native/moto-ssh-panel.py', '/usr/sbin/moto-ssh-panel.py', '644'),
    @('native/moto-ssh-launch.py', '/usr/sbin/moto-ssh-launch', '755'),
    @('native/moto-ssh-askpass.py', '/usr/sbin/moto-ssh-askpass', '755'),
    @('native/moto-services.py', '/usr/sbin/moto-services.py', '644'),
    @('native/moto-terminals.py', '/usr/sbin/moto-terminals.py', '644'),
    @('native/moto-voice.py', '/usr/sbin/moto-voice.py', '644'),
    @('native/moto-capture.py', '/usr/sbin/moto-capture.py', '644'),
    @('native/moto-hermes.py', '/usr/sbin/moto-hermes.py', '644'),
    @('native/moto-hermes-panel.py', '/usr/sbin/moto-hermes-panel.py', '644'),
    @('native/moto-hermes-pet.py', '/usr/sbin/moto-hermes-pet.py', '644'),
    @('native/moto-quick-voice.py', '/usr/sbin/moto-quick-voice.py', '644'),
    @('native/moto-voice-panel.py', '/usr/sbin/moto-voice-panel.py', '644'),
    @('native/moto-audio.py', '/usr/sbin/moto-audio.py', '644'),
    @('native/moto-ui-control.py', '/usr/sbin/moto-ui-control', '755'),
    @('native/moto-fingerprint-control.py', '/usr/sbin/moto-fingerprint-control', '755'),
    @('initramfs/desktop-start', '/usr/sbin/moto-desktop-start', '755'),
    @('initramfs/terminal-session', '/usr/sbin/moto-terminal-session', '755'),
    @('initramfs/power', '/usr/sbin/moto-power', '755'),
    @('config/xorg-athene.conf', '/etc/X11/xorg-athene.conf', '644'),
    @('config/openbox-moto.xml', '/etc/X11/openbox-moto.xml', '644'),
    @('config/tmux-moto.conf', '/etc/X11/tmux-moto.conf', '644'),
    @('config/moto-help.txt', '/etc/moto-help.txt', '644')
)
foreach ($item in $files) {
    & "$PSScriptRoot/device-upload.ps1" -Source (Join-Path $project $item[0]) -RemotePath $item[1] -Mode $item[2]

}
& "$PSScriptRoot/device-ssh.ps1" -Command 'python3 -m py_compile /usr/sbin/moto-capture.py /usr/sbin/moto-hermes.py /usr/sbin/moto-hermes-pet.py /usr/sbin/moto-hermes-panel.py /usr/sbin/moto-experience.py /usr/sbin/moto-appearance.py /usr/sbin/moto-inputd /usr/sbin/moto-shell /usr/sbin/moto-panel.py /usr/sbin/moto-widgets.py /usr/sbin/moto-wifi.py /usr/sbin/moto-wifi-panel.py /usr/sbin/moto-hosts.py /usr/sbin/moto-ssh-panel.py /usr/sbin/moto-ssh-launch /usr/sbin/moto-ssh-askpass /usr/sbin/moto-quick-voice.py /usr/sbin/moto-services.py /usr/sbin/moto-terminals.py /usr/sbin/moto-voice.py /usr/sbin/moto-voice-panel.py /usr/sbin/moto-audio.py /usr/sbin/moto-ui-control && /usr/sbin/moto-ui-control'
if ($LASTEXITCODE -ne 0) { throw 'Desktop restart failed' }
