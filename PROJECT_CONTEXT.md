# FRP — Project context and scientific rationale

**Last updated:** 2026-10-30  
**Project stage:** Early research, experiment design, pinned static source review of candidate models (Milestone 003, merged), and a CPU-only harness with a *simulated* pipeline, offline provenance validation and an offline GPU-readiness template check. Milestone 004 ([#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)) is current and its first PR is CPU-only preparation. No model inference, GPU run or evaluation of real people has taken place, and no Wan experiment results are reported.

## What is FRP?

**Facial Replication Prevention (FRP)** is a research project investigating ways to reduce unauthorised reproduction of real people's recognisable facial identity by generative image and video models, particularly open-weight systems runnable locally.

The motivating concern is that someone may obtain an online portrait and use generative tools to create a recognisable, non-consensual synthetic depiction. We seek **preventive** safeguards, not solely retrospective deepfake detection.

### Long-term aspiration

Find whether the behaviour of a model can be changed intrinsically—through representation learning, architecture, conditioning or training objectives—so it becomes substantially less capable of reproducing an unauthorised identity while still supporting useful, legitimate generation.

**This aspiration has not been demonstrated.** Even effective learned safeguards would not make freely editable model weights universally tamper-proof or prevent use of unrelated unprotected models.

## The CID proposal

Earlier discussions called a candidate architecture the **CID pipeline**. Its proposed components are:

1. A representation of facial identity-related features.
2. A separate context/permission process.
3. A generation-time or training-time mechanism that attempts to prevent disallowed identity reproduction.

The CID design is a **research hypothesis**, not a proven architectural property. In particular:
- A facial embedding cannot establish informed consent.
- The proposed identity flag (e.g. `is_real_identity`) is not reliable evidence of a real identity or permission.
- Identity cues can travel through multiple visual-conditioning and model-weight pathways.
- A single software gate can be changed or bypassed in a local open-weight deployment.
- "Mathematical mutual exclusion" should be treated as an aspirational conjecture, not a proven guarantee.

## Key separations

| Problem | What we seek | What it does *not* solve |
| --- | --- | --- |
| **Measurement** | Quantify recognisable identity preservation and errors | Establish consent or prevent replication |
| **Model-level mitigation** | Reduce unwanted identity retention while preserving utility | Make open weights immutable |
| **Authorisation** | Reliably distinguish approved and unapproved use | Derive permission from face geometry |
| **Hardening** | Raise the effort needed to bypass a useful safeguard | Guarantee safety against all modified or alternate models |
| **Governance** | Incentivise/enforce adoption in supported settings | Replace technical evidence |

We are deliberately tackling **measurement and model feasibility first**, with hardening as a separate, later research direction.

## Current architecture under investigation

**Initial candidate:** [Official Wan2.1 image-to-video](https://github.com/Wan-Video/Wan2.1), pinned at commit `9737cba9c1c3c4d04b33fcad41c111989865d315`, with the `Wan-AI/Wan2.1-I2V-14B-480P` checkpoint at Hub revision `6b73f84e66371cdfe870c72acd6826e1d61cf279` (weight hashes not yet verified), as described in [Experiment 002](experiments/002-conditioning-ablation-protocol.md) and [Research 005](research/005-wan-model-candidates.md).

The implementation exposes two image-conditioning routes:
- **CLIP Vision pathway:** visual image features projected into transformer attention.
- **Video VAE first-frame pathway:** an encoded conditioning video containing the source frame, followed by blank frames, with a mask; the condition joins the denoising latent input.

This is a **source-code-derived architectural observation**, re-checked at the pinned commit; it does not establish the exact location or separability of facial identity. See [Research 003](research/003-wan21-i2v-architecture.md) and [Research 005](research/005-wan-model-candidates.md). The same code also offers an optional, default-off prompt-extension mode that can pass the image to a vision-language model and so influence text conditioning; Experiment 002 assumes it is off.

## Model scope and multi-model strategy

FRP is a **cross-model** research project, not a Wan 2.1-only project. Experiments are nevertheless **model-specific**.

- **Why open weights:** locally run open-weight models are outside hosted-service filters, so any durable safeguard would need to be a property of the model or its training, which is the long-term question above.
- **Wan 2.1 I2V** is the original, specifically scoped reference for the CLIP-Vision/VAE first-frame ablation. Research 003–004, Experiment 002, the harness's A/B/C/D run plan and its result protocol id `wan2.1-i2v-clip-vae-2x2` all apply to Wan 2.1 only.
- **Wan 2.2 I2V-A14B** is the optional later candidate. A static review at pinned commit `1ea34ff48f87168174e12956e200b1d908b1c5ff` found **no CLIP-vision pathway**: the image enters only through the VAE first-frame latent and mask, and denoising is split between two expert models. The Wan 2.1 A/B/C/D design therefore does **not** transfer; a separate protocol would need its own scientific review. Wan 2.2 TI2V-5B uses yet another mechanism (first-latent-frame replacement).
- **Other official generations and derivative/community checkpoints** are inventoried in [Research 005](research/005-wan-model-candidates.md) only where existence and access are confirmed; unverified properties are marked as such. No Wan generation after 2.2 was found in the official organisations as of 2026-10-30.
- **Distinct properties:** facial identity retention, content/safety capabilities and authorisation are separate questions. Derivative fine-tunes with relaxed content restrictions, and quantised or distilled derivatives that lower hardware requirements, matter to the threat model and could undo a future model-level mitigation; initial FRP experiments remain neutral, consented and non-explicit, and FRP does not acquire or test explicit-content checkpoints.
- **Model-specific reproducibility and provenance:** every model studied needs its own pinned source commit, checkpoint revision and weight hashes, licence review, a verified description of its conditioning paths and a reviewed protocol identifier. These are recorded in the machine-readable [provenance inventory](provenance/model-candidates.yaml) with explicit `verified` / `pending` / `not_verified` / `unknown` statuses and checked offline by `frp provenance`, which refuses to apply the Wan 2.1 protocol to any other architecture. A valid inventory is internally consistent, not proof of the recorded facts.

Model selection and verification were Milestone 003 ([#7](https://github.com/FacialReplicationPrevention/FRP/issues/7), PR [#8](https://github.com/FacialReplicationPrevention/FRP/pull/8), merged; documentation tracker [#4](https://github.com/FacialReplicationPrevention/FRP/issues/4)) and Phase 2b of the [roadmap](ROADMAP.md). The recommended initial baseline is a recommendation, not an authorisation to download weights or run GPU jobs.

**Current milestone — Milestone 004** ([#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)): a controlled Wan 2.1 baseline, calibration and private visual review, in three gated PRs. PR 1 (this stage) is **preparation only**: a [GPU readiness protocol](docs/gpu-readiness.md) defining seven separate human approvals (licence and intended use; consent and data processing; restricted storage, retention and deletion; cloud-provider terms; quote and budget cap; checkpoint download and hashing; the GPU smoke test), a blank cost-quote template, the [single-condition baseline design](experiments/003-wan21-i2v-baseline-design.md) (distinct from A/B/C/D, using the original reference on both Wan 2.1 image routes with `use_prompt_extend: false`) and a [private visual-review specification](docs/private-review-viewer.md). Every gate is pending; the GPU, inference and evaluation have **not** run. Wan 2.2 has no transferable A/B/C/D protocol.

## Current experimental hypothesis

Use a paired **2 × 2 conditioning ablation** with fixed prompts, seeds, model/checkpoint and preprocessing:

| Condition | CLIP conditioning | VAE first-frame conditioning |
| --- | --- | --- |
| A | Original | Original |
| B | Altered | Original |
| C | Original | Altered |
| D | Altered | Altered |

The current proposed alteration is a deterministic face-region low-pass transformation, applied **only** to the selected route. This is a diagnostic distribution shift, not a validated anonymisation technique. It may degrade output quality, create branch disagreement, and confound interpretation.

**Primary question:** Does altering either path change calibrated face similarity in generated videos, and what video-utility cost accompanies the change?

Provisional metrics:
- Valid-face detection rate and ambiguous/failed-frame counts.
- Reference-to-generated-frame embedding similarity, calibrated on separate authorised genuine/impostor pairs.
- Temporal identity drift, specifically distinguishing early/first frames from later frames.
- Video usefulness, including subject visibility, scene continuity, motion and prompt adherence.
- Paired comparisons with identity-level statistical uncertainty and explicit missingness.

A lower similarity score alone is **not a successful prevention result**; an absent face or ruined video must be accounted for.

## Published project material

- [Research 001 — Identity replication measurement](research/001-identity-replication-measurement.md): measuring retention and limitations of face similarity.
- [Research 002 — CID feasibility and threat model](research/002-cid-feasibility-threat-model.md): architectural hypotheses and bypass risks.
- [Research 003 — Wan2.1 I2V architecture](research/003-wan21-i2v-architecture.md): observed conditioning pathways.
- [Research 004 — Conditioning ablation design](research/004-conditioning-ablation-design.md): methodological controls and hypotheses (Wan 2.1 only).
- [Research 005 — Wan model candidates](research/005-wan-model-candidates.md): pinned source verification of Wan 2.1 and 2.2, candidate inventory and baseline recommendation.
- [Experiment 001 — Baseline protocol](experiments/001-baseline-protocol.md): evaluation baseline plan.
- [Experiment 002 — Conditioning ablation protocol](experiments/002-conditioning-ablation-protocol.md): proposed pilot and data schema.
- [Experiment 003 — Wan 2.1 I2V single-condition baseline](experiments/003-wan21-i2v-baseline-design.md): design only; baseline contract separate from the ablation.
- [GPU readiness protocol](docs/gpu-readiness.md) and [private visual-review specification](docs/private-review-viewer.md): Milestone 004 design documents; nothing approved or built.

**Evidence status:** These are literature/source-code studies and proposed protocols. The project has **not** reported empirical model mitigation results. Do not imply that any tested protection, percentage reduction or universal safeguard exists. The harness's simulated reports ([docs/harness.md](docs/harness.md)) are software tests on synthetic fixtures, not evidence, and a valid provenance inventory is a consistency check, not verification of model behaviour.

## Development environment and working model

- **Repository:** https://github.com/FacialReplicationPrevention/FRP
- **Editing and tests:** GitHub Codespaces, initially a lightweight CPU environment.
- **Code:** Python first for PyTorch/Wan interoperability; C# may eventually provide orchestration.
- **Compute:** short-lived rented GPU infrastructure **only when** the harness, data permissions and cost approval are ready.
- **AI collaboration:** A research/planning assistant and one or more coding agents may have **different conversation memories**. Repository files are the shared project context. [AGENTS.md](AGENTS.md) gives coding agents practical instructions.
- **Privacy:** The repository is public. No private photos, identifiable outputs, biometric embeddings, consent records, API keys or participant mappings should be committed.

## Unresolved scientific questions

1. How much identity information is available through each Wan image-conditioning route?
2. Are measured effects distinguishable from general visual degradation or out-of-distribution artefacts?
3. Can training-time changes suppress novel, previously unseen identity reproduction while retaining motion and visual utility?
4. Can protection preserve **authorised** use in the presence of a trustworthy permission system?
5. What is the cost/quality trade-off, including false positives and variation across people and input conditions?
6. How easily could a local operator restore identity reproduction by replacing components or adapting weights?
7. What independent mechanisms could verify consent without creating an invasive biometric registry?

## Decision discipline

Do not start a model-training effort or claim tamper resistance before the baseline and feasibility results warrant it. Document scientific claims with citations and mark all proposed mechanisms clearly as hypotheses.

See [ROADMAP.md](ROADMAP.md) for the next implementable tasks and checkpoints.
