# Harness issues found during the N=1 validation runs — and their fixes

**Date:** 2026-06-25
**Purpose:** One consolidated log of every harness/infra bug hit while bringing the Layer-2 sweep
up on real models, so the whole debugging story is readable in one place. The two deep-dive
findings (the rubric confound and the nemotron incompatibility) have their own docs; this file
links to them and covers everything else, plus the concurrency bug that kept biting us.

Branch: `feat/benchmark-harness`. Relevant commits: `5196928`, `3ad917c`, and the concurrency-lock
commit that accompanies this doc.

---

## 1. Concurrent sweeps corrupt each other (the recurring one)

**Symptom.** Twice, two `run-benchmark.sh` sweeps ended up running at once (once via an accidental
`source run-benchmark.sh`; once because a background sweep and a hand-started sweep overlapped).
Signature: a node-track build and a python-track build running *simultaneously* (a single sweep
runs tracks sequentially), two `logs/run-benchmark-*.log` files, and taskflow left on a run branch
with a dirty tree.

**Root cause.** Both sweeps share two singletons: the vLLM server on `:8000` and the **one**
taskflow git repo. Each run does `git checkout baseline-v6 && git checkout -B <run-id>` on that
single repo, so when two runs interleave, the repo's HEAD flips between branches *while an
opencode agent is mid-write*. The builds' files and commits cross-contaminate. Nothing prevented a
second sweep from starting.

**Fix.** `run-benchmark.sh` now takes an exclusive `flock` on `.run-benchmark.lock` for the whole
sweep. A second invocation fails fast with a clear message instead of silently producing garbage.
Verified: second concurrent attempt is rejected. Lockfile is gitignored.

**Operational rule going forward:** exactly one owner launches the sweep. Don't run
`./run-benchmark.sh` by hand while a background one is going (the lock now enforces this, but the
habit matters). Recovery if it happens again: kill both trees (`pkill -9 -f run-benchmark.sh;
pkill -9 -f run-appcase.sh; pkill -9 -f "opencode run"`), `rm` the lock, reset taskflow
(`git checkout baseline-v6`, delete `*-l2-*` branches, `git clean -fdx apps/`), delete partial
`results/raw/*` dirs that lack `rubric-score.json`, then start ONE sweep.

## 2. nemotron/qwen silently skipped — docker-group detection (commit `5196928`)

**Symptom.** First multi-model sweep ran only gpt-oss; nemotron and qwen were skipped instantly
with "docker not usable and you're not in the docker group."

**Root cause.** `in_docker_group()` used `id -nG`, which lists only the *active* session's groups.
The user is a docker member in `/etc/group` but the group isn't active in the shell — which is
exactly when the `sg docker` fallback is needed and works.

**Fix.** `in_docker_group()` now also reads `/etc/group` via `getent group docker`, so the
`sg docker` serve path fires correctly.

## 3. Missing `run-summary.json` — invalid `window.json` (commit `5196928`)

**Symptom.** gpt-oss runs produced no `run-summary.json`; `aggregate.py` failed with
"Invalid control character at line 7 …".

**Root cause.** `run-context.sh` wrote the build command into `window.json` by escaping quotes
only. The Layer-2 build prompt is multi-line, and raw newlines inside a JSON string are invalid →
`aggregate.py` couldn't parse it and skipped the summary. A one-line smoke test had hidden this.

**Fix.** `run-context.sh` JSON-encodes the command with `python3 json.dumps` (emits a valid quoted
string). Salvaged the already-captured gpt-oss runs by repairing their `window.json` and
re-aggregating rather than rebuilding.

## 4. serve-model.sh never wrote the serve manifest (earlier, pre-`5196928`)

**Symptom.** After a successful sanity gate, `serve-model.sh` exited 0 but the serve manifest
(model identity, expert counts, power level) was never written.

**Root cause.** Two `set -e` traps in the best-effort manifest tail: (a) a bare
`[[ cond ]] && cmd` returns 1 when the condition is false, aborting under `set -e`; (b) early-exit
pipelines like `nvidia-smi -q | awk '/CUDA Version/{print;exit}'` raise SIGPIPE (exit 141).

