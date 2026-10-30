# GPU readiness protocol — Wan 2.1 I2V-14B-480P baseline (Milestone 004, PR 1)

**Status:** Design and checklist only. **Nothing here has been done, approved or executed.** No GPU has been provisioned, no weights downloaded, no person's data processed, no quote obtained.
**Issue:** [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9). **Machine-readable template:** [`readiness/wan21-i2v-baseline.yaml`](../readiness/wan21-i2v-baseline.yaml), checked offline by `frp readiness`.
**Companion documents:** [Experiment 003 — baseline design](../experiments/003-wan21-i2v-baseline-design.md), [Private visual-review specification](private-review-viewer.md), [Research 005](../research/005-wan-model-candidates.md).

## Evidence labels

| Label | Meaning |
| --- | --- |
| **[published]** | Stated in external, citable material (e.g. a model card). Not checked by FRP unless said so. |
| **[source]** | Observed in source at a pinned commit (Research 005). |
| **[requirement]** | A need FRP must *assess*; not a measured or quoted fact. |
| **[planned]** | A procedure to be performed later, after the relevant gate. |

## What this document does and does not do

- It defines the **go/no-go gates** that must each be passed, by a named human decision recorded in private, before the corresponding action.
- It does **not** authorise anything. Merging this document, a valid `frp readiness` result, or any populated field is not an approval. Approval of the PR containing this document is *not* approval of any gate.
- It is **not legal advice**. Consent, biometric-data and cloud-processing rules vary by jurisdiction; the relevant gates require human review by someone qualified.

## 1. The seven separate human approvals

Each gate is an independent decision with its own evidence and its own private record. **Approving one never implies another**, and no gate is inferred from a field being filled, a checklist being complete, a test passing or the preceding gate being approved.

| # | Gate id | Decision | Minimum evidence (kept in a private record) | Must precede |
| --- | --- | --- | --- | --- |
| 1 | `licence_and_intended_use` | The checkpoint and source licences and model-card terms permit this research use. | Reviewer, date, texts reviewed at the pinned revisions, conclusion, conditions (e.g. obligations on personal information or harm in the model card). Apache-2.0 *metadata* is **[published]**; whether this use is permitted is a human judgement. | 6, 7 |
| 2 | `consent_and_data_processing` | Each identity has given specific, informed, withdrawable consent from a verified adult for generation, measurement and visual review, and the processing has a lawful basis and ethics/legal review. | Consent record per participant (private), age-verification method, ethics/legal review outcome, withdrawal procedure. | 7 |
| 3 | `restricted_storage_retention_deletion` | Source portraits, outputs, derived data and logs have access-controlled storage with approved retention and verified deletion. | Storage location and access list (private), encryption statement, retention period per artefact class, deletion procedure including derived data, backups and provider-side copies. | 6, 7 |
| 4 | `cloud_provider_terms` | The chosen provider's terms permit this workload and data handling. | Reviewed terms/DPA version and date; statements on logging, snapshots, region/data residency, support access and deletion; whether uploading biometric-derived data is allowed. | 5, 6, 7 |
| 5 | `quote_and_budget_cap` | A *quoted* price and a hard budget cap are accepted. | Completed quote template (section 3), budget cap, quota confirmation, shutdown policy; approver. | 6, 7 |
| 6 | `checkpoint_download_and_hashing` | The pinned checkpoint may be downloaded and hashed (section 4). | Gates 1, 3, 4, 5 recorded; destination, expected file list, who runs it. | 7 |
| 7 | `gpu_smoke_test` | The smallest neutral-motion smoke test may run on specified consented references. | Gates 1–6 recorded; frozen controls (section 6); stop conditions; list of identities and the exact run count. | — |

The "must precede" column is a *dependency*, not an authorisation: gate 6 additionally needs a fresh decision at the time. The `frp readiness` template records all seven as `pending` and **cannot express anything else** (readiness schema 1.0), in the same way that provenance schema 1.0 fixes `execution_readiness: not_ready`. Granting a gate in a machine-readable form needs a separately proposed and reviewed schema version.

### Stop rules

Any of the following returns the project to "no-go" until a human re-reviews: a change to a pinned revision, licence text, provider terms or price; a consent withdrawal; evidence that a reference is not a consenting adult; a storage or retention change; an unexplained cost or quota event; a hash mismatch; or any leak of private material.

## 2. Hardware, VRAM and storage — requirements to assess

**None of the following is a quote or a verified fact.** Each is a `value: null`, `status: unverified` entry in the template until grounded in a quoted provider specification and the upstream documentation at the pinned commit.

