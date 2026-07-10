#!/usr/bin/env python3
"""model-metadata.py — emit a model's metadata JSON (for the run manifest).

Reads infra/models.json for the given profile and, when the model's weights are
cached locally, verifies MoE expert counts from its config.json (overriding the
registry so the manifest reflects the actual served model). Prints one JSON object.

Usage: model-metadata.py --profile <profile> [--hf-home DIR]
"""
import argparse
import glob
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def find_config(hf_home, hf_id):
    org_name = "models--" + hf_id.replace("/", "--")
    pat = os.path.join(hf_home, "hub", org_name, "snapshots", "*", "config.json")
    hits = sorted(glob.glob(pat))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--hf-home", default=os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")))
    args = ap.parse_args()

    reg = json.loads((REPO_ROOT / "infra" / "models.json").read_text())
    m = next((x for x in reg["models"] if x["profile"] == args.profile), None)
    if not m:
        print(json.dumps({"error": f"profile {args.profile} not in registry"}))
        return

    meta = {k: m.get(k) for k in ("arch", "total_params_b", "active_params_b",
                                  "num_experts", "experts_per_token", "quant", "license", "role")}
    meta["params_source"] = "registry"

    cfg_path = find_config(args.hf_home, m["hf_id"])
    if cfg_path:
        try:
            cfg = json.loads(Path(cfg_path).read_text())
            ne = cfg.get("n_routed_experts") or cfg.get("num_local_experts") or cfg.get("num_experts")
            ept = cfg.get("num_experts_per_tok") or cfg.get("moe_top_k")
            if ne is not None:
                meta["num_experts"] = ne
            if ept is not None:
                meta["experts_per_token"] = ept
            meta["n_shared_experts"] = cfg.get("n_shared_experts")
            meta["model_type"] = cfg.get("model_type")
            meta["config_torch_dtype"] = cfg.get("torch_dtype")
            # compact quant summary only (the full per-layer config can be megabytes)
            qc = cfg.get("quantization_config")
            if isinstance(qc, dict):
                meta["config_quantization"] = {
                    k: qc.get(k) for k in ("quant_method", "format", "kv_cache_scheme", "weights", "bits")
                    if k in qc and not isinstance(qc.get(k), (dict, list))
                }
                meta["config_quantization"]["present"] = True
            else:
                meta["config_quantization"] = None
            meta["params_source"] = "config.json (verified) + registry"
        except Exception as e:
            meta["config_read_error"] = str(e)

    if meta.get("total_params_b") and meta.get("active_params_b"):
        meta["sparsity_active_fraction"] = round(meta["active_params_b"] / meta["total_params_b"], 4)

    print(json.dumps(meta))


if __name__ == "__main__":
    main()
