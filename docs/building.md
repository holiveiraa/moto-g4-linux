# Building

Build on Linux, or Ubuntu/WSL with Docker available. Use a Linux filesystem for
the working directory, not a synchronized Windows folder. Python 3.10+, Git,
curl, make and the documented toolchains are required. A build does not access
the phone unless you separately invoke a maintenance/install operation.

## Hermes companion builds

The optional fullscreen app has an independent Rust build and a pinned local
activation helper/model. Use [the companion build guide](hermes-setup.md#build-from-public-source)
and [speech detector build](hermes-setup.md#build-the-local-speech-detector).
The base userspace assembler copies its Python UI modules; Rust/helper/model
artifacts must be built and installed separately as a matching set. You do not
need to rebuild the kernel or boot images to add this app to a working system.

For an already installed runtime, start with
[first connection](hermes-setup.md#first-connection-checklist). Server setup is
performed by [Hermes inside its own app](hermes-server-agent.md), not by the
phone build process.

## Sources and clean checks

Revisions/checksums are recorded in [sources.lock.json](../sources.lock.json).
The kernel recipe comes from the pinned archived postmarketOS port; it is not a
floating latest-kernel download. New lk2nd builds fetch their pinned Git commit,
not the developer's `.local-tools/` archive.

```sh
python3 scripts/check-repository.py
python3 scripts/run-tests.py
export MOTO_WORK_ROOT="$HOME/src/moto-g4-linux"
bash scripts/build-kernel.sh
```

The container in `docker/kernel.Dockerfile` intentionally supplies GCC 6 for the
archived kernel. It uses historical Debian packages inside a build container.
`MOTO_BUILD_JOBS` controls parallelism. Default builds apply the native playback
gain fix; opt-in diagnostic code is not part of the production kernel.

## Owner-specific inputs

Create new project maintenance keys in `.private/`; do not use your cloud key.
The debug-root builder creates a separate Dropbear host identity there.

```sh
mkdir -p .private
chmod 700 .private
ssh-keygen -t ed25519 -f .private/device-debug-ed25519
```

If a passphrase is used, the maintenance SSH client must have an unlocked agent
or receive that passphrase interactively. Do not put it in a script or chat.
Stock boot/DT and firmware come from this owner's device and remain private.
The modem firmware partition is preserved and mounted read-only at runtime;
some firmware/INI/calibration files still need extraction into `/lib/firmware`
as established for that device. A missing firmware file is not solved by
downloading another person's identity/calibration partition.

## Build the diagnostic RAM image

```sh
bash scripts/build-boot-image.sh
```

This prepares the Alpine debug root and boot tools, compiles framebuffer/rescue
helpers, and emits `out/athene-usb-debug.img` plus hashes. It can exceed 16 MiB;
**RAM boot only**, never a direct boot-partition flash. It is diagnostic, not
the complete persistent desktop installer. `out/` contains per-install keys,
firmware and artifacts and must stay private.

## Assemble a clean persistent userspace

Use a fresh ARM64 Alpine root with signed packages installed for that architecture.
`assemble-userspace.py` contains the package list in `PACKAGES`; cross-install
with APK only in an isolated staging root and do not run foreign post-install
scripts on x86. Use an ARM64 environment/emulation for necessary post-install
steps. Verify installed binaries, libraries, fonts and OpenRC before boot.

Supply compiled ARM64 `msm-fb-refresher` and `reboot-bootloader` binaries from the
debug build's `firstlight-rootfs/usr/sbin`. Download the pinned official ARM64
Tailscale archive from the lock file, verify its checksum and unpack it locally.
Never copy `/var/lib/tailscale` from the running prototype.

```sh
python3 scripts/assemble-userspace.py \
  --root "$MOTO_WORK_ROOT/clean-rootfs" \
  --public-key .private/device-debug-ed25519.pub \
  --host-key .private/dropbear_ed25519_host_key \
  --tools-dir "$MOTO_WORK_ROOT/boot-tools/firstlight-rootfs/usr/sbin" \
  --tailscale-dir "$MOTO_WORK_ROOT/tailscale-arm64"
```

This is an offline overlay assembler, not an APK installer or block-device writer.
It refuses obvious existing personal state and symlinked write destinations
before copying files, and stages current modules, service
ordering, maintenance keys and empty network/user configuration. It does not
certify firmware, libraries, calibration or a new hardware revision. The current
fstab/early-root checks target the reference userdata layout; verify it before use.
Its clean-state behavior is unit-tested; a fresh assembled root still needs a
new-device RAM/boot acceptance run.

## Build lk2nd and the small persistent image

The lk2nd host build needs `arm-none-eabi-gcc`, make, device-tree tools and its
upstream prerequisites:

```sh
bash scripts/build-lk2nd.sh normal
```

For a recovery build, set `MOTO_RECOVERY_BYTES` from the verified device profile;
the script refuses to guess its padded partition size. Never use the 512 KiB
loader reservation as the recovery partition size.

The small boot-root archive is generated by `prepare-persistent-boot.sh` in this
owner's working ARM64 RAM session. Upload current `persistent-init`/`rescue` to
the paths that script expects and download its generated archive privately.
`build-persistent-image.sh` consumes that small boot-root plus the owner's stock
boot/DT; `prepare-lk2nd-payload.py` handles the reference Athene_16MP/QCDT layout.
Read those scripts and [installation](installation.md) before assembling images.

`prepare-ram-kernel.py` and `prepare-updated-boot.py` are local image transformers.
The latter requires an exact owner-supplied source hash and preserves existing
loader/ramdisk/DT. It is an update tool, not a clean first-install shortcut.

## Reproducibility boundary

Upstream kernel/lk2nd revisions and downloaded base artifacts are pinned. APK
repositories/container package archives can still evolve; package manifests,
toolchains and artifact hashes must be recorded per build. The entire historical
prototype rootfs is not claimed bit-for-bit reproducible. Complete independent
reproduction is a release gate, not a result inferred from a passing source test.
