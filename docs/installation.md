# Installation and recovery

Start with the [agent workflow](agent-installation.md). Installation is currently
an engineering task for the confirmed hardware, not a one-command installer.
No prebuilt public image is provided, and another owner's images are not inputs.

## Prerequisites

- A compatible Moto G4 Plus, charged and with a reliable data USB cable.
- An owner who understands the data erase and can authorize the official unlock.
- Windows USB tools plus Linux/WSL/Docker build tools, or an equivalent supported
  host layout. Keep Linux builds outside synced Windows folders.
- Private host storage for verified stock backups and newly generated keys.
- Device-specific stock boot/DT and required OEM firmware obtained from this
  unit; these are deliberately not redistributed by the repository.
- Another browser-capable device for Motorola/Tailscale authorization when needed.

## Tested boot design

The prototype uses a full legacy Android-format boot container. Adapted lk2nd
occupies the first **512 KiB**, with the Linux boot payload after that boundary.
The tested boot partition is **16 MiB**. These are observed reference values,
not permission to assume another handset has the same layout.

Stock Motorola QCDT v0x103 includes hardware-specific DTBs. The tested P2A
requires its **Athene_16MP** description; the archived ARM64 tree alone describes
earlier revisions. `extract-stock-dt.py` and `prepare-lk2nd-payload.py` preserve
that description and adapt the table format. The latter is explicitly scoped
to the reference DT/geometry and must not be treated as a generic model detector.

The lk2nd adaptation forwards firmware-selected `/chosen` properties so panel,
touch and other hardware selection remain correct. Full boot padding matters:
a leftover stock signature/footer changed the observed boot path. The small
persistent initramfs switches to the owner's labeled Linux userdata root, or
starts USB rescue if the root check fails. Recovery can provide an lk2nd menu.

## Storage rules

Discover PARTNAMEs and sizes on the actual device. The reference persistent-init
additionally checks `/dev/mmcblk0p48` and the `moto-linux` label. It must be
reviewed against the new device profile. Never translate these checks into an
unchecked device-node write.

The tested userdata root uses ext4 with features compatible with kernel 3.10:
`has_journal,ext_attr,resize_inode,dir_index,filetype,extent,flex_bg,sparse_super,`
`large_file,huge_file,dir_nlink,extra_isize,uninit_bg`, 4096-byte blocks, starting
from `-O none`. New mkfs defaults such as metadata checksums/64-bit support must
not be assumed compatible. Test on an image/loop device before touching eMMC.

The original production root was evolved on the tested phone; a clean independent
rootfs installation remains a release acceptance item. An agent must assemble
OpenRC/services/packages from source and owner-specific inputs, not clone a
configured filesystem. See [building](building.md) for component boundaries.

## Write gate and recovery

Every install plan needs an identity check, backup verification, exact image
size/hash, destination guard, readback verification and recovery instructions.
Keep bootloader, GPT, modem, persist, calibration and security partitions intact.
Do not erase Android system until native boot/recovery is proven and the owner
has specifically authorized retiring that installation.

The repository contains **no portable partition writer**. The one-unit writers
used during bring-up were archived privately; their hardcoded identifiers are
not a safe public API. Source assembly scripts do not invoke ADB/Fastboot or
write the handset. An agent prepares the checked per-device write plan.

If a test fails, retain evidence, return to a known RAM/rescue image or the
owner's stock backup and investigate. Do not relock a bootloader with custom
images installed. See [troubleshooting](troubleshooting.md).
