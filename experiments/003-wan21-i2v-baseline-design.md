# Experiment 003 — Wan 2.1 I2V single-condition baseline (design only)

**Date:** 2026-10-30
**Status:** Design only — **not implemented, not executed, not reviewed.** No model has been run and nothing has been measured.
**Milestone:** [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9) (Roadmap Phase 3), PR 1 of 3.
**Builds on:** [Experiment 001](001-baseline-protocol.md) (generic baseline plan, unchanged), [Research 001](../research/001-identity-replication-measurement.md), [Research 005](../research/005-wan-model-candidates.md).
**Distinct from:** [Experiment 002](002-conditioning-ablation-protocol.md), the Wan 2.1 CLIP × VAE A/B/C/D diagnostic ablation. That design, its manifest schema 1.0 and result protocol `wan2.1-i2v-clip-vae-2x2` are unchanged.
**Gates and controls:** [GPU readiness protocol](../docs/gpu-readiness.md); [private review specification](../docs/private-review-viewer.md).

## Purpose and scope

Specify a **single-condition, unaltered image-to-video baseline** for `Wan-AI/Wan2.1-I2V-14B-480P` (revision `6b73f84e66371cdfe870c72acd6826e1d61cf279`, source `Wan-Video/Wan2.1` at `9737cba9c1c3c4d04b33fcad41c111989865d315`): the original reference image on **both** the CLIP and the VAE first-frame route, prompt extension off, no adapters.

This is the measurement baseline Experiment 001 calls for. It is **not** a protection experiment: no alteration, safeguard or mitigation is involved, and nothing here supports a claim about identity protection. It also does not authorise any GPU, data or download action; those need the separate human gates in the readiness protocol.

> **Why not run A/B/C/D and use A?** Variant A is identical in *conditioning* to the baseline, but the existing planner and result schema require every trial group to contain A, B, C and D. Running the 2 × 2 design to obtain one condition would either generate four identical runs (cost with no information) or require weakening the pairing invariants. The baseline therefore gets its own, smaller contract.

## 1. Reuse analysis

| Existing component | Verdict | Reason |
| --- | --- | --- |
| Manifest strictness machinery (`frp.manifest`: strict loader, `Text`, `GitSha`, `Sha256Hex`, `Resolution`, `Seed`, placeholder rejection, error redaction) | **Reuse** | Generic; no A/B/C/D dependency |
| `ExperimentManifest` schema 1.0 | **Do not extend** | Requires `variants` A–D and alteration fields; it is the ablation's schema |
| `frp.planner` (`PlannedRun`, `generate_run_plan`) | **Do not reuse** | Trial groups are fixed at four runs with a `Variant`; run ids end in `-[ABCD]` |
| `RunExecutor` | **Do not change** | Consumes `PlannedRun`; a *separate* `BaselineExecutor` contract is proposed for PR 2 so existing semantics are untouched |
| `FaceIdentityEvaluator`, `VideoQualityEvaluator` | **Reuse unchanged** | Take only an artefact reference (plus pseudonym/frame indices); not told a variant; model-agnostic |
| `FrameEvaluation`, `QualityEvaluation`, `ExecutionRecord`, `ArtefactRef`, adapter info types | **Reuse** | Express the required face statuses, missing-data rules and failure outcomes (see §4) |
| `RunResult`, `ResultSet` (`frp.results`) | **Do not extend** | Require variant conditioning, one A/B/C/D per group and protocol literal `wan2.1-i2v-clip-vae-2x2` |
| `frp.aggregation` clip → identity levels, later-frame rule, `UncertaintyEstimator` | **Reuse the approach** | Variant-level and paired-contrast code is ablation-specific; a baseline summary needs its own entry point |
| `frp.reporting` real-data guard | **Keep** | Real-data public reports stay disabled pending privacy review |
| `frp provenance` | **Unchanged** | `execution_readiness: not_ready` and `weight_sha256` never `verified` in schema 1.0 |
| Prompt extension | **Not yet a manifest control** | Harness docs say so; the readiness template records `use_prompt_extend: false` and PR 2 must enforce it |

A new protocol id is **not** registered in `frp.provenance.PROTOCOL_SCOPES` or `frp.results`: that needs a scientific review of its own. The readiness template names `wan2.1-i2v-baseline` only as a draft label.

