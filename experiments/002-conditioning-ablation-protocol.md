# Experiment 002 — Wan2.1 conditioning-pathway ablation

**Date:** 2026-10-29  
**Status:** Planned — not executed  
**Design rationale:** [Research 004](../research/004-conditioning-ablation-design.md)  
**Ethics:** No portraits, biometric embeddings, identity-matched outputs or consent records in this public repository.

## Goal

Evaluate whether changes to either or both input-image conditioning paths alter facial-identity similarity while preserving acceptable, useful video quality.

**This is a diagnostic study, not a deployed safeguard.**

## Test stages and cost gate

### Gate 0 — No GPU

- [ ] Pin a Wan2.1 upstream commit, choose *I2V-14B-480P* checkpoint and record model licence and weight hashes.
- [ ] Inspect the two paths in `wan/image2video.py` and `wan/modules/model.py` at the pinned revision.
- [ ] Define a deterministic branch-specific altered image transform and verify crop/colour/size invariants.
- [ ] Draft consent, retention/deletion procedure, restricted storage and approved benign prompts.
- [ ] Record machine requirements and obtain a rental quote **before** allocating GPU time.
- [ ] Freeze experiment manifest and results schema.

Official checkpoint: https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P

**Important:** The public 1.3B model is text-to-video; it is not a drop-in smaller equivalent of the 14B I2V checkpoint. Hardware costs must be established for the actual selected checkpoint.

### Gate 1 — Instrumentation / smoke test

- [ ] Record only shapes, dtypes, device and control-flow assertions for `clip_context`, encoded `y`, mask, `arg_c` and `arg_null`; never publish raw tensors.
- [ ] Confirm that both positive and negative text passes receive the same branch conditions for each variant.
- [ ] Check paired runs reuse the same noise seed and sampling settings.
- [ ] Attempt A–D on one explicitly consented benign input. This is a **technical test**, not a scientific estimate.

### Gate 2 — Exploratory pilot

- [ ] Example starting budget: 3–5 consenting adult identities, one image each, two seeds, one neutral-motion prompt, A–D = **24–40 generated clips**.
- [ ] Treat all pilot comparisons as exploratory; estimate runtimes and variability rather than making population-level efficacy claims.
- [ ] Check frame detection reliability, calibration and blind quality rubric feasibility.
- [ ] Estimate a confirmatory sample size based on pilot variability and target confidence precision; do not retroactively choose thresholds after viewing confirmatory data.

### Gate 3 — Confirmatory replication

- [ ] Select identity count and balance with a documented power/precision rationale.
- [ ] Freeze prompts, seeds, transformation parameters, evaluator versions and the statistical analysis plan.
- [ ] Split consented identities between calibration and test sets, with no identity overlap.
- [ ] Report all trials, including unusable outputs and failed detections.

## A–D test matrix

| Condition | CLIP input | VAE first-frame input |
| --- | --- | --- |
| A | Original | Original |
| B | Altered | Original |
| C | Original | Altered |
| D | Altered | Altered |

The 'altered' input is one fixed, documented face-region low-pass transformation of that reference. This is an **evaluation manipulation**, not a validated anonymisation method. Maintain unchanged reference-frame mask and all noncondition variables.

## Run manifest (example, values must be filled before running)

```yaml
experiment_id: FRP-EXP-002
status: planned
upstream_repository: Wan-Video/Wan2.1
upstream_commit_sha: null
checkpoint: Wan-AI/Wan2.1-I2V-14B-480P
checkpoint_hashes: null
model_license_reviewed: false
consent_record_location: private_only
number_of_identities: null
image_count_per_identity: 1
seeds: null
prompt_template_version: null
alteration_method_version: null
alteration_parameters: null
sampler: null
sampling_steps: null
guidance_scale: null
frame_count: null
resolution: null
precision: null
face_evaluator_revision: null
face_detection_settings: null
calibration_dataset_version: null
frame_indices: null
quality_rubric_version: null
analysis_plan_version: null
gpu_model: null
software_environment_hash: null
```

**Do not fill unspecified values from guesses; record actual values after selection.**

## Analysis unit and frame sampling

- Primary comparison unit: *identity*, with paired runs matched by source image, prompt and seed.
- For 81-frame video a candidate pre-registered measurement set is frames **0, 20, 40, 60, 80**, and primary later-frame median uses **20, 40, 60, 80**; adapt the indices proportionally if a different frame count is locked in.
- Log multiple faces or no face as a distinct ambiguous/detection failure outcome; do not arbitrarily pick whichever face scores highest.
- Reference image should have one consenting adult and one clearly visible face.
- Assess quality using blinded raters not told which variant was generated.

## Outcomes

| Field | Description |
| --- | --- |
| `run_id` | Random non-identifying ID |
| `identity_pseudonym` | Private, not published |
| `variant` | A, B, C or D |
| `seed` | Sampling seed |
| `frame_index` | Preselected sampled frame index |
| `face_status` | valid / absent / multiple / low_quality / error |
| `similarity` | Calibrated model cosine score **only if valid**, otherwise null |
| `face_quality_flag` | Predefined diagnostic |
| `utility_score` | Blinded rubric, on a predeclared scale |
| `gpu_seconds` | Runtime |
| `software_hashes` | Pinned revisions |

Public results should be **aggregated** without identity linkage or biometric data. Preserve all attempted runs in private audit logs as permitted by consent agreements.

### Primary comparisons

- Median later-frame similarity conditional on successful detection, reported jointly with the detection rate.
- Paired A–B, A–C and A–D differences at identity level.
- Conditional video-utility score and unusable-video rate for every variant.
- Genuine/impostor calibration performance at declared threshold settings. No arbitrary universal threshold.
- Exploratory two-factor interaction, with uncertainty and no false claims of causal disentanglement.

## Interpretation rules

A lower match score together with reduced face detection, loss of subject, severe blur or unacceptable quality **does not count as protective success**. An unchanged score does not prove that the path carries no information: the model may compensate, or the intervention may be ineffective.

No outcomes are currently known. Never publish fabricated results, confidence intervals, hardware costs or safety guarantees.

## Source references

- [Wan2.1 official inference code](https://github.com/Wan-Video/Wan2.1/blob/main/wan/image2video.py)
- [Wan2.1 transformer model](https://github.com/Wan-Video/Wan2.1/blob/main/wan/modules/model.py)
- [ArcFace](https://openaccess.thecvf.com/content_CVPR_2019/html/Deng_ArcFace_Additive_Angular_Margin_Loss_for_Deep_Face_Recognition_CVPR_2019_paper.html)
- [NIST FRTE 1:1](https://pages.nist.gov/frvt/html/frvt11.html)
- [VBench](https://github.com/Vchitect/VBench)
