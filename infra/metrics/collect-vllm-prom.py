#!/usr/bin/env python3
"""collect-vllm-prom.py — vLLM inference telemetry collector (source B of 3).

Polls the vLLM Prometheus /metrics endpoint at a fixed interval and writes every
`vllm:` series to a long-format CSV (epoch_ms, metric, le, labels, value). Long
format handles counters, gauges, and histogram buckets uniformly; aggregate.py
pivots and computes per-task-window deltas and distributions.

Stdlib only (urllib). Stops on SIGTERM/SIGINT.

Usage:
  collect-vllm-prom.py --out <out_dir> [--url http://127.0.0.1:8000/metrics] [--interval 0.25]
"""
import argparse
import csv
import re
import signal
import sys
import time
import urllib.request
from pathlib import Path

_STOP = False


def _stop(*_):
    global _STOP
    _STOP = True


# matches:  name{label="v",le="0.1"} 1.23   OR   name 1.23
LINE_RE = re.compile(r'^(vllm:[a-zA-Z0-9_:]+)(\{(?P<labels>[^}]*)\})?\s+(?P<value>[-+0-9.eE]+|NaN|\+Inf|-Inf)\s*$')
LE_RE = re.compile(r'le="([^"]*)"')


def scrape(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode("utf-8", "replace")


def parse(text):
    rows = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        labels = m.group("labels") or ""
        le_m = LE_RE.search(labels)
        le = le_m.group(1) if le_m else ""
        rows.append((name, le, labels, m.group("value")))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://127.0.0.1:8000/metrics")
    ap.add_argument("--interval", type=float, default=0.25)
    args = ap.parse_args()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "vllm-metrics.csv"
    f = csv_path.open("w", newline="")
    w = csv.writer(f)
    w.writerow(["epoch_ms", "metric", "le", "labels", "value"])

    pidfile = out / "vllm-prom.pid"
    pidfile.write_text(str(__import__("os").getpid()))

    errors = 0
    while not _STOP:
        t0 = time.time()
        ms = int(t0 * 1000)
        try:
            rows = parse(scrape(args.url))
            for name, le, labels, value in rows:
                w.writerow([ms, name, le, labels, value])
            f.flush()
        except Exception as e:  # endpoint briefly unavailable -> keep going
            errors += 1
            if errors <= 3:
                print(f"[collect-vllm-prom] scrape error: {e}", file=sys.stderr)
        dt = time.time() - t0
        if dt < args.interval:
            time.sleep(args.interval - dt)

    f.close()
    try:
        pidfile.unlink()
    except FileNotFoundError:
        pass
    print(f"[collect-vllm-prom] stopped; wrote {csv_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
