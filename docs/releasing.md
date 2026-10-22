# Source publication and future binary releases

Preparing files locally is not publishing. The owner decides when to create a
GitHub repository, commit, push, enable its Wiki or make a release. This guide
does not automate those network changes.

## Source repository

Run `python3 scripts/check-repository.py` and the offline tests. Review the actual
file set, not just `.gitignore`. Keep `.private/`, downloaded sources/tools,
generated firmware/images, logs and old device journals out. Synthetic UI
screenshots are acceptable; real credentials, account hosts and raw logs are not.

Confirm the license map, notices and upstream pins. Source checks reduce common
mistakes but are not proof that every possible secret or license issue is absent.
Review the final diff and selected files before committing. Use a description
that accurately calls this an experimental source port for the tested variant.

For an extra inspection of a source-only copy, run
`python3 scripts/export-source.py --output out/public-source`. It copies only
the checked Git candidate list into a new local directory, without `.git`,
private state or generated inputs. It refuses to merge into an existing folder
and never uploads anything. A fresh-copy test can then establish that offline
regressions do not depend on the developer's private workspace.

GitHub-ready materials include an issue form, pull-request template, CI and
[wiki export](wiki.md). Enable private vulnerability reporting in repository
settings if maintainers can receive and handle such reports.

## Before a public flashable/rootfs release

The completed local source checks and isolated phone reviews are recorded in
[status](status.md#public-source-validation--21-october-2026). They establish the
source-publication checkpoint, not the binary-release gates below.

| Gate | Acceptance |
| --- | --- |
| Clean provenance | Every source, patch, package and binary has a recorded origin/license |
| Firmware | Distribution rights resolved or owner-side extraction documented/tested |
| Clean rootfs | Fresh build has no personal identities, networks, SSH/Groq secrets or recordings |
| Per-install identity | Maintenance/device keys are unique; no shared developer credentials |
| Installer | Exact variant/geometry, backups, image sizes/hashes and recovery guards |
| New-device test | Independent installation on supported hardware |
| First use | Wi-Fi → first Tailscale QR → own SSH destination without maintenance PC |
| Unplugged test | Shutdown/Power-on, saved Wi-Fi/identity, audio/volume and optional dictation |
| Reproduction | Toolchain/package manifest, inputs/hashes and sufficient build instructions |
| Disclosure | Old kernel, root UI, no screen lock/suspend and unsupported hardware stated |

The prototype passed many hardware features, but a source-ready repository is
not equivalent to a certified binary installer. Keep those milestones separate.
Never create a release by uploading the owner's `.private/` backup.
