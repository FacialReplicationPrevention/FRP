# GPU procurement evidence and private go/no-go dossier — Wan 2.1 I2V-14B-480P (Milestone 004, PR 3D)

**Status: PLANNING ONLY. NOT AUTHORISED. Nothing here has been rented, bought, downloaded, hashed, loaded, run or approved.**
No GPU, no checkpoint, no real-person media, no biometric evaluation, no cloud media upload. All seven human gates in the
[GPU readiness protocol](gpu-readiness.md) stay **pending**; `readiness/wan21-i2v-baseline.yaml` and
`provenance/model-candidates.yaml` are unchanged (`not_ready`). A rate card is not a quote, a merged PR is not an approval,
and a passing test is not evidence about a GPU.

**Issue:** [#18](https://github.com/FacialReplicationPrevention/FRP/issues/18) (parent [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9) stays open;
[#14](https://github.com/FacialReplicationPrevention/FRP/issues/14) stays blocked). **Builds on:** [gpu-readiness](gpu-readiness.md),
[procurement worksheet](private-run-procurement-worksheet.md), [security design](private-execution-security-design.md),
[runbook](wan21-private-execution-runbook.md), [Experiment 003](../experiments/003-wan21-i2v-baseline-design.md),
[Research 005](../research/005-wan-model-candidates.md). It adds **no code, schema or model pin**.

**Pinned target (unchanged):** `Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`;
`Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`; `use_prompt_extend: false`; the original reference
on both the CLIP-Vision and VAE first-frame routes; no LoRA, identity adapter or remote inference. Weight hashes, real
loader/encoder behaviour, VRAM and runtime are **unverified**.

## 0. Labels and how evidence was gathered

| Label | Meaning |
| --- | --- |
| **PROPOSED** | An FRP suggestion for a human to accept, change or reject. Not decided. |
| **PENDING** | A human decision or private record that does not exist yet. |
| **UNVERIFIED** | A claim not checked against a primary source by FRP (including any vendor figure below). |
| **[upstream-reported]** | Stated by the upstream project at the pinned commit; not reproduced by FRP. |
| **[vendor-snippet]** | Text of a vendor page as returned by a search tool on the stated date; the page itself was not opened. |
| **[secondary]** | A third-party aggregator or blog; may be stale or wrong. |
| **[derived]** | Arithmetic on the figures above, with the formula shown. |
| **[FRP-measured]** | Measured by FRP on real hardware. **None exists.** |

**Retrieval constraint (2026-11-03).** The agent environment that prepared this dossier could reach `github.com` and
`raw.githubusercontent.com` but not `huggingface.co` or any cloud-provider domain (DNS refused). Vendor figures were therefore
obtained only as **search-tool snippets** (dated below) and are **UNVERIFIED**; they were not read from the vendor's pages, and
snippets can interleave table columns. An operator must re-retrieve every figure from the vendor URL (the *retrieval path*
column) and record it, dated, in the private quote record. No figure here may be copied into a quote, cap or approval.

## 1. Gap / evidence matrix (decision → current facts → evidence required → source → owner → blocker)

"Owner" is a **role** that would make or supply the decision; no person is named or assumed. Every row is **PENDING** unless a
fact in column 2 says otherwise.

| # | Decision | Current facts (public) | Evidence still required (private) | Source / retrieval path | Owner role | Blocks |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Source/checkpoint licence permits this research use (gate 1) | Card/`LICENSE.txt` metadata Apache-2.0 [published, Research 005]; texts not re-read for obligations | Reviewer, date, texts read at the pinned revisions, conclusion, conditions | `LICENSE.txt` at `9737cba…`; model card at `6b73f84…` | Licence reviewer (qualified human) | gates 6, 7 |
| D2 | Adult, specific, withdrawable consent; lawful basis; ethics/legal (gate 2) | Procedure drafted ([gpu-readiness §5](gpu-readiness.md)); no consent exists | Consent record, age-verification method, ethics/legal outcome, withdrawal procedure, **retained-token decision** (design §3.4/§8.1) | Private | Responsible researcher + ethics/legal reviewer | gate 7 (and any real-person reference) |
| D3 | Restricted storage, retention, deletion (gate 3) | `LocalPrivateStore` CPU-tested (Linux only); volume locality is a private attestation | Access list, encryption statement, retention per artefact class, deletion incl. backups/provider copies, **local-volume attestation**, **ledger-key custody** | Design §3.1, §3.4, §8 | Data-protection owner | gates 6, 7 |
| D4 | Provider terms/DPA, region, logging, snapshots, deletion (gate 4) | No provider chosen; §3–4 below list questions only | Terms/DPA versions and dates, region, support-access and logging statements, biometric-upload position | Vendor legal pages (§4) | Legal/procurement reviewer | gates 5, 6, 7 |
| D5 | Dated quote, quota and **human-approved hard cap** (gate 5) | Rate cards only (§2); `cost_quote.status: not_obtained` | Dated vendor quotation or confirmed rate, quota, billing minimum, hard-stop mechanism, approved cap | Vendor sales/console (§2.3) | Budget approver (human) | gates 6, 7 |
| D6 | Hardware sufficiency (VRAM, host RAM, scratch) | Only upstream-reported **720P** peak memory (§2.1); no 480P figure; `t5_cpu`/multi-GPU refused by the adapter | A dated provider spec and, later, FRP-measured peak VRAM/RAM/runtime | §2.1 and gate 7 run | Technical reviewer | quote basis (gate 5) |
| D7 | Private runtime handoff (grant issuance/revocation, launcher, egress, hard kill, cleanup) | Public CPU contracts only; no granting provider exists by design | Private provider/launcher/runbook reviewed outside this repo; tests of the hard kill and egress block | §5 | Private-runtime owner | gate 7 |
| D8 | Checkpoint download and local SHA-256 (gate 6) | Hub-reported sizes only (≈ 82 GB); local digests: none | Separate approval, destination, expected file list, who runs it | Research 005 retrieval commands | Security owner + approver | gate 7 |
| D9 | Smoke-test controls frozen (prompt, seed, frames, steps, …) | Candidates in §6 are **PROPOSED** only | A recorded freeze before any output is seen; reviewed manifest | §6, [Experiment 003](../experiments/003-wan21-i2v-baseline-design.md) | Scientific lead | gate 7 |
| D10 | One specified smoke run (gate 7) | Nothing approved | Gates 1–6 recorded; frozen controls; stop conditions; exact run count; reference | §7 | Approver (human, separate from D5/D8) | execution |

## 2. Hardware, provider and cost evidence (no spend)

### 2.1 What the upstream project reports (the only memory/runtime evidence available)

| Item | Value | Label | Source (dated 2026-11-03) |
| --- | --- | --- | --- |
| Peak GPU memory, `I2V-14B`, **720P**, 1 GPU, `--offload_model True` | **76.7 GB** (identical on H20, A800/A100 and H800/H100 columns) | [upstream-reported] | Image [`assets/comp_effic.png`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/assets/comp_effic.png) (SHA-256 `b0e225caffb4b31295ad150f95ee852e4c3dde4a00ac8f79a2ff500f2ce26b8d`), referenced at [README L588–L606](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/README.md?plain=1#L588-L606); transcribed by FRP from the image |
| Total time, same configuration | 1491.6 s (H800/H100), 2715.5 s (A800/A100), 5494.8 s (H20) | [upstream-reported] | same; the note under the table says I2V-14B samples **40 steps** |
| Defaults for I2V at 480P | 40 steps, shift 3.0, guide scale 5.0, 81 frames, solver `unipc`, single-GPU `offload_model` default `True` | [source] | [`generate.py` L70–L89, L242–L246, L273–L276](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L70-L89) and [`image2video.py` L133–L144](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L133-L144) |
| Dependencies | `torch>=2.4.0` (FRP requires ≥ 2.6 for weights-only defaults), `flash_attn`, `imageio-ffmpeg`, and `dashscope` (remote client; must stay unused) | [source] | [`requirements.txt`](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/requirements.txt) |

**Why this is not a sufficiency claim.** (1) The figures are for **720P** (921,600 px), FRP's target is **480P** (`max_area` 399,360 px, ≈ 0.43 ×); no 480P figure was published or measured, and activation memory need not scale linearly. (2) Which checkpoint/precision/FRP wrapper produced the figures is not stated. (3) FRP's adapter adds metadata probes whose memory/time effect is unmeasured and **refuses** `t5_cpu=True`, FSDP/USP/multi-GPU and any precision other than the upstream config, so the usual VRAM-saving options are unavailable without a separately reviewed adapter change. (4) An 80 GB card has ≈ 3.3 GB (4 %) headroom over 76.7 GB **if** 480P used the same peak; the true 480P peak is **UNVERIFIED**. (5) 24 GB class GPUs are out of scope for this adapter. (6) Cross-hardware determinism is unknown (Research 005).

### 2.2 Candidate options (shortlist for comparison; **none selected**, none rented)

All rates are USD on-demand list prices from **search-tool snippets of 2026-11-03** (vendor pages not opened by the agent) and are **UNVERIFIED rate cards, not quotes**. "Retrieval path" is where an operator must re-read the figure.

| | **P1 — Lambda On-Demand Cloud, 1× H100 80 GB** | **P2 — Runpod Pod (Secure Cloud), H100-class** | **P3 — AWS EC2 `p5.4xlarge` (1× H100 80 GB)** |
| --- | --- | --- | --- |
| GPU / VRAM | H100 PCIe 80 GB; an SXM 80 GB 1× row also exists but its price was not legible in the snippet (a [secondary] page lists $4.29/GPU-h) | H100 NVL **94 GB** ($3.19/h); H100 PCIe 80 GB ($2.89/h, [secondary]); RTX Pro 6000 **96 GB** ($2.49/h; Blackwell — torch/flash-attn compatibility **UNVERIFIED**); H200 141 GB ($5.29/h) | H100 80 GB |
| vCPU / host RAM / local storage | 26 vCPU / 225 GiB / 1 TiB SSD (PCIe row) | NVL: 16 vCPU / **94 GB RAM**; disk size user-selected (limits **UNVERIFIED**) | 16 vCPU / 256 GiB / 1× 3,840 GB local NVMe [secondary] |
| List rate | **$3.29/h** (+ sales tax/VAT) | $3.19/h (NVL); $2.89/h (H100 PCIe, [secondary]) | from $5,022.40/month ⇒ **≈ $6.88/h** [derived: 5022.40 ÷ 730; [secondary] `cloudprice.net`, 2026-11-02; a second [secondary] source also says $6.88/GPU-h, "last verified July 2026"] |
| Billing granularity / minimum | One-minute increments from health-check pass to terminate; weekly invoices; filesystems per GiB-month in one-hour increments (docs example $0.20/GiB-month) | Per second; **prepaid credits**; billing runs every 5 minutes; balance $0 ⇒ running pods stopped (terminated, data unrecoverable, if no network volume); storage rates differ for running/stopped disks and network volumes (snippet columns ambiguous) | **Not retrieved** (per-second/minimum, EBS and data-transfer rates all unknown) |
| Egress / transfer fees | "No egress fees" (pricing page snippet) | "No fees for data transfer" (billing docs snippet) | **Unknown** |
| Hard-stop facts retrieved | Terminate via console/API ("erase data on instance"). **In-instance `shutdown`/`poweroff` is documented as *not working* and billing continues** ⇒ an on-instance timer is **not** a valid stop. No prepaid cap or spend limit found | Prepaid balance is a de-facto ceiling (deposit only the cap; auto-pay off); 5-minute billing lag can overshoot | AWS Budgets data is updated ≈ 3×/day (8–12 h apart) with up to 24 h delay ⇒ **alert, not a hard cap**; Budgets actions are delayed and not auto-reversed |
| Local vs network storage | Persistent **filesystems are NFS-mounted** (`/lambda/nfs/persistent-storage`) ⇒ **excluded** for the store and checkpoint (design §3.1); no quota; cannot be attached after launch; the 1 TiB root disk is a virtio device — whether it counts as "local block storage" is a **human attestation question** | "Network volumes" are network storage ⇒ excluded; container/volume disk locality **UNVERIFIED** | Instance-store NVMe is physically local (ephemeral); EBS is network-attached block storage (attestation question) |
| Isolation / terms signals | Terms/DPA/AUP **not retrieved** | Secure Cloud = T3/T4 data centres; Community Cloud = third-party hosts ⇒ **Community Cloud is a proposed no-go for any identifiable data**; DPA/SCC statements in docs (snippet) | Mature VPC/security-group egress control; DPA/Service Terms **not retrieved** |
| Region / residency | **Unknown** (region list not retrieved) | 30+ regions claimed; EU regions mentioned in GDPR docs | 11 regions list `p5.4xlarge` [secondary] |
| Quota / availability | **Unknown**; "listed pricing does not confirm regional stock" [secondary] | **Unknown** | **Unknown**; P-family quota and Capacity Blocks availability must be confirmed |
| Retrieval paths | <https://lambda.ai/pricing>; <https://docs.lambda.ai/public-cloud/billing/>; <https://docs.lambda.ai/public-cloud/filesystems/>; <https://docs.lambda.ai/public-cloud/on-demand/creating-managing-instances/> | <https://www.runpod.io/pricing>; <https://docs.runpod.io/accounts-billing/billing>; <https://docs.runpod.io/references/security-and-compliance> | <https://aws.amazon.com/ec2/pricing/on-demand/>; <https://aws.amazon.com/ec2/instance-types/p5/>; <https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html> |
| Snippet dates | pricing crawled 2026-11-03; billing/filesystem/instances docs crawled 2026-09-28 to 2026-11-03 | pricing "updated October 28, 2026" (crawled 2026-11-02); billing docs updated 2026-10-23 | cloudprice 2026-11-02; Budgets docs crawled 2026-10-26 |

**Reading the comparison (assessment, not a recommendation to rent).**
- *VRAM:* the three 80 GB rows leave ≈ 4 % headroom against the 720P upstream figure; 94–141 GB rows reduce out-of-memory risk at a higher hourly rate. Sufficiency is **UNVERIFIED** for every option.
- *Host RAM:* with `offload_model`, weights move between GPU and host memory and loading reads ≈ 82 GB of files. A 94 GB host (P2-NVL) may be tight; 225–256 GiB hosts are not. The real requirement is **UNVERIFIED** (the load path has never been run).
- *Isolation:* only P3 offers well-established guest-network control, but it is the most expensive and has the most quota friction; P1 and P2 egress controls (firewall/"block all after download") were **not established** from the retrieved text and are vendor questions.
- *Stop mechanics:* the three vendors need **different** hard-stop designs (§3.3). Do not assume a single supervisor works on all.
- Wan 2.1 weights come from Hugging Face; whether egress to it is possible from each provider and how it can be closed again afterward is part of the vendor question list below.

### 2.3 Exact questions to put to a vendor (to obtain a **dated quotation**)

For each shortlisted provider, in writing, recorded privately with date, channel and responder (no account identifiers in this repository):

1. For the exact SKU and region: hourly rate, currency, tax treatment, billing granularity, minimum charge, and what is billed between launch, health check, termination and *verified deletion*.
2. Storage: local scratch size and persistence on stop/terminate/failure; whether the root and data disks are local or network-backed; snapshot/image defaults; all storage, snapshot and transfer rates; how and when each is deleted.
3. Quota/stock: confirmed quota for this SKU in this region *now*, and the lead time to obtain it.
4. Spend control: is there a **provider-enforced hard spend limit** (not an alert)? Exact behaviour at the limit; reporting delay; whether running instances and storage are stopped, terminated or deleted.
5. Termination: an API/CLI **terminate** call that works from a separate machine; confirmation that in-guest shutdown behaves as stated; time to release; what remains billable after.
6. Network: can all outbound traffic be blocked at the provider/network level after the weight download, while leaving only an operator-controlled management channel; is there any provider telemetry or metadata egress from the guest?
7. Data handling: logging of guest content, support/administrator access, residency, subprocessors, backups/snapshots, retention and deletion SLAs; written position on processing biometric or biometric-derived data and on face media.
8. Terms: current Terms, AUP and DPA version/date; any clause restricting face/likeness processing or generated content.
9. Environment: GPU driver/CUDA versions available; whether a customer-supplied image is accepted and how its digest is exposed; whether `ffmpeg` and `flash_attn` build tooling are available offline.

### 2.4 Local scratch budget [derived; allowances are PROPOSED, not measured]

| Component | Size | Basis |
| --- | --- | --- |
| Checkpoint files at the pinned revision | ≈ 82.3 GB ≈ 76.7 GiB | Sum of the Research 005 hub-reported approximate sizes (65.6 + 11.4 + 4.8 + 0.5 GB); **not re-measured** — Hugging Face was unreachable from the preparing environment. Exact bytes/file count are a gate-6 item |
| Second copy if the download tool stages in a cache before moving | up to + 76.7 GiB | Avoidable by downloading in place; hashing can stream |
| Source checkout, CUDA/PyTorch environment, `flash_attn`, ffmpeg, logs, temporary and output video | **PROPOSED allowance 50 GiB** | No measurement exists; replace by an observed figure |
| **PROPOSED minimum local scratch** | **≥ 250 GiB** | ≈ 76.7 + 76.7 + 50 rounded up. Headroom is intentional; a measured value should replace it |

Compare: P1 1 TiB, P3 3,840 GB; P2 user-selected (verify the maximum and whether it is local).

## 3. Scenario-cost worksheet (illustrative arithmetic — not quotes, not caps)

**Formula.** `Spend_max = Σ stage_hours × hourly_rate (× billing-rounding) + storage (rate × GiB × time) + transfer + fees + tax + contingency`, where `stage_hours` runs from provisioning to *verified termination* (not just to the end of the clip).

**Unknowns that dominate `stage_hours` (none measured by FRP):** instance boot and image/environment build (including `flash_attn`); 82 GB download time and egress closure; local SHA-256 time; model load time; per-attempt generation time at 480P (the only reference is the 720P upstream figure 1491.6 s on H100-class, 2715.5 s on A100-class — a **proxy, not a bound**); evidence retrieval and deletion verification.

**Illustrative compute-only grid** (hours × list rate from §2.2; USD; excludes tax, storage, transfer and contingency; arithmetic checked by script on 2026-11-03):

| Rate source (UNVERIFIED rate card) | $/h | 2 h | 4 h | 8 h |
| --- | --- | --- | --- | --- |
| Lambda H100 PCIe 80 GB [vendor-snippet] | 3.29 | 6.58 | 13.16 | 26.32 |
| Lambda H100 SXM 80 GB [secondary] | 4.29 | 8.58 | 17.16 | 34.32 |
| Runpod H100 NVL 94 GB [vendor-snippet] | 3.19 | 6.38 | 12.76 | 25.52 |
| Runpod H100 PCIe 80 GB [secondary] | 2.89 | 5.78 | 11.56 | 23.12 |
| AWS `p5.4xlarge` [derived, secondary] | 6.88 | 13.76 | 27.52 | 55.04 |

The 2/4/8 h windows are **illustrative bounds for arithmetic**, not predictions: 2 h = tight (environment pre-built, nothing fails); 4 h = one pessimistic stretch; 8 h = rebuild/retry plus verification delays. **Storage and fees (where supported by retrieved text):** Lambda filesystem ≈ $0.20/GiB-month (not usable for the private store, so effectively $0 if none is created); Runpod disk/volume rates unclear from the snippet; AWS EBS/transfer **not retrieved**; Lambda and Runpod state no data-transfer fees. A failed or aborted attempt still bills — the grid already includes it only if it falls within the window.

### 3.1 Cap options for the budget approver (none is chosen here)

A cap is a **human decision under gate 5** and must be (a) accepted in writing before spend, (b) enforced **outside Python** (§3.3), and (c) at least the worst case under the enforced hard stop, otherwise it is not a cap.

| Option | Structure | What the approver must decide | Trade-off |
| --- | --- | --- | --- |
| **C1** | One bounded window of *H* hours covering download, hashing, load and one attempt | *H* and the contingency percentage; cap = quoted rate × *H* × (1 + contingency) + storage + fees + tax | Simplest; one approval of spend, but gate 6 and gate 7 still need **separate** approvals within it |
| **C2** | Two windows, each with its own cap: stage A = environment, download and hashing (gate 6; no personal data on the host), stage B = the single smoke attempt (gate 7) | *H_A*, *H_B*, whether the instance is terminated between them | Separates risk and approvals; if the instance is terminated, the ephemeral weights are lost and must be re-downloaded (spend ×2 for the download), unless a persistent **local** volume is attested |
| **C3** | Prepaid ceiling: fund the account with no more than the cap (where the vendor is prepaid, e.g. Runpod) | The funded amount; confirm auto-pay is off and the 5-minute billing lag is inside the contingency | A provider-enforced ceiling that does not depend on any FRP process; behaviour at $0 is destructive (data deletion), which is acceptable for an ephemeral run |
| **C4** | Independent financial limit (e.g. a funding source limited to the cap) combined with C1/C2 | Who holds the funding limit and what happens on a declined charge | Provider-agnostic backstop; not a substitute for an instance kill and may leave unpaid usage or a suspension |

Illustrative cap sizes for C1 are the §3 grid (e.g. 4 h at the quoted rate) **plus** contingency; **no number is proposed as "the" cap**.

### 3.2 Idle shutdown, emergency stop and hard-kill considerations

| Control | Requirement | Provider-specific note (from retrieved snippets; **verify**) |
| --- | --- | --- |
| Idle shutdown | If no job is active for *N* minutes, the instance is terminated by something other than the model process | Lambda: on-instance poweroff does **not** work ⇒ must be an off-instance watchdog calling the terminate API |
| Wall-clock deadline | Termination at *H* hours regardless of job state | Off-instance timer (separate trusted machine) **and**, where it works, an in-guest root-owned timer (defence in depth) |
| Emergency stop | A human can terminate in < 1 minute without the instance's cooperation; the procedure is **rehearsed on a zero-GPU or trivial instance**, never on a loaded one | Console and API terminate exist for P1; confirm for P2/P3 |
| Process hard kill | A supervisor that is not the Python process kills the process group at `max_attempt_seconds` + grace | `systemd` `RuntimeMaxSec=` is a candidate; **UNVERIFIED** by FRP |
| Spend ceiling | Provider-enforced if available (C3); alerts are **not** a cap | AWS Budgets lag (8–24 h) ⇒ alert only |
| Verified deletion | After termination, list and confirm that instances, volumes, snapshots, images and logs are gone; compare the final bill with the estimate | Record actual charges (readiness field `actual_charges`, private) |

## 4. Licence, intended-use and provider-terms questions (for qualified human review; **no approval**)

**Retrieved 2026-11-03 from GitHub at the pinned commit:** `LICENSE.txt` is the Apache License 2.0 text; the README "License Agreement" section ([L663–L664](https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/README.md?plain=1#L663-L664)) says the models are Apache-2.0, claims no rights over generated content, and that the user is "fully accountable" and the use "must not involve sharing any content that violates applicable laws, causes harm to individuals or groups, disseminates personal information intended for harm, spreads misinformation, or targets vulnerable populations". **Not retrieved** (Hugging Face unreachable): the checkpoint model card at `6b73f84…`. Retrieval path: <https://huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/blob/6b73f84e66371cdfe870c72acd6826e1d61cf279/README.md>.

| Gate | Question for the human reviewer | Evidence / source | Unresolved interpretation |
| --- | --- | --- | --- |
| 1 | Do the Apache-2.0 text and the README's additional accountability language permit a private, non-sharing technical test with benign neutral prompts? | Pinned `LICENSE.txt`, README L663–L664, model card at the pinned revision | Whether the README sentence adds restrictions beyond Apache-2.0; its application to biometric/likeness research. Human/legal judgement |
| 1 | Do the dependencies' licences (`flash_attn`, `torch`, `imageio-ffmpeg`/ffmpeg builds, CUDA stack, face evaluator later) matter for private research use? | Package metadata at the frozen environment | Not reviewed |
| 2 | Is the processing (generation, later similarity measurement, human review) of a real adult's face lawfully based, consented, withdrawable and ethics-reviewed; may keyed pseudonymous ledger tokens/tombstones survive withdrawal? | Private consent record, ethics/legal outcome | Jurisdiction-dependent; open per design §8.1 |
| 3 | Do retention/deletion rules cover source media, outputs, derived data, logs, backups, provider snapshots and the ledger key? | Private | Deletion verification method on a vendor platform |
| 4 | Does the provider's Terms/AUP/DPA permit face/likeness processing, and what logging, support access, snapshotting, subprocessing, residency and deletion apply? | Terms, AUP, DPA and Service Terms with version and date, per provider | Not retrieved for any provider; Runpod's public docs (snippet) state Community hosts are third-party and that Secure Cloud uses T3/T4 data centres; Lambda and AWS terms unread |
| 4 | Is uploading a **real person's portrait** to a rented GPU allowed at all for this first test? | Gate 2/3/4 decisions | See reference-class options R1–R3 in §6.1 |

No provider-terms clause was read or interpreted in preparing this dossier, so **no statement here is a terms finding**.

## 5. Private security and environment handoff (contracts only; nothing here executes)

**Scope.** This section reconciles the residual risks listed in [PR #17](https://github.com/FacialReplicationPrevention/FRP/pull/17)'s final review and the [security design §8](private-execution-security-design.md#8-blockers-surfaced-not-resolvable-in-public-cpu-safe-code-no-gate-weakened). `DenyAllAuthorisation` and `DenyAllReviewAccess` remain the **only** operative public providers. This repository must never receive a granting provider, test grant, activation CLI, approved private runtime configuration, secret, storage path, hash of a privately obtained asset or an executable path to real generation. Windows/macOS identifiable storage stays refused.

### 5.1 Residual risk register

| # | Residual risk (source) | What public CPU code does today | What stays private / unverified | Owner role | Verification path before gate 7 |
| --- | --- | --- | --- | --- | --- |
| R1 | **Grant issuance, authenticity, revocation** (design §3.5, §8.2) | Enforces an *identical canonical grant* at A0–A3 and refuses any change under one id; no provider grants anything | Who issues, how grants are authenticated/signed, revocation source and latency, how an unchanged grant is returned | Private-runtime owner | Private provider reviewed outside this repo; a test of revoke-then-attempt on synthetic runs in the private environment |
| R2 | **Ledger-key custody and keyed-token / tombstone retention vs withdrawal** (§3.4, §8.1) | HMAC-keyed attempt markers and tombstones survive deletion and withdrawal; `erase_store` is the irreversible alternative | Key location, backup and destruction; whether retention is lawful and consented (gate 2/3); losing the key forfeits replay protection, leaking it makes tokens linkable | Data-protection owner + legal reviewer | Written retention decision; key-custody record; a rehearsed **revoke → tombstone → delete** drill on a synthetic store, confirming the order |
| R3 | **Local-volume attestation** (§3.1, §8.4) | Refuses non-canonical, non-owner-only roots; cannot see filesystem type | Attestation that store root **and** checkpoint volume are local, not NFS/SMB/FUSE/synced folders; definition of "local" for cloud block volumes (e.g. a virtio root disk, EBS) | Data-protection owner + technical reviewer | `findmnt -T <path>`-style inspection by the operator recorded privately; **human decision on whether a virtualised block device qualifies** (§9, Q6). Vendor example: Lambda persistent filesystems are NFS and must not be used |
| R4 | **Owner-only storage, backups, snapshots** | Owner-only, no-follow storage on Linux | Backup/snapshot/image policy on the provider; deletion of derived copies | Data-protection owner | Provider-side inventory after teardown (§3.2 last row) |
| R5 | **Externally enforced time/spend limits** (§3.5, §8.3) | `max_attempt_seconds` polled before the reference opens and before every denoiser call; ≤ 24 h grant lifetime | Python cannot interrupt model load, text/CLIP/VAE encode, VAE decode or ffmpeg; provider hard stop and spend ceiling | Budget approver + private-runtime owner | Hard-kill drill on a trivial instance (§3.2); written provider answers to §2.3 Q4–Q5 |
| R6 | **Process / ffmpeg egress** (§3.7) | In-process socket guard; `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` required | Provider/host egress block (the guard cannot see subprocesses such as ffmpeg, git or native extensions) | Private-runtime owner | Attempted outbound connection from a sacrificial process **on the instance, before any private data**, observed to fail; recorded |
| R7 | **Incident cleanup** | `cleanup()` and inode-checked rollback; a killed process can leave a reservation or partial file that blocks that attempt index | Whole-instance and provider-side deletion; leak response | Data-protection owner | Written incident procedure; deletion verification list |
| R8 | **Fresh checkout, `python -I -B`, sanitised environment** (§3.6, §5.8) | Refuses unclean/unpinned checkout, symlinks, `LD_PRELOAD`/`LD_AUDIT`/`IMAGEIO_FFMPEG_EXE`; requires an isolated interpreter | The launcher that actually sets this; a fresh clone every run | Private-runtime owner | Launcher reviewed privately; `git status --porcelain` empty and `git rev-parse HEAD` = pin recorded |
| R9 | **CUDA / driver / GPU / container-image / ffmpeg provenance** (§3.6; worksheet §2) | Environment digest covers installed distributions and the Python version only | Driver and toolkit versions, image digest, kernel, GPU firmware, ffmpeg binary identity | Private-runtime owner | Values recorded in the private record before load; mismatch with the approved record = NO-GO |
| R10 | **Pinned `.pth` weights-only compatibility** (runbook §5) | Requires torch ≥ 2.6, refuses the override variable and extra pickle files; fail-closed if a load fails | Whether the T5, VAE and CLIP `.pth` files load under weights-only unpickling is **unverified**; there is **no unsafe fallback** | Technical reviewer | Observed only in the gated run; a refusal there is a gate-7 **finding**, not a reason to relax the loader |
| R11 | **`cache_video`/ffmpeg staged-file inode behaviour** (runbook §8) | Deferred commit refuses (fail-closed) if the encoder replaces the staged partial's inode | Real encoder behaviour is **unverified**; a change to the adapter would need a separate reviewed PR | Technical reviewer | Observed only in the gated run (T8 in §6.2) |
| R12 | Same-uid/root TOCTOU (design §8.5) | Documented residual | Single-tenant, ephemeral, credential-free host | Private-runtime owner | Accepted-risk entry in the private record |
| R13 | Reference transfer and output retrieval across an egress-blocked host | None | **Open design question:** how references enter and outputs leave a host whose outbound traffic is blocked (e.g. an operator-initiated transfer on an allow-listed management channel) without a cloud media upload to any third party | Private-runtime owner + data-protection owner | Written transfer design reviewed under gates 3 and 4 |

### 5.2 Fail-closed inspection and stop checklist for a later, separately authorised run

This is an **evidence checklist, not a command**. Each line is a human-attested fact recorded in the private record. **"No" or "unknown" on any line is NO-GO (before the run) or STOP (during it).** Nothing here may be scripted into this repository.

*Before any spend:* (1) gates 1–5 recorded and current; none contradicted by a later change of terms, price, licence or consent; (2) quote dated and unexpired, hard cap approved, enforcement mechanism named and rehearsed; (3) vendor answers to §2.3 stored; (4) incident contact and withdrawal procedure exist.

*After provisioning, before weights or data:* (5) instance type/region/GPU equal the quote; (6) local-volume attestation recorded for store and checkpoint volumes; (7) driver/CUDA/image/ffmpeg identities recorded; (8) fresh clone at `9737cba…`, clean; (9) environment installed from the frozen specification, torch ≥ 2.6; (10) offline variables set, `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`, `LD_PRELOAD`, `LD_AUDIT`, `IMAGEIO_FFMPEG_EXE` absent; (11) hard-kill supervisor and external watchdog running; (12) egress policy staged for the post-download state.

*Gate 6 stage (separate approval; no personal data on the host):* (13) download only the pinned revision; (14) file list equals the Hub list at that revision, nothing extra; (15) local SHA-256 of **every** file recorded privately and compared with Hub-reported values; any mismatch = STOP; (16) egress closed and **demonstrated** closed before any reference arrives.

*Gate 7 stage:* (17) grant is the approved one, unexpired, un-revoked, single run, attempt cap 1; (18) reference bytes hash equals the grant; (19) no remote service, no prompt extension, no LoRA/adapter loaded; (20) resource monitors running outside the Python process.

*Stop immediately, then terminate, then verify deletion, then record:* a cost/quota event not in the plan; elapsed time at the deadline; unexplained egress attempt; evidence of a non-consenting or underage person; a withdrawal; a hash or provenance mismatch; unexpected files or processes; any sign of a leak; a request to relax a refusal to "make it work".

*Close-out:* (21) outputs only in approved private storage; (22) every instance/volume/snapshot/image/log deleted and listed; (23) actual charges recorded against the cap; (24) every attempt (including refusals and kills) accounted for; (25) ledger/token retention applied as decided under R2.

## 6. Proposed minimal technical smoke-test specification (`smoke-spec-0.1-proposed`) — NOT AUTHORISED, NOT EXECUTED

Everything below is **PROPOSED** for human freeze under gate 7 and Experiment 003 §7. It is a technical pipeline test, not calibrated science, and it must not be started or tuned after seeing any output. Candidate defaults are copied from the pinned upstream source read on 2026-11-03; the readiness template deliberately does **not** adopt upstream defaults automatically, so each is a decision.

### 6.1 Controls

| Control | PROPOSED value | Basis | Status |
| --- | --- | --- | --- |
| Run role / count | `smoke`; **1** planned run, `max_attempts: 1`, grant attempt cap 1 | Experiment 003 §2, design §3.5 | PENDING (freeze) |
| Retries | None automatic. A second attempt needs a new gate-7 decision, a new grant and a higher ledger index (spent indices never reopen). A pre-load refusal is an *unexecuted* run, not a failed attempt (design §5.9) | Design §5 | PENDING |
| Source / checkpoint | pins above; `use_prompt_extend: false`; original reference to both routes; no adapter/remote service | AGENTS.md; runbook | **Decided** |
| Prompt | `prompt_template_version` = `smoke-neutral-v0.1`; text: "A person in a softly lit room looks toward the camera with a neutral expression, then slowly turns their head slightly to one side and back." Neutral motion only; negative prompt = upstream config default | The synthetic example prompt is illustrative; this text is a new proposal | PENDING |
| Seed | one arbitrary non-negative integer in [0, 2³²−1], drawn once and recorded before any run (candidate `2026110301`); never chosen after viewing outputs | Adapter refuses negative seeds | PENDING |
| Frame count | **81** (= 4·20+1) | Upstream default, `generate.py` L84–L85 at the pinned commit | PENDING |
| Resolution label | `480*832` (portrait reference); expected output geometry computed offline with the existing CPU helper `expected_geometry`: a 832-high × 480-wide reference gives 832×480 with no refusal (a 480-high × 832-wide landscape reference would give **464×832** because of upstream float arithmetic) | `frp.baseline.wan21_adapter`, runbook §3 | PENDING |
| Sampler / steps / shift / CFG | `unipc` / **40** / **3.0** / **5.0** | Upstream I2V-480P defaults, `generate.py` L70–L81 and L242–L246 at the pinned commit | PENDING |
| Precision | `upstream-i2v-14B-config` (the only label the adapter accepts) | Runbook §3 | PENDING (open review item 1 in runbook §10) |
| Offload | `offload_model: true`; `t5_cpu`, FSDP/USP/multi-GPU refused | README footnote (2); adapter | PENDING |
| Image preprocessing | `RGB` conversion by the adapter; EXIF orientation applied by the *private reference provider* before hashing; version label `smoke-pre-v0.1` | Runbook §3 | PENDING |
| Sampled frames | `0, 20, 40, 60, 80` (candidate; frozen before any viewing); frame 0 reported separately | Experiment 003 §4 | PENDING; only relevant if any face check is run |
| Monitoring | Outside Python: GPU memory/utilisation sampling and host RAM/disk to a private log (no media, no paths in public); provider console for billing; wall-clock timer | §3.2, §5.2 | PENDING; peak VRAM sampled at an interval can miss a peak (see §10, G1) |

**Offline check of the proposed values (2026-11-03, CPU only).** A temporary copy of `examples/manifests/synthetic-baseline-dry-run.yaml` (not committed) with `run_role: smoke`, one synthetic identity with `identity_split: null` (the implemented smoke rule; Experiment 003 §3 only says "no split"), one prompt, one seed and the control values above (`resolution: "480*832"`, `frame_indices: [0, 20, 40, 60, 80]`, the rest as tabulated) was accepted by the strict loader: `frp baseline-plan` exit 0, role `smoke`, 1 planned run, claims `technical_smoke_only`, **NOT EXECUTION READY** (hashes, environment digest, GPU model unset; no authorisation mechanism; live backend disabled). This shows only that the proposal is *syntactically* consistent with the manifest contract; it does not exercise the adapter's runtime refusals and says nothing about a GPU.

**Reference class (human decision R).** *R1* — one consenting verified adult (Experiment 003 §2 default; requires gate 2 and the private transfer in R13). *R2* — **PROPOSED for consideration:** a licence-verified synthetic portrait that does not depict a real person, because a technical smoke test needs no real identity and this removes real-person biometric transfer from the first spend; it **deviates from Experiment 003's "consented adult"** wording, needs an explicit recorded decision (including whether gate 2 may record "no real person" — an agent cannot decide this), and synthetic faces can resemble real people and carry their own licences. *R3* — a non-face technical image: exercises the pipeline and probes but not face-detection sanity. **This dossier selects none.**

### 6.2 Technical success and failure criteria (the run is a **failure** unless every T-item holds)

| # | Criterion | Evidence (private) |
| --- | --- | --- |
| T1 | Executed source commit, checkpoint revision and **locally hashed** weights equal the approved pins | `git rev-parse HEAD`; gate-6 digest record; executor provenance |
| T2 | Environment digest, driver/CUDA, image digest, ffmpeg identity equal the approved record | Private record (R9) |
| T3 | Result is **real**, not simulated: the backend declared `live` and the real runtime type loaded; the record is not marked simulated; a fake-runtime result never counts | `ExecutionRecord` / adapter info |
| T4 | `use_prompt_extend` off, no remote module imported, **zero** blocked network attempts, and external egress observed closed | Executor guards; R6 evidence |
| T5 | Original reference reached CLIP and VAE routes and both CFG branches; denoiser pairs = `sampling_steps` (40) | Probe metadata (shapes, dtypes, devices only) |
| T6 | Output tensor/geometry `(3, 81, h, w)` equals the expected geometry | Executor output check |
| T7 | Artefact exists **only** in approved private storage under a private reference; nothing in the public repo, CI, issue or log | Close-out list |
| T8 | Deferred commit succeeded under the real encoder (inode preserved) *or* the refusal is recorded as a finding | Attempt record |
| T9 | Loader outcome recorded: whether `.pth` files loaded weights-only on the pinned torch (R10) | Attempt record |
| T10 | Measured resource and cost: wall time per stage, GPU-seconds (wall-clock of `generate`), peak VRAM and host RAM **as sampled**, and the provider's **actual charge** against the cap | Private log + invoice |
| T11 | **Full attempt accounting:** every attempt, refusal, abort and kill recorded; a missing, truncated or failed output is a **FAIL**, never discarded or re-run silently | Attempt ledger, billing lines |
| T12 | Every stop condition in §5.2 either did not occur or was handled as specified | Operator record |

Outcomes: **PASS-technical** (T1–T12 all hold), **FAIL** (any T-item fails or output missing), **INCONCLUSIVE** (monitoring or evidence gap). A failed or inconclusive run is reported with its cost; it neither proves nor refutes anything about Wan's identity behaviour.

### 6.3 What a technical smoke test cannot prove

It does **not** show identity reproduction, a similarity level, protection, any property of the A/B/C/D pathways, a population effect, determinism across GPUs, video utility, or that the detector or recogniser works. At most it shows that the pinned pipeline ran once under the frozen controls on one reference, with the recorded resources and charges. A decrease or increase in face similarity from one clip means nothing.

**Follow-on, separate and later (not started here):** consenting adults and identity-disjoint calibration data; detection/utility measurement with failures kept; a second evaluation method; identity-clustered uncertainty; a predeclared minimum of valid later frames and attempt-selection rule (Experiment 003 §7 decisions 2 and 4, still open); and private original-versus-generated review. Only then can a baseline be claimed, and A/B/C/D (Milestone 005 / #14) stays blocked until that baseline is accepted.

## 7. Seven-gate go/no-go table (all **pending**; public schema 1.0 cannot express anything else)

A gate is decided only by a named human in a private record. The table gives what would be needed. "Blocks" lists what stays forbidden until the gate is separately decided.

| # | Gate | Private evidence needed | Decision-maker role | Prerequisites | Status | Next human action | Blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `licence_and_intended_use` | Licence texts at the pinned revisions (source `LICENSE.txt`, README L663–L664, model card), dependency licences, written conclusion and conditions | Qualified licence reviewer | None; re-open on any pin or licence change | **pending** | Read the model card and decide the §4 question | Gates 6, 7 |
| 2 | `consent_and_data_processing` | Per-participant consent, age verification, lawful basis, ethics/legal outcome, withdrawal procedure, retained-token decision — **or** a recorded determination that no real person is involved (R2/R3) | Responsible researcher with ethics/legal reviewer | Decision on reference class R | **pending** | Choose R; start the consent/ethics process if R1 | Gate 7; any real-person reference |
| 3 | `restricted_storage_retention_deletion` | Storage location/access list, encryption, retention per class, deletion procedure including backups and provider copies, local-volume attestation, ledger-key custody | Data-protection owner | Decisions on R3 definition, R2/R13 | **pending** | Decide attestation wording and retention; draft deletion drill | Gates 6, 7 |
| 4 | `cloud_provider_terms` | Terms/AUP/DPA versions and dates, residency, logging, snapshots, support access, biometric-upload position, written vendor answers (§2.3) | Legal/procurement reviewer | Provider shortlist | **pending** | Shortlist ≤ 2 providers and send §2.3 questions | Gates 5, 6, 7 |
| 5 | `quote_and_budget_cap` | **Dated vendor quotation**, quota confirmation, billing minimum, enforcement mechanism, **user-approved hard cap**, shutdown policy; approver | Budget approver (human) | Gate 4 reviewed for the chosen provider | **pending** | Pick a cap option C1–C4 and amounts after a real quotation | Gates 6, 7 |
| 6 | `checkpoint_download_and_hashing` | **Separate** approval; destination, who runs it, expected file list, local SHA-256 of every file; no personal data on the host | Security owner with approver | Gates 1, 3, 4, 5 recorded; fresh decision at the time | **pending** | None until 1, 3, 4, 5 are decided | Gate 7; any download or hashing |
| 7 | `gpu_smoke_test` | **Separate** approval of **one** specified run: frozen controls (§6.1), stop conditions (§5.2), the reference, exact run count, grant citing records 1–6 | Approver (a different decision from 5 and 6) | Gates 1–6 recorded; private provider/launcher reviewed; hard-kill drill done | **pending** | None until 1–6 are decided | All execution |

`readiness/wan21-i2v-baseline.yaml` stays fully `pending` with `approval_record: null`; `provenance/model-candidates.yaml` stays `not_ready`. A filled field, a valid `frp readiness` result, a passing test, a merged PR or a vendor price approves nothing.

## 8. Explicit no-go conditions

Any of these means **NO-GO** until a human re-reviews and records the change:

1. Any of gates 1–7 not decided in a private record, or any earlier gate later contradicted.
2. No dated vendor quotation, no confirmed quota, or no user-approved hard cap; a cap that depends on Python or on an alert with reporting delay.
3. No tested emergency termination and no external watchdog; on Lambda, reliance on an on-instance shutdown; on AWS, reliance on Budgets alone.
4. No attested **local** store/checkpoint volume (NFS/SMB/FUSE/synced folders, Lambda persistent filesystems, Runpod network volumes, or an undecided block-volume definition).
5. Egress not demonstrably blocked after the download; no reviewed channel for reference/output transfer (R13).
6. Provider terms/DPA unread or not permitting the workload; Runpod Community Cloud or any multi-tenant third-party host for identifiable data.
7. Any real-person reference without gate 2 consent and withdrawal procedure; any minor, third party, or sexual/deceptive prompt.
8. Pin change, licence/terms/price change, hash mismatch, unexpected files, or an unclean or unpinned checkout.
9. Environment not frozen, torch < 2.6, a requested relaxation of a refusal (`t5_cpu`, precision, loader), or a request to enable prompt extension, LoRA or any remote service.
10. Granting provider, activation flag, test grant or private path present in the public repository.
11. Evidence gaps: a missing T-item in §6.2 is a FAIL, not a reason to rerun unplanned.

## 9. Decisions only humans can make (exact list)

1. **Provider shortlist** (≤ 2) from §2.2, or others; and whether larger-VRAM SKUs are preferred over 80 GB SKUs given the unmeasured 480P peak.
2. **Region/residency** acceptable under gate 2/4.
3. **Cap option** (C1–C4), *H* hours, contingency percentage and the dollar cap — only after a dated quotation.
4. **Who enforces the hard stop** and who holds the emergency-stop credentials (and that they are separate from the run operator where possible).
5. **Reference class R1/R2/R3** and, if R2 or R3, whether gate 2 may record "no real person".
6. **Definition of "local block storage"** for virtualised cloud volumes (virtio root, EBS, instance store) for the attestation.
7. **Retained-token decision**: suppression (tombstones) versus whole-store erasure, and ledger-key custody.
8. **Freeze or amend** every §6.1 control before any output is seen.
9. **Separate approvers/records** for gates 5, 6 and 7.
10. **Reviewed channel** for moving a reference in and an output out of an egress-blocked host (R13).
11. Whether to request the narrow follow-up issues in §10.

## 10. Software gaps found (to propose as separate issues; **none implemented here**)

| # | Gap | Why it is separate |
| --- | --- | --- |
| G1 | The adapter records `gpu_seconds` but **not peak VRAM or host RAM**; external sampling can miss a peak. A metadata-only `torch.cuda.max_memory_allocated` record would help T10 | Touches the adapter and result contract; needs its own review and CPU-fake tests |
| G2 | Weight digests cannot be marked `verified` under provenance schema 1.0 | Needs a separately reviewed schema version (AGENTS.md); nothing changed here |
| G3 | The private launcher, grant provider, hard-kill supervisor and transfer channel (R1, R5, R13) have no home | Must live **outside** this public repository; a design for a private repo or runbook is the proposal |
| G4 | If R10 or R11 surface in the gated run, the adapter may need a reviewed fix | Cannot be known on CPU; never relax a refusal to pass |

## 11. Verification record

Offline, CPU-only checks run on this branch on 2026-11-03 (results are recorded in the PR description; they say **nothing** about GPUs, weights or runtime):

- `frp provenance provenance/model-candidates.yaml` — exit 0; every candidate `NOT READY`.
- `frp readiness readiness/wan21-i2v-baseline.yaml --provenance provenance/model-candidates.yaml` — exit 0; all gates `pending`; cost quote `not_obtained`; hardware requirements all unverified.
- `frp baseline-plan examples/manifests/synthetic-baseline-dry-run.yaml` — planning only.
- No code, schema, readiness template, provenance inventory or model pin was changed.
