# Methodology fix: the `npm ci` lockfile confound and the fixed-denominator rubric

**Date:** 2026-06-25
**Status:** Fixed in `layer2_appcase/rubric_tests/{contract.py,run_rubric.py}`. All Layer-2 runs are re-scored under the corrected rubric.
**Why this matters:** left unfixed, the headline model gap in the paper would have been an artifact of build tooling, not coding ability — exactly the kind of confound a reviewer flags.

## Symptom

In the first multi-model sweep, **qwen3-coder-30b scored 0.0 on both tracks** while **gpt-oss-120b scored 0.64 (node)**. Taken at face value, that's a huge capability gap. It is not real.

## Root cause #1 — `npm ci` hard-requires a committed lockfile

The rubric started the backend and built the frontend with `npm ci && npm run start` / `npm ci && npm run build`. **`npm ci` aborts immediately if there is no `package-lock.json`:**

```
npm error code EUSAGE
npm error The `npm ci` command can only install with an existing package-lock.json ...
```

Inspecting the two app branches:

| Model | Wrote a working app? | Committed `package-lock.json`? | `npm ci` result | Score |
|---|---|---|---|---|
| gpt-oss-120b | yes | **yes** (backend + frontend) | installs | 0.64 |
| qwen3-coder-30b | **yes** — Express backend on :4000 with `/api/health`, 12 backend + 13 frontend files, all routes | **no** | aborts → backend never boots | 0.0 |

qwen wrote a correct application. It just didn't run `npm install` to emit a lockfile. With `npm ci`, that single omission cascaded: backend never started → every API check failed → 0.0. **The benchmark was partly measuring "did the model emit a lockfile," not "can the model write a working app."** That's a confound.

## Root cause #2 — collapsing denominator

When the backend failed to boot, the rubric short-circuited after `health_ok` and recorded **only 2 checks** (`health_ok`, `frontend_build`). A run where the backend *did* boot recorded **28**. So a dead-backend run was scored out of 2 and a live one out of 28 — the `pass_rate` values weren't on the same scale and couldn't be compared across runs or models.

## The fix

### 1. Install with a fallback, not a hard gate
`contract.py` now uses `(npm ci || npm install) && ...` for every npm step (both tracks; the python track's frontend build too). When the model committed a lockfile, the reproducible `npm ci` still runs; when it didn't, `npm install` resolves and installs anyway. **The code is what gets evaluated**, not the presence of a lockfile.

### 2. Keep the reproducibility signal — but as one point, not a cliff
Emitting a committed lockfile is still a real engineering signal, so it is captured as its own graded check, `lockfile_present` (group `reproducibility`): true only if every npm package dir in the track committed a `package-lock.json`. A model that skips it loses **1 point out of 29**, not the entire run.

### 3. Fixed canonical denominator
`contract.CANONICAL_CHECKS` pins the full 29-check list. `run_rubric.py` reconciles each run's emitted checks against it: any check not reached (e.g. all the API probes when the backend never boots) is recorded as `failed / "not reached"`. **Every run is now scored out of the same 29**, so a dead-backend run scores `k/29` and is directly comparable to a fully-working `28/29`.

The 29 checks: `health_ok`; auth (`login_admin_ok`, `login_bad_creds_401`, `me_without_token_401`, `me_with_token_200`, `login_member_ok`); `user_no_password_field`; `member_create_project_403`; projects (`admin_create_project`, `project_list_contains`, `project_get_by_id`, `project_edit`, `project_archive`); tasks/comments (`task_create`, `task_list`, `task_get`, `task_update_status`, `task_filter_status`, `task_search`, `comment_add`, `comment_list`, `task_delete`); validation (`validation_project_no_name_400`, `validation_task_no_title_400`, `validation_task_bad_priority_400`); `dashboard_summary_keys`; `protected_route_no_token_401`; `frontend_build`; `lockfile_present`.

## Why this is the right call (and what was rejected)

- **Rejected: keep `npm ci` as a hard reproducibility gate.** Defensible in principle, but it conflates "wrote working code" with "remembered to commit a lockfile," and a single missing file zeroing an otherwise-correct app overstates capability gaps. Reproducibility deserves *a* point, not veto power.
- **Rejected: `npm install` only, drop the lockfile signal.** Simpler, but throws away a genuine reproducibility signal we can capture for free.
- **Chosen: fallback install + `lockfile_present` as 1/29 + fixed denominator.** Measures the code, still rewards reproducibility proportionally, and makes every run comparable.

## Disclosure for the paper

State plainly: installs use `npm ci` when a lockfile is committed and fall back to `npm install` otherwise; lockfile emission is scored as one reproducibility point; all runs are scored against an identical 29-item checklist with unreached checks counted as failures. Report `lockfile_present` per model — it's a real, interesting difference (gpt-oss emitted lockfiles; qwen did not) that now informs the score by ~3% instead of dominating it.

## Validation — the fix didn't flip the result, it *validated* it

The corrected rubric was re-run against qwen's *original* node branch (the one that scored 0.0). The `npm install` fallback now installs successfully — and the app **still fails**, but for its own genuine reasons, not the lockfile:

- **Backend crashes on boot:** `ERR_MODULE_NOT_FOUND: Cannot find package 'sqlite'` — qwen's `database.js` imports `sqlite`, but `package.json` declares `sqlite3` (a different package). An undeclared/mismatched dependency.
- **Frontend build fails:** `RollupError: Could not resolve "./pages/ProjectDetailPage" from src/App.jsx` — qwen's `App.jsx` imports a page component file it never created.

Result under the corrected rubric: **qwen node = 1/29 → 0/29** once the `lockfile_present` self-pollution bug was fixed (see below). gpt-oss node = 0.64 (app boots, most API checks pass). **So the gap is real and about code quality**, not lockfile emission. Before the fix we could not have told these apart — `npm ci` would have zeroed qwen regardless of whether its code worked. Now the score reflects the actual defects.

### Sub-bug found and fixed during validation
The first cut of `lockfile_present` checked the working tree *after* the rubric's own `npm install` had run — which generates a `package-lock.json` — so it always reported `True`. Fixed by capturing lockfile presence **before** any install runs (the working tree at that point is exactly what the model committed, since `run-appcase.sh` commits before invoking the rubric). Verified: clean qwen branch → `lockfile_present = False` (0/2 npm dirs).
