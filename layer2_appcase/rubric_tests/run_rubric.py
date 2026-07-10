#!/usr/bin/env python3
"""run_rubric.py — automated acceptance rubric for the Layer 2 TaskFlow Local app.

Scores a built app against the PINNED api-contract.md. Score = checklist pass-rate,
run identically for both models. Optionally starts the backend / builds the frontend
first; otherwise tests an already-running backend.

Writes rubric-score.json:
  {track, pass_rate, passed, total, checks:[{name,group,passed,detail}], build, tests}

Usage:
  # against an already-running backend:
  run_rubric.py --track node --base-url http://127.0.0.1:4000 --out results/raw/<run-id>

  # start + build + score + teardown (app lives under <app-dir>):
  run_rubric.py --track node --app-dir ~/projects/taskflow-local-app-benchmark/apps/node-track \
                --start --build --out results/raw/<run-id>
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract as C  # noqa: E402
import re  # noqa: E402


def port_of(url):
    m = re.search(r"://[^/:]+:(\d+)", url)
    return int(m.group(1)) if m else 80


def port_busy(base_url):
    try:
        return requests.get(base_url.rstrip("/") + C.API + "/health", timeout=2).status_code == 200
    except Exception:
        return False


def free_port(port):
    # Best-effort kill of whatever is listening on the port (M4). fuser is present on this box;
    # the lsof form is a fallback. Both are no-ops if nothing is listening.
    for cmd in ([f"fuser -k {port}/tcp"], [f"lsof -ti tcp:{port} | xargs -r kill -9"]):
        try:
            subprocess.run(["bash", "-lc", cmd[0]], capture_output=True, timeout=10)
        except Exception:
            pass


class Rubric:
    def __init__(self, base_url):
        self.base = base_url.rstrip("/")
        self.checks = []
        self.state = {}

    def add(self, name, group, passed, detail=""):
        self.checks.append({"name": name, "group": group, "passed": bool(passed), "detail": str(detail)[:300]})
        return passed

    def req(self, method, path, token=None, **kw):
        headers = kw.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            r = requests.request(method, self.base + path, headers=headers, timeout=10, **kw)
            return r, None
        except Exception as e:
            return None, str(e)

    # ---- check groups ----
    def boot(self):
        r, err = self.req("GET", C.API + "/health")
        ok = bool(r is not None and r.status_code == 200)
        try:
            ok = ok and r.json().get("status") == "ok"
        except Exception:
            ok = False
        self.add("health_ok", "boot", ok, err or (r.status_code if r else "no response"))

    def auth(self):
        a = C.SEED["admin"]
        r, err = self.req("POST", C.API + "/auth/login", json={"email": a["email"], "password": a["password"]})
        token = None
        if r is not None and r.status_code == 200:
            try:
                body = r.json()
                token = body.get("token")
                user = body.get("user", {})
                self.add("login_admin_ok", "auth", bool(token) and user.get("role") == "admin", body)
                self.add("user_no_password_field", "security",
                         not any(k.lower() in ("password", "passwordhash") for k in user), list(user.keys()))
            except Exception as e:
                self.add("login_admin_ok", "auth", False, e)
                self.add("user_no_password_field", "security", False, "unparseable")
        else:
            self.add("login_admin_ok", "auth", False, err or (r.status_code if r else "no response"))
            self.add("user_no_password_field", "security", False, "no login")
        self.state["admin_token"] = token

        rb, _ = self.req("POST", C.API + "/auth/login", json={"email": a["email"], "password": "wrong-pw"})
        self.add("login_bad_creds_401", "auth", rb is not None and rb.status_code == 401, rb.status_code if rb else "none")

        rn, _ = self.req("GET", C.API + "/auth/me")
        self.add("me_without_token_401", "auth", rn is not None and rn.status_code == 401, rn.status_code if rn else "none")
        if token:
            rm, _ = self.req("GET", C.API + "/auth/me", token=token)
            self.add("me_with_token_200", "auth", rm is not None and rm.status_code == 200, rm.status_code if rm else "none")

        m = C.SEED["member"]
        rmem, _ = self.req("POST", C.API + "/auth/login", json={"email": m["email"], "password": m["password"]})
        mt = None
        if rmem is not None and rmem.status_code == 200:
            try:
                mt = rmem.json().get("token")
            except Exception:
                pass
        self.state["member_token"] = mt
        self.add("login_member_ok", "auth", bool(mt), rmem.status_code if rmem else "none")

    def rbac_and_projects(self):
        at = self.state.get("admin_token")
        mt = self.state.get("member_token")
        # member forbidden
        if mt:
            r, _ = self.req("POST", C.API + "/projects", token=mt, json={"name": "X"})
            self.add("member_create_project_403", "rbac", r is not None and r.status_code == 403, r.status_code if r else "none")
        else:
            self.add("member_create_project_403", "rbac", False, "no member token")
        # admin create
        pid = None
        if at:
            r, _ = self.req("POST", C.API + "/projects", token=at, json={"name": "Benchmark Project", "description": "d"})
            ok = r is not None and r.status_code in (200, 201)
            if ok:
                try:
                    pid = r.json().get("id")
                except Exception:
                    ok = False
            self.add("admin_create_project", "projects", ok and pid is not None, r.status_code if r else "none")
        else:
            self.add("admin_create_project", "projects", False, "no admin token")
        self.state["project_id"] = pid

        if at and pid is not None:
            r, _ = self.req("GET", C.API + "/projects", token=at)
            found = False
            try:
                found = any(str(p.get("id")) == str(pid) for p in r.json())
            except Exception:
                pass
            self.add("project_list_contains", "projects", found, r.status_code if r else "none")

            r, _ = self.req("GET", C.API + f"/projects/{pid}", token=at)
            self.add("project_get_by_id", "projects", r is not None and r.status_code == 200, r.status_code if r else "none")

            r, _ = self.req("PATCH", C.API + f"/projects/{pid}", token=at, json={"description": "edited"})
            self.add("project_edit", "projects", r is not None and r.status_code == 200, r.status_code if r else "none")

            r, _ = self.req("POST", C.API + f"/projects/{pid}/archive", token=at)
            ok = r is not None and r.status_code == 200
            try:
                ok = ok and r.json().get("status") == "archived"
            except Exception:
                ok = False
            self.add("project_archive", "projects", ok, r.status_code if r else "none")
        # validation
        if at:
            r, _ = self.req("POST", C.API + "/projects", token=at, json={"description": "no name"})
            self.add("validation_project_no_name_400", "validation", r is not None and r.status_code == 400, r.status_code if r else "none")

    def tasks_and_comments(self):
        at = self.state.get("admin_token")
        pid = self.state.get("project_id")
        if not at:
            for n in ("task_create", "task_list", "task_get", "task_update_status",
                      "task_filter_status", "task_search", "task_delete",
                      "comment_add", "comment_list"):
                self.add(n, "tasks", False, "no admin token")
            return
        # create
        tid = None
        payload = {"projectId": pid, "title": "Benchmark Task ZZZ", "priority": "high", "status": "backlog"}
        r, _ = self.req("POST", C.API + "/tasks", token=at, json=payload)
        ok = r is not None and r.status_code in (200, 201)
        if ok:
            try:
                tid = r.json().get("id")
            except Exception:
                ok = False
        self.add("task_create", "tasks", ok and tid is not None, r.status_code if r else "none")
        self.state["task_id"] = tid

        r, _ = self.req("GET", C.API + "/tasks", token=at)
        self.add("task_list", "tasks", r is not None and r.status_code == 200, r.status_code if r else "none")

        if tid is not None:
            r, _ = self.req("GET", C.API + f"/tasks/{tid}", token=at)
            self.add("task_get", "tasks", r is not None and r.status_code == 200, r.status_code if r else "none")

            r, _ = self.req("PATCH", C.API + f"/tasks/{tid}/status", token=at, json={"status": "in_progress"})
            ok = r is not None and r.status_code == 200
            try:
                ok = ok and r.json().get("status") == "in_progress"
            except Exception:
                ok = False
            self.add("task_update_status", "tasks", ok, r.status_code if r else "none")

            r, _ = self.req("GET", C.API + "/tasks", token=at, params={"status": "in_progress"})
            found = False
            try:
                found = any(str(t.get("id")) == str(tid) for t in r.json())
            except Exception:
                pass
            self.add("task_filter_status", "tasks", found, r.status_code if r else "none")

            r, _ = self.req("GET", C.API + "/tasks", token=at, params={"q": "ZZZ"})
            found = False
            try:
                found = any(str(t.get("id")) == str(tid) for t in r.json())
            except Exception:
                pass
            self.add("task_search", "tasks", found, r.status_code if r else "none")

            # comments
            r, _ = self.req("POST", C.API + f"/tasks/{tid}/comments", token=at, json={"body": "looks good"})
            self.add("comment_add", "comments", r is not None and r.status_code in (200, 201), r.status_code if r else "none")
            r, _ = self.req("GET", C.API + f"/tasks/{tid}/comments", token=at)
            ok = r is not None and r.status_code == 200
            try:
                arr = r.json()
                ok = ok and len(arr) >= 1 and ("createdAt" in arr[0])
            except Exception:
                ok = False
            self.add("comment_list", "comments", ok, r.status_code if r else "none")

            r, _ = self.req("DELETE", C.API + f"/tasks/{tid}", token=at)
            self.add("task_delete", "tasks", r is not None and r.status_code in (200, 204), r.status_code if r else "none")
        # validation
        r, _ = self.req("POST", C.API + "/tasks", token=at, json={"projectId": pid, "priority": "high"})
        self.add("validation_task_no_title_400", "validation", r is not None and r.status_code == 400, r.status_code if r else "none")
        r, _ = self.req("POST", C.API + "/tasks", token=at, json={"projectId": pid, "title": "t", "priority": "URGENT"})
        self.add("validation_task_bad_priority_400", "validation", r is not None and r.status_code == 400, r.status_code if r else "none")

    def dashboard_and_security(self):
        at = self.state.get("admin_token")
        if at:
            r, _ = self.req("GET", C.API + "/dashboard/summary", token=at)
            ok = r is not None and r.status_code == 200
            try:
                body = r.json()
                missing = [k for k in C.DASHBOARD_KEYS if k not in body]
                ok = ok and not missing
            except Exception:
                ok = False
                missing = C.DASHBOARD_KEYS
            self.add("dashboard_summary_keys", "dashboard", ok, f"missing={missing}" if not ok else "ok")
        else:
            self.add("dashboard_summary_keys", "dashboard", False, "no admin token")
        r, _ = self.req("GET", C.API + "/projects")  # no token
        self.add("protected_route_no_token_401", "security", r is not None and r.status_code == 401, r.status_code if r else "none")

    def run_http(self):
        self.boot()
        # only continue if the server booted
        if self.checks[0]["passed"]:
            self.auth()
            self.rbac_and_projects()
            self.tasks_and_comments()
            self.dashboard_and_security()

    def summary(self):
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c["passed"])
        return {"pass_rate": round(passed / total, 4) if total else 0.0,
                "passed": passed, "total": total, "checks": self.checks}


def run_cmd(cmd, cwd, timeout):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "returncode": p.returncode,
                "stdout_tail": p.stdout[-1500:], "stderr_tail": p.stderr[-1500:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "returncode": None, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", choices=list(C.TRACKS), required=True)
    ap.add_argument("--base-url", default=C.BASE_URL)
    ap.add_argument("--app-dir", help="track dir containing backend/ and frontend/")
    ap.add_argument("--out", required=True, help="dir to write rubric-score.json")
    ap.add_argument("--start", action="store_true", help="start the backend before testing")
    ap.add_argument("--build", action="store_true", help="build the frontend")
    ap.add_argument("--test", action="store_true", help="run the app's own test suite")
    ap.add_argument("--boot-timeout", type=int, default=300)  # venv + pip install (python track) can exceed 120s
    ap.add_argument("--build-timeout", type=int, default=900)
    args = ap.parse_args()

    tcfg = C.TRACKS[args.track]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"track": args.track, "base_url": args.base_url}
    proc = None

    # Capture lockfile presence BEFORE anything installs: our own `npm install` fallback would
    # otherwise generate a package-lock.json in the working tree and make this always True. At this
    # point the tree reflects exactly what the model produced/committed (run-appcase commits before
    # calling the rubric), so this measures whether the MODEL emitted a lockfile.
    lock_total, lock_have, lock_detail = 0, 0, "no app-dir"
    if args.app_dir:
        npm_dirs = [tcfg["frontend_dir"]] if args.track == "python" else [tcfg["backend_dir"], tcfg["frontend_dir"]]
        lock_total = len(npm_dirs)
        lock_have = sum(1 for d in npm_dirs if (Path(args.app_dir) / d / "package-lock.json").is_file())
        lock_detail = f"{lock_have}/{lock_total} npm dir(s) committed a package-lock.json (checked pre-install)"

    try:
        if args.start:
            if not args.app_dir:
                print("--start requires --app-dir", file=sys.stderr)
                sys.exit(2)
            bdir = Path(args.app_dir) / tcfg["backend_dir"]
            booted = False
            if not bdir.is_dir():
                # The model produced a non-standard layout (no backend dir at the contract path).
                # That's a real failure of the build, NOT a harness error: record backend-not-booted
                # and let the canonical reconciliation below score it (most checks "not reached" → ~0).
                # Previously Popen(cwd=<missing>) raised FileNotFoundError and crashed the whole run
                # before rubric-score.json was written, so the run silently vanished from the sample
                # and biased the model's mean UPWARD (a guaranteed-low run dropped). See node-17.
                print(f"[rubric] backend dir missing: {bdir} — backend not booted (non-standard layout)")
            else:
                # M4: a backend leaked from a PREVIOUS run (even a different model) can still be
                # listening on this port; without a pre-boot check we would health-poll IT and score
                # the wrong app — silent cross-model leakage. Free the port before starting ours.
                if port_busy(args.base_url):
                    print(f"[rubric] a server is ALREADY responding on {args.base_url} before boot "
                          f"— killing the leaked backend (M4)", file=sys.stderr)
                    free_port(port_of(args.base_url))
                    time.sleep(2)
                print(f"[rubric] starting backend: {tcfg['backend_start']} (cwd={bdir})")
                try:
                    proc = subprocess.Popen(tcfg["backend_start"], cwd=str(bdir), shell=True,
                                            stdout=open(out / "backend.log", "w"), stderr=subprocess.STDOUT,
                                            preexec_fn=os.setsid)
                    # wait for health
                    deadline = time.time() + args.boot_timeout
                    while time.time() < deadline:
                        try:
                            if requests.get(args.base_url + C.API + "/health", timeout=3).status_code == 200:
                                booted = True
                                break
                        except Exception:
                            pass
                        time.sleep(2)
                except Exception as e:
                    print(f"[rubric] backend failed to start: {e} — backend not booted")
            result["backend_booted"] = booted

        r = Rubric(args.base_url)
        r.run_http()
        result.update(r.summary())

        if args.build and args.app_dir:
            fdir = Path(args.app_dir) / tcfg["frontend_dir"]
            print(f"[rubric] building frontend: {tcfg['frontend_build']} (cwd={fdir})")
            result["build"] = run_cmd(tcfg["frontend_build"], str(fdir), args.build_timeout)
            r.add("frontend_build", "frontend", result["build"]["ok"], result["build"].get("error", result["build"].get("returncode")))
            result.update(r.summary())  # include build in pass-rate

        # Reproducibility signal (captured pre-install above): did the model commit a
        # package-lock.json for each npm package dir? Scored as its own 1-point check rather than
        # gating install, so a missing lockfile costs one point, not the whole run.
        if args.app_dir:
            r.add("lockfile_present", "reproducibility", lock_total > 0 and lock_have == lock_total, lock_detail)
            result.update(r.summary())

        if args.test and args.app_dir:
            bdir = Path(args.app_dir) / tcfg["backend_dir"]
            print(f"[rubric] running app tests: {tcfg['test_cmd']} (cwd={bdir})")
            result["tests"] = run_cmd(tcfg["test_cmd"], str(bdir), args.build_timeout)

    finally:
        # M4: escalate teardown — SIGTERM, then SIGKILL if the process group survives, then verify
        # the port is actually freed so it can't be scored as the next run's app.
        if proc is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except Exception:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        if args.start:
            time.sleep(1)
            if port_busy(args.base_url):
                print(f"[rubric] backend still listening on {args.base_url} after teardown — "
                      f"force-freeing the port (M4)", file=sys.stderr)
                free_port(port_of(args.base_url))

    # Final reconciliation against the fixed canonical checklist (contract.CANONICAL_CHECKS):
    # score EVERY run against the same denominator. Any canonical check not emitted this run
    # (e.g. the API probes when the backend never booted) is recorded as failed/"not reached",
    # so a dead-backend run scores out of the same N as a fully-working one and pass_rates compare.
    by_name = {c["name"]: c for c in result.get("checks", [])}
    canon = [by_name.get(name, {"name": name, "group": group, "passed": False, "detail": "not reached"})
             for name, group in C.CANONICAL_CHECKS]
    passed = sum(1 for c in canon if c["passed"])
    total = len(canon)
    result["checks"] = canon
    result["passed"] = passed
    result["total"] = total
    result["pass_rate"] = round(passed / total, 4) if total else 0.0

    # C1: dual-report a k/25 rate over the checks that are reachable without the (historically
    # absent) api-contract.md. See contract.UNREACHABLE_WITHOUT_CONTRACT.
    reachable = [c for c in canon if c["name"] not in C.UNREACHABLE_WITHOUT_CONTRACT]
    passed_25 = sum(1 for c in reachable if c["passed"])
    result["passed_reachable"] = passed_25
    result["total_reachable"] = len(reachable)
    result["pass_rate_25"] = round(passed_25 / len(reachable), 4) if reachable else 0.0

    # Disclose whether the frozen contract the prompt references was actually present in the
    # workspace. If it is missing, the four UNREACHABLE_WITHOUT_CONTRACT checks cannot be met
    # from prose alone (this is exactly the baseline-v4/v6 lineage break behind C1).
    if args.app_dir:
        # The contract lives at the app-repo ROOT (benchmark-spec/api-contract.md), not under the
        # per-track app dir. app_dir is <repo>/apps/<track>-track, so search upward for it.
        ad = Path(args.app_dir).resolve()
        contract_fp = None
        for base in [ad, *ad.parents][:4]:
            cand = base / "benchmark-spec" / "api-contract.md"
            if cand.exists():
                contract_fp = cand
                break
        result["contract_present"] = contract_fp is not None
        if contract_fp is None:
            print("[rubric] WARNING: benchmark-spec/api-contract.md not found under the app repo — "
                  "the graded API contract was not visible to the model; k/25 (pass_rate_25) is the "
                  "fair rate.", file=sys.stderr)

    (out / "rubric-score.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in
                      ("track", "pass_rate", "pass_rate_25", "passed", "total") if k in result}, indent=2))
    print(f"[rubric] wrote {out/'rubric-score.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