## 2. Run roles

Three roles with different purposes. A run's role is fixed in the plan and determines which claims its results may support.

| Role | Question answered | Minimal size | Permitted statement | **Not** permitted |
| --- | --- | --- | --- | --- |
| `smoke` | Does the pinned, hash-verified pipeline run end to end with the frozen controls, record all required provenance and stay within budget? | One consented adult reference, one neutral prompt, one seed | "Technical smoke test passed/failed", runtime and cost; face detection may be run as a **technical sanity check** only, labelled *uncalibrated* | Any similarity-based, retention or utility conclusion; any statement about a population |
| `calibration` | How do the chosen face detector/recogniser and utility rubric behave, and what do identity-disjoint genuine and impostor controls look like? | Preregistered; not assumed here | Operating points chosen on calibration identities, with their error rates and uncertainty | Reusing the same identities for evaluation; a universal threshold |
| `baseline` | How much identity is retained by unaltered Wan 2.1 I2V on evaluation identities, with what variability and failures? | Preregistered after calibration feasibility is known | Calibrated, identity-clustered descriptive statistics with all failures | Any efficacy or protection claim; extrapolation to other models, prompts or recognisers |

If there are too few consented identities to calibrate or to estimate identity-level uncertainty, results are reported as a **technical smoke test or an exploratory, uncalibrated baseline** only, and scientific baseline acceptance stays open (as the Milestone 004 issue requires).

## 3. Proposed manifest contract (`baseline-0.1-draft`)

Not implemented. It reuses the manifest conventions (strict keys, `null` as the only "unset", placeholder rejection, no values echoed in errors).

| Field | Rule |
| --- | --- |
| `schema_version` | Distinct from `"1.0"`; a baseline manifest never validates as an ablation manifest and vice versa |
| `protocol` | `wan2.1-i2v-baseline`; `run_role` ∈ `smoke`, `calibration`, `baseline` |
| Model provenance | `upstream_repository`/`checkpoint` fixed to the Wan 2.1 values (Wan 2.1 guard retained); `upstream_commit_sha`, `checkpoint_hashes` (local SHA-256 per file) and environment digest required before any execution |
| Conditioning | Fixed: `clip_conditioning: original`, `vae_first_frame_conditioning: original`; no `alteration_*` fields exist |
| `use_prompt_extend` | Fixed `false`; any other value is a validation error |
| Identities | Pseudonyms as in schema 1.0, each with `identity_split` ∈ `calibration`, `evaluation`, and no overlap; the smoke role takes one identity and no split |
| Prompts, seeds | As schema 1.0 (neutral-motion prompts; non-negative seeds). Plan = identities × prompts × seeds, each a **single run** with no variants |
| Controls | `sampler`, `sampling_steps`, `guidance_scale`, `frame_count` (4n+1), `resolution`, `precision`, `image_preprocessing_version`, `frame_indices`: unset until decided; hashed into a `generation_controls_sha256` |
| Evaluation provenance | `face_evaluator_revision`, `face_detection_settings`, `calibration_dataset_version`, `quality_rubric_version`, `analysis_plan_version` |
| Readiness | Execution is not inferred from fields being set. A human go/no-go input, defined in PR 2, is required in addition |

Run ids: `<EXPERIMENT_ID>-R<NNNN>` (no variant suffix); the **attempt** is a separate index (§4) so retries never overwrite a run.

## 4. Proposed result contract (`baseline-0.1-draft`)

Not implemented. It would be a **new** result set type rather than a change to `ResultSet`.

**Every attempt is recorded.** An attempt record holds: run id, `attempt_index`, `run_role`, ordinal identity/prompt indices (never pseudonyms or prompt text), seed, `generation_controls_sha256`, executor/evaluator component info with verified weight-set digest and environment digest, an `ExecutionRecord`, per-frame face evaluations and a quality evaluation. Failed, aborted and unexecuted attempts are never dropped, and a retry is a new attempt, not a replacement. The primary analysis uses a **predeclared** attempt-selection rule (e.g. the first attempt per planned run), with all other attempts reported.

