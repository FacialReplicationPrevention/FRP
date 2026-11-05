# Participant data lifecycle — private handling design (draft)

**Status:** Design only; **not legal advice** and not a consent form. No participant has been recruited, no consent obtained, no data collected or processed, no provider contacted. Issue [#25](https://github.com/FacialReplicationPrevention/FRP/issues/25) (Milestone 004, PR 3G).
**All seven readiness gates in [GPU readiness](gpu-readiness.md) remain `pending`.** This document, a volunteer's offer to take part, or a completed checklist does **not** satisfy gate 2 (consent and data processing), gate 3 (storage, retention, deletion) or any other gate.
**Companions:** [Participant capture protocol](participant-capture-protocol.md), [Analysis preregistration](baseline-analysis-preregistration.md), [Private execution security design](private-execution-security-design.md), [Private review viewer](private-review-viewer.md).

## 1. Public vs private

| Public (this repository) | Private (access-controlled storage only) |
| --- | --- |
| Procedures, templates, checklists, synthetic examples, privacy-reviewed aggregates | Consent records, age verification, identity mappings, reference and calibration photos, generated clips, extracted frames, embeddings, reviewer records, logs, approvals, quotes |

Never commit or attach private items, including screenshots and access logs.

## 2. Adult verification and consent-purpose checklist (template)

Consent must be **specific, informed and withdrawable**, given by a verified adult **before** any capture. The checklist below is a template for a qualified person to adapt; it is not a completed or approved form, and nothing implies consent has been obtained from anyone.

| # | Item | Done in private record? |
| --- | --- | --- |
| 1 | Adult status verified by an approved method (method **pending**); no ID image kept unless the plan requires it | ☐ |
| 2 | Plain-language description of purpose: neutral image-to-video generation with an open-weight model | ☐ |
| 3 | Purpose: similarity measurement (face matching) on the generated video | ☐ |
| 4 | Purpose: blinded quality review and identity-observation review by named roles | ☐ |
| 5 | Which processors/providers (including a rented GPU host) may see the data | ☐ |
| 6 | What is kept, where, for how long (**retention pending**) and who can access it | ☐ |
| 7 | Right to withdraw at any time without penalty, and what withdrawal can and cannot remove (§6) | ☐ |
| 8 | Whether results may appear in aggregate form only | ☐ |
| 9 | **Optional, separate:** future reuse. Only for a specific, independently reviewed scope, with its own consent. Not blanket consent for future FRP features | ☐ |
| 10 | Statement that taking part grants no approval of any project gate | ☐ |

Consent for generation does not cover reuse, publication of media, or model training.

## 3. Data classification (proposed; handling decisions pending)

| Class | Example | Sensitivity (proposed) | Notes |
| --- | --- | --- | --- |
| Originals | Reference and calibration photos | Restricted; special-category-relevant (see §8) | Strip EXIF/location from derived copies; originals only in restricted storage |
| Generated clips | Wan outputs | Restricted | Identifiable by nature |
| Extracted frames | Sampled frames for evaluation/review | Restricted | In memory or private working dir only; removed at session end |
| Embeddings | Recogniser vectors | Restricted; biometric-derived | Never logged or printed; no public release |
| Reviewer decisions | Ratings, identity observations, free text | Restricted | Free text may contain personal data |
| Audit logs | Access and attempt logs | Restricted | Contain pseudonyms/ordinals, not names |
| Backups, snapshots | Local backups, provider volume snapshots | Same as source | Often outside the software's reach (§7) |
| Consent/ID records | Consent forms, verification result | Restricted; separate store from media | Linking key held separately |

## 4. Access, encryption and ownership (all pending human decisions)

Role-based least privilege, with named roles for operator, reviewer and data steward and separation of the pseudonym-to-person key from media. Encryption at rest and in transit, key custodian, storage owner and location, and whether any cloud copy is permitted are **pending** and belong to gates 3 and 4. The existing private store requires owner-only permissions on a local volume; it states no encryption guarantee.

## 5. Retention (pending)

No retention period is set. A human decides, per class in §3, the period, the review date and the deletion trigger, and records it privately. Default posture until then: do not collect.

## 6. Withdrawal and cascade deletion

A withdrawal propagates to every class in §3 for that participant: media, outputs, frames, embeddings, reviewer records, derived analyses where practicable, logs, backups and processor copies.

What already exists (CPU-tested on synthetic fixtures only, no real data):
- `frp.private_storage`: `withdrawal_run_ids`, tombstone-first `LocalPrivateStore.withdraw` (a withdrawn run can never be reserved or committed again), `remaining()` verification and an irreversible `erase_store`.
- `frp.review`: `withdrawal_scope()` and `withdrawal_remaining()` for review stores.

Limits: these act only on a local store they manage. They do **not** guarantee deletion from backups, synced folders, provider snapshots or other processors, and they do not by themselves remove analyses already computed. Grant revocation by a private provider (not implemented) must precede withdrawal.

**Evidence of verification (private record):** date, operator, scope list, each class checked, tool output showing zero remaining, and explicit notes of copies that could not be verified. Result is "verified for X" or "not verified", never a blanket statement.

## 7. Backups, processors and cloud

Backups and provider-side snapshots may outlive a withdrawal. Whether a provider permits deletion, snapshot control or a data-processing agreement is a gate 4 question. If a copy cannot be deleted, the participant is told before consenting. Residual aggregate results already derived are handled by a pre-agreed rule (**pending**).

## 8. Questions for qualified review (not conclusions)

- UK GDPR: is the processing biometric data for the purpose of unique identification, and does the evaluation use special-category rules? Lawful basis and the Article 9 condition?
- Is consent the right basis, and is it freely given in this context? DPIA required?
- Controller/processor roles for a GPU provider; international transfers; data-processing terms.
- Ethics review route; handling of withdrawal after results are aggregated.
- Retention periods; deletion proof across processors; breach procedure.
- Permissibility of any future reuse and of publishing aggregated results.

## 9. What is not done

No consent collected, no adult verification performed, no storage provisioned, no retention or deletion procedure approved, no provider terms reviewed. Each requires its own human decision and private record.
