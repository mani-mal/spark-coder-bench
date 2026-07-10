#!/usr/bin/env python3
"""collect-opencode.py — OpenCode task-accounting collector (source C of 3).

Best-effort extraction of per-task agent accounting from OpenCode's session
storage: total tokens (input/output/reasoning), agent turns, tool calls, failed
tool calls, and wall-clock. OpenCode's on-disk schema varies by version, so this
collector is defensive: it discovers session files modified within the task
window, parses them, and heuristically sums known fields. It ALWAYS writes
opencode-accounting.json (with a `confidence` flag) and never fails the run.

For a real run the exact schema should be confirmed once and the field map below
tightened (see spec section 13). You may also pass --session-file to point
directly at a known JSON.

Usage:
  collect-opencode.py --out <dir> --start <epoch_ms> --end <epoch_ms> [--session-file F]
"""
import argparse
import json
import os
import sys
from pathlib import Path

# Candidate session-storage roots, most-specific first.
CANDIDATE_ROOTS = [
    os.environ.get("OPENCODE_DATA_DIR"),
    os.path.expanduser("~/.local/share/opencode"),
    os.path.expanduser("~/.config/opencode"),
    os.path.join(os.getcwd(), ".opencode"),
]

# Heuristic key sets (lowercased) we look for when summing usage.
INPUT_KEYS = {"input", "input_tokens", "prompt_tokens", "promptTokens", "tokens_in"}
OUTPUT_KEYS = {"output", "output_tokens", "completion_tokens", "completionTokens", "tokens_out"}
REASON_KEYS = {"reasoning", "reasoning_tokens", "reasoningTokens"}
CACHE_KEYS = {"cache_read", "cache_read_tokens", "cacheRead", "cached_tokens"}


def find_session_files(start_ms, end_ms):
    found = []
    lo, hi = start_ms / 1000.0 - 5, end_ms / 1000.0 + 60  # generous window
    for root in CANDIDATE_ROOTS:
        if not root:
            continue
        p = Path(root)
        if not p.exists():
            continue
        for f in p.rglob("*.json"):
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if lo <= mt <= hi:
                found.append(f)
    return found


def walk(obj):
    """Yield every dict in a nested JSON structure."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def load_docs(files, command_log):
    """Return a list of parsed JSON structures from session files and, if present,
    the run-context command.log (which holds `opencode run --format json` events,
    either one JSON document or JSON-lines)."""
    docs = []
    for f in files:
        try:
            docs.append(json.loads(Path(f).read_text()))
        except Exception:
            pass
    if command_log and Path(command_log).exists():
        text = Path(command_log).read_text()
        try:
            docs.append(json.loads(text))           # whole-file JSON
        except Exception:
            for line in text.splitlines():           # JSON-lines events
                line = line.strip()
                if line.startswith("{") or line.startswith("["):
                    try:
                        docs.append(json.loads(line))
                    except Exception:
                        pass
    return docs


def extract(files, command_log=None):
    tok = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0}
    turns = 0
    tool_calls = 0
    tool_failures = 0
    matched = False

    for data in load_docs(files, command_log):
        for d in walk(data):
            lk = {str(k).lower(): k for k in d.keys()}
            for keyset, slot in ((INPUT_KEYS, "input"), (OUTPUT_KEYS, "output"),
                                 (REASON_KEYS, "reasoning"), (CACHE_KEYS, "cache_read")):
                for cand in keyset:
                    if cand.lower() in lk:
                        v = d[lk[cand.lower()]]
                        if isinstance(v, (int, float)):
                            tok[slot] += v
                            matched = True
            role = str(d.get("role", "")).lower()
            if role == "assistant":
                turns += 1
            if "tool" in lk or "tool_calls" in lk or d.get("type") in ("tool", "tool_use", "tool_result"):
                tool_calls += 1
                if d.get("error") or str(d.get("status", "")).lower() in ("error", "failed"):
                    tool_failures += 1

    return {
        "tokens": tok,
        "total_tokens": sum(tok.values()),
        "agent_turns": turns or None,
        "tool_calls": tool_calls or None,
        "failed_tool_calls": tool_failures or None,
        "matched_usage_fields": matched,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--session-file")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    if args.session_file:
        files = [Path(args.session_file)]
    else:
        files = find_session_files(args.start, args.end)

    command_log = out / "command.log"
    result = extract(files, command_log)
    result.update({
        "wall_clock_ms": args.end - args.start,
        "session_files_scanned": [str(f) for f in files],
        "command_log_parsed": command_log.exists(),
        "confidence": "high" if result["matched_usage_fields"] else "low",
        "note": ("No OpenCode usage fields matched. Confirm session storage path/schema "
                 "for this OpenCode version and tighten collect-opencode.py, or pass "
                 "--session-file. Token totals from vLLM Prometheus remain authoritative "
                 "for inference accounting."),
    })

    (out / "opencode-accounting.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not files:
        print("[collect-opencode] no session files found in window", file=sys.stderr)


if __name__ == "__main__":
    main()
