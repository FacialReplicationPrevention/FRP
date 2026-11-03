# Wan 2.1 I2V gated private-execution runbook and adapter contract map (Milestone 004, PR 3B)

**Status: NOT AUTHORISED. NO GPU / NO WEIGHTS / NO REAL MEDIA / NO LIVE INFERENCE.**
Nothing in this document has been performed. The adapter it describes has run only against a CPU
fake of the upstream interface. All seven human gates in the [GPU readiness protocol](gpu-readiness.md)
are **pending**, and neither this document, a passing test nor a merged PR approves any of them.

**Later planning (PR 3D):** the [GPU go/no-go dossier](gpu-go-no-go-dossier.md) maps the PR 3C
residual risks and a fail-closed inspection/stop checklist onto this procedure and proposes (does
not authorise) a single-condition smoke-run spec. It changes no contract in this runbook.

**Issue:** [#13](https://github.com/FacialReplicationPrevention/FRP/issues/13) (sub-task of
[#9](https://github.com/FacialReplicationPrevention/FRP/issues/9)).
**Code:** [`frp.baseline.wan21_adapter`](../src/frp/baseline/wan21_adapter.py),
[`frp.baseline.wan21_probe`](../src/frp/baseline/wan21_probe.py),
[`frp.baseline.wan21_runtime`](../src/frp/baseline/wan21_runtime.py).
**Milestone 004 (3C):** private storage, immutable per-call authorisation, deferred output commit,
source/runtime hardening and the withdrawal ledger are specified in the
[private-execution security design](private-execution-security-design.md) (PR #17) and described in
§6 and §8 below. The 3C code is CPU-tested only and authorises nothing.
**Pins:** source `Wan-Video/Wan2.1` @ `9737cba9c1c3c4d04b33fcad41c111989865d315`; checkpoint
`Wan-AI/Wan2.1-I2V-14B-480P` @ `6b73f84e66371cdfe870c72acd6826e1d61cf279`. Published Hub digests
are **expected values only**; no file has been downloaded or hashed by FRP.

## Evidence labels

| Label | Meaning |
| --- | --- |
| **[code]** | Read in upstream source at the pinned commit (links below). Not executed by FRP. |
| **[metadata]** | Hub file list at the pinned revision (no weights downloaded). |
| **[CPU-fake]** | Exercised by FRP unit tests against a synthetic stand-in. Says nothing about the real model. |
| **[unverified]** | Needs an approved run on real hardware to establish. |

## 1. Architecture

~~~text
Wan21BaselineExecutor  (unchanged gates: exact run -> manifest complete -> private authorisation
   |                    -> no prompt-extension module -> check_available -> clean pinned source
   |                    -> environment digest -> every weight file hashed -> network blocked)
   v
Wan21UpstreamAdapter   (implements Wan21Backend; fail-closed configuration; control mapping;
   |                    geometry; write-once private artefact; typed failures; cleanup)
   |-- ConditioningProbe   (per-call delegating proxies on one WanI2V instance; metadata only)
   v
UpstreamRuntime        (narrow, injectable surface)
   |-- TorchWanRuntime   real: lazy torch/wan imports; constructed by NO command, default or CI path
   |-- FakeRuntime       tests only: synthetic tensors, no pixels, no weights
   v
wan.WanI2V             (pinned upstream; never imported in CI; never run)
~~~

The default backend used everywhere else remains the **disabled** `UpstreamWan21Backend`. The only
provider shipped is `DenyAllAuthorisation`, so with the defaults the adapter is unreachable: the
executor refuses `not_authorised` before calling any adapter method ([CPU-fake] tests assert no
runtime method, load or generate is called). `info.live` is true only when the runtime's type is
exactly `TorchWanRuntime`; through any other runtime every result is labelled `simulated`.

## 2. Contract map

Upstream links: `I2V` = [`wan/image2video.py`][i2v], `GEN` = [`generate.py`][gen].

| `Wan21Backend` method | Executor already validates (reused, unchanged) | Adapter supplies | Upstream source [code] | Cannot yet be verified |
| --- | --- | --- | --- | --- |
| `info` | `simulated = not info.live`; grant must match `executor_mode` | `live` only for the real runtime type; `revision` = pinned source commit | — | — |
| `check_available` | Called only after exact-run, manifest-ready, authorisation and prohibited-module gates; any exception → refusal `backend_unavailable` | `configuration_problems` (precision label, decided controls, pins, 480P size, solver, 4n+1 frames, non-negative seeds, required checkpoint files, no extra pickle files); runtime: no CI/Codespaces, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` unset, torch >= 2.6, deps findable **without importing**, `wan` package in the source checkout | Loader calls [t5.py L496][t5load], [vae.py L614][vaeload], [clip.py L519][clipload]; tokenizers [tokenizers.py L46][tok]; file names [wan_i2v_14B.py L13-L23][cfg] + [metadata] | Whether those `.pth` files load under weights-only unpickling |
| `environment_sha256` | Must equal the approved digest before hashing weights | Installed distributions (all versions per name) + Python version, metadata only | — | Coverage: CUDA driver/toolkit, GPU firmware and container image digest are **not** included |
| `load(VerifiedCheckpoint)` | Only a checkpoint whose every file just matched the private approved SHA-256 manifest; network blocked | Rejects anything but a `VerifiedCheckpoint` and a second load; `device_name()` must equal `gpu_model`; `wan` imported only from the source checkout; `WanI2V(config=WAN_CONFIGS["i2v-14B"], checkpoint_dir, device_id, rank=0, t5_fsdp=False, dit_fsdp=False, use_usp=False, t5_cpu=False, init_on_cpu=True)`; loaded config must equal the pinned facts; INFO logging suppressed during load; failure → unload + `model_load_error`/`resource_exhausted` | Constructor [I2V L34-L131][init]; `WAN_CONFIGS` [configs L20-L28][cfgs]; dtypes [shared_config L10-L19][shared]; VAE dtype [vae.py L624][vaedtype] | Real VRAM, load time, loader safety in production, CUDA init behaviour |
| `generate(request, stop)` | Request built from the exact planned run and frozen manifest; one `reference` field; no prompt-extension field; network blocked; after return: `output_problems`, `verify_conditioning`, prohibited modules | `map_request` (every upstream argument explicit, mismatch → refuse); open reference as `Image.open(..).convert("RGB")`; orientation and exact (h, w) check; probe; stop/deadline polled before each denoiser call; nested network guard that also catches swallowed refusals; same `output_problems` + `verify_conditioning` **before** writing; exclusive-create output, 0600, atomic replace | Signature [I2V L133-L144][sig]; image [GEN L392][img]; tensor + geometry [I2V L181-L193][geo]; seed [I2V L199-L201][seed]; negative prompt [I2V L219-L220][neg]; text [I2V L225-L226][t5]; CLIP [I2V L236][clip]; VAE [I2V L240-L249][vae]; CFG args [I2V L284-L296][args]; CFG calls [I2V L302-L319][calls]; save [GEN L575-L581][save] | Real CLIP/VAE execution; bit-exact CPU bicubic reproducibility used by the VAE input check; runtime per clip; determinism across hardware; probe overhead |
| `cleanup()` | Called after every attempt (success, failure, `KeyboardInterrupt`); failure → `cleanup_ok: false` and the committed artefact is retracted (attempt fails, index stays spent) | Removes reserved/partial files; `gc.collect()` + `torch.cuda.empty_cache()` | — | Whether GPU memory is actually released after an interrupted offloaded run |
| `close()` | Called once by the executor | Drops the pipeline and frees memory | — | — |

## 3. Control mapping

| Manifest field | `GenerationRequest` | Upstream argument | Supported / refused |
| --- | --- | --- | --- |
| prompt (`neutral_motion_only`) | `prompt_text` | `input_prompt` | Must be a planned prompt; the probe checks the text encoder received exactly it |
| reference (`original` on both routes) | `reference` (one) | `img` (PIL RGB) | One image object; the probe checks CLIP and VAE inputs equal it (by value) |
| `seeds` | `seed` | `seed` → `torch.Generator(device).manual_seed` | 0 <= seed <= 2**32-1; negative refused (upstream would randomise) |
| `resolution` | `max_area` | `max_area` | `480*832`, `832*480` only (area 399 360). Orientation follows the reference ([I2V L184-L193][geo]); the adapter requires it to match the `width*height` label ([configs L30-L36][sizes], [text2video.py L131-L132][t2vsize]); square references refused |
| `frame_count` | `frame_count` | `frame_num` | 4n+1 |
| `sampler` | `sample_solver` | `sample_solver` | `unipc`, `dpm++` |
| `sampling_steps` | `sampling_steps` | `sampling_steps` | Must equal the number of positive/negative denoiser pairs observed |
| `guidance_scale` | `guide_scale` | `guide_scale` | Positive |
| `sample_shift` | `sample_shift` | `shift` | Positive; passed explicitly (CLI defaults are not used) |
| `offload_model` | `offload_model` | `offload_model` | Explicit bool (upstream default `True` is not relied on) |
| `negative_prompt_policy: upstream_config_default` | — | `n_prompt=""` | Probe checks the negative text equals the loaded config's `sample_neg_prompt` |
| `precision` | — | none (fixed by config) | Only `upstream-i2v-14B-config` (DiT autocast bf16, T5 bf16, CLIP fp16, VAE fp32); anything else refused. **Proposed label, for review** |
| `gpu_model` | — | — | Must equal `torch.cuda.get_device_name(device_id)` at load |
| `use_prompt_extend: false`, `adapters: none`, `remote_inference_services: none`, `generator` | — | — | Re-asserted; `generate.py` (which imports `wan.utils.prompt_extend` at [GEN L19][genpe]) is never imported |
| `prompt_template_version`, `image_preprocessing_version` | — | — | Labels only; the adapter cannot verify them. Preprocessing (including EXIF orientation, which upstream does not apply) belongs to the private reference provider |

Unsupported and refused: 720P sizes, FSDP/USP/multi-GPU, `t5_cpu=True`, any LoRA/adapter,
prompt extension, a random seed, a custom negative prompt, any precision other than the
upstream config, and checkpoints whose approved file list lacks a file the loaders open or contains
any other pickle-format file (`.pth .pt .bin .pkl .pickle .ckpt`).

**Source observation [code, CPU arithmetic only].** For an exactly `832x480` landscape reference,
upstream's float arithmetic (`399360 * (480 / 832) = 230399.99999999997`) floors the output height
to **464**, giving `464x832`; a `480x832` portrait gives `832x480`. The adapter mirrors this rather
than correcting it. **[unverified]** on real hardware.

## 4. Conditioning instrumentation

`ConditioningProbe` replaces `text_encoder`, `clip`, `vae` and `model` on **one `WanI2V` instance**
with delegating proxies for a single `generate` call, then restores them (the upstream checkout
stays clean). It asserts, failing immediately (no further GPU time) where possible:

1. the text encoder is called exactly twice: the planned prompt, then the config default negative prompt;
2. CLIP `visual` is called once, with exactly the reference (singleton frame axis) **[I2V L236]**;
3. VAE `encode` is called once; frame 0 equals the bicubic resize of the reference and frames 1..F-1 are zero **[I2V L240-L248]**;
4. the denoiser's `y` is the 4 mask channels followed by exactly that encoding **[I2V L249]**;
5. every denoiser call has text, `clip_fea` and `y`; its branch is identified by the text-context object (positive or negative), never by position.

The executor's existing `verify_conditioning` then checks branch order, step count, that both
branches share the same CLIP features and VAE condition objects, and that these are the routes'
outputs. Only shape/dtype/device and branch order are recorded. Comparisons are by value or object
identity and their results are booleans; no tensor value, embedding, image, prompt, token or path
is logged or stored. **[CPU-fake]** for all of the above; whether the real tensors satisfy these
equalities is **[unverified]**.

## 5. Checkpoint loader safety

- `WanModel.from_pretrained(checkpoint_dir)` reads the DiT from `.safetensors` shards **[code, metadata]**.
- T5, VAE and CLIP use `torch.load` **without** `weights_only` **[code]**: [t5.py L496][t5load], [vae.py L614][vaeload], [clip.py L519][clipload]. With torch < 2.6, or with `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` set, this is arbitrary-code-execution-capable unpickling.
- Mitigations in this PR: torch >= 2.6 required (weights-only default); the override variable refused; only the three upstream `.pth` files may be pickle-format; every file is SHA-256 matched to a privately approved manifest before load; network blocked during load; never run in CI or Codespaces.
- Not mitigated: a malicious file that was itself approved; whether these files load under weights-only rules (if not, load fails closed and there is **no unsafe fallback**); the time between hashing and loading on a shared filesystem. Run in an isolated, single-tenant, ephemeral environment without credentials.
- Importing `wan` calls `torch.cuda.current_device()` at import ([t5.py L478][t5cuda]) and sets `TOKENIZERS_PARALLELISM` ([configs L5][cfgenv]); this happens only inside `load`.

## 6. Preconditions: approval-dependent steps (none done)

Each is a separate, recorded human decision in private storage ([GPU readiness §1](gpu-readiness.md#1-the-seven-separate-human-approvals)):

1. `licence_and_intended_use` — licence and research-use review at the pinned revisions.
2. `consent_and_data_processing` — adult, specific, withdrawable consent; lawful basis; ethics/legal review.
3. `restricted_storage_retention_deletion` — private storage for references, outputs, logs; retention; deletion.
4. `cloud_provider_terms` — provider terms/DPA, logging, snapshots, region.
5. `quote_and_budget_cap` — a **dated** provider quote and a hard spend cap; `max_attempt_seconds` derived from it.
6. `checkpoint_download_and_hashing` — download at the pinned revision; local SHA-256 of every file; private expected manifest.
7. `gpu_smoke_test` — explicit approval of one neutral-motion smoke run for named consenting references.

Then, separately reviewed code (not in this PR): a private `AuthorisationProvider` that issues
grants citing all seven records, signed or otherwise authenticated and revocable (3C only enforces
that a grant is unchanged within a call; it cannot establish who issued it); a private
`ReferenceProvider` returning the approved reference bytes (SHA-256 recorded in the grant); a
frozen, hashed execution environment and its digest; a trusted launcher that starts the interpreter
as `python -I -B` with a sanitised environment; and a private entry point that constructs
`LocalPrivateStore` (or an equivalent reviewed store) + `TorchWanRuntime` + `Wan21UpstreamAdapter` +
`Wan21BaselineExecutor`. The executor refuses
(`provenance_mismatch`, before load) unless the backend's declared `source_dir` resolves to the
executor's own verified checkout, and the runtime separately checks that checkout is clean at the
pinned commit before importing (see §10, item 3). The artefact store is now the reviewed
`frp.private_storage.LocalPrivateStore`, which refuses a root that is not a canonical, owner-only
directory on a local POSIX volume (Linux only; Windows and macOS are refused) and creates files
exclusively without following links. That the volume is genuinely local block storage (not NFS/SMB/
FUSE) is a private attestation, not something code can establish.

## 7. Operator procedure for a future approved smoke test (planned)

1. Fresh ephemeral GPU instance per the approved quote; no credentials beyond what the run needs; no CI, Codespaces or shared notebook.
2. Clone `Wan-Video/Wan2.1`, check out `9737cba…`, confirm `git status --porcelain` is empty.
3. Install the frozen environment (torch >= 2.6); compute its digest with `TorchWanRuntime.environment_sha256()` and compare with the approved one.
4. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`; ensure `TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD` is unset; block egress at the provider/network level (the in-process guard does not cover subprocesses).
5. Place the checkpoint obtained under gate 6; the executor re-hashes every file before load.
6. Run the private entry point for the single approved smoke run (`max_attempts: 1`).

**Stop procedure.** The stop signal and the grant's `max_attempt_seconds` are polled before the
reference is opened and **before every denoiser call**. They are **not** polled during model load,
text/CLIP/VAE encoding, VAE decode or video writing; to stop there, terminate the process, then
stop/terminate the instance through the provider, then verify deletion. The billing cap must be
enforced by the provider (budget alert/auto-shutdown), not by this code.

## 8. Provenance and artefacts

Recorded per attempt (private): source commit, checkpoint revision, weight-file manifest digest,
environment digest, `verified_before_load`, controls hash, seed, attempt index, start/end, wall
seconds, `gpu_seconds` (wall-clock duration of the upstream `generate` call, **not** GPU
utilisation), failure category/detail and conditioning metadata.

The adapter reserves `<run>/attempt-NN.mp4` and a hidden partial file next to it through the store
(exclusive create, mode 0600, never overwrites, refuses symlinks and stale partial files) and writes
the partial file via upstream `cache_video` with its stdout discarded. **`generate` only stages the
output.** The executor commits (identity-checked atomic replace plus fsync of file and directory)
only after the conditioning and output checks, a stop/expiry check and a final identical-grant
check; if anything fails after the commit, the inode-checked rollback removes the committed file. A
late rejection therefore leaves no final or partial MP4 (see design §3.3; tested with synthetic
fixtures). Every attempt index is spent once in a keyed ledger whose markers survive deletion and
withdrawal (design §3.4), so deleting files cannot re-enable an old attempt. A killed process
(SIGKILL, instance loss) can leave an empty reservation or a partial file, which then blocks that
attempt index: the gate 3 deletion procedure must cover the store. Whether the real encoder
rewrites the partial under the same inode is unverified; if it does not, commit is refused
(fail-closed) and this is a gate 7 finding. `cache_video` encodes through an `ffmpeg`
subprocess, which the in-process network guard does not cover.

## 9. Smoke-test acceptance (technical only; Experiment 003 §6)

Pass only if all hold: executor provenance equals the pins and locally hashed weights; the attempt
is `succeeded` with conditioning metadata showing the same reference on both routes, both
CFG branches sharing image conditioning and pairs equal to `sampling_steps`; `use_prompt_extend`
off, no remote module imported and zero blocked network attempts; output `(3, frame_count, h, w)`
equal to the expected geometry; artefact only in approved private storage; runtime and the
provider's actual charge recorded; every attempt, including failures, accounted for. A pass
supports **no** claim about identity retention, similarity or protection.

## 10. Remaining unverified, and items surfaced for review

Unverified until an approved run: VRAM and host RAM; load and per-clip runtime; cost; that the
`.pth` files load under weights-only unpickling; real CLIP/VAE execution and the probe's equality
checks on real tensors (including CPU bicubic bit-reproducibility); probe overhead; determinism
across GPUs/drivers; GPU memory release after interruption; `cache_video`/ffmpeg behaviour offline.

For Ada's review (not silently decided):

1. **Precision label** `upstream-i2v-14B-config`: upstream exposes no precision argument, so this is the only value the adapter can honour. Experiment 003 lists precision as pending.
2. **Executor changes** (strengthening only): a backend-raised `ConditioningContractViolation` or `OutputContractViolation` is recorded as that detail instead of `generation_error`; a loaded prompt-extension/remote-service module now overrides any other failure detail.
3. **Source binding** (re-review P1): the executor refuses a backend whose declared `source_dir` is not its own verified checkout, and a *live* backend that declares none. `TorchWanRuntime` independently requires its checkout to be clean at the pinned commit and fails **before any import** if any cached `wan` or `wan.*` module comes from elsewhere; after import it re-checks every `wan.*` module. The check is a path comparison plus a git inspection, not an attestation: the time between inspection and import, and a different checkout mounted at the same path, are not covered. **[CPU-fake]** (synthetic package tree).
4. **Orientation rule**: references must match the `width*height` label; upstream itself ignores the label's orientation.
5. **Process environment** (re-review P1): `TorchWanRuntime` always judges the real `os.environ`; the constructor accepts no mapping. `runtime_environment_problems(mapping)` remains a pure helper for isolated tests only. The in-process network guard is a backstop, not a substitute.
6. **Environment digest** excludes CUDA driver/toolkit and container image digest; these belong in the private record.
7. **Instrumentation effect**: proxies add attribute indirection and device-side equality checks to the run; their effect on timing is unmeasured (they do not change upstream arguments).
8. **3C hardening and its limits** (see design §8): grant authenticity/revocation, the hard time/budget kill, the local-volume attestation and the retained-token decision remain private or human. `max_attempt_seconds` covers model load through commit but not weight hashing; Python cannot interrupt a model load, a denoiser step or ffmpeg. The live runtime refuses to start unless the interpreter is isolated (`-I`) with bytecode disabled, `LD_PRELOAD`, `LD_AUDIT` and `IMAGEIO_FFMPEG_EXE` are unset, and the source and checkpoint trees contain no symlinks, special files or foreign/writable entries. A fresh clone is required because ignored files make the checkout unclean. **[CPU-fake]**

[i2v]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py
[gen]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py
[init]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L34-L131
[sig]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L133-L144
[geo]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L181-L193
[seed]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L199-L201
[neg]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L219-L220
[t5]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L225-L226
[clip]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L236
[vae]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L240-L249
[args]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L284-L296
[calls]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/image2video.py#L302-L319
[img]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L392
[save]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L575-L581
[genpe]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/generate.py#L19
[cfg]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/wan_i2v_14B.py#L13-L23
[cfgs]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/__init__.py#L20-L28
[cfgenv]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/__init__.py#L5
[sizes]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/__init__.py#L30-L36
[shared]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/configs/shared_config.py#L10-L19
[t2vsize]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/text2video.py#L131-L132
[t5load]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/t5.py#L496
[t5cuda]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/t5.py#L478
[vaeload]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/vae.py#L614
[vaedtype]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/vae.py#L624
[clipload]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/clip.py#L519
[tok]: https://github.com/Wan-Video/Wan2.1/blob/9737cba9c1c3c4d04b33fcad41c111989865d315/wan/modules/tokenizers.py#L46
