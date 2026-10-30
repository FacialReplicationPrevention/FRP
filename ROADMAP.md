# FRP roadmap

**Last updated:** 2026-10-30  
**Operating principle:** Establish reliable measurements and a reproducible experiment before committing resources to intrinsic model protection or tamper resistance.

## Progress overview

| Phase | Status | Goal |
| --- | --- | --- |
| 0. Initial research | **Documented** | Frame problem and design scientific tests |
| 1. Portable project context | **Documented** | Give humans and coding agents shared instructions and decisions |
| 2. CPU experiment harness | **Milestones 001 and 002 merged** ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1)/PR [#2](https://github.com/FacialReplicationPrevention/FRP/pull/2); [#5](https://github.com/FacialReplicationPrevention/FRP/issues/5)/PR [#6](https://github.com/FacialReplicationPrevention/FRP/pull/6)); remaining items listed below | Reproducible config, variant planning, simulated execution/evaluation/reporting and tests |
| 2b. Model selection and architecture verification | **Milestone 003 merged** ([#7](https://github.com/FacialReplicationPrevention/FRP/issues/7)/PR [#8](https://github.com/FacialReplicationPrevention/FRP/pull/8)); weight hashes, licence-use review and GPU quote still pending | Pin and source-verify candidate open-weight models before any GPU work |
| 3. GPU instrumentation and baseline | **In progress — Milestone 004 ([#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)): PR 1 merged ([#10](https://github.com/FacialReplicationPrevention/FRP/pull/10)); PR 2 of 3 (CPU-only baseline executor contracts, mocked) under review. No GPU, download, inference or evaluation has run** | Verify Wan pathways and generate authorised baseline results |
| 4. Conditioning-pathway experiment | **Not started** | Test Wan 2.1 A/B/C/D and jointly measure identity + utility |
| 5. Intrinsic model mitigation | **Research hypothesis** | Evaluate training-time/model-weight changes |
| 6. Robustness and hardening | **Future research** | Evaluate resistance to adaptation and deployment bypass |
| 7. Publication and repeatability | **Ongoing** | Publish clear methods and privacy-safe evidence |

**Important:** "Documented" means research files exist, **not** that experiments were run or a prevention technology was validated. A completed harness milestone means software contracts were tested on synthetic fixtures, **not** that anything was measured.

**Model scope:** FRP is a cross-model research project. The existing A/B/C/D CLIP/VAE design (Research 004, Experiment 002) and the harness's run plan and result protocol are specific to **Wan 2.1 I2V**. Other model families need source verification at a pinned revision and their own reviewed protocol. [Research 005](research/005-wan-model-candidates.md) found that Wan 2.2 I2V-A14B has no CLIP-vision path at its pinned commit, so the A/B/C/D design does not transfer to it.

## Phase 0 — Research foundation (documented)

- [x] Define the FRP objective and distinguish identity measurement from consent and enforcement.
- [x] Record the provisional CID concept and limitations.
- [x] Review Wan2.1 I2V image-conditioning architecture at a conceptual/source-code level.
- [x] Draft baseline and conditioning-ablation protocols.
- [ ] Freeze an exact Wan upstream commit and checkpoint hashes before implementation or benchmarking. *(Source commit and checkpoint revision recorded in [Research 005](research/005-wan-model-candidates.md), pending review; weight hashes not verified.)*
- [x] Independently verify code assumptions at the pinned revision. *(Static source re-check in Research 005, pending review; no runtime instrumentation.)*

**Links:** [Research 001–005](README.md#research-library) · [Experiments 001–002](README.md#experimental-design).

## Phase 1 — Shared context for AI coding agents (documented)

- [x] Add [AGENTS.md](AGENTS.md).
- [x] Add [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
- [x] Add [ROADMAP.md](ROADMAP.md).
- [ ] Revisit these documents after each major scientific or architectural decision.
- [ ] For agents that do not automatically read `AGENTS.md`, add provider-specific pointers or explicitly include it in task instructions.

**Exit criterion:** A new agent can read repository documentation and accurately describe mission, actual evidence status, current milestone, privacy rules and next task without private chat history.

## Phase 2 — CPU-first experiment harness (MILESTONES 001–002 MERGED)

### Milestone 001 — manifest and dry-run planner (merged: [#1](https://github.com/FacialReplicationPrevention/FRP/issues/1), PR [#2](https://github.com/FacialReplicationPrevention/FRP/pull/2))

- [x] Add a minimal, pinned Python package (`pyproject.toml`, `src/frp/`, `tests/`).
- [x] Configure reproducible Codespaces development (`.devcontainer/`) without large GPU/model dependencies.
- [x] Add `pytest` and `ruff`; automate checks via GitHub Actions on synthetic/unit fixtures only.
- [x] Add strict, versioned experiment manifest parsing and validation (e.g. Pydantic/YAML), with hashes and explicit unset values.
- [x] Implement A/B/C/D variant mapping with invariant checks; in each variant only selected image-conditioning input changes. (Planning level only — not yet enforced on a real executor.)
- [x] Implement deterministic planning/seed management, input validation and structured run metadata.

### Milestone 002 — simulated execution, evaluation and reporting (merged: [#5](https://github.com/FacialReplicationPrevention/FRP/issues/5), PR [#6](https://github.com/FacialReplicationPrevention/FRP/pull/6))

- [x] Define adapter interfaces for run execution, face detection/identity evaluation and video-quality evaluation **without** making GPU execution a dependency of tests. (Contracts only; no real adapter exists.)
- [x] Define a versioned result schema with explicit missingness and plan linkage (rejects missing, orphaned, duplicate and mismatched records).
- [x] Build deterministic simulated execution and tests for execution failures, detection failures, missing scores, identity-level aggregation, incomplete pairs, report generation and private-data redaction.
- [x] Define an aggregate-only Markdown/CSV report format, marked as simulated. (Real-data public reports remain disabled pending privacy review.)
- [x] Document local CPU commands and example synthetic output in [docs/harness.md](docs/harness.md).

**Exit criterion:** In a clean CPU Codespace an agent can install the lightweight package, validate a manifest, run A/B/C/D dry-run planning, run the simulated pipeline, execute tests and produce a synthetic report, with no network downloads of model weights and no personal data. Met by the merged Milestone 002 for software contracts on synthetic fixtures only.

### Not yet done in Phase 2

- [ ] Identity-clustered uncertainty estimation (extension point only).
- [ ] Private storage, retention and reload of result records.
- [ ] Blinding codes for human quality raters.
- [ ] Privacy-reviewed disclosure rules (e.g. small-cell suppression) for real-data reports.

## Phase 2b — Model selection and architecture verification (MILESTONE 003 MERGED)

Milestone 003: [#7](https://github.com/FacialReplicationPrevention/FRP/issues/7), PR [#8](https://github.com/FacialReplicationPrevention/FRP/pull/8) (merged), with the documentation tracker [#4](https://github.com/FacialReplicationPrevention/FRP/issues/4). No GPU required. The boxes below record what was done in that PR; unchecked items remain open.

- [x] Pin the Wan 2.1 upstream commit (`9737cba…`) and the `Wan2.1-I2V-14B-480P` Hub revision (`6b73f84…`); statically re-verify the CLIP and VAE first-frame conditioning paths at that revision ([Research 005](research/005-wan-model-candidates.md)).
- [ ] Checkpoint weight hashes. **Not verified:** requires an approved download and local hashing.
- [x] Inventory candidate open-weight models (Wan 2.2 I2V-A14B and TI2V-5B, other official Wan checkpoints, selected derivatives) with pinned revisions, provenance, licence metadata, conditioning paths and cited resource statements; unverifiable items are marked as such.
- [x] Add a machine-readable provenance inventory ([`provenance/model-candidates.yaml`](provenance/model-candidates.yaml)) and an offline validator (`frp provenance`) that refuses to apply the Wan 2.1 protocol to other architectures; `frp plan` / `frp simulate` also fail closed on manifests naming a source or checkpoint other than the reviewed Wan 2.1 I2V-14B-480P.
- [x] Recommend an initial reproducible baseline (Wan2.1-I2V-14B-480P) and an optional later candidate (Wan2.2-I2V-A14B). A recommendation, not an authorisation to execute.
- [ ] Only if source verification supports it, draft a separate protocol for another model. Research 005 shows the Wan 2.1 A/B/C/D design does **not** transfer to Wan 2.2 I2V-A14B (no CLIP path); no Wan 2.2 protocol has been proposed.
- [ ] Human review of licence terms and permitted research use. *(Defined as gate 1 in [docs/gpu-readiness.md](docs/gpu-readiness.md); not performed.)*
- [ ] Plan the private, consented baseline measurement and obtain an approved GPU quote. *(Plan drafted in Milestone 004 PR 1; no quote obtained.)*

## Phase 3 — Controlled GPU smoke test and baseline (IN PROGRESS — PREPARATION ONLY)

### Milestone 004 ([#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)) — three gated PRs

**PR 1 — CPU-only readiness and private-review design (merged, [#10](https://github.com/FacialReplicationPrevention/FRP/pull/10)).** Preparation only: it authorises no GPU spend, download or processing.

- [x] Draft the [GPU readiness protocol](docs/gpu-readiness.md): seven separate human approvals, unverified hardware requirements, a blank cost-quote template, secure weight acquisition, a consented-adult private-data procedure and the execution allowlist (including `use_prompt_extend: false`). *Drafted; every gate is pending.*
- [x] Add a public readiness template ([`readiness/wan21-i2v-baseline.yaml`](readiness/wan21-i2v-baseline.yaml)) and `frp readiness`, an offline drift check that can express only pending gates and cannot grant anything.
- [x] Draft the single-condition baseline design ([Experiment 003](experiments/003-wan21-i2v-baseline-design.md)), separate from A/B/C/D, with smoke, calibration and baseline roles.
- [x] Draft the [private visual-review specification](docs/private-review-viewer.md) (design only; no viewer built).
- [x] Ada review. Approval of PR 1 did **not** approve any gate.

**PR 2 — Wan 2.1 baseline executor contracts and mocked integration (under review).** Does not itself authorise running a GPU.

- [x] Separate `baseline-0.1-draft` manifest, plan and result contracts (`frp.baseline`); A/B/C/D contracts unchanged; `frp baseline-plan` (planning only).
- [x] `BaselineExecutor` interface and a fail-closed `Wan21BaselineExecutor` over an injected backend: local hash, source, environment and private-authorisation gates, prompt-extension and network guards, conditioning/CFG control-flow checks, cleanup. Tested with fake backends only.
- [x] `build_readiness_report` now performs the provenance cross-check itself.
- [ ] **Live Wan 2.1 backend: disabled.** Not wired, not verified; no upstream call has been run.
- [ ] Private authorisation provider, approved environment digest, real checkpoint hashes: none exist.
- [ ] Ada review.

**PR 3 — Approved smoke test, face/identity and quality evaluation, private visual review (not started).** Requires separate human budget, licence and consent approvals.

### Phase 3 exit items
- [ ] Confirm model/checkpoint licence and permitted research use.
- [ ] Approve a GPU-provider budget, quota and shutdown policy; record an actual quote rather than estimate it as fact.
- [ ] Pin upstream source, model hashes, dependencies and reproducible container image.
- [ ] Lock upstream prompt extension off (`use_prompt_extend: false`) among the recorded generation controls, so a vision-language model cannot add an uncontrolled image → text route ([Research 005](research/005-wan-model-candidates.md); requested in the Milestone 003 review). *(Fixed control in the readiness template and locked in the baseline manifest, with a runtime guard in the mock-tested baseline executor; not enforced for the A/B/C/D manifest and unverified against a live run.)*
- [ ] Prepare a private, permission-verified adult dataset and ethical handling/retention procedure.
- [ ] Instrument CLIP feature and VAE condition metadata (shape/dtype/device), not raw biometric information in shared logs.
- [ ] Verify positive- and negative-text passes use the intended paired image conditions.
- [ ] Run a minimal authorised smoke test; record all attempted trials and runtime.
- [ ] Establish real baseline calibration using identity-disjoint genuine/impostor data and a second evaluation method where feasible.

**Exit criterion:** Repeatable, documented baseline with calibrated similarity, detection failures, independent video utility measurements and no privacy leaks.

## Phase 4 — Conditioning experiment (NOT STARTED)

- [ ] Pre-register A/B/C/D alterations, matched seeds, prompts and frame sampling.
- [ ] Run a limited exploratory pilot using authorised references (see [Experiment 002](experiments/002-conditioning-ablation-protocol.md)).
- [ ] Jointly evaluate identity similarity, detection coverage, temporal drift and video quality.
- [ ] Examine sensitivity to each pathway and interaction without claiming localisation or disentanglement from ablation alone.
- [ ] Decide whether a larger, pre-registered confirmatory study is scientifically justified.
- [ ] Publish privacy-safe aggregate outcomes, limitations and negative results.

**Decision gate:** If route alterations only reduce similarity by ruining video quality, do **not** call that protective success. Reconsider the mechanism.

## Phase 5 — Intrinsic/model-weight protection (HYPOTHESIS)

- [ ] Review relevant literature on model representation learning, selective suppression and generalisation to unseen faces.
- [ ] Formulate an explicit training objective and separate utility and identity metrics.
- [ ] Document how an independently verified authorisation signal would work (or state clearly that the experiment treats all identity retention uniformly).
- [ ] Prototype the smallest feasible training-time intervention, if warranted by earlier findings.
- [ ] Test held-out identity generalisation, false positives, authorised-use preservation and distribution shifts.
- [ ] Replicate and publish uncertainty before making efficacy claims.

**Decision gate:** Only advance if a measured effect is statistically and practically meaningful **without unacceptable utility losses**. No mathematical impossibility claim is assumed.

## Phase 6 — Robustness, deployment and hardening (FUTURE)

- [ ] Distinguish learned mitigation from inference-time policy controls.
- [ ] Evaluate how component substitution, fine-tuning and alternate pipelines affect a validated model-level mitigation.
- [ ] Assess signed model distribution, controlled runtimes and permission systems as distinct operational controls.
- [ ] State residual risk, enforceability assumptions, costs and limits against independently modified/open weights.

## Rules for changes to this roadmap

1. Update checkboxes **only after verifying that work occurred**.
2. Link evidence (commit, test run, experiment manifest or report) when marking execution milestones complete.
3. Label exploratory results separately from confirmatory results.
4. Do not include private participant information or raw face data in the public repository.
5. Prefer small changes and explicit review gates over an all-at-once ML infrastructure build.

## Next immediate action

Milestone 003 is merged ([PR #8](https://github.com/FacialReplicationPrevention/FRP/pull/8)). The current milestone is **Milestone 004** ([#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)); PR 1 is merged and PR 2 (CPU-only baseline executor contracts, mocked; live backend disabled) awaits review. After PR 2 is merged, the separately approved steps are, in order: the human gates in [docs/gpu-readiness.md](docs/gpu-readiness.md) (licence, consent, storage, provider terms, quote and budget cap), then PR 2 (real executor behind mock tests), then, only with explicit approvals, PR 3 (smoke test and private visual review). **No GPU rental, weight download, inference, portrait processing or evaluation of real people is authorised by Milestone 003 or by PR 1 of Milestone 004.** Wan 2.2 has no transferable A/B/C/D protocol and is not part of this milestone.
