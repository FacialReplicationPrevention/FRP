# Baseline analysis preregistration — draft decision register

**Version:** `analysis-plan-0.1-draft` (document v0.1, **draft**). **Status:** proposal for review. Nothing here is frozen, approved, or evidence. No data exists; no output has been inspected.
**Issue:** [#25](https://github.com/FacialReplicationPrevention/FRP/issues/25) (Milestone 004, PR 3G). **Design source:** [Experiment 003](../experiments/003-wan21-i2v-baseline-design.md) §4–5 and §7. **Companions:** [Participant capture protocol](participant-capture-protocol.md), [Participant data lifecycle](participant-data-lifecycle.md), [Private review viewer](private-review-viewer.md).
**Target (fixed):** Wan 2.1 I2V-14B-480P, single condition, original reference on both CLIP and VAE routes, `use_prompt_extend: false`. No A/B/C/D contrast and no statement about Wan 2.2 or other models.

## 1. Claim classes

| Class | Basis | May say | May not say |
| --- | --- | --- | --- |
| **Smoke** (uncalibrated) | One consented adult, one prompt, one seed | Technical pass/fail, runtime, cost | Any similarity, retention, utility or population statement |
| **Exploratory, uncalibrated** | Too few identities to calibrate or cluster | Descriptive counts, coverage, failures, labelled *uncalibrated* | Match decisions, intervals, efficacy |
| **Calibrated baseline** | Identity-disjoint calibration set exists and operating points were fixed before evaluation | Descriptive, identity-clustered statistics with all failures | Efficacy, protection, other models/recognisers |

**One person can support a technical smoke test but cannot supply identity-disjoint calibration and evaluation populations, impostor controls or population-level uncertainty.** A face-similarity value is neither identity proof nor consent evidence; a low one is not protection evidence. **Public reports of real data remain disabled** until a privacy review defines disclosure rules.

## 2. Decision register

Legend: **Enforced** = checked by existing code; **Proposed** = candidate to freeze before real outputs are examined; **Review** = needs human/scientific review. Entries with no defensible value stay `pending`; no numbers are invented.

| ID | Decision | State | Detail / candidate | Where enforced |
| --- | --- | --- | --- | --- |
| D01 | Single condition, original on CLIP and VAE, no prompt extension | Enforced | Literal-typed manifest fields | `frp.baseline.manifest` |
| D02 | Role ↔ identity split (`smoke` none; `calibration`; `baseline` = evaluation) | Enforced | Per run set | `frp.baseline.manifest`, `identity_overlap` |
| D03 | Calibration/evaluation lists disjoint inside one plan; ≥2 calibration identities to claim calibration | Enforced (draft check) | Logical minimum, not a sample size | `frp.baseline.analysis_plan` |
| D04 | Frame sampling rule frozen before outputs | Proposed | For 81 frames `0,20,40,60,80`; proportional for other 4n+1 counts | Bounds/ordering enforced in manifest and plan check; the set itself is not |
| D05 | Frame 0 reported separately; frames with index ≠ 0 are primary | Enforced | Conditioned first frame may be unusually close to source | `frp.baseline.aggregation` |
| D06 | Minimum valid later frames per clip | **Pending** | Must satisfy 1 ≤ min ≤ number of later sampled frames (checked). Value to be chosen from pilot evidence | Range only (plan check); required caller input in aggregation |
| D07 | Frame status denominators | Enforced | See §3 | `frp.results`, `frp.baseline.aggregation` |
| D08 | No zero/imputed similarity | Enforced | Similarity exists only for `valid` | `frp.results.FrameEvaluation`; plan field fixed |
| D09 | Attempt inclusion/selection | Proposed | `first_attempt` per planned run for the primary analysis; `last_attempt` only as labelled sensitivity. All attempts reported | Choice restricted to the two supported values (aggregation, plan check) |
| D10 | Seed-consistency vs quality-failure separation | Proposed | See §4 | Not enforced |
| D11 | Face evaluator and second evaluator | **Review** | Feasibility, licence and recogniser-specific effects open (Exp. 003 decision 3) | Not enforced |
| D12 | Genuine/impostor calibration on independent adults | Proposed | See §5 | Not enforced; no calibration code exists |
| D13 | Operating thresholds | **Pending** | Fixed on calibration identities only; **no universal cutoff** | — |
| D14 | Minimum identities for calibration and for an identity-clustered interval | **Pending** | Not defensible before pilot evidence (Exp. 003 decision 2) | Mechanical only: the synthetic prototype withholds an interval below two identity values; this is not a minimum sample size |
| D15 | Uncertainty method | **Review** | Identity-clustered; method and few-identity limits in §6 | Only a synthetic, opt-in demonstration (`frp.baseline.synthetic_uncertainty`), refused for non-simulated and smoke results; the method is **not** chosen or approved |
| D16 | Video utility: automated metrics + blinded human rubric | **Review** | Rubric `frp-blinded-quality-rubric-0.1-draft` is unvalidated | Viewer records ratings (synthetic only) |
| D17 | Failure reporting and disclosure safeguards | Proposed | See §7 | Partly (all attempts kept; no public real-data reports) |
| D18 | Draft plan status and review state | Enforced | `status` is only `draft`; per-decision `pending`/`proposed`; no reviewed/frozen/approved value exists | `frp.baseline.analysis_plan` |
| D19 | Distinct pseudonyms are not proof of distinct people | **Review** | A private data steward must verify calibration/evaluation separation against the restricted participant-to-pseudonym mapping before calibration or evaluation. The draft check compares pseudonym strings only and **cannot** establish identity-disjointness in a real dataset. The mapping is never added to this repository | Not enforceable in public code |

## 3. Denominators and statuses

Per sampled frame the status is one of `valid`, `absent`, `multiple`, `low_quality`, `error`, `not_evaluated`. Coverage tables report counts of **every** status at each index with explicit denominators over *all planned* runs, including failed and unexecuted ones (`not_evaluated`).

- Similarity summaries use `valid` frames only and are always shown with their coverage.
- `absent`, `multiple`, `low_quality`, `error` and `not_evaluated` are **never** zero-imputed, dropped from the denominator, or averaged in. When several faces are present, no face is chosen by highest score.
- A clip with fewer than the minimum valid later frames (D06) has no later-frame similarity and is counted as such, not as zero.
- Generation failures and unexecuted runs stay in the identity's run count.

## 4. Attempts, seeds and failures

- Every attempt is recorded; a retry is a new attempt. Only transient failures are retried up to the plan's cap (existing executor behaviour).
- The primary rule is fixed **before** outputs are examined; changing it after is a reported deviation, not a re-analysis.
- Seed consistency (does the same seed reproduce a clip on the same/another hardware) is assessed with a same-seed repeat and reported separately from **quality failure** (a clip that is unscorable, distorted or has no face). Between-seed variability is reported per identity; neither is folded into similarity.

## 5. Calibration and controls

1. **Genuine/impostor pairs** from real-photograph calibration data on **independent adults** (≥2 identities needed; the count is D14), using calibration photos that are not the Wan reference ([capture protocol](participant-capture-protocol.md)).
2. **Generated-video impostor controls:** reference of identity *i* against frames of clips generated for identity *j ≠ i*, matched as far as possible on prompt, seed, frame index, controls and quality status, because a photo-derived threshold need not transfer to compressed or blurred generated frames. Any unmatched factor is disclosed.
3. **Thresholds are fixed on calibration identities only**, applied unchanged to evaluation identities, and never tuned on evaluation outputs.
4. **Evaluation identities are disjoint** from calibration identities.
5. **Secondary evaluation approach** (second recogniser, detector or human identity-observation mode) is an **unresolved future choice**, recorded as D11.
6. Where a calibrated operating point cannot be set, results stay exploratory and uncalibrated.

## 6. Aggregation and uncertainty

Frames → clip (later-frame median over valid frames, frame 0 separate) → identity (median over clips) → role (median over identities), as implemented descriptively in `frp.baseline.aggregation`. Intervals, if computed, are **clustered by identity** with a method fixed in the plan (D15). With few identities (the threshold is D14, pending) report each identity's value individually and no interval; a two- or three-identity result is a case series, not a population estimate. Video utility is summarised separately and never combined with similarity into one score; a blinded human rubric is used alongside automated metrics, with reviewers shielded from run condition where feasible.

## 7. Failure reporting and disclosure

Report all attempts, failures, missingness and negative results; subgroup and demographic limits; and that results concern one model, recogniser and prompt set. Never publish real images, frames, embeddings or small-cell tables that could identify a participant. Preserve unexpected behaviour and confounders (e.g. recogniser-specific effects, video-quality drops).

## 8. Freeze, hash and sign-off procedure (human, private)

1. A human drafts the plan in a **private** versioned file with all pending items resolved or explicitly left pending.
2. A qualified reviewer reads it and the open decisions (D06, D11, D13–D16).
3. A human computes a digest of the exact file (for example SHA-256) and records it, the date and the reviewer in a **private** approval record **before** any real output is viewed.
4. Any later change creates a new version and a recorded deviation.
5. `status: draft` in a repository file proves nothing. No schema value, command or CI check here grants or records a freeze, ethics approval or readiness gate; a plan labelled "frozen" anywhere is not evidence of approval. The existing `analysis_plan_version` manifest field only names a version string.

## 9. Check available now

`frp.baseline.analysis_plan.parse_analysis_plan` / `load_analysis_plan` validate a synthetic **draft** plan record (example: [`examples/analysis-plans/synthetic-draft-analysis-plan.yaml`](../examples/analysis-plans/synthetic-draft-analysis-plan.yaml)) for role/split consistency, duplicate or overlapping pseudonyms, frame bounds (a proposed selection needs a known `frame_count`, frame 0 and at least one later frame), an impossible minimum-later-frames rule (a proposed minimum needs proposed `frame_indices`), unsupported attempt-selection values, placeholders presented as proposed settings, and false approved states. Errors withhold input values and pseudonyms. A validated plan does not show that calibration was performed or accepted, and `calibration_claim: calibrated` states an intended draft configuration only. It consumes no media and calls no model; it is a consistency check, not an approval.

## 10. Limitations

Proposed rules are untested; no threshold, sample size, ArcFace compatibility or efficacy is validated. Numeric choices wait for pilot evidence and human review.
