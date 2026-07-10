# Layer 1 (SWE-bench Verified) on aarch64 — three arch bugs, and the fix

**Date:** 2026-06-26
**Scope:** Making the official SWE-bench Verified evaluation run on the DGX Spark
GB10 (aarch64) host. swebench 4.1.0, Docker 29.2.1, docker-py 7.1.0.

## Result

**SWE-bench Verified IS runnable on this aarch64 host** by building task images
**natively for arm64** instead of using the official x86_64 images. A 4-task
feasibility probe (flask, requests, pylint, pytest — pure-Python repos) built and
resolved their gold patches **4/4** on arm64. Each task built+resolved in ~25s once
the shared base image was cached; env images are ~2.2GB each.

This removes the earlier blocker ("Layer 1 needs docker group / is x86-only"): docker
needs no system change (the `sg docker` path already used for vLLM works), and the
x86-only assumption is false for pure-Python repos once images are built natively.

## The three layered bugs (each hid the next)

### 1. The official images are x86_64 and can't execute here
By default swebench pulls prebuilt `swebench/sweb.eval.x86_64.*` images from Docker
Hub. There is no qemu binfmt registered on this host (`/proc/sys/fs/binfmt_misc` has
no qemu entry), so an x86_64 container starts and its entrypoint dies instantly with
`exec /bin/sh: exec format error`; the harness then errors with a 409 "container is
not running". **Fix:** pass `--namespace none` so swebench builds images locally
instead of pulling the x86_64 prebuilts.

### 2. swebench 4.1.0 hardcodes `arch="x86_64"` — it never checks the host
With local builds forced, swebench *still* targeted amd64: `make_test_spec()` takes
`arch: str = "x86_64"` as a default and **never inspects `platform.machine()`**
(which correctly returns `aarch64` here). So every generated Dockerfile got
`FROM --platform=linux/amd64 ...` and failed the same way. There is no CLI flag to
override it. **Fix:** `layer1_swebench/_swebench_arm64_run.py` — a thin wrapper that
monkeypatches `make_test_spec` to default `arch` from the host machine, then runs the
official `swebench.harness.run_evaluation` `__main__` via `runpy` with argv intact.
Because run_evaluation binds `make_test_spec` at import time and swebench parallelizes
in-process (threads, not subprocesses), patching the symbol before import makes every
worker build native-arch images. No-op on an x86_64 host. Both `select-arm64-subset.py`
and `run-task.py` now invoke this wrapper instead of `python -m swebench...`.

### 3. A cached amd64 `ubuntu:22.04` poisoned the arm64 build
Even with the Dockerfile correctly saying `FROM --platform=linux/arm64/v8 ubuntu:22.04`,
the build still ran amd64. Cause: an amd64 `ubuntu:22.04` was already cached locally
(pulled during bugs #1–#2), and swebench builds through **docker-py's classic builder**
(not BuildKit), which reuses a locally-present tag regardless of the requested
`--platform`. **Fix:** `docker rmi ubuntu:22.04 && docker pull --platform linux/arm64
ubuntu:22.04`. After that the base image (`sweb.base.py.arm64`) builds cleanly (conda
for aarch64) and env/instance images follow. Operationally: don't leave a wrong-arch
base tag cached; the classic builder won't correct it for you.

## Validity for the paper

This is a **relative A/B on identical hardware** — both models solve the same
arm64-built tasks, so any arm64-vs-x86 behavioral difference in the task environments
cancels across models. The arm64-buildable subset is disclosed in `coverage.md`, not
silently truncated. Coverage is bounded to repos whose env builds on arm64; pure-Python
repos (flask, requests, pylint, pytest, sympy, sphinx, xarray, etc.) are expected to
build, while repos needing x86-only wheels or heavy C/Fortran toolchains may not — the
selector proves buildability empirically per task rather than assuming it.

## How to run

```bash
# 0) one-time: ensure no wrong-arch base tag is cached
sg docker -c 'docker rmi -f ubuntu:22.04; docker pull --platform linux/arm64 ubuntu:22.04'

# 1) select + verify the arm64 subset (gold-patch buildability probe)
export HF_HOME="$PWD/.hf-cache"   # dataset cache must be user-writable (model cache is root-owned)
sg docker -c '.venv/bin/python layer1_swebench/select-arm64-subset.py --verify --limit 50'

# 2) serve a model, run the suite (resumable), repeat per model
infra/vllm/serve-model.sh qwen3-coder-30b
sg docker -c 'layer1_swebench/run-suite.sh qwen3-coder-30b 3'
```
