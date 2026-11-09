# Face-evaluation and calibration readiness (Milestone 004, PR 3I)

> **Status: planning only — nothing here is approved, installed, downloaded, run or measured.**
> No detector, recogniser, weight file, package, image or embedding is added, fetched or executed
> by this PR. All seven human GPU-readiness gates in [gpu-readiness.md](gpu-readiness.md) stay
> `pending`; a legal/licence review remains gate 1. No FRP real-face measurement or mitigation
> efficacy exists. Merging this document approves no recogniser, licence use, threshold, sample
> size or data processing.

Claim classes used below: **[source]** = read from a public primary page at the stated revision
(text only, not executed); **[proposal]** = FRP design suggestion; **[synthetic]** = behaviour of
CPU tests on fabricated numbers; **[unverified]** = not checked, to be verified later and
privately. Related: [preregistration draft](baseline-analysis-preregistration.md) (decisions
D06–D19, referred to rather than restated), [capture protocol](participant-capture-protocol.md),
[data lifecycle](participant-data-lifecycle.md), [Research 001](../research/001-identity-replication-measurement.md),
[Experiment 003](../experiments/003-wan21-i2v-baseline-design.md).

## 1. Gap analysis of `main` (after merged PR #28)

| Need | Already present | Gap |
|---|---|---|
| Evaluator contract | `FaceIdentityEvaluator.evaluate(artefact, pseudonym, frame_indices)` → one `FrameEvaluation` per index; similarity only for `valid` faces; `FaceEvaluatorInfo` records name/revision/settings digest/`simulated` | None for the contract; no real adapter exists (by design) |
| Post-hoc use | `evaluate_baseline_results` refuses smoke, repeat evaluation and simulated/real mismatch; exceptions become `error` without messages | — |
| Aggregation | `aggregate_baseline`: all attempts and denominators, frame 0 separate, later-frame median over valid frames, `calibration_status = uncalibrated`, estimator refused for real/smoke | No threshold, FMR/FNMR or calibration concept (intended) |
| Plan check | `frp.baseline.analysis_plan` checks pseudonym-string disjointness and ≥2 calibration identities | Cannot show person-level disjointness (D19, private steward) |
| Calibration diagnostics | none | See §6: justified as **tests only**; no production module added |

## 2. Candidate detection + recognition pipelines (comparison matrix)

"ArcFace" is a *training loss / algorithm*, not a single ready-to-use checkpoint. Four layers must
be named separately for any pipeline: algorithm, framework package, pretrained-weight
repository, and the face detector/aligner. Revisions are the default-branch heads read on
2026-11-09 (**not** release pins; a real pin must be chosen and recorded in a reviewed change).

| ID | Detector / aligner | Recogniser (algorithm → weights) | Code licence **[source]** | Weight / training-data terms **[source]** | Source status |
|---|---|---|---|---|---|
| P1 InsightFace family | SCRFD or the package's bundled detector (which model files, unverified) | ArcFace-family (e.g. ResNet via the `insightface` package; `buffalo_*` packs) | MIT, per README ("no limitation for both academic and commercial usage"). No top-level `LICENSE` file found at `deepinsight/insightface@c6c3af7` (path 404); the README statement is the only text read | README: training data "and the models trained with these data" are **non-commercial research purposes only**; package auto-downloads follow the same policy; `buffalo_l` recognition pack: README directs licensing enquiries to the vendor | Primary README (secondary for per-model file lists: not retrieved) |
| P2 Independent second method A | dlib HOG or CNN (`mmod_human_face_detector`) + 5/68-point landmarks | dlib ResNet metric-learning model (`dlib_face_recognition_resnet_model_v1`) | Library licence: not retrieved (Boost expected, **unverified**) | `dlib-models` repo: CC0-1.0 declared; README says trained on ~3M faces scraped/derived from FaceScrub, VGG, and other scraped images; landmark models note a dataset licence excluding commercial use. Whether CC0 on the weights resolves training-data restrictions is **unresolved** | Primary README + LICENSE at `davisking/dlib-models@fd81b63` |
| P3 Independent second method B | MTCNN (as shipped by `facenet-pytorch`) | Inception-ResNet-V1 (FaceNet-style), VGGFace2 or CASIA-WebFace weights | MIT (`timesler/facenet-pytorch@787da06`) | Weight files are release assets; their terms and the VGGFace2/CASIA dataset terms are **not retrieved / unresolved** | Primary README + LICENSE |
| P4 Quality-aware variant | any of the above | AdaFace (quality-adaptive margin) with CASIA/WebFace/MS1MV2/MS1MV3 weights | MIT declared for repo (`mk-minchul/AdaFace@c60eaa7`) | Weights distributed via links in README; dataset terms (MS1M/WebFace families) **unresolved**; same-training-data caveat vs P1 | Primary README (licence file via API only) |
| P5 Human judgement | n/a | Blinded visual rating ([viewer spec](private-review-viewer.md)) | n/a | n/a | Not a ground-truth identity label; a distinct observation mode |

