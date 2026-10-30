# FRP CPU-only harness — manifest, A/B/C/D planner, simulated pipeline, provenance and readiness validators

**Status:** Phase 2 Milestones 001 (manifest schema and dry-run planner,
[issue #1](https://github.com/FacialReplicationPrevention/FRP/issues/1),
[PR #2](https://github.com/FacialReplicationPrevention/FRP/pull/2)) and 002 (simulated
execution, evaluation and reporting,
[issue #5](https://github.com/FacialReplicationPrevention/FRP/issues/5),
[PR #6](https://github.com/FacialReplicationPrevention/FRP/pull/6)) and Phase 2b
Milestone 003 (model provenance inventory and offline validator,
[issue #7](https://github.com/FacialReplicationPrevention/FRP/issues/7),
[PR #8](https://github.com/FacialReplicationPrevention/FRP/pull/8)) are merged. Milestone 004
([issue #9](https://github.com/FacialReplicationPrevention/FRP/issues/9)) is current; its PR 1
adds the offline readiness-template check described
[below](#gpu-readiness-template-milestone-004-pr-1) and design documents only.

**No real inference or measurement.** The harness loads no model, runs no inference, reads no
images, computes no embeddings and has **measured no scientific outcome**. A valid manifest,
run plan or simulated report is not evidence that any conditioning alteration protects
identity. Simulated reports test software contracts only.

**Model scope.** FRP's research mission covers multiple generative model families, but the
fixed A/B/C/D mapping, run plan, result protocol id (`wan2.1-i2v-clip-vae-2x2`) and simulated
executor model family (`wan2.1-i2v`) model the **Wan 2.1 I2V** CLIP/VAE ablation hypothesis
only. Nothing here implies support for Wan 2.2 or any other model; another model family needs
its own source-verified, reviewed protocol. [Research 005](../research/005-wan-model-candidates.md)
found that Wan 2.2 I2V-A14B has no CLIP-vision path at its pinned commit, and the provenance
validator rejects declaring the Wan 2.1 protocol for it (see
[below](#model-provenance-inventory-milestone-003)).

## What it does

1. Parses a YAML (or JSON) experiment manifest and validates it against schema version `1.0`.
2. Generates a deterministic, paired run plan for the 2 × 2 design in
   [Experiment 002](../experiments/002-conditioning-ablation-protocol.md).
3. Verifies pairing invariants and prints a privacy-safe summary (`frp plan … --dry-run`).
4. Runs the plan through **simulated** executor and evaluator adapters, validates the result
   records against the plan, aggregates them identity-first and writes aggregate-only
   Markdown/CSV reports (`frp simulate …`).
5. Validates the model-candidate provenance inventory offline (`frp provenance …`).
6. Validates the public GPU-readiness template offline (`frp readiness …`); it grants nothing.

| Module | Responsibility |
| --- | --- |
| [`frp.variants`](../src/frp/variants.py) | Fixed A/B/C/D → (CLIP source, VAE first-frame source) mapping |
| [`frp.manifest`](../src/frp/manifest.py) | Schema, YAML loading, readiness check, content hashes |
| [`frp.planner`](../src/frp/planner.py) | Run-plan generation and invariant verification |
| [`frp.interfaces`](../src/frp/interfaces.py) | Executor, face/identity evaluator and video-quality evaluator contracts |
| [`frp.results`](../src/frp/results.py) | Result schema `1.0`, null rules, plan linkage checks |
| [`frp.pipeline`](../src/frp/pipeline.py) | Orchestrator: plan → adapters → validated result records |
| [`frp.simulation`](../src/frp/simulation.py) | Deterministic synthetic executor/evaluators and scenarios |
| [`frp.aggregation`](../src/frp/aggregation.py) | Frame → clip → identity → variant summaries and paired contrasts |
| [`frp.reporting`](../src/frp/reporting.py) | Aggregate-only Markdown and CSV reports (report schema `1.0`) |
| [`frp.provenance`](../src/frp/provenance.py) | Provenance schema `1.0`, claim status rules, protocol scope guard |
| [`frp.readiness`](../src/frp/readiness.py) | Readiness schema `1.0`: public GPU-readiness template, pending-only gates, fixed controls |
| [`frp.cli`](../src/frp/cli.py) | `frp plan MANIFEST --dry-run`, `frp simulate MANIFEST --report-dir DIR`, `frp provenance INVENTORY`, `frp readiness RECORD` |

## Reproducible local commands

In a clean CPU Codespace (Python 3.11+; no GPU, network model downloads or personal data):

~~~bash
python -m pip install -c constraints.txt -e ".[dev]"
ruff check .
ruff format --check .
pytest -q
frp plan examples/manifests/synthetic-dry-run.yaml --dry-run
frp simulate examples/manifests/synthetic-dry-run.yaml --report-dir runs/simulated-report
frp provenance provenance/model-candidates.yaml
frp readiness readiness/wan21-i2v-baseline.yaml --provenance provenance/model-candidates.yaml
~~~

`runs/` is git-ignored. `frp simulate` refuses to replace existing report files unless
`--overwrite` is passed, and its output is byte-for-byte reproducible for the same manifest,
scenario and `frp` version.

## Manifest schema 1.0

See the synthetic example in
[`examples/manifests/synthetic-dry-run.yaml`](../examples/manifests/synthetic-dry-run.yaml).

### Planning inputs (required, non-empty)

| Field | Rules |
| --- | --- |
| `schema_version` | Must be the string `"1.0"` (quote it in YAML) |
| `experiment_id` | Upper-case letters, digits and `-` |
| `status` | Must be `planned` |
| `variants` | Each of `A`, `B`, `C`, `D` exactly once; listing order does not affect the plan |
| `identities` | `[{pseudonym: SYN-001}, …]`; format `^[A-Z]{2,8}-[0-9]{3,8}$`; unique; no other keys |
| `prompts` | `[{id, text}, …]`; unique ids and unique texts |
| `seeds` | Unique integers in `[0, 2**32 - 1]`; booleans, floats and strings are rejected |

### Execution fields (may be `null` while planning)

All other fields from the Experiment 002 example manifest are **required keys**. While planning
they may be `null`, which is the *only* accepted "explicitly unset" marker. Placeholder text
such as `TODO`, `TBD`, `<fill me>`, `{{ x }}`, `???` or `N/A` is rejected so that unset values
cannot be mistaken for real ones. `frp plan … --dry-run` lists every unset field;
`--require-ready` exits with code 3 until all are set and `model_license_reviewed` is `true`.
Readiness is a **presence and format check only**: it does not verify consent, licence
validity, that hashes match real files, or that the selected values are scientifically
appropriate.

Format checks applied when a value is set: `upstream_commit_sha` is a 40-hex Git SHA;
`checkpoint_hashes` maps file names to 64-hex SHA-256 digests; `frame_count` has the form
4n+1; `frame_indices` are strictly increasing and below `frame_count`; `resolution` uses
Wan's `W*H` form (e.g. `832*480`); `number_of_identities`, if set, equals the identity count.

Fixed values: `consent_record_location: private_only` and `image_count_per_identity: 1`.

**Wan 2.1-only guard.** Schema 1.0 plans the Wan 2.1 I2V CLIP × VAE protocol only, so it fails
closed on any other model: `upstream_repository` must be `Wan-Video/Wan2.1` and `checkpoint`
must be `Wan-AI/Wan2.1-I2V-14B-480P` (case-insensitive). A manifest naming Wan 2.2 or another
checkpoint is rejected by `frp plan` and `frp simulate` with exit code 1 and no plan. The allowed
values are `WAN21_SOURCE_REPOSITORY` and `WAN21_I2V_CHECKPOINTS` in `frp.manifest`, which also
define the provenance protocol scope; widening them needs scientific review.

### Strictness

Unknown keys, duplicate YAML keys, custom YAML tags, multi-document files, type coercion
(e.g. `"42"` for a seed), non-finite floats (`.inf`, `.nan`) and non-mapping documents are
rejected. Exponent-form numbers such as `1e-05` (as written by JSON serialisers) load as floats,
not strings. Validation errors report the schema path, rule and YAML line/column but never echo
input values: user-supplied mapping keys are shown as `<key>`, and YAML parser messages are
replaced by fixed descriptions.

## How A/B/C/D pairing is guaranteed

- A **trial group** is one `(identity, prompt, seed)` tuple. Groups are the Cartesian product
  identities × prompts × seeds, in manifest order, numbered from 1.
- Each group contains exactly four runs in the fixed order A, B, C, D. The conditioning for
  each variant comes from the immutable protocol table in `frp.variants`, not from the manifest.
- Every run in a group carries the same identity, prompt id, seed and
  `generation_controls_sha256` (a hash of model revision, checkpoint, alteration and sampling
  settings). Only `clip_conditioning` and `vae_first_frame_conditioning` vary.
- `generate_run_plan` always calls `verify_run_plan`, which re-checks these invariants plus:
  every run id equals `make_run_id(experiment_id, group_index, variant)` (so a unique but
  wrong or swapped id is rejected), unique run ids, unique tuples, consecutive numbering and,
  when the manifest is supplied, matching experiment id and exact, index-consistent coverage
  of the manifest product. Tests tamper with plans to confirm each violation is detected.

## Privacy of CLI output

- Identity pseudonyms are replaced by ordinal labels (`identity-01`) unless
  `--show-pseudonyms` is passed; keep such output private, as Experiment 002 treats
  pseudonyms as non-public.
- Prompt ids are user-controlled and could accidentally contain personal information, so
  they are replaced by ordinal labels (`prompt-01`, in manifest order) unless
  `--show-prompt-ids` is passed for private debugging.
- Prompt text, file paths, image references and embeddings are never printed. The manifest is
  identified by a SHA-256 content hash.
- Run ids (`<experiment_id>-G0001-A`) contain no pseudonym, prompt text or seed.

Exit codes: `0` success, `1` invalid manifest/plan (or, for `simulate`, invalid results; for
`provenance`, an invalid inventory), `2` usage error (including omitting `--dry-run` for
`plan`), `3` not ready (only with `--require-ready`), `4` report files could not be written
(including existing files without `--overwrite`).

## Simulated pipeline (Milestone 002)

`frp simulate MANIFEST --report-dir DIR [--scenario NAME] [--overwrite]` runs:

```mermaid
flowchart LR
    M[Manifest 1.0] --> P[Verified A/B/C/D run plan]
    P --> E[RunExecutor]
    E -->|artefact reference only| F[FaceIdentityEvaluator]
    E -->|artefact reference only| Q[VideoQualityEvaluator]
    F --> R[ResultSet 1.0]
    Q --> R
    R -->|verified against plan| A[Identity-first aggregation]
    A --> O[report.md + summary.csv]
```

In this milestone every adapter is a deterministic **simulation**; no real adapter exists.

### Adapter interfaces (`frp.interfaces`)

Structural `typing.Protocol` contracts with no ML, imaging or GPU imports. Each adapter exposes
an `info` record (name, revision, simulated flag) that is copied into the results.

| Contract | Input | Output | Notes |
| --- | --- | --- | --- |
| `RunExecutor` | `PlannedRun` | `ExecutionRecord` (`succeeded` + artefact reference, or `failed` + failure category) | Wan 2.1 A/B/C/D specific because it consumes the Wan 2.1 plan; `not_executed` is set only by the orchestrator |
| `FaceIdentityEvaluator` | artefact reference, identity pseudonym, frame indices | one `FrameEvaluation` per frame, in order | Not told the variant. Detection status is separate from similarity |
| `VideoQualityEvaluator` | artefact reference only | `QualityEvaluation` | Blind to variant and identity; unscorable output is a status, never an invented score |

The orchestrator (`frp.pipeline.execute_plan`) verifies the plan and runs a **preflight**
before any adapter is called: frame indices must be non-empty, non-negative, strictly
increasing and below `frame_count` when it is known, and component provenance must satisfy the
`ResultSet` rules below (no mixing of simulated and real adapters). It then executes runs in
plan order and assigns exactly one result record per planned run. Adapter exceptions become `failed` runs
(`executor_error`) or `error` evaluations **without** their messages, which could contain
paths or private data. Adapter contract violations (wrong frame list, executor claiming
`not_executed`) raise `ResultValidationError`. `max_runs` simulates an interrupted experiment:
the remaining runs are recorded as `not_executed`, not dropped.

### Result schema 1.0 (`frp.results`)

Result records are **private structured records**: they hold run ids, group, variant,
conditioning, seed and *ordinal* identity/prompt indices, plus artefact references — but never
pseudonyms, prompt text, media or embeddings. Persisting them to private storage is future work;
`parse_result_set_json` validates a serialised `ResultSet`.

| Level | Rules |
| --- | --- |
| `FrameEvaluation` | `face_status` ∈ `valid`, `absent`, `multiple`, `low_quality`, `error`, `not_evaluated`. `similarity` is a finite number in [-1, 1] **only** when `valid`, otherwise `null` (never `0`) |
| `QualityEvaluation` | `status` ∈ `scored`, `unscorable`, `error`, `not_evaluated`; `score` only when `scored`, and within the evaluator's declared scale |
| `ExecutionRecord` | `succeeded` requires an artefact reference (URI form, so a bare file path is rejected); `failed` requires a `failure_category` (fixed vocabulary, no free text); `not_executed` has no runtime. `gpu_seconds` is optional |
| `RunResult` | Conditioning must match the protocol table for its variant; run id must match group and variant; a run that did not succeed must have every frame and quality `not_evaluated` |
| `ResultSet` | `result_schema_version: "1.0"`, `protocol: wan2.1-i2v-clip-vae-2x2` (executor `model_family` must be `wan2.1-i2v`), plan hashes, declared `frame_indices` and their source, adapter info. Every group has exactly one A, B, C and D record with identical identity, prompt and seed. Duplicate run ids are rejected. Simulated and non-simulated adapters may not be mixed, and `simulated` must equal every adapter's flag in both directions; `simulation_scenario` is required for, and only for, simulated results |

`verify_results_against_plan(results, plan, manifest)` additionally rejects missing, orphaned,
duplicate or mismatched records and hash mismatches. With a manifest, frame indices must be
below `frame_count` when it is set and must equal the manifest's `frame_indices` when it sets
them; for **non-simulated** results the manifest must set them and
the evaluator revisions must equal `face_evaluator_revision` and `quality_rubric_version`.
Strictness matches the manifest: unknown keys, type coercion and non-finite numbers are
rejected, and errors never echo input values or unknown key names.

### Simulation scenarios (`frp.simulation`)

All values are synthetic fixtures. Outcomes follow fixed modular rules over (group index,
variant position, frame position); valid-face "similarities" are SHA-256-derived numbers in
[0.1, 0.9] and quality "scores" are integers on a simulated 1–5 rubric. Fixture values do **not**
depend on the variant's conditioning, so any between-variant difference is an artefact.
`gpu_seconds` is left `null` rather than inventing a hardware cost. If the manifest leaves
`frame_indices` unset, the Experiment 002 candidate set `0, 20, 40, 60, 80` (for 81 frames) is
scaled proportionally to `frame_count` when that is set (e.g. `frame_count: 9` gives
`0, 2, 4, 6, 8`), or used as-is when `frame_count` is also unset; either way it is recorded as
`simulation_default`.

| Scenario | Exercises |
| --- | --- |
| `mixed` (default) | Failed runs, an interrupted tail (`not_executed`), every face status and every quality status |
| `all-valid` | Every run succeeds and every value is present |
| `absent-face` | Frames with no detectable face |
| `multiple-faces` | Ambiguous frames with more than one face |
| `evaluator-error` | Face and quality evaluator errors |
| `missing-quality` | Unavailable (`not_evaluated`) and `unscorable` quality |
| `failed-run` | Runs that fail to execute |
| `incomplete` | Experiment interrupted after 75% of planned runs |

### Aggregation (`frp.aggregation`)

Frames within a clip and clips within an identity are **not** independent observations.

1. **Clip:** face-status counts; later-frame similarity = median over `valid` frames with
   index ≠ 0, available only if at least `min_valid_later_frames` (default 1) exist;
   first-frame (index 0) similarity reported separately.
2. **Identity × variant:** median of available clip values.
3. **Variant:** median across identities, with the number of contributing identities.
   Detection coverage, execution and quality status counts are reported as descriptive totals
   with explicit denominators.
4. **Paired contrasts** B − A, C − A, D − A (later-frame similarity and quality): differences
   are formed only within a trial group where both values exist, summarised per identity
   (median), then as a median across identities. Incomplete groups are counted by cause
   (baseline missing, variant missing, both); nothing is imputed. A contrast with no complete
   identity is reported as insufficient.

No calibration, thresholds, confidence intervals or tests are computed. `UncertaintyEstimator`
is the extension point for a future identity-clustered method: it receives one unlabelled value
per identity and returns an interval or `None`.

### Reports (report schema 1.0, `frp.reporting`)

- `report.md` — banner, provenance (hashes, schema versions, adapter revisions, frame indices),
  execution outcomes, detection coverage, similarity, quality, paired contrasts and
  interpretation constraints.
- `summary.csv` — long format with columns `data_provenance, report_schema_version,
  experiment_id, section, subject, metric, value, value_status`. Every row's
  `data_provenance` is `SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE`. Missing values
  are an empty `value` with `value_status` `not_available` (or `not_computed` for intervals).

Reports are aggregate-only: they never contain pseudonyms or ordinal identity labels, prompt ids
or text, seeds, run ids, artefact references, file paths, media or embeddings, and the CLI does
not print the report directory. Adversarial tests plant marker strings in pseudonyms, prompt
ids, prompt text, seeds and the report path and check that none appear. **Only simulated results
can be reported:** `render_markdown`/`render_csv` raise `ReportError` unless the summary and
every adapter (executor, face evaluator, quality evaluator) are marked simulated, until a privacy
review defines disclosure rules for real data (e.g. small-cell suppression).

### Example synthetic output

> SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE. The numbers below come from fixture
> rules and describe no model, person or safeguard.

~~~text
$ frp simulate examples/manifests/synthetic-dry-run.yaml --report-dir runs/simulated-report
SIMULATED DATA — NOT SCIENTIFIC EXPERIMENTAL EVIDENCE
Synthetic fixtures only: no model, image, video, face or embedding was used.

Experiment:  FRP-EXP-002-SYNTHETIC-EXAMPLE (scenario mixed)
Planned runs: 24  Simulated successes: 17  Trial groups: 6
Wrote report.md and summary.csv to the report directory.
~~~

Excerpt of the generated `report.md`:

~~~markdown
## Run execution outcomes

| Variant | CLIP | VAE first frame | Planned | Succeeded | Failed | Not executed |
| --- | --- | --- | --- | --- | --- | --- |
| A | original | original | 6 | 5 | 1 | 0 |
| B | altered | original | 6 | 4 | 1 | 1 |
| C | original | altered | 6 | 4 | 1 | 1 |
| D | altered | altered | 6 | 4 | 1 | 1 |

## Paired comparisons (identity level, no imputation)

| Contrast | Metric | Median identity difference | Identities with pair | Complete groups | Missing A only | Missing variant only | Missing both | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B - A | Later-frame similarity | +0.065 | 2 / 3 | 3 / 6 | 1 | 2 | 0 | incomplete pairs excluded (not imputed) |
~~~

### Milestone 002 decisions for review

These are implementation choices, not protocol changes.

1. **Later frames** are all declared frame indices except `0`; Experiment 002's candidate
   primary set (`20, 40, 60, 80`) follows from this when frame indices are `0, 20, 40, 60, 80`.
2. **`min_valid_later_frames` defaults to 1.** Experiment 002 does not specify a minimum; the
   value should be fixed in the analysis plan before real data.
3. **Primary contrasts are B − A, C − A, D − A** as listed in Experiment 002. The B/C/D
   interaction is not summarised.
4. **Medians at each level** (clip, identity, variant) as a robust descriptive summary; the
   analysis plan may choose otherwise.
5. **Detection coverage totals pool frames** as descriptive counts with explicit denominators,
   alongside identity-level availability; they are not treated as independent observations.
6. **The face evaluator receives the identity pseudonym** (to locate a private reference
   image) but not the variant; the quality evaluator receives only an artefact reference.
   Blinding codes for human raters are still to be designed.
7. **Real-data public reports are disabled** until a privacy review defines disclosure rules.

## Departures from Experiment 002 and decisions for review

These are implementation choices, not protocol changes. Each needs scientific review.

1. **Additional planning fields.** `schema_version`, `variants`, `identities` and `prompts`
   are added; Experiment 002's example has `seeds: null`, but schema 1.0 requires concrete
   seeds because a paired plan cannot be built without them.
2. **Run ids are deterministic ordinals, not random.** Experiment 002 describes `run_id` as a
   "random non-identifying ID". Ordinal ids keep planning reproducible. Because they contain
   the variant letter, they **must not** be shown to blinded quality raters; separate
   blinding codes are still to be designed.
3. **Full crossing.** Every identity is planned with every prompt and seed. Per-identity seed
   or prompt subsets are not supported.
4. **One reference image per identity** (`image_count_per_identity` fixed at `1`), matching the
   pilot description.
5. **Seed range** `[0, 2**32 - 1]`. Negative seeds are rejected because upstream Wan2.1
   replaces `seed < 0` with a random seed (`wan/image2video.py` L199 and `generate.py` L91,
   re-checked at pinned commit `9737cba9c1c3c4d04b33fcad41c111989865d315`). The upper bound is
   a conservative FRP portability choice, not an upstream limit.
6. **`frame_count` must be 4n+1**, following the `--frame_num` help text in upstream
   `generate.py` (L117–L120 at the same pinned commit).
7. **Negative-prompt text is not a separate field.** Research 004 requires identical
   positive/negative prompts across A–D; schema 1.0 relies on `prompt_template_version` for
   this. A dedicated field may be warranted.

## Model provenance inventory (Milestone 003)

`frp provenance INVENTORY [--format text|json]` validates a provenance inventory such as
[`provenance/model-candidates.yaml`](../provenance/model-candidates.yaml) and prints a summary.
It is **static and offline**: it never fetches source code, metadata or weights, imports no ML
packages, and does not re-verify upstream facts. A valid inventory is internally consistent;
whether each evidence link really supports its claim must be reviewed by a person. The research
behind the committed inventory is in [Research 005](../research/005-wan-model-candidates.md).

### Provenance schema 1.0 (`frp.provenance`)

Top level: `provenance_schema_version: "1.0"`, `inventory_id`, `reviewed_on` (ISO date) and a
non-empty list of `candidates`. Each candidate has:

| Field | Rules |
| --- | --- |
| `candidate_id` | Lower-case id; unique (case-insensitive) |
| `model_family` | Lower-case id, e.g. `wan2.1-i2v`, `wan2.2-i2v` |
| `task` | `image-to-video`, `text-image-to-video`, `character-animation` or `speech-to-video` |
| `provenance` | `official`, `official-conversion` or `derivative` |
| `frp_role` | `initial-baseline` (at most one), `later-candidate` or `inventory-only` |
| `source_repository` | GitHub `owner/name`, or `null` if unknown |
| `checkpoint_repository` | Hub `owner/name`; unique (case-insensitive) |
| `source_commit`, `checkpoint_revision` | Claims whose value is a full 40-hex SHA |
| `weight_sha256` | Claim whose value maps relative file names to 64-hex SHA-256 digests |
| `licence` | Claim whose value is a licence identifier such as `Apache-2.0` |
| `conditioning` | Claim whose value lists observed paths: `text_t5`, `clip_vision`, `vae_first_frame_concat`, `first_frame_latent_replacement`, `optional_vlm_prompt_extension` |
| `derived_from` | Claim naming the base checkpoint; required for, and only for, non-official provenance |
| `protocols` | Reviewed protocol ids that may be applied (usually empty) |
| `execution_readiness` | Must be `not_ready`: schema 1.0 cannot mark anything ready to run |

A **claim** is `{value, status, evidence}`. Evidence links must be `https://` URLs on
`github.com`, `huggingface.co` or `arxiv.org`, so local paths and private storage locations are
rejected.

| Status | Value | Evidence |
| --- | --- | --- |
| `verified` | Required | At least one; every link pinned to a 40-hex revision (`/blob/`, `/tree/`, `/commit/` or `/resolve/`) or a versioned arXiv abstract. Moving links such as `/blob/main/` are rejected |
| `pending` | Required | Optional (credible source, FRP check or human review incomplete) |
| `not_verified` | Must be `null` | Optional (not yet checkable) |
| `unknown` | Must be `null` | Optional (not determinable) |

Cross-field rules:

- Evidence URLs are parsed, not substring-matched: a pinned link has the form
  `https://<github.com|huggingface.co>/<owner>/<repo>/<blob|tree|commit|resolve>/<40-hex>[/path]`,
  and only the revision in that path position counts. A SHA in a query string, fragment or later
  path segment is ignored, so a link pinned to a different commit cannot pass.
- A verified `source_commit` must cite a GitHub link whose repository equals `source_repository`
  and whose path revision equals the commit; a verified `checkpoint_revision` must cite a Hugging
  Face link whose repository equals `checkpoint_repository` and whose path revision equals that
  revision. Repository names compare case-insensitively. A commit without a
  `source_repository` is rejected.
- Verified `conditioning` requires a verified `source_commit`, and every evidence link must be a
  source file at exactly that commit (`github.com/<repo>/blob/<sha>/<file>`) or a checkpoint file
  (`blob` or `resolve`) at exactly the verified revision.
- `weight_sha256` can **never** be `verified` in schema 1.0: digests must be checked against
  approved local downloads, a later gated step. Platform-reported digests may be `pending`.
- **Protocol guard.** The only supported protocol is `wan2.1-i2v-clip-vae-2x2`. It may be
  declared only for model family `wan2.1-i2v`, source `Wan-Video/Wan2.1`, checkpoint
  `Wan-AI/Wan2.1-I2V-14B-480P`, `official` provenance, a verified source commit and verified
  conditioning that includes both `clip_vision` and `vae_first_frame_concat`. Relabelling a
  Wan 2.2 candidate's `model_family` does not bypass the source, checkpoint and conditioning
  checks. Unknown protocol ids are rejected without echoing them. Widening this scope (e.g. to
  the 720P checkpoint) requires scientific review.
- Placeholder text (`TODO`, `TBD`, `unknown`, …) is rejected in identifiers and licence values.

Strictness and error safety follow the manifest: unknown keys, duplicate YAML keys, custom tags,
multi-document files and type coercion are rejected, and errors report schema paths and rules
but never input values or user-supplied key names.

Text output lists each candidate's provenance, role, source commit, conditioning status and
protocols, then every claim that is not `verified`, and states that every candidate is
**NOT READY** for execution. `--format json` emits the same summary with claim values and
statuses.

## GPU-readiness template (Milestone 004, PR 1)

`frp readiness RECORD --provenance INVENTORY [--format text|json]` validates a readiness
record such as [`readiness/wan21-i2v-baseline.yaml`](../readiness/wan21-i2v-baseline.yaml). It
is **static and offline**, reads no media, and exists to stop the public template from drifting.
`--provenance` is **required**: without it the command exits `2` (usage error) and reports
nothing, because a record whose pins were only shape-checked must not be reported as valid. A
mismatch with the inventory exits `1`. The comparison is an offline *consistency* check against
the reviewed inventory, not verification of upstream sources or weights.
The procedure it mirrors is in [GPU readiness protocol](gpu-readiness.md).

**A valid record authorises nothing.** Readiness schema 1.0 can describe only a record in which:

| Section | What schema 1.0 enforces |
| --- | --- |
| `gates` | Each of the seven gates exactly once, `status: pending`, `approval_record: null`. `approved` (or any other value) is rejected; approvals, consent and quotes belong in private records |
| `hardware_requirements` | Each requirement exactly once, `status: unverified`, `value: null` (no VRAM, RAM, storage or runtime figure) |
| `cost_quote` | `status: not_obtained` and every field `null` (provider, rate, region, budget cap, charges, …) |
| `execution_controls` | Fixed: `use_prompt_extend: false`, original CLIP and VAE first-frame reference, no identity adapters, no remote inference services, neutral-motion prompts, private output. Undecided controls (seeds, sampler, steps, guidance, frame count, resolution, precision, frame indices, preprocessing, prompt template) are `null` (pending) or, if set, well formed (4n+1 frame count, non-negative unique seeds, `W*H` resolution) — but a set value is still not approved |
| `target` | Wan 2.1 guard retained (`Wan-Video/Wan2.1`, `Wan-AI/Wan2.1-I2V-14B-480P`), full 40-hex pins; the pins must equal a candidate whose source commit and checkpoint revision are `verified` in the provenance inventory (mandatory CLI cross-check) |
| `template_updated_on` | ISO date the template was last edited. It is **not** evidence that any licence, consent or other gate was reviewed |
| `protocol` | `wan2.1-i2v-baseline`, a **draft label** that is deliberately *not* registered in `PROTOCOL_SCOPES` or the result protocol table |

Provenance schema 1.0 is unchanged: `execution_readiness` stays `not_ready` and `weight_sha256`
cannot be `verified`. Making a gate grantable, or weight digests verifiable after local hashing,
would be a *separately proposed, versioned* extension with its own review. The output always
states `Authorised to execute: NO` (`authorised_to_execute: false` in JSON). Validation errors
never echo input values or unknown key names.

## Known limitations

- No real inference, image transform, face detection, identity evaluation or video-quality
  scoring is implemented. Only simulated adapters exist; their outputs are fixtures.
- Simulated reports validate software contracts and denominators, not scientific outcomes.
  Fixture similarity/quality values do not resemble real recogniser or rubric distributions.
- No calibration, match thresholds, uncertainty intervals, interaction analysis or
  inferential statistics are implemented.
- Result records are validated in memory and via `parse_result_set_json`; there is no private
  storage integration, retention policy or CLI for persisting/reloading records.
- Equality of generation controls is guaranteed by construction from a single manifest; the
  harness cannot yet verify that a future executor actually applies them.
- With few identities, aggregate medians can approximate individual values. Real-data public
  reporting is therefore disabled pending a privacy review.
- The pseudonym pattern is a format guard, not proof that a value is non-identifying.
- `--require-ready` checks presence and format, not correctness of hashes, licences or consent.
- The executor contract and result protocol are Wan 2.1 A/B/C/D specific; other model
  families need their own reviewed protocol.
- `frp provenance` checks consistency, not truth: it cannot tell whether a pinned link actually
  shows what a claim says, and it does not re-query upstream repositories.
- The manifest guard compares `upstream_repository` and `checkpoint` identifiers only; it does
  not consult the provenance inventory and cannot confirm that a future executor loads that
  source or checkpoint. Prompt extension (`--use_prompt_extend`) is not yet a locked manifest
  control.
- Dependency lower bounds in `pyproject.toml` are untested; only `constraints.txt` pins are
  tested in CI.
- `frp readiness` checks the public template only. It cannot confirm that any licence, consent,
  storage, provider or budget review took place, and prompt extension is **not yet enforced** by
  any executor or by the Wan 2.1 A/B/C/D manifest. No baseline manifest, run plan, result schema
  or executor exists; [Experiment 003](../experiments/003-wan21-i2v-baseline-design.md) is a
  design only.

## Dependency versioning strategy

`pyproject.toml` declares compatible ranges for runtime (`pydantic`, `PyYAML`) and development
(`pytest`, `ruff`) dependencies. [`constraints.txt`](../constraints.txt) pins the exact tested
set, including transitive packages, and is used by the devcontainer and CI. Update pins
deliberately in a dedicated change and re-run lint and tests. No ML, CUDA or model packages
are dependencies.
