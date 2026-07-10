#!/usr/bin/env python3
"""clock-sync.py — establish one shared time reference for all collectors.

All collectors timestamp rows with wall-clock epoch_ms; they run on a single host,
so epoch_ms is the join key. This records the wall<->monotonic relationship and a
small repeated-read skew estimate, so the join can be trusted (and any clock step
during a run is visible). Writes clock-sync.json into the run's output dir.

Usage: clock-sync.py --out <out_dir>
"""
import argparse
import json
import time
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # sample wall vs monotonic a few times; report jitter between consecutive reads
    samples = []
    for _ in range(20):
        wall = time.time()
        mono = time.monotonic()
        samples.append((wall, mono))
        time.sleep(0.005)

    # offset = wall - monotonic; should be ~constant. Spread => clock instability.
    offsets = [w - m for (w, m) in samples]
    offset_spread_ms = (max(offsets) - min(offsets)) * 1000.0

    out = {
        "host": __import__("socket").gethostname(),
        "reference_wall_epoch_ms": int(samples[0][0] * 1000),
        "reference_monotonic_s": samples[0][1],
        "wall_minus_monotonic_s": round(offsets[0], 6),
        "offset_spread_ms": round(offset_spread_ms, 4),
        "clock_id": "CLOCK_REALTIME(epoch_ms) joined; CLOCK_MONOTONIC reference recorded",
        "note": "All collectors use epoch_ms (date +%s%3N / time.time()*1000). "
                "offset_spread_ms is the max wall-vs-monotonic drift across 20 reads; "
                "values >> a few ms suggest NTP stepping during the run.",
    }
    p = Path(args.out)
    p.mkdir(parents=True, exist_ok=True)
    (p / "clock-sync.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