Not assessed (unretrieved, **unverified**): MediaPipe, RetinaFace and cloud APIs. Cloud face APIs
are excluded by the no-external-contact and data-retention constraints unless gate 2/4 reviews
decide otherwise.

Per-pipeline questions that sources must answer later, privately and with pinned revisions
(all **unverified** now; FRP has measured none): input size and alignment template; embedding
dimension and similarity definition (cosine on L2-normalised vectors is typical, not assumed);
runtime and dependency requirements as *claimed by the source* (CPU feasibility, ONNX/PyTorch/C++
versions); behaviour when no face or several faces are found; sensitivity to pose, occlusion,
compression and generated-video artefacts; published demographic performance gaps; checkpoint
hashes and download provenance; whether the package phones home or auto-downloads at import.

## 3. Licence and use-rights position (not a legal conclusion)

* Code licence, weight licence and training-data restrictions are **three separate questions**.
  Permissive code (P1, P3, P4 MIT) says nothing about weights. For P1 the README itself states
  weights are non-commercial research only; whether FRP's use qualifies (and whether *later public
  reproduction* by others is permitted) is for gate 1 reviewers and is **unresolved**.
* A CC0 declaration on a weights repository (P2) is not assumed to remove restrictions that apply
  to the training data or to third-party landmark datasets.
* Do not assume a research or academic grant covers FRP's use, or that a package's auto-download
  is licensed for the intended purpose.
* Any retrieval failure is to be logged as `not retrieved`, never replaced by an assumed or
  "latest" licence.

## 4. Conditional shortlist (not a selection, not approved)

* **Primary candidate for review: P1** — widest use in the literature and in FRP's own Research
  001 framing — *conditional on* gate 1 resolving the weight/data licence and on pinned,
  hash-verified private weights.
* **Secondary method for review: P2 or P3, chosen so that the pair is as independent as possible.**
  Independence is a spectrum: different architecture, loss, **training data**, detector and
  alignment all matter. Two recognisers sharing a detector/alignment, or trained on overlapping
  data (P1 and P4 both draw on MS1M/WebFace families), are *not* automatically independent, and
  agreement between them is weaker evidence than between genuinely different pipelines. A second
  method can show whether a finding is recogniser-specific (D11); it cannot establish ground truth.
  Human visual judgement is another observation mode, with its own bias and not a label.
* **Trade-offs [proposal]:** P1 — strong and common, licence-constrained, heavier dependencies;
  P2 — small, CPU-friendly, older and weaker on hard poses, dataset provenance questions; P3 —
  simple PyTorch stack, weaker than modern margin-loss models, dataset terms unresolved.
* **If no pipeline clears gate 1, the evaluator stays unselected** and the baseline remains
  uncalibrated/exploratory. That is an acceptable outcome to record.

## 5. Proposed evaluator adapter boundary (design only)

A future private adapter (not in `src/` public paths, never auto-constructed by a command, default
or CI path) would implement the existing protocol unchanged:

* `info`: `FaceEvaluatorInfo(name=<pipeline id>, revision=<pinned source+weights id>,
  settings_sha256=<digest of detector/alignment/similarity settings>, simulated=False)`. The
  digest, hashes and paths live in private records, not the public repo.
* `evaluate(...)`: locate the private reference by pseudonym; for each requested frame run the
  detector then the recogniser, and return one `FrameEvaluation` in order. Status mapping:
  `valid` (exactly one face passing the quality criteria) → similarity; `absent` (none);
  `multiple` (≥2 faces above the detection threshold — **never choose the best-scoring face**);
  `low_quality` (face found but fails the proposed criteria, below); `error` (any exception, no
  message text); `not_evaluated` is reserved for failed/unexecuted generation. No status other
  than `valid` carries a similarity, and nothing is imputed as zero.
* Detector, crop, alignment and similarity definitions must be identical across reference
  photographs, calibration pairs and generated frames; reference photos must be independent of
  the Wan conditioning image and from a separate capture ([capture protocol](participant-capture-protocol.md)).
