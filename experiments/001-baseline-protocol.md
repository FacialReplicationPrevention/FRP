# Experiment 001 — Baseline identity preservation

**Date:** 2026-10-29  
**Status:** Design only; no experiment has been executed.

## Objective

Establish reference-to-output identity similarity distributions in a benign, authorised image-to-video scenario before introducing a safeguard.

## Dataset and ethics

Only use adults giving informed, specific consent or data for which the licence and usage permissions have been verified. Do not publish identifiable images, output videos or face embeddings without specific permission. Avoid minors, sexual impersonation, defamatory content and covert identity-matching of uninvolved people.

## Preregistration

Record the model and weight hash, inference commit, software versions, GPU, generation resolution, prompt templates, number of seeds, reference selection, frame sampling and face-embedding evaluator before inspecting results.

## Procedure

1. Gather authorised portraits and separate same-person and different-person calibration pairs.
2. Split identity-disjoint calibration and evaluation sets.
3. Select error-rate operating points on calibration data, not test data.
4. Generate neutral, benign motion-only clips without additional identity adapters.
5. Sample frames using a fixed rule; preserve face detection failures as missing measurements with explicit counts.
6. Compute calibrated similarity distributions and motion/prompt quality metrics.
7. Aggregate first by video, then identity; compute identity-clustered intervals.
8. Report all pre-registered conditions, subgroup limitations and unsuccessful runs.

## Primary outcomes

- Face embedding similarity distribution against calibration controls.
- Match/nonmatch error rates at specified thresholds.
- Usable face detection rate.
- Frame-by-frame drift in similarity.
- Per-identity variability and uncertainty.

## Secondary outcomes

Video quality, realism, motion fidelity, prompt fidelity, runtime and compute cost.

## Advance criteria

Proceed to intervention testing only when results reproduce under fixed configurations and the evaluation includes uncertainty, failure rates, confounders and all attempted runs. No FRP efficacy claim should be made before comparing a fixed baseline with an intervention under matching conditions.

## References

- [Wan2.1](https://github.com/Wan-Video/Wan2.1)
- [ArcFace](https://openaccess.thecvf.com/content_CVPR_2019/html/Deng_ArcFace_Additive_Angular_Margin_Loss_for_Deep_Face_Recognition_CVPR_2019_paper.html)
- [NIST FRTE demographic effects](https://pages.nist.gov/frvt/html/frvt_demographics.html)
