# Private visual-review specification (design only)

**Status:** Specification for a future PR (Milestone 004, PR 3). **No viewer has been built, and no real media is used in tests or this repository.**
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

## 6. Verification plan for PR 3 (not done)

- Unit tests with generated synthetic frames (e.g. flat colour or procedural patterns, not faces) for frame selection, later-frame default, status display, blinded mode hiding scores and ids, record immutability and disagreement handling.
- A test that the application opens no non-loopback sockets and makes no outbound requests, and that the page assets reference no external origin.
- A test that logs and records contain no path, pseudonym or media bytes.
- A privacy review of real-data screenshots **before** any appear anywhere; none are committed.

## Residual risks and open questions

- Human judgements of identity are subjective, vary across raters and with image conditions, and are not demographically neutral.
- The number of reviewers and items needed for useful agreement estimates is undetermined.
- Whether the reviewer machine, rather than a stricter environment, is acceptable must be decided under the storage and consent gates.
- The choice of desktop application versus loopback web page is left to PR 3 and must satisfy V1–V12.
