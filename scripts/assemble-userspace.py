#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage clean phone userspace in an unpacked Alpine tree; never touches a device."""
import argparse
from pathlib import Path
import re
import shutil
import time

PROJECT = Path(__file__).resolve().parents[1]
PRIVATE_STATE = ('var/lib/tailscale/tailscaled.state', 'root/.config/moto-linux',
                 'root/.ssh/id_ed25519', 'root/.ssh/id_rsa', 'var/log/moto-boots')
PACKAGES = ('openrc busybox-extras dropbear dnsmasq wpa_supplicant iw e2fsprogs '
            'xorg-server xf86-video-fbdev xf86-input-evdev xterm openbox font-dejavu '
            'xrandr xinput xdpyinfo xwininfo xset xdotool xprop python3 python3-tkinter '
            'tmux openssh-client-default alsa-utils qrencode curl ca-certificates').split()


def assemble(root, public_key, host_key, tools, tailscale, epoch=None):
    root = Path(root).resolve()
    if root == Path(root.anchor) or root == PROJECT or PROJECT.is_relative_to(root):
        raise ValueError('Use a dedicated staging root, never / or the repository.')
    if not (root/'etc/alpine-release').is_file():
        raise ValueError('Unpack a fresh ARM64 Alpine minirootfs first.')
    for relative in PRIVATE_STATE:
        if (root/relative).exists():
            raise ValueError('Existing personal state detected; use a fresh staging tree.')
    wpa = root/'etc/wpa_supplicant.conf'
    if wpa.exists() and re.search(r'\bnetwork\s*=', wpa.read_text(encoding='utf-8')):
        raise ValueError('Existing Wi-Fi profiles detected; do not copy a personal rootfs.')
    public_key, host_key, tools, tailscale = map(Path,(public_key,host_key,tools,tailscale))
    key = public_key.read_text(encoding='utf-8').strip()
    if not key.startswith('ssh-ed25519 ') or len(key.split()) < 2:
        raise ValueError('Generate a new project Ed25519 maintenance public key.')
    required = [host_key, tools/'msm-fb-refresher',tools/'reboot-bootloader',
                tailscale/'tailscale',tailscale/'tailscaled']
    for path in required:
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('Missing per-install build input: '+str(path))
    # Queue every write so containment is checked before changing the tree.
    # A fresh minirootfs contains symlinks; none may redirect our destinations.
    writes = []
    def put(source, relative, mode):
        source = Path(source)
        if not source.is_file():
            raise ValueError('Missing source input: '+str(source))
        writes.append((relative, source, mode))
    def text(relative,value,mode=0o644):
        writes.append((relative, value.encode('utf-8'), mode))
    for name in ('LICENSE','NOTICE.md','sources.lock.json'):
        put(PROJECT/name,'usr/share/licenses/moto-g4-linux/'+name,0o644)
    for source in (PROJECT/'native').glob('moto-*.py'):
        if source.name == 'moto-audio-memory.py': continue
        put(source,'usr/sbin/'+source.name,0o644)
    for name in ('inputd','shell','ui-control','audio-start','boot-diagnostics','ssh-launch','ssh-askpass'):
        put(PROJECT/f'native/moto-{name}.py',f'usr/sbin/moto-{name}',0o755)
    for name in ('wifi-init','wifi-connect','network-start','wait-network','desktop-start',
                 'terminal-session','power','hardware-start'):
        put(PROJECT/'initramfs'/name,'usr/sbin/moto-'+name,0o755)
    for source in (PROJECT/'config').glob('moto-*.openrc'):
        put(source,'etc/init.d/'+source.stem,0o755)
    config = {'moto-inittab':'etc/inittab','xorg-athene.conf':'etc/X11/xorg-athene.conf',
        'openbox-moto.xml':'etc/X11/openbox-moto.xml','tmux-moto.conf':'etc/X11/tmux-moto.conf',
        'moto-audio.json':'etc/moto-audio.json','moto-asound.conf':'etc/asound.conf','moto-help.txt':'etc/moto-help.txt'}
    for source,target in config.items(): put(PROJECT/'config'/source,target,0o644)
    for name in ('msm-fb-refresher','reboot-bootloader'): put(tools/name,'usr/sbin/'+name,0o755)
    put(tailscale/'tailscale','usr/bin/tailscale',0o755)
    put(tailscale/'tailscaled','usr/sbin/tailscaled',0o755)
    put(host_key,'etc/dropbear/dropbear_ed25519_host_key',0o600)
    text('root/.ssh/authorized_keys',key+'\n',0o600)
    text('etc/wpa_supplicant.conf','ctrl_interface=/run/wpa_supplicant\nupdate_config=1\n',0o600)
    text('etc/moto-persistent','motorola-athene-native-v1\n')
    text('etc/moto-build-epoch',str(int(epoch or time.time()))+'\n')
    text('etc/fstab','/dev/mmcblk0p48 / ext4 defaults,noatime 0 1\n')
    text('etc/hostname','moto-g4-linux\n')
    text('etc/moto-required-packages','\n'.join(PACKAGES)+'\n')
    levels={'sysinit':('devfs','dmesg','mdev'),'boot':('bootmisc','sysctl','urandom'),
            'shutdown':('killprocs','savecache','mount-ro'),
            'default':('moto-hardware','moto-audio','moto-network','moto-tailscale','moto-desktop')}
    links = [('etc/runlevels/'+level+'/'+service, '/etc/init.d/'+service)
             for level, services in levels.items() for service in services]
    directories = ('dev','proc','sys','run','tmp','var/lib','firmware','mnt','root/.ssh')
    for relative in [item[0] for item in writes+links] + list(directories):
        target = root/relative
        for part in (target, *target.parents):
            if part == root:
                break
            if part.is_symlink():
                raise ValueError('Symlink at a staging destination: '+str(part.relative_to(root)))
        if not target.resolve().is_relative_to(root):
            raise ValueError('Staging destination escapes its root.')
    for relative, content, mode in writes:
        target = root/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            shutil.copyfile(content,target)
        target.chmod(mode)
    for relative, destination in links:
        link = root/relative
        link.parent.mkdir(parents=True,exist_ok=True)
        if not link.exists():
            link.symlink_to(destination)
    for name in directories:
        (root/name).mkdir(parents=True,exist_ok=True)
    (root/'root/.ssh').chmod(0o700)
    (root/'tmp').chmod(0o1777)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','public-key','host-key','tools-dir','tailscale-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--epoch',type=int)
    args=parser.parse_args()
    assemble(args.root,args.public_key,args.host_key,args.tools_dir,args.tailscale_dir,args.epoch)
    print('Clean userspace staged. Install/verify the listed ARM64 packages, licenses and hardware inputs before any RAM/boot test.')


if __name__=='__main__': main()
