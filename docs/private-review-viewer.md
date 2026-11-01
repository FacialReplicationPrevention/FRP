# Private visual-review specification

**Status:** Specification (Milestone 004, PR 1) with a CPU-only implementation in Milestone 004 PR 3A ([section 7](#7-implementation-status-milestone-004-pr-3a)). **The implementation can open only procedurally generated synthetic content; no real media has been reviewed, and no real media is used in tests or this repository.**
**Issue:** [#9](https://github.com/FacialReplicationPrevention/FRP/issues/9). **Related:** [Experiment 003](../experiments/003-wan21-i2v-baseline-design.md), [GPU readiness protocol](gpu-readiness.md).

Human review supplements the automated face measurements: it can reveal failures that scores hide (a different-looking person with a high score, a ruined video with a plausible score). Observations are descriptive and are **not proof of protection or of identity**.

## 1. Purpose and non-goals

A simple, **local-only** viewer that shows the original consented portrait next to the generated Wan output, so an authorised reviewer can spot-check identity retention and record observations.

Non-goals: publishing or sharing media; a web service; automated decisions; consent verification (a viewer cannot establish consent); a replacement for calibrated evaluation.

## 2. Two review modes that must stay separate

| | **Mode A — identity inspection** | **Mode B — video utility scoring** |
| --- | --- | --- |
| Question | Does the output look like the source person, frame by frame? | Is the video useful: subject visible, scene continuity, motion, prompt adherence? |
| Blinding | **Unblinded** by necessity: the reviewer sees the source portrait | **Blinded**: no source portrait, no similarity or detection scores, no run id, no variant or condition |
| Identification | Opaque private references | Per-session **blinding codes** distinct from run ids (run ids may reveal ordering or, for the ablation, the variant) |
| Order | Any | Randomised per rater |
| Output | Observation records | Rubric scores on a predeclared scale (rubric version recorded) |

A rater who has done Mode A on a clip should not later score the same clip in Mode B, or the sessions must be separated in time and order, with the choice documented. Mode B ratings feed the independent video-quality assessment; Mode A observations never replace calibrated similarity.

## 3. Mode A interface requirements

- **Side by side:** original portrait (left) and playable, scrubbable output video (right). Pause and frame stepping.
- **Sampled-frame thumbnails** at the manifest's frame indices (e.g. 0, 20, 40, 60, 80 for an 81-frame video), each linked to the exact frame. Selecting one shows it beside the portrait.
- **Later frames first.** Default to a later frame, not frame 0: the conditioned first frame can look unusually close to the source and give a misleading impression of retention. Frame 0 is shown and labelled, not hidden.
- **Optional zoom** on both panels, synchronised or independent.
- **Annotations, when available**, clearly labelled and optionally hidden until the reviewer has recorded an initial impression (to limit anchoring): per-frame detection status (`valid`, `absent`, `multiple`, `low_quality`, `error`) and calibrated similarity. Calibration state is shown ("uncalibrated" for smoke tests). Human recognisability and the numerical face-similarity score are displayed as distinct things.
- **Missing and unusable outputs.** A failed run, absent artefact, absent face or unscorable video is shown explicitly with its status; the viewer never substitutes a score or skips it silently.
- **Free-text observations** per run and optionally per frame.

## 4. Records

All review records are **private structured records**, never public.

- Fields: opaque run reference; mode; reviewer role code (not a name); rubric/instrument version; frame index (if frame-level); categorical judgement (for Mode A: *same person / different person / uncertain / not assessable*; for Mode B: the rubric scale or `unscorable`); free text; timestamp; viewer version.
- Free text may accidentally contain personal information, so it is stored privately, never exported or logged elsewhere, and subject to the same retention and deletion as the media.
- **Independent ratings.** Each rater's record is stored separately and never overwritten. Disagreement is retained: an adjudication, if any, is a **new** record linked to the originals. Agreement statistics (and their limits with few raters or items) are specified in the analysis plan, not assumed here.
- **Not assessable.** `not assessable`, `unscorable` and `output absent` are first-class values and count in denominators.
- Observations are never treated as a protection result, and uncertainty is reported with them.

## 5. Security and privacy requirements

The requirements below are normative for PR 3 and checkable in review.

| # | Requirement |
| --- | --- |
| V1 | **Local only.** Runs on an approved, access-controlled reviewer machine. If a local server is used it binds to the loopback interface only, serves a per-session unguessable token, and is not started in a port-forwarded or shared environment. |
| V2 | **No cloud dev environments for real media.** Not run in GitHub Codespaces, hosted notebooks or any remote development environment (forwarded ports and storage would move identifiable media off-machine). CPU tests use synthetic, non-biometric fixtures only. |
| V3 | **No public hosting or sharing.** No static hosting, tunnelling, link sharing or public bucket. |
| V4 | **No third-party endpoints.** No CDN fonts, scripts, map tiles, analytics, telemetry, crash reporters or remote error tracking; all assets bundled; strict content-security policy permitting only the local origin; no outbound network calls. |
| V5 | **No accidental export.** No upload, share, download or "save as" of media; no clipboard or print-to-PDF of media; thumbnails and frame extractions kept in memory or in an approved private working directory and removed at session end; no browser history, cache or autofill retention (`Cache-Control: no-store` if a browser is used). |
| V6 | **No artefacts to GitHub or CI.** Media, thumbnails, screenshots, review records and logs are never committed, attached to issues/PRs or uploaded as CI artefacts; `.gitignore` already excludes common media/weights patterns and must be extended for any viewer working directories. |
| V7 | **Private references only.** The viewer is given opaque private artefact references resolved against approved storage; no personal path, filename or participant identifier appears in the UI title, logs or records. |
| V8 | **Restricted access and audit.** Access limited to named, approved reviewers; a private access log (who/when/which opaque reference), no media content in logs. |
| V9 | **Retention and deletion.** Working copies, caches and review records follow the approved retention schedule; deletion is verified, and withdrawal of a participant removes their media, derived data and review records. |
| V10 | **Screen exposure.** Reviewers are instructed not to screen-record, screenshot or review in shared spaces; this cannot be enforced technically and is recorded as a residual risk. |
| V11 | **Fail closed.** The viewer refuses to open media if its configuration enables any network egress, if the storage location is unapproved, or if the approval reference is missing. |
| V12 | **Untrusted input.** Media and metadata are untrusted; parsing happens in a constrained process, and file names or metadata are never interpreted as code or markup. |

## 6. Verification plan

- [x] Unit tests with generated synthetic frames (procedural patterns, not faces) for frame selection, later-frame default, status display, blinded mode hiding scores and ids, record immutability and disagreement handling. *(PR 3A; `tests/test_review_*.py`.)*
- [x] A test that the application binds only to loopback, refuses outbound connections and name lookups, and that the page assets reference no external origin. *(PR 3A; in-process checks only.)*
- [x] A test that logs and records contain no path, pseudonym or media bytes. *(PR 3A.)*
- [ ] A privacy review of real-data screenshots **before** any appear anywhere; none are committed. *(Not applicable until real media is authorised.)*
- [ ] Browser-level testing of the page (the player's frame logic is tested under Node.js when available; no browser automation runs in CI).

## Residual risks and open questions

- Human judgements of identity are subjective, vary across raters and with image conditions, and are not demographically neutral.
- The number of reviewers and items needed for useful agreement estimates is undetermined.
- Whether the reviewer machine, rather than a stricter environment, is acceptable must be decided under the storage and consent gates.
- PR 3A chose a loopback web page (Python standard-library HTTP server, bundled HTML/JS/CSS) over a desktop application; section 7 maps it to V1–V12.

## 7. Implementation status (Milestone 004, PR 3A)

Package [`frp.review`](../src/frp/review/); commands `frp review-demo` and `frp review` (see the [harness guide](harness.md#baseline-evaluation-and-private-review-milestone-004-pr-3a)). **Only `DenyAllReviewAccess` ships, so stores labelled identifiable are always refused; the only content that can be opened is the procedurally generated synthetic demo.**

### Modes as implemented

- **Mode A (identity inspection).** Reference still on the left, output on the right. Play, pause, previous/next frame, a scrubber, and sampled-frame thumbnails at the catalogue's frame indices. The default is the first sampled later frame (never frame 0 automatically); frame 0 is labelled as the conditioned first frame. Zoom (1–4×) is applied to both panels. Automated detection statuses and similarities are **hidden until the reviewer asks for them**, are labelled *uncalibrated*, and whether they were revealed before a judgement is stored in the record. Failed, unexecuted and media-unavailable items, and items whose original reference is missing or unreadable (`reference_unavailable`), are listed with their status and can only be judged `not_assessable`. Judgements are `same_person`, `different_person`, `uncertain` and `not_assessable`, per clip or per frame, with optional private notes.
- **Mode B (blinded quality).** Only succeeded attempts, keyed by fresh session-specific codes (`Q-XXXXXXXXXX`) in an order shuffled with `secrets.SystemRandom`. The browser never receives the reference, measurements, run ids, attempt numbers, identity/prompt ordinals, outcome or conditioning information. The rubric `frp-blinded-quality-rubric-0.1-draft` (a draft, **not validated**) scores subject visibility, temporal continuity, motion plausibility and freedom from artefacts on 1–5, or records the clip as `unscorable` with a reason. Prompt adherence is excluded so that no prompt text reaches the blinded page. A reviewer who has opened **any** Mode A session on the store is refused a Mode B session, whether or not they saved a judgement: the Mode A session file is written before any media is served and is the durable exposure evidence. A Mode B session also stops accepting ratings if its reviewer opens Mode A concurrently; ratings saved before that are kept. The rule is store-wide (conservative), because a Mode A session can display every item.
- **No combined score.** Identity observations and quality ratings are separate record types and are never merged.

Playback uses one PNG per frame rather than a video file, so frame indices are exact and no video container parser is involved.

### Records, retention and withdrawal

- Each record is written once with an exclusive create, made read-only and stored with the SHA-256 of its canonical content; reading verifies it (`RecordIntegrityError` on mismatch). No update API exists. A second opinion or an `Adjudication` (linked to the original record ids) is a new record. `disagreements()` reports differing judgements without choosing a winner.
- Records carry the reviewer role code (pattern `AA-00`), mode, instrument/rubric version, viewer version, timestamp and opaque item reference or blinding code. Mode B's code-to-item key lives only in the private session record.
- **Integration points (not policy):** `withdrawal_scope()` locates every item, media id, record and blinding entry derived from one identity ordinal; deletion must run under the approved storage procedure (readiness gate 3), after which `withdrawal_remaining()` reports every class of material that still refers to the identity *in the store*: media, records, catalogue items or media entries, session blinding entries and access-log lines. Anything it cannot read is reported as remaining. Withdrawal is verified only when it returns an empty list. The catalogue and session records are write-once, so removing an identity from them is a deliberate replacement under the approved procedure, not an API call. Backups, provider snapshots and copies outside the store are beyond this software. No retention schedule is implemented; it must come from the approved storage gate.

### Requirement mapping

| # | Implemented control (software, best effort) | What it cannot do |
| --- | --- | --- |
| V1 | Binds only to a literal loopback address (others refused before a socket opens); unguessable per-session URL token compared in constant time; `Host` must be a loopback name (DNS-rebinding and forwarded-domain defence) | Cannot stop another local user or process on the same machine from connecting with the token |
| V2 | Identifiable stores refused when any remote/hosted/CI indicator is set (Codespaces, dev containers, SSH, Colab, Jupyter, CI, …) | Detection is by environment variables; an unrecognised remote environment is not detected |
| V3 | No hosting, sharing or tunnelling feature exists | Cannot stop a user from deliberately tunnelling the port |
| V4 | All assets bundled; CSP `default-src 'none'` with `'self'` only for scripts, styles, images and fetch; in-process block on non-loopback connections and name lookups while serving; tests scan assets for external origins | The guard does not cover subprocesses or native code; the browser itself may contact its vendor |
| V5 | `Cache-Control: no-store` and related headers; no download/export endpoint; context menu, drag and printing of media suppressed; images rendered from same-origin URLs only | Screenshots, screen recording, browser developer tools and the browser's own caches/crash dumps are outside the page's control |
| V6 | `.gitignore` excludes review stores, `frp-review-*/` and access logs; identifiable stores inside a git working tree are refused | Cannot stop a deliberate copy into a repository or attachment |
| V7 | Media addressed by random opaque ids looked up in the catalogue; filesystem paths never appear in responses, errors, logs or records; item labels are positional ("Item 2 of 7") | Content of the media itself is, by necessity, identifiable in Mode A |
| V8 | Private grant must name the reviewer role code and mode; private append-only `access-log.jsonl` records session open/close, first view of each reference/output, measurement reveals and record saves, with opaque references only | Role codes are not authentication; the operating-system account is the real access boundary |
| V9 | Withdrawal scope and verification hooks; owner-only permissions; session ends leave no thumbnails on disk (frames are served from the store) | No retention schedule or deletion procedure is implemented; backups are out of scope |
| V10 | Persistent on-page warning and banner; documented below | Not technically enforceable |
| V11 | Fail-closed: missing storage approval, remote environment, store in a git working tree or accessible to group/others, missing/expired/mismatched grant, or a synthetic label on non-demo frames each refuse the session before any media is read | Only as strong as the private grant provider, which does not exist yet |
| V12 | Strict catalogue and record schemas; ids pattern-checked; symlinks and out-of-store paths refused; size limits; per-frame digest check; PNG structure and CRC validated and all ancillary (metadata) chunks dropped before serving; all text inserted with `textContent`, never as markup | Pixel decoding happens in the browser's image decoder, not in a separate constrained process |

### Residual risks software cannot eliminate

- Screenshots, screen recording, phone cameras, screen sharing and shoulder-surfing (V10).
- A compromised or shared reviewer machine, other local users, browser extensions, and the browser's own crash reports or caches.
- Copies made outside the store (backups, synced folders, provider snapshots), which withdrawal verification cannot see.
- Reviewer judgement bias, fatigue and anchoring; hiding measurements until requested limits but does not remove anchoring.
- Mode B blinding can be broken by recognising a clip seen elsewhere; the Mode A exclusion applies only to records in the same store.

### Not implemented (future, separately reviewed)

A private `ReviewAccessProvider` that issues grants; import of real Wan outputs and consented references into a store; a retention schedule and verified deletion procedure; agreement statistics; any real-data report.
