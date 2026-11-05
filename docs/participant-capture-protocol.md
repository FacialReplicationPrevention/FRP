# Participant capture protocol — future adult-consenting participants (draft)

**Status:** Draft procedure for **future, separately authorised** use (Milestone 004, PR 3G, [#25](https://github.com/FacialReplicationPrevention/FRP/issues/25)). **This is not a request to collect any photograph now.** No participant has been recruited, no consent obtained, no image captured, and no readiness gate has passed (see [GPU readiness](gpu-readiness.md); all seven stay `pending`).
**Scope:** Wan 2.1 I2V-14B-480P single-condition baseline ([Experiment 003](../experiments/003-wan21-i2v-baseline-design.md)). Nothing here applies to the Milestone 005 A/B/C/D study, and nothing claims Wan 2.2 shares this design.
**Companions:** [Analysis preregistration](baseline-analysis-preregistration.md), [Participant data lifecycle](participant-data-lifecycle.md), [Private review viewer](private-review-viewer.md).

## Evidence labels

| Label | Meaning |
| --- | --- |
| **[proposal]** | A controlled starting rule chosen by FRP for review. Not an upstream Wan requirement, not validated, not a threshold. |
| **[requirement]** | A need to assess before use. |
| **[pending]** | Deliberately unset; a qualified human decides. |

Upstream Wan 2.1 documents no portrait-framing requirement that FRP has verified. Every framing, size and quality rule below is a **[proposal]** to make captures comparable and inspectable; none is asserted as something the model needs.

## 1. Roles and what each input may support

| Role | Input | Supports | Never supports |
| --- | --- | --- | --- |
| `smoke` | One reference photo of one consented adult | Technical pass/fail of the pipeline | Any similarity, retention or population statement |
| `calibration` | Reference photos **plus** independently captured same-person photos of calibration identities | Choosing recogniser/quality operating points | Evaluation of the same identities |
| `baseline` | Reference photos of **evaluation** identities, disjoint from calibration | Descriptive, identity-clustered measurement | Efficacy or protection claims |

- **Reference photo** = the single image given to Wan on both the CLIP and VAE routes (`image_count_per_identity: 1`, original on both routes, `use_prompt_extend: false`).
- **Calibration photos** = separate captures of the same person, never the reference photo, used only as genuine-comparison material. They are captured and stored separately and are not selected by looking at generated output.
- **Calibration and evaluation identities must be disjoint**, as the manifest already enforces per run set (`frp.baseline.manifest`) and the draft plan check enforces across lists (`frp.baseline.analysis_plan`).
- **One willing participant supports only the technical smoke role, or an explicitly exploratory demonstration.** One person cannot supply identity-disjoint calibration and evaluation populations, impostors, or population-level uncertainty. A single participant never yields a calibrated, population-level baseline.

## 2. Participant eligibility (summary; the full process is in the [lifecycle](participant-data-lifecycle.md))

Adult only; specific, informed, withdrawable consent for the named purposes; no capture before consent is recorded privately. Consent for one purpose is not consent for another. Willingness to be photographed is not approval of any readiness gate.

## 3. Capture specification **[proposal]**

| Aspect | Proposed starting rule | Notes |
| --- | --- | --- |
| Framing | Head-and-shoulders, single person, face unobstructed, near-frontal | Controlled starting point only. Not claimed to be an upstream requirement. Do **not** silently crop; if a face-only crop or full-body image is used, record it as a different, exploratory input class. |
| Minimum facial detail | Face region visibly sharp with eyes, nose, mouth and facial contour resolvable; numeric minimum face size **[pending]** | Set only after a detector exists and pilot evidence supports a number. |
| Pose | Neutral, looking toward camera; yaw/pitch tolerance **[pending]** | Altered poses are **exploratory**, not baseline. |
| Expression | Neutral or mild natural; no extreme expression | Other expressions: exploratory. |
| Lighting | Even, diffuse, no strong cast shadows or blown highlights on the face | Record light type descriptively, not by location. |
| Occlusion | No hat, hand, hair across eyes, mask or heavy shadow over the face; glasses recorded as present/absent | Glasses captured in a session are a labelled condition, not mixed silently. |
| Sharpness | No motion blur or missed focus on the face | Judged by the checklist below; an automated score is not defined here. |
| Resolution / compression | Highest practical native resolution; minimal compression; no beautify filters, upscaling, or AI enhancement | Record the capture-device class and file format at a coarse level. Resolution minimum **[pending]**. |
| Background | Plain and uncluttered; no other faces or readable text | |
| Provenance | Captured by the project for this purpose, never taken from social media or third-party sources | Record capture-by-whom as an opaque operator label. |

## 4. Quality / rejection checklist (inspectable)

Reviewed by a human operator **before** any generation, against the photo only. Record one result per item and a reason code for any failure. Never evaluate against generated output.

| # | Check | Pass criterion | Reason code if failed |
| --- | --- | --- | --- |
| 1 | Exactly one face | One clear face | `R01_FACE_COUNT` |
| 2 | Face visible | Whole face inside frame | `R02_FACE_CUT` |
| 3 | Sufficient detail | Features resolvable on inspection | `R03_LOW_DETAIL` |
| 4 | Focus / motion | Face sharp | `R04_BLUR` |
| 5 | Lighting | Even, no clipped regions | `R05_LIGHTING` |
| 6 | Occlusion | None beyond recorded glasses | `R06_OCCLUSION` |
| 7 | Pose / expression | Within proposal | `R07_POSE_EXPR` |
| 8 | Processing | No filter, retouch, upscale | `R08_PROCESSED` |
| 9 | Compression | No visible block artefacts | `R09_COMPRESSION` |
| 10 | Provenance | Captured in-session as recorded | `R10_PROVENANCE` |
| 11 | Consent state | Consent record exists privately for this purpose | `R11_CONSENT` |
| 12 | Role separation | Photo not reused across reference and calibration roles | `R12_ROLE_REUSE` |

Allowed recapture reasons are exactly these codes plus `R99_WITHDRAWN`. Recapture is at most a fixed number of times per participant per session (**[pending]**, set by the plan). **Every rejected capture and its reason code is logged** (a rejection count is reported, not dropped). A capture rejected for any reason is never revisited because of how a model rendered it.

## 5. Per-session reproducibility metadata (private record)

Recorded in private storage, never in Git: session label (opaque), operator label (opaque), capture-device class, file format, native resolution, lighting description, glasses present/absent, checklist outcome per item, reason codes, recapture count, role assignment, SHA-256 of the stored file, protocol version, and the plan version in force. **Strip EXIF, GPS, device serial numbers and timestamps finer than the session day before storing derived copies**; keep the original only if the lifecycle document's classification requires it and in restricted storage.

## 6. Input selection without cherry-picking

1. Capture and checklist-review **before** any generation.
2. The first photo that passes the checklist for a role is the one assigned to that role (ordered by capture sequence). If several pass, the earliest in capture order is used; a different rule is a recorded **[pending]** decision made before capture.
3. Role assignment and the identity split (calibration vs evaluation) are decided and recorded **before** any output exists, by a procedure independent of output (e.g. a seeded assignment recorded in the plan), and are not changed afterwards.
4. No photo is replaced because its video looked poor, its similarity was low, or a face detector failed. A generation failure is reported as a failure.
5. Excluding a participant after outputs exist is allowed only for withdrawal or a recorded consent/eligibility problem, and the exclusion is reported.

## 7. Synthetic example records (fictional; opaque labels only)

```yaml
# SYNTHETIC. Opaque labels. No name, date of birth, location, EXIF or consent evidence.
session: SYN-SESSION-001
participant: SYN-101
role: smoke
capture_class: head_and_shoulders_proposal
glasses: absent
checklist: {R01: pass, R02: pass, R03: pass, R04: pass, R05: pass, R06: pass}
recaptures: 0
status: draft_example_only
```

## 8. Open decisions for human review

Numeric minimum face size and resolution; pose tolerance; recapture cap; whether glasses/other conditions are a separate exploratory class; how many participants are available; whether a different framing is needed after pilot evidence. None is decided here.

## 9. Limitations

This protocol is unvalidated, covers capture only, and creates no approval. It cannot establish consent, adult status or lawful processing.
