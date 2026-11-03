# Private execution security design — Milestone 004, PR 3C (revision 2, CPU only)

**Status: DESIGN REVISED AFTER ADA'S REVIEW OF PR #17. NOTHING AUTHORISED.** CPU-only security
integration. Seven gates pending. No GPU, model weights, live inference or real biometric media.
This note is a contract and threat model for code that a *future*, separately approved private run
would rely on; merging it approves no gate, and a passing test proves neither that a private run is
authorised nor that it is scientifically valid. Statements about code are **proposals** until the
implementation commits on this branch land and their tests pass (§9 records which have).

**Issue:** [#16](https://github.com/FacialReplicationPrevention/FRP/issues/16) (parent
[#9](https://github.com/FacialReplicationPrevention/FRP/issues/9), which stays open; #14 stays blocked).
**Builds on:** PR #15 (merged): `Wan21BaselineExecutor`, `Wan21UpstreamAdapter`, `TorchWanRuntime`,
`DenyAllAuthorisation`; PR #12: `frp.review` store, access and withdrawal hooks.
**Pins (unchanged):** `Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`;
`Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`. Checkpoint hashes,
VRAM, runtime and cost are **not verified**.

**Revision 2** resolves the three high and three medium findings of Ada's independent review and
her documentation notes; §7 maps each finding to its resolution and test, §8 lists what cannot be
resolved in code and is surfaced as a human/private decision instead of weakening a gate.

## 1. Trust boundaries and actors

| Actor | Trusted? | Design stance |
| --- | --- | --- |
| Operator running the private entry point, same OS user (uid) | Trusted | Cannot be defended against in-process; same-uid processes can rewrite anything the run can. |
| Private launcher (process start) | Trusted, private | Must sanitise the environment **before** the interpreter starts (`python -I -B`, fixed `PATH`, no `LD_PRELOAD`/`LD_AUDIT`, offline variables set). In-process checks are tripwires that detect a bad start; they cannot undo code that already ran at startup. |
| `root` / provider administrators / hypervisor | Trusted by necessity | Out of scope for software; covered only by gates 3 and 4 (provider terms, ephemeral single-tenant instance). |
| Other local OS users on the GPU host or reviewer machine | **Untrusted** | Blocked by owner-only roots, ancestor checks and exclusive, no-follow file creation. |
| Inputs: URIs, reference bytes, checkpoint files, environment variables, git config | **Untrusted** | Strict grammars, size limits, content hashes, refused variables. |
| Public contributors / CI | **Untrusted for activation** | No granting provider, no activation command or flag; static regression tripwires **plus human review and repository protection** (§3.10). |
| Reviewer machine OS, screen, backups, sync, indexing | Residual | Documented; software cannot stop screenshots, cloud-sync clients or a compromised OS. |

## 2. Public code versus private integration

**Proposed for public implementation (CPU-tested; not claimed until the code and tests land, §9):**

1. A hardened local private store (`frp.private_storage`, standard library only): root posture
   checks, `private://` grammar, race-resistant reservation, **staged output with a deferred,
   identity-checked commit**, inode-checked rollback, durable (fsynced) writes, keyed attempt ledger
   with withdrawal tombstones, idempotent deletion, bounded reference reads, stale-reservation listing.
2. Run-scoped authorisation extensions on the existing `PrivateAuthorisation` model and their
   enforcement in `Wan21BaselineExecutor`: expiry, per-call **canonical-grant identity**,
   re-authorisation at four points, attempt cap, artefact and reference scope, end-to-end attempt
   deadline, final stop/expiry/authorisation check immediately before commit.
3. Source-binding and runtime-environment hardening (git environment scrubbing; no symlinks in the
   source or checkpoint trees; refused binary-substitution and import-path variables).
4. A fail-closed private-root posture shared with `frp.review` identifiable stores (fixes the
   non-POSIX fail-open), with synthetic demo stores unchanged.
5. Static regression tripwires that the package ships no granting provider and no activation path.

**Remains a private integration contract (never in this repository):** any `AuthorisationProvider`
that can grant, its issuance, signing, storage and revocation list; grant instances and gate
records; the `ReferenceProvider` mapping from pseudonyms to references; the store root path and
namespace; approved environment digest and weight hashes; the private entry point composing
`TorchWanRuntime` + `Wan21UpstreamAdapter` + `Wan21BaselineExecutor`; `StopSignal` wiring to provider
budget alerts; `SIGTERM` → `KeyboardInterrupt` handling; provider-level egress blocking, idle
shutdown, **hard kill and the billing cap (independent of Python polling)**; host/container/driver/GPU
provenance; the attestation that store and checkpoint volumes are local block storage; the trusted
launcher that sanitises the process environment before Python starts (§1).

**Explicitly rejected:** a public allow-all, demo, "test" or time-limited granting provider in
`src/`; a sample or example grant file; a CLI command, flag or environment variable (e.g.
`--enable-live`, `FRP_ALLOW_LIVE`) that constructs the live runtime, adapter or executor; a grant
issuer or signing helper; production secrets. Test-only providers stay in `tests/` as today.

## 3. Contract map

Columns: **current control → gap → minimal implementation → test evidence (CPU) → remaining
private/human dependency.**

### 3.1 Paths, symlinks, races and durability

- **Current:** adapter `_reserve_output` uses `O_CREAT|O_EXCL|O_NOFOLLOW` on the *final* component
  only; `final.parent.mkdir(parents=True, exist_ok=True)` follows symlinked ancestors and accepts
  pre-existing directories of any mode; the test `StoreLocator` maps any suffix under a temp root.
- **Gap:** no fixed root, no ancestor validation, traversal is prevented only by whoever writes the
  locator; reservation → `cache_video` → `os.replace` is path-based; nothing is fsynced.
- **Implementation:** `ArtefactLocator.local_path` is replaced by two narrow protocols the adapter
  sees — `OutputStore` (`problems`, `check_reservable`, `reserve`, `commit`, `discard`, `rollback`)
  and `ReferenceReader` (`problems`, `read`, bounded) — implemented by one class,
  `LocalPrivateStore(root, namespace)`. Operator operations (`withdraw`, `delete`, `remaining`,
  `stale_reservations`, `erase_store`) exist only on the concrete class, never on the protocols the
  adapter receives. URI grammar is exact: `private://<ns>/outputs/<BaselineRunId>/attempt-NN.mp4`
  and `private://<ns>/references/<name>.(png|jpg|jpeg)` (`<ns>` and `<name>`
  `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; no `..`, `%`, `\`, empty or extra components). All operations
  walk from a root directory file descriptor with `O_DIRECTORY|O_NOFOLLOW` and `dir_fd`-relative
  `mkdir`/`open`/`link`/`unlink`, so a symlink swapped into any component is refused rather than
  followed. Directories are created `0700` and verified by `fstat` (owner = effective uid, no
  group/other bits) even when they already exist. **Reservation** = exclusive creation of a ledger
  marker (§3.4) plus an exclusive, no-follow, `0600` partial file; the final name is *not*
  pre-created. Reservation refuses if the final, partial or marker already exists, or the run is
  withdrawn. **Commit** is specified in §3.3.
- **Durability (fsync):** every state the store promises survives a crash is fsynced, file *and*
  parent directory entry: the ledger marker and tombstone (file, then `ledger/<token>` directory,
  and the `ledger` directory when it was created) before `reserve`/`withdraw` return; at commit the
  partial's **data** (through a descriptor opened no-follow and identity-checked) before the link,
  the output directory after the link and again after unlinking the partial; the output directory
  after any `unlink` in `delete`/`withdraw`. An `fsync` error fails closed (refused reservation or
  commit; the staged output is discarded). Test hook: `os.fsync` is wrapped and each directory
  fsync is asserted by `S_ISDIR(fstat(fd))`. Not claimed: durability on filesystems that lie about
  `fsync`, disk write caches, or a crash during the encoder's own writes (the data fsync covers them).
- **Tests:** traversal and malformed URIs; symlinked root, ancestor, run directory, final and partial;
  pre-existing final/partial/marker (stale) refused without modification; a final created by
  someone else between reservation and commit is never replaced; swapped partial (different inode or
  symlink) refused at commit; fsync of file and directory observed; fsync failure → refused and no
  final; every test asserts the set of files outside the store is unchanged.
- **Residual (documented, not claimed):** `cache_video` hands ffmpeg a *path*; between reservation
  and commit a same-uid process can redirect it. The inode check detects a swap before commit but
  cannot stop ffmpeg having written through a substituted link. Mitigation is the trust boundary
  (owner-only directories, ancestors not writable by others, ephemeral single-tenant host).
- **Network/FUSE/shared filesystems (explicit private gate, not code):** local mode bits, `link(2)`,
  `O_EXCL` atomicity and `fsync` semantics are **not guaranteed** on NFS/SMB/9p/FUSE/overlay-over-
  network volumes, and Python cannot reliably prove a volume is local. The store therefore documents
  the requirement and the private launcher/gate 3–4 record must **attest** that the store root,
  checkpoint directory and source checkout are on local block storage. No in-code detection is
  claimed or added (a best-effort mount-type deny list would imply a guarantee it cannot give).

### 3.2 Permission model and platforms

- **Current:** `review.security.group_or_world_accessible` returns `False` on non-POSIX, so an
  identifiable store on Windows *passes* the permission check (shipped `DenyAllReviewAccess` still
  denies). No owner or ancestor check anywhere. `chmod` is used as if it were an access control on
  every platform.
- **Implementation:** `private_root_problems(path)` (fixed messages, never paths) requires: **Linux**
  (`sys.platform == "linux"`) and `os.supports_dir_fd` for the needed calls; absolute, canonical path
  (`realpath(path) == path`, so no symlinked component); an existing directory owned by the effective
  uid with mode `& 0o077 == 0`; ancestors per the shared rule below; not inside a git working tree
  (reuses `inside_git_worktree`). Used by `LocalPrivateStore.problems()` (surfaced through the
  adapter's `check_available` → existing refusal `backend_unavailable`) and by `authorise_review`
  for **identifiable** stores, replacing `group_or_world_accessible` (which becomes fail-closed:
  `True` when it cannot verify).
- **Shared ancestor rule** (store root, source checkout, checkpoint directory): every ancestor is
  owned by root or the effective uid and is **not group- or other-writable**, with one exception: a
  group/other-writable ancestor is accepted only if it is **sticky** *and* the next path component
  beneath it is owned by the effective uid or root. This is what lets a checkout live under `/tmp`
  or `/dev/shm`-style sticky directories: in a sticky directory only the entry's owner (or the
  directory owner) may rename or delete the entry, so another local user cannot swap our component.
  It does **not** protect against root, same-uid code, or a malicious sticky-directory *owner*, and it
  is not an argument to store private data under `/tmp` (tmp cleaners and backups); operators should
  prefer a path under an owner-only parent (documented in the runbook). A non-sticky
  group/other-writable ancestor is always refused.
- **Platform decision (for review):** Windows **and macOS** are refused for private/identifiable
  storage. POSIX mode bits do not express NTFS ACLs, and macOS extended ACLs (`chmod +a`) can grant
  access independently of mode bits; neither can be checked with the standard library, and this
  design makes **no claim** that mode bits enforce NTFS ACLs. On Linux, POSIX ACL named entries are
  bounded by the mask shown in the group bits, so `mode & 0o077 == 0` leaves them ineffective.
  Synthetic demo stores are unaffected on every platform. No identifiable store can be opened today
  (deny-all), so this costs no current usability.
- **Tests:** group/other-readable root, wrong owner (simulated via injected `stat`), group-writable
  non-sticky ancestor refused, sticky ancestor accepted only with an owned child, symlinked ancestor,
  inside git worktree, non-Linux platform (monkeypatched) refused; synthetic demo still opens with
  the platform patched.

### 3.3 Output lifecycle: staging, deferred commit and rollback (Ada finding 1)

- **Current:** the adapter's `generate` writes the MP4 and atomically replaces it into the final name
  **before returning**. The executor then runs its own post-generation checks (network-call counter,
  prohibited modules, output shape/URI, conditioning). A late executor rejection therefore leaves a
  committed final MP4 on disk and only a failed record: §3.3's earlier "every failure leaves no
  output" was not true.
- **Decision: deferred commit, with rollback as defence in depth.** The adapter's `generate` ends with
  the video written to the reserved **partial** only (a *staged* output); the executor makes the
  commit the **last fallible step** of a successful attempt:

  1. `generate` returns → executor runs every post-generation check (remote-call counter, prohibited
     modules, `output_problems`, `verify_conditioning`);
  2. executor's **pre-commit gate** (§3.5, time scope): stop signal, attempt deadline, grant expiry,
     and re-authorisation with an identical grant;
  3. the executor builds the `ArtefactRef`/`ExecutionRecord` (pure, fallible work done *before* commit);
  4. `backend.commit_output(request)` → `OutputStore.commit` (below);
  5. cleanup runs in `finally` as today.

  Any failure at 1–3 leaves **no final file**; cleanup discards the staged partial. If anything (including
  `KeyboardInterrupt`) raises during or after 4 before the outcome is returned, the executor calls
  `backend.discard_output(request)`, an **inode-checked rollback** (`OutputStore.rollback`: unlink
  the final only if it is still the committed `(st_dev, st_ino)` regular file), then re-raises. So a
  recorded failure never has a surviving artefact, and a surviving artefact always has a success record.
- **Protocol change (minimal):** `Wan21Backend` gains `check_attempt`, `commit_output` and
  `discard_output` (§3.5, §4). Fakes and the disabled `UpstreamWan21Backend` implement them
  (the disabled backend refuses `check_attempt` and has nothing to commit). No results/readiness schema change.
- **Store commit** (`OutputStore.commit(reservation)`): refuse if the run has a tombstone (§3.4);
  open the partial `O_NOFOLLOW` by `dir_fd`, require the reserved `(st_dev, st_ino)`, a regular file,
  `st_nlink == 1`, owner-only; `fsync(fd)`; `os.link(partial, final, src_dir_fd, dst_dir_fd,
  follow_symlinks=False)` — which **fails if the final exists** (no-replace, unlike `rename(2)`);
  `fsync(dirfd)`; unlink the partial; `fsync(dirfd)`; verify the final's inode and `st_nlink == 1`;
  **re-check the tombstone after the link** and, if a withdrawal raced the commit, remove the final
  (inode-checked) and refuse. Filesystems without hard links fail closed.
- **Tests (observable, synthetic fixtures):** *adapter-success / executor-rejection*: the adapter
  stages successfully and the executor then rejects for each of: a late remote-call counter, a
  prohibited module appearing after generate, an `output_problems` violation, a conditioning
  violation, a stop signal, deadline overrun during the save, grant expiry during the save,
  revocation before commit, and a changed grant before commit — each asserts **no final and no partial
  MP4** remains, no ledger *reopening* (the index stays spent), and a failed record with no artefact.
  Success commits exactly one `0600` file after the checks. A commit that links and then raises
  (`KeyboardInterrupt` injected after the link) is rolled back by inode; a final replaced by another
  file is **not** removed by rollback. Withdrawal racing commit leaves no final.
- **Private/human:** the entry point converts `SIGTERM` to `KeyboardInterrupt`; SIGKILL, OOM-kill and
  instance loss leave a partial/marker that `stale_reservations()` lists and the gate 3 deletion
  procedure (volumes, snapshots, images, provider-side copies) removes.

### 3.4 Attempt ledger, withdrawal, deletion and retention (Ada finding 3)

- **Current:** `frp.review.records.withdrawal_scope/withdrawal_remaining` locate and verify review
  material for one identity; nothing for baseline outputs or references; the executor's attempt record
  is per-process, and a failed attempt's discard removes its only on-disk trace.
- **Correction to revision 1:** a permanent `ledger/<BaselineRunId>/attempt-NN` is **not** "no personal
  data". `BaselineRunId` contains the experiment identifier and, through the private plan, maps to an
  identity pseudonym; retention beyond a withdrawal would be linkable.
- **Ledger design.** Two different needs, two different mechanisms:
  - *Attempt cap across restarts (budget integrity):* exclusive markers `ledger/<token>/attempt-NN`.
  - *Withdrawal anti-replay (consent):* an exclusive tombstone `ledger/<token>/withdrawn` that blocks
    **every** index of a withdrawn run and makes a withdrawn run unreservable and uncommittable.

  `token = hex(HMAC-SHA256(ledger_key, "run:" + run_id))`, with `ledger_key` = 32 random bytes in
  `<root>/ledger.key` (`0600`, created exclusively on first use, fsynced; a missing/short/readable
  key beside an existing ledger **fails closed** in `problems()`). Ledger names thus contain no run
  id, experiment id, pseudonym or hash, and no index→identity link can be made *without the key
  and the private plan*. This is **pseudonymisation, not anonymisation**: whoever holds the store
  directory (which contains the key) and the private plan can recompute tokens. That is acceptable
  only because the ledger is inside the same owner-only store as the outputs it protects; it is
  surfaced as a gate 2/3 decision in §8.
- **Retention.** Markers and tombstones are kept **for the life of the store**; nothing deletes them
  automatically, and `delete`/`withdraw` never remove them (deletion must not re-enable attempts).
  They hold no media, prompt, pseudonym, run id or hash. The store writes **no** audit log (a log would
  itself become withdrawal residue); the caller persists receipts in its private gate 3 record.
- **Withdrawal (`withdraw(run_ids, reference_uris)`), order matters:**
  1. *Grant revocation first* — private: the provider stops returning grants naming the identity's
     runs (the executor's four re-authorisations then fail an in-flight attempt before it commits).
     Stop signal / instance termination for any attempt already running.
  2. *Tombstone every run id* (`run_ids` from `withdrawal_run_ids(plan, pseudonym)`: all planned runs
     of that identity, executed or not), fsynced, **before** anything is deleted.
  3. Enumerate and delete **every** file in each run's output directory (finals, partials,
     stale leftovers, not only recorded results), the given references, then remove emptied run
     directories; fsync parents; return content-free receipts `{kind, outcome, at}` (no URI, path,
     pseudonym, token, prompt or hash).
  4. `remaining(run_ids, reference_uris)` re-checks: anything unreadable, undeleted, or **not
     tombstoned** counts as remaining.
  Withdrawal is idempotent and safe to repeat after a crash. A reservation, commit or re-run of a
  tombstoned run is refused in every future store instance, **at any attempt index and under any new
  grant** — the executor's `check_attempt` refuses it before model load (`invalid_input`).
- **Full erasure / irreversible de-linking.** Tokens cannot be removed for one identity without
  reopening that identity's attempts, so per-identity "delete the ledger" is deliberately **not**
  offered. When the retained pseudonymous tokens are not acceptable (end of study, consent terms),
  the operator calls `erase_store(revoked_grants_confirmed=True)`, which removes **everything**
  including `ledger.key` and the whole ledger (so the tokens become unrecoverable), fsyncs, and
  leaves an empty `ERASED` sentinel. An erased root is refused by `problems()` for every future
  store instance, so an old grant **cannot replay against it**; a new run needs a new root and
  namespace (a grant binds the namespace via `artefact_base_uri`) and a new human decision.
  `revoked_grants_confirmed` is a deliberate friction flag, not an authorisation check: the code
  cannot see private grants, so grant revocation remains the private provider's job (§8).
- **Anti-replay layering (none is claimed sufficient alone):** (i) grant expiry ≤ 24 h and canonical
  identity (§3.5); (ii) private revocation; (iii) per-store attempt markers; (iv) withdrawal
  tombstones; (v) the `ERASED` sentinel; (vi) in-process `_used_attempts`.
- **Tests (withdrawal / restart / replay):** ledger directory names contain none of the run id,
  experiment id or pseudonym; tokens differ between two stores; a different or missing key does not
  find an old marker (and fails closed rather than reopening); delete twice; delete with a symlink at
  the name removes the link only; withdrawal removes committed outputs, stale partials and references of
  one identity and nothing of another, and leaves markers; **after withdrawal + new store instance +
  new executor, replay of the same run at index 1 and at a higher index under a fresh grant is
  refused before load/reference read, with zero files created**; withdrawal during an in-flight attempt
  leaves no final (tombstone + post-link recheck); `remaining` empty after withdrawal and non-empty
  before a tombstone; `erase_store` removes the key and ledger, leaves only `ERASED`, and the same root
  refuses all use afterwards; erasing without the confirm flag does nothing; receipts and exceptions
  contain no root path, pseudonym or reference name.
- **Private/human:** retention periods, backups, snapshots, provider copies, the reviewer's machine,
  whether pseudonymous tokens may outlive a withdrawal (§8) — all gate 3.

### 3.5 Authorisation scope, expiry, grant identity and time (Ada findings 2, 4, 6)

- **Current:** `PrivateAuthorisation` binds run ids, manifest/controls hashes, pins, environment
  digest, expected weight hashes, seven gate references and `max_attempt_seconds`. No expiry,
  revocation, attempt cap, reference scope or artefact scope; authorised once at the start of
  `execute`, before the slow weight hashing; `deadline_seconds = max_attempt_seconds` starts only
  when the adapter's `generate` begins, so load, reference decoding and video encoding are outside it.
- **Grant fields (same model; new required fields):** `issued_at`, `expires_at` (aware;
  `issued_at < expires_at`, lifetime ≤ `MAX_GRANT_LIFETIME` = 24 h, **for review**);
  `artefact_base_uri` (must equal the executor's); `reference_sha256: {pseudonym: sha256}` (must
  contain the run's pseudonym); `max_attempts_per_run` (1 ≤ n ≤ `MAX_ATTEMPTS_LIMIT`).
  `AuthorisationRequest` gains `identity_pseudonym`, `attempt_index` and `artefact_base_uri`;
  `authorisation_problems(grant, request, now)` adds not-yet-valid, expired, base-URI,
  reference-scope and attempt-cap checks and requires `type(grant) is PrivateAuthorisation`.
- **Immutable grant identity (finding 2).** An unchanged `authorisation_id` proves nothing. Define
  `grant_sha256(grant)` = SHA-256 of the canonical JSON (`sort_keys`, compact separators) of the
  grant's validated fields, computed from the base-class dump so a subclass cannot override it. The
  executor records the digest at the first authorisation of an `execute()` call and **every later
  check must return a grant with the identical digest**; any difference in **any** field — expiry
  (earlier *or later*), `reference_sha256`, `gates`, `max_attempts_per_run`, `max_attempt_seconds`,
  `artefact_base_uri`, `run_ids`, `expected_files`, `authorisation_id` — is refused (fail closed; the
  executor cannot tell a legitimate re-issue from tampering). Extending or changing a grant is a new
  human decision applied to a **new** `execute()` call. The executor keeps using the first
  snapshot object, never the re-fetched one. What stays private: signing/authenticity of the grant
  itself and who may issue it; the executor only guarantees the provider handed it the *same* grant
  throughout one attempt.
- **Four authorisation points per attempt**, each `authorise(request)` → `authorisation_problems` →
  identical digest: **A0** before any preflight; **A1** after preflight (weight hashing is slow),
  before reference lookup; **A2** after load, before `generate`; **A3** immediately before commit
  (§3.3). A denial at A0/A1/A2 raises `ExecutionRefused("not_authorised")` after cleanup (nothing was
  generated; the attempt index is released in-process; the `ExecutionRefused` docstring is amended:
  "no reference was decoded and nothing was generated; the model may have been loaded"). A denial
  at **A3** happens after GPU time was spent: the attempt is recorded as a **failed** attempt with
  detail `operator_abort` (a human revoked it), no artefact, with its wall seconds; no schema change.
- **Reference check before load (finding 6) — decision: do it before load.** After A1 and the
  reference lookup, the executor calls `backend.check_attempt(request)` which performs, with **no
  decoding and no model/upstream import**: store posture; output reservability (marker absent,
  not tombstoned, final/partial absent); and a **bounded** (`MAX_REFERENCE_BYTES` = 32 MiB, regular
  file, no-follow) read of the exact reference with its SHA-256 compared to the grant's
  `reference_sha256`. A valid authorisation permits opening exactly that reference for hashing. Any
  failure → `ExecutionRefused("invalid_input")` before load. The adapter **re-reads and re-hashes in
  `generate`** before decoding (the bytes actually decoded are the bytes verified; closes the
  window between the check and the use). A mismatch there (tampering during the load window) is a
  `generation_error` with **no output file** (the file is not yet reserved or is discarded);
  it is the only remaining post-load case and exists because the executor itself never reads media.
- **Time scope of `max_attempt_seconds` (finding 4).** The attempt clock starts at the **start of
  `_run_attempt`** (before model load, if the model is not already loaded) and ends when the output
  is committed. It therefore covers: model load; reference re-read/decode; denoising (polled before
  each denoiser call); video save/encoding; the pre-commit gate; commit. It does **not** cover
  weight hashing/preflight (bounded only by A1 expiry), once per executor lifetime, or `check_attempt`.
  `deadline_seconds` passed to the backend = `min(max_attempt_seconds − elapsed, seconds until
  expires_at)` computed at A2; ≤ 0 at that point is a `timeout` failure before `generate`. Python can
  only *poll* at: A2, before the reference read, before each denoiser call, before save, and in the
  executor's pre-commit gate. A single denoiser step, model load and the ffmpeg encode are **not
  interruptible by Python**; an overrun there is caught **after the fact** by the pre-commit gate,
  which refuses to commit (`timeout`) and leaves no file. The **hard** bound (SIGKILL/instance
  termination, provider billing cap, idle shutdown) is a **private dependency** independent of any
  Python polling (§8).
- **Pre-commit gate (executor):** in order — stop signal (`budget_stop`/`operator_abort`), attempt
  deadline `timer() − t0 > max_attempt_seconds` → `timeout`, `clock() ≥ expires_at` → `timeout`, A3.
  Clocks (`clock`, `timer`) are already injected into the executor so every case is testable.
- **Tests:** initial denial (missing/expired/not-yet-valid/over-long grant, pseudonym outside scope,
  attempt index above cap, mismatched base URI, subclass instance, mock grant for live and vice
  versa) asserts **zero** backend `check_available`/`environment_sha256`/`load`/`generate` calls,
  reference lookups, upstream imports and files created. Per re-check point A1/A2/A3 and per mutated
  field (expiry earlier and later, reference hash, a gate reference, attempt cap, `max_attempt_seconds`,
  base URI, extra run id, extra expected file, `authorisation_id`), **same id but changed grant is
  refused**, with the stage-appropriate zero-effects assertions (A1: zero reference lookups, loads,
  files; A2: zero decodes/generations/files and cleanup ran; A3: no final/partial). Revocation (provider
  returns `None`) at each point. Reference-hash mismatch at `check_attempt` → zero loads, imports, decodes
  and files; mismatch swapped in after `check_attempt` → no decode, no output. Expiry/stop/overrun
  **during the post-generation save** (a fake runtime's `save_video` advances the injected timer or
  clock, or trips the stop) → no commit, no final, no partial. Deadline accounting includes load time.
- **Private/human:** who may issue, how grants are signed and stored, the revocation source and the
  seven gate records. Revocation is polled only at A0–A3, not continuously; emergency stop is the
  stop signal or process/instance termination.

### 3.6 Source, environment and weight binding

- **Current:** executor and runtime check the checkout is clean at the pinned commit and that the
  imported `wan.*` modules come from it; environment digest = installed distributions + Python
  version (`cuda_version` is always `None`); every weight file SHA-256 matched before load;
  `verify_checkpoint_files` already refuses symlinks inside the checkpoint directory (the
  `.cache` top-level directory is skipped).
- **Gap (reproduced on CPU):** `GitSourceInspector` inherits `GIT_DIR` and related variables, so
  `GIT_DIR=<other>/.git` makes it report the other repository's commit and cleanliness for the
  verified path. `IMAGEIO_FFMPEG_EXE` substitutes the ffmpeg binary `cache_video` executes;
  `PYTHONPATH`/`PYTHONHOME`/`PYTHONSTARTUP` can inject code not covered by the distribution digest.
  Repository-local `core.worktree` makes `git status` inspect a different tree (reproduced), and a
  `.git` *file* (`gitdir:`) points elsewhere. Ignored files (e.g. a planted `wan/__pycache__/*.pyc`)
  are invisible to `git status --porcelain` (reproduced). A writable checkout or checkpoint
  directory allows replacement between verification and import/load.
- **Implementation:** git runs with every `GIT_*` variable removed, `GIT_CONFIG_NOSYSTEM=1`,
  `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, explicit
  `--git-dir=<checkout>/.git --work-tree=<checkout>` (overrides `core.worktree`), `--no-optional-locks`
  and the existing `core.fsmonitor=false`; `<checkout>/.git` must be a real directory. Cleanliness is
  `status --porcelain --untracked-files=all --ignored` == empty, so any ignored file (including bytecode
  caches) fails closed; the operator uses a fresh clone and `python -B`.
- **Tree policy (`trusted_tree_problems`, shared; finding 5):** canonical root path; the shared
  ancestor rule of §3.2; then a **no-follow walk of every entry** (including `.git` for the source
  checkout and the `.cache` directory the checkpoint hasher skips) requiring: **no symbolic link
  anywhere** (file or directory, in the source *or* checkpoint tree), no special file (socket, FIFO,
  device), owner = effective uid or root, and not group/other-writable (symlink targets are never
  followed). This is **consistent with, and stricter than, the checkpoint check** that already
  rejects internal symlinks (it additionally rejects symlinks under `.cache` and in the source tree);
  the pinned Wan2.1 tree at `9737cba9…` contains **no** symlinks or submodules (verified from the
  public git tree listing: no mode `120000` or `160000` entries), so the rule costs nothing.
  Hard links are *not* rejected (a local `git clone` hard-links `.git/objects`); a same-uid hard-link
  swap is within the same-uid residual. Applied to the source checkout (runtime `check_available` →
  `backend_unavailable`) and to the checkpoint directory (inside `verify_checkpoint_files` →
  `weights_verification_failed`). `TorchWanRuntime.check_available` additionally requires
  `sys.flags.isolated` and `sys.flags.dont_write_bytecode` (a tripwire proving `python -I -B` started the
  process) and refuses `IMAGEIO_FFMPEG_EXE`, `LD_PRELOAD`, `LD_AUDIT` (names only in messages).
  `PYTHONPATH` etc. need no separate refusal under `-I`. `git` is located via `PATH`; the trusted
  launcher fixes `PATH`.
- **Tests:** two synthetic git repositories: `GIT_DIR`/`GIT_WORK_TREE`, a repo-local `core.worktree`
  and a `.git` file pointing at the other repo do not change the reported commit or cleanliness; an
  ignored `.pyc` makes the checkout unclean; a symlink (file or directory, top level or nested, in the
  source tree, `.git`, checkpoint tree, `.cache`) is refused; group-writable checkpoint file or
  source directory refused; a sticky `/tmp`-style ancestor with an owned child accepted and a
  non-sticky group-writable ancestor refused; the runtime tripwire refuses a non-isolated interpreter
  and each refused variable by name, never value.
- **Not changed / documented:** the digest still excludes CUDA driver/toolkit, GPU, kernel, container
  image and the ffmpeg binary hash; these belong in the private run record (Deliverable C worksheet).
  No host-provenance collector is added because it could not be verified on CPU. Hash-then-load and
  inspect-then-import windows remain for same-uid or root writers (runbook §5, §10); the tree checks
  remove them for other local users only. Git's stat cache is trusted (forging `ctime` needs root).

### 3.7 Network and subprocess limits

- **Current:** in-process socket guard during load/generate; nested guard in the adapter; the
  prohibited prompt-extension modules check; `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` required.
- **Residual:** ffmpeg (via `imageio-ffmpeg`) and git are subprocesses the in-process guard cannot
  see; native extensions can bypass Python sockets. Provider/host-level egress blocking is mandatory
  (private). No change beyond §3.6 refusals.

### 3.8 Logging and disclosure

- **Current:** fixed refusal codes; exception messages never recorded; `repr=False` on locations,
  prompts and URIs; no `logging` use in `frp.baseline`.
- **Implementation:** the same rules for the store: fixed problem strings, `repr=False` on every path
  field, no root/URI/name/token in exceptions or receipts. Tests assert `str()`/`repr()` of store,
  reservation, receipts and raised errors contain neither the root path, the reference name, a run
  id nor a ledger token.

### 3.9 Local reviewer machine trust

- **Unchanged controls:** loopback-only server, `Host` checks, CSP, remote-environment refusal for
  identifiable stores, synthetic digest check, blinded Mode B, immutable records.
- **Gap:** an identifiable review grant is checked only when `ReviewController` is constructed, so
  a long-running session would outlive the grant's `expires_at`.
- **Added:** the shared Linux-only posture check (§3.2) for identifiable stores; `authorise_review`
  returns the grant's expiry and the controller refuses every media and submission request at or
  after it (synthetic stores have no expiry). Revocation during an open session is not polled; the
  reviewer closes the viewer. Tests use an injected clock with a test-only provider (as today).
- **Residual:** screenshots, recordings, cloud-sync folders, OS indexing, swap and backups, a
  compromised OS or browser extensions. Full-disk encryption and the machine's suitability are
  gate 3 decisions.

### 3.10 Activation invariants (regression tripwires, not a proof)

- **Implementation:** AST-based tests over `src/frp`: every class defining `authorise` is a
  `Protocol` or one of `DenyAllAuthorisation`/`DenyAllReviewAccess` and returns only `None`;
  `TorchWanRuntime`, `Wan21UpstreamAdapter`, `Wan21BaselineExecutor` and `LocalPrivateStore` are
  never constructed in `src/frp` (including `cli.py`); no `FRP_*` enabling environment variable is
  read. Import of `frp` and `frp.private_storage` pulls in no torch/PIL/wan/ffmpeg.
- **What this does and does not establish:** these are **static regression tripwires** that catch an
  accidental or naive re-introduction of an activation path. They are **not proof** that malicious or
  dynamic code (`getattr`, `importlib`, `exec`, `__import__`, string-built names, a different
  module, a build-time patch) cannot construct a runtime or grant. The actual control is **human code
  review (Ada) plus repository protection** (reviewed merges only, no direct pushes to `main`);
  the tests do not replace either, and a green run authorises nothing.

## 4. Interface changes (minimal; no results or readiness schema change)

| Item | Change |
| --- | --- |
| `frp.private_storage` (new) | `private_root_problems`, `trusted_tree_problems`, `OutputStore`, `ReferenceReader`, `LocalPrivateStore`, `Reservation`, `DeletionReceipt`, `withdrawal_run_ids`. Standard library only. |
| `Wan21Backend` protocol | Adds `check_attempt(request)`, `commit_output(request)`, `discard_output(request)`. `generate` now leaves the output **staged**. Fakes and `UpstreamWan21Backend` updated. |
| `wan21_adapter.ArtefactLocator` | Replaced by `OutputStore` (`artefacts=`) plus a new `references=` `ReferenceReader` argument. |
| `UpstreamRuntime.open_reference(location)` | Becomes `decode_reference(data: bytes)`; the runtime never opens paths. |
| `GenerationRequest` | Adds `reference_sha256` (`repr=False`); `deadline_seconds` is the remaining attempt budget. |
| `PrivateAuthorisation` / `AuthorisationRequest` / `authorisation_problems` | Fields and checks in §3.5; new `grant_sha256`; `authorisation_problems` gains `now`. |
| `Wan21BaselineExecutor` | Four authorisation points, grant-digest identity, `check_attempt`, pre-commit gate, deferred commit with rollback, end-to-end deadline. Constructor unchanged. |
| `review.access.authorise_review` / `ReviewController` | Identifiable posture via `private_root_problems`; returns grant expiry, enforced per request; `group_or_world_accessible` fails closed off POSIX. |
| `preflight.GitSourceInspector`, `verify_checkpoint_files`, `wan21_runtime.runtime_environment_problems` / `TorchWanRuntime.check_available` | §3.6. |
| `ExecutionRefused` docstring | A post-load denial is a refusal: nothing was decoded or generated. |
| Results, readiness, provenance, manifest schemas, `RefusalReason`, `FailureDetail` | **Unchanged.** A reference-hash mismatch discovered inside `generate` is `generation_error`; revocation at A3 is `operator_abort`; expiry/overrun is `timeout`. |

## 5. Decisions surfaced for review (not silently made)

1. **Linux-only private storage**; Windows and macOS refused for identifiable/private stores until a
   tested ACL check exists.
2. **`MAX_GRANT_LIFETIME` = 24 h** as a security bound, not a scientific parameter.
3. **Reference byte binding**: gate 2/7 records must name the exact reference bytes (SHA-256 held
   only in the private grant); verified **before** load and again before decode.
4. **Grants are immutable per `execute()` call**: any change under the same id is refused, including
   loosening. A legitimate extension is a new call.
5. The private provider must return the **identical** grant for an unchanged, unrevoked authorisation.
6. New refusal causes reuse `not_authorised` / `backend_unavailable` / `invalid_input`; finer causes
   are not recorded.
7. **Attempt indices are spent once per store** (keyed markers survive deletion and withdrawal);
   a re-run under a new grant needs a new store/namespace or a higher index within its cap.
8. **The live runtime requires `python -I -B`** and a fresh clone with no ignored files; operators
   cannot reuse a checkout that has ever been imported with bytecode writing on.
9. **A refusal can follow a model load** (A2); accounting records the run as unexecuted
   `not_authorised`, not as a failed attempt. A revocation at A3 *is* a failed attempt (`operator_abort`).
10. **`max_attempt_seconds` covers load through commit** (not weight hashing); Python polling is
    best-effort, the hard bound is private (§3.5).
11. **Keyed pseudonymous ledger tokens and withdrawal tombstones survive withdrawal** for the life of
    the store; per-identity de-linking is not offered because it would reopen attempts (§3.4).
    Whole-store `erase_store` is the irreversible alternative.
12. **Sticky shared ancestors** (e.g. `/tmp`) are accepted only with an owned child; recommended
    practice is an owner-only parent.
13. **Network/FUSE volumes are excluded by a private attestation**, not by code (§3.1).

## 6. Deliverable C/D outline (documentation, implemented after the code)

An unfilled, cited hardware/quote worksheet for 14B/480P (VRAM, RAM, scratch, file count/storage,
network controls, billing granularity, idle timeout, hard cap, emergency termination and deletion),
every value **unverified**; an environment-digest coverage table; a gate 1–7 human handoff checklist
(including local-volume attestation, hard-kill/budget bound, grant-revocation-before-withdrawal and
the retained-token decision); loader risks (`.pth` weights-only compatibility), stop-polling gaps
and the ffmpeg subprocess. Updates to README, ROADMAP, `PROJECT_CONTEXT.md`, `docs/harness.md`, the
runbook and the GPU readiness protocol only where facts change.

## 7. Resolution of Ada's review (PR #17)

| # | Finding | Resolution | Where | Test evidence (planned; actual in §9) |
| --- | --- | --- | --- | --- |
| 1 | High: commit before executor checks | Deferred commit as the last fallible step; inode-checked rollback for post-commit failure | §3.3 | Adapter-success/executor-rejection matrix, no final/partial; rollback only removes the committed inode |
| 2 | High: same id ≠ same grant | `grant_sha256` identity across A0–A3; any field change refused; exact type | §3.5 | Same-id/changed-field × A1/A2/A3 |
| 3 | High: ledger vs withdrawal | Keyed tokens, tombstones that never reopen, retention rules, `erase_store` + `ERASED` sentinel, revocation-first order | §3.4 | Withdraw/restart/replay, higher index, in-flight withdrawal, erase |
| 4 | Medium: time scope | Attempt clock from `_run_attempt` through commit; pre-commit gate; hard kill private | §3.5 | Expiry/stop/overrun during save |
| 5 | Medium: fsync, symlinks, sticky, FUSE | fsync of data and directories; no symlinks in any tree; sticky rule; FUSE attestation gate | §3.1, §3.2, §3.6 | fsync observation, symlink matrix, sticky cases |
| 6 | Medium: early reference hash | `check_attempt` before load, re-hash before decode | §3.5 | Mismatch before/after check |
| — | Doc: "Implemented in public" | Reworded to "Proposed for public implementation" until code lands | §2, §9 | — |
| — | Doc: AST ≠ proof | Stated as tripwire; human review and repository protection are the control | §3.10 | — |

## 8. Blockers surfaced (not resolvable in public, CPU-safe code; no gate weakened)

1. **Retained pseudonymous tokens (gate 2/3, human/legal).** Whether a keyed per-run token and
   withdrawal tombstone may outlive a withdrawal depends on the consent terms and applicable law; code
   cannot decide it. Offered: tombstones (suppression) by default; `erase_store` for full erasure.
2. **Grant authenticity and revocation (private provider).** The executor enforces *identity* of the
   grant within an attempt; signing, issuance, expiry policy and the revocation source are private.
3. **Hard time/budget bound (private launcher/provider).** Python cannot interrupt a model load, a
   denoiser step or ffmpeg; SIGKILL, billing cap and idle shutdown are required and cannot be verified on CPU.
4. **Local-volume attestation (private gate 3/4).** NFS/SMB/FUSE exclusion cannot be verified in code.
5. **Same-uid/root TOCTOU** (including ffmpeg reopening the partial by path) remains a documented residual.
6. **Platforms**: Windows and macOS private storage stays refused until a tested ACL check exists.

## 9. Implementation status

*Design only at the time of writing. This section is updated by the implementation commits with the
actual test, lint and CLI results; nothing here is claimed before it is run.*
