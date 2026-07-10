#!/usr/bin/env python3
"""run-task.py — run ONE SWE-bench task end-to-end with full metric capture.

Flow:
  1. Load the instance (repo, base_commit, problem_statement) from the dataset.
  2. Clone the repo at base_commit into a clean workdir.
  3. Hand the issue to OpenCode headless (`opencode run`), wrapped in run-context.sh
     so the 3-source metrics are captured for the agent's work window.
  4. Extract the model's patch as `git diff` over the workdir.
  5. Score with the OFFICIAL SWE-bench evaluation (FAIL_TO_PASS / PASS_TO_PASS).
  6. Write resolved.json into results/raw/<run-id>/ next to run-summary.json.

Requires: datasets, swebench, Docker (the eval builds the task env image — on ARM64
only tasks in the verified subset will build; see select-arm64-subset.py).

Usage:
  run-task.py --instance-id <id> --profile qwen3-coder-30b --repeat 1
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DATASET = "princeton-nlp/SWE-bench_Verified"
REPO_ROOT = Path(__file__).resolve().parents[1]


def load_instance(instance_id):
    from datasets import load_dataset
    ds = load_dataset(DATASET, split="test")
    for it in ds:
        if it["instance_id"] == instance_id:
            return it
    sys.exit(f"instance not found: {instance_id}")


def sh(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def clone_at(repo, base_commit, workdir):
    url = f"https://github.com/{repo}.git"
    workdir.mkdir(parents=True, exist_ok=True)
    if (workdir / ".git").exists():
        # M3: a retry into an existing workdir must not inherit the previous attempt's staged or
        # working-tree changes — `git checkout <same-commit>` alone leaves them in place, so the
        # scored diff could mix two attempts. Reset to a pristine tree first.
        sh(["git", "reset", "-q", "--hard"], cwd=workdir, check=False)
        sh(["git", "clean", "-fdxq"], cwd=workdir, check=False)
    sh(["git", "init", "-q"], cwd=workdir)
    sh(["git", "remote", "add", "origin", url], cwd=workdir, check=False)
    # fetch just the base commit when possible, fall back to full fetch
    if sh(["git", "fetch", "-q", "--depth", "1", "origin", base_commit], cwd=workdir, check=False).returncode != 0:
        sh(["git", "fetch", "-q", "origin"], cwd=workdir)
    sh(["git", "checkout", "-q", base_commit], cwd=workdir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--repeat", default="1")
    ap.add_argument("--metrics-url", default="http://127.0.0.1:8000/metrics")
    ap.add_argument("--workroot", default="/tmp/swebench-work")
    ap.add_argument("--opencode-bin", default="opencode")
    # Runtime selection: default reproduces the original vLLM behavior exactly
    # (provider=vllm-local, empty tag → run-ids unchanged). For TensorRT-LLM pass
    # --provider trt-local --runtime-tag trt --metrics-url http://127.0.0.1:8355/metrics.
    ap.add_argument("--provider", default="vllm-local")
    ap.add_argument("--runtime-tag", default="")
    args = ap.parse_args()

    tag = f"-{args.runtime_tag}" if args.runtime_tag else ""

    inst = load_instance(args.instance_id)
    run_id = f"{args.profile}{tag}-l1-{args.instance_id}-{args.repeat}"
    out_dir = REPO_ROOT / "results" / "raw" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(args.workroot) / run_id

    print(f"[task] {run_id}: cloning {inst['repo']}@{inst['base_commit'][:10]}")
    clone_at(inst["repo"], inst["base_commit"], workdir)

    prompt = (
        "You are fixing a real GitHub issue in this repository. Make the minimal "
        "code change that resolves the issue. Do NOT modify or write tests; the "
        "graders run hidden tests. Issue:\n\n" + inst["problem_statement"]
    )

    # agent step with full metric capture
    rc = subprocess.run([
        str(REPO_ROOT / "infra/metrics/run-context.sh"), run_id,
        "--metrics-url", args.metrics_url, "--",
        args.opencode_bin, "run", "--format", "json",
        "-m", f"{args.provider}/{args.profile}", "--dir", str(workdir), prompt,
    ])
    print(f"[task] agent finished (run-context exit={rc.returncode})")

    # extract model patch
    diff = sh(["git", "add", "-A"], cwd=workdir, check=False)
    model_patch = sh(["git", "diff", "--cached"], cwd=workdir, check=False).stdout
    (out_dir / "model_patch.diff").write_text(model_patch)

    # predictions for official eval
    preds = out_dir / "predictions.jsonl"
    preds.write_text(json.dumps({
        "instance_id": args.instance_id,
        "model_name_or_path": args.profile,
        "model_patch": model_patch,
    }) + "\n")

    if not model_patch.strip():
        # M1: distinguish a genuine empty-diff (agent ran, produced nothing) from an infra failure
        # (server death / guard kill / timeout mid-sweep). Recording the latter as resolved=0 would
        # brand it a legitimate model failure AND — because a present resolved.json is resume-
        # skipped — freeze that wrong verdict forever. On a nonzero agent exit, leave an
        # infra-error marker instead and do NOT write resolved.json, so the sweep re-attempts it.
        if rc.returncode != 0:
            (out_dir / "infra-error.json").write_text(json.dumps(
                {"instance_id": args.instance_id, "model": args.profile, "repeat": args.repeat,
                 "agent_exit_code": rc.returncode,
                 "note": "agent step exited nonzero and produced no diff; not scored (infra)"},
                indent=2))
            print(f"[task] agent step failed (exit={rc.returncode}) with no diff — "
                  f"marked infra-error, NOT scored/resume-skipped")
            sys.exit(rc.returncode or 1)
        print("[task] empty patch — recording unresolved")
        (out_dir / "resolved.json").write_text(json.dumps(
            {"instance_id": args.instance_id, "model": args.profile, "repeat": args.repeat,
             "resolved": 0, "note": "model produced no diff"}, indent=2))
        return

    # official evaluation
    # M2: include the instance id in the eval run_id so the report filename is unique per task.
    # Previously the id was omitted (l1-<profile>-<repeat>), so the official report — named
    # <profile>.<run_id>.json — collided across tasks, and the glob fallback could silently read a
    # STALE previous instance's report and misattribute its resolved/unresolved verdict. Run the
    # eval inside the per-run dir so the report (and swebench's logs/) land there, not as litter in
    # the repo root.
    run_eval_id = f"l1-{args.profile}{tag}-{args.instance_id}-{args.repeat}"
    cmd = [sys.executable, str(REPO_ROOT / "layer1_swebench" / "_swebench_arm64_run.py"),
           "--dataset_name", DATASET, "--predictions_path", str(preds),
           "--max_workers", "1", "--run_id", run_eval_id,
           "--instance_ids", args.instance_id, "--cache_level", "env",
           # aarch64: build images locally (native arm64) instead of pulling the
           # x86_64 prebuilts, which can't run here. See select-arm64-subset.py.
           "--namespace", "none"]
    print(f"[task] official eval: run_id={run_eval_id}")
    subprocess.run(cmd, check=False, cwd=out_dir)

    # Report is <model_name_or_path>.<run_id>.json in the eval CWD (out_dir). Match on the exact
    # instance-qualified run_eval_id only — never a bare-prefix glob that could match another task.
    report = {}
    hits = sorted(out_dir.glob(f"*.{run_eval_id}.json"))
    if hits:
        report = json.loads(hits[0].read_text())

    resolved = 1 if args.instance_id in set(report.get("resolved_ids", [])) else 0
    (out_dir / "resolved.json").write_text(json.dumps(
        {"instance_id": args.instance_id, "model": args.profile, "repeat": args.repeat,
         "resolved": resolved, "eval_run_id": run_eval_id}, indent=2))
    print(f"[task] {run_id}: resolved={resolved}")


if __name__ == "__main__":
    main()
