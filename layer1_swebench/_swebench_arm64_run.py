#!/usr/bin/env python3
"""_swebench_arm64_run.py — run the official SWE-bench evaluation CLI on aarch64.

WHY THIS EXISTS
---------------
swebench 4.1.0's `make_test_spec()` hardcodes `arch="x86_64"` as a default and
NEVER inspects `platform.machine()`. On this GB10/aarch64 host that makes every
image spec target `linux/amd64`, so the base Dockerfile runs an x86_64 `apt` step
that dies instantly with `exec /bin/sh: exec format error` (there is no qemu
binfmt on the box). The official images on Docker Hub (`sweb.eval.x86_64.*`) are
x86_64 too, so pulling them fails the same way.

There is no CLI flag or env var to override the arch in this version. This shim
monkeypatches `make_test_spec` to default `arch` from the host machine BEFORE the
`swebench.harness.run_evaluation` module is imported, then hands off to that
module's real `__main__` via runpy with the original argv. Because run_evaluation
binds `make_test_spec` at import time, importing it after the patch picks up the
patched symbol, and swebench's in-process (threaded) workers all see it.

Net effect: on aarch64 the harness BUILDS native arm64 images locally (use it with
`--namespace none`); on x86_64 it is a no-op pass-through. Behavior is otherwise
identical to `python -m swebench.harness.run_evaluation`.

Usage (drop-in for `python -m swebench.harness.run_evaluation`):
  python layer1_swebench/_swebench_arm64_run.py --dataset_name ... --run_id ... [...]
"""
import platform
import runpy
import sys

import swebench.harness.test_spec.test_spec as _ts

_HOST_ARCH = "arm64" if platform.machine() in ("aarch64", "arm64") else "x86_64"
_orig_make_test_spec = _ts.make_test_spec


def _make_test_spec_host_arch(
    instance,
    namespace=None,
    base_image_tag=_ts.LATEST,
    env_image_tag=_ts.LATEST,
    instance_image_tag=_ts.LATEST,
    arch=None,
):
    # Only override the unset / wrong-by-default value; respect an explicit arm64.
    if arch is None or arch == "x86_64":
        arch = _HOST_ARCH
    return _orig_make_test_spec(
        instance,
        namespace=namespace,
        base_image_tag=base_image_tag,
        env_image_tag=env_image_tag,
        instance_image_tag=instance_image_tag,
        arch=arch,
    )


_ts.make_test_spec = _make_test_spec_host_arch
print(f"[arm64-shim] forcing swebench image arch -> {_HOST_ARCH}", file=sys.stderr)

# Hand off to the official CLI's __main__ with our argv intact. Importing it now
# (after the patch) binds the patched make_test_spec inside run_evaluation.
sys.argv[0] = "swebench.harness.run_evaluation"
runpy.run_module("swebench.harness.run_evaluation", run_name="__main__", alter_sys=True)
