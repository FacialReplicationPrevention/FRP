# Conditional GPU provider decision and procurement handoff (Milestone 004, PR 3F)

**Status: PLANNING ONLY. NO GPU / NO WEIGHTS / NO REAL MEDIA / NO INFERENCE / NO SPEND. ALL SEVEN HUMAN GATES PENDING. NOTHING AUTHORISED.**
No account, vendor contact, quote request, rental, download, hash, image or run exists. A ranking is not a vendor selection, a list rate is not a quote, and a merged PR approves
nothing. `readiness/wan21-i2v-baseline.yaml` (all gates `pending`) and `provenance/model-candidates.yaml` (`not_ready`) are unchanged, as are the pins
(`Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`; `Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`), `use_prompt_extend: false` and the
original CLIP/VAE/CFG controls. Issue [#23](https://github.com/FacialReplicationPrevention/FRP/issues/23); parent [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9) stays open,
[#14](https://github.com/FacialReplicationPrevention/FRP/issues/14) stays blocked. This file links, and does not reproduce, the [3D dossier](gpu-go-no-go-dossier.md) (`D§n`) and the
[3E evidence delta](gpu-evidence-delta.md) (`E1–E12`, `V1–V9`, `B1–B8`). Gate order and stop rules in [gpu-readiness.md](gpu-readiness.md) take precedence.

## 1. Decision / status

| Question | Provisional answer |
| --- | --- |
| Overall | **NO-GO to procure or run.** Every decision-critical control below is unverified for both providers. |
| Which provider is investigated first? | **Lambda On-Demand, 1× H100 PCIe 80 GB — conditional preference for further procurement verification only.** |
| Fallback | **Runpod Secure Cloud, H100-class (NVL 94 GB listed) — conditional fallback.** Community Cloud stays excluded for any identifiable data (D§8-6). |
| If neither can clear §4 | **NO PROVIDER.** The next action is to stop and escalate, not to design a workaround. |
| Who selects | The budget approver, legal/procurement reviewer and data-protection owner, in private records, gate by gate. Nothing here selects. |

**Why Lambda first (verified or scoped evidence only).** (a) A published host spec of 225 GiB RAM / 1 TiB SSD (L1) versus no host RAM or scratch limit in Runpod's documentation (R2);
this matters because loading ≈ 82 GB of checkpoint files with offload needs large host RAM and scratch (D§2.4; the real need is unmeasured). (b) Lambda's docs are described as covering
VM instances (L2), whereas Runpod's docs state each Pod is a multi-tenant *container* (R3); a dedicated-VM boundary is *unconfirmed* for Lambda but a container boundary is *stated* for Runpod.
**Against Lambda:** 80 GB leaves ≈ 4 % headroom (80 − 76.7 = 3.3 GB) over the *720P* upstream peak, versus ≈ 23 % for 94 GB (94 − 76.7 = 17.3 GB). That arithmetic assumes equal units and a 480P peak equal to
720P; neither 480P need nor sufficiency of 80 or 94 GB is measured, and VRAM can only be measured at gate 7, i.e. after spend. An out-of-memory result on 80 GB is therefore a plausible, recorded
smoke failure (D§6.2), and moving to a larger SKU needs a fresh quote and approval. **For Runpod:** a documented prepaid-balance mechanism (R1) is the nearest thing to a spend ceiling in either
evidence set, but it is a rate limit plus balance, not a verified total/liability cap. **The ranking is fragile**: it rests on a published spec and an unconfirmed isolation inference, and it
reverses on the triggers in §4.

## 2. Evidence table

Labels as in [3E §0](gpu-evidence-delta.md). Nothing is FRP-MEASURED. Only text/metadata was read; no billing console, account action, calculator or form was used.

| ID | Claim | Label and scope | Not supported by it |
| --- | --- | --- | --- |
| L1 | Lambda 1× H100 PCIe 80 GB, 26 vCPU, 225 GiB RAM, 1 TiB SSD, USD $3.29 per GPU-hour plus tax; docs SKU table "as of December 2025" | **PRIOR-RETRIEVAL** — Ada's independent read of `lambda.ai/instances`, 2026-11-04 (3E §1, E5). **Not re-read here** (DNS failure, §2.1) | Quote, region, stock, quota, currency beyond USD, billing minimum |
| L2 | Lambda on-demand docs cover VM instances, root storage, NFS filesystems, regions, base images | **PRIOR-RETRIEVAL** — Ada, `docs.lambda.com/public-cloud/on-demand/`, 2026-11-04; summary only | Which page states what; dedicated-VM/GPU-passthrough boundary |
| L3 | Terminate via console/API; in-guest poweroff does not stop billing; one-minute increments; no egress fee; persistent filesystems are NFS | **SECONDARY** (3D search snippets 2026-11-03); NFS partly covered by L2 | Anything about guest-independent kill being sufficient |
| L4 | Spend limit or liability bound, outbound deny, quota, Terms/AUP/DPA, snapshots, post-stop charges, API credential scopes | **UNVERIFIED** — nothing found; absence from a summary is not proof the vendor cannot offer it | — |
| R1 | Prepaid credits; billing every 5 min; $0 balance stops Pods (terminates, unrecoverable, if no network volume); auto-pay at most hourly; minimum one hour of credit to deploy; default spend limit **$80/h** across all resources; credits non-refundable; prepaid *cards* "should deposit at least $100 per transaction" | **PRIMARY-VENDOR** — `runpod/docs` @ [`93f2147…`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/accounts-billing/billing.mdx) (committed 2026-11-04T15:16:02Z), read 2026-11-04; rendered pages not opened. GitHub compare shows only `serverless/endpoints/endpoint-configurations.mdx` changed since the 3E commit `bb50dd3`, so 3E §4.2 statements are textually unchanged | A total cap, a liability bound, or invoice terms; GPU rates (docs say rates are shown in the console) |
| R2 | GPU catalogue lists H100 SXM 80, H100 PCIe 80, **H100 NVL 94 GB**; no host RAM/vCPU listed. "$3.19/h, 16 vCPU, 94 GB RAM" is **SECONDARY** (3D); the 94 there is host RAM, a *different* quantity from the 94 GB device VRAM | **PRIMARY-VENDOR** ([`references/gpu-types.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/references/gpu-types.mdx)) for the catalogue only | Which SKU is offered in which region; host RAM; rate |
| R3 | "Multi-tenant environment with containerized isolation"; Secure Cloud in T3/T4 data centres; host terms prohibit inspecting Pod data; SOC 2/ISO 27001/PCI DSS stated for "vetted infrastructure partners"; GDPR statement for EU regions | **PRIMARY-VENDOR** ([`security-and-compliance.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/references/security-and-compliance.mdx)). Compliance statements are not contract terms | DPA, subprocessors, biometric position, Terms/AUP (**not read**) |
| R4 | Storage: container disk $0.10 (erased on stop); volume disk $0.10 running / **$0.20 stopped**, kept until Pod deleted, labelled "fast (local)"; optional volume encryption (no BYOK); network volume and **new:** beta *global volume* ($0.09/GB-month + IOPS) are network storage; "GB" undefined | **PRIMARY-VENDOR** ([`pods/storage/types.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/pods/storage/types.mdx), [`pods/pricing.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/pods/pricing.mdx)) | Whether `/workspace` is a host-local block device, bind mount or overlay; snapshots; provider-initiated data migration (the zero-GPU page describes copying a Pod's data to another machine) |
| R5 | Stop keeps `/workspace` and keeps billing it; terminate deletes it; CLI/REST/console terminate exist; the docs' stop-timer example runs *inside* the Pod. **New:** team roles (Dev can create/delete/start/stop Pods and cannot see billing; Billing cannot touch compute); API keys are All/Restricted/Read-only, with per-API access levels | **PRIMARY-VENDOR** ([`manage-pods.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/pods/manage-pods.mdx), [`manage-accounts.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/accounts-billing/manage-accounts.mdx), [`get-started/credentials.mdx`](https://github.com/runpod/docs/blob/93f2147761903839f4a2b3e595117f4f20fd9a89/get-started/credentials.mdx)) | A **terminate-only Pod credential** (not found); that a Dev-role key cannot also create Pods and so spend |
| R6 | No setting to block outbound traffic was found in the Pod networking/storage/pricing pages, or by searching the docs source for "firewall"/"outbound" | **PRIMARY-VENDOR, absence only.** Not proof that Runpod cannot offer it | Anything either way |
| U1 | Upstream peak 76.7 GB is for **720P**, 1 GPU, offload; 480P peak, runtime and compatibility on any SKU | **UPSTREAM-REPORTED** (D§2.1); **UNVERIFIED** for FRP 480P | Sufficiency of 80 GB or 94 GB |
| H1 | Hugging Face pinned card/tree: Ada's read (3E §1) stands at its scope; recursive inventory, Xet/LFS/Git identifiers and local hashes absent; **licence metadata is not human licence approval** | **PRIOR-RETRIEVAL**; author retry failed again | Gate 1, gate 6 |

### 2.1 Retrieval delta (2026-11-04, ≈ 15:18 UTC; agent sandbox; plain text only)

| Endpoint attempted | Method | Result |
| --- | --- | --- |
| `lambda.ai/instances`, `lambda.ai/pricing`, `docs.lambda.ai/public-cloud/on-demand/`, `docs.lambda.com/public-cloud/on-demand/` | `curl`; for `lambda.ai/instances` also the agent web-fetch tool | No connection (HTTP status `000`; "No address associated with hostname") |
| `www.runpod.io/pricing`, `docs.runpod.io/pods/pricing` | `curl`; `docs.runpod.io` also web-fetch | Same |
| `huggingface.co/Wan-AI/Wan2.1-I2V-14B-480P/raw/6b73f84…/README.md` | `curl`, web-fetch | Same |
| Name resolution for `lambda.ai`, `docs.lambda.ai`, `runpod.io`, `docs.runpod.io`, `huggingface.co` | `getent hosts` | No answers |
| `api.github.com` (`runpod/docs` @ `93f2147…`) | GitHub API, read-only | Reachable → R1–R6 |
| Official Lambda documentation source on GitHub | Repository search of the `lambdal` organisation | None found → Lambda stays on L1–L2 (Ada) and L3 (secondary) |

L1/L2 and H1 are **not upgraded**; they keep 3E's attribution. 3E's independent Ada reads and Runpod `bb50dd3` reads are preserved at their original scope; no moving `main` reference is used.
**Operator evidence request (privately, on a networked machine, metadata only, no login or calculator):** re-read the Lambda pricing and on-demand/billing/filesystem pages, the Runpod public
pricing and legal pages and the pinned Hub card/tree; record URL, date, effective date, exact line and currency/region scope in the private record.

## 3. Distinctions this decision depends on

| Never equate | With |
| --- | --- |
| Published hourly list rate | Binding dated quote with confirmed quota |
| USD list price | VAT/tax-inclusive, region-specific amount |
| Device VRAM (80/94 GB) | Host RAM (225 GiB for L1; Runpod host RAM unknown) |
| Storage size (1 TiB, "fast (local)") | Storage locality, backing device and filesystem |
| Guest shutdown/stop timer | Charge termination by the provider |
| Prepaid balance or an $80/h rate limit | Enforceable total liability ceiling including fees, storage and billing lag |
| Traffic *pricing* ("no egress fees") | Traffic *control* (verified deny) |
| Compliance marketing (SOC 2, GDPR statement) | Contract terms, DPA, subprocessors |
| Container isolation | Dedicated VM (and neither says anything about the provider's own access) |
| Synthetic image (R2, still a provider transfer; proposal only) | Approved biometric processing (R1, real adults; gates 2/3/4) |

**Bounded cost illustration (the only one the evidence supports).** *Runpod stopped volume disk*, USD, per-second billing, excluding tax, "GB" and "month" undefined (30 days assumed for the daily figure):
250 × $0.20 = $50.00 per month (≈ $1.67 per day) retained after stop, against 250 × $0.10 = $25.00 per month while running (R4; same as 3E §4.2). **No compute illustration is given:** Lambda's list rate has no
primary billing granularity or retained-storage statement (L3 is secondary), and Runpod's GPU rate is not in its documentation. Unknown stays unknown. No budget ceiling is set or implied; the $80/h default
limit is a rate limit far above any single-GPU hourly rate in the 3D snippets and does not bound a run.

## 4. Hard blockers and reversal criteria

Missing critical evidence is **NO-GO**, never "probably acceptable". Each row must be cleared by a dated, privately recorded artefact; clearing all rows still approves nothing.

| Control | Lambda: today / disqualifier / minimum to clear | Runpod: today / disqualifier / minimum to clear |
| --- | --- | --- |
| **Total billable cap + written limit on late/post-stop charges** | No mechanism found (L4). *Disqualify:* none offered, or a limit that is only alerts or in-guest. *Clear:* written vendor confirmation of an independently enforced cap, behaviour and delay at the limit, and a written bound on post-stop liabilities | Prepaid balance + $80/h rate limit (R1); destructive at $0; auto-pay, 5-min lag and other products drawing on the balance are open. *Disqualify:* no written bound on lag overshoot, stopped-volume and network-volume accrual, or if the funding workaround is the only control. *Clear:* written answer to P0-1 and a tested ceiling |
| **Provider-API kill independent of the guest; zero-data drill first** | Console/API terminate (L3, secondary); in-guest poweroff does not stop billing. *Disqualify:* drill not rehearsed, or only the guest can stop. *Clear:* off-instance terminate from a separate machine/credential on a trivial zero-data instance, then listings showing nothing remains | CLI/REST/console terminate (R5); the in-guest timer pattern is **not** this control. *Disqualify:* no terminate-only or separately held credential, or a billing-capable key in the guest. *Clear:* credential scope and custody (P0-2), plus the drill |
| **Verified outbound-deny after download** | Unknown (L4). *Disqualify:* cannot block and verify at the network layer. *Clear:* provider configuration record and an in-guest sacrificial attempt (3E §7) | No setting found (R6; absence ≠ proof). *Disqualify:* as for Lambda. *Clear:* same, plus ffmpeg and any provider telemetry covered |
| **Local attested Linux block storage; no NFS/network/overlay** | Persistent filesystems are NFS ⇒ excluded; 1 TiB root-disk locality unknown. *Disqualify:* cannot attest the root/checkpoint volume | Network and global volumes excluded; volume-disk backing unknown (R4). *Disqualify:* cannot show host-local block storage rather than bind mount/overlay; provider data migration without control |
| **Terms/AUP/DPA/privacy/region** | Unread. *Disqualify:* terms bar face media/likeness, no DPA for a later adult-face dataset, or no acceptable region. *Clear:* qualified legal reading (gate 4) | Unread; GDPR text only (R3). *Disqualify:* as for Lambda; Community Cloud for any identifiable data |
| **Dated quote + confirmed quota** | Only a list rate (L1). *Disqualify:* no quota or stock for the exact SKU/region | No GPU rate in docs; secondary only. *Disqualify:* same |
| **Isolation / hardware fit** | VM boundary unconfirmed; 80 GB headroom ≈ 4 % over the 720P figure (U1). *Disqualify:* shared or non-dedicated GPU; or the owner rejects the 80 GB OOM risk | Container only (R3). *Disqualify:* owner or data-protection owner rejects container isolation; 94 GB does not remove the unmeasured-fit risk |
| **Owner-approved risk acceptance** | HUMAN-PENDING | HUMAN-PENDING |

**Ranking reversal.** Lambda → fallback if it cannot give a written liability bound, outbound-deny or an acceptable region, or if its isolation turns out not to be a dedicated VM, while Runpod can clear the same rows. Runpod → first
if it clears the rows and the owner prefers 94 GB headroom over Lambda's published host spec. **Both fail ⇒ NO PROVIDER.** A later reversal is a documented change to this file, not an approval.

## 5. Vendor questions

**Vendor contact is not authorised by this issue.** The owner must separately approve outreach (≤ 2 vendors, 3D gate 4); only then may an operator use this list, privately. No reply or quote exists. Derived from 3E V1–V9 and D§2.3, not a transcript.
Status for every row: **not asked**. Mapping to 3E: P0-1 ← V1–V3; P0-2 ← V2, V8; P0-3 ← V5; P0-4 ← V4; P0-5 ← V6, D§2.3 Q7–Q8; P0-6 ← V7; P1-1/P1-3 ← D§2.3 Q1, Q3; P1-2 ← V9.

| # | Question | Lambda / Runpod specifics | Acceptable evidence | Gates blocked | Owner (role) |
| --- | --- | --- | --- | --- | --- |
| P0-1 | Is there an externally enforced **total** liability ceiling, including storage, fees, tax, billing lag and charges after stop? | Lambda: any limit beyond invoices? Runpod: do prepaid balance, auto-pay off, 5-min cycle and the $80/h limit bound total loss? | Written vendor statement of mechanism, delay and exact limit; tested before data | 5, 6, 7 | Budget approver |
| P0-2 | Can a **separately held credential** terminate instances from a different machine, and what remains billable after? | Lambda: API key scope. Runpod: restricted/role-limited key; is terminate-only possible, and can the Dev role also create Pods? | Scope list; dated zero-data drill with before/after listings | 5, 7 | Private runtime owner |
| P0-3 | Can **all outbound traffic be denied and verified** after download, leaving only an operator channel? Any provider telemetry from the guest? | Both: network-layer control, not an in-guest rule | Configuration record plus sacrificial-process result | 6, 7 | Security owner |
| P0-4 | Is the root/data disk **local block storage**? Mount type, overlay/bind, snapshots, provider migration, encryption | Lambda: 1 TiB root disk vs NFS filesystems. Runpod: volume disk vs network/global volume | Vendor statement plus in-guest inspection output (3E §6) | 3, 6, 7 | Data-protection owner |
| P0-5 | Do Terms/AUP/DPA permit synthetic face media now and **adult face data later**? Subprocessors, logging, support access | Both: current versions and dates; Runpod legal pages not read | Written DPA/terms with version/date and a qualified reading | 2, 4 | Legal/procurement reviewer |
| P0-6 | What **copies and logs** persist after terminate, for how long, and how is deletion evidenced? | Lambda: instances, filesystems, snapshots. Runpod: volume disk, logs, migrated copies | Retention statement and a deletion drill record | 3, 4 | Data-protection owner |
| P1-1 | Exact region, SKU, VRAM, vCPU, **host RAM**, scratch size and maximum | Lambda: H100 PCIe 80 GB row. Runpod: which of 80/94 GB is offered where | Dated quote or catalogue entry for the exact region | 4, 5 | Budget approver |
| P1-2 | Driver, CUDA, OS and kernel image provenance; customer image digest | Both | Version record before any data arrives | 6, 7 | Private runtime owner |
| P1-3 | Confirmed quota/stock, minimums, rounding, tax/VAT, currency, promotions | Both | **Dated quote** and quota confirmation | 5 | Budget approver |

## 6. Private handoff (description only; each step needs its own fresh explicit approval)

The seven-gate dependencies stand: gate 5 needs gate 4 reviewed for the chosen provider; gate 6 needs 1, 3, 4, 5 plus a fresh decision; gate 7 needs 1–6. This sequence completes no gate.

1. Qualified source/checkpoint licence review at the pins (gate 1).
2. Decide reference class and legal/privacy requirements (gate 2). R2 (licensed synthetic portrait) first is a **proposed** protocol decision with its own source-licence check and exempts no control; R1 (real consenting adults) needs specific consent, legal, storage and provider review. Experiment 003 is unchanged.
3. Choose the candidate region/SKU and obtain the exact dated quote and quota (gates 4/5).
4. Independently validate the hard cap, post-stop liability and provider-side emergency terminate (gate 5). A zero-data drill needs a provider account and spends; the seven-gate protocol has no separate slot for it, so the owner must decide whether it sits inside the gate-5 cap. **Escalate to Ada.**
5. Review DPA/AUP, egress control and physical/virtual volume backing (gates 3/4); choose custody and retention/deletion policy (gate 3).
6. Separately approve the dependency lock and environment build (3E §5).
7. Obtain gate-6 checkpoint authority and hash evidence.
8. Separately approve **one** controlled gate-7 smoke run, a technical pipeline test that measures no identity retention and supports no protection claim; the later real-person scientific baseline stays separate.

**Private record only, never GitHub:** account details, quotes and approvals, private hashes, credentials, grant tokens and ledger keys, mount points, deletion and cost logs, portraits, outputs, embeddings, screenshots.
**If a private implementation cannot meet cap, egress, filesystem, loader or grant-revocation constraints, stop and escalate; do not add a public executable workaround** (launcher, watchdog, kill, grant provider, deployment automation).

## 7. Validation and next decision

Offline checks for this documentation-only change are recorded in the PR description. They show only that the public contracts remain unready; they say nothing about vendors, GPUs or weights.
**Next decision for the owner:** approve or decline vendor outreach (§5). Without it, or if P0-1 to P0-4 cannot be answered favourably, the outcome stays NO-GO / NO PROVIDER.
