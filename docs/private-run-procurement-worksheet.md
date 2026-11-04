# Private-run procurement and gate worksheet (Milestone 004, PR 3C) — UNFILLED

**TEMPLATE ONLY. NOT AUTHORISED. Nothing here has been obtained, verified or approved.** CPU-only
security integration. Seven gates pending. No GPU, model weights, live inference or real biometric
media. Every value below is `_unset_` or an unchecked box. Do not fill any field from memory, a
guess or a vendor web page that is not retrievable and dated. Completing this worksheet, passing
the tests or merging the PR that added it authorises nothing: each gate is a separate human decision
([GPU readiness protocol](gpu-readiness.md)).

Companion documents: [security design](private-execution-security-design.md) (§ numbers below refer
to it), [runbook](wan21-private-execution-runbook.md), and the machine-readable
[readiness template](../readiness/wan21-i2v-baseline.yaml). The
[GPU go/no-go dossier](gpu-go-no-go-dossier.md) (PR 3D, planning only) lists the public-source
evidence, unverified provider questions, illustrative cost scenarios and per-gate private evidence
needed to fill this worksheet; it fills nothing in and approves nothing. The
[provider decision](gpu-provider-decision.md) (PR 3F, planning only) adds a non-binding
conditional ranking, disqualifiers, prioritised vendor questions and a private handoff order; it
also fills nothing in and selects no provider.

**Pinned targets (expected values only):** `Wan-Video/Wan2.1` @
`9737cba9c1c3c4d04b33fcad41c111989865d315`; `Wan-AI/Wan2.1-I2V-14B-480P` @
`6b73f84e66371cdfe870c72acd6826e1d61cf279`. Checkpoint hashes, VRAM, runtime and cost: **not locally
verified**.

## 1. Hardware and quote (gate 5; see [gpu-readiness §2–3](gpu-readiness.md))

| Field | Value | Source / evidence (dated, retrievable) |
| --- | --- | --- |
| Provider, region | _unset_ | |
| GPU model, VRAM | _unset_ | |
| Host RAM | _unset_ | |
| Scratch/working storage (source, checkpoint ≈ 82 GB by hub-reported sizes — unverified, outputs, logs) | _unset_ | |
| Checkpoint file count and total bytes at the pinned revision | _unset_ | |
| Network egress controls available (block-all after download?) | _unset_ | |
| Billing granularity, minimum charge | _unset_ | |
| Hard spend cap and who enforces it **outside Python** (design §8 item 3) | _unset_ | |
| Idle shutdown | _unset_ | |
| Emergency termination (hard kill independent of the process) and how it is tested | _unset_ | |
| Derived `max_attempt_seconds` and the arithmetic (covers load → commit, not weight hashing; design §3.5) | _unset_ | |
| Provider-side deletion of volumes, snapshots, images, logs | _unset_ | |

## 2. Execution-environment digest coverage (design §3.6)

The environment digest covers installed distributions and the Python version. It does **not** cover:

| Not covered by the digest | Recorded privately where? | Verified? |
| --- | --- | --- |
| CUDA driver and toolkit versions | _unset_ | no |
| Container/VM image digest | _unset_ | no |
| Host kernel, GPU model/firmware | _unset_ | no |
| ffmpeg binary identity (the encoder spawns it) | _unset_ | no |
| Launcher command line (`python -I -B`), `PATH`, absence of `LD_PRELOAD`/`LD_AUDIT`/`IMAGEIO_FFMPEG_EXE` | _unset_ | no (in-process check detects, cannot undo) |

## 3. Gate 1–7 handoff checklist (all unchecked; each is a human decision)

- [ ] Gate 1 — licence and intended use at the pinned revisions.
- [ ] Gate 2 — adult, specific, withdrawable consent; lawful basis; ethics/legal review. Includes the
  **retained-token decision** below.
- [ ] Gate 3 — restricted storage, retention, deletion. Includes the **local-volume attestation**
  and the withdrawal order below.
- [ ] Gate 4 — provider terms/DPA, logging, snapshots, region.
- [ ] Gate 5 — dated quote and hard cap (section 1).
- [ ] Gate 6 — download at the pinned revision; local SHA-256 of every file; private expected manifest.
- [ ] Gate 7 — one neutral-motion smoke run for named consenting references.

## 4. Decisions only a human can make (design §8)

| Item | Decision / evidence | Owner | Date |
| --- | --- | --- | --- |
| **Local-volume attestation:** store root and checkpoint volume are local block storage, not NFS/SMB/FUSE/network or synced folders (code cannot establish this) | _unset_ | | |
| **Sticky/shared ancestors:** store parent is owner-only; if an ancestor such as `/tmp` is sticky, the owned-child rule is accepted | _unset_ | | |
| **Grant authenticity:** who issues grants, how they are authenticated, how an unchanged grant is returned for an unchanged authorisation (design §3.5) | _unset_ | | |
| **Revocation before withdrawal:** the provider revokes live grants **first**, then the tombstone is written, then files are deleted (design §3.4) | _unset_ | | |
| **Retained-token decision:** whether keyed pseudonymous ledger tokens and withdrawal tombstones may outlive a withdrawal (suppression), or the whole store is erased via `erase_store` with revocation confirmed (design §3.4, §8 item 1) | _unset_ | | |
| **Ledger key custody:** where `ledger.key` lives, backups, destruction (losing it forfeits replay protection; leaking it makes tokens linkable) | _unset_ | | |
| **Hard time/budget kill** independent of Python (design §8 item 3) | _unset_ | | |
| **Windows/macOS** private storage stays refused; any change needs a tested ACL check | n/a | | |

## 5. Loader, runtime and encoder risks to resolve before gate 7

- [ ] Whether the upstream `.pth` checkpoints load under weights-only unpickling on the pinned torch
  (runbook §5); unverified.
- [ ] Whether the real `cache_video`/ffmpeg encoder keeps the staged partial's inode. If it replaces
  it, the deferred commit refuses (fail-closed) and the adapter would need a reviewed change; unverified.
- [ ] ffmpeg runs as a subprocess outside the in-process network guard; egress must be blocked at the
  provider or host level.
- [ ] Python polling cannot interrupt a model load, a denoiser step or ffmpeg (design §3.5).
- [ ] A fresh clone is required (ignored files make a checkout unclean); the interpreter must be
  isolated with bytecode off.

## 6. What the public CPU code does and does not establish

| Established by CPU tests with synthetic fixtures | Not established |
| --- | --- |
| A late executor rejection leaves no final or partial MP4 | That real encoder output behaves the same (item 5 above) |
| Any change to a grant under the same id is refused at every re-check | That a grant is authentic or unrevoked in the provider's system |
| Deleted or withdrawn runs cannot re-enable an attempt | That retaining tokens is lawful or consented |
| Symlinks, foreign owners, writable entries and bad roots are refused on POSIX | Behaviour as an unprivileged user, on NFS/FUSE, or on a different host |
| No granting provider, activation flag or live-construction path ships | That one cannot be added by malicious code (human review is the control) |

Nothing in this table approves any gate or shows that private execution is authorised or
scientifically valid.
