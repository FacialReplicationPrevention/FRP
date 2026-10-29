# Research 002 — CID feasibility and threat model

**Date:** 2026-10-29  
**Status:** Untested architectural hypothesis.

## Aim

Investigate whether a model-level intervention can reduce unauthorised replication of recognisable facial features in generative image-to-video systems.

## Proposed CID layers

1. **Identity-related representation:** assess facial characteristics in reference inputs and outputs.
2. **Context and permission gate:** determine whether requested use is authorised using external, verifiable permission information where available. Facial geometry and text prompts alone cannot establish consent.
3. **Generation intervention:** test whether a conditioned model can reduce identity retention while preserving benign motion and visual quality.

These are proposed research components, not established or mathematically guaranteed mechanisms.

## Threat model

**Asset:** a person's recognisable likeness and control over its use.

**Attacker:** can obtain a publicly available portrait, run open weights locally, modify prompts and preprocessing, alter inference code, and potentially fine-tune weights.

**Failure:** a recognisable synthetic depiction is produced without permission.

**Trust boundaries:** source files, identity or image encoders, model conditioning, model weights, external permission registry, runtime controls, and independent evaluation.

## Candidate approaches

- **Image-side perturbation:** research such as [PhotoGuard (ICML 2023)](https://proceedings.mlr.press/v202/salman23a.html) explores adversarial protection of images against certain editing pipelines; such approaches cannot be assumed robust against alternative or modified models.
- **Inference-time refusal:** policy gates in cooperative systems; readily removable by a local operator controlling the runtime.
- **Conditioning intervention:** suppress identity-related signals at an identified entry point. Unknown whether identity is sufficiently separable to do this without substantial quality loss.
- **Training-time objectives:** optimise a model to avoid some prohibited identity reconstructions. Potentially more intrinsic than a wrapper but not guaranteed against modification or fine-tuning.

## Research questions

1. Which Wan I2V components transfer the reference face to output frames?
2. Is identity information concentrated in a controllable signal or distributed through pixels and internal features?
3. Which intervention causes measurable changes against a frozen baseline?
4. What is lost in legitimate generation quality?
5. Can resizing, crop, screenshot, alternate pipelines or model modification bypass the proposed safeguard?
6. What independent system could establish explicit permission without constructing a public biometric identification registry?

## Current conclusion

A general guarantee that open-weight models cannot reproduce a person is not justified. The narrower and testable aim is measurable reduction of identity reproduction under documented conditions.

## Research classification

Future notes must label statements as **external published evidence**, **FRP replication**, **FRP measured result**, or **unverified hypothesis**.
