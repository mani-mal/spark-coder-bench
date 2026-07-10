#!/usr/bin/env python3
"""sanity-check.py — SM121/FP4 coherence gate. Run BEFORE any timed measurement.

On GB10 (SM121), FP4 kernels targeting SM120 can run silently and emit garbage, and
fp8 KV-cache can corrupt long generations. This sends a fixed prompt, generates ~600
tokens, and verifies the output is coherent and non-repeating. If it degenerates, the
caller must ABORT the run and NOT record its metrics. Writes sanity-check.json.

Stdlib only (urllib). Exit 0 = passed, 1 = failed/degenerate, 2 = could not run.

Usage:
  sanity-check.py --served <model> --out <dir> [--base-url ...] [--api-key ...] [--max-tokens 600]
"""
import argparse
import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

FIXED_PROMPT = (
    "Write a Python function `nth_prime(n)` that returns the n-th prime number "
    "(1-indexed), with a short docstring and three example assertions. Then explain "
    "in two sentences how it works."
)


def generate(base_url, api_key, model, max_tokens, temperature, seed):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": FIXED_PROMPT}],
        "max_tokens": max_tokens, "temperature": temperature, "seed": seed,
    }).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}"})
    # Warmup-tolerant timeout. TRT-LLM's FIRST request triggers a one-time autotune +
    # CUDA-graph capture that can take ~215s on GB10; the old 180s timeout disconnected
    # mid-warmup, and that aborted request WEDGED the executor (no subsequent request was
    # ever scheduled — GPU idle, zero iters). vLLM responds in seconds so this is a no-op
    # there. Override via SANITY_HTTP_TIMEOUT. See docs/findings 2026-07-01 nemotron-trt-warmup.
    _timeout = float(os.environ.get("SANITY_HTTP_TIMEOUT", "600"))
    with urllib.request.urlopen(req, timeout=_timeout) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]


def degeneration_metrics(text):
    words = text.split()
    n = len(words)
    distinct_ratio = len(set(words)) / n if n else 0.0
    # longest run of an immediately-repeating 5-gram
    max_consec = 0
    if n >= 10:
        grams = [" ".join(words[i:i + 5]) for i in range(n - 4)]
        run = 1
        for i in range(1, len(grams)):
            if grams[i] == grams[i - 1]:
                run += 1
                max_consec = max(max_consec, run)
            else:
                run = 1
    # most common 5-gram frequency share
    top_share = 0.0
    if n >= 10:
        grams = [" ".join(words[i:i + 5]) for i in range(n - 4)]
        c = Counter(grams)
        top_share = c.most_common(1)[0][1] / len(grams)
    return {"tokens": n, "distinct_ratio": round(distinct_ratio, 4),
            "max_consecutive_5gram_repeat": max_consec, "top_5gram_share": round(top_share, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--served", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    ap.add_argument("--api-key", default="local-dgx-spark-key")
    # Default overridable via SANITY_MAX_TOKENS. On TRT-LLM nemotron the NON-streaming sanity
    # request must stay under the ~350-token executor-wedge point (see docs/findings 2026-07-01);
    # set SANITY_MAX_TOKENS=200 there. vLLM is unaffected (streams fine at any length).
    ap.add_argument("--max-tokens", type=int, default=int(os.environ.get("SANITY_MAX_TOKENS", "600")))
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"model": args.served, "prompt": FIXED_PROMPT}
    try:
        text = generate(args.base_url, args.api_key, args.served, args.max_tokens,
                        args.temperature, args.seed)
    except Exception as e:
        result.update({"ok": False, "error": f"generation failed: {e}"})
        (out / "sanity-check.json").write_text(json.dumps(result, indent=2))
        print(f"[sanity] {args.served}: COULD NOT RUN ({e})", file=sys.stderr)
        sys.exit(2)

    m = degeneration_metrics(text)
    # degenerate if too few distinct tokens, long literal loop, or one 5-gram dominates
    repetition = (m["distinct_ratio"] < 0.15
                  or m["max_consecutive_5gram_repeat"] >= 4
                  or m["top_5gram_share"] > 0.2)
    coherent = m["tokens"] >= 30 and ("def" in text)
    ok = coherent and not repetition
    result.update({"ok": ok, "coherent": coherent, "repetition_detected": repetition,
                   "metrics": m, "completion_preview": text[:400]})
    (out / "sanity-check.json").write_text(json.dumps(result, indent=2))
    print(f"[sanity] {args.served}: {'PASS' if ok else 'FAIL'} "
          f"(distinct={m['distinct_ratio']}, loop={m['max_consecutive_5gram_repeat']}, "
          f"top5gram={m['top_5gram_share']})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
