# External evidence delta and private Linux environment specification — Wan 2.1 I2V-14B-480P (Milestone 004, PR 3E)

**Status: PLANNING ONLY. NOT AUTHORISED. NO GPU / NO WEIGHTS / NO REAL MEDIA / NO INFERENCE.**
Nothing here has been rented, bought, downloaded, hashed, built, pulled, loaded, run or approved; no vendor was contacted and
no account exists. All seven gates in the [GPU readiness protocol](gpu-readiness.md) stay **pending**;
`readiness/wan21-i2v-baseline.yaml` and `provenance/model-candidates.yaml` are unchanged (`not_ready`). A rate card is not a
quote, a Hub-reported hash is not a local hash, a specification is not an image, and a merged PR is not an approval.

**Issue:** [#20](https://github.com/FacialReplicationPrevention/FRP/issues/20) (parent [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)
stays open; [#14](https://github.com/FacialReplicationPrevention/FRP/issues/14) stays blocked). **Builds on, and does not repeat,** the merged
[PR 3D dossier](gpu-go-no-go-dossier.md) (§1–§11; [PR #19](https://github.com/FacialReplicationPrevention/FRP/pull/19), Ada final re-review: ready as a
planning-only PR). Section numbers `D§n` below refer to that dossier. **Pins (unchanged):** `Wan-Video/Wan2.1` @
`9737cba9c1c3c4d04b33fcad41c111989865d315`; `Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`.

## 0. Evidence labels (defined before retrieval)

The dossier's labels (D§0) are reused; the right-hand column maps this document's labels onto them. Nothing is **FRP-MEASURED**.

| Label (this document) | Meaning | Dossier label |
| --- | --- | --- |
| **PRIMARY-PINNED** | Read by this PR's author at the exact commit/revision from the owning host, on the stated date | `[source]` / `[metadata]` |
| **PRIMARY-VENDOR** | Official vendor material with a stated date and scope. A list rate or document statement, never a quote | (upgrade of `[vendor-snippet]`) |
| **PRIOR-RETRIEVAL** | Read from the owning host by an *earlier* FRP document at a pinned revision; **not re-checked on 2026-11-04** | `[metadata]` |
| **UPSTREAM-REPORTED** | Stated by the model authors; not reproduced by FRP | `[upstream-reported]` |
| **SECONDARY** | Third-party aggregator/blog/search snippet; may be stale or wrong | `[secondary]` / `[vendor-snippet]` |
| **UNVERIFIED** | Not checked against a primary source; or untested on hardware (compatibility claims) | `UNVERIFIED` |
| **PROPOSED** | FRP suggestion for a human to accept, change or reject | `PROPOSED` |
| **FRP-MEASURED** | Measured by FRP on real hardware. **None exists.** | `[FRP-measured]` |
| **HUMAN-PENDING** | A human decision or private record that does not exist | `PENDING` |

Three distinctions that this document never blurs: (a) a **Hub-reported identifier/SHA-256** (platform metadata; the pinned tree is Xet-backed, so LFS-style SHA-256 availability is unconfirmed) ≠ a **Git blob id**
(SHA-1 identifier of an ordinary Git-tracked file) ≠ a **locally computed SHA-256** (only after an approved download; none exists) ≠ a **private
expected-digest manifest** (reviewed outside this repository); (b) a **public list rate** ≠ a **dated quotation** (none); (c) **published host
specification** ≠ **demonstrated fit** (nothing has been run).

## 1. Retrieval log (2026-11-04)

Retrieval time: 2026-11-04 ≈ 12:10 UTC. Agent environment: Linux sandbox, DNS-restricted. Only metadata/text was fetched; no model file, LFS
object, container image or wheel was downloaded, and the checkpoint repository was not cloned.

| Route | Result | Consequence |
| --- | --- | --- |
| `github.com`, `raw.githubusercontent.com`, GitHub API | **Reachable** | Pinned-source and vendor-docs-source evidence below |
| `huggingface.co` (tree page and raw model card at `6b73f84…`), tried with two independent fetch tools | **Failed** (`No address associated with hostname`) | Model card, Hub tree, file counts, LFS digests and Git blob ids are **UNVERIFIED today**; route stopped, no mirror or `main` substituted |
| `lambda.ai`, `docs.lambda.ai`, `runpod.io` (marketing/pricing), `aws.amazon.com`, `docs.aws.amazon.com` | **Failed** (same) | All rates, regions, host specs and legal pages remain **SECONDARY/UNVERIFIED** unless noted in §4 |
| `docs.runpod.io` source repository `runpod/docs` on GitHub | Reachable; read at commit `bb50dd3e90ddb2dfedf2d0c89fa8ed3feeadd01f` (committed 2026-11-03T19:04:18Z) | **PRIMARY-VENDOR** for Runpod documentation *text* only (rendered pages not opened; prices are not in the docs) |
| AWS documentation repositories on GitHub | Archived since June 2023 | Too old to support any 2026 claim; not used |
| Lambda documentation source | No official public source repository found | Unavailable to the author; Ada independently read Lambda's official pages (see below) |

**Separately attributed independent retrieval (Ada review of this PR, 2026-11-04; read-only public browsing; recorded here from the review comment, not re-performed by the PR author).** Ada reached
the pinned Hugging Face [README](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/6b73f84e66371cdfe870c72acd6826e1d61cf279/README.md),
[file tree](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/tree/6b73f84e66371cdfe870c72acd6826e1d61cf279) and
[LICENSE.txt](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/6b73f84e66371cdfe870c72acd6826e1d61cf279/LICENSE.txt), plus Lambda's official
[pricing](https://lambda.ai/instances) and [on-demand docs](https://docs.lambda.com/public-cloud/on-demand/). The author's own sandbox failures above stand unchanged; they are not
contradicted, and nothing here implies the author's retrieval succeeded. A full recursive inventory was **not** completed, no checkpoint hash was verified, and no licence use is approved.

A chat/search answer is not used as a citation anywhere in this document.

## 2. Evidence-delta table

"3D" = state in the merged dossier. "Today" = what this PR could add. Nothing in this table approves a gate.

| # | Assertion | 3D state | Today (2026-11-04) | Residual action (HUMAN/operator) |
| --- | --- | --- | --- | --- |
| E1 | Source licence is Apache-2.0 and what the README adds | PRIMARY-PINNED read 2026-11-03 | Re-read; unchanged. `LICENSE.txt` SHA-256 recorded (§3.1) | Gate 1 human review |
| E2 | Checkpoint **model card** text, licence statements, gating | Not retrieved | **Author: not retrieved** (Hub unreachable). **Ada (independent, 2026-11-04): pinned card has `license: apache-2.0` and a License Agreement/accountability paragraph; pinned `LICENSE.txt` read.** Earlier `apache-2.0`/not-gated record: PRIOR-RETRIEVAL (Research 005, 2026-10-30) | Qualified human licence review of card and `LICENSE.txt` (§3.4); gate 1 stays pending |
| E3 | Hub file inventory (count, names, sizes, LFS SHA-256, Git blob ids) | Sizes ≈ 82.3 GB (sum of Research 005 approximate sizes), no count | **Author: not retrieved.** **Ada: pinned tree shows 82.3 GB and top-level file names/sizes; no complete recursive inventory.** Hashes remain unverified. Adds a source-derived *minimum* list of 20 files the adapter requires (§3.2) | Complete recursive metadata-only inventory, then private expected-digest process (§3.3) |
| E4 | Dependencies, Python/torch/flash-attn requirements | `requirements.txt` read | New: `requirements.txt` SHA-256; `pyproject.toml` Python range; flash-attn is optional at import with an SDPA fallback; PyTorch CUDA matrix; flash-attn wheel *names* (§5) | Frozen, hashed lock built later (§5.2) |
| E5 | Vendor rates, regions, host RAM, scratch | SECONDARY / snippets | **Author: vendor sites unreachable.** **Ada: Lambda official pricing lists 1× H100 PCIe 80 GB, 26 vCPU, 225 GiB RAM, 1 TiB SSD at USD $3.29/GPU-hour plus tax (retrieved 2026-11-04; the docs' SKU specs table is dated "as of December 2025"); Lambda ODC docs cover VM instances, root storage, NFS filesystems, regions and base images.** Scoped PRIMARY-VENDOR for Lambda, not an accepted quote or regional availability. Runpod rates remain SECONDARY. Runpod docs text gives billing/storage/isolation facts only | Operator re-reads vendor pages and records privately |
| E6 | Runpod billing, low-balance and storage semantics | Snippets | **PRIMARY-VENDOR** (docs source): confirmed prepaid credits, 5-minute billing, $0 behaviour; **new** default $80/h spend limit, minimum one-hour balance, auto-pay cadence, stopped-pod storage rates (§4.1) | Written vendor confirmation (§4.4) |
| E7 | Lambda terminate/no-egress-fee/NFS/no spend limit | Snippets | Partly covered by Ada's reading of Lambda's official pricing and ODC docs (VM instances, root storage, NFS filesystems; scope per §1): treat NFS and published-list claims as scoped PRIMARY-VENDOR. Termination semantics, no-egress-fee wording and the absence of a spend limit remain **UNVERIFIED** (not confirmed in Ada's summary) | Operator re-reads the official pages and records privately |
| E8 | AWS Budgets lag, `p5.4xlarge` rate | Snippets / SECONDARY | Unchanged, **UNVERIFIED**; AWS docs on GitHub are archived and unusable | P3 not refreshed here |
| E9 | Linux environment (torch/CUDA/flash-attn/ffmpeg, directories, network phases) | Risk R9 only | New specification §5 (all PROPOSED; compatibility UNVERIFIED on hardware) | Private build and record |
| E10 | Windows/Docker bind-mount caveat | Not addressed | §6 | Operator attestation |
| E11 | Paper-only external controls (watchdog, drills, custody) | D§3.2, §5 | Consolidated and sharpened in §7, incl. a Runpod-docs observation about in-guest stop timers | Private runtime owner |
| E12 | 480P VRAM/time, host-RAM fit | 720P upstream figure only | No new data (§4.3) | Gate 7 measurement only |

## 3. Pinned source and checkpoint-repository evidence

### 3.1 `Wan-Video/Wan2.1` @ `9737cba…` — PRIMARY-PINNED (GitHub, read 2026-11-04; commit date 2026-03-05T09:38:07Z)

| Item | Fact at the pin | Pinned reference |
| --- | --- | --- |
| Licence file | Apache License 2.0 text; file SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` (hash of this public upstream file only) | [`LICENSE.txt`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/LICENSE.txt) |
| README licence statement | "The models in this repository are licensed under the Apache 2.0 License. We claim no rights over the your generated contents … You are fully accountable for your use of the models, which must not involve sharing any content that violates applicable laws, causes harm to individuals or groups, disseminates personal information intended for harm, spreads misinformation, or targets vulnerable populations." Refers to the full text of the licence for restrictions | [`README.md` L663–L664](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/README.md?plain=1#L663-L664); file SHA-256 `3bdaca69aa116222a49859dc21d4a735b60a580af7e1b81531085c87227e4486` |
| Upstream download instruction | README shows downloading the **whole** model repository with the Hub CLI (L120–L123, shown for the T2V-14B checkpoint). FRP must not run this from CI or an unapproved host; see gate 6 | [README L120–L129](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/README.md?plain=1#L120-L129) |
| Python / torch / dependency ranges | `requires-python >=3.10,<4.0`; `torch>=2.4.0`, `torchvision>=0.19.0`, `numpy>=1.23.5,<2`, `transformers>=4.49.0`, `diffusers>=0.31.0`; **all lower bounds, none exact**; includes `dashscope` (remote client, must stay unused), `gradio`, `flash_attn`, `imageio-ffmpeg`. `requirements.txt` SHA-256 `70b8bd1018b0465ddcb2525da541302fd713b4d39c26e3a833fb549262d99251` | [`requirements.txt`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/requirements.txt), [`pyproject.toml` L14–L29](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/pyproject.toml#L14-L29) |
| Checkpoint file names the code opens | `models_t5_umt5-xxl-enc-bf16.pth`, `models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth`, `Wan2.1_VAE.pth`; tokenizer names `google/umt5-xxl` and `xlm-roberta-large` (resolved under the checkpoint directory in FRP's offline adapter) | [`wan_i2v_14B.py` L13–L23](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/wan_i2v_14B.py#L13-L23) |
| dtypes | T5 `bfloat16`, DiT `bfloat16`, CLIP `float16` | [`shared_config.py`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/shared_config.py), `wan_i2v_14B.py` L18 |
| `flash_attn` is optional at import | Tries FlashAttention 3, then 2; otherwise falls back to `scaled_dot_product_attention` with a warning that the **padding mask is disabled** (a numerics/performance difference) | [`attention.py` L4–L14, L148–L175](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/attention.py#L4-L14) |
| Weight loading | Three `.pth` loads via `torch.load` without `weights_only` (see the runtime docstring and runbook §5); torch ≥ 2.6 required by FRP | `wan/modules/t5.py` L496, `vae.py` L614, `clip.py` L519 |

These statements are **source observations**, not observed FRP behaviour.

### 3.2 `Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84…` — author retrieval failed; Ada's independent read-only retrieval is recorded separately; hashes UNVERIFIED

Author's requests were **not retrievable** on 2026-11-04 (DNS refusal, two tools); Ada's independent retrieval of the same pinned pages is recorded in §1:
<https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/tree/6b73f84e66371cdfe870c72acd6826e1d61cf279> and
<https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/raw/6b73f84e66371cdfe870c72acd6826e1d61cf279/README.md>.

| Item | Status | What is and is not known |
| --- | --- | --- |
| Model card text and licence/usage statements | Author: **UNVERIFIED**. Ada: **read at the pin** | Ada reports `license: apache-2.0` and a License Agreement/accountability paragraph in the pinned card, and read the pinned `LICENSE.txt`. Earlier `apache-2.0`/"not gated" record: [Research 005](../research/005-wan-model-candidates.md), 2026-10-30 (PRIOR-RETRIEVAL). Reading is not approval; gate 1 stays pending |
| File inventory (count, names, per-file bytes) | Author: **UNVERIFIED**. Ada: **partial** (top-level names/sizes, 82.3 GB total) | Not a complete recursive inventory; no verified file count. Research 005 records only approximate component sizes: DiT ≈ 65.6 GB in 7 shards, T5 ≈ 11.4 GB, CLIP ≈ 4.8 GB, VAE ≈ 0.5 GB (sum ≈ 82.3 GB); no exact bytes and no file count |
| Minimum files FRP's adapter requires (source-derived, not Hub-derived) | PROPOSED expectation from [`wan21_adapter.py`](../src/frp/baseline/wan21_adapter.py) (`WAN21_I2V_REQUIRED_FILES`) | **20 files:** 3 `.pth` (T5, CLIP, VAE) + `config.json` + `diffusion_pytorch_model.safetensors.index.json` + 7 DiT shards + 6 tokenizer JSON files + `google/umt5-xxl/spiece.model` + `xlm-roberta-large/sentencepiece.bpe.model`. The adapter also refuses any *additional* pickle-format file. Whether the Hub tree contains further files (e.g. README, licence, example media) is **UNVERIFIED** — the private expected-file list must decide whether a download restricted to the required files is intended (a gate-6 choice) |
| Platform-exposed content identifiers per file | **UNVERIFIED** | The pinned tree labels files as **Files xet**, with large weights marked *xet*. Whether an LFS-style SHA-256 is published for each file is **unconfirmed**; none is claimed. (Research 005's note that VAE and T5 digests equal those of the Wan 2.2 I2V-A14B repository is PRIOR-RETRIEVAL.) None is re-recorded here; they are platform metadata, not FRP verification |
| Git blob ids per file | **UNVERIFIED** | Apply to ordinary Git-tracked files (small text/JSON/tokenizer files); an identifier of Git object content, **not** a SHA-256 |

**Later verification path (operator on a networked machine; metadata only).** Re-run the metadata-only retrieval described in
[Research 005 §Method](../research/005-wan-model-candidates.md) against the **pinned revision URL** (never `main`), save the model card and the
file list with its Xet/LFS and Git-object fields, and record date and tool, requesting only identifiers the platform exposes (Xet and/or LFS/Git fields as shown). Do not fetch resolved file URLs, clone the repository, or invoke a
download tool. Compare the list with the 20-file expectation above and record every difference as a finding.

### 3.3 Digest taxonomy and the private expected-digest process

| Kind | Source | Where it may live | Proves |
| --- | --- | --- | --- |
| Xet content metadata (pinned tree: *Files xet*) | Hub metadata at the pin | Public notes *labelled platform-reported* (none committed by this PR) | Only what the platform says; Xet identifiers are not assumed to equal an LFS or local SHA-256 |
| Hub-reported LFS SHA-256 (only where the platform actually exposes one) | Hub metadata at the pin | Same | Only what the platform says; do not claim one is published where unconfirmed |
| Git blob id | Hub/Git metadata | Same | Identity of a Git object (SHA-1); not usable as a SHA-256 |
| Locally computed SHA-256 | Approved gate-6 download on a private host | **Private record only** | That these bytes exist on that host |
| Private expected-digest manifest | Reviewed outside this repository: for large files, any platform-exposed digest **plus** an independent confirmation (e.g. a second separately reviewed retrieval); for Git-tracked files, an independently established digest or a recorded human trust decision | **Private record only**; no expected hash is put in the public repository or schema 1.0 | The reference against which the local hash is compared |

Missing, extra or mismatching files are STOP (D§5.2 step 14–15). Provenance schema 1.0 cannot mark a weight digest `verified`; that stays unchanged (D§10 G2).

### 3.4 Licence questions for qualified human review (**not** a decision that the use is allowed; gate 1 stays pending)

1. Does the README's "must not involve … disseminates personal information intended for harm" sentence add conditions beyond the Apache-2.0 text, and how
   would a reviewer read it for a private, non-sharing technical test with neutral prompts?
2. Ada read the pinned [model card](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/6b73f84e66371cdfe870c72acd6826e1d61cf279/README.md) and [`LICENSE.txt`](https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/6b73f84e66371cdfe870c72acd6826e1d61cf279/LICENSE.txt) (see §1). The card has `license: apache-2.0` and a License Agreement/accountability paragraph (relevant terms are at that link; they are not adjudicated or paraphrased as permission here). How should a qualified reviewer interpret that paragraph and `LICENSE.txt` for a private, non-sharing technical test, and do they add conditions beyond the README sentence in question 1?
3. The checkpoint bundles third-party components (a T5-family text encoder, a CLIP-family image encoder, tokenizers from other model families). Do their own
   licences or terms apply independently of the Apache-2.0 declaration? (Unreviewed; no claim is made.)
4. Does research use involving **face likeness or biometric-derived data** (even synthetic, even later) interact with any term?
5. Do dependency licences (`torch`, `flash_attn`, `imageio-ffmpeg`/the bundled ffmpeg binary, CUDA runtime, the NVIDIA driver, a base-image OS) matter? (Not reviewed.)
6. Is a licence determination needed per pin, so that any later pin change reopens gate 1? (Recommended: yes, as already stated in D§7.)

## 4. Provider evidence refresh

### 4.1 Comparison candidates and why these two

Candidates are **P1 Lambda On-Demand Cloud (1× H100 80 GB)** and **P2 Runpod Pod, Secure Cloud (H100-class / 94–96 GB SKUs)**, both already in the dossier (D§2.2).
This is a **comparison pair, not a selection or recommendation**. They were picked because they are the two dossier options whose *stop/billing/storage* models differ most
(external terminate API with no documented spend limit, versus prepaid credits with a platform-side stop). P3 (AWS `p5.4xlarge`) is **not refreshed**: its vendor pages were
unreachable and the AWS documentation repositories on GitHub are archived (2023); its D§2.2 column stands unchanged as SECONDARY/UNVERIFIED. No "best" ranking is made.

### 4.2 Runpod facts read from the vendor's documentation source — PRIMARY-VENDOR (scope: documentation text in `runpod/docs` @ `bb50dd3`, committed 2026-11-03; retrieved 2026-11-04; rendered pages and the console not opened)

| Topic | Statement in the documentation | Pages (`docs.runpod.io` path) |
| --- | --- | --- |
| Credit model | Prepaid credits deducted in real time; "Billing runs every 5 minutes"; compute and storage billed per second; "no fees for data transfer" (pods: "no fees for data ingress or egress") | `accounts-billing/billing`, `pods/pricing` |
| Balance reaches $0 | All running Pods are stopped. With a network volume the Pod is stopped and data kept; **without one the Pod is terminated and data "can't be recovered"**. Network-volume storage keeps accruing and "may eventually be terminated" if balance stays at $0 | `accounts-billing/billing` |
| Auto-pay | Reloads the default card below a threshold; attempts limited to once per hour. Low-balance email alerts are separate | `accounts-billing/billing` |
| Deploy minimum | At least **one hour's** credits for the selected configuration must be present | `accounts-billing/billing`, `pods/pricing` |
| **Default spend limit** | **$80 per hour across all resources**, increasing automatically with account history; higher on request. This bounds the *rate* of spend, not a total or per-run cap, and is not a hard cap an FRP run could rely on | `accounts-billing/billing`, `pods/pricing` |
| Storage rates (USD) | Container disk $0.10/GB-month (running; erased on stop, not charged when stopped); volume disk $0.10 running / **$0.20 stopped** (persists until the Pod is deleted); network volume $0.07 (< 1 TB) / $0.05 (> 1 TB), billed hourly. Units "GB" are not defined as GB or GiB | `pods/pricing`, `pods/storage/types` |
| Credits | "Non-refundable"; post-paid billing exists for enterprise contracts only (stops-at-$0 behaviour does not apply there) | `accounts-billing/billing`, `accounts-billing/post-paid-billing` |
| GPU rates | **Not in the documentation**: "Find the latest GPU pricing on the Runpod console during Pod deployment" ⇒ the dossier's per-hour rates remain SECONDARY/UNVERIFIED | `pods/pricing` |
| GPU catalogue | H100 SXM 80 GB, H100 PCIe 80 GB, H100 NVL 94 GB, RTX PRO 6000 Blackwell (several editions) 96 GB listed; host RAM/vCPU not listed | `references/gpu-types` |
| Isolation | "Multi-tenant environment with containerized isolation"; Secure Cloud in T3/T4 data centres; host terms prohibit hosts inspecting Pod data (a *contractual* control, not a technical one). Per this text each Pod is a **container**, not a VM | `references/security-and-compliance` |
| Encryption | Optional "Encrypt volume": volume disk only, at rest on the host, key not retrievable, **no BYOK**; container disk and network volumes cannot be encrypted | `pods/storage/types` |
| GDPR | Statement of GDPR compliance for EU regions; points to a legal page. **A DPA, subprocessor list, biometric-data position and Terms/AUP text were not read** | `references/security-and-compliance` |
| Stop vs terminate | Stop keeps only `/workspace` (volume disk), **keeps billing it**, releases the GPU; terminate deletes the Pod and its volume disk. The docs' "schedule a stop" example runs a timer **inside the Pod** using the account CLI/API key | `pods/manage-pods` |
| Networking | Documentation describes private Pod-to-Pod networking and exposed ports; **no setting to block all outbound traffic from a Pod was found** | `pods/networking` |

Consequences for FRP (assessment, not a provider finding): the documented spend controls are prepaid balance and a rate limit, neither a vendor-verified *total* cap; the $0
behaviour is destructive (acceptable only for an ephemeral run); post-stop liability exists (stopped volume disk at the higher rate); an in-guest stop timer would put a billing-capable
credential on the instance and is not an independent control; outbound blocking is not documented.

**Illustrative post-stop storage arithmetic** [derived from PRIMARY-VENDOR rates; units GB/GiB undefined; excludes tax]: a 250 GB volume disk left *stopped* is 250 × $0.20 = $50.00 per
month (≈ $1.67 per day). With the proposed ≥ 250 GiB scratch (D§2.4) kept on a *running* Pod, 250 × $0.10 = $25.00 per month (≈ $0.83 per day) is added to compute while it runs. These are
bounds on a storage line item only; they are not a quote or a cap.

### 4.3 Decision matrix (P1 vs P2; every cell is a *state of knowledge*, not a score)

Legend: **V** PRIMARY-VENDOR this PR; **S** SECONDARY/snippet (dossier); **U** UNVERIFIED/unknown; **H** HUMAN-PENDING.

| Criterion | P1 Lambda H100 80 GB | P2 Runpod Secure Cloud | Notes |
| --- | --- | --- | --- |
| Exact GPU/VRAM | H100 PCIe 80 GB [V, Ada: official pricing, scoped] | H100 80/94 GB, RTX PRO 6000 96 GB listed [V]; which SKU is offered per region **U** | 80 GB leaves ≈ 4 % headroom over the 720P upstream figure; 480P peak is **UNVERIFIED** |
| Host RAM / vCPU | 225 GiB / 26 vCPU [V, Ada: official pricing] | 94 GB (NVL row) [S]; docs list none [V: absent] | Offload RAM requirement **UNVERIFIED**; published spec ≠ fit |
| Ephemeral scratch | 1 TiB SSD [V, Ada: official pricing] | User-selected; maximum **U** [V: sizes adjustable] | Proposed ≥ 250 GiB (D§2.4) is an allowance, not a measurement |
| Candidate region | **U** | **U** (EU regions mentioned) [V: GDPR page] | Gate 2/4 residency decision (H) |
| Isolation | VM-style instance? **U** | Container, multi-tenant [V] | Container ≠ VM trust boundary; kernel shared with host |
| Volumes: local vs network | Persistent FS is NFS ⇒ excluded; 1 TiB root disk locality **U** [S] | Container/volume disk "local" per docs [V]; network volumes excluded; whether `/workspace` is a host-local block device or an overlay/bind mount **U** | Attestation question (D§5.1 R3, human decision Q6) |
| Billing minimum/granularity | 1-minute increments [S] | Per second; 5-minute billing cycle; one-hour minimum balance [V] | |
| Spend cap mechanism | None found [S] | Prepaid balance + $80/h default rate limit [V]; not a total cap | **No vendor-verified total cap exists in the evidence for either** ⇒ NO-GO under D§8-2 until answered |
| Post-stop liability | Filesystems per GiB-month [S] | Stopped volume disk $0.20/GB-month; network volume accrues at $0 balance [V] | Written bound required |
| Egress: block/verify | **U** | Not documented [V: absent] | Vendor question V5 (V4 is storage backing) |
| Egress fees | "None" [S] | "None" [V] | Not a security property |
| Terms / AUP / DPA | Unread **U** | Unread (legal pages not retrieved) **U** | Gate 4 (H) |
| API termination | Console/API terminate [S]; in-guest poweroff does not stop billing [S] | CLI/API/console terminate [V]; in-guest timer pattern documented [V] | Independent external watchdog still required |
| Deletion evidence | **U** | Terminate deletes volume disk [V]; provider-side logs/snapshots **U** | Deletion drill (§7) |
| Quota / stock | **U** | Zero-GPU restart caveat documented for stopped Pods [V]; quota **U** | Dated quotation (H) |
| Rate | $3.29/GPU-h list + tax [V, Ada, retrieved 2026-11-04; docs table "as of December 2025"] | $3.19/h (NVL) list [S]; not in docs | Lambda refreshed per Ada, Runpod not; neither is a quote; currency, region, tax/VAT, promotions and quota can change it |

**Data boundary (both).** Whether the guest filesystem is local to the Linux instance or container, a real-person portrait sent there is a transfer to, and hosting/processing by, the
**cloud provider** (D§5.1 R13). Egress blocking does not change that. Container/VM guest semantics govern *who inside the guest* can read files; they say nothing about the provider's
hypervisor, host operator, snapshots, support access or logs.

**Calculation caveats.** Any future cost arithmetic must record currency, region, tax/VAT, quota, promotional status, network volumes, guest RAM, billing granularity/minimum and storage that
outlives the instance. The upstream 720P peak (76.7 GB, 1 GPU, offload) and times (D§2.1) are **UNPUBLISHED for 480P**; no 480P figure exists; the ≈ 82 GB checkpoint size is Hub-reported
(PRIOR-RETRIEVAL) and implies large host-RAM, scratch and temporary/cache allowances whose real value is **UNVERIFIED**. The §3 cost grid in the dossier is **not refreshed**: no source in this
PR supports updated rates.

### 4.4 Additional questions for a future human/vendor exchange (extends D§2.3 Q1–Q9; nothing was sent)

| # | Question | Why it matters |
| --- | --- | --- |
| V1 | Can the provider contractually limit **total billable liability** for the account, including storage, snapshots and charges after stop/terminate and after the account balance or card fails? | D§8-2: no cap without a vendor-verified mechanism |
| V2 | Is there a **truly externally enforced termination cap** (a provider-side stop at a stated amount, tested), as opposed to alerts, rate limits or payment workarounds? Exact behaviour and delay at the limit | C1–C4 in D§3.1 are not caps |
| V3 | Do auto-pay/auto-top-up, billing delay (e.g. the documented 5-minute cycle) or invoice-in-arrears terms undermine a prepaid ceiling? How do other products on the same account draw on the balance? | Overshoot and hidden top-ups |
| V4 | Is the guest root and data disk **local block storage or network-backed**, how can an operator show it from inside the guest, and is the `/workspace`-style path a bind mount or overlay? | Local-volume attestation (R3) |
| V5 | Can outbound traffic be **blocked and the block verified** at the network layer after the weight download, leaving only an operator channel? Any provider telemetry/metadata egress from the guest? | R6, D§5.2 step 16 |
| V6 | Is **processing of face media / biometric-derived data** (real or synthetic) permitted under the current Terms/AUP/DPA, with which subprocessors, logging and support-access rules? | Gate 4 |
| V7 | What **copies and logs** of guest content, images, snapshots, console sessions and billing records remain after termination, for how long, and how is deletion evidenced? | Deletion drill, gate 3 |
| V8 | Which API credential scopes exist (e.g. terminate-only), and can the terminate credential be held off-instance by a different person? | §7 credential custody |
| V9 | How is a customer-supplied image or template identified (digest) and can the driver/CUDA/kernel/firmware versions be recorded before any data arrives? | R9, §5 |

## 5. Linux environment specification (SPECIFICATION ONLY — nothing is installed, built or pulled)

All values are **PROPOSED**. "Source-checked" means a published name/statement was read from the cited primary source today; **no row has been tested on hardware** and every
compatibility claim is **UNVERIFIED on hardware** unless stated otherwise. The pinned upstream commit, not a package index, supplies the source tree.

### 5.1 Component table

| Component | PROPOSED | Source-checked fact (primary) | UNVERIFIED on hardware |
| --- | --- | --- | --- |
| Operating system | PROPOSED: Ubuntu 22.04 LTS `x86_64` (Lambda's public image table lists 22.04 with default Python 3.10 and 24.04 with default Python 3.12; per Ada's review). Pin policy: record exact distro point release, architecture, kernel release and NVIDIA driver version, and the provider image identity/digest, freeze them before any build, and treat any change as a new specification | Lambda image table per Ada (not re-read by the author) | Driver and library packaging on the chosen provider image |
| Kernel | Whatever the provider guest provides; **record** the release string and boot parameters before load | — | Whether a provider kernel matches the NVIDIA driver in use |
| Python | **3.11**, installed from an explicitly proposed and frozen source (neither Ubuntu 22.04 nor 24.04 defaults to 3.11 on the Lambda image table; the source, e.g. a pinned distribution package or a hashed build, is a human decision, not provisioned here) (FRP requires ≥ 3.11 in `pyproject.toml`; the upstream pin allows ≥ 3.10) | flash-attn `v2.8.3.post2` publishes `cp311` Linux `x86_64` wheel names (see below); the PyTorch matrix (`RELEASE.md` on `main` @ `4a442f4e2e07ee3ff6b0baf45e5ae435d9c62229`, 2026-11-04) lists Python ≥ 3.9 for torch 2.8 and ≥ 3.10 for 2.9–2.14 | Interpreter build and `-I -B` behaviour on the provider image |
| torch / torchvision | **torch 2.8.x** (≥ 2.6 is FRP's weights-only requirement) with the matching `torchvision`, from CUDA 12.x wheels | The PyTorch release matrix lists CUDA 12.6 and 12.8 as stable for 2.8; the Wan pin requires only `torch>=2.4.0` | Whether the Wan pin runs correctly on torch 2.8, and whether the three `.pth` files load under weights-only unpickling (runbook §5; R10) |
| CUDA runtime/toolkit | **12.6** (bundled with the torch wheel; no system toolkit install proposed) | Matrix above (12.6 is stable for torch 2.8–2.14) | Driver/runtime pairing, Hopper behaviour |
| NVIDIA driver | The provider's installed driver; **record** version before load; do not upgrade in place | **Not source-checked** (NVIDIA pages unreachable): the minimum driver for the chosen CUDA is **UNVERIFIED** | Everything |
| `flash_attn` | Pre-built wheel from the `Dao-AILab/flash-attention` release `v2.8.3.post2` (published 2026-10-13) matching `cu12`, `torch2.8`, `cp311`, `linux_x86_64`; hash-pinned. **Alternative:** deliberately run without it (SDPA fallback) | The release lists 10 matching `cp311` wheel names for `cu12torch2.4`–`2.8` with `cxx11abiFALSE` and `TRUE`; upstream Wan treats the package as optional at import (§3.1) | Which ABI variant matches the installed torch build; Hopper correctness/speed; whether the fallback's disabled padding mask changes outputs. **Whether flash_attn is present is a recorded control** because it changes numerics |
| ffmpeg | The `imageio-ffmpeg` wheel's bundled binary (FRP refuses `IMAGEIO_FFMPEG_EXE`); record the wheel SHA-256 and the binary's version/build string | Upstream lists `imageio-ffmpeg`; FRP's runtime refuses an overriding binary | Provenance, licence and codec features of the bundled binary; behaviour of the staged-file inode check under it (R11) |
| Upstream source | Fresh clean clone at `9737cba9c1c3c4d04b33fcad41c111989865d315`; no package-index install of `wan` | Commit date 2026-03-05T09:38:07Z (§3.1) | — |
| Frozen dependencies | A **hashed lock** (every distribution with an exact version and SHA-256, `linux_x86_64`, `cp311`) produced later on a CPU-only networked machine and reviewed; installed with hash enforcement; **no ranges**. Propose a minimal subset (omit `gradio`; keep `dashscope` out of the set if the import path does not need it — FRP's runtime already refuses it) | Upstream pins are lower bounds only (`requirements.txt` hash above) | Whether the subset suffices; transitive dependency licences |
| Image/VM digest | **To be created later, outside this PR.** If a container image is used: a base image pinned by digest, built in a separate reviewed private process; if a VM: the provider image id recorded | — | A reproducible build; the provider's ability to expose a digest (V9) |
| Host GPU/firmware | Record GPU model, VRAM, driver, VBIOS/firmware as reported, before load; a mismatch with the approved record is NO-GO (R9) | — | Whether a provider exposes firmware data |
| Directories (names only) | Separate, Linux-local, owner-only (single non-root user): source checkout (clean, read-only after verification); checkpoint directory (read-only after verification); empty offline Hub-cache directory; private store root (canonical, mode 0700, never a symlink); scratch/temp; private logs. **No path is published** | `LocalPrivateStore` requires Linux, canonical owner-only roots; network/FUSE/shared filesystems are unsupported and cannot be detected there ([`private_storage.py` L22–L25](../src/frp/private_storage.py)) | Real mount type, ownership and permissions, `fsync`/`link` semantics on the provider volume |
| Offline variables | `HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE` set; `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`, `LD_PRELOAD`, `LD_AUDIT`, `IMAGEIO_FFMPEG_EXE` absent (adapter refusals) | Runbook §5, runtime docstring | Completeness against provider-injected variables |

### 5.2 Reproducible future build procedure (a description, not a script)

1. On a CPU-only, non-private, networked machine, resolve the minimal dependency set for `cp311`/`linux_x86_64`/torch 2.8/CUDA 12.x, producing a **hashed lock** and a list of
   download sources; review it (including licences) as a separate step. 2. Obtain each artefact (wheels, the flash-attn wheel, the pinned source tree) from its owner, verify hashes
   against the lock, and store the *artefact bundle* privately. 3. Create the image or VM base **later** under a separate decision, recording its digest. 4. At run time, install only from
   the bundle with hash enforcement, with no index access. 5. Record every identity listed in §5.1 in the private record **before** any weight or reference is present. Any difference from
   the approved record is NO-GO. Steps 2–5 are not authorised or performed here, and no CUDA stack, image, wheel or checkpoint was obtained by this PR.

### 5.3 Network phases (PROPOSED policy; enforced and verified **outside** the instance)

| Phase | Allowed | Evidence |
| --- | --- | --- |
| N0 Provision/build | Only the operator management channel and the pre-reviewed artefact bundle source | Provider network configuration recorded |
| N1 Checkpoint download (gate 6 only; no personal data present) | Only the approved Hub endpoint(s) for the pinned revision | File list and local hashes (private) |
| N2 **Closed** (before any reference arrives) | Default-deny outbound; only the operator management channel | A sacrificial outbound attempt **observed to fail**, plus provider-level confirmation (V5) |
| N3 Reference ingress / output egress | **Synthetic (R2)**: a licence-verified synthetic image in and a synthetic output out over an operator-initiated channel, still reviewed as a transfer to the provider. **Real (R1)**: forbidden until gates 2, 3 and 4 explicitly decide path, provider access, logging, snapshots and deletion (D§5.1 R13) | Transfer record (private) |

## 6. Windows host, Codespaces and Docker: what actually attests what

Development on Windows and in Codespaces stays **CPU-only** with synthetic fixtures; no identifiable store is created there (existing Linux-only enforcement is unchanged).

| Setting | What it can show | What it cannot show |
| --- | --- | --- |
| Windows host | Nothing for the private store: the store **refuses** non-Linux platforms | — |
| Codespaces / dev container | CPU tests only. The workspace volume, snapshots and tooling are provider-managed and were not assessed here; the repository forbids real media there | Private-store guarantees |
| Docker Engine on a **genuinely attested Linux** host with a local block filesystem, an owner-only directory and a documented snapshot policy | A candidate for the store | Provider/hypervisor access unless the host itself is controlled |
| Docker Desktop / WSL2 / Linux VM **on Windows** | Linux *kernel semantics* inside the guest. `sys.platform == "linux"` is true there, so FRP's platform check **passes** | The **filesystem backing type**: a bind mount of a Windows folder is served across a host–guest filesystem layer, so ownership/mode bits, `link`/`fsync` semantics and what the Windows user, backups or indexers can read are **not established** by the guest's POSIX view. This is not source-checked here and is UNVERIFIED either way |

An operator attestation for any Linux guest must separately record: (1) **Linux guest semantics** (kernel, uid model, no mapped Windows identities); (2) **filesystem backing type** of the store and
checkpoint paths (local ext4/xfs on a virtual or physical block device, versus a host-shared, network, FUSE or overlay mount); (3) **owner and permissions** observed from inside the guest;
(4) **snapshot, backup and sync** coverage on the guest *and* the host; (5) **provider or host access** (hypervisor, support, other tenants). Elements 2 and 4 are invisible to the CPU-tested
store. Passing these is a human decision (D§9 Q6), not a property this repository can assert, and no enforcement or schema was changed.

## 7. Paper-only control specification (no executable code, launcher, granting provider or runnable example is added)

Each control is a requirement for a **private** runtime reviewed outside this repository. Anything resembling these controls as a script, test grant or configuration is forbidden in the public
tree (AGENTS.md; D§5).

| Control | Requirement | Independence / evidence to record privately | Open question |
| --- | --- | --- | --- |
| External runtime watchdog | A separate machine/account, not the Python process or the instance, observes elapsed time, instance state and resource/charge signals and calls provider termination at the deadline | Different credentials, host and operator from the run | Who operates it; its own availability |
| Termination and confirmation | Termination by provider API/console, then a **list** that confirms instances, volumes, snapshots, images and logs are gone | Provider listing before/after; time to release | What remains billable (V1, V7) |
| Resource / charge observations | GPU, host RAM, disk and network sampled outside Python; provider charge line observed against the approved cap at an interval shorter than the billing delay | Private log (no media, no paths) | Peak between samples can be missed (D§10 G1) |
| Emergency-stop drill | A human terminates a *trivial, zero-data* instance in < 1 minute without the instance's cooperation, rehearsed before any gated stage | Dated drill record | Per-provider mechanics differ (D§3.2); the Runpod docs' in-guest timer pattern is **not** this control |
| Credential custody | The termination credential is held off-instance, least-privilege (terminate-only if the provider can issue one), separate from the operator holding the run; no billing-capable key ever enters the guest | Custody record; rotation after the run | Scope options (V8) |
| Ledger-key custody | Where the keyed-token/tombstone key lives, who can read it, backup, destruction, and whether retention survives withdrawal (R2) | Private record | Lawful basis (gate 2/3) |
| Immutable grant authenticity / revocation | A grant is issued and authenticated by a private issuer, is identical at every re-check, is revocable with a stated latency, and a revoked grant is refused before an attempt | A rehearsed revoke-then-attempt on synthetic runs | Issuer, signature scheme, revocation source — **escalate to Ada**; not designed here |
| Local-volume attestation | §6 elements (1)–(5) recorded for the store and checkpoint volume | Inspection output recorded privately | Whether a virtualised block device counts (human decision) |
| Post-download egress closure | N2 in §5.3, observed from inside **and** confirmed at the provider network layer, before any reference arrives | Sacrificial-process attempt; provider configuration record | Whether the provider can block all egress (V5) |
| Ingress/egress for synthetic vs real media | Per §5.3 N3; synthetic = still a provider transfer; real = explicit gate 2/3/4 decisions | Transfer record | Channel design (R13) |
| Provider-side deletion drill | After a *synthetic* run, delete everything and verify via provider listings, billing lines and a support confirmation where available | Dated drill record | Backups/snapshots the customer cannot see |

**Escalation.** Questions that would change the private-runtime or security architecture materially (for example a grant issuer design, a provider gateway, or moving the launcher to a private
repository) are for Ada's review. They are recorded as questions, not implemented, so this PR is not blocked on them.

## 8. Smoke-run scope reminder

If separately approved, the proposed GPU smoke is the **upstream-default full-path** run (81 frames × 40 steps, D§6.1) using a **licence-verified synthetic portrait (R2)**; R2 is a *proposal needing a
recorded human protocol decision*, not an automatic authorisation, and not a protocol change. It is a technical pipeline test, **not scientific calibration**: it measures no identity retention
and supports no protection claim (D§6.3). The consenting-adult baseline (R1), detection/utility calibration, a second evaluation method and the A/B/C/D study (#14) are separate later work.

## 9. Blockers and human decisions (delta; D§9 still applies in full)

| # | Blocker | State | Blocks |
| --- | --- | --- | --- |
| B1 | Card and top-level tree read independently by Ada; complete recursive inventory, Xet/LFS/Git identifiers and expected digests still absent; licence not approved | **Partly narrowed; unresolved**; metadata-only re-retrieval and human review needed (§3.2) | Gates 1, 6 |
| B2 | No dated quotation, region availability, quota, Terms/AUP/DPA, no-egress, storage locality or vendor-enforced spend cap/liability bound; Lambda list rate/specs now scoped PRIMARY-VENDOR (Ada), Runpod rate SECONDARY | **Unresolved** | Gates 4, 5 |
| B3 | No vendor-verified **total** spend cap or post-stop liability bound in the evidence (Runpod: prepaid balance + $80/h rate limit; Lambda: none found) | **NO-GO** under D§8-2 until answered | Gate 5 |
| B4 | No documented way to block and verify outbound traffic on either candidate | Unresolved (V5) | Gate 6, 7 |
| B5 | Local-volume attestation definition; container (Runpod) versus VM guest | Human decision | Gates 3, 7 |
| B6 | Reference class decision (R2 first smoke vs R1 later) and transfer channel | Human decision | Gates 2, 7 |
| B7 | Environment never built; torch 2.8/CUDA 12.6/flash-attn compatibility with the Wan pin untested | UNVERIFIED on hardware | Gate 7 |
| B8 | Licence review of the card, bundled third-party components and dependencies | Human | Gate 1 |

Operator actions (not agent actions): re-retrieve the Hub card/tree and vendor pages from a networked machine and record them privately with date; send V1–V9 and D§2.3 to at most two vendors **only** on a separate
human decision; produce the hashed lock (§5.2). Candidate future issues, **not opened or implemented here**: D§10 G1–G4 (unchanged) and a private-repository home for the launcher/watchdog design (G3).

## 10. Verification record

Recorded in the PR description with exact commands and results; offline, CPU-only; they say nothing about GPUs, weights, vendors or runtime. No file under `src/`, `tests/`, `provenance/`, `readiness/`,
the manifest schema or `examples/` was changed.

| Command (run in a throw-away virtual environment outside the repository) | Result |
|---|---|
| `frp provenance provenance/model-candidates.yaml` | exit 0; 9 candidates; **NOT READY** for every candidate; weight SHA-256 `not_verified` |
| `frp readiness readiness/wan21-i2v-baseline.yaml --provenance provenance/model-candidates.yaml` | exit 0; **Authorised to execute: NO**; all seven gates `pending`; cost quote `not_obtained` |
| `frp baseline-plan examples/manifests/synthetic-baseline-dry-run.yaml` | exit 0; plan valid; **NOT EXECUTION READY** (unset fields; no private authorisation mechanism; live backend disabled) |
| `ruff check .`, `ruff format --check .`, `pytest -q` | clean; 92 files formatted; 1100 passed (run as a regression check although no code changed) |

**Not tested:** anything involving a GPU, CUDA, weights, Hugging Face, a vendor, an image build or a real or synthetic portrait.
