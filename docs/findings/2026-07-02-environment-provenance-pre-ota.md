# Environment provenance snapshot — frozen before DGX Spark OTA update

**Date captured:** 2026-07-02 12:21 UTC
**Why:** The full 3-model × 3-layer benchmark completed on 2026-07-02 with results
committed and pushed. Immediately after, we discovered the box had never run the
DGX Spark OTA update and was behind (build 7.2.3, OTA target 7.5.0). This note freezes
the exact environment the **published results were produced on**, so the numbers stay
interpretable after the box is updated. The OTA was run right after writing this doc.

All benchmark results in `results/summary/benchmark-{long,summary}.csv`, the findings
docs, and the charts were produced on the environment below. They are NOT changed by the
update — an OS upgrade cannot alter data already written to disk and pushed to GitHub.
This snapshot exists purely so "results were produced on X" is airtight for the writeup.

---

## System (as-run for all benchmark results)

| Component | Value |
|---|---|
| Machine | NVIDIA DGX Spark (`spark-ae6d`), aarch64, GB10 |
| DGX OS build | **7.2.3** (2025-09-10, commit 833b4a7) |
| OS | Ubuntu 24.04.4 LTS (Noble) |
| Kernel | **6.17.0-1021-nvidia** (#21, 2026-05-27) |
| GPU driver (nvidia-smi) | **580.159.03** |
| GPU driver kernel-module branch | 580-open |
| Unified memory | 121 GiB (nvidia-smi reports memory.* = [N/A], unified) |
| Docker | 29.2.1 (build a5c7197) |
| CUDA (in-container) | 13.1 via forward-compat on 580 driver |

## Serving images (as-run)

| Image | ID | Used for |
|---|---|---|
| `nvcr.io/nvidia/vllm:26.02-py3` | 1f992bc7f8cc | vLLM path (qwen3-coder-30b, gpt-oss-120b) — vLLM 0.15.1 |
| `nvcr.io/nvidia/tensorrt-llm/release:1.3.0rc9` | 279d4b6d6ef1 | nemotron-super TRT-LLM path (L1/L2/L3) |
| `nvcr.io/nvidia/tensorrt-llm/release:1.2.1` | f2ba682cbd4f | earlier TRT-LLM probing |

State at capture time: **no container running** (clean; nothing serving).

## Shared inference config (as-run, L3)

seed 0 / temp 0.2 / top_p 0.95 / n=1 / max_tokens 8192 / single-stream. L1/L2 per their runners.

---

## What the OTA changes (and does not)

**Does NOT change:** any recorded result. Quality/capability metrics (LiveCodeBench pass@1,
SWE-bench resolved rate, app-build rubric) are properties of the model weights + prompts +
seeds, not the box. Rankings and all methodological findings (low-N mis-ranking / flip table,
code-gen ≠ agentic tool-use, nemotron truncation-artifact, deployment-reality blockers) are
driver- and kernel-independent.

**COULD nudge (only if efficiency runs were repeated after update):** decode tok/s, TTFT,
Wh/task, tok/J — these are the only box-tied metrics. Even here the impact is expected small
because the update is primarily a kernel refresh + DGX tooling; the **GPU driver stays on the
580-open branch** (see nuance below). Efficiency findings are reported as relative A/B with the
FP4-weight-only-on-GB10 caveat already disclosed, so a minor throughput shift would not overturn
them.

### Nuance: this OTA is not a 580→610 driver-family swap
The upgradable list shows `nvidia-modprobe 580.82 → 610.43`, but that package is only the
small userspace setuid helper. The GPU **kernel driver module stays 580-open**
(`linux-modules-nvidia-580-open-nvidia-hwe-24.04` → 6.17.0-1026, still the 580-open flavor).
So the GPU driver family is unchanged; the substantive parts of this OTA are the HWE kernel
bump (6.17.0-1021 → -1026) and DGX platform tooling (dashboard, telemetry, oobe, ota-meta,
wifi firmware).

---

## Pending upgrade set (apt lists refreshed 2026-07-02 11:22 UTC) — 50 packages

DGX / NVIDIA:
- dgx-dashboard 0.23.3 → 0.29.0
- dgx-oobe 0.19.4 → 0.25.1
- dgx-spark-ota-update-meta 26.03.1 → 26.04.1  (the OTA "sync" metapackage)
- nvidia-ai-workbench 0.132.25 → 0.169.2
- nvidia-dgx-telemetry 4.11 → 5.22
- nvidia-modprobe 580.82 → 610.43  (userspace helper only; kernel module stays 580-open)
- nvidia-spark-wifi-fw-ppa 1.1 → 1.2

Kernel / HWE (NVIDIA-open branch, reboot required):
- linux-{image,headers,tools}-nvidia-hwe-24.04 6.17.0-1021.21 → 6.17.0-1026.26
- linux-modules-nvidia-580-open-nvidia-hwe-24.04 → 6.17.0-1026.26
- linux-modules-nvidia-fs-nvidia-hwe-24.04 → 6.17.0-1026.26
- linux-nvidia-hwe-24.04 → 6.17.0-1026.26
- linux-crashdump / linux-libc-dev / linux-tools-common 6.8.0-124 → 6.8.0-134

Ubuntu base (security/updates): curl/libcurl 8.5.0-2ubuntu10.9→.10, libnss3, libxml2,
libsqlite3-0/sqlite3 3.45.1-ubuntu2.5→.6, perl/perl-base/perl-modules 5.38.2-3.2ubuntu0.2→.3,
tar, iproute2, multipath-tools/kpartx, hplip/printer drivers, libfprint, freerdp/vnc/winpr,
python3-pip/wheel, libdbi-perl, libnfs14, code (VS Code) 1.125.1 → 1.127.0.

Full machine-readable list preserved in this repo's git history alongside this doc.

---

## To reproduce the exact pre-OTA environment later
Pin: DGX OS 7.2.3, kernel 6.17.0-1021-nvidia, driver 580.159.03, vLLM image `26.02-py3`
(vLLM 0.15.1), TRT-LLM `release:1.3.0rc9`, CUDA 13.1 forward-compat, single-stream shared config.
