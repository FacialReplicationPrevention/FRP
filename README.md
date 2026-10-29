# FRP

## Research programme

FRP studies how to measure and potentially reduce unauthorised facial identity replication in generative image and video models, including locally operated open-weight systems.

**Status:** Early research. No prevention mechanism has been validated by FRP. The proposed CID architecture is a hypothesis rather than a demonstrated guarantee.

### Research notes

- [001 — Measuring facial identity replication](research/001-identity-replication-measurement.md)
- [002 — CID feasibility and threat model](research/002-cid-feasibility-threat-model.md)

- [003 — Wan 2.1 image-to-video conditioning architecture](research/003-wan21-i2v-architecture.md)
- [004 — Conditioning-pathway ablation design](research/004-conditioning-ablation-design.md)

### Experiment designs

- [001 — Baseline identity preservation](experiments/001-baseline-protocol.md)
- [002 — Conditioning-pathway ablation protocol](experiments/002-conditioning-ablation-protocol.md)

### Research principles

Use authorised adult or appropriately licensed datasets; keep portraits and biometric embeddings private; record methods and negative results; distinguish evidence from hypotheses; and evaluate generation quality, uncertainty, and bypass risks alongside identity similarity.

## Project guidance for human and AI contributors

- [Agent instructions](AGENTS.md) — expectations for coding agents, experimental discipline and privacy.
- [Project context](PROJECT_CONTEXT.md) — FRP goals, CID hypotheses and current scientific position.
- [Roadmap](ROADMAP.md) — research and engineering phases, status and milestone exit criteria.

**Next engineering milestone:** Create a CPU-only Python experiment harness in GitHub Codespaces. The research plans are not experimental results; a working prevention mechanism has not yet been demonstrated.

## Local development (CPU-only harness — planning/dry-run only)

The `frp` package validates experiment manifests and prints deterministic A/B/C/D run plans. It runs **no** inference, downloads **no** model weights and processes **no** images or biometric data; **no scientific outcome has been measured**. Details: [docs/harness.md](docs/harness.md).

Requires Python 3.11+. In a Codespace, [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) runs the install step automatically. Elsewhere:

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -c constraints.txt -e ".[dev]"   # pinned, CPU-only dependencies

ruff check . && ruff format --check .                     # lint + formatting
pytest                                                    # synthetic, non-biometric unit tests

frp plan examples/manifests/synthetic-dry-run.yaml --dry-run                 # text summary
frp plan examples/manifests/synthetic-dry-run.yaml --dry-run --format json   # machine-readable
```

The example manifest uses synthetic pseudonyms (`SYN-001`…) and leaves every execution field explicitly unset (`null`), so the dry run reports **NOT READY**. Add `--require-ready` to fail (exit 3) until all execution fields are filled with real, selected values. Real manifests referencing participants belong in private storage, not in this repository.
