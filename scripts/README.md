# Tool map

| Class | Tools | Effect |
| --- | --- | --- |
| Repository | `check-repository.py`, `run-tests.py`, `export-wiki.py` | Local checks/tests/export; no publishing |
| Source builds | `build-kernel.sh`, `build-lk2nd.sh`, `build-boot-image.sh` | Fetch pinned sources and emit private artifacts; no phone writes |
| Optional Rust app | `build-companion.py` | Checks/exports public sources, runs host Rust tests/lints, builds host or ARM64 musl and emits hashes/licenses; no device writes |
| Root staging | `assemble-userspace.py`, `rootfs-in-container.sh` | Offline staging; personal state must be empty |
| Persistent image assembly | `prepare-persistent-boot.sh`, `build-persistent-image.sh`, `prepare-lk2nd-payload.py` | Needs this owner's generated boot-root/stock DT; no partition writes |
| Image transforms | `extract-stock-dt.py`, `prepare-ram-kernel.py`, `prepare-updated-boot.py` | Read/emit files; reference geometry is not universal |
| USB maintenance | `device-ssh.ps1`, `device-upload.ps1`, `device-download.ps1`, `wait-device.ps1` | Actual device access with fresh project keys/pinned host identity |
| UI/audio maintenance | `deploy-mobile-ux.ps1`, `deploy-audio.ps1` | Changes installed userspace/services; intentional owner scope required |
| Diagnostics | `measure-mobile-ux.py`, `check-ext4.sh`, `reboot-to-recovery.py` | Read each tool; some mount test images or reboot the handset |

`device-console.ps1` and the debug-console service are legacy diagnostic escape
tools, not normal production access. They use a per-install private token and
must not be exposed outside USB. Fingerprint probes and memory diagnostics are
deferred experiments, not part of the supported desktop startup.

The original device-specific partition writers are deliberately not public tools.
See [installation](../docs/installation.md) and [AGENTS.md](../AGENTS.md).

`build-wake.py` builds the pinned local Portuguese wake experiment on a separate
Linux filesystem using CMake/make and pinned Zig. `--target host` or
`--target aarch64-linux-musl` emits the static helper, verified multilingual
model, hashes and upstream notices. It never deploys to a phone/server. Read
[Hermes setup](../docs/hermes-setup.md) for the still-open physical acceptance gates.