| Requirement | What is known | What is unknown |
| --- | --- | --- |
| GPU VRAM (14B DiT, T5, CLIP, VAE, 480P, 81 frames) | The upstream README publishes memory figures as an image that FRP did not transcribe (Research 005). | The VRAM needed at the chosen precision, offload settings and resolution; whether a single GPU suffices. **[requirement]** |
| System RAM | Not stated in the material reviewed. | Whether offload or CPU-resident T5 raises it. **[requirement]** |
| Weight storage | Hub-reported file sizes at the pinned revision: DiT ≈ 65.6 GB, T5 ≈ 11.4 GB, CLIP ≈ 4.8 GB, VAE ≈ 0.5 GB, summing to roughly 82 GB (an arithmetic sum of the approximate Research 005 figures, not re-measured). **[published/metadata]** | Exact bytes; whether the provider bills the volume separately; space for a second copy during hashing. |
| Working storage | Not determined. | Source checkout, environment/image, intermediate and output videos, logs. **[requirement]** |
| Runtime per clip | Not measured by FRP. | Depends on hardware, offload, steps and frame count. **[requirement]** |
| Determinism across hardware | Seeded generation uses a CUDA generator; cross-hardware determinism is unknown (Research 005). | Whether re-runs on another GPU/driver reproduce a clip. |

Do not select a GPU, region or provider from this table. Selection belongs to gate 5, using a real quote.

## 3. Provider quote and spend template (blank — do not fill from guesses)

> **TEMPLATE ONLY. No quote has been obtained. Every value below is unset, and no gate has passed.** This block is the human-readable counterpart of `cost_quote` in the machine-readable template, which schema 1.0 forces to remain `null`. Populated quotes, caps and charges belong in the private approval record.

| Field | Value | Notes |
| --- | --- | --- |
| Provider name | _unset_ | |
| GPU model / VRAM | _unset_ | Must satisfy the assessed VRAM requirement |
| Region | _unset_ | Subject to gate 2/4 data-residency review |
| Quote source and date | _unset_ | A dated, retrievable provider quote; not an estimate from memory |
| Currency | _unset_ | |
| GPU hourly rate | _unset_ | |
| Billing granularity | _unset_ | e.g. per second/minute/hour, minimum charge |
| Storage billing | _unset_ | Volume, snapshot and egress charges, including while the GPU is off |
| Estimated **upper-bound** spend | _unset_ | Derived from the quote and a pessimistic runtime; show the arithmetic |
| Budget cap (hard) | _unset_ | Approved separately by a human |
| Quota / availability confirmed | _unset_ | |
| Idle timeout | _unset_ | Automatic stop if no job is active |
| Emergency termination procedure | _unset_ | Who, how, and how it is tested; includes provider-side deletion |
| Deletion procedure and verification | _unset_ | Volumes, snapshots, images, logs |
| Actual charges (after any run) | _unset_ | Compared with the estimate; overruns documented |

## 4. Secure weight-acquisition process (planned; not authorised)

Performed only after gates 1, 3, 4, 5 and a fresh decision under gate 6.

1. **Pin.** Use only the pinned checkpoint revision (`6b73f84e66371cdfe870c72acd6826e1d61cf279`) and source commit (`9737cba9c1c3c4d04b33fcad41c111989865d315`) from the provenance inventory. A moving branch or "latest" is never acceptable; verify `git rev-parse HEAD` equals the pinned commit before use.
2. **Isolated destination.** Download into approved, access-controlled, ephemeral storage. Record who ran it, when and where, without personal paths in the public repository.
3. **File list.** Compare the downloaded file set with the Hub file list at that revision. Unexpected or missing files are a no-go.
4. **Independent local hashing.** Compute SHA-256 **locally for every downloaded file**. The Hub's platform-reported LFS digests are *expected* values, not FRP verification (Research 005): record both, and treat a mismatch between them as a stop.
5. **Record.** Store the digests in the private record. Only after review may a *versioned* schema extension allow weight digests to be marked verified; provenance schema 1.0 deliberately forbids `verified` for `weight_sha256`, and this process does not change that.
6. **Load safely.** Several Wan checkpoint components are `.pth` files, a format that can execute code when deserialised unsafely **[requirement: assess whether the pinned loader restricts this]**. Load only hash-verified files, inside the isolated environment, with outbound network access disabled for the load and inference steps.
7. **Executable provenance.** Record the source commit and a tree hash; the dependency set with hashes (upstream gives lower bounds only, and its requirements include a remote-service client — `dashscope` — that must remain unused); the container/image digest; Python, CUDA/driver and GPU details. These feed `software_environment_hash` in a future manifest.
8. **Cleanup.** Wipe working storage and verify deletion at the end of every session per gate 3.

## 5. Consented-adult, benign-only input and private-data procedure (draft)

Nothing in this procedure has been adopted or reviewed. It must be reviewed under gates 2 and 3 before any person's data is handled.

