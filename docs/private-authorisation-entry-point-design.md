# Private authorisation and entry-point design — Milestone 004 3L

**Status: DESIGN ONLY. NO-GO / NO PROVIDER. NOT AUTHORISED.**
CPU-only synthetic design work. No GPU, weight download, real media, inference, signing key,
approval record, provider contact or spend. PR 3K is closed as planning-only; it found
Blackwell/Wan compatibility and mandatory controls unknown and left the decision
**NO-GO / NO PROVIDER**. All seven gates remain pending.

**Issue:** [#35](https://github.com/FacialReplicationPrevention/FRP/issues/35), parent
[#9](https://github.com/FacialReplicationPrevention/FRP/issues/9). It follows PR 3K / [#34](https://github.com/FacialReplicationPrevention/FRP/pull/34)
and issue [#33](https://github.com/FacialReplicationPrevention/FRP/issues/33), closed 2026-11-21.
It does not close #9 or unblock [#14](https://github.com/FacialReplicationPrevention/FRP/issues/14).

**Builds on:** [private-execution security design](private-execution-security-design.md),
[Wan 2.1 private-execution runbook](wan21-private-execution-runbook.md),
[GPU readiness protocol](gpu-readiness.md), and
[Experiment 003](../experiments/003-wan21-i2v-baseline-design.md).

The exact pins remain:
`Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`;
`Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`.
Published/metadata values are not weight digests verified by FRP.

## 1. Scope and evidence labels

| Label | Meaning here |
| --- | --- |
| [code] | Grounded in this repository's implementation or pinned source read. |
| [CPU-fake] | Demonstrated with synthetic fixtures, no real model or media. |
| [proposal] | A future private design requiring separate review and implementation. |
| [private-human] | A decision/evidence record outside this public repository. |
| [provider-control] | A control that must exist at the provider/hypervisor, not Python. |
| [unresolved] | A gap explicitly not claimed closed. |

This document proposes a trust boundary; it does not create an issuer, key, grant provider,
launcher, credential or executable live path. A passing test or merged PR remains neither
permission nor a scientific result.

## 2. Existing public trust boundary

### 2.1 Grant identity is not issuer authenticity

The public `PrivateAuthorisation` contract is immutable only as a Python Pydantic model:
extra fields are forbidden, the model is frozen, and `grant_sha256()` canonically hashes every
validated field. It does not prove who created the grant. [code:
`src/frp/baseline/authorisation.py`, `PrivateAuthorisation`, `grant_sha256`]

The current control therefore separates:

- **Canonical grant identity:** digest of the validated grant fields, used to detect a changed
  snapshot under the same `authorisation_id` during A0–A3.
- **Authentic issuance:** independent evidence that a trusted private issuer issued that exact
  grant for this run. The public provider protocol has no issuer identity, signature,
  evidence attestation or revocation state.

The shipped `DenyAllAuthorisation` returns `None` and has no granting implementation. [code:
`DenyAllAuthorisation`] Test-only providers in `tests/` are synthetic only.

### 2.2 Gate-to-grant mapping

The existing grant names one opaque `RecordRef` per readiness gate:

| Gate ID | Existing grant binding |
| --- | --- |
| `licence_and_intended_use` | `gates[...]` |
| `consent_and_data_processing` | `gates[...]` |
| `restricted_storage_retention_deletion` | `gates[...]` |
| `cloud_provider_terms` | `gates[...]` |
| `quote_and_budget_cap` | `gates[...]` |
| `checkpoint_download_and_hashing` | `gates[...]` |
| `gpu_smoke_test` | `gates[...]` |

The opaque references mean no approval, consent, quote or key enters public code. [code]
No public field currently stores a role/record type, issuance key ID, evidence snapshot digest,
revocation epoch or issuer subject. Those would require a separately reviewed schema change.
The public readiness schema 1.0 deliberately cannot express granted gates.

### 2.3 Request and grant bindings

`AuthorisationRequest`/`PrivateAuthorisation` currently bind:

- exact run ID and attempt index;
- run role in the request (but only indirectly in the grant digest, because the grant does not
  retain `run_role`);
- mock/live executor mode;
- canonical manifest and generation-control digests;
- pinned source commit and checkpoint revision;
- approved environment digest;
- exact private expected weight-file map;
- private artefact base URI;
- identity pseudonym and exact reference SHA-256;
- attempt cap and attempt wall-clock cap;
- issued/expiry time.

Not currently represented and not silently inferable: the future private evidence-set ID and
issuer, evidence snapshot digest and revocation epoch; run role on the grant itself; exact
provenance of the approved reference-provider read; exact provider egress/Kill controls;
provider/hypervisor identity; and output namespace attestation beyond the artefact URI.
They need review before a trust-boundary extension.

## 3. Proposed private evidence, issuance and revocation boundary

### 3.1 Separate actors

A future private provider should require four independent roles:

1. **Human gate authorities:** named people or delegated groups decide each gate. Each gate has
   a private, append-only record with authority, scope, date, evidence reference and withdrawal/
   supersession status.
2. **Evidence issuer:** verifies and authenticates each gate record, freezes the seven current
   records into an evidence-set snapshot, and rejects missing or conflicting records. It can sign
   evidence metadata but must not control the GPU process.
3. **Grant issuer:** uses the evidence-set snapshot plus a run-specific request to issue a bound,
   short-lived grant. Separation between evidence issuer and grant issuer is preferable so neither
   can silently convert a passing readiness check into approval. Both identities and keys remain
   private.
4. **Executor/verifier:** checks the grant cryptographically, exact scope and freshness against
   private evidence/revocation sources, but does not issue or sign grants.

[proposal] `DenyAllAuthorisation` remains the public default. The private provider and evidence
database belong outside this repository and public source distributions.

### 3.2 Opaque evidence records

Each gate reference should identify a private evidence record, not its content. The future
provider may inspect the record to verify:

- seven separate gate IDs, no duplicate or conflicting snapshot;
- human authority and mandate;
- evidence is current, not superseded, and not withdrawn;
- licence, consent, storage, provider terms, quote/cap, download/hash and smoke-test scope;
- exact run role and attempt scope.

Opaque references must never be invented by public tests and must never enter public logs,
reports or grant digests as more than private opaque IDs.

### 3.3 Integrity and revocation

[proposal] Every evidence/issuer relationship should use an independently reviewed key inventory
and algorithm:

- authenticated issuance containing issuer identity, evidence-set digest, request binding,
  issued/not-before/expiry, replay identifiers and grant scope;
- a trust anchor held only by the verifier;
- key ID/version and rotation plan;
- a revocation source separate from the issuer and executor;
- record/warrant verification online or by an authenticated signed revocation snapshot.

No production key, algorithm claim, certificate or signed sample belongs in this repository.
The public Pydantic model's `grant_sha256` can detect a changed snapshot but cannot authenticate
the issuer or prove that a revocation source was consulted.

### 3.4 Exact future binding

A future private provider should bind the grant to exactly:

- run ID and fixed run role;
- attempt index and attempt/cap;
- executor mode;
- manifest canonical digest and generation-control digest;
- source commit and checkpoint revision;
- exact expected file inventory and private weight digests;
- environment digest and frozen interpreter/container/image identity;
- reference identity pseudonym and reference SHA-256;
- artefact namespace/base URI;
- private evidence-set/issuer references;
- wall-clock cap and grant validity window;
- provider/instance kill and budget references, if represented by a separately reviewed schema.

The public grant is already the first 12 run/material checks but omits evidence issuer/revocation
semantics and role-on-grant. [unresolved] Do not widen the public schema merely to imitate
these controls.

## 4. Fail-closed outcome matrix

| Condition | Required private behavior | Existing public enforcement |
| --- | --- | --- |
| Missing or duplicate gate/evidence | Reject at evidence assembly; no grant. | Public model requires all seven gate IDs once. [code] |
| Conflicting/superseded gate record | Reject snapshot; no grant. | Not represented. [unresolved] |
| Stale evidence or withdrawn gate | Reject before A0 and re-check revocation at every point. | Revocation requires provider behavior; unchanged snapshot is re-asked. [code/CPU-fake] |
| Revocation source unavailable | Reject issuance and deny re-authorisation. | Not implemented; fail closed can only be provider denial/exception. [unresolved] |
| Unknown issuer or failed signature | Reject no-grant. | Not represented. [unresolved] |
| Malformed request/grant | Reject and expose fixed failure text. | Pydantic strict validation and fixed authorisation problems. [code/CPU-fake] |
| Not-yet-valid, expired or validity >24 hours | Reject. | Pydantic and `authorisation_problems` enforce window/24-hour maximum. [code/CPU-fake] |
| Replay on another run/attempt/role/environment | Reject. | Run, attempt, manifest, controls, pins, environment and mode checks. Role is request-only today. [code/gap] |
| Changed grant under same ID | Reject and keep no artefact. | Canonical digest compared at A0–A3. [code/CPU-fake] |
| Reference hash mismatch | Reject before model load; re-read before decode. | Grant/reference checks and adapter private check. [code/CPU-fake] |
| Provider exception or unavailable clock | Deny the attempt. | `_authorise()` catches provider exceptions; `now` is injected/UTC. Provider-independent clock trust remains unresolved. [proposal] |
| Concurrent withdrawal | Re-check after staging, block A3, roll back a race. | Tombstone and deferred commit/rollback. [code/CPU-fake] |
| Attempt reservation conflict | Refuse spend and no silent reuse. | Keyed ledger/attempt marker. [code/CPU-fake] |
| Unknown/rebinding artefact namespace | Reject. | URI grammar and grant exact comparison; store binds a root to a namespace. [code] |
| In-process polling while load/encode/decode/save is blocked | Detect at next software checkpoint; provider kill remains mandatory. | Documented limitation; no Python interrupt claim. [code/unresolved] |

An `AuthorisationProvider` returning `None` or throwing is a denial, never a crash or grant.
Every later answer must exactly match the first canonical digest; a different/denied answer
ends the attempt. Reissue for a later attempt is a separate private decision and is never
allowed to reuse an old attempt reservation.

## 5. Existing A0–A3 call order

The public executor already defines:

1. **Run-plan exactness** before authorisation or reference lookup.
2. **Manifest execution readiness**.
3. **A0:** ask the private provider and validate the complete request/grant.
4. **Prepare:** clean pinned source, environment digest, exact weight inventory/hash.
5. **A1:** ask the provider again before any private reference lookup.
6. Read the private reference and ask the backend to verify it.
7. Mark the attempt used only after a backend attempt check.
8. **Load:** network blocked and a `VerifiedCheckpoint` required.
9. **A2:** re-ask the provider after load, before generation.
10. Generate under network blocking and the attempt deadline.
11. Validate shape and conditioning; detect remote/prohibited-module events.
12. **A3:** stop, remaining deadline/grant validity and identical canonical grant before commit.
13. Build the output record, commit, then stop/clock-check again.
14. Cleanup; if cleanup fails or a post-commit fault occurs, rollback and leave no final/partial.

[code: `src/frp/baseline/executor.py`] A3 is not an authentication check and A0–A3 do not verify
an issuer or consult revocation state. The private provider must supply those properties.

## 6. Future private entry point — design only

No repo command, flag, environment switch or constructor may enable this boundary. The future
location should be a private deployment package or privately held launcher, never a public
enabling example.

### 6.1 Ordered preflight sequence

1. Start `python -I -B` with a fixed interpreter, `PATH`, no startup config, no
   `PYTHON*`-derived imports, no `LD_PRELOAD`, `LD_AUDIT`, `IMAGEIO_FFMPEG_EXE`,
   `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD`, or remote prompt-extension variables.
2. Independent launcher verifies a provider/hypervisor kill handle and hard billing cap.
3. Private provider loads and authenticates all seven current gate evidence records.
4. Verifies issuer/revocation state and assembles an exact run request.
5. Calls A0 and fails before any real reference open or ML import.
6. Verifies local source cleanliness/pin and image/container/interpreter/package digest.
7. Hashes every local checkpoint file against the private expected inventory and exact revision.
8. Constructs or reuses `LocalPrivateStore` only after private local-volume attestation and
   namespace binding.
9. Constructs a private reference provider, then existing executor and gated adapter/runtime
   only after all checks pass.
10. Run A1, bounded private reference read, backend check, load, A2 and generation.
11. Stage output privately, run A3 and post-commit checks, then cleanup.
12. Emit only privacy-safe audit metadata; delete or retain by the approved lifecycle.

No private reference, upstream import, model package, weight load or GPU operation precedes
the evidence and executor gates. The in-process guards supplement but do not replace provider
egress isolation and an independent provider/hypervisor stop.

### 6.2 Responsibilities

| Responsibility | Owner |
| --- | --- |
| Human gate evidence and withdrawal authority | Named human/private authority |
| Evidence authenticity and revocation | Private issuer/verifier |
| Run scope and grant issuance | Private authorisation provider |
| Reference access bytes | Private reference provider; separate from grant issuer |
| Local Linux volume, namespace and cleanup attestation | Private storage owner/operator |
| Interpreter/source/checkpoint/environment verification | Trusted launcher plus existing executor |
| Provider egress, instance isolation and snapshot policy | Provider control under gate 4 |
| Independent hard spend/time and emergency kill | Provider control plus human approver |
| Output retrieval, expiry and deletion verification | Data steward/operator |
| Stop, rollback and process replacement | Entry-point/launcher plus executor |

Stop/rollback responsibility:

- **Provider kill:** stop first for load/encode/decode/save/fsync, then instance/volume deletion.
- **Operator stop:** verify process stopped and use provider kill if the process is unresponsive.
- **Executor rollback:** remove staged/final artefacts it committed or can inode-identify.
- **Data steward:** verify private references/outputs/logs/backups/snapshots against lifecycle.

No provider has been selected and no paid zero-data drill is proposed. A future drill or
quoting decision is an independent human decision, not an activation mechanism.

## 7. Synthetic verification status

No new implementation or test dependency is justified: the existing suite covers the public
and synthetic gaps needed by this design.

| Requirement | Existing CPU evidence |
| --- | --- |
| Denial before backend/reference activity | `tests/test_baseline_executor.py`: deny-all/default |
| Provider exception/unavailable authority | `tests/test_baseline_executor.py`: provider exception |
| Scope mismatch | `tests/test_baseline_executor.py`: run/plan/pin/manifest mismatches |
| Stale/not-yet-valid/expired/malformed grant | `tests/test_private_execution_security.py`: immutable and malformed-grant tests |
| Attempt mismatch | `tests/test_private_execution_security.py`: beyond authorised attempt |
| Revocation at A0–A3 | `tests/test_private_execution_security.py`: revocation at each authorisation point |
| Changed grant under same ID | `tests/test_private_execution_security.py`: mutation matrix at A1–A3 |
| Late refused output/rollback | `tests/test_private_execution_security.py`: shape, conditioning, stop, deadline, expiry and slow-commit rollback |
| Withdrawal concurrent with commit | `tests/test_private_execution_security.py`: withdrawal race |
| Activation/no live construction tripwires | `tests/test_activation_tripwires.py` |

No test proves issuer authenticity, external revocation availability, cryptographic signing,
provider-side kill, local-volume attestation or real Wan behaviour. These remain provider/human
controls or unresolved gaps.

## 8. Future private implementation boundary

The following is a future review plan, not a file layout or runnable implementation:

- `AuthorisationProvider`: private package/module outside public `src/`; authenticates issuer,
  evidence, revocation and exact request.
- `ReferenceProvider`: private package/module outside public `src/`; maps pseudonym to an
  approved private reference after A1.
- Trusted launcher: privately held, starts isolated interpreter and wires provider kill,
  storage attestation and stop signal.
- Evidence store: private database/object store outside the public repository.
- Entry point: privately held composition of `LocalPrivateStore`, private providers,
  `TorchWanRuntime`, `Wan21UpstreamAdapter` and `Wan21BaselineExecutor`.

Any public trust-boundary change requires a separate reviewed issue defining schema, key
management and revocation semantics. It must not alter `DenyAllAuthorisation`, add a public
granting provider or CLI/flag, or construct the live runtime from a default/CI path.

Remaining prerequisites:

1. A reviewed issuance/verifier/evidence design and key lifecycle.
2. A private revocation source and availability/failure policy.
3. Review of fields missing from the public grant and run-role binding.
4. Provider selection remains blocked; there is no provider, quote or kill evidence.
5. Gate 1–7 approvals and the separately reviewed private/human controls.
6. Frozen environment, weight verification and local-volume attestation.
7. Independent provider egress, hard kill/billing cap and deletion verification.
8. Only after those approvals: a separately reviewed, tightly scoped approved smoke test.

No live authorisation mechanism, private deployment or experiment has been established.
