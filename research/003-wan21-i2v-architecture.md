# Research 003 — Wan 2.1 image-to-video conditioning architecture

**Date:** 2026-10-29  
**Status:** Source-code analysis; intervention hypotheses untested  
**Target:** Official Wan2.1 I2V inference, not Wan2.2, VACE or third-party ComfyUI variants.

> **Scope and pinned re-check (2026-10-30).** All conclusions in this note are **Wan 2.1 I2V-specific** and must not be generalised to other models: Wan 2.2 I2V-A14B, for example, has no CLIP-vision path ([Research 005](005-wan-model-candidates.md#2-wan-22-i2v-a14b-at-1ea34ff-verified-independently)). The trace was re-checked at pinned commit `9737cba9c1c3c4d04b33fcad41c111989865d315`. Its substantive statements hold, but the approximate line numbers below refer to an unrecorded `main` revision and are superseded by the pinned permalinks and [correction table in Research 005](005-wan-model-candidates.md#corrections-to-research-003-line-references). The body of this note is otherwise unchanged.

## Research question

Where does a reference photograph influence Wan2.1 video generation, and which points are candidates for measuring or reducing identity retention?

## Primary sources

- [Wan technical report (arXiv:2503.20314)](https://arxiv.org/abs/2503.20314)
- [Wan2.1 official repository](https://github.com/Wan-Video/Wan2.1)
- [wan/image2video.py](https://github.com/Wan-Video/Wan2.1/blob/main/wan/image2video.py)
- [wan/modules/model.py](https://github.com/Wan-Video/Wan2.1/blob/main/wan/modules/model.py)

**Reproducibility note:** Links above target the upstream `main` branch. Before instrumenting or citing line-specific behaviour in experiments, freeze an upstream commit SHA and model weight hashes; files can change.

## Confirmed implementation observations

### Two image-conditioning routes

In `WanI2V.generate` (`wan/image2video.py`):

1. Image preprocessing converts the input to a normalised tensor and determines target geometry from aspect ratio.
2. The CLIP vision encoder computes `clip_context = self.clip.visual(...)` (around line 216).
3. Independently, the code builds a video tensor comprising the resized input first frame and zero-valued subsequent frames. The VAE encodes it into `y`; a first-frame mask is concatenated to `y` (around lines 192–199 and 219–228).
4. Text is encoded by T5 (around lines 203–214).
5. The denoiser receives `context`, `clip_fea`, and `y` in both conditional and negative-prompt model calls (around lines 260–271). Only text context differs in the shown classifier-free-guidance calls.
6. The sampling loop iteratively updates video latents, which are VAE-decoded into output frames (around lines 277–312).

In `wan/modules/model.py`:

- The forward pass concatenates the conditional video input `y` with the current latent `x` **along the channel dimension**, before 3D patch embedding (around lines 490–493).
- `MLPProj` projects CLIP image features; these tokens are concatenated with text context (around lines 518–520).
- `WanI2VCrossAttention` separates image and text tokens, computes separate attention outputs, adds them, and applies an output projection (around lines 173–211).
- The model applies transformer blocks repeatedly (around lines 530–531), so the influence of inputs may become distributed through internal activations.

**Interpretation:** Wan2.1 I2V uses at least two visually informative conditioning routes: first-frame video latents/mask and CLIP image features. Neither is a dedicated biometric consent or face-identity channel. The source code **does not demonstrate** that identity resides exclusively within either route.

## Simplified data flow

```text
Reference portrait
    |------------------------------|
    v                              v
CLIP Vision                   First-frame + zero frames
    |                              |
Image tokens                  Video VAE -> latents + mask
    |                              |
MLP projection                     |
    |                              |
I2V cross-attention            Channel concatenation
    |                              |
    |----------- DiT --------------|
                  ^
             T5 text tokens
                  |
       Iterative latent sampling
                  |
               VAE decode
                  |
             Generated video
```

This diagram is an explanatory simplification of the code; it does not indicate that the two paths carry independent or separable identities.

## Consequences for FRP

**Finding A — A single-path image filter is insufficient evidence of protection.** Modifying CLIP features alone leaves the VAE first-frame condition present. Modifying the VAE condition alone leaves CLIP image features present.

**Finding B — Identity and general appearance may be entangled.** Removal of identity-relevant information may also damage clothing, background, pose, subject consistency and video quality.

**Finding C — Inference wrappers are bypassable.** In an open-weight local deployment, operators can modify the runtime. Any claim of universal unremovable safeguards is unsupported.

**Finding D — Consent cannot be inferred from either pathway.** External permission/policy information would be required for authorisation decisions.

## Hypotheses requiring experimentation

- H3.1: The two image-conditioning pathways contribute differently to output identity retention.
- H3.2: Neutralising either route alone will not consistently eliminate recognisable likeness when the other route remains.
- H3.3: Unselective interference with both routes will degrade legitimate video utility.
- H3.4: A more selective, trained or otherwise constrained intervention may achieve a more favourable privacy–utility trade-off than crude ablation.

These are **FRP hypotheses, not results**.

## Proposed study: conditioning-route ablation

Only with consented adult reference identities and benign motion prompts:

| Variant | CLIP branch | First-frame VAE branch | Purpose |
| --- | --- | --- | --- |
| A | Original | Original | Frozen baseline |
| B | Controlled neutral input | Original | Approximate CLIP contribution |
| C | Original | Controlled neutral input | Approximate VAE contribution |
| D | Controlled neutral input | Controlled neutral input | Combined dependence / utility penalty |

Ablations must respect tensor shape, scale and model expectations. Zeroing an embedding is generally **out of distribution** and may produce failure unrelated to identity. A neutral substitute may alter scene/subject information; therefore comparisons must not be interpreted as causal proof of facial-identity localisation. Record all controls and interpret results cautiously.

Evaluate:
- Identity similarity using independently calibrated face embeddings and detection-failure rates.
- Temporal drift, frame-level variation and confidence intervals clustered by identity.
- Motion quality, scene fidelity, subject quality and prompt adherence.
- Differences between first-frame similarity (potential anchor effect) and later generated frames.
- Fixed seeds, generation settings, frozen model/checkpoint hashes and independent evaluation model.

## Avoid premature claims

The source code establishes *where image information enters*, not which activations specifically encode a real person's identity. We have not executed an ablation, measured reductions, established thresholds, or demonstrated a prevention mechanism.

## Next milestone

1. Freeze the upstream Wan2.1 revision and choose a specific I2V checkpoint.
2. Build a minimal read-only instrumentation plan: record tensor metadata (shape, dtype, layer names), not raw face tensors.
3. Define a consented/permission-verified benchmark and baseline generation protocol.
4. Only then compare route-level ablations and report identity **and** utility effects.
