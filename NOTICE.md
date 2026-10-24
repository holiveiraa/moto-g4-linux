# Notices

Original integration work: Copyright © 2026 Henrique and contributors.

The top-level MIT license applies to original userspace, scripts, tests,
documentation and artwork unless a file or [license map](LICENSES/README.md)
specifies otherwise. It does not relicense Linux, lk2nd, downloaded build tools,
distribution packages, firmware or other upstream projects.

- Linux-derived patches in `patches/` and `native/moto-audio-memory.c` use
  GPL-2.0-only. Preserve the original kernel notices and provide corresponding
  source if distributing covered binaries.
- `native/lk2nd-motorola-chosen.c` retains BSD-3-Clause. lk2nd itself has mixed
  upstream licenses; preserved overview/specific notices are in `LICENSES/`.
- AsteroidOS `msm-fb-refresher` v0.2 is Copyright © 2015 Florent Revest,
  **GPL-3.0-or-later**, compiled/downloaded separately. Its license/copyright must
  accompany redistribution; the MIT project license does not replace it.
- Alpine packages retain their package/file licenses. Record exact package
  versions and notices for any binary/rootfs release.
- OEM firmware, device trees extracted from stock images and calibration data
  are owner-provided inputs, not licensed or redistributed by this project.

Do not distribute device identities, maintenance private keys, Wi-Fi/SSH/Groq
credentials, recordings, owner logs or rootfs backups. See [credits](CREDITS.md)
for provenance and [release gates](docs/releasing.md) before creating binaries.

The optional local speech detector builds whisper.cpp separately (MIT), using
its Silero VAD API and pinned Silero weights, without Whisper ASR. Preserve the
Silero model and upstream notices.
The Rust WebRTC VAD wrapper/libfvad retain their own MIT/BSD-style notices;
the Rust build helper collects dependency notice files. Robot-eye behavior was
researched in RoboEyes (GPL-3.0); its implementation/art is not included here.
