# FRP roadmap

**Last updated:** 2026-10-29  
**Operating principle:** Establish reliable measurements and a reproducible experiment before committing resources to intrinsic model protection or tamper resistance.

## Progress overview

| Phase | Status | Goal |
| --- | --- | --- |
| 0. Initial research | **Documented** | Frame problem and design scientific tests |
| 1. Portable project context | **Documented** | Give humans and coding agents shared instructions and decisions |
| 2. CPU experiment harness | **In progress — first increment under review ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1))** | Reproducible config, variant planning, unit tests and validation |
| 3. GPU instrumentation and baseline | **Not started** | Verify Wan pathways and generate authorised baseline results |
| 4. Conditioning-pathway experiment | **Not started** | Test A/B/C/D and jointly measure identity + utility |
| 5. Intrinsic model mitigation | **Research hypothesis** | Evaluate training-time/model-weight changes |
| 6. Robustness and hardening | **Future research** | Evaluate resistance to adaptation and deployment bypass |
| 7. Publication and repeatability | **Ongoing** | Publish clear methods and privacy-safe evidence |

**Important:** "Documented" means research files exist, **not** that experiments were run or a prevention technology was validated.

## Phase 0 — Research foundation (documented)

- [x] Define the FRP objective and distinguish identity measurement from consent and enforcement.
- [x] Record the provisional CID concept and limitations.
- [x] Review Wan2.1 I2V image-conditioning architecture at a conceptual/source-code level.
- [x] Draft baseline and conditioning-ablation protocols.
- [ ] Freeze an exact Wan upstream commit and checkpoint hashes before implementation or benchmarking.
- [ ] Independently verify code assumptions at the pinned revision.

**Links:** [Research 001–004](README.md#research-notes) · [Experiments 001–002](README.md#experiment-designs).

## Phase 1 — Shared context for AI coding agents (documented)

- [x] Add [AGENTS.md](AGENTS.md).
- [x] Add [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md).
- [x] Add [ROADMAP.md](ROADMAP.md).
- [ ] Revisit these documents after each major scientific or architectural decision.
- [ ] For agents that do not automatically read `AGENTS.md`, add provider-specific pointers or explicitly include it in task instructions.

**Exit criterion:** A new agent can read repository documentation and accurately describe mission, actual evidence status, current milestone, privacy rules and next task without private chat history.

## Phase 2 — CPU-first experiment harness (NEXT)

### Deliverables

- [x] Add a minimal, pinned Python package (`pyproject.toml`, `src/frp/`, `tests/`). ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1))
- [x] Configure reproducible Codespaces development (`.devcontainer/`) without large GPU/model dependencies. ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1))
- [x] Add `pytest` and `ruff`; automate checks via GitHub Actions on synthetic/unit fixtures only. ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1))
- [x] Add strict, versioned experiment manifest parsing and validation (e.g. Pydantic/YAML), with hashes and explicit unset values. ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1))
- [x] Implement A/B/C/D variant mapping with invariant checks; in each variant only selected image-conditioning input changes. ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1); planning level only — not yet enforced on a real executor)
- [x] Implement deterministic planning/seed management, input validation and structured run metadata. ([#1](https://github.com/FacialReplicationPrevention/FRP/issues/1))
- [ ] Define adapter interfaces for Wan inference, face detection, identity evaluation and video-quality evaluation **without** making GPU execution a dependency of tests.
- [ ] Build mock/dry-run execution and tests for detection failures, missing scores, identity-level aggregation, report generation and private-data redaction.
- [ ] Define an aggregate-only, privacy-reviewed Markdown/CSV report format.
- [ ] Document local CPU commands and expected test outputs.

**Exit criterion:** In a clean CPU Codespace an agent can install the lightweight package, validate a manifest, run A/B/C/D dry-run planning, execute tests and produce a synthetic report, with no network downloads of model weights and no personal data.

**First coding-agent task:** Implement only the package skeleton, manifest schema, and deterministic A/B/C/D plan generator with tests. Keep inferencing as an interface/stub. Ask for review before expanding to face recognition, GPU dependencies or real participant material.

## Phase 3 — Controlled GPU smoke test and baseline (NOT STARTED)

- [ ] Confirm model/checkpoint licence and permitted research use.
- [ ] Approve a GPU-provider budget, quota and shutdown policy; record an actual quote rather than estimate it as fact.
- [ ] Pin upstream source, model hashes, dependencies and reproducible container image.
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

Create Phase 2's minimal CPU-only Python scaffold and validate it with `pytest` / `ruff`. **No GPU rental is required for this next task.**
