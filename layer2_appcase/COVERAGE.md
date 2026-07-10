# Layer 2 — what the acceptance-check fraction (k/29) does and does not measure

**The Layer 2 metric is the *TaskFlow API acceptance-check fraction*: the fraction of 29
equally-weighted, automated HTTP assertions (`rubric_tests/contract.py::CANONICAL_CHECKS`) that
pass against the running backend.** It is a pinned request/response contract check — a *necessary*
signal that the API boots and behaves, **not** a measure of full-stack app quality, security, or
UI correctness. This file enumerates exactly what the 29 checks cover, and the required behaviors
they do **not**, so the number is never over-read.

> The weighted **100-point rubric** in `benchmark-spec/evaluation-rubric.md` was a design artifact
> and was never implemented as the scorer. This matrix is the source of truth for L2 coverage.

> ## ⚠️ C1 (RESOLVED by rerun): the frozen contract was not visible to the models
>
> `prompt.md` tells the model to implement the pinned `benchmark-spec/api-contract.md` **exactly**,
> but in the original sweep that file was never present in the app workspace: it was added at
> app-repo tag `baseline-v4`, and **`baseline-v4` is not an ancestor of `baseline-v6`** (the tag
> the runner checked out), so the contract was lost in the lineage split. Four checks that assert
> *unguessable* contract specifics — **`dashboard_summary_keys`, `project_archive`, `project_edit`,
> `task_update_status`** — were structurally unreachable and scored **0 across all 61 original
> runs**. The original k/29 numbers measured "contract inference from prose," not acceptance
> against a *communicated* contract.
>
> **Resolution (2026-07-04): reran L2 with the contract restored.** App-repo tag **`baseline-v7`**
> = `baseline-v6` + `api-contract.md`; the two vLLM models were re-run (node N=20, python N=8).
> `run_rubric.py` now records `contract_present` (and warns when absent). The pre-contract runs are
> archived at `results/_archive_l2_pre_contract_20260703/`; the corrected runs are the primary L2
> result. **The bug had inverted the conclusion:** gpt-oss node went 0.252 → **0.724** (working
> 6/20 → **16/20**; the four dead checks 0 → 48 passes), while qwen barely moved (0.155 → 0.178) —
> so two models that looked *indistinguishable* are in fact clearly separated. Full ablation:
> `results/summary/l2-ablation-contract.csv`, `docs/findings/2026-07-03-l2-rerun-with-contract-decision.md`.
> (nemotron was not rerun — TRT-only and floor-saturated; its rows stay contract-invisible.)
>
> The k/25 "reachable" dual-report (`pass_rate_25` / `rubric_pass_rate_25`,
> `results/summary/l2-rescore-25.csv`) is retained for the archived pre-contract data and as a
> guard; with the contract visible, k/25 ≈ k/29 because the four checks now pass. Original-bug
> write-up: `docs/findings/2026-07-03-l2-contract-invisible.md`.

## The 29 canonical checks

| # | Check | Group | What it asserts |
|---|-------|-------|-----------------|
| 1 | `health_ok` | boot | `GET /api/health` → `{"status":"ok"}` |
| 2 | `login_admin_ok` | auth | admin login returns a token with `role=admin` |
| 3 | `user_no_password_field` | security | login-response user object has no `password`/`passwordHash` **key** |
| 4 | `login_bad_creds_401` | auth | wrong password → 401 |
| 5 | `me_without_token_401` | auth | `/auth/me` without token → 401 |
| 6 | `me_with_token_200` | auth | `/auth/me` with token → 200 |
| 7 | `login_member_ok` | auth | member login succeeds |
| 8 | `member_create_project_403` | rbac | member creating a project → 403 |
| 9 | `admin_create_project` | projects | admin create project → 200/201 |
| 10 | `project_list_contains` | projects | created project appears in list |
| 11 | `project_get_by_id` | projects | project fetch by id |
| 12 | `project_edit` | projects | project edit persists |
| 13 | `project_archive` | projects | project archive |
| 14 | `validation_project_no_name_400` | validation | project without name → 400 |
| 15 | `task_create` | tasks | task create → 200/201 |
| 16 | `task_list` | tasks | task list |
| 17 | `task_get` | tasks | task fetch by id |
| 18 | `task_update_status` | tasks | `PATCH /tasks/{id}/status` |
| 19 | `task_filter_status` | tasks | filter tasks by **status** |
| 20 | `task_search` | tasks | text search (`q`) |
| 21 | `comment_add` | comments | add comment → 200/201 |
| 22 | `comment_list` | comments | list comments |
| 23 | `task_delete` | tasks | delete task → 200/204 |
| 24 | `validation_task_no_title_400` | validation | task without title → 400 |
| 25 | `validation_task_bad_priority_400` | validation | task with bad priority → 400 |
| 26 | `dashboard_summary_keys` | dashboard | dashboard response contains the expected **keys** |
| 27 | `protected_route_no_token_401` | security | a protected route without token → 401 |
| 28 | `frontend_build` | frontend | `npm run build` succeeds |
| 29 | `lockfile_present` | reproducibility | a dependency lockfile was emitted |