**Generation failures** reuse the existing `ExecutionRecord` statuses and failure categories (`executor_error`, `timeout`, `resource_exhausted`, `invalid_input`, `other`). Candidate additions for review: `model_load_error`, `budget_stop`, `operator_abort`. Free-text messages are never stored because they may leak paths or private data.

**Face status per sampled frame** — `valid`, `absent`, `multiple`, `low_quality`, `error`, plus `not_evaluated` for runs that produced nothing. `similarity` exists **only** for `valid` (never `0` or an imputed value), as in `FrameEvaluation`. When several faces are present, no face is chosen by highest score.

**Sampled frames.** A fixed rule frozen in the manifest. Candidate for 81 frames: `0, 20, 40, 60, 80` (Experiment 002), adapted proportionally if another 4n+1 frame count is chosen. **Frame 0 is reported separately** because the conditioned first frame can be unusually close to the source; later frames are primary.

## 5. Measurement and analysis plan (to be preregistered)

1. **Detection coverage first.** Report, per run and per identity, the counts of each face status at each sampled index, with denominators. Similarity is conditional on `valid`, so every similarity summary is reported with its coverage.
2. **Per-clip similarity.** Later-frame median over `valid` frames (index ≠ 0), available only if a predeclared minimum number of valid later frames exists; frame-0 similarity separately. The minimum is not set here.
3. **Temporal drift.** The sampled-frame similarity trajectory per clip, and frame 0 minus later-frame median, as descriptive quantities. No linear trend is assumed.
4. **Independent video quality.** Assessed separately from identity, with (a) automated quality metrics that do not use the face recogniser, with versions recorded, and (b) a blinded human rubric (see the [review specification](../docs/private-review-viewer.md)). Unusable output is a status, never a score. Low quality can itself explain lower similarity, so similarity is never interpreted without coverage and quality.
5. **Identity-level aggregation.** Frames within a clip and clips within an identity are not independent. Aggregate clip → identity → role-level; intervals are clustered by identity.
6. **Calibration.** Choose operating points on **identity-disjoint** genuine/impostor controls and apply them unchanged to evaluation identities. No numerical threshold is assumed to be universal, and none is fixed here. Controls to specify:
   - genuine and impostor pairs from *real-photograph* calibration data (the recogniser's behaviour on its intended input);
   - **matched generated-video impostor controls**: reference of identity *i* against frames of clips generated for identity *j ≠ i*, matched on prompt, seed, frame index and controls, because a threshold chosen on photographs need not transfer to compressed, blurred or re-posed generated frames;
   - a **second evaluation method** where feasible, to expose recogniser-specific effects.
7. **Uncertainty and variability.** Identity-clustered intervals using a method fixed in the analysis plan; seed-to-seed and (if tested) run-to-run variability; a same-seed repeat to examine determinism, since cross-hardware determinism is unknown.
8. **Reporting.** All attempts, failures, missingness, subgroup and demographic limits, and negative results. Real-data public reports remain disabled until a privacy review defines disclosure rules (small cells).

A high similarity to a reference is neither proof of identity nor of consent; a low one is not evidence of protection.

## 6. Smoke-test acceptance (technical only)

The smoke test passes only if, for the single consented reference: the executed source commit, checkpoint revision and locally hashed weights equal the pins; `use_prompt_extend` was off and no network service was used; both routes received the unaltered reference; the clip has the frozen frame count and resolution; the artefact exists only in approved private storage; seed, controls, runtime and measured cost are recorded; and every attempt, including failures, is accounted for. It supports no claim about identity retention.

## 7. Decisions for review

1. Should `frame_indices` follow the 81-frame candidate set or be set after seeing runtime constraints (the set must be frozen before viewing outputs)?
2. Minimum valid later frames per clip and minimum identities for calibration and for an identity-clustered interval.
3. Which second face evaluator and which automated quality metrics, and under what licences.
4. Attempt-selection rule when retries occur.
5. Whether a baseline-specific protocol id should be added to the provenance/results registries, which needs its own scientific review.
6. Whether `use_prompt_extend` should become a locked field of the existing manifest schema 1.0 or only of the new baseline schema.

## Limitations

This is a plan. It fixes few numerical values deliberately, and none has been validated on data. Any property attributed to Wan 2.1 is a source observation at the pinned commit (Research 005), not a measured behaviour.
