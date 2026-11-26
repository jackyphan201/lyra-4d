#!/usr/bin/env python3
"""Run the live acceptance cases against real hosts and record what happened.

  python3 tests/live/run_live.py --host claude [--cases 1-translate,4-grill] [--baseline 1-translate,2-po-tool-no-docs]
  python3 tests/live/run_live.py --host codex  [...]

Each run uses a fresh copy of the case fixture in a temp dir. Records per turn: reply text, tools the host
reports (Skill calls, commands, file changes, denied writes), token usage and cost as reported by the host.
Writes raw results to tests/live/results/ (git-ignored). Uses your own Claude / ChatGPT login and quota.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "tests" / "live"
sys.path.insert(0, str(ROOT / "installer"))
import lyra4d  # noqa: E402

CODEX = shutil.which("codex") or "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"


def metrics_lines() -> int:
    p = lyra4d.lyra_home() / "metrics.jsonl"
    return len(p.read_text().splitlines()) if p.exists() else 0


def new_metrics(since: int) -> list:
    p = lyra4d.lyra_home() / "metrics.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines()[since:] if l.strip()]


# ------------------------------------------------------------------ Claude

def claude_turn(ws: Path, prompt: str, session: str | None, arm: str, disable_skill: str | None) -> dict:
    exe = lyra4d.find_claude()
    args = [exe, "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--allowedTools", "Read", "Glob", "Grep", "Skill"]
    enabled = {}
    if arm == "baseline":
        enabled["lyra-4d@lyra-4d-local"] = False
    if disable_skill == "brainstorming":
        enabled["superpowers@lyra-4d-local"] = False
    if enabled:
        args += ["--settings", json.dumps({"enabledPlugins": enabled})]
    if session:
        args += ["--resume", session]
    t0 = time.time()
    # a clean child: drop variables inherited from a parent Claude Code session
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("CLAUDE_CODE_") or k in ("CLAUDECODE", "ANTHROPIC_BASE_URL", "CLAUDE_PID", "CLAUDE_EFFORT"))}
    r = subprocess.run(args, cwd=ws, capture_output=True, text=True, timeout=900, env=env)
    out = {"seconds": round(time.time() - t0, 1), "exit": r.returncode, "tools": [], "hook_events": []}
    for line in r.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init":
            out["model"] = ev.get("model")
            out["plugins"] = [p.get("name") for p in ev.get("plugins", [])]
            out["skills_listed"] = len(ev.get("skills", []) or [])
            out["session"] = ev.get("session_id")
        elif t == "system" and "hook" in str(ev.get("subtype", "")):
            out["hook_events"].append(ev.get("subtype") + ":" + str(ev.get("hook_name") or ev.get("hook_event") or ""))
        elif t == "assistant":
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    inp = b.get("input", {})
                    out["tools"].append({"name": b.get("name"), "input": {k: (str(v)[:200]) for k, v in inp.items()}})
        elif t == "result":
            out["text"] = ev.get("result", "")
            out["usage"] = ev.get("usage", {})
            out["cost_usd"] = ev.get("total_cost_usd")
            out["num_turns"] = ev.get("num_turns")
            out["denied"] = [d.get("tool_name") for d in ev.get("permission_denials", [])]
            out["session"] = ev.get("session_id") or out.get("session")
    if "text" not in out:
        out["error"] = (r.stderr or r.stdout)[-2000:]
    u = out.get("usage", {})
    out["input_total"] = sum(int(u.get(k, 0) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    out["output_tokens"] = int(u.get("output_tokens", 0) or 0)
    return out


# ------------------------------------------------------------------ Codex

def codex_turn(ws: Path, prompt: str, session: str | None, arm: str, disable_skill: str | None) -> dict:
    base = [CODEX, "exec"]
    if session:
        base += ["resume", session]
    args = base + ["--json", "--skip-git-repo-check"]
    if not session:
        args += ["-s", "read-only", "-C", str(ws)]
    if disable_skill:
        path = lyra4d.agents_skills_dir() / disable_skill / "SKILL.md"
        args += ["-c", f'skills.config=[{{path="{path}", enabled=false}}]']
    args.append(prompt)
    t0 = time.time()
    r = subprocess.run(args, cwd=ws, capture_output=True, text=True, timeout=900)
    out = {"seconds": round(time.time() - t0, 1), "exit": r.returncode, "tools": [], "texts": []}
    usage = {}
    for line in r.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = ev.get("type")
        if t == "thread.started":
            out["session"] = ev.get("thread_id")
        elif t == "item.completed":
            it = ev.get("item", {})
            ty = it.get("type")
            if ty == "agent_message":
                out["texts"].append(it.get("text", ""))
            elif ty in ("command_execution", "file_change", "mcp_tool_call", "web_search"):
                out["tools"].append({"name": ty, "input": {"command": str(it.get("command") or it.get("changes") or it.get("query") or "")[:300],
                                                           "status": it.get("status")}})
        elif t == "turn.completed":
            for k, v in (ev.get("usage") or {}).items():
                usage[k] = usage.get(k, 0) + int(v or 0)
        elif t in ("error", "turn.failed"):
            out["error"] = json.dumps(ev)[:1000]
    out["session"] = out.get("session") or session
    out["text"] = "\n\n".join(out.pop("texts"))
    out["usage"] = usage
    out["input_total"] = usage.get("input_tokens", 0)
    out["output_tokens"] = usage.get("output_tokens", 0)
    if r.returncode != 0 and "error" not in out:
        out["error"] = r.stderr[-1500:]
    return out


# ------------------------------------------------------------------ main

def run_case(host: str, case: dict, arm: str) -> dict:
    ws = Path(tempfile.mkdtemp(prefix=f"lyra-live-{case['id']}-"))
    shutil.copytree(LIVE / "fixtures" / case["fixture"], ws, dirs_exist_ok=True)
    (ws / ".keep").unlink(missing_ok=True)
    before = sorted(str(p.relative_to(ws)) for p in ws.rglob("*"))
    m0 = metrics_lines()
    session = None
    turns = []
    for prompt in case["turns"]:
        fn = claude_turn if host == "claude" else codex_turn
        res = fn(ws, prompt, session, arm, case.get("disable_skill"))
        session = res.get("session") or session
        turns.append(res)
    after = sorted(str(p.relative_to(ws)) for p in ws.rglob("*"))
    hooks = new_metrics(m0)
    rec = {"case": case["id"], "host": host, "arm": arm, "turns": turns,
           "files_created": [p for p in after if p not in before],
           "lyra_hook_events": [f"{h['event']}{'+core' if h.get('core_fallback') else ''}" for h in hooks],
           "lyra_injected_chars": sum(h.get("injected_chars", 0) for h in hooks),
           "skills_logged_by_hook": [h["skill"] for h in hooks if h.get("skill")]}
    shutil.rmtree(ws, ignore_errors=True)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, choices=["claude", "codex"])
    ap.add_argument("--cases", default="")
    ap.add_argument("--baseline", default="", help="case ids to also run without Lyra")
    a = ap.parse_args()
    cases = json.loads((LIVE / "cases.json").read_text())["cases"]
    want = [c.strip() for c in a.cases.split(",") if c.strip()]
    if want:
        cases = [c for c in cases if c["id"] in want]
    base_ids = {c.strip() for c in a.baseline.split(",") if c.strip()}
    results = []
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outp = LIVE / "results" / f"{stamp}-{a.host}.json"
    outp.parent.mkdir(exist_ok=True)
    for c in cases:
        print(f"[{a.host}] {c['id']} (lyra)", flush=True)
        results.append(run_case(a.host, c, "lyra"))
        outp.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    if base_ids:
        disabled = False
        try:
            if a.host == "codex":
                subprocess.run([sys.executable, str(ROOT / "installer" / "lyra4d.py"), "disable"], check=True, capture_output=True)
                disabled = True
            for c in [c for c in json.loads((LIVE / "cases.json").read_text())["cases"] if c["id"] in base_ids]:
                print(f"[{a.host}] {c['id']} (baseline, Lyra off)", flush=True)
                results.append(run_case(a.host, c, "baseline"))
                outp.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        finally:
            if disabled:
                subprocess.run([sys.executable, str(ROOT / "installer" / "lyra4d.py"), "enable"], check=True, capture_output=True)
    print(f"wrote {outp}")


if __name__ == "__main__":
    main()
