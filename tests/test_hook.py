import json
import shutil
import unittest

from helpers import ROOT, Env

CORE = (ROOT / "core" / "LYRA-CORE.md").read_text().strip()
TICK = (ROOT / "core" / "LYRA-TICK.md").read_text().strip()


class HookTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def tearDown(self):
        shutil.rmtree(self.e.tmp, ignore_errors=True)

    def ctx(self, out):
        return json.loads(out)["hookSpecificOutput"]

    def test_claude_session_start_then_tick_only(self):
        o = self.ctx(self.e.hook("claude", "session-start", {"session_id": "s1", "source": "startup"}))
        self.assertEqual(o["hookEventName"], "SessionStart")
        self.assertEqual(o["additionalContext"], CORE)
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "s1", "prompt": "hello"}))
        self.assertEqual(o["hookEventName"], "UserPromptSubmit")
        self.assertEqual(o["additionalContext"], TICK)

    def test_resume_does_not_duplicate_core(self):
        self.e.hook("claude", "session-start", {"session_id": "r1", "source": "startup"})
        self.assertEqual(self.e.hook("claude", "session-start", {"session_id": "r1", "source": "resume"}), "")
        o = self.ctx(self.e.hook("claude", "session-start", {"session_id": "r1", "source": "compact"}))
        self.assertEqual(o["additionalContext"], CORE)  # compaction drops it, so re-inject
        o = self.ctx(self.e.hook("claude", "session-start", {"session_id": "new", "source": "resume"}))
        self.assertEqual(o["additionalContext"], CORE)  # unknown session: inject

    def test_claude_prompt_without_session_start_injects_core_once(self):
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "s2", "prompt": "a"}))
        self.assertIn(CORE, o["additionalContext"])
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "s2", "prompt": "b"}))
        self.assertEqual(o["additionalContext"], TICK)

    def test_codex_tick_only_core_lives_in_agents_md(self):
        o = self.ctx(self.e.hook("codex", "prompt", {"session_id": "c1", "prompt": "a", "turn_id": "t"}))
        self.assertEqual(o["hookEventName"], "UserPromptSubmit")
        self.assertEqual(o["additionalContext"], TICK)

    def test_gemini_shapes(self):
        o = self.ctx(self.e.hook("gemini", "prompt", {"session_id": "g1", "prompt": "a"}))
        self.assertEqual(o["hookEventName"], "BeforeAgent")
        out = self.e.hook("gemini", "post-tool", {"session_id": "g1", "tool_name": "activate_skill", "tool_input": {"name": "grilling"}})
        self.assertEqual(json.loads(out), {})

    def test_diag_reports_logged_skills(self):
        self.e.hook("claude", "session-start", {"session_id": "d1"})
        self.e.hook("claude", "post-tool", {"session_id": "d1", "tool_name": "Skill", "tool_input": {"skill": "mattpocock-skills:grilling"}})
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "d1", "prompt": "lyra diag please"}))
        self.assertIn("host-evidence: host=claude", o["additionalContext"])
        self.assertIn("mattpocock-skills:grilling", o["additionalContext"])
        o = self.ctx(self.e.hook("codex", "prompt", {"session_id": "d2", "prompt": "Lyra chẩn đoán"}))
        self.assertIn("core_source=AGENTS.md", o["additionalContext"])

    def test_metrics_never_store_prompt_text(self):
        secret = "PROMPT-TEXT-THAT-MUST-NOT-BE-LOGGED"
        self.e.hook("claude", "prompt", {"session_id": "m1", "prompt": secret})
        log = (self.e.home / ".lyra-4d" / "metrics.jsonl").read_text()
        self.assertNotIn(secret, log)
        self.assertNotIn("m1", log)  # session id is hashed
        rows = [json.loads(l) for l in log.splitlines()]
        self.assertTrue(rows[0]["core_fallback"])

    def test_disabled_and_metrics_off(self):
        lh = self.e.home / ".lyra-4d"
        lh.mkdir(parents=True, exist_ok=True)
        (lh / "metrics-off").write_text("off")
        self.e.hook("claude", "prompt", {"session_id": "x", "prompt": "a"})
        self.assertFalse((lh / "metrics.jsonl").exists())
        (lh / "disabled").write_text("1")
        self.assertEqual(self.e.hook("claude", "prompt", {"session_id": "x", "prompt": "a"}), "")
        self.assertEqual(self.e.hook("gemini", "prompt", {"session_id": "x", "prompt": "a"}), "{}")

    def test_garbage_input_never_breaks_turn(self):
        import subprocess, sys
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / "lyra_hook.py"), "--host", "claude", "--event", "prompt"],
                           input="not json", env=self.e.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Lyra intake", r.stdout)

    def test_mcp_calls_logged_by_server_only(self):
        secret = "MCP-INPUT-THAT-MUST-NOT-BE-LOGGED"
        self.e.hook("claude", "session-start", {"session_id": "p1"})
        self.e.hook("claude", "post-tool", {"session_id": "p1", "tool_name": "mcp__plugin_acme-kit_docs__search",
                                            "tool_input": {"q": secret}, "tool_response": {"text": secret}})
        self.e.hook("claude", "post-tool", {"session_id": "p1", "tool_name": "ListSkills", "tool_input": {}})
        lh = self.e.home / ".lyra-4d"
        self.assertNotIn(secret, (lh / "metrics.jsonl").read_text())
        self.assertNotIn(secret, "".join(f.read_text() for f in (lh / "sessions").glob("*.json")))
        rows = [json.loads(l) for l in (lh / "metrics.jsonl").read_text().splitlines()]
        self.assertEqual([r.get("mcp") for r in rows if r["event"] == "post-tool"], ["plugin_acme-kit_docs"])
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "p1", "prompt": "lyra diag"}))
        self.assertIn("mcp_servers_logged={'plugin_acme-kit_docs': 1}", o["additionalContext"])

    def test_complexity_hint_without_logging_prompt(self):
        prompt = "Tôi cần tư vấn xây dựng bộ máy vận hành đội BA hoàn chỉnh"
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "h1", "prompt": prompt}))
        self.assertIn("Lyra · DETAIL", o["additionalContext"])
        self.assertIn("complexity signals", o["additionalContext"])
        o = self.ctx(self.e.hook("claude", "prompt", {"session_id": "h1", "prompt": "Dịch câu này sang tiếng Anh"}))
        self.assertEqual(o["additionalContext"], TICK)
        log = (self.e.home / ".lyra-4d" / "metrics.jsonl").read_text()
        self.assertNotIn("bộ máy", log)
        rows = [json.loads(l) for l in log.splitlines() if '"prompt"' in l]
        self.assertEqual([r["complex_hint"] for r in rows], [True, False])

    def test_core_and_tick_carry_the_detail_gate(self):
        self.assertTrue(TICK.startswith("Lyra intake"))
        self.assertIn("Lyra · DETAIL", CORE)
        self.assertIn("Lyra · DETAIL", TICK)
        self.assertIn("Complex:", CORE)
        self.assertLessEqual(len(CORE), 4800)

    def test_context_fits_host_limits(self):
        # Claude caps additionalContext at 10,000 chars; Codex previews above ~2,500 tokens.
        self.assertLess(len(CORE) + len(TICK) + 200, 10000)
        self.assertLess(len(TICK), 400)


if __name__ == "__main__":
    unittest.main()
