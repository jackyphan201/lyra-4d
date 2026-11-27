import json
import shutil
import subprocess
import sys
import unittest

from helpers import ROOT, Env


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        h = self.e.home
        (h / ".codex").mkdir()
        (h / ".codex" / "AGENTS.md").write_text("# My rules\n\nUse Scrapling for scraping.\n")
        (h / ".codex" / "hooks.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "/usr/bin/true user-hook"}]}]}}))
        (h / ".gemini").mkdir()
        (h / ".gemini" / "settings.json").write_text(json.dumps({"theme": "dark", "hooks": {"BeforeTool": [
            {"matcher": "write_file", "hooks": [{"type": "command", "command": "/usr/bin/true guard"}]}]}}))

    def tearDown(self):
        shutil.rmtree(self.e.tmp, ignore_errors=True)

    def lyra_count(self, hooks):
        return sum(1 for gs in hooks.values() for g in gs for x in g["hooks"] if "lyra_hook.py" in x["command"])

    def test_install_is_idempotent_and_keeps_user_config(self):
        self.e.install()
        self.e.install()
        h = self.e.home
        agents = (h / ".codex" / "AGENTS.md").read_text()
        self.assertTrue(agents.startswith("<!-- lyra-4d:begin"))
        self.assertEqual(agents.count("lyra-4d:begin"), 1)
        self.assertIn("Use Scrapling for scraping.", agents)
        ch = json.loads((h / ".codex" / "hooks.json").read_text())["hooks"]
        self.assertEqual(self.lyra_count(ch), 1)
        self.assertTrue(any("user-hook" in x["command"] for g in ch["UserPromptSubmit"] for x in g["hooks"]))
        gs = json.loads((h / ".gemini" / "settings.json").read_text())
        self.assertEqual(gs["theme"], "dark")
        self.assertEqual(self.lyra_count(gs["hooks"]), 2)
        self.assertIn("BeforeTool", gs["hooks"])
        gm = (h / ".gemini" / "GEMINI.md").read_text()
        self.assertEqual(gm.count("lyra-4d:begin"), 1)

    def test_local_host_kits_reach_installed_copies_only(self):
        lh = self.e.home / ".lyra-4d"
        lh.mkdir(parents=True, exist_ok=True)
        (lh / "host-kits.json").write_text(json.dumps({"kits": [{
            "name": "acme-kit", "entry": "acme-workflow", "mcp_prefix": "mcp__plugin_acme-kit_",
            "skills": [{"name": "acme-review", "hint": "Cross-check a spec.", "effects": ["none"]}]}]}))
        self.e.install()
        for p in (self.e.home / ".agents/skills/lyra/SKILL-MAP.md",
                  lh / "claude-marketplace/plugins/lyra-4d/skills/lyra/SKILL-MAP.md"):
            text = p.read_text()
            self.assertIn("### acme-kit (start with `acme-workflow`)", text)
            self.assertIn("`acme-review` (effects: none): Cross-check a spec.", text)
            self.assertLess(text.index("acme-kit"), text.index("## Overlaps"))
        self.assertNotIn("acme-kit", (ROOT / "skills/lyra/SKILL-MAP.md").read_text())

    def test_exposure_policy(self):
        self.e.install()
        sk = self.e.home / ".agents" / "skills"
        names = sorted(p.name for p in sk.iterdir())
        self.assertEqual(names, ["brainstorming", "grill-me", "grilling", "lyra", "research", "writing-plans"])
        self.assertFalse((sk / "using-superpowers").exists())  # bootstrap replaced by Lyra
        self.assertFalse((sk / "loop-me").exists())  # in-progress is opt-in
        self.assertTrue((sk / "grill-me" / "agents" / "openai.yaml").exists())
        self.e.install("--matt-extra")
        self.assertTrue((sk / "loop-me").exists())

    def test_upstream_files_are_byte_identical(self):
        self.e.install()
        r = self.e.run("verify")
        self.assertIn("all upstream files intact", r.stdout)
        src = (self.e.ups["mattpocock"] / "skills/productivity/grilling/SKILL.md").read_bytes()
        dst = (self.e.home / ".agents/skills/grilling/SKILL.md").read_bytes()
        self.assertEqual(src, dst)

    def test_tamper_is_detected_and_repaired(self):
        self.e.install()
        p = self.e.home / ".agents/skills/grilling/SKILL.md"
        p.write_text("tampered")
        r = self.e.run("verify", check=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)
        store = next((self.e.home / ".lyra-4d/store").glob("superpowers@*"))
        (store / "skills/brainstorming/SKILL.md").write_text("tampered")
        self.e.install()
        self.assertEqual(self.e.run("verify").returncode, 0)

    def test_source_not_matching_lock_is_refused(self):
        m = self.e.ups["mattpocock"]
        (m / "skills/productivity/grilling/SKILL.md").write_text("changed but uncommitted")
        r = self.e.run("install", "--hosts", "codex", "--source", f"mattpocock={m}",
                       "--source", f"superpowers={self.e.ups['superpowers']}", check=False)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("does not match the lock", r.stdout + r.stderr)

    def test_foreign_skill_dir_is_not_overwritten(self):
        d = self.e.home / ".agents/skills/grilling"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("my own grilling")
        r = self.e.install()
        self.assertIn("not managed by Lyra", r.stderr)
        self.assertEqual((d / "SKILL.md").read_text(), "my own grilling")

    def test_claude_marketplace_has_no_superpowers_bootstrap(self):
        self.e.install()
        mp = self.e.home / ".lyra-4d/claude-marketplace"
        sp = mp / "plugins/superpowers"
        self.assertFalse((sp / "hooks").exists())
        self.assertFalse((sp / "skills/using-superpowers").exists())
        self.assertTrue((sp / "skills/brainstorming/SKILL.md").exists())
        mpj = json.loads((mp / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual([p["name"] for p in mpj["plugins"]], ["lyra-4d", "mattpocock-skills", "superpowers"])
        self.assertEqual((mp / "plugins/mattpocock-skills/.claude-plugin/plugin.json").read_bytes(),
                         (self.e.ups["mattpocock"] / ".claude-plugin/plugin.json").read_bytes())
        calls = self.e.claude_log.read_text()
        self.assertIn("plugin marketplace add", calls)
        for n in ("lyra-4d", "mattpocock-skills", "superpowers"):
            self.assertIn(f"plugin install {n}@lyra-4d-local", calls)

    def test_uninstall_restores_user_files_and_rollback(self):
        before_agents = (self.e.home / ".codex/AGENTS.md").read_text()
        before_gemini = json.loads((self.e.home / ".gemini/settings.json").read_text())
        self.e.install()
        self.e.run("uninstall")
        self.assertEqual((self.e.home / ".codex/AGENTS.md").read_text(), before_agents)
        self.assertEqual(json.loads((self.e.home / ".gemini/settings.json").read_text()), before_gemini)
        self.assertFalse((self.e.home / ".gemini/GEMINI.md").exists())
        sk = self.e.home / ".agents/skills"
        self.assertEqual(list(sk.iterdir()) if sk.exists() else [], [])
        self.e.run("rollback")  # undo the uninstall
        self.assertIn("lyra-4d:begin", (self.e.home / ".codex/AGENTS.md").read_text())
        self.assertTrue((sk / "grilling/SKILL.md").exists())

    def test_disable_enable(self):
        self.e.install()
        self.e.run("disable")
        self.assertNotIn("lyra-4d:begin", (self.e.home / ".codex/AGENTS.md").read_text())
        out = self.e.hook("codex", "prompt", {"session_id": "z", "prompt": "a"})
        self.assertEqual(out, "")
        self.e.run("enable")
        self.assertIn("lyra-4d:begin", (self.e.home / ".codex/AGENTS.md").read_text())

    def test_dry_run_changes_nothing(self):
        before = (self.e.home / ".codex/AGENTS.md").read_text()
        self.e.run("install", "--hosts", "codex,gemini", "--dry-run",
                   "--source", f"mattpocock={self.e.ups['mattpocock']}",
                   "--source", f"superpowers={self.e.ups['superpowers']}")
        self.assertEqual((self.e.home / ".codex/AGENTS.md").read_text(), before)
        self.assertFalse((self.e.home / ".agents").exists())

    def test_invalid_gemini_settings_left_untouched(self):
        p = self.e.home / ".gemini/settings.json"
        p.write_text("{ // comments are not JSON\n}")
        r = self.e.install()
        self.assertIn("not plain JSON", r.stderr)
        self.assertEqual(p.read_text(), "{ // comments are not JSON\n}")


class BuildTests(unittest.TestCase):
    def test_generated_files_current(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools/build.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_catalog_covers_lock(self):
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        cat = json.loads((ROOT / "catalog/catalog.json").read_text())
        names = {(s["repo"], s["name"]) for g in cat["groups"] for s in g["skills"]}
        for e in lock["upstreams"]:
            for s in e["skills"]:
                self.assertIn((e["name"], s["name"]), names)

    def test_lock_pins_release_commits(self):
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        pins = {e["repo"]: (e["commit"], e["tags"]) for e in lock["upstreams"]}
        self.assertEqual(pins["mattpocock/skills"], ("d1478fcb140db0b93c0c8df17bcfd311844749d0", ["v1.3.2"]))
        self.assertEqual(pins["obra/superpowers"], ("22f0b463e7a5e579904dd6211a520321035526f7", ["v7.0.2"]))

    def test_claude_plugin_hooks_json_shape(self):
        hj = json.loads((ROOT / "adapters/claude/lyra-4d/hooks/hooks.json").read_text())
        self.assertIn("hooks", hj)
        self.assertEqual(set(hj["hooks"]), {"SessionStart", "UserPromptSubmit", "PostToolUse"})
        self.assertEqual(hj["hooks"]["PostToolUse"][0]["matcher"], "^Skill$|^mcp__")

    def test_skill_map_has_host_kits_section_without_private_kits(self):
        sm = (ROOT / "skills/lyra/SKILL-MAP.md").read_text()
        self.assertIn("## Host-provided kits (not pinned by Lyra)", sm)
        self.assertLess(sm.index("## Host-provided kits"), sm.index("## Overlaps"))
        cat = json.loads((ROOT / "catalog/catalog.json").read_text())
        self.assertEqual(cat["host_kits"]["kits"], [])  # private kit names stay out of the public repo

    def test_host_kit_name_colliding_with_locked_skill_is_refused(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import importlib
        build = importlib.import_module("build")
        orig = build.json.loads
        def fake(text, *a, **k):
            d = orig(text, *a, **k)
            if isinstance(d, dict) and "groups" in d and "host_kits" in d:
                d["host_kits"]["kits"] = [{"name": "x", "skills": [{"name": "grilling", "hint": "h", "effects": ["none"]}]}]
            return d
        build.json.loads = fake
        try:
            with self.assertRaises(SystemExit):
                build.skill_map()
        finally:
            build.json.loads = orig


if __name__ == "__main__":
    unittest.main()
