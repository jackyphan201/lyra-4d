#!/usr/bin/env python3
"""Lyra 4-D hook: gives the model the Lyra intake note on every user turn.

Hosts: claude (SessionStart, UserPromptSubmit, PostToolUse on Skill and MCP tools),
       codex (UserPromptSubmit), gemini (BeforeAgent, AfterTool:activate_skill).
Prints only the host's JSON on stdout; never blocks a turn; exits 0 on any error.
Logs counts only (no prompt text, no tool input or output) to ~/.lyra-4d/metrics.jsonl unless metrics are off.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

DIAG_RE = re.compile(r"\blyra\s*(diag|diagnostics?|chẩn\s*đoán|chan\s*doan|debug)\b", re.I)
# Prompts that usually ask for a system, process, team or end-to-end result. Matched in memory only; never logged.
COMPLEX_RE = re.compile(
    r"(xây\s*dựng|thiết\s*kế|quy\s*trình|hệ\s*thống|vận\s*hành|bộ\s*máy|toàn\s*bộ|hoàn\s*chỉnh|tư\s*vấn|lộ\s*trình|chiến\s*lược"
    r"|\bend[\s-]*to[\s-]*end\b|\boperating\s+model\b|\broadmap\b|\bstrategy\b"
    r"|\bfrom\s+scratch\b|\bcomplete\s+(system|process|plan|setup)\b)",
    re.I,
)
COMPLEX_HINT = ("This prompt matches Lyra complexity signals. Unless a workflow is already approved in this conversation "
                "or the request is clearly simple, the reply is the `Lyra · DETAIL` message, not finished work.")
EVENT_NAMES = {
    ("claude", "session-start"): "SessionStart",
    ("claude", "prompt"): "UserPromptSubmit",
    ("codex", "session-start"): "SessionStart",
    ("codex", "prompt"): "UserPromptSubmit",
    ("gemini", "session-start"): "SessionStart",
    ("gemini", "prompt"): "BeforeAgent",
}


def lyra_home() -> Path:
    if os.environ.get("LYRA_HOME"):
        return Path(os.environ["LYRA_HOME"])
    base = Path(os.environ.get("LYRA_TEST_HOME") or Path.home())
    return base / ".lyra-4d"


def core_dir() -> Path:
    if os.environ.get("LYRA_CORE_DIR"):
        return Path(os.environ["LYRA_CORE_DIR"])
    here = Path(__file__).resolve().parent
    for cand in (here / "core", here.parent / "core"):
        if (cand / "LYRA-CORE.md").exists():
            return cand
    return here / "core"


def read_core(name: str) -> str:
    return (core_dir() / name).read_text(encoding="utf-8").strip()


def session_key(data: dict) -> str:
    sid = str(data.get("session_id") or data.get("sessionId") or os.environ.get("GEMINI_SESSION_ID") or "unknown")
    return hashlib.sha256(sid.encode()).hexdigest()[:12]


class Registry:
    """Per-session flags (no prompt text): turns seen, whether the core was injected, skills logged."""

    def __init__(self, key: str):
        self.dir = lyra_home() / "sessions"
        self.path = self.dir / f"{key}.json"
        try:
            self.data = json.loads(self.path.read_text())
        except Exception:
            self.data = {"turns": 0, "core": False, "skills": [], "mcp": {}}

    def save(self):
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data))
            os.replace(tmp, self.path)
            if self.data["turns"] % 50 == 1:
                self._prune()
        except Exception:
            pass

    def _prune(self):
        cutoff = time.time() - 14 * 86400
        for p in self.dir.glob("*.json"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except Exception:
                pass


def log_metric(row: dict):
    home = lyra_home()
    if (home / "metrics-off").exists():
        return
    try:
        home.mkdir(parents=True, exist_ok=True)
        p = home / "metrics.jsonl"
        if p.exists() and p.stat().st_size > 2_000_000:
            os.replace(p, home / "metrics.1.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def context_output(host: str, event: str, text: str) -> str:
    name = EVENT_NAMES[(host, event)]
    return json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}, ensure_ascii=False)


def skill_from_tool(host: str, data: dict):
    tool = str(data.get("tool_name") or "")
    tin = data.get("tool_input") or {}
    if not isinstance(tin, dict):
        return None
    if host == "claude" and tool == "Skill":
        return tin.get("skill") or tin.get("command") or tin.get("name")
    if host == "gemini" and tool == "activate_skill":
        return tin.get("name") or tin.get("skill")
    return None


def mcp_from_tool(host: str, data: dict):
    """Server part of an MCP tool name (mcp__<server>__<tool>); only the name is read, never input or output."""
    tool = str(data.get("tool_name") or "")
    if host != "claude" or not tool.startswith("mcp__"):
        return None
    parts = tool.split("__")
    return parts[1] if len(parts) >= 3 and parts[1] else None


def run(host: str, event: str, data: dict) -> str:
    home = lyra_home()
    silent = "{}" if host == "gemini" else ""
    if (home / "disabled").exists():
        return silent
    key = session_key(data)
    reg = Registry(key)
    row = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "host": host, "event": event, "session": key}
    if data.get("transcript_path"):
        row["transcript"] = str(data["transcript_path"])

    if event == "post-tool":
        skill = skill_from_tool(host, data)
        if skill:
            reg.data.setdefault("skills", []).append(str(skill))
            reg.save()
            row["skill"] = str(skill)
            log_metric(row)
            return silent
        server = mcp_from_tool(host, data)
        if server:
            counts = reg.data.setdefault("mcp", {})
            counts[server] = int(counts.get(server, 0)) + 1
            reg.save()
            row["mcp"] = server
            log_metric(row)
        return silent

    if event == "session-start":
        source = str(data.get("source") or "")
        if source == "resume" and reg.data.get("core"):
            # the resumed transcript already carries the core; skip a duplicate copy
            row.update({"injected_chars": 0, "skipped": "resume-duplicate"})
            log_metric(row)
            return silent
        text = read_core("LYRA-CORE.md")
        reg.data["core"] = True
        reg.save()
        row["injected_chars"] = len(text)
        log_metric(row)
        return context_output(host, event, text)

    # event == "prompt"
    reg.data["turns"] = int(reg.data.get("turns", 0)) + 1
    parts = [read_core("LYRA-TICK.md")]
    fallback = False
    core_in_hook = host == "claude" or os.environ.get("LYRA_CORE_IN_HOOK") == "1"
    if core_in_hook and not reg.data.get("core"):
        parts.insert(0, read_core("LYRA-CORE.md"))
        reg.data["core"] = True
        fallback = True
    prompt = str(data.get("prompt") or "")
    complex_hint = bool(COMPLEX_RE.search(prompt))
    if complex_hint:
        parts.append(COMPLEX_HINT)
    if DIAG_RE.search(prompt):
        skills = reg.data.get("skills", [])
        source = "hook" if host == "claude" else ("AGENTS.md" if host == "codex" else "GEMINI.md")
        parts.append(
            f"host-evidence: host={host} hook={EVENT_NAMES[(host, 'prompt')]} turn={reg.data['turns']} "
            f"core_source={source} skills_invoked_logged={skills or 'none'} "
            f"mcp_servers_logged={reg.data.get('mcp') or 'none'}"
        )
    reg.save()
    text = "\n\n".join(parts)
    row.update({"turn": reg.data["turns"], "injected_chars": len(text), "core_fallback": fallback,
                "complex_hint": complex_hint})
    log_metric(row)
    return context_output(host, event, text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True, choices=["claude", "codex", "gemini"])
    ap.add_argument("--event", required=True, choices=["session-start", "prompt", "post-tool"])
    args = ap.parse_args()
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    try:
        out = run(args.host, args.event, data)
    except Exception as e:  # never break the user's turn
        try:
            home = lyra_home()
            home.mkdir(parents=True, exist_ok=True)
            with open(home / "hook-errors.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} {args.host} {args.event} {type(e).__name__}: {e}\n")
        except Exception:
            pass
        out = "{}" if args.host == "gemini" else ""
    if out:
        sys.stdout.write(out)
    sys.exit(0)


if __name__ == "__main__":
    main()
