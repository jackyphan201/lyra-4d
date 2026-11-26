#!/usr/bin/env python3
"""A/B token measurement: the same one-turn prompt with Lyra on and off, N runs each.

  python3 tests/live/measure_tokens.py --host claude --runs 3
  python3 tests/live/measure_tokens.py --host codex --runs 3

Claude: both arms disable the two upstream plugins so only Lyra differs. Codex: the baseline arm runs with
`lyra4d.py disable` (removes the AGENTS.md block) and restores it afterwards.
Reports host-reported input/output tokens per run and the median difference. Uses your own quota.
"""
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_live  # noqa: E402

PROMPT = "Cổng mặc định của PostgreSQL là gì?"


def one(host: str, arm: str) -> dict:
    ws = Path(tempfile.mkdtemp(prefix="lyra-measure-"))
    try:
        if host == "claude":
            exe = run_live.lyra4d.find_claude()
            enabled = {"mattpocock-skills@lyra-4d-local": False, "superpowers@lyra-4d-local": False}
            if arm == "baseline":
                enabled["lyra-4d@lyra-4d-local"] = False
            env = {k: v for k, v in run_live.os.environ.items()
                   if not (k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "ANTHROPIC_BASE_URL", "CLAUDE_PID", "CLAUDE_EFFORT"))}
            r = subprocess.run([exe, "-p", PROMPT, "--output-format", "json", "--settings", json.dumps({"enabledPlugins": enabled})],
                               cwd=ws, capture_output=True, text=True, timeout=600, env=env)
            d = json.loads(r.stdout)
            u = d.get("usage", {})
            return {"input": sum(int(u.get(k, 0) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
                    "output": int(u.get("output_tokens", 0) or 0), "cost": d.get("total_cost_usd"), "text": d.get("result", "")[:120]}
        res = run_live.codex_turn(ws, PROMPT, None, arm, None)
        return {"input": res["input_total"], "output": res["output_tokens"], "text": res.get("text", "")[:120]}
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, choices=["claude", "codex"])
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    out = {"lyra": [], "baseline": []}
    for i in range(a.runs):
        out["lyra"].append(one(a.host, "lyra"))
        print("lyra", out["lyra"][-1], flush=True)
    disabled = False
    try:
        if a.host == "codex":
            subprocess.run([sys.executable, str(run_live.ROOT / "installer" / "lyra4d.py"), "disable"], check=True, capture_output=True)
            disabled = True
        for i in range(a.runs):
            out["baseline"].append(one(a.host, "baseline"))
            print("baseline", out["baseline"][-1], flush=True)
    finally:
        if disabled:
            subprocess.run([sys.executable, str(run_live.ROOT / "installer" / "lyra4d.py"), "enable"], check=True, capture_output=True)
    med = {k: statistics.median(r["input"] for r in v) for k, v in out.items()}
    summary = {"host": a.host, "runs": a.runs, "prompt": PROMPT,
               "input_lyra": [r["input"] for r in out["lyra"]], "input_baseline": [r["input"] for r in out["baseline"]],
               "median_input_delta": med["lyra"] - med["baseline"],
               "output_lyra": [r["output"] for r in out["lyra"]], "output_baseline": [r["output"] for r in out["baseline"]]}
    print(json.dumps(summary, ensure_ascii=False))
    p = run_live.LIVE / "results" / f"measure-{a.host}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({"summary": summary, "runs": out}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