**Fix.** Converted the bare `[[ ]] &&` to a full `if`, and wrapped the manifest tail in
`set +e +o pipefail` since it's best-effort.

## 5. serve-model.sh polled a dead container for 15 min (commit `3ad917c`)

**Symptom.** nemotron "NOT ready after timeout" — but the container had actually crashed in ~6s;
the script waited the full 15-minute readiness window anyway, and the next model's serve
`docker rm -f`'d the container before anyone could read its logs (this is why nemotron's real
error stayed hidden for two runs).

**Fix.** The readiness loop now checks `docker inspect -f '{{.State.Running}}'` each iteration; if
the container has exited, it dumps the last 25 log lines and returns immediately. This is how
nemotron's real error (issue #8 below) was finally captured.

## 6. Rubric measured lockfile-emission, not code — `npm ci` confound (commit `3ad917c`)

**Symptom.** qwen scored 0.0 on both tracks while gpt-oss scored 0.64.

**Root cause + fix:** full write-up in
[`2026-06-25-rubric-npm-ci-confound.md`](./2026-06-25-rubric-npm-ci-confound.md). In short:
`npm ci` hard-fails without a committed lockfile, which qwen didn't emit; switched to
`(npm ci || npm install)`, added `lockfile_present` as a 1-point check, and pinned a fixed
29-check denominator so dead-backend runs (k/29) compare to live ones. Validation showed qwen's
app fails for *genuine* defects, so the gap is real code quality.

### 6a. Sub-bug: `lockfile_present` self-pollution
First cut checked the working tree *after* the rubric's own `npm install` had generated a
`package-lock.json` → always true. Fixed by capturing lockfile presence **before** any install.

## 7. Every python backend scored 0 — PEP 668 + pinned entrypoint path (commit `0626c99`)

**Symptom.** In the corrected sweep, all python-track backends failed to boot for BOTH models
(gpt-oss python 0.03, qwen python 0.0) while node worked — suspicious, since gpt-oss scored 0.69
on node.

**Root cause (two layered issues).**
1. The rubric's python `backend_start` ran a bare `pip install -r requirements.txt`. On the
   Debian/Ubuntu Spark host the system Python is **externally-managed (PEP 668)**, so pip refuses:
   `error: externally-managed-environment`. The `&&` short-circuits → uvicorn never starts → every
   python backend scores 0 regardless of code quality (identical failure for both models = the
   tell-tale sign of a harness issue, not a model one).
2. The start command pinned `uvicorn app.main:app`, but a correct FastAPI app may expose `app` at
   `main:app` or `app:app`. gpt-oss put its app in `main.py` → `app.main:app` would fail to import
   even after the pip fix. Zeroing a working app over module nesting is the same anti-pattern as
   the npm-ci/lockfile confound (issue #6).

**Fix.** New `layer2_appcase/rubric_tests/start-python-backend.sh`: create a **per-run venv**
(what a real deployment does), install requirements into it, **probe the standard entrypoints**
(`app.main:app` → `main:app` → `app:app`, first one exposing `app` wins), then exec uvicorn.
Bumped `--boot-timeout` 120→300s (venv + pip install can exceed 120s). `test_cmd` runs in the same
venv.

**Validation.** Against gpt-oss's python app the backend now boots (probe resolved `main:app`,
`Application startup complete`, health 200). Its score stays low — but now *legitimately*: the API
deviates from the contract (`POST /api/auth/login` → 422, `/api/auth/me` → 404, `/api/projects`
returns 200 without a token). So gpt-oss is genuinely strong on node (0.69) and weak on python
(~0.07) — a real signal, no longer a harness artifact. python build/energy metrics from the sweep
were valid (the build ran fine; only scoring was broken), so the runs were **re-scored** in place
rather than rebuilt.

