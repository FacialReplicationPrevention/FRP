# Research 005 — Wan model candidates: pinned source verification and comparison

**Date:** 2026-10-30  
**Status:** Static source-code and repository-metadata analysis. No weights downloaded, no code from the inspected repositories executed, no inference run, no identity measured.  
**Milestone:** [#7](https://github.com/FacialReplicationPrevention/FRP/issues/7) (Roadmap Phase 2b); documentation tracker [#4](https://github.com/FacialReplicationPrevention/FRP/issues/4).  
**Machine-readable record:** [`provenance/model-candidates.yaml`](../provenance/model-candidates.yaml), validated offline by `frp provenance` (see [harness guide](../docs/harness.md#model-provenance-inventory-milestone-003)).  
**Builds on:** [Research 003](003-wan21-i2v-architecture.md) and [Research 004](004-conditioning-ablation-design.md); does **not** change the Wan 2.1 A/B/C/D protocol in [Experiment 002](../experiments/002-conditioning-ablation-protocol.md).

## Evidence labels

| Label | Meaning |
| --- | --- |
| **[code]** | Read in source at the pinned commit; permalinks below are fixed to that commit. |
| **[metadata]** | Read from official repository or model-card metadata at a pinned revision (GitHub/Hugging Face APIs, `config.json`, `README.md`) without downloading weights. |
| **[reported]** | Stated by an official README or model card; not checked by FRP (e.g. VRAM figures). |
| **[hypothesis]** | FRP interpretation that needs experiment. |
| **[unknown]** | Not determined. |

"Verified" in this note and in the inventory means *checked by FRP against the cited primary source at a pinned revision*. It does **not** mean that model behaviour, identity effects or any safeguard has been observed.

## Method

1. On 2026-10-30 the current `main` HEAD of each official GitHub repository was recorded via the GitHub API, cloned without blobs, checked out at that SHA, and the files below were read at that SHA. Line numbers refer to the pinned SHA only.
2. Hugging Face model metadata was read through the Hub API at a pinned revision (`/api/models/<repo>/revision/<sha>`: revision, file list, file sizes, platform-reported LFS digests, card licence). Only small text files (`config.json`, `README.md`) were fetched at the pinned revision. No `.safetensors` or `.pth` file was downloaded.
3. Choosing the HEAD at query time is a reproducibility convenience, not a quality judgement. Later upstream changes are not covered.

Reproduce (source and metadata only):

~~~bash
git clone --filter=blob:none --no-checkout https://github.com/Wan-Video/Wan2.1.git
git -C Wan2.1 checkout 9737cba9c1c3c4d04b33fcad41c111989865d315
git clone --filter=blob:none --no-checkout https://github.com/Wan-Video/Wan2.2.git
git -C Wan2.2 checkout 1ea34ff48f87168174e12956e200b1d908b1c5ff
curl -s "https://huggingface.co/api/models/Wan-AI/Wan2.1-I2V-14B-480P/revision/6b73f84e66371cdfe870c72acd6826e1d61cf279?blobs=true"
curl -s "https://huggingface.co/api/models/Wan-AI/Wan2.2-I2V-A14B/revision/206a9ee1b7bfaaf8f7e4d81335650533490646a3?blobs=true"
~~~

## Pinned revisions

| Item | Repository | Pinned revision | Notes [metadata] |
| --- | --- | --- | --- |
| Wan 2.1 source | [Wan-Video/Wan2.1](https://github.com/Wan-Video/Wan2.1/tree/9737cba9c1c3c4d04b33fcad41c111989865d315) | `9737cba9c1c3c4d04b33fcad41c111989865d315` | Commit date 2026-03-05; `main` HEAD on 2026-10-30; Apache-2.0 `LICENSE.txt` |
| Wan 2.2 source | [Wan-Video/Wan2.2](https://github.com/Wan-Video/Wan2.2/tree/1ea34ff48f87168174e12956e200b1d908b1c5ff) | `1ea34ff48f87168174e12956e200b1d908b1c5ff` | Commit date 2026-09-21; `main` HEAD on 2026-10-30; Apache-2.0 `LICENSE.txt` |
| Wan 2.1 I2V 480P checkpoint | [Wan-AI/Wan2.1-I2V-14B-480P](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/tree/6b73f84e66371cdfe870c72acd6826e1d61cf279) | `6b73f84e66371cdfe870c72acd6826e1d61cf279` | Card licence `apache-2.0`; not gated |
| Wan 2.2 I2V A14B checkpoint | [Wan-AI/Wan2.2-I2V-A14B](https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/tree/206a9ee1b7bfaaf8f7e4d81335650533490646a3) | `206a9ee1b7bfaaf8f7e4d81335650533490646a3` | Card licence `apache-2.0`; not gated |
| Wan 2.2 TI2V 5B checkpoint | [Wan-AI/Wan2.2-TI2V-5B](https://huggingface.co/Wan-AI/Wan2.2-TI2V-5B/tree/921dbaf3f1674a56f47e83fb80a34bac8a8f203e) | `921dbaf3f1674a56f47e83fb80a34bac8a8f203e` | Card licence `apache-2.0`; not gated |

**Weight digests:** `not_verified` for every checkpoint. The Hub API reports per-file LFS SHA-256 values at each revision; these are platform-reported expected values, not FRP verification. Local hashing requires an approved download (a later gated step).

## 1. Wan 2.1 I2V re-verification at `9737cba`

### Conditioning trace [code]

| Step | Observation | Evidence |
| --- | --- | --- |
| Input | PIL image → tensor normalised to [-1, 1]; latent grid derived from aspect ratio and `max_area` (from `--size`). The image is not resized here; CLIP and VAE each resize it separately. | [image2video.py L181–L193][w21-pre], [generate.py L429–L432][w21-call] |
| Seed and noise | `seed < 0` is replaced by a random seed; 16 × ((F−1)/4+1) × h × w noise from a seeded CUDA generator. | [L199–L208][w21-seed] |
| Mask | Ones for frame 0, zeros elsewhere; the first frame is repeated 4× and folded into 4 mask channels over latent time. The mask does not depend on image content. | [L210–L217][w21-mask] |
| Text | Positive prompt and negative prompt (config default if empty) encoded by umT5. | [L219–L231][w21-t5] |
| CLIP Vision | `clip_context = self.clip.visual([img[:, None, :, :]])` on the full-resolution image; `visual()` bicubic-resizes to 224 × 224, applies CLIP normalisation and returns features from `use_31_block=True`. Model: open-clip XLM-RoBERTa-large ViT-H/14, fp16. | [L235–L238][w21-clip], [clip.py L527–L542][w21-clipvis], [wan_i2v_14B.py L16–L20][w21-cfg] |
| VAE first frame | Image bicubic-resized to (h, w), concatenated with F−1 zero frames, VAE-encoded; mask prepended on the channel axis: `y = concat([msk, y])`. Zero in the [-1, 1] space is mid-grey, not black. | [L240–L249][w21-vae] |
| Denoiser calls | `arg_c` and `arg_null` share identical `clip_fea` and `y`; only text `context` differs. CFG: `uncond + scale · (cond − uncond)`. | [L284–L296][w21-args], [L308–L319][w21-cfg-calls] |
| Model input | i2v asserts both `clip_fea` and `y`; `y` is channel-concatenated with the noisy latent before patch embedding. | [model.py L523–L531][w21-concat] |
| Image tokens | `img_emb` (MLPProj) projects CLIP features; they are prepended to the text context. Each block's `WanI2VCrossAttention` splits image tokens from the 512 text tokens, attends to each with the same query and sums the results before the output projection. | [model.py L561–L563][w21-ctx], [L202–L229][w21-xattn], [L14][w21-t5n] |
| Output | Final latent is VAE-decoded. | [image2video.py L339–L340][w21-decode] |
| Checkpoint | `config.json`: `model_type: i2v`, `in_dim: 36`, `out_dim: 16`, `dim: 5120`, 40 layers, 40 heads. 36 = 16 latent + 4 mask + 16 VAE channels, consistent with the code. [metadata] | [config.json @ 6b73f84][w21-hfcfg] |

Further observations relevant to FRP [code]:

- **Optional image → text path.** `--use_prompt_extend` (default off) passes the input image to a prompt expander ([generate.py L184–L189][w21-pe-flag], [L392–L400][w21-pe-call]). The default method `local_qwen` runs a local vision-language model; the `dashscope` method calls a remote service. When enabled, the reference image can change the *text* conditioning, and with `dashscope` the image would leave the controlled environment. Experiment 002 does not mention this option.
- **CLI defaults.** For I2V, 40 sampling steps ([generate.py L71–L74][w21-steps]) and `sample_shift = 3.0` at 480P sizes ([L76–L79][w21-shift]); `--frame_num` "should be 4n+1" ([L117–L120][w21-fn]). These are upstream defaults, not FRP choices.
- **Revision sensitivity.** Upstream commit [`841fe52`](https://github.com/Wan-Video/Wan2.1/commit/841fe5237bbf8724e08870b1e83213e669cda0d1) (2025-12-02) changed the mask from a hard-coded 81 frames to `F`. Earlier revisions build a mismatched mask when `frame_num ≠ 81`: a concrete reason to pin.
- **Dependencies.** `requirements.txt` sets lower bounds only (e.g. `torch>=2.4.0`, `transformers>=4.49.0`) and includes `flash_attn` and `dashscope` ([requirements.txt][w21-req]). An FRP execution environment must be frozen separately.

### Corrections to Research 003 line references

Research 003 cited approximate line numbers against moving `main`. Its substantive statements hold at `9737cba`; the locations differ:

| Research 003 statement | Cited | At `9737cba` |
| --- | --- | --- |
| `clip_context = self.clip.visual(...)` | ~216 | 236 |
| First-frame video, VAE `y`, mask | ~192–199, 219–228 | mask 210–217; VAE `y` 240–249 |
| T5 text encoding | ~203–214 | 219–231 |
| Conditional / negative model calls | ~260–271 | argument dicts 284–296; calls 308–319 |
| Sampling loop and decode | ~277–312 | loop 302–332; decode 339–340 |
| `model.py`: `y` channel concat | ~490–493 | 530–531 |
| `model.py`: CLIP projection joins context | ~518–520 | 561–563 |
| `model.py`: `WanI2VCrossAttention` | ~173–211 | 187–229 |
| `model.py`: transformer blocks | ~530–531 | 574–575 |

### What is observed versus hypothesised about identity

- **Observed [code]:** two image-derived inputs reach every denoiser step and both CFG branches: CLIP tokens through a dedicated image cross-attention, and the VAE first-frame latent plus mask through channel concatenation. Neither is a dedicated identity or consent channel. Because both CFG branches receive the same image conditions, guidance contrasts text, not image conditioning.
- **Hypothesis:** the paths contribute differently to identity retention (H3.1, H4.1). The mask marks frame 0 as given, which *may* anchor first-frame likeness via the VAE path; the CLIP path sees a 224 × 224 resize of the whole frame, so a small face *may* contribute few patches. Neither has been tested.
- **Unknown:** where identity information resides in internal activations; whether either path is sufficient alone.

### Applicability of the Wan 2.1 A/B/C/D protocol

- The design's premise holds at this revision [code]: `clip_context` and `y` are computed separately from the same `img`, and the mask, noise, text and sampler do not depend on image content. An executor could therefore supply different source images to the two paths. *Feasibility of that substitution is an inference; no executor exists.*
- Research 004's controls are consistent with the code: the mask is image-independent and both CFG calls share `clip_fea` and `y`.
- **Limitations to record (not protocol changes):**
  1. The two paths resize differently (224² bicubic for CLIP; h × w bicubic for VAE), so one altered image is seen at different resolutions by each path.
  2. Prompt extension must stay disabled or the image also enters through text. **Proposed clarification for review:** record `use_prompt_extend: false` explicitly in a future protocol/manifest revision.
  3. Seeded generation uses a CUDA generator; cross-hardware determinism is unknown.
  4. The `bs x 257` token count appears only as a code comment ([model.py L562][w21-ctx]); FRP has not observed tensor shapes.
- Scope: the protocol applies to Wan 2.1 I2V-14B-480P at this revision only. The provenance validator enforces this (see below).

## 2. Wan 2.2 I2V-A14B at `1ea34ff` (verified independently)

### Conditioning trace [code]

| Step | Observation | Evidence |
| --- | --- | --- |
| Configuration | umT5 text encoder; VAE `Wan2.1_VAE.pth`, stride (4, 8, 8); two DiT experts `low_noise_model` and `high_noise_model`; `boundary = 0.900`; guidance `(3.5, 3.5)` (low, high); 40 steps; shift 5.0. **No CLIP checkpoint or tokenizer is configured.** | [wan_i2v_A14B.py L9–L37][w22-cfg] |
| Components | `WanI2V.__init__` builds T5, `Wan2_1_VAE` and two `WanModel` experts. **No CLIP model is constructed or imported.** | [image2video.py L99–L119][w22-init] |
| Input, seed, mask | Same form as Wan 2.1. | [L259–L296][w22-pre] |
| VAE first frame | Same construction: resized first frame + F−1 zero frames, VAE-encoded, mask prepended. | [L314–L323][w22-vae] |
| Denoiser calls | `arg_c` / `arg_null` hold `context`, `seq_len`, `y` — **no `clip_fea`**. | [L367–L402][w22-args] |
| Expert switch | Timestep `t ≥ 0.9 × 1000` uses the high-noise expert, otherwise the low-noise expert, each with its own guidance scale; `y` is shared by both experts. | [L172–L204][w22-switch] |
| Model | `WanCrossAttention` attends to text only (no image-token split); `y` is channel-concatenated before patch embedding. | [model.py L158–L180][w22-xattn], [L437–L445][w22-concat] |
| Checkpoint | Both experts' `config.json`: `model_type: i2v`, `in_dim: 36`, `out_dim: 16`, `dim: 5120`, 40 layers. No CLIP file in the revision's file list. [metadata] | [high][w22-hi], [low][w22-lo] |
| Prompt extension | Same optional image → VLM → text path. | [generate.py L169–L173][w22-pe-flag], [L380–L387][w22-pe-call] |

**Shared components [metadata, platform-reported]:** the Hub reports identical LFS SHA-256 digests for `Wan2.1_VAE.pth` and `models_t5_umt5-xxl-enc-bf16.pth` in Wan2.1-I2V-14B-480P@`6b73f84` and Wan2.2-I2V-A14B@`206a9ee`. Not verified by local hashing.

### Implications

- **The Wan 2.1 A/B/C/D CLIP × VAE design does not transfer** [code]. There is no CLIP-vision path to alter; the reference image reaches the denoiser only through the VAE first-frame latent and mask (and optionally through prompt extension).
- A Wan 2.2 study would need its own reviewed protocol. Possible directions, recorded only as **hypotheses, not a proposed protocol**: a single-factor original/altered VAE first-frame comparison, and whether the high-noise versus low-noise expert phase matters (which the official code does not expose separately, since `y` is shared).
- If the VAE files are truly identical (to be confirmed by local hashing), the same image would produce the same VAE first-frame latent in both generations, which *could* support a cross-generation comparison of the VAE path [hypothesis].

## 3. Wan 2.2 TI2V-5B at `1ea34ff` (brief) [code]

- Configuration: Wan 2.2 VAE (`Wan2.2_VAE.pth`, stride (4, 16, 16)), `dim` 3072, 30 layers, 121 frames, 24 fps, 50 steps, guidance 5.0 ([wan_ti2v_5B.py][w22-ti2v-cfg]); sizes `704*1280` / `1280*704` only ([configs/\_\_init\_\_.py L46][w22-sizes]). No CLIP.
- Image conditioning differs again: the single input frame is VAE-encoded into `z` ([textimage2video.py L512][w22-ti2v-z]); the first latent frame of the noisy latent is **replaced** by `z` at the start and after every step ([L550–L561][w22-ti2v-init], [L598][w22-ti2v-step]); first-frame tokens receive timestep 0 ([L573–L578][w22-ti2v-ts]). No channel-concatenated `y`. Checkpoint `config.json`: `model_type: ti2v`, `in_dim` = `out_dim` = 48 [metadata].
- A/B/C/D does not apply. This is a third distinct image-conditioning mechanism.

## 4. Inventory of other official and derivative candidates

Only candidates whose existence and access were confirmed through official repositories or Hub metadata are listed. Absence from this list is not a judgement about any model.

| Candidate | Provenance | Confirmed | Not verified |
| --- | --- | --- | --- |
| [Wan-AI/Wan2.1-I2V-14B-720P](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-720P/tree/8823af45fcc58a8aa999a54b04be9abc7d2aac98) | Official | Revision `8823af4…`; card licence Apache-2.0; same `i2v-14B` task and code path ([configs L45–L49][w21-sizes]) | Its `config.json`; conditioning recorded as `pending` |
| [Wan-AI/Wan2.1-I2V-14B-480P-Diffusers](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P-Diffusers/tree/b184e23a8a16b20f108f727c902e769e873ffc73) | Official-org conversion | Revision `b184e23…`; listed in the official README ([README L352–L353][w21-diffusers]) | The `huggingface/diffusers` implementation (separate code, not inspected); lineage |
| [Wan-AI/Wan2.2-Animate-14B](https://huggingface.co/Wan-AI/Wan2.2-Animate-14B/tree/cb93a225fbaf1ca100f54e79da8f994995b689b3) | Official | Revision `cb93a22…`; config references a CLIP checkpoint ([wan_animate_14B.py L13][w22-animate-cfg]); module files named `face_blocks.py` and `motion_encoder.py` exist | Conditioning (file names alone establish nothing). **Directly relevant to identity replication; recommended for a later trace.** |
| [Wan-AI/Wan2.2-S2V-14B](https://huggingface.co/Wan-AI/Wan2.2-S2V-14B/tree/dab4e9c55bbe4c8c4d03db1c2c98c7f0ac9c454b) | Official | Revision `dab4e9c…`; speech-to-video task in the Wan 2.2 repository | Conditioning |
| Wan-AI/Wan2.1-FLF2V-14B-720P, Wan2.1-VACE-1.3B / 14B | Official | Listed under Wan-AI on the Hub | Not inventoried (first-last-frame and editing tasks are outside the current I2V scope) |
| Wan-AI/Wan-Dancer-14B ([Wan-Video/Wan-Dancer](https://github.com/Wan-Video/Wan-Dancer/tree/e6c87a94ec733230dac15b924c015f6e6501e618)), Wan-AI/Wan2.2-Animate-2-14B ([Wan-Video/Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2/tree/3ad2fef7d61d6200c9c653e0fe47be7616b323f3)) | Official | Repositories exist with Apache-2.0 metadata (Hub entries created 2026-07) | Task, architecture, conditioning; not in the YAML inventory |
| [city96/Wan2.1-I2V-14B-480P-gguf](https://huggingface.co/city96/Wan2.1-I2V-14B-480P-gguf/tree/b4b6b3b3f0f64975fb33b1d5d1a46ca24e065f03) | Derivative (quantisation) | Revision `b4b6b3b…`; card declares base model Wan2.1-I2V-14B-480P and licence apache-2.0 | Lineage, conversion code, conditioning |
| [lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v](https://huggingface.co/lightx2v/Wan2.1-I2V-14B-480P-StepDistill-CfgDistill-Lightx2v/tree/9bedb7ceaf40d43b47d892382612ff157ca15c52) | Derivative (distillation) | Revision `9bedb7c…`; declared base model and apache-2.0; LightX2V is listed in the official README's community works ([README L41][w21-community]) | Lineage, training, conditioning |
| Kijai/WanVideo_comfy | Derivative (repackaged collection) | Exists; the wrapper project is listed in the Wan 2.2 README ([README L56][w22-community]) | No licence in card metadata; mixed contents. Not inventoried |

**Newer generations.** As of 2026-10-30 no repository for a Wan generation after 2.2 was found under the `Wan-AI` Hub organisation or the `Wan-Video` GitHub organisation. FRP makes no claim about the existence, licensing or openness of later Wan generations.

**Declared base models** are self-reported card metadata, not verified lineage; the inventory records them as `pending`.

## 5. Comparison matrix

Execution figures are either Hub-reported file sizes [metadata] or official README statements [reported]. Complexity is an **FRP qualitative judgement**, not a measurement.

| | Wan2.1-I2V-14B-480P | Wan2.2-I2V-A14B | Wan2.2-TI2V-5B | Derivatives (city96, lightx2v) |
| --- | --- | --- | --- | --- |
| Provenance | Official | Official | Official | Community, declared base Wan2.1-I2V-14B-480P |
| Source @ commit | Wan-Video/Wan2.1 @ `9737cba` | Wan-Video/Wan2.2 @ `1ea34ff` | Wan-Video/Wan2.2 @ `1ea34ff` | Unknown |
| Checkpoint @ revision | `6b73f84` | `206a9ee` | `921dbaf` | `b4b6b3b`, `9bedb7c` |
| Licence | Apache-2.0 (repo + card) [metadata]; research-use review pending | Apache-2.0 [metadata]; review pending | Apache-2.0 [metadata]; review pending | apache-2.0 card metadata; pending |
| Image conditioning | CLIP Vision → image cross-attention; VAE first frame + mask → channel concat; optional prompt extension [code] | VAE first frame + mask → channel concat only; optional prompt extension [code] | First-latent-frame replacement with timestep-0 tokens; optional prompt extension [code] | Not inspected |
| Denoiser | One 14B DiT (`dim` 5120, 40 layers) | Two 14B experts switched at t = 900 | One 5B DiT (`dim` 3072, 30 layers) | Unknown |
| Weight storage at revision [metadata] | DiT ≈ 65.6 GB (7 shards) + T5 ≈ 11.4 GB + CLIP ≈ 4.8 GB + VAE ≈ 0.5 GB | Each expert ≈ 57.2 GB (6 shards) + T5 + VAE; repository LFS total ≈ 126 GB | Repository LFS total ≈ 34 GB | Not recorded |
| GPU memory | README figures are given as an image; FRP did not transcribe them → **unknown** | "at least 80GB VRAM" for the single-GPU example with offload and dtype conversion ([README L196–L201][w22-vram]) [reported] | "at least 24GB VRAM" with offload, dtype conversion and T5 on CPU ([README L228–L234][w22-ti2v-vram]) [reported] | Unknown |
| Dependencies | `torch>=2.4.0`, `flash_attn`, `transformers>=4.49.0`, … (lower bounds only) | Same family; `transformers<=4.51.3` upper bound | As Wan 2.2 | Unknown |
| Practical complexity (qualitative) | Moderate: single DiT; two explicit, separately computed image inputs; protocol exists | Higher: twice the DiT storage, expert switching, no protocol | Lower compute per README, but different mechanism and fixed 704p / 121-frame defaults | Unknown provenance; not an unmodified checkpoint |
| Confidence / unknowns | High for code path; weight hashes, runtime, determinism unknown | High for code path; weight hashes, runtime unknown | Medium (brief trace) | Low |
| Relevance to FRP | Reference baseline for the existing CLIP × VAE ablation | Newer generation; tests whether conclusions about the VAE path generalise | Possible low-cost smoke target, separate protocol | Threat model: wider access, potential bypass of model-level mitigations |

## 6. Identity retention, permissiveness and authorisation

These are separate properties and must not be conflated:

- **(a) Identity retention** — how strongly a reference identity persists in generated video. Depends on conditioning paths and weights; FRP's planned measurements target this. Nothing about it has been measured.
- **(b) Permissiveness / content filtering** — what content a model will produce. A keyword search of the traced I2V/TI2V code paths at the pinned commits found no image-content filter or safety checker [code, traced files only; the repositories were not fully audited]. Usage restrictions appear as model-card licence text, which places responsibility on the user [metadata].
- **(c) Authorisation** — whether the depicted person consented. No inspected component carries or checks consent; neither conditioning path is a consent signal.

**Threat-model implications of derivatives.** Quantised and distilled derivatives lower hardware requirements and therefore broaden who can run identity-preserving I2V. Community fine-tunes or LoRA merges may change (b) — for example by relaxing content restrictions — without any change to (a), and could also undo a future model-level mitigation applied to official weights. An unmodified official checkpoint also remains available. Any FRP mitigation claim would therefore need evaluation against adaptation of the protected weights (Phase 6) and would not cover unrelated models. FRP did **not** search for, download or test NSFW or other explicit-content checkpoints, and initial experiments remain neutral, consented and non-explicit.

## 7. Recommendation and decision gate

**Initial reproducible baseline (recommendation, not authorisation):** `Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279` with `Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`.

- Its verified conditioning matches the existing reviewed A/B/C/D protocol and the harness's result protocol `wan2.1-i2v-clip-vae-2x2`.
- Single DiT; two separately computed image inputs that an executor could substitute independently.
- Apache-2.0 licence metadata; pinned Hub revision recorded; declared as the base model by both inventoried derivatives (card metadata), so baseline findings are relevant to the wider ecosystem.

**Optional later candidate:** `Wan-AI/Wan2.2-I2V-A14B` @ `206a9ee1b7bfaaf8f7e4d81335650533490646a3` with `Wan-Video/Wan2.2` @ `1ea34ff48f87168174e12956e200b1d908b1c5ff`. It shares the VAE first-frame mechanism (and, per platform-reported digests, the VAE file) but has no CLIP path, uses two experts and roughly 1.5× the repository storage. It needs a separately proposed and reviewed protocol.

**Still unverified:**

1. SHA-256 of every weight file (requires an approved download and local hashing).
2. GPU memory, runtime and cost of Wan2.1-I2V-14B-480P on any specific hardware.
3. Determinism of seeded generation across GPUs, drivers and attention backends.
4. A frozen dependency set (upstream specifies lower bounds only).
5. Human review of licence terms and permitted research use (model-card text includes obligations about harm and personal information).
6. Equivalence of the Diffusers implementation; conditioning of Animate and S2V models.
7. That a real executor substituting CLIP or VAE inputs preserves every other control (Experiment 002 Gate 1 instrumentation).

**Decision gate (no GPU).** Nothing in this note authorises downloads, GPU rental or experiments. Before Phase 3: (1) review of this note and the inventory; (2) human licence and research-use review; (3) consent, private storage and retention procedures; (4) an approved GPU quote and shutdown policy; then (5) a separately scoped issue for weight download, local hashing and a metadata-only smoke test.

## Machine-readable inventory and protocol guard

[`provenance/model-candidates.yaml`](../provenance/model-candidates.yaml) records every candidate above with explicit `verified` / `pending` / `not_verified` / `unknown` statuses and pinned evidence links. `frp provenance` validates it offline and rejects, among other things: `verified` claims without pinned evidence, evidence whose path revision or repository differs from the claimed one (a matching SHA in a query string does not count), verified conditioning evidence not at the pinned commit, any `verified` weight digest, duplicate candidates, and declaring `wan2.1-i2v-clip-vae-2x2` on anything other than the official Wan2.1-I2V-14B-480P checkpoint with verified CLIP and VAE paths. Independently, the Wan 2.1 experiment manifest fails closed: `frp plan` and `frp simulate` reject a manifest naming any source other than `Wan-Video/Wan2.1` or any checkpoint other than `Wan-AI/Wan2.1-I2V-14B-480P`. Validation proves internal consistency only; the links must be reviewed by a person.

## Sources

- Wan-Video, [Wan2.1 @ 9737cba](https://github.com/Wan-Video/Wan2.1/tree/9737cba9c1c3c4d04b33fcad41c111989865d315) and [Wan2.2 @ 1ea34ff](https://github.com/Wan-Video/Wan2.2/tree/1ea34ff48f87168174e12956e200b1d908b1c5ff) (Apache-2.0).
- Wan-AI model cards at the revisions listed above (Hugging Face).
- Wan Team, [Wan: Open and Advanced Large-Scale Video Generative Models (arXiv:2503.20314)](https://arxiv.org/abs/2503.20314) — background only; no claim in this note depends on it.

[w21-pre]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L181-L193
[w21-call]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L429-L432
[w21-seed]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L199-L208
[w21-mask]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L210-L217
[w21-t5]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L219-L231
[w21-clip]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L235-L238
[w21-clipvis]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/clip.py#L527-L542
[w21-cfg]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/wan_i2v_14B.py#L16-L20
[w21-vae]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L240-L249
[w21-args]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L284-L296
[w21-cfg-calls]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L308-L319
[w21-concat]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/model.py#L523-L531
[w21-ctx]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/model.py#L561-L563
[w21-xattn]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/model.py#L202-L229
[w21-t5n]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/model.py#L14
[w21-decode]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L339-L340
[w21-hfcfg]: https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/6b73f84e66371cdfe870c72acd6826e1d61cf279/config.json
[w21-pe-flag]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L184-L189
[w21-pe-call]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L392-L400
[w21-steps]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L71-L74
[w21-shift]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L76-L79
[w21-fn]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L117-L120
[w21-req]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/requirements.txt
[w21-sizes]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/__init__.py#L45-L49
[w21-diffusers]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/README.md?plain=1#L352-L353
[w21-community]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/README.md?plain=1#L41
[w22-cfg]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/configs/wan_i2v_A14B.py#L9-L37
[w22-init]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/image2video.py#L99-L119
[w22-pre]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/image2video.py#L259-L296
[w22-vae]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/image2video.py#L314-L323
[w22-args]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/image2video.py#L367-L402
[w22-switch]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/image2video.py#L172-L204
[w22-xattn]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/modules/model.py#L158-L180
[w22-concat]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/modules/model.py#L437-L445
[w22-hi]: https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/blob/206a9ee1b7bfaaf8f7e4d81335650533490646a3/high_noise_model/config.json
[w22-lo]: https://huggingface.co/Wan-AI/Wan2.2-I2V-A14B/blob/206a9ee1b7bfaaf8f7e4d81335650533490646a3/low_noise_model/config.json
[w22-pe-flag]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/generate.py#L169-L173
[w22-pe-call]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/generate.py#L380-L387
[w22-ti2v-cfg]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/configs/wan_ti2v_5B.py#L8-L36
[w22-sizes]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/configs/__init__.py#L46
[w22-ti2v-z]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/textimage2video.py#L512
[w22-ti2v-init]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/textimage2video.py#L550-L561
[w22-ti2v-step]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/textimage2video.py#L598
[w22-ti2v-ts]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/textimage2video.py#L573-L578
[w22-animate-cfg]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/wan/configs/wan_animate_14B.py#L13
[w22-community]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/README.md?plain=1#L56
[w22-vram]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/README.md?plain=1#L196-L201
[w22-ti2v-vram]: https://github.com/Wan-Video/Wan2.2/blob/1ea34ff48f87168174e12956e200b1d908b1c5ff/README.md?plain=1#L228-L234
