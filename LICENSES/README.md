# License scope

| Material | License / rule |
| --- | --- |
| Original Python/Rust userspace, scripts, tests, config, docs and artwork | [MIT](../LICENSE) unless an explicit per-file notice says otherwise |
| Linux-derived `patches/*.patch` and `native/moto-audio-memory.c` | [GPL-2.0-only](GPL-2.0-only.txt) |
| `native/lk2nd-motorola-chosen.c` | [BSD-3-Clause](BSD-3-Clause.txt) |
| lk2nd downloaded source/binaries | [upstream overview](lk2nd-upstream.txt), [lk2nd-specific notice](lk2nd-specific.txt), plus individual file licenses |
| AsteroidOS msm-fb-refresher v0.2 | [GPL-3.0-or-later](GPL-3.0-or-later.txt); upstream copyright/license remain with the downloaded component |
| Alpine packages / other downloaded tools | Their own source/package licenses; not relicensed by this repository |
| Rust companion dependencies | Their individual Cargo license declarations and upstream notices; `Cargo.lock` pins source packages, and the build helper collects license metadata/notices for review |
| Local speech detector | Downloaded whisper.cpp source retains MIT notices; `scripts/build-hearing.py` verifies pins and collects notices. No Whisper ASR weights are required. |
| WebRTC VAD | Rust wrapper and bundled libfvad retain their individual MIT/BSD-style notices, collected with Rust dependency sources |
| Silero VAD model / verifier | [Silero Team MIT license](silero-vad-MIT.txt); pinned upstream ggml conversion and whisper.cpp retain their own notices. Downloaded during build, not bundled in Git. |
| Proprietary firmware / calibration / OEM images | Not included and no redistribution grant is asserted |

The original README/artwork/docs are covered by MIT for straightforward reuse.
The [OpenAI model license](whisper-model-MIT.txt) is retained for historical
Whisper-weight experiments. Current builds use only Silero detector weights
and collect their license plus whisper.cpp/ggml source notices.
File-specific SPDX headers take precedence over the default scope. This source
repository does not include a complete downstream kernel/tool checkout; download
the pinned sources and preserve their notices. A binary release needs a fuller
component/package/source-offer review than the source repository alone.

Canonical license texts were obtained from the
[SPDX license-list data](https://github.com/spdx/license-list-data/tree/main/text).
lk2nd notices were preserved from its exact pinned source revision, recorded in
[sources.lock.json](../sources.lock.json).
