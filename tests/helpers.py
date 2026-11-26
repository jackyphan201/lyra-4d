"""Offline fixtures: tiny fake upstream repos shaped like mattpocock/skills and obra/superpowers."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "installer" / "lyra4d.py"
HOOK = ROOT / "hooks" / "lyra_hook.py"


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})


def write(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def skill(name, desc, user_only=False):
    fm = f"---\nname: {name}\ndescription: {desc}\n" + ("disable-model-invocation: true\n" if user_only else "") + "---\n\nBody of " + name + "\n"
    return fm


def make_upstreams(base: Path) -> dict:
    m = base / "matt"
    m.mkdir()
    write(m, "LICENSE", "MIT License\n\nCopyright (c) 2026 Matt Pocock\n")
    write(m, ".claude-plugin/plugin.json", json.dumps({"name": "mattpocock-skills", "version": "1.3.2", "skills": [
        "./skills/productivity/grilling", "./skills/productivity/grill-me", "./skills/engineering/research"]}))
    write(m, "skills/productivity/grilling/SKILL.md", skill("grilling", "Grill the user."))
    write(m, "skills/productivity/grill-me/SKILL.md", skill("grill-me", "Wrapper.", True))
    write(m, "skills/productivity/grill-me/agents/openai.yaml", "policy:\n  allow_implicit_invocation: false\n")
    write(m, "skills/engineering/research/SKILL.md", skill("research", "Research."))
    write(m, "skills/in-progress/loop-me/SKILL.md", skill("loop-me", "Loop.", True))
    write(m, "CLAUDE.md", "# claude\n")
    os.symlink("CLAUDE.md", m / "AGENTS.md")
    git(m, "init", "-q", "-b", "main")
    git(m, "add", "-A")
    git(m, "commit", "-q", "-m", "init")
    git(m, "tag", "v1.3.2")

    s = base / "sp"
    s.mkdir()
    write(s, "LICENSE", "MIT License\n\nCopyright (c) 2025 Jesse Vincent\n")
    write(s, ".claude-plugin/plugin.json", json.dumps({"name": "superpowers", "version": "7.0.2"}))
    write(s, "hooks/hooks.json", json.dumps({"hooks": {"SessionStart": []}}))
    write(s, "hooks/session-start", "#!/bin/bash\necho hi\n")
    write(s, "skills/using-superpowers/SKILL.md", skill("using-superpowers", "Bootstrap."))
    write(s, "skills/brainstorming/SKILL.md", skill("brainstorming", "Brainstorm."))
    write(s, "skills/writing-plans/SKILL.md", skill("writing-plans", "Plans."))
    git(s, "init", "-q", "-b", "main")
    git(s, "add", "-A")
    git(s, "commit", "-q", "-m", "init")
    git(s, "tag", "v7.0.2")
    return {"mattpocock": m, "superpowers": s}


class Env:
    """A throwaway HOME with fake upstreams, a lock for them, and a fake `claude` CLI."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lyra-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.ups = make_upstreams(self.tmp)
        self.lock = self.tmp / "lock.json"
        self.claude_log = self.tmp / "claude-calls.log"
        fake = self.tmp / "fake-claude"
        fake.write_text("#!/bin/sh\necho \"$@\" >> " + str(self.claude_log) + "\n"
                        "if [ \"$1 $2\" = \"plugin list\" ]; then echo '[]'; fi\nexit 0\n")
        fake.chmod(0o755)
        self.env = {**os.environ, "LYRA_TEST_HOME": str(self.home), "LYRA_LOCK": str(self.lock),
                    "LYRA_CLAUDE_BIN": str(fake)}
        self.env.pop("LYRA_HOME", None)
        self.env.pop("CODEX_HOME", None)
        self.run("lock", f"mattpocock={self.ups['mattpocock']}@v1.3.2", f"superpowers={self.ups['superpowers']}@v7.0.2",
                 "--out", str(self.lock))

    def run(self, *args, check=True):
        r = subprocess.run([sys.executable, str(INSTALLER), *args], env=self.env, capture_output=True, text=True)
        if check and r.returncode != 0:
            raise AssertionError(f"lyra4d {args} failed:\n{r.stdout}\n{r.stderr}")
        return r

    def install(self, *extra):
        return self.run("install", "--hosts", "claude,codex,gemini",
                        "--source", f"mattpocock={self.ups['mattpocock']}",
                        "--source", f"superpowers={self.ups['superpowers']}", *extra)

    def hook(self, host, event, payload, extra_env=None):
        env = {**self.env, **(extra_env or {})}
        r = subprocess.run([sys.executable, str(HOOK), "--host", host, "--event", event],
                           input=json.dumps(payload), env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout
