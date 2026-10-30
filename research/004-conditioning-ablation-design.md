# Research 004 — Conditioning-pathway ablation design for Wan 2.1 I2V

**Date:** 2026-10-29  
**Status:** Preregistered-design draft; no model runs or efficacy results  
**Depends on:** [Research 001](001-identity-replication-measurement.md), [Research 003](003-wan21-i2v-architecture.md)  
**Execution protocol:** [Experiment 002](../experiments/002-conditioning-ablation-protocol.md)

> **Scope (2026-10-30).** This design applies to **Wan 2.1 I2V only** (official `Wan-AI/Wan2.1-I2V-14B-480P`). [Research 005](005-wan-model-candidates.md) re-checked the cited code at pinned commit `9737cba9c1c3c4d04b33fcad41c111989865d315` and found it consistent with the assumptions below. It also records limitations for review: an optional `--use_prompt_extend` path that can route the image into text conditioning, and different resize paths for CLIP and VAE. Wan 2.2 I2V-A14B has no CLIP-vision path, so this 2 × 2 design does not transfer. Nothing in the design below has been changed.

## Core question

How sensitive is output facial-identity similarity to separately changing the CLIP-image and first-frame VAE conditioning pathways in an unmodified Wan2.1 image-to-video (I2V) checkpoint?

This is a **mechanistic sensitivity experiment**, *not* a demonstration of selective face de-identification, verified consent, or universally enforceable protection.

## Evidence from upstream implementation

In the official `wan/image2video.py` implementation:

- `clip_context = self.clip.visual(...)` produces image-conditioning features.
- The pipeline separately constructs a video with the first reference frame followed by blank frames, encodes this using the video VAE, and concatenates a temporal first-frame mask into `y`.
- The same `clip_fea` and `y` are supplied to conditional and negative-text model calls. Text context changes between these calls.
- The denoised latent is VAE-decoded to video.

In `wan/modules/model.py`, the first-frame condition `y` is channel-concatenated with video latent `x`, while projected CLIP features are incorporated in the transformer's cross-attention context.

