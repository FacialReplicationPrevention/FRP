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

**Sections 2–10 are being completed in this PR; see its description for status.**
