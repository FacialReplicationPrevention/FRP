# FRP — Project context and scientific rationale

**Last updated:** 2026-10-29  
**Project stage:** Early research and experiment design; no Wan GPU experiments reported.

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

**Initial candidate:** [Official Wan2.1 image-to-video](https://github.com/Wan-Video/Wan2.1), especially the `Wan2.1-I2V-14B-480P` checkpoint described in [Experiment 002](experiments/002-conditioning-ablation-protocol.md).

The implementation exposes two image-conditioning routes:
- **CLIP Vision pathway:** visual image features projected into transformer attention.
- **Video VAE first-frame pathway:** an encoded conditioning video containing the source frame, followed by blank frames, with a mask; the condition joins the denoising latent input.

This is a **source-code-derived architectural observation**; it does not establish the exact location or separability of facial identity. See [Research 003](research/003-wan21-i2v-architecture.md).

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
- [Research 004 — Conditioning ablation design](research/004-conditioning-ablation-design.md): methodological controls and hypotheses.
- [Experiment 001 — Baseline protocol](experiments/001-baseline-protocol.md): evaluation baseline plan.
- [Experiment 002 — Conditioning ablation protocol](experiments/002-conditioning-ablation-protocol.md): proposed pilot and data schema.

**Evidence status:** These are literature/source-code studies and proposed protocols. The project has **not** reported empirical model mitigation results. Do not imply that any tested protection, percentage reduction or universal safeguard exists.

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