**Sources:** [official I2V inference](https://github.com/Wan-Video/Wan2.1/blob/main/wan/image2video.py), [official model](https://github.com/Wan-Video/Wan2.1/blob/main/wan/modules/model.py). Freeze exact upstream commit SHA and checkpoint hashes before execution; links to `main` alone are not reproducible.

## Design: paired 2 × 2 comparison

Two factors: CLIP image-conditioning input (original / altered) and VAE first-frame input (original / altered). These are processing-path interventions; they should not alter the text prompt, initial noise, image geometry, frame count, VAE mask definition, checkpoint, sampler or guidance parameters.

| ID | CLIP source | VAE first-frame source | Interpretation |
| --- | --- | --- | --- |
| A | Original approved image | Original approved image | Baseline |
| B | Pre-registered altered image | Original approved image | Sensitivity to CLIP path |
| C | Original approved image | Pre-registered altered image | Sensitivity to VAE path |
| D | Pre-registered altered image | Pre-registered altered image | Combined intervention / interaction |

**Initial alteration:** A deterministic, fixed-parameter face-region low-pass transformation derived from the *same* authorised reference image, with consistent geometry and untouched outer image area. The parameters, face-mask provenance and resulting distribution shift must be recorded. The altered image is used *only* in the selected path. Pilot the transformation on non-identifiable content before authorised portrait evaluation.

This alteration is not presumed to remove identity or to be a robust defence: residual structure may remain, and quality changes are expected. Do not interpret a lower similarity score as a successful safeguard if the generated subject disappears, the face detector fails, or the video quality collapses.

**Important controls:**

1. Preserve the same temporal first-frame mask across A–D. In VAE interventions alter the encoded first-frame *image content*, not the mask or future-frame zeros.
2. Maintain exactly the same original/negative text prompts and guidance logic. Pass each selected pair of image conditions consistently to both positive-text and negative-text denoiser calls.
3. Use identical seed, latent-noise shape, noise generator settings and sampling parameters across paired A–D runs.
4. Avoid zeroing model embeddings as a primary comparison: all-zero tensors may be far outside the training distribution.
5. Validate reference and altered images share size, aspect ratio, colour range, preprocessing and crop geometry.
6. Treat interactions as possible: the branches are not assumed independent or additive.
7. Use the unmodified upstream checkpoint; do not train or fine-tune during this experiment.

## Preregistered hypotheses

- **H4.1:** At least one path alteration changes facial-identity similarity relative to baseline under fixed seeds.
- **H4.2:** Combined alteration may have a different effect from either individual alteration, including a non-additive interaction.
- **H4.3:** Some changes that reduce measured identity similarity will also harm useful video generation, face visibility or temporal quality.
- **H4.4:** Conditions with similar identity scores may differ in detection failure, recognisability and video quality.

Do not presume direction or size of effects. If all measured changes are negligible or unreliable, report that result.

## Outcomes and interpretation

### Identity-related outcomes

For each *single-face* approved reference and generated video:

- Detect faces at preselected frames and log successful/failed/ambiguous detections.
- For valid faces only, evaluate cosine similarity between normalised reference and frame embeddings using a fixed recogniser (e.g. ArcFace-family model).
- Separate first-frame similarity from later frames to avoid conflating anchored-frame reconstruction with sustained preservation.
- Primary summary: median similarity across selected later frames **conditional on valid detection**; include the proportion of videos for which this summary is unavailable.
- Calibrate match thresholds from a non-overlapping set of consenting genuine/impostor pairs; report threshold error rates, not an unexplained universal score.
- Compare with an independent recogniser or blinded opt-in recognisability assessment where available.

A missing face is **not automatically privacy protection**: it may reflect an unusable video.

### Video-utility outcomes

Use a pre-registered blinded quality rubric for (i) a visible, plausible single subject, (ii) scene continuity, (iii) smoothness/flicker, (iv) motion plausibility, and (v) prompt adherence. Where feasible, report corresponding VBench/VBench++ dimensions, with evaluation versions specified.

VBench: https://openaccess.thecvf.com/content/CVPR2024/html/Huang_VBench_Comprehensive_Benchmark_Suite_for_Video_Generative_Models_CVPR_2024_paper.html

### Paired contrasts

Within each identity, source image, prompt and seed, estimate A-to-B, A-to-C and A-to-D outcome differences. Report paired effect-size distributions and uncertainty using identity-level clustering. With four conditions, examine the **B/C/D interaction** qualitatively or quantitatively only with sufficient data.

**No universal numeric pass threshold** is asserted at this design stage. A meaningful result requires both calibrated identity outcomes and non-inferior/acceptable video utility, with acceptability defined before confirmatory tests.

## Major validity threats

- **Out-of-distribution intervention:** blurred input features were not necessarily seen in training; altered outputs do not prove identity was localised to that branch.
- **Branch disagreement:** condition B or C supplies inconsistent interpretations of the same subject, itself potentially causing instability.
- **Misleading face-matching:** expression, pose, crop, brightness, and demographic effects can change face similarities. See [NIST FRTE](https://pages.nist.gov/frvt/html/frvt11.html).
- **Selection bias:** analysing only easy, correctly detected faces can inflate apparent fidelity.
- **Dependence:** frames from one clip and clips from one identity are not independent observations.
- **Scope:** results on one checkpoint, one alteration, or one consented cohort do not generalise to all models, contexts or malicious local modifications.

## Why this matters to CID / FRP

If changing CLIP conditioning barely changes similarity but changing the VAE path does, that would help prioritise future study *for that exact setup*. If both carry influential identity cues or quality declines severely, simple path blocking is unlikely to be an adequate safeguard. Neither result would show facial identity is encoded in a single cleanly separable tensor.

An inference-time policy can be bypassed by local model operators; the experiment tests conditioning sensitivity and **does not** solve enforcement or authentication of consent.

## Decision and next milestone

Proceed in gates:
1. **Static design and source audit** without renting a GPU.
2. **Non-identifying shape/metadata instrumentation** to check both paths and matched sampling.
3. **Authorised pilot** to estimate measurement variance and utility trade-offs.
4. **Pre-registered confirmatory study**, only if pilot quality and consent constraints are satisfied.

See [Experiment 002](../experiments/002-conditioning-ablation-protocol.md) for the runnable planning checklist and results schema.

## Supporting sources

- Wan-Video, [Wan2.1](https://github.com/Wan-Video/Wan2.1)
- Deng et al., [ArcFace (CVPR 2019)](https://openaccess.thecvf.com/content_CVPR_2019/html/Deng_ArcFace_Additive_Angular_Margin_Loss_for_Deep_Face_Recognition_CVPR_2019_paper.html)
- NIST, [Face Recognition Technology Evaluation — 1:1](https://pages.nist.gov/frvt/html/frvt11.html)
- Huang et al., [VBench (CVPR 2024)](https://openaccess.thecvf.com/content/CVPR2024/html/Huang_VBench_Comprehensive_Benchmark_Suite_for_Video_Generative_Models_CVPR_2024_paper.html)
