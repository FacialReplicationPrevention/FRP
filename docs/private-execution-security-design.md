# Private execution security design — Milestone 004, PR 3C (frozen design, CPU only)

**Status: DESIGN FROZEN FOR IMPLEMENTATION. NOTHING AUTHORISED.** CPU-only security integration.
Seven gates pending. No GPU, model weights, live inference or real biometric media. This note is a
contract and threat model for code that a *future*, separately approved private run would rely on;
merging it approves no gate, and a passing test proves neither that a private run is authorised nor
that it is scientifically valid.

**Issue:** [#16](https://github.com/FacialReplicationPrevention/FRP/issues/16) (parent
[#9](https://github.com/FacialReplicationPrevention/FRP/issues/9), which stays open).
**Builds on:** PR #15 (merged): `Wan21BaselineExecutor`, `Wan21UpstreamAdapter`, `TorchWanRuntime`,
`DenyAllAuthorisation`; PR #12: `frp.review` store, access and withdrawal hooks.
**Pins (unchanged):** `Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`;
`Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`. Checkpoint hashes,
VRAM, runtime and cost are **not verified**.

## 1. Trust boundaries and actors

| Actor | Trusted? | Design stance |
| --- | --- | --- |
| Operator running the private entry point, same OS user (uid) | Trusted | Cannot be defended against in-process; same-uid processes can rewrite anything the run can. |
| Private launcher (process start) | Trusted, private | Must sanitise the environment **before** the interpreter starts (`python -I -B`, fixed `PATH`, no `LD_PRELOAD`/`LD_AUDIT`, offline variables set). In-process checks are tripwires that detect a bad start; they cannot undo code that already ran at startup. |
| `root` / provider administrators / hypervisor | Trusted by necessity | Out of scope for software; covered only by gates 3 and 4 (provider terms, ephemeral single-tenant instance). |
| Other local OS users on the GPU host or reviewer machine | **Untrusted** | Blocked by owner-only roots, ancestor checks and exclusive, no-follow file creation. |
| Inputs: URIs, reference bytes, checkpoint files, environment variables, git config | **Untrusted** | Strict grammars, size limits, content hashes, refused variables. |
| Public contributors / CI | **Untrusted for activation** | No granting provider, no activation command or flag; static invariant tests. |
| Reviewer machine OS, screen, backups, sync, indexing | Residual | Documented; software cannot stop screenshots, cloud-sync clients or a compromised OS. |

## 2. Public code versus private integration

**Implemented in public, CPU-tested code (this PR):**

1. A hardened local private store (`frp.private_storage`, standard library only) implementing the
   adapter's storage contract: root posture checks, `private://` grammar, race-resistant reservation,
   identity-checked atomic commit, idempotent discard and deletion, reference reads bound to a
   content hash, stale-reservation listing.
2. Run-scoped authorisation contract extensions on the existing `PrivateAuthorisation` model and
   their enforcement in `Wan21BaselineExecutor` (expiry, revocation by re-authorisation, attempt
   cap, artefact and reference scope).
3. Source-binding and runtime-environment hardening (git environment scrubbing; refused
   binary-substitution and import-path variables).
4. Fail-closed private-root posture shared with `frp.review` identifiable stores (fixes the
   non-POSIX fail-open), with synthetic demo stores unchanged.
5. Static invariant tests that the package ships no granting provider and no activation path.

**Remains a private integration contract (never in this repository):** any `AuthorisationProvider`
that can grant, its issuance, signing, storage and revocation list; grant instances and gate
records; the `ReferenceProvider` mapping from pseudonyms to references; the store root path and
namespace; approved environment digest and weight hashes; the private entry point composing
`TorchWanRuntime` + `Wan21UpstreamAdapter` + `Wan21BaselineExecutor`; `StopSignal` wiring to provider
budget alerts; `SIGTERM` → `KeyboardInterrupt` handling; provider-level egress blocking, idle
shutdown and the hard billing cap; host/container/driver/GPU provenance records; the trusted
launcher that sanitises the process environment before Python starts (§1).

**Explicitly rejected:** a public allow-all, demo, "test" or time-limited granting provider in
`src/`; a sample or example grant file; a CLI command, flag or environment variable (e.g.
`--enable-live`, `FRP_ALLOW_LIVE`) that constructs the live runtime, adapter or executor; a grant
issuer or signing helper; production secrets. Test-only providers stay in `tests/` as today.

## 3. Contract map

Columns: **current control → gap → minimal implementation → test evidence (CPU) → remaining
private/human dependency.**

### 3.1 Paths, symlinks and races

- **Current:** adapter `_reserve_output` uses `O_CREAT|O_EXCL|O_NOFOLLOW` on the *final* component
  only; `final.parent.mkdir(parents=True, exist_ok=True)` follows symlinked ancestors and accepts
  pre-existing directories of any mode; the test `StoreLocator` maps any suffix under a temp root.
- **Gap:** no fixed root, no ancestor validation, traversal is prevented only by whoever writes the
  locator; reservation → `cache_video` → `os.replace` is path-based.
- **Implementation:** `ArtefactLocator.local_path` is replaced by two narrow protocols the adapter
  sees — `OutputStore` (`problems`, `reserve`, `commit`, `discard`) and `ReferenceReader`
  (`problems`, `read`) — implemented by one class, `LocalPrivateStore(root, namespace)`. Operator
  operations (`withdraw`, `delete`, `remaining`, `stale_reservations`) exist only on the concrete
  class, never on the protocols the adapter receives. URI grammar is exact:
  `private://<ns>/outputs/<BaselineRunId>/attempt-NN.mp4` and
  `private://<ns>/references/<name>.(png|jpg|jpeg)` (`<ns>` and `<name>` `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`;
  no `..`, `%`, `\`, empty or extra components). All operations walk from a root directory file
  descriptor with `O_DIRECTORY|O_NOFOLLOW` and `dir_fd`-relative `mkdir`/`open`/`rename`/`unlink`,
  so a symlink swapped into any component is refused rather than followed. Directories are created
  `0700` and verified by `fstat` (owner = effective uid, no group/other bits) even when they already
  exist. **Reservation** = exclusive creation of an attempt-ledger marker (§3.3) plus an exclusive,
  no-follow, `0600` partial file; the final name is *not* pre-created. Reservation refuses if the
  final, partial or marker already exists. **Commit** requires the partial to still be the reserved
  `(st_dev, st_ino)`, a regular, single-link, owner-only file; then `os.link(partial, final,
  src_dir_fd, dst_dir_fd, follow_symlinks=False)` — which **fails if the final exists** (no-replace,
  unlike `rename(2)`) — fsync, unlink the partial, and re-check the final's inode and link count.
  Filesystems without hard links fail closed. The adapter's filesystem code moves into the store (no
  duplication).
- **Tests:** traversal and malformed URIs; symlinked root, ancestor, run directory, final and partial;
  pre-existing final/partial/marker (stale) refused without modification; a final created by
  someone else between reservation and commit is never replaced; swapped partial (different inode or
  symlink) refused at commit; every test asserts the set of files outside the store is unchanged.
- **Residual (documented, not claimed):** `cache_video` hands ffmpeg a *path*; between reservation
  and commit a same-uid process can redirect it. The inode check detects a swap before commit but
  cannot stop ffmpeg having written through a substituted link. Mitigation is the trust boundary
  (owner-only directories, ancestors not writable by others, ephemeral single-tenant host).

### 3.2 Permission model and platforms

- **Current:** `review.security.group_or_world_accessible` returns `False` on non-POSIX, so an
  identifiable store on Windows *passes* the permission check (shipped `DenyAllReviewAccess` still
  denies). No owner or ancestor check anywhere. `chmod` is used as if it were an access control on
  every platform.
- **Implementation:** `private_root_problems(path)` (fixed messages, never paths) requires: **Linux**
  (`sys.platform == "linux"`) and `os.supports_dir_fd` for the needed calls; absolute, canonical path
  (`realpath(path) == path`, so no symlinked component); an existing directory owned by the effective
  uid with mode `& 0o077 == 0`; every ancestor owned by root or the effective uid and not group/other
  writable unless sticky; not inside a git working tree (reuses `inside_git_worktree`). Used by
  `LocalPrivateStore.problems()` (surfaced through the adapter's `check_available` → existing refusal
  `backend_unavailable`) and by `authorise_review` for **identifiable** stores, replacing
  `group_or_world_accessible` (which becomes fail-closed: `True` when it cannot verify).
- **Platform decision (for review):** Windows **and macOS** are refused for private/identifiable
  storage. POSIX mode bits do not express NTFS ACLs, and macOS extended ACLs (`chmod +a`) can grant
  access independently of mode bits; neither can be checked with the standard library. On Linux,
  POSIX ACL named entries are bounded by the mask shown in the group bits, so `mode & 0o077 == 0`
  leaves them ineffective. Network filesystems (NFS/SMB/FUSE) may not honour local mode bits and are
  **unsupported** but not detected. Synthetic demo stores are unaffected on every platform. No
  identifiable store can be opened today (deny-all), so this costs no current usability.
- **Tests:** group/other-readable root, wrong owner (simulated via injected `stat`), group-writable
  non-sticky ancestor, sticky `/tmp`-style ancestor accepted, symlinked ancestor, inside git worktree,
  non-Linux platform (monkeypatched) refused; synthetic demo still opens with the platform patched.

### 3.3 Output reservations, atomic commit and interrupted runs

- **Current:** write-once reservation, `0600`, atomic replace, discard on failure; executor's
  `_used_attempts` is per-process only; a SIGKILL leaves an empty reservation and/or partial file that
  blocks the attempt index.
- **Gap:** the executor's attempt record is per-process, and a failed attempt's discard removes its
  only on-disk trace, so a new process could reuse attempt 1 indefinitely despite an attempt cap.
- **Implementation:** an **attempt ledger** in the store: `ledger/<BaselineRunId>/attempt-NN`, an
  empty `0600` marker created exclusively at reservation and **never removed** by discard, failure
  cleanup, deletion or withdrawal (it holds no media, prompt, pseudonym or hash; only the run id and
  index in its name). An index is therefore spent once per store, across processes; with the grant's
  `max_attempts_per_run` bounding the index (§3.5), the cap holds across restarts. A new grant cannot
  reuse spent indices. `stale_reservations()` lists opaque output URIs with a leftover partial, for
  operator cleanup via `delete`. No automatic stale cleanup (an operator decides).
- **Tests:** success commits exactly one `0600` file; every failure category (load error, generation
  error, interrupt, timeout, output/conditioning violation, `KeyboardInterrupt`) leaves no file;
  simulated kill (partial and marker left in place) → listed as stale, the same index refused in a
  new store instance, `delete` clears the partial but the index stays spent; a failed attempt's index
  cannot be reused by a second `LocalPrivateStore` over the same root.
- **Private/human:** the entry point must convert `SIGTERM` to `KeyboardInterrupt` so cleanup runs;
  SIGKILL, OOM-kill and instance loss need the gate 3 deletion procedure (volumes, snapshots, images,
  provider-side copies).

### 3.4 Withdrawal, deletion and retention

- **Current:** `frp.review.records.withdrawal_scope/withdrawal_remaining` locate and verify review
  material for one identity; nothing for baseline outputs or references.
- **Implementation:** `LocalPrivateStore.delete(uri) -> DeletionReceipt` removes the output (final
  and partial) or reference named by a valid URI, never following links; idempotent (`deleted` then
  `absent`). `withdraw(run_ids, reference_uris)` enumerates **every** file in each run's output
  directory (finals, partials and stale leftovers, not only recorded results) plus the given
  references, deletes them, removes empty run directories and returns receipts; ledger markers stay
  (no personal data). `run_ids` come from a pure helper `withdrawal_run_ids(plan, pseudonym)` (all
  planned runs of that identity, executed or not); reference URIs come from the private
  `ReferenceProvider`. `remaining(run_ids, reference_uris)` re-checks and reports anything unreadable
  as remaining. Receipts hold only `{kind, outcome, at}`: no URI, path, pseudonym, token, prompt or
  hash. The store writes **no** audit log of its own (a log would itself become withdrawal residue);
  the private caller persists receipts in its gate 3 record.
- **Tests:** delete twice; delete with symlink at the name removes the link only; malformed/escaping
  URI refused; withdrawal removes committed outputs, stale partials and references of one identity
  and nothing of another; `remaining` after withdrawal is empty; receipts and exceptions contain no
  root path, pseudonym or reference name.
- **Private/human:** retention periods, backups, snapshots, provider copies and the reviewer's
  machine are outside the store and stay under gate 3.

### 3.5 Authorisation scope, expiry and revocation

- **Current:** `PrivateAuthorisation` binds run ids, manifest/controls hashes, pins, environment
  digest, expected weight hashes, seven gate references and `max_attempt_seconds`. No expiry,
  revocation, attempt cap, reference scope or artefact scope; authorised once at the start of
  `execute`, before the slow weight hashing.
- **Implementation (same model and provider protocol; new required fields):** `issued_at`,
  `expires_at` (aware; `issued_at < expires_at`, lifetime ≤ `MAX_GRANT_LIFETIME` = 24 h, **for
  review**); `artefact_base_uri` (must equal the executor's); `reference_sha256: {pseudonym: sha256}`
  (must contain the run's pseudonym); `max_attempts_per_run` (1 ≤ n ≤ `MAX_ATTEMPTS_LIMIT`).
  `AuthorisationRequest` gains `identity_pseudonym`, `attempt_index` and `artefact_base_uri`.
  `authorisation_problems(grant, request, now)` adds not-yet-valid, expired, base-URI, reference-scope
  and attempt-cap checks. The executor (i) authorises before any preflight; (ii) **re-authorises
  after preflight** (weight hashing), before the reference lookup and load; (iii) **re-authorises
  after load and before `generate`** (load can take minutes), each time requiring the same
  `authorisation_id` — revocation is the provider no longer returning the grant; (iv) computes
  `deadline_seconds = min(max_attempt_seconds, seconds until expires_at)` at (iii), so expiry during
  generation stops at the next poll (which precedes reference reading and every denoiser call) as
  `timeout`; (v) passes the grant's reference hash to the adapter, which verifies the bytes it read
  before decoding. A denial at (ii) or (iii) raises `ExecutionRefused("not_authorised")` after
  cleanup; the `ExecutionRefused` docstring is amended to "no reference was read and nothing was
  generated (the model may have been loaded)". All refusals reuse `not_authorised` (no results
  schema change).
- **Tests:** initial denial (missing/expired/not-yet-valid/over-long grant, pseudonym outside
  scope, attempt index above cap, mismatched base URI, mock grant for live and vice versa) asserts
  **zero** backend `check_available`/`environment_sha256`/`load`/`generate` calls, reference lookups,
  upstream imports and files created. Revocation or expiry at (ii) asserts zero reference lookups,
  loads, generations and files; at (iii) zero reference reads, generations and output files, and
  cleanup ran. A different `authorisation_id` on re-check is refused. Reference bytes whose hash
  differs → failure with no decode and no output file.
- **Private/human:** who may issue, how grants are signed and stored, the revocation source and
  the seven gate records. Revocation is *not* polled during an attempt (only the stop signal and
  deadline are); emergency stop is the stop signal or process/instance termination.

### 3.6 Source, environment and weight binding

- **Current:** executor and runtime check the checkout is clean at the pinned commit and that the
  imported `wan.*` modules come from it; environment digest = installed distributions + Python
  version (`cuda_version` is always `None`); every weight file SHA-256 matched before load.
- **Gap (reproduced on CPU):** `GitSourceInspector` inherits `GIT_DIR` and related variables, so
  `GIT_DIR=<other>/.git` makes it report the other repository's commit and cleanliness for the
  verified path — both the executor and `TorchWanRuntime` would attest the wrong source.
  `IMAGEIO_FFMPEG_EXE` substitutes the ffmpeg binary `cache_video` executes; `PYTHONPATH`/`PYTHONHOME`/
  `PYTHONSTARTUP` can inject code not covered by the distribution digest.
  Repository-local configuration can also redirect: `core.worktree` in `<checkout>/.git/config`
  makes `git status` inspect a different tree (reproduced), and a `.git` *file* (`gitdir:`) points
  elsewhere. Ignored files (e.g. a planted `wan/__pycache__/*.pyc`, which Python may load instead of
  source) are invisible to `git status --porcelain` (reproduced). A writable checkout or checkpoint
  directory allows replacement between verification and import/load.
- **Implementation:** git runs with every `GIT_*` variable removed, `GIT_CONFIG_NOSYSTEM=1`,
  `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, explicit
  `--git-dir=<checkout>/.git --work-tree=<checkout>` (overrides `core.worktree`), `--no-optional-locks`
  and the existing `core.fsmonitor=false`; `<checkout>/.git` must be a real directory, not a file or
  link. Cleanliness is `status --porcelain --untracked-files=all --ignored` == empty, so any ignored
  file (including bytecode caches) fails closed; the operator uses a fresh clone and `python -B`.
  A shared `trusted_tree_problems(path)` (canonical path; root, ancestors and every entry owned by the
  effective uid or root and not group/other-writable) is applied to the source checkout (runtime
  `check_available` → `backend_unavailable`) and to the checkpoint directory (inside
  `verify_checkpoint_files` → `weights_verification_failed`). `TorchWanRuntime.check_available`
  additionally requires `sys.flags.isolated` and `sys.flags.dont_write_bytecode` (a tripwire proving
  `python -I -B` started the process) and refuses `IMAGEIO_FFMPEG_EXE`, `LD_PRELOAD`, `LD_AUDIT`
  (names only in messages). `PYTHONPATH` etc. need no separate refusal under `-I`. `git` is still
  located via `PATH`; the trusted launcher fixes `PATH`.
- **Tests:** two synthetic git repositories: `GIT_DIR`/`GIT_WORK_TREE`, a repo-local `core.worktree`
  and a `.git` file pointing at the other repo do not change the reported commit or cleanliness; an
  ignored `.pyc` makes the checkout unclean; group-writable checkpoint file or source directory
  refused; the runtime tripwire refuses a non-isolated interpreter and each refused variable by name,
  never value (pure helper over a mapping plus `sys.flags` stand-in).
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
  field, no root/URI/name in exceptions or receipts. Tests assert `str()`/`repr()` of store,
  reservation, receipts and raised errors contain neither the root path nor the reference name.

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

### 3.10 Activation invariants

- **Implementation:** AST-based tests over `src/frp`: every class defining `authorise` is a
  `Protocol` or one of `DenyAllAuthorisation`/`DenyAllReviewAccess` and returns only `None`;
  `TorchWanRuntime`, `Wan21UpstreamAdapter`, `Wan21BaselineExecutor` and `LocalPrivateStore` are
  never constructed in `src/frp` (including `cli.py`); no `FRP_*` enabling environment variable is
  read. Import of `frp` and `frp.private_storage` pulls in no torch/PIL/wan/ffmpeg.

## 4. Interface changes (minimal; no results or readiness schema change)

| Item | Change |
| --- | --- |
| `frp.private_storage` (new) | `private_root_problems`, `trusted_tree_problems`, `OutputStore`, `ReferenceReader`, `LocalPrivateStore`, `Reservation`, `DeletionReceipt`, `withdrawal_run_ids`. Standard library only. |
| `wan21_adapter.ArtefactLocator` | Replaced by `OutputStore` (`artefacts=`) plus a new `references=` `ReferenceReader` argument; adapter delegates reserve/commit/discard/reference reads. |
| `UpstreamRuntime.open_reference(location)` | Becomes `decode_reference(data: bytes)`; the runtime never opens paths. |
| `GenerationRequest` | Adds `reference_sha256` (`repr=False`). |
| `PrivateAuthorisation` / `AuthorisationRequest` / `authorisation_problems` | Fields and checks in §3.5; `authorisation_problems` gains `now`. |
| `review.access.authorise_review` / `ReviewController` | Identifiable posture via `private_root_problems`; returns grant expiry, enforced per request; `group_or_world_accessible` fails closed off POSIX. |
| `preflight.GitSourceInspector`, `verify_checkpoint_files`, `wan21_runtime.runtime_environment_problems` / `TorchWanRuntime.check_available` | §3.6. |
| `ExecutionRefused` docstring | A post-load denial is a refusal: no reference read, nothing generated. |
| Results, readiness, provenance, manifest schemas, `RefusalReason`, `FailureDetail` | **Unchanged.** A reference-hash mismatch is recorded as `generation_error` (after load; surfaced below). |

## 5. Decisions surfaced for review (not silently made)

1. **Linux-only private storage**; Windows and macOS refused for identifiable/private stores until a
   tested ACL check exists.
2. **`MAX_GRANT_LIFETIME` = 24 h** as a security bound, not a scientific parameter.
3. **Reference byte binding**: gate 2/7 records must name the exact reference bytes (SHA-256 held
   only in the private grant).
4. A reference-hash mismatch is detected inside `generate`, i.e. **after** model load (the executor
   never reads media), and is recorded as `generation_error`; a distinct `FailureDetail` would be a
   results-schema change and is not proposed here.
5. Re-authorisation requires the private provider to be idempotent for an unchanged, unrevoked grant.
6. New refusal causes reuse `not_authorised` / `backend_unavailable`; finer causes are not recorded.
7. **Attempt indices are spent once per store** (ledger markers survive deletion and withdrawal);
   a re-run under a new grant needs a new store or higher indices within its cap.
8. **The live runtime requires `python -I -B`** and a fresh clone with no ignored files; operators
   cannot reuse a checkout that has ever been imported with bytecode writing on.
9. **A refusal can now follow a model load** (re-authorisation after load); accounting records the
   run as unexecuted `not_authorised`, not as a failed attempt.

## 6. Deliverable C/D outline (documentation, implemented after this design)

An unfilled, cited hardware/quote worksheet for 14B/480P (VRAM, RAM, scratch, file count/storage,
network controls, billing granularity, idle timeout, hard cap, emergency termination and deletion),
every value **unverified**; an environment-digest coverage table; a gate 1–7 human handoff checklist;
loader risks (`.pth` weights-only compatibility), stop-polling gaps and the ffmpeg subprocess.
Updates to README, ROADMAP, `PROJECT_CONTEXT.md`, `docs/harness.md`, the runbook and the GPU
readiness protocol only where facts change.
