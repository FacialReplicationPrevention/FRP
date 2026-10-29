# FRP CPU-only harness — manifest schema and A/B/C/D dry-run planner

**Status:** Phase 2, first coding increment ([issue #1](https://github.com/FacialReplicationPrevention/FRP/issues/1)).
**Planning / dry-run only.** The harness loads no model, runs no inference, reads no images,
computes no embeddings and has **measured no scientific outcome**. A valid manifest or run
plan is not evidence that any conditioning alteration protects identity.

## What it does

1. Parses a YAML (or JSON) experiment manifest and validates it against schema version `1.0`.
2. Generates a deterministic, paired run plan for the 2 × 2 design in
   [Experiment 002](../experiments/002-conditioning-ablation-protocol.md).
3. Verifies pairing invariants and prints a privacy-safe summary (`frp plan … --dry-run`).

| Module | Responsibility |
| --- | --- |
| [`frp.variants`](../src/frp/variants.py) | Fixed A/B/C/D → (CLIP source, VAE first-frame source) mapping |
| [`frp.manifest`](../src/frp/manifest.py) | Schema, YAML loading, readiness check, content hashes |
| [`frp.planner`](../src/frp/planner.py) | Run-plan generation and invariant verification |
| [`frp.cli`](../src/frp/cli.py) | `frp plan MANIFEST --dry-run` |

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

Exit codes: `0` success, `1` invalid manifest/plan, `2` usage error (including omitting
`--dry-run`), `3` not ready (only with `--require-ready`).

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
   replaces `seed < 0` with a random seed (`wan/image2video.py`, observed at upstream `main`
   commit `9737cba`; re-check at the pinned revision). The upper bound is a conservative
   FRP portability choice, not an upstream limit.
6. **`frame_count` must be 4n+1**, following the `--frame_num` help text in upstream
   `generate.py` (same commit, to be re-checked at the pinned revision).
7. **Negative-prompt text is not a separate field.** Research 004 requires identical
   positive/negative prompts across A–D; schema 1.0 relies on `prompt_template_version` for
   this. A dedicated field may be warranted.

## Known limitations

- No inference, image transform, face detection, identity evaluation, video-quality scoring
  or reporting is implemented; adapter interfaces for these are future work.
- Equality of generation controls is guaranteed by construction from a single manifest; the
  harness cannot yet verify that a future executor actually applies them.
- The pseudonym pattern is a format guard, not proof that a value is non-identifying.
- `--require-ready` checks presence and format, not correctness of hashes, licences or consent.
- Dependency lower bounds in `pyproject.toml` are untested; only `constraints.txt` pins are
  tested in CI.

## Dependency versioning strategy

`pyproject.toml` declares compatible ranges for runtime (`pydantic`, `PyYAML`) and development
(`pytest`, `ruff`) dependencies. [`constraints.txt`](../constraints.txt) pins the exact tested
set, including transitive packages, and is used by the devcontainer and CI. Update pins
deliberately in a dedicated change and re-run lint and tests. No ML, CUDA or model packages
are dependencies.
