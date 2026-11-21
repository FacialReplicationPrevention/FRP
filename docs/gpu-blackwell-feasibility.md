# Blackwell compatibility and fixed-duration feasibility delta (Milestone 004, PR 3K)

**Status: PLANNING ONLY. NO GPU / NO WEIGHTS / NO REAL MEDIA / NO INFERENCE / NO SPEND. ALL SEVEN HUMAN GATES PENDING. NOTHING AUTHORISED. Decision: NO-GO / NO PROVIDER.**
Issue [#33](https://github.com/FacialReplicationPrevention/FRP/issues/33); follows merged PR #32 (issue [#31](https://github.com/FacialReplicationPrevention/FRP/issues/31), merged 2026-11-21). Parent [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9) stays open; [#14](https://github.com/FacialReplicationPrevention/FRP/issues/14) stays blocked. This appendix extends [§2.3 of the provider decision](gpu-provider-decision.md#23-fixed-duration-and-isolation-feasibility-delta-2026-11-20-issue-31) and does not repeat it: 3J's reviewer-attributed GPUServerHub evidence, control matrix and vendor questions P0/P1 are preserved. Pins are unchanged: `Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`; `Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`; `use_prompt_extend: false`; original reference on both conditioning paths; CFG controls unchanged. Nothing below is an FRP measurement, quote, approval or compatibility claim.

## 1. Retrieval log (2026-11-21; agent environment; text/metadata only)

| Source | Result | Used as |
| --- | --- | --- |
| `https://gpuserverhub.com/`, `/terms/`, `/documents/1.8/r2/daily-rental-terms.html` (`curl`, web-fetch) | **RETRIEVAL-FAILED** — no DNS answer ("No address associated with hostname"). | Nothing. 3J's Ada-attributed statements (terms `gpu-daily-rental-v3`, dated 2026-11-17) are retained **unchanged and not re-read**; no changed version/date can be reported. Every GPUServerHub control stays UNKNOWN. **Targeted Ada primary-source re-read requested** (§6). |
| `docs.nvidia.com`, `developer.nvidia.com`, `huggingface.co` | Not reachable (HTTP `000`). | NVIDIA driver/compute-capability pages and the Hub tree were **not** read; related rows are marked UNVERIFIED. |
| [`pytorch/pytorch` `RELEASE.md`](https://github.com/pytorch/pytorch/blob/66fa84cbcb2001a816dc228dbde29ca184ff9d73/RELEASE.md) @ `66fa84cbcb2001a816dc228dbde29ca184ff9d73` (`main`, read via raw GitHub) | Retrieved. Compatibility matrix: torch 2.8 stable CUDA 12.6 / 12.8 (experimental 12.9), Python ≥ 3.9 ≤ 3.13; 2.9: 12.6 / 12.8 (exp. 13.0). The architecture table in this revision covers only **release 2.15** (CUDA 13.2.2 / 13.4.3; Hopper 9.0, Blackwell 10.0 and 12.0; wheels ship SASS only). | Documented matrix for CUDA versions per torch release; **no per-architecture list for torch 2.8 was retrieved**. |
| [`Dao-AILab/flash-attention` release `v2.8.3.post2`](https://github.com/Dao-AILab/flash-attention/releases/tag/v2.8.3.post2) (published 2026-10-13; GitHub API) | Retrieved. 48 assets; Linux `x86_64` wheel names tagged `cu12` with `torch2.4`–`torch2.8`, `cxx11abi{FALSE,TRUE}`; body mentions `cu13` prebuilt wheels. Release notes state "no kernel feature changes". | Wheel naming only. **No statement about sm_120 (RTX PRO 6000 Blackwell) support was found.** |
| [Wan2.1 `attention.py`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/attention.py) and [`image2video.py`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py) @ the pin | Retrieved. `flash_attn_interface` (FA3) then `flash_attn` (FA2) are optional imports; otherwise `scaled_dot_product_attention` fallback (padding mask disabled; 3E §3). Half-precision (bf16/fp16) is asserted in the flash path; generation runs under `torch.cuda.amp.autocast(dtype=param_dtype)`. | Static source observation. |

## 2. Blackwell software compatibility matrix

Labels: **DOC** = documented in a retrieved primary source, at its stated scope; **STATIC** = inference from source/docs without a run; **TEST** = needs a separately approved no-participant-data runtime test; **UNVERIFIED** = not retrieved here. A VRAM figure or a generic "Blackwell/CUDA supported" statement is not a compatibility finding for this model.

| Item | Candidate fact / requirement | Basis | Status |
| --- | --- | --- | --- |
| Advertised GPU | "Dedicated RTX PRO 6000 Blackwell 96 GB; up to 192 GB RAM; 4 TB NVMe" (3J, Ada-attributed). **Variant not stated** in the reviewed excerpt: Workstation Edition vs Max-Q vs Server Edition differ in power/cooling/vBIOS; display/MIG/ECC/vGPU settings are also unspecified. | 3J | UNKNOWN variant; ask |
| Compute capability | RTX PRO 6000-class (workstation-Blackwell, GB202) is expected to be `sm_120` (CC 12.0), **not** the datacentre `sm_100`. The PyTorch 2.15 table lists 12.0 for Linux x86 wheels. NVIDIA's GPU table was not retrieved. | PyTorch `RELEASE.md` @ `66fa84c` (2.15 only); NVIDIA UNVERIFIED | UNVERIFIED for the SKU; DOC for torch 2.15 only |
| Usable host RAM / local disk | "Up to" 192 GB RAM, 4 TB NVMe are ceilings. Actual provisioned amount, whether the disk is a host-local block device, and whether usable capacity equals the headline are unknown. Checkpoint files ≈ 82.3 GB (Hub-reported, not re-measured). | 3J; dossier D§2.4 | UNKNOWN |
| OS / driver access | Whether the customer chooses the OS image, receives root, can see the NVIDIA driver version, and whether a driver can be installed or is pre-installed (the terms reportedly include OS installation inside the rental). Blackwell needs a driver new enough for the chosen CUDA; the minimum was not retrieved. 3E's proposal "do not upgrade the driver in place" may conflict with a Blackwell image. | 3J; 3E §5 | UNKNOWN / UNVERIFIED |
| Linux / Python | 3E proposes Ubuntu 22.04 + Python 3.11. Torch 2.8 supports Python ≥ 3.9 ≤ 3.13; the Wan pin allows ≥ 3.10; FRP requires ≥ 3.11. No conflict found statically. | PyTorch matrix; 3E | STATIC |
| CUDA runtime vs toolkit vs driver | Three distinct things: *runtime* (bundled in the torch wheel), *toolkit* (nvcc; only needed to compile extensions), *driver* (kernel-side, host-provided). 3E proposes CUDA **12.6** runtime. PyTorch lists 12.6 and 12.8 as stable for 2.8, but a 12.6 build is a Hopper-era choice; **whether a CUDA 12.6 wheel contains sm_120 kernels, or PTX that can JIT to it, was not retrieved**. Blackwell-class GPUs generally need a CUDA ≥ 12.8 build (**NVIDIA documentation not retrieved here**). | PyTorch matrix; NVIDIA UNVERIFIED | **Likely conflict with 3E's CUDA 12.6 proposal — STATIC, UNVERIFIED** |
| torch / torchvision | FRP loader safety requires torch ≥ 2.6 (weights-only unpickling; runbook §5). Candidate range for Blackwell: a build documented for CUDA ≥ 12.8 (torch 2.8 with CUDA 12.8 is in the stable matrix; newer releases also qualify). The Wan pin requires only `torch>=2.4.0` and was developed on earlier torch; correctness on a newer torch is **untested**. | PyTorch matrix; Wan `requirements.txt` | STATIC; TEST |
| Weights-only load of the 3 `.pth` files | Independent of GPU architecture; still unproven under any torch (runbook §5). | Runbook | TEST (CPU-only, separate step) |
| `flash_attn` (FA2/FA3) | Optional at import. v2.8.3.post2 ships `cu12` wheels up to `torch2.8`; the release notes make no sm_120 statement, and prebuilt FA2 wheels are not documented here to include sm_120 kernels. FA3 (`flash_attn_interface`) is Hopper-oriented; not evidenced for sm_120. Compiling from source would need a CUDA toolkit and extended build time on the rental, conflicting with the 24-hour budget and with "no unsupported fallback". | Release page; Wan `attention.py` | UNVERIFIED; TEST |
| Attention fallback | Running without `flash_attn` uses SDPA with the padding mask disabled, a numerics difference. Whether to use it is a recorded **protocol-level control**, not a fix to make Blackwell fit; changing it needs separate review. | Wan `attention.py`; 3E | Proposal for separate review only |
| Precision | Upstream bf16/fp16 autocast; FRP's adapter refuses any other precision. Blackwell bf16 execution is expected but unrun; no quantisation, FP8/FP4 or other precision change may be used. | `image2video.py`; adapter refusals | STATIC; TEST |
| Other compiled deps | `requirements.txt` at the pin also lists `opencv-python`, `imageio-ffmpeg` (bundled binary; adapter refuses `IMAGEIO_FFMPEG_EXE`), `numpy<2`, `tokenizers`, `accelerate`, `gradio` and `dashscope` (remote client, must stay unused); `flash_attn` is the only listed GPU-kernel package. Triton/cuDNN come with the torch wheel. Whether each prebuilt binary wheel is usable in the approved environment is unverified. | Wan `requirements.txt` (3E §3.1) | UNVERIFIED |
| Memory fit | 96 GB exceeds the 76.7 GB **720P** upstream peak; the 480P peak and FRP wrapper overhead are unmeasured. Capacity does not imply compatibility and no offload/quantisation workaround is permitted. | Dossier D§2.1 | UNVERIFIED |
| Determinism | Seeded CUDA generator; cross-GPU results unknown. Blackwell outputs would not be comparable to an H100 reference. | Research 005 | UNKNOWN |

**Conflicts with the proposed H100 environment (3E §5).** 3E proposes torch 2.8.x with CUDA 12.6 wheels and an optional `cu12torch2.8` `flash_attn` wheel, written for Hopper. A Blackwell candidate would likely need a different CUDA runtime build (and possibly a different driver), different or absent flash-attn, and therefore a **new environment specification and hashed lock**. These are **proposals for separate review**, not changes: no environment lock, dependency, adapter code, refusal or pin is edited here. The existing refusals (torch ≥ 2.6, precision, checkpoint file list, offline/loader-safety environment, CI/Codespaces) stay intact.

**Summary.** Nothing here supports "Wan 2.1 I2V-14B-480P runs on this GPU." The only separately testable path is a later, separately approved, zero-participant-data compatibility run.

## 3. Can a 24-hour rental support the baseline? Scenario model

All numbers are **labelled scenario arithmetic or formulas**, not predictions. Unknown durations stay symbols. No H100 benchmark is used as a bound (the 720P upstream 1491.6 s on H100-class is a proxy for a different GPU, resolution and scope).

**Formula.** `T_total = T_boot + T_env + T_dl + T_hash + T_iso + T_load + n·T_gen + T_retrieve + T_delete`, with a reserve `R`. Feasible only if `T_total + R ≤ 24 h − T_elapsed_before_start`, where the rental clock reportedly includes OS installation (3J).

| Phase | Symbol | What it covers | Size / rate basis | Status |
| --- | --- | --- | --- | --- |
| OS install, provisioning, driver | `T_boot` | Customer or provider OS image; driver check; operator channel | None | Unknown |
| Environment preparation | `T_env` | Approved hash-locked wheels, pinned Wan source, record of versions | Wheel sizes not measured; a source build of flash-attn would be hours, if even possible | Unknown |
| Checkpoint acquisition | `T_dl` | 20 required files, ≈ 82.3 GB (≈ 76.7 GiB) Hub-reported | `T_dl = 82.3 GB × 8 / rate`: at 1 Gbit/s ≈ 0.18 h; 500 Mbit/s ≈ 0.37 h; 100 Mbit/s ≈ 1.8 h; 10 Mbit/s ≈ 18 h (rates are **illustrative scenarios**, none measured or offered) | Unknown |
| Local SHA-256 | `T_hash` | Read ≈ 82.3 GB | `82.3 GB / disk_read_rate`; at 1 GB/s ≈ 1.4 min, at 200 MB/s ≈ 6.9 min (scenarios) | Unknown |
| Outbound-deny verification | `T_iso` | Provider-side deny applied after download; in-guest sacrificial probe (3E §7) | Depends on provider turnaround (hours if via support ticket) | Unknown; **may dominate** |
| Model load | `T_load` | ≈ 82 GB read, bf16 placement, no `t5_cpu`/FSDP | Not measured | Unknown |
| Minimal neutral smoke run | `n·T_gen` | Neutral/synthetic input only, per runbook | Not measured on this GPU; no bound derived from H100 | Unknown |
| Private output retrieval | `T_retrieve` | Through the operator channel while egress is otherwise denied | Output size small; channel unknown | Unknown |
| Verified deletion | `T_delete` | Wipe plus evidence; provider expiry erasure has exceptions | Evidence format unknown | Unknown |

**Plausibility.** Bandwidth arithmetic alone does not rule the term out for rates ≥ 100 Mbit/s, but the 24-hour term is a hard prepaid cap, there is no early restart, and the network dependency is the problem: download must complete **before** egress is denied, while the denial must be provider-enforced (unresolved), and the operator channel, retrieval and deletion evidence must also fit. A failed hash, torch/CUDA mismatch, absent flash-attn wheel or OOM consumes the single rental with no replacement; any retry is a new rental needing a fresh quote and approval (D§6.2). Fit is therefore **UNKNOWN**, with the dominant risks being `T_env` (an unvalidated Blackwell stack), `T_iso` and provider turnaround.

**Preparation that needs no restricted asset, spend or real media (proposals; none performed).** (a) On a CPU-only, non-private, networked machine, resolve a candidate Blackwell-capable dependency set, produce a hashed lock for review, and read the NVIDIA support statements (3E §5.2 steps 1–2, redone for the new architecture). (b) Draft the exact private runbook checklist, timing sheet and abort script text (documentation only, no executable workaround in `src/`). (c) Pre-agree the evidence format for deletion and isolation. (d) Obtain the written provider answers in §5, after separate outreach approval. Downloading wheels, source trees or weights to a rental, or any rental-side step, is **not** pre-rental preparation.

**Proposed abort/minimum-remaining-time rule (for later human review; no threshold is approved).** The human decision-maker should set, in the private record before any rental: a minimum remaining time `R_min` at each checkpoint (after environment ready, after hash verified, after egress denial verified, before the smoke run) such that remaining time ≥ `(measured-or-bounded T_load + T_gen + T_retrieve + T_delete) + reserve`; abort and start deletion if any checkpoint fails, a mandatory control cannot be verified, or a version mismatches the approved record. This repository sets no numeric `R_min`.

## 4. Terms and control gaps (reconciled with 3J)

3J's evidence is preserved at its attribution (Ada, 2026-11-20; not re-read here); the GPUServerHub URLs could not be retrieved on 2026-11-21 (§1), so **no changed version or date is known**. Statuses: **DOC** = contractual/published statement per Ada's review, scope-specific, not operational proof; **FAIL**; **UNKNOWN**.

| Mandatory control | Status (GPUServerHub) | Evidence that would resolve it | Gate(s) blocked |
| --- | --- | --- | --- |
| Maximum total contractual liability (VAT, extras, storage, network, snapshots, damage/support, expiry, post-stop) | UNKNOWN. Final-consumer €49 prepaid is a headline price, not a total bound. | Written statement/terms covering all charge classes, current VAT treatment for the buyer; evidence of no automatic renewal | 5 |
| No automatic renewal / independent spend enforcement | **DOC (term only):** fixed 24 h, no automatic extension. Independent enforcement UNKNOWN | Terms text plus provider statement of billing behaviour after expiry | 5 |
| Emergency termination before expiry, separately scoped and testable | UNKNOWN. Fixed expiry is not early termination. | Described credential/interface not shared with the guest, ideally with a zero-participant-data drill | 5, 7 |
| Provider-enforced outbound deny (IPv4/IPv6, DNS, metadata/service routes, alternate interfaces); guest networking alone insufficient | UNKNOWN | Provider configuration record; in-guest sacrificial attempt | 6, 7 |
| Permitted workload (face media/likeness, research), AUP | UNKNOWN (terms not read by the author) | Qualified legal reading of current terms | 1, 2, 4 |
| Tenancy (dedicated physical GPU/host, no sharing) | **DOC (advertised "dedicated"):** meaning unspecified; UNKNOWN | Written definition; hypervisor/passthrough vs bare-metal | 4, 7 |
| DPA, residency, support access | UNKNOWN | DPA, subprocessors, location, support/remote-access policy | 2, 4 |
| Local Linux block storage, encryption at rest | UNKNOWN (NVMe advertised) | Vendor statement plus in-guest inspection output | 3, 6 |
| Retention, backups, snapshots, logs | UNKNOWN | Retention schedule | 3, 4 |
| Verified deletion / erasure exceptions | **DOC TERM:** erasure on expiry subject to exceptions; operational evidence UNKNOWN | Exceptions list; post-expiry evidence method | 3, 4 |
| Blackwell/Wan compatibility | UNKNOWN (§2) | Separately approved zero-data run | 5, 7 |

No mandatory row is cleared; any FAIL/UNKNOWN prevents procurement or execution.

## 5. Residual vendor questions (only genuinely unresolved; not sent)

No contact, quote request or account action is made or authorised. Compare with 3J's P0/P1 and private correspondence before any approved outreach; items already answered privately must be removed.

1. **(P0-1+)** What is the maximum total liability for one 24-hour rental for a buyer in the buyer's jurisdiction (VAT, any extras/overage, storage, network, damage/support, post-expiry)? Is renewal impossible without a new explicit order?
2. **(P0-2)** Is there a provider-side action, independent of the guest and separately scoped from account administration, to stop a rental early? What is its latency and is any refund/charge effect stated?
3. **(P0-3)** Can the provider enforce deny-all outbound (IPv4/IPv6, DNS, metadata/service routes, any other interface) on request after download, and how is it confirmed? Does the server have any out-of-band management interface (BMC/KVM) the provider can reach?
4. **(P1-6)** Exact GPU variant (Workstation/Max-Q/Server), compute capability, vBIOS, driver version and CUDA runtime preinstalled, and whether the customer may install an OS, driver and kernel.
5. **(P1-4)** When does the rental clock start, what image/OS install time is counted, and is the provisioned RAM/disk exactly the "up to" headline?
6. **(P1-5/P0-6)** Which erasure exceptions, backups, logs and provider-held copies exist, and what deletion evidence can be provided?
7. **(P0-5)** Do terms/AUP/DPA permit later adult-face research workloads, and what are subprocessors, region and support access?

## 6. Decision and handoff

**Decision: NO-GO / NO PROVIDER.** Continue **narrowly scoped, documentation-only due diligence** on GPUServerHub only if the human owner wants to spend effort; otherwise stop this candidate. Reasons: every mandatory control is UNKNOWN; Blackwell (sm_120) compatibility with the pinned Wan source, FRP's torch ≥ 2.6 requirement, the attention path and the 3E environment is untested, and the likely CUDA/flash-attn conflicts require a new environment specification; the 24-hour term leaves no slack for a failed first attempt.

**Source-retrieval failure.** GPUServerHub pages (three URLs above) failed DNS on 2026-11-21; status stays UNKNOWN. **Requested: a targeted Ada primary-source evidence review** of those three URLs, recording URL, retrieval date, document version/effective date and exact clauses on liability, termination, egress, deletion, workload and tenancy, plus the NVIDIA compute-capability/driver pages and the torch ≥ 2.6 per-architecture wheel list for the chosen CUDA build.

**Reversal criteria (all needed before reconsidering; none sufficient to approve).** (1) Current, dated written evidence for each §4 row. (2) A reviewed Blackwell environment specification and hashed lock (separate PR). (3) Owner decision on whether a **paid zero-participant-data compatibility/control drill** is permitted. The gate protocol has no slot for it; this is a **sequencing exception requiring a separate human decision (escalate to Ada/Mark)** and is not invented or approved here. (4) All seven gates approved separately in the private record.

**What a minimal future zero-participant-data validation would have to prove (not authorised, implemented or executed):** the exact SKU/driver/CUDA identity record; torch's CUDA build exposes sm_120 and runs a trivial kernel; the three `.pth` loads succeed under weights-only unpickling; attention path selection and numerics are recorded; provider-enforced deny and early termination work as documented; deletion evidence is delivered; and every duration in §3 is measured. It would not measure identity retention or support any protection claim.

**Human decisions next:** (a) whether to continue or stop this candidate; (b) whether to approve a targeted Ada evidence re-read; (c) whether an exception for a paid no-data drill is to be considered at all. Only Mark decides merge.
