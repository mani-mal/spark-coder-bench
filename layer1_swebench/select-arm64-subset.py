#!/usr/bin/env python3
"""select-arm64-subset.py — choose the ARM64-buildable subset of SWE-bench Verified.

DGX Spark is aarch64 and the official SWE-bench Verified Docker images are x86-64
only, so we cannot run the full 500. This script (a) lists candidate tasks grouped
by repo, and (b) with --verify, empirically proves buildability on THIS host by
running each task's GOLD patch through the official evaluation: if the env image
builds and the gold patch resolves on ARM64, the task is ARM64-runnable.

Outputs:
  subset-candidates.json   all instance_ids grouped by repo (buildability unverified)
  subset-verified.json     instance_ids proven to build+resolve on ARM64 (with --verify)
  coverage.md              honest coverage statement for the paper

Requires: `datasets` (always); `swebench` + Docker (only for --verify).

Usage:
  select-arm64-subset.py                       # emit candidates
  select-arm64-subset.py --verify --limit 25   # probe 25 tasks for ARM64 buildability
  select-arm64-subset.py --verify --instances a__b-1 c__d-2
"""
import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DATASET = "princeton-nlp/SWE-bench_Verified"
HERE = Path(__file__).resolve().parent


def load_instances():
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("datasets not installed — `pip install -r requirements.txt`")
    ds = load_dataset(DATASET, split="test")
    return list(ds)


def emit_candidates(instances):
    by_repo = defaultdict(list)
    for it in instances:
        by_repo[it["repo"]].append(it["instance_id"])
    cand = {"dataset": DATASET, "total": len(instances),
            "by_repo": {k: sorted(v) for k, v in sorted(by_repo.items())}}
    (HERE / "subset-candidates.json").write_text(json.dumps(cand, indent=2))
    print(f"[select] {len(instances)} tasks across {len(by_repo)} repos "
          f"-> {HERE/'subset-candidates.json'}")
    return cand


def gold_predictions(instances, ids):
    """Predictions file using each task's GOLD patch — a buildability probe."""
    sel = [it for it in instances if it["instance_id"] in ids]
    preds = HERE / "_gold_preds.jsonl"
    with preds.open("w") as f:
        for it in sel:
            f.write(json.dumps({
                "instance_id": it["instance_id"],
                "model_name_or_path": "gold",
                "model_patch": it["patch"],
            }) + "\n")
    return preds


def run_official_eval(preds_path, run_id, instance_ids):
    """Invoke the official SWE-bench evaluation. Returns parsed report dict or None."""
    cmd = [
        # _swebench_arm64_run.py wraps the official CLI and forces native-arch
        # image builds on aarch64 (swebench 4.1.0 hardcodes x86_64); no-op on x86.
        sys.executable, str(HERE / "_swebench_arm64_run.py"),
        "--dataset_name", DATASET,
        "--predictions_path", str(preds_path),
        "--max_workers", "1",
        "--run_id", run_id,
        "--instance_ids", *instance_ids,
        "--cache_level", "env",
        # CRITICAL on aarch64: the default namespace ("swebench") pulls the
        # prebuilt sweb.eval.x86_64.* images from Docker Hub, which cannot
        # execute on this GB10 host (no qemu binfmt) — the container exits
        # instantly and eval errors out. "--namespace none" forces swebench to
        # BUILD the base/env/instance images LOCALLY from its specs, producing
        # native arm64 images. This is the whole mechanism of the ARM64 probe:
        # a task is "arm64-buildable" iff its image builds natively here.
        "--namespace", "none",
    ]
    print(f"[select] running official eval: {' '.join(cmd[:6])} ... ({len(instance_ids)} instances)")
    subprocess.run(cmd, check=False)
    # report is written as <model_name_or_path>.<run_id>.json in CWD
    for cand in (Path.cwd() / f"gold.{run_id}.json", Path.cwd() / f"gold.{run_id}.json"):
        if cand.exists():
            return json.loads(cand.read_text())
    # fallback: search
    hits = list(Path.cwd().glob(f"*{run_id}*.json"))
    return json.loads(hits[0].read_text()) if hits else None


def verify(instances, ids):
    preds = gold_predictions(instances, ids)
    report = run_official_eval(preds, "arm64-probe", ids)
    if not report:
        print("[select] no eval report found — check swebench/docker install", file=sys.stderr)
        return []
    resolved = set(report.get("resolved_ids", []))
    verified = sorted(i for i in ids if i in resolved)
    out = {"dataset": DATASET, "host_arch": "aarch64",
           "probed": sorted(ids), "arm64_buildable": verified,
           "n_probed": len(ids), "n_buildable": len(verified)}
    (HERE / "subset-verified.json").write_text(json.dumps(out, indent=2))
    cov = (HERE / "coverage.md")
    cov.write_text(
        f"# Layer 1 ARM64 coverage\n\n"
        f"- Dataset: `{DATASET}` (500 tasks; x86-64 official images).\n"
        f"- Host arch: aarch64 (GB10).\n"
        f"- Probed {len(ids)} tasks by running their GOLD patch through the official\n"
        f"  evaluation on this host; {len(verified)} built and resolved on ARM64.\n"
        f"- **Reported results use only the disclosed ARM64-buildable subset** — call it\n"
        f"  'pass rate on the disclosed {len(verified)}-task ARM64-buildable subset', NOT\n"
        f"  SWE-bench Verified performance. Same tasks run on identical hardware, but equal\n"
        f"  task exposure does NOT mean contamination cancels: per-model training corpora and\n"
        f"  dedup differ, so memorization can differ on the same tasks. The subset is disclosed\n"
        f"  here, not silently truncated; treat cross-model gaps as descriptive.\n")
    print(f"[select] verified {len(verified)}/{len(ids)} ARM64-buildable "
          f"-> {HERE/'subset-verified.json'}, {cov}")
    return verified


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="empirically probe ARM64 buildability via gold patches")
    ap.add_argument("--limit", type=int, default=25, help="how many tasks to probe with --verify")
    ap.add_argument("--instances", nargs="*", help="explicit instance_ids to probe")
    args = ap.parse_args()

    instances = load_instances()
    emit_candidates(instances)
    if args.verify:
        ids = args.instances or [it["instance_id"] for it in instances][: args.limit]
        verify(instances, ids)


if __name__ == "__main__":
    main()