**Participants.** Adults only, with specific, informed consent covering generation, measurement (including face-similarity computation), human visual review, retention period and the right to withdraw with deletion of the participant's portraits, outputs and derived data. Consent covers neutral, benign motion only. FRP does not generate sexual, defamatory, deceptive, stalking or harassing content and does not involve minors or uninvolved third parties.

**Reference portraits.** One clearly visible face of the consenting adult, with no other identifiable person. No portrait is chosen to be adversarial.

**Pseudonyms.** Pseudonyms follow the harness format (`^[A-Z]{2,8}-[0-9]{3,8}$`) and are assigned randomly. The mapping from person to pseudonym is kept only in private storage, separately from media.

**What never enters this public repository, CI, issues, PRs or public logs:** reference portraits or any crop; generated videos or frames; face embeddings or tensors; participant identifiers or the pseudonym mapping; consent forms or records; credentials; personal or storage paths; provider account details.

**Storage and transfer.** Media and biometric-derived data stay in access-controlled private storage with an approved retention period and a documented deletion procedure. Moving a portrait to a rented GPU is a data transfer that needs gate 2, 3 and 4 approval; use encrypted transfer to an ephemeral volume, no third-party media endpoints and no reference images sent to any remote service (see `use_prompt_extend: false`, section 6). Records refer to media only through opaque private references.

**Withdrawal and incidents.** A withdrawal triggers deletion across all copies and a recorded confirmation. A suspected leak is a stop condition and is reported to the responsible human owner.

**Public reporting.** Only privacy-reviewed aggregates; small-cell risks are reviewed before any real-data export (existing report guard: real-data public reports are disabled).

## 6. Execution allowlist and controls

The template fixes the decisions already made and leaves the rest unset. Allowed controls for the baseline (see [Experiment 003](../experiments/003-wan21-i2v-baseline-design.md)):

| Control | Value | Status |
| --- | --- | --- |
| Model / source | Wan 2.1 I2V-14B-480P at checkpoint `6b73f84…`; `Wan-Video/Wan2.1` at `9737cba…` | Pinned (Research 005). Weight hashes **not verified** |
| `use_prompt_extend` | `false` | **Decided.** Upstream offers an optional image → VLM → text route (`--use_prompt_extend`, default off), and a `dashscope` method that is a remote service **[source]**. It must stay off so no image reaches text conditioning or leaves the controlled environment |
| CLIP route | original reference | **Decided** |
| VAE first-frame route | original reference | **Decided** (the same unaltered reference feeds both routes) |
| Identity adapters / LoRA | none | **Decided** |
| Remote inference services | none | **Decided** |
| Prompts | neutral motion only; template version | Policy decided; template version **pending** |
| Seeds | explicit non-negative integers (negative seeds are replaced by random ones upstream) | **Pending** |
| Sampler, sampling steps, guidance scale | — | **Pending.** Upstream defaults noted in Research 005 are not adopted |
| Frame count (4n+1), resolution (`W*H`), precision | — | **Pending** |
| Sampled frame indices | Candidate `0, 20, 40, 60, 80` for 81 frames (Experiment 002) | **Pending**; later frames prioritised |
| Image preprocessing | — | **Pending** |
| Output | Private artefact reference only | **Decided** |

The control values come with required **output provenance**: a per-run record of the executed source commit, checkpoint revision, locally verified file hashes, environment/image digest, seed, all controls above, GPU model and measured runtime, plus branch metadata limited to shapes, dtypes and devices. No tensors, embeddings, portrait bytes or paths are logged.

## 7. Checklist (all unchecked)

- [ ] Gate 1: licence and intended use reviewed and approved by a human.
- [ ] Gate 2: adult consent, data-processing basis and ethics/legal review approved.
- [ ] Gate 3: restricted storage, retention and deletion approved.
- [ ] Gate 4: cloud-provider terms reviewed and approved.
- [ ] Gate 5: dated provider quote obtained; hard budget cap approved.
- [ ] Hardware requirements grounded in the quoted specification and upstream documentation.
- [ ] Pending controls (section 6) frozen and recorded in a reviewed manifest extension.
- [ ] Gate 6: checkpoint download and local SHA-256 verification approved and completed.
- [ ] Gate 7: smoke test approved for a stated, minimal set of consented references.

Passing every box here would still not constitute scientific evidence: a smoke test shows only that a pipeline runs.

## Limitations

- The readiness validator checks the public template's consistency and its agreement with the provenance inventory. It cannot confirm that any human review occurred.
- Provider-specific risks (data retention, logging, snapshots) cannot be assessed before a provider is chosen.
- Licence, consent and data-protection determinations are human, jurisdiction-dependent decisions outside this repository's scope.