Group totals: auth 5, tasks 7, projects 5, validation 3, security 2, comments 2, boot/rbac/dashboard/frontend/reproducibility 1 each = **29**, each weight 1/29.

## Requirement → coverage matrix

| Required behavior (spec/contract) | Coverage | Notes |
|---|---|---|
| API boots; health endpoint | ✅ full | check 1 |
| Auth: login, bad-creds, token-gated `/me` | ✅ full | checks 2,4,5,6,7 |
| Project CRUD (admin) | ✅ full | checks 9–13 |
| Task create/list/get/delete | ✅ full | checks 15,16,17,23 |
| Input validation (missing name/title, bad priority) | ✅ full | checks 14,24,25 |
| Comments add/list | 🟡 partial | presence only; no authorization on who may comment |
| Password **not leaked** in API response | ✅ full | check 3 (key-absence only) |
| Passwords **hashed at rest** | ❌ none | never inspects storage or hash algorithm — only response key absence |
| RBAC / role enforcement | 🟡 partial | only member→project-create 403 (check 8); **assigned-vs-unassigned task/comment update rights not tested** |
| Task filtering | 🟡 partial | **status only** (check 19); contract also requires `priority`, `assigneeId`, `projectId` filters — **untested** |
| Task search | ✅ full | check 20 (text `q`) |
| Task edit (title/priority/description/assignee/due-date) | 🟡 partial | **status PATCH only** (check 18); general task edit untested |
| Due-date validation | ❌ none | not tested |
| Dashboard summary | 🟡 partial | **key presence only** (check 26); values not checked for correctness |
| Persistence across restart | ❌ none | backend is started once; no restart/reload test |
| Logout / protected **frontend** routing | ❌ none | `POST /auth/logout` and gated UI routes untested |
| Frontend renders / pages work | ❌ none | only `npm run build` succeeds (check 28); no rendering, routing, or interaction |
| App's own test suite | ❌ excluded | `test_cmd` **runs** and is recorded in `result["tests"]` but is **not** part of k/29 |
| Code quality / maintainability | ❌ none | not scored (was in the unimplemented 100-pt rubric) |
| Documentation | ❌ none | not scored |
| Agent efficiency | ❌ none | not scored (captured separately as metrics, not in k/29) |

## Caveats that bound interpretation

- **Checks are stateful and dependent, not 29 independent requirements.** They run in sequence
  against shared state (login → create project → create task → …). An early failure (e.g. login)
  cascades into many downstream failures, so k/29 is not a count of 29 orthogonal capabilities.
- **Tolerant status codes.** Create endpoints accept `200` *or* `201`; delete accepts `200` *or*
  `204`. This is deliberate leniency against an "exact" contract — document, don't over-read.
- **Presence ≠ correctness.** `dashboard_summary_keys` and several status-only assertions can pass
  for a semantically wrong implementation (right keys/status, wrong values).
- **"Working app" = pass-rate ≥ 0.5 is an arbitrary, unvalidated cutoff.** A score above 0.5 does
  not imply a usable UI, a secure app, or a complete app. Report the full pass-rate distribution,
  not just the working-app rate. The cutoff is applied to both denominators (k/29 and k/25); the
  working-app counts come out identical, so the Bernoulli story is robust to the C1 rescore.
- **Four checks were unreachable (C1, above).** The fair denominator is the 25 reachable checks
  (`rubric_pass_rate_25`); the k/29 rate understates every model by four dead checks.
