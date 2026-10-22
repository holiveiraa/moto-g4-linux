# Contributing

Read [status](docs/status.md), [architecture](docs/architecture.md) and
[AGENTS.md](AGENTS.md). Human and agent-assisted contributions are welcome.

Useful work: independent reproduction on confirmed XT1640 P2A hardware, touch UX,
input languages, reproducible provisioning/recovery and measured power/rendering
improvements. Keep kernel migrations, suspend and new audio hardware separate
from small interface changes.

1. Describe the problem and resulting behavior; keep the change scoped.
2. Preserve licenses and credit borrowed code/ideas.
3. Run `python3 scripts/check-repository.py` and `python3 scripts/run-tests.py`
   on Linux/WSL; UI changes also need the relevant isolated UI/PTY review.
4. Report exact hardware, tests performed and limits. Use synthetic screenshots.
5. Never attach credentials, identity files, raw dumps, firmware or private logs.

Submitters review their AI-assisted work and remain responsible for provenance,
licensing and test claims. Passing CI does not certify a handset installation.
Binary releases need a separate license, firmware, identity and first-use review.