qwen's python app also fails genuinely (0/29): its `main.py` uses **relative imports**
(`from .database import …`), which require a package context. It is not under an `app/` package (so
the pinned `app.main:app` fails) and the relative imports break direct `main:app` execution
(`ImportError: attempted relative import with no known parent package`). So it can't be started by
the pinned command or any standard entrypoint — a real spec-compliance failure, matching its broken
node app (`sqlite` vs `sqlite3`, missing page). The probe intentionally covers the three standard
layouts the contract implies; auto-discovering an arbitrary package root + relative-import context
to rescue one model's non-compliant layout would be over-fitting, so it's left as a genuine fail.

## 8. nemotron-super not servable on vLLM — MIXED_PRECISION checkpoint

**Symptom + root cause + decision:** full write-up in
[`2026-06-25-nemotron-super-vllm-mixed-precision.md`](./2026-06-25-nemotron-super-vllm-mixed-precision.md).
In short: the checkpoint declares `quant_algo=MIXED_PRECISION` (FP8 Mamba + NVFP4 MoE, per-layer);
vLLM 0.15.1 only accepts a single uniform algo and rejects it at config validation. Known upstream
(vllm#37854, NVIDIA/dgx-spark-playbooks#77). Removed from the vLLM comparison; TensorRT-LLM is the
path to add it back. Weights are fully downloaded and finalized (17 shards).

## 9. N=3 sweep half-failed — `git checkout` aborts on a dirty taskflow tree (commit `<this>`)

**Symptom.** The N=3 sweep scored only 6/12. Every run after the first model's node tracks died with
`error: Your local changes to the following files would be overwritten by checkout:
apps/node-track/frontend/package-lock.json … Aborting` → `[appcase] git checkout failed`.

**Root cause.** `run-appcase.sh` did `git checkout baseline-v6 && git checkout -B <run-id>` without
scrubbing the working tree first. The rubric's `(npm ci || npm install)` regenerates a
**tracked** `package-lock.json` (and untracked `node_modules`, `.venv`, `*.db`) *after* the
per-run commit, leaving the tree dirty. The next run's `git checkout` then refuses to overwrite the
modified tracked file and aborts — and since the tree stays dirty, it cascades to every subsequent
run. (N=1 didn't hit it because manual cleans happened to reset the tree between runs.)

**Fix.** `run-appcase.sh` now scrubs before checkout: `git reset --hard && git clean -fdx` →
`git checkout baseline-v6` → `git checkout -B <run-id>`. Discards tracked changes and removes build
artifacts so checkout can never abort. (Per-run model builds remain safe — they're committed on
their own `<run-id>` branches before the rubric runs.)

## 10. gpt-oss skipped in N=3 — serve readiness timeout too short for a cold load (commit `<this>`)

**Symptom.** In N=3, gpt-oss "NOT ready after timeout" → the whole model was skipped; only qwen ran.
No "container exited" message, so it was **not** a crash — the container was alive but not ready.

**Root cause.** The readiness window was 180×5s = 15 min. In N=1 gpt-oss was already warm (served,
skipped), so a real cold load was never timed. In N=3 gpt-oss had to load ~61GB MXFP4 from cold
page cache right after qwen was swapped out, and 15 min was too tight.

**Fix.** Raised the readiness ceiling to 360×5s = 30 min. A warm/healthy model still answers in
seconds; only a genuinely slow cold load uses the extra headroom. (The fail-fast on container
*exit* from issue #5 still short-circuits real crashes immediately, so a bad model never waits the
full 30 min.)

---

## Net state after all fixes

- The vLLM head-to-head is **gpt-oss-120b vs qwen3-coder-30b**, scored on a fixed 29-check rubric
  with a fair install path.
- Two models are documented deployment-reality findings rather than data points: DeepSeek
  (won't drive the agent loop) and nemotron (not vLLM-servable).
- The sweep is concurrency-safe, fails fast on a crashed serve, captures valid metrics JSON, serves
  via the `sg docker` fallback, and writes its serve manifest.
- All old run data scored under the buggy rubric is archived under
  `results/_archive_old_rubric_20260625/`; collision logs under `logs/_collision_20260625/`.