* Proposed (not approved) quality criteria: minimum face size in pixels, detector confidence
  floor, pose/landmark sanity, blur/exposure bounds; values are chosen **before** looking at
  results and belong to D16/D13-adjacent private decisions. Raw frames, crops and embeddings are
  never logged or committed.

## 6. Calibration methodology (proposal; links to D11–D16, D19)

**Separate quantities, never merged into one score:** (1) detection coverage / per-status
denominators; (2) identity similarity on valid faces; (3) operating-point decisions and error
rates at a threshold fixed beforehand; (4) video utility (automated + blinded rubric, D16);
(5) human impression. A cosine similarity is not a calibrated match, not proof of personhood and
not a consent signal ([AGENTS.md](../AGENTS.md)).

**Controls (future, private, independent consenting adults):**

* *Genuine photo pairs*: two independent photographs of the same adult.
* *Impostor photo pairs*: photographs of different adults.
* *Generated-video impostor controls*: a generated frame from a clip conditioned on person A
  compared with a *different* person B's reference, matched where feasible on prompt, seed,
  sampled frame index, pose/quality and processing — so that video artefacts are not mistaken
  for identity differences.
* *Calibration and evaluation are separated by actual person*, verified by the private data
  steward against the restricted mapping (D19). Different pseudonyms do not establish different
  humans; `analysis_plan` only compares strings.

**Error rates (definitions, with denominators).** At a *caller-fixed* threshold *t* and the rule
"match if similarity ≥ *t*" (the proposed boundary convention; ties count as matches), FMR (=FAR)
= impostor comparisons with similarity ≥ *t* ÷ valid impostor comparisons; FNMR (=FRR) = genuine
comparisons with similarity < *t* ÷ valid genuine comparisons. Comparisons without a valid face
are excluded from both denominators **and counted separately**; a zero denominator makes the rate
*undefined*, never 0. FMR and FNMR trade off as *t* moves; a threshold is specific to
recogniser, version, preprocessing and population, and photo-to-photo scores need not transfer to
reference-to-generated-video scores. This PR sets **no** universal cutoff, target error rate or
numeric threshold (D13), no sample size (D14), no uncertainty method (D15).

**Analysis rules retained:** frame 0 reported separately; later frames primary; explicit
minimum-valid-later-frames rule (D06, pending); first/last-attempt logic (D09); all attempts and
missingness kept; clip → identity → role aggregation. **A single participant is smoke/exploratory
only and never scientific calibration.** Thresholds are never tuned on evaluation identities.

### Decision register (3I does not settle any row)

| Decision | Owner (proposed) | State after 3I | Evidence needed before any approval |
|---|---|---|---|
| D11 recogniser / second method | Scientific lead + licence reviewer | Review | Gate 1 licence result per pipeline; pinned revisions and hashes; independence argument |
| D12 controls | Scientific lead + data steward | Proposed | Consent covering photo and video controls; capture design review |
| D13 operating thresholds | Scientific lead | **Pending** | Calibration identities only; no numeric value proposed here |
| D14 minimum identities / sample size | Statistician | **Pending** | Pilot evidence; no number proposed here |
| D15 uncertainty method | Statistician | Review | Method choice; few-identity behaviour; not approved |
| D16 quality rubric | Scientific lead + reviewers | Review | Validated rubric and blinding procedure |
| D19 real-world disjointness | Private data steward | Review | Private mapping check before calibration and evaluation |

## 7. Synthetic diagnostics: why no production module was added

The existing components already enforce the evaluator-side invariants (status/similarity
separation, error redaction, denominators, frame-0 separation, simulated/real refusal,
`uncalibrated`). The missing material is a demonstration of FMR/FNMR arithmetic, which a
documented, test-local helper in `tests/test_face_calibration_readiness.py` shows without
creating a public calibration API, schema, CLI or any route to real data. A `frp` helper would
risk being read as a general calibration library or being wired to `aggregate_baseline`; it was
therefore **omitted**. The tests use fabricated numbers with **no inferential meaning**
(SIMULATED / METHOD TEST ONLY).

## 8. What is not established

No recogniser performance, licence permission, calibration, threshold, sample size, interval,
demographic effect, protection or consent property has been measured or approved. External
statements above were read from public text only; nothing was downloaded or executed, and
unretrieved facts remain `unverified`. Blocker matrix: gate 1 (licence), gate 2 (consent/data),
gate 3 (storage), D11–D16 and D19 — all open; parent #9 stays open and Milestone 005 (#14)
stays blocked.
