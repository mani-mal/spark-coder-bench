"""Pinned contract constants shared by the rubric runner. Mirrors api-contract.md."""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

BASE_URL = "http://127.0.0.1:4000"
API = "/api"

SEED = {
    "admin": {"email": "admin@example.com", "password": "Admin123!", "role": "admin"},
    "member": {"email": "member@example.com", "password": "Member123!", "role": "member"},
}

TASK_STATUSES = ["backlog", "in_progress", "blocked", "done"]
TASK_PRIORITIES = ["low", "medium", "high"]

DASHBOARD_KEYS = [
    "totalProjects", "totalTasks", "tasksByStatus",
    "highPriorityOpen", "myTasks", "overdue",
]

# Per-track process commands (relative to the app track dir).
#
# Install uses `npm ci || npm install`, NOT bare `npm ci`. `npm ci` hard-requires a committed
# package-lock.json; a model that writes a correct app but doesn't emit a lockfile would otherwise
# fail to install and score 0 — measuring lockfile-emission, not coding skill (see
# docs/findings/2026-06-25-rubric-npm-ci-confound.md). The fallback runs the reproducible `npm ci`
# when a lockfile is present and `npm install` otherwise, so the *code* is what's evaluated.
# Lockfile presence is still captured as its own graded check (`lockfile_present`) in run_rubric.py.
TRACKS = {
    "node": {
        "backend_dir": "backend",
        "frontend_dir": "frontend",
        "backend_start": "(npm ci || npm install) && npm run start",
        "frontend_build": "(npm ci || npm install) && npm run build",
        "test_cmd": "npm test",
    },
    "python": {
        "backend_dir": "backend",
        "frontend_dir": "frontend",
        # Per-run venv (PEP 668) + entrypoint probing — see start-python-backend.sh for the why.
        "backend_start": f"bash {_HERE}/start-python-backend.sh",
        "frontend_build": "(npm ci || npm install) && npm run build",
        # tests run in the same venv the backend used (falls back to system pytest if absent).
        "test_cmd": "{ [ -x .venv/bin/python ] && .venv/bin/python -m pytest -q; } || pytest -q",
    },
}

# Canonical, fixed rubric checklist. Every run is scored against EXACTLY this set so the
# denominator is identical across models and runs (a backend that never boots scores its API
# checks as failed, not as "absent" — otherwise a dead backend is scored out of 2 while a live
# one is scored out of 28, and the pass-rates aren't comparable). run_rubric.py reconciles its
# emitted checks against this list and fills any that weren't reached as failed.
# Order/grouping mirrors the HTTP probes in run_rubric.py, plus frontend_build and lockfile_present.
CANONICAL_CHECKS = [
    ("health_ok", "boot"),
    ("login_admin_ok", "auth"),
    ("user_no_password_field", "security"),
    ("login_bad_creds_401", "auth"),
    ("me_without_token_401", "auth"),
    ("me_with_token_200", "auth"),
    ("login_member_ok", "auth"),
    ("member_create_project_403", "rbac"),
    ("admin_create_project", "projects"),
    ("project_list_contains", "projects"),
    ("project_get_by_id", "projects"),
    ("project_edit", "projects"),
    ("project_archive", "projects"),
    ("validation_project_no_name_400", "validation"),
    ("task_create", "tasks"),
    ("task_list", "tasks"),
    ("task_get", "tasks"),
    ("task_update_status", "tasks"),
    ("task_filter_status", "tasks"),
    ("task_search", "tasks"),
    ("comment_add", "comments"),
    ("comment_list", "comments"),
    ("task_delete", "tasks"),
    ("validation_task_no_title_400", "validation"),
    ("validation_task_bad_priority_400", "validation"),
    ("dashboard_summary_keys", "dashboard"),
    ("protected_route_no_token_401", "security"),
    ("frontend_build", "frontend"),
    ("lockfile_present", "reproducibility"),
]

# C1: these four checks assert exact api-contract.md specifics (routes/keys the requirements
# prose does not pin down — e.g. PATCH /tasks/{id}/status, the dashboard summary key set,
# project edit/archive semantics). They are only reachable if the frozen api-contract.md is in
# the model's workspace. It was NOT (baseline-v4 added it but is not an ancestor of the
# baseline-v6 the runs start from), so these scored 0 across every run. The k/25 "reachable"
# rate excludes them; run_rubric.py dual-reports pass_rate (k/29) and pass_rate_25 (k/25).
UNREACHABLE_WITHOUT_CONTRACT = {
    "dashboard_summary_keys", "project_archive", "project_edit", "task_update_status",
}
