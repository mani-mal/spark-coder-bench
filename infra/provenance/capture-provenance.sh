#!/usr/bin/env bash
# Capture immutable provenance for the benchmark: container image digests (by sha256),
# upstream dataset snapshot revisions, L1 ARM64-subset checksums, and the frozen L3 window.
# Writes infra/provenance/provenance.json.
#
# Live probes (Docker image digests, HF cache revisions, file sha256) are used when available;
# otherwise the RECORDED_* values captured on the benchmark box are emitted, so a fresh public
# clone still gets a complete, pin-for-pin manifest. Reproducers should compare their live
# digests against these to confirm they are on the same images/datasets.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
OUT="infra/provenance/provenance.json"

# ---- Recorded pins (captured on the DGX Spark benchmark box) -----------------
VLLM_IMAGE="nvcr.io/nvidia/vllm:26.02-py3"
TRT_IMAGE="nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9"
RECORDED_VLLM_DIGEST="sha256:1bec659df62970ce856523b67868ab9f92cf947946ee5e89cc6a9cabe9d783da"
RECORDED_TRT_DIGEST="sha256:6c3c31a599a0fe744aa626abc49a49f6f7b642676e8162404f25bf1fef1f0e6d"
RECORDED_SWEBENCH_REV="c104f840cc67f8b6eec6f759ebc8b2693d585d4a"   # princeton-nlp/SWE-bench_Verified
RECORDED_LCB_REV="0fe84c3912ea0c4d4a78037083943e8f0c4dd505"        # livecodebench/code_generation_lite

# ---- Live probes with fallback ----------------------------------------------
img_digest() { # $1=image ref  $2=recorded fallback
  local d=""
  if command -v docker >/dev/null 2>&1; then
    d="$(docker images --digests --format '{{.Repository}}:{{.Tag}} {{.Digest}}' 2>/dev/null \
         | awk -v i="$1" '$1==i{print $2; exit}')"
  fi
  [[ -n "$d" && "$d" != "<none>" ]] && echo "$d" || echo "$2"
}
hf_rev() { # $1=cache dir basename  $2=recorded fallback
  local snap="$ROOT/.hf-cache/hub/$1/snapshots"
  if [[ -d "$snap" ]]; then ls "$snap" 2>/dev/null | head -1; else echo "$2"; fi
}
sha() { [[ -f "$1" ]] && sha256sum "$1" | awk '{print $1}' || echo "MISSING"; }

VLLM_DIGEST="$(img_digest "$VLLM_IMAGE" "$RECORDED_VLLM_DIGEST")"
TRT_DIGEST="$(img_digest "$TRT_IMAGE" "$RECORDED_TRT_DIGEST")"
SWEBENCH_REV="$(hf_rev datasets--princeton-nlp--SWE-bench_Verified "$RECORDED_SWEBENCH_REV")"
LCB_REV="$(hf_rev datasets--livecodebench--code_generation_lite "$RECORDED_LCB_REV")"
SUBSET_CAND_SHA="$(sha layer1_swebench/subset-candidates.json)"
SUBSET_VERIF_SHA="$(sha layer1_swebench/subset-verified.json)"
CAPTURED_AT="$(date -u +%FT%TZ)"
GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"

python3 - "$OUT" <<PY
import json, sys
manifest = {
  "captured_at_utc": "$CAPTURED_AT",
  "git_commit": "$GIT_COMMIT",
  "note": "Immutable pins for reproduction. Live-probed where possible; else recorded on the benchmark box.",
  "container_images": {
    "vllm":  {"ref": "$VLLM_IMAGE", "digest": "$VLLM_DIGEST"},
    "tensorrt_llm": {"ref": "$TRT_IMAGE", "digest": "$TRT_DIGEST"},
  },
  "datasets": {
    "swe_bench_verified": {"repo": "princeton-nlp/SWE-bench_Verified", "revision": "$SWEBENCH_REV",
                            "note": "L1 draws the disclosed 29-task ARM64-buildable subset from this snapshot."},
    "livecodebench_code_generation_lite": {"repo": "livecodebench/code_generation_lite", "revision": "$LCB_REV"},
  },
  "layer1_subset": {
    "candidates_json_sha256": "$SUBSET_CAND_SHA",
    "verified_json_sha256":   "$SUBSET_VERIF_SHA",
  },
  "layer3_window": {
    "window": "pre2024m06", "end_date": "2024-05-31", "inclusive": True,
    "n_problems": 512, "samples_per_problem": 1, "temperature": 0.2, "max_tokens": 8192,
    "note": "Fixed historical contamination-possible window; see docs/methodology.md.",
  },
}
open(sys.argv[1], "w").write(json.dumps(manifest, indent=2) + "\n")
print("wrote", sys.argv[1])
PY
