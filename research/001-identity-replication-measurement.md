# Research 001 — Measuring facial identity replication

**Date:** 2026-10-29  
**Status:** Initial literature review and experimental hypotheses; no FRP results yet.

## Research question

Can a reproducible evaluation measure how strongly a generated video preserves the facial identity in a consenting reference portrait?

## Established starting points

- [Wan2.1](https://github.com/Wan-Video/Wan2.1) supports image-to-video generation and provides an open system for controlled evaluation. This does not establish how consistently identity survives generation.
- [ArcFace (CVPR 2019)](https://openaccess.thecvf.com/content_CVPR_2019/html/Deng_ArcFace_Additive_Angular_Margin_Loss_for_Deep_Face_Recognition_CVPR_2019_paper.html) learns face embeddings that support similarity comparisons. Similarity is an imperfect proxy for identity, not proof of authenticity or consent.
- [InstantID (2024)](https://arxiv.org/abs/2401.07519) illustrates deliberate identity conditioning in an image diffusion architecture. Do not assume its conditioning architecture is identical to Wan I2V.
- [NIST demographic effects](https://pages.nist.gov/frvt/html/frvt_demographics.html) describes face-recognition performance differences and underscores the need to report operating conditions and group-specific uncertainty.

## Measurement proposal

1. Choose a consenting adult dataset with rights for this specific research (or suitably permitted synthetic identities).
2. Calibrate a face matcher on genuine and impostor image pairs, with identity-disjoint partitions.
3. Generate benign I2V clips from consented reference portraits with fixed prompt templates and recorded seeds.
4. Sample video frames at a predefined interval and record face detection failures instead of discarding them.
5. Compute cosine similarity between unit-normalised embeddings of the reference and each detected face: `s_t = e(reference) · e(frame_t)`.
6. Aggregate within each clip and then by person. Report median similarity, variation over time, uncertainty and failure rate.
7. Independently assess motion quality, prompt fidelity, pose and expression confounding.

**Never assume one universal similarity threshold.** Report the false-match/false-nonmatch trade-off on calibrated data. Include confidence intervals clustered by identity, not by frame.

## Falsifiable hypotheses

- **H1:** Under at least one baseline I2V configuration, authorised reference portraits result in generated clips with identity similarity distinguishable from impostor controls.
- **H2:** Identity similarity changes with expression, pose, occlusion, and input quality.
- **H3:** The evaluation can detect a change in retention without conflating it with lower video utility.

These hypotheses remain **untested** by FRP.

## Limits

Face embeddings cannot determine whether someone consented. A high score is neither proof of the same real person nor proof of impersonation. Matching errors can vary by demographics and image quality. Results from one model, prompt or recogniser are not universal.

## Safety and reproducibility

Keep portraits, outputs and biometric embeddings out of the public repository. Record provenance, model/weight versions, preprocessing, prompts, seeds, evaluation library revisions and inclusion/exclusion decisions in private controlled records.

## Next step

Implement dataset permission checks and an evaluation-only baseline before attempting any prevention intervention.
