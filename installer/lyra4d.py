#!/usr/bin/env python3
"""Lyra 4-D installer and maintenance CLI (Python 3.8+, standard library only).

Commands: install, update, verify, status, uninstall, rollback, enable, disable,
diag, metrics, lock (maintainers). Run `python3 installer/lyra4d.py -h`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = Path(os.environ.get("LYRA_LOCK") or REPO_ROOT / "upstream.lock.json")
MARKETPLACE_NAME = "lyra-4d-local"
BLOCK_BEGIN = "<!-- lyra-4d:begin (managed by lyra4d.py; edit core/LYRA-CORE.md instead) -->"
BLOCK_END = "<!-- lyra-4d:end -->"
HOOK_MARK = "lyra_hook.py"


# ---------------------------------------------------------------- paths

def home() -> Path:
    return Path(os.environ.get("LYRA_TEST_HOME") or Path.home())


def lyra_home() -> Path:
    return Path(os.environ.get("LYRA_HOME") or home() / ".lyra-4d")


def codex_home() -> Path:
    if os.environ.get("LYRA_TEST_HOME"):
        return home() / ".codex"
    return Path(os.environ.get("CODEX_HOME") or home() / ".codex")


def gemini_home() -> Path:
    return home() / ".gemini"


def agents_skills_dir() -> Path:
    return home() / ".agents" / "skills"


def store_dir() -> Path:
    return lyra_home() / "store"


def runtime_dir() -> Path:
    return lyra_home() / "runtime"


def state_path() -> Path:
    return lyra_home() / "state.json"


# ---------------------------------------------------------------- utils

def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def say(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"WARN  {msg}", file=sys.stderr, flush=True)


def load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return default
    return json.loads(text)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".lyra-tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".lyra-tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def parse_frontmatter(text: str) -> dict:
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if mm:
            val = mm.group(2).strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            out[mm.group(1)] = val
    return out


# ---------------------------------------------------------------- state & backups

class State:
    def __init__(self):
        self.data = load_json(state_path(), {"version": VERSION, "installs": [], "current": {}})

    @property
    def current(self) -> dict:
        return self.data.setdefault("current", {})

    def save(self):
        self.data["version"] = VERSION
        write_json(state_path(), self.data)


class Session:
    """One install/uninstall run: keeps backups so `rollback` can undo it."""

    def __init__(self, action: str, dry_run: bool):
        self.dry = dry_run
        self.id = now_stamp()
        self.action = action
        self.backup_root = lyra_home() / "backups" / self.id
        self.record = {"id": self.id, "action": action, "backups": [], "created": []}

    def backup(self, path: Path):
        if self.dry or not path.exists():
            if not path.exists():
                self.record["created"].append(str(path))
            return
        rel = str(path).lstrip("/")
        dest = self.backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, dest, symlinks=True)
        else:
            shutil.copy2(path, dest)
        self.record["backups"].append({"path": str(path), "copy": str(dest)})

    def commit(self, state: State):
        if self.dry:
            return
        state.data.setdefault("installs", []).append(self.record)
        state.data["installs"] = state.data["installs"][-10:]
        state.save()


# ---------------------------------------------------------------- upstream lock & store

def load_lock() -> dict:
    if not LOCK_PATH.exists():
        raise SystemExit(f"Missing {LOCK_PATH}. Run `lyra4d.py lock` first.")
    return load_json(LOCK_PATH, {})


def walk_tree(root: Path) -> dict:
    """Map relative path -> {"sha256"} or {"link"} for every file under root (no .git)."""
    files = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for d in list(dirnames):
            p = Path(dirpath) / d
            if p.is_symlink():
                files[str(p.relative_to(root))] = {"link": os.readlink(p)}
                dirnames.remove(d)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root))
            if p.is_symlink():
                files[rel] = {"link": os.readlink(p)}
            else:
                files[rel] = {"sha256": sha256_file(p)}
    return files


def tree_digest(files: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        v = files[rel]
        h.update(rel.encode() + b"\0" + (v.get("sha256") or ("link:" + v["link"])).encode() + b"\n")
    return h.hexdigest()


def verify_tree(root: Path, expected: dict, allow_extra: bool = False) -> list:
    problems = []
    actual = walk_tree(root)
    for rel, v in expected.items():
        a = actual.get(rel)
        if a is None:
            problems.append(f"missing {rel}")
        elif a != v:
            problems.append(f"changed {rel}")
    if not allow_extra:
        for rel in actual:
            if rel not in expected:
                problems.append(f"unexpected {rel}")
    return problems


def safe_extract(tar: tarfile.TarFile, dest: Path):
    dest = dest.resolve()
    for m in tar.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(dest) + os.sep) and target != dest:
            raise SystemExit(f"Refusing unsafe path in archive: {m.name}")
        if m.isdev() or m.isfifo():
            raise SystemExit(f"Refusing special file in archive: {m.name}")
        if m.issym() or m.islnk():
            link_target = (target.parent / m.linkname).resolve()
            if not str(link_target).startswith(str(dest)):
                raise SystemExit(f"Refusing link escaping archive: {m.name}")
    tar.extractall(dest)


def download_archive(owner_repo: str, commit: str) -> bytes:
    url = f"https://codeload.github.com/{owner_repo}/tar.gz/{commit}"
    req = urllib.request.Request(url, headers={"User-Agent": "lyra4d-installer"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def fetch_upstream(entry: dict, source_dir: Path | None = None, dry: bool = False) -> Path:
    """Return a verified store directory for one lock entry, fetching it if needed."""
    dest = store_dir() / f"{entry['name']}@{entry['commit']}"
    if dest.exists():
        problems = verify_tree(dest, entry["files"])
        if not problems:
            return dest
        warn(f"store copy of {entry['name']} failed verification ({len(problems)} issues); refetching")
        if not dry:
            shutil.rmtree(dest)
    if dry:
        say(f"would fetch {entry['repo']}@{entry['commit'][:12]}")
        return dest
    tmp = Path(tempfile.mkdtemp(prefix="lyra4d-"))
    try:
        if source_dir:
            src = Path(source_dir)
            if (src / ".git").exists():
                head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
                if head != entry["commit"]:
                    raise SystemExit(f"{src} is at {head[:12]}, lock wants {entry['commit'][:12]}")
            root = tmp / "src"
            shutil.copytree(src, root, symlinks=True, ignore=shutil.ignore_patterns(".git"))
        else:
            say(f"fetch {entry['repo']}@{entry['commit'][:12]} from codeload.github.com")
            data = download_archive(entry["repo"], entry["commit"])
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                safe_extract(tar, tmp)
            tops = [p for p in tmp.iterdir() if p.is_dir()]
            if len(tops) != 1:
                raise SystemExit("unexpected archive layout")
            root = tops[0]
        problems = verify_tree(root, entry["files"])
        if problems:
            raise SystemExit(f"{entry['repo']}@{entry['commit'][:12]} does not match the lock:\n  " + "\n  ".join(problems[:20]))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), str(dest))
        return dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_lock(specs: list, out: Path):
    """Maintainer command: pin upstreams. spec = name=owner/repo@ref[:tag]."""
    entries = []
    for spec in specs:
        name, rest = spec.split("=", 1)
        repo, ref = rest.split("@", 1)
        tmp = Path(tempfile.mkdtemp(prefix="lyra4d-lock-"))
        try:
            local = os.path.isdir(repo)
            clone_src = repo if local else f"https://github.com/{repo}.git"
            subprocess.run(["git", "clone", "-q"] + ([] if local else ["--filter=blob:none"]) + [clone_src, str(tmp / "r")], check=True)
            subprocess.run(["git", "-C", str(tmp / "r"), "checkout", "-q", ref], check=True)
            commit = subprocess.run(["git", "-C", str(tmp / "r"), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            tags = subprocess.run(["git", "-C", str(tmp / "r"), "tag", "--points-at", "HEAD"], capture_output=True, text=True).stdout.split()
            date = subprocess.run(["git", "-C", str(tmp / "r"), "log", "-1", "--format=%cI"], capture_output=True, text=True).stdout.strip()
            root = tmp / "r"
            files = walk_tree(root)
            skills = []
            for rel in sorted(files):
                if rel.endswith("/SKILL.md") and rel.startswith("skills/") and "sha256" in files[rel]:
                    fm = parse_frontmatter((root / rel).read_text(encoding="utf-8"))
                    sdir = rel[: -len("/SKILL.md")]
                    oy = root / sdir / "agents" / "openai.yaml"
                    implicit = not (oy.exists() and "allow_implicit_invocation: false" in oy.read_text(encoding="utf-8"))
                    skills.append({
                        "name": fm.get("name", Path(sdir).name),
                        "dir": sdir,
                        "user_only": fm.get("disable-model-invocation", "").lower() == "true" or not implicit,
                        "description": fm.get("description", ""),
                    })
            manifest = {}
            pj = root / ".claude-plugin" / "plugin.json"
            if pj.exists():
                manifest = json.loads(pj.read_text(encoding="utf-8"))
            lic = (root / "LICENSE").read_text(encoding="utf-8") if (root / "LICENSE").exists() else ""
            entries.append({
                "name": name,
                "repo": repo,
                "url": repo if local else f"https://github.com/{repo}",
                "commit": commit,
                "tags": tags,
                "commit_date": date,
                "license": "MIT" if lic.startswith("MIT License") else "SEE LICENSE",
                "license_copyright": next((l for l in lic.splitlines() if l.startswith("Copyright")), ""),
                "plugin_name": manifest.get("name"),
                "plugin_version": manifest.get("version"),
                "plugin_skills": manifest.get("skills"),
                "tree_digest": tree_digest(files),
                "skills": skills,
                "files": files,
            })
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    write_json(out, {"lock_version": 1, "generated": _dt.date.today().isoformat(), "upstreams": entries})
    say(f"wrote {out}")


# ---------------------------------------------------------------- exposure policy

def exposed_skills(entry: dict, opts) -> list:
    """Skill dirs (relative to repo root) that Lyra exposes to hosts by default."""
    name = entry["name"]
    out = []
    if name == "mattpocock":
        promoted = {s.lstrip("./") for s in (entry.get("plugin_skills") or [])}
        for s in entry["skills"]:
            bucket = s["dir"].split("/")[1]
            if s["dir"] in promoted or (opts.matt_extra and bucket in ("in-progress", "misc")):
                out.append(s)
    elif name == "superpowers":
        for s in entry["skills"]:
            if s["name"] == "using-superpowers" and not opts.superpowers_bootstrap:
                continue
            out.append(s)
    else:
        out = list(entry["skills"])
    return out


def files_under(entry: dict, prefix: str) -> dict:
    pre = prefix.rstrip("/") + "/"
    return {rel: v for rel, v in entry["files"].items() if rel.startswith(pre)}


def copy_rel(src_root: Path, rel: str, dst_root: Path, dst_rel: str | None = None):
    src = src_root / rel
    dst = dst_root / (dst_rel or rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_symlink():
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(os.readlink(src), dst)
    else:
        shutil.copy2(src, dst)


# ---------------------------------------------------------------- text blocks

def core_text() -> str:
    return (REPO_ROOT / "core" / "LYRA-CORE.md").read_text(encoding="utf-8")


def managed_block() -> str:
    return f"{BLOCK_BEGIN}\n{core_text().strip()}\n{BLOCK_END}\n"


def strip_block(text: str) -> str:
    pattern = re.compile(re.escape(BLOCK_BEGIN.split(" (")[0]) + r".*?" + re.escape(BLOCK_END) + r"\n?", re.S)
    return pattern.sub("", text)


def upsert_block(path: Path, sess: Session):
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    rest = strip_block(old).lstrip("\n")
    new = managed_block() + ("\n" + rest if rest else "")
    if new == old:
        say(f"ok    {path} (Lyra block current)")
        return
    sess.backup(path)
    if sess.dry:
        say(f"would write Lyra block at top of {path}")
        return
    write_text(path, new)
    say(f"wrote Lyra block at top of {path} (rest of the file kept)")


def remove_block(path: Path, sess: Session):
    if not path.exists():
        return
    old = path.read_text(encoding="utf-8")
    new = strip_block(old)
    if new == old:
        return
    sess.backup(path)
    if sess.dry:
        say(f"would remove Lyra block from {path}")
        return
    if new.strip():
        write_text(path, new.lstrip("\n"))
    else:
        path.unlink()
    say(f"removed Lyra block from {path}")


# ---------------------------------------------------------------- hook config (Codex / Gemini)

def hook_command(host: str, event: str) -> str:
    py = shlex.quote(sys.executable or "python3")
    script = shlex.quote(str(runtime_dir() / "lyra_hook.py"))
    return f"{py} {script} --host {host} --event {event}"


def strip_lyra_hooks(hooks: dict) -> dict:
    out = {}
    for event, groups in (hooks or {}).items():
        new_groups = []
        for g in groups or []:
            hs = [h for h in g.get("hooks", []) if HOOK_MARK not in str(h.get("command", ""))]
            if hs:
                ng = dict(g)
                ng["hooks"] = hs
                new_groups.append(ng)
        if new_groups:
            out[event] = new_groups
    return out


def lyra_hook_entries(host: str) -> dict:
    if host == "codex":
        return {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": hook_command("codex", "prompt"), "timeout": 10, "statusMessage": "Lyra intake"}]}],
        }
    if host == "gemini":
        return {
            "BeforeAgent": [{"matcher": "*", "hooks": [{"name": "lyra-intake", "type": "command", "command": hook_command("gemini", "prompt"), "timeout": 10000}]}],
            "AfterTool": [{"matcher": "activate_skill", "hooks": [{"name": "lyra-skill-log", "type": "command", "command": hook_command("gemini", "post-tool"), "timeout": 10000}]}],
        }
    raise ValueError(host)


def merge_hooks(existing: dict, ours: dict) -> dict:
    merged = strip_lyra_hooks(existing)
    for event, groups in ours.items():
        merged.setdefault(event, [])
        merged[event] = merged[event] + groups
    return merged


def install_hook_file(path: Path, host: str, sess: Session, container_key: str = "hooks"):
    try:
        data = load_json(path, {})
    except json.JSONDecodeError as e:
        warn(f"{path} is not plain JSON ({e}); leaving it untouched. Add the Lyra hook by hand (see README).")
        return False
    new = dict(data)
    new[container_key] = merge_hooks(data.get(container_key, {}), lyra_hook_entries(host))
    if new == data:
        say(f"ok    {path} (Lyra hook current)")
        return True
    sess.backup(path)
    if sess.dry:
        say(f"would merge Lyra hook into {path}")
        return True
    write_json(path, new)
    say(f"merged Lyra hook into {path} (other hooks kept, no duplicates)")
    return True


def remove_hook_file(path: Path, sess: Session, container_key: str = "hooks"):
    if not path.exists():
        return
    try:
        data = load_json(path, {})
    except json.JSONDecodeError:
        warn(f"{path} is not plain JSON; remove the Lyra hook entries by hand")
        return
    if container_key not in data:
        return
    stripped = strip_lyra_hooks(data[container_key])
    if stripped == data[container_key]:
        return
    sess.backup(path)
    new = dict(data)
    if stripped:
        new[container_key] = stripped
    else:
        new.pop(container_key)
    if sess.dry:
        say(f"would remove Lyra hook from {path}")
        return
    if new:
        write_json(path, new)
    else:
        path.unlink()
    say(f"removed Lyra hook from {path}")


def count_lyra_hooks(hooks: dict) -> int:
    n = 0
    for groups in (hooks or {}).values():
        for g in groups or []:
            n += sum(1 for h in g.get("hooks", []) if HOOK_MARK in str(h.get("command", "")))
    return n


# ---------------------------------------------------------------- runtime (hook + core copies)

def install_runtime(sess: Session):
    rt = runtime_dir()
    files = {
        "lyra_hook.py": REPO_ROOT / "hooks" / "lyra_hook.py",
        "core/LYRA-CORE.md": REPO_ROOT / "core" / "LYRA-CORE.md",
        "core/LYRA-TICK.md": REPO_ROOT / "core" / "LYRA-TICK.md",
    }
    if sess.dry:
        say(f"would copy hook runtime to {rt}")
        return
    for rel, src in files.items():
        dst = rt / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    say(f"ok    runtime at {rt}")


# ---------------------------------------------------------------- skills in ~/.agents/skills (Codex + Gemini)

def lyra_skill_files() -> dict:
    root = REPO_ROOT / "skills" / "lyra"
    return {p.name: p for p in sorted(root.iterdir()) if p.is_file()}


def install_agents_skills(lock: dict, stores: dict, opts, state: State, sess: Session):
    target = agents_skills_dir()
    managed = state.current.setdefault("agents_skills", {})
    wanted = {}
    for entry in lock["upstreams"]:
        for s in exposed_skills(entry, opts):
            wanted[s["name"]] = (entry, s)
    # conflicts: same skill name from two upstreams
    names = [s["name"] for e in lock["upstreams"] for s in exposed_skills(e, opts)]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        warn(f"skill names exposed by both upstreams: {sorted(dupes)}; installing the first only")
    for name, (entry, s) in sorted(wanted.items()):
        dst = target / name
        expected = {rel[len(s['dir']) + 1:]: v for rel, v in files_under(entry, s["dir"]).items()}
        if dst.exists() and name not in managed:
            if not verify_tree(dst, expected):
                managed[name] = {"source": f"{entry['name']}@{entry['commit']}", "dir": s["dir"]}
                say(f"ok    {dst} (identical copy already present, now managed)")
            else:
                warn(f"{dst} exists and is not managed by Lyra; skipped (resolve the duplicate by hand)")
            continue
        if dst.exists() and not verify_tree(dst, expected):
            continue
        if sess.dry:
            say(f"would install skill {name} -> {dst}")
            continue
        if dst.exists():
            sess.backup(dst)
            shutil.rmtree(dst)
        for rel in expected:
            copy_rel(stores[entry["name"]], f"{s['dir']}/{rel}", dst, rel)
        managed[name] = {"source": f"{entry['name']}@{entry['commit']}", "dir": s["dir"]}
    # skills we managed earlier but no longer expose
    for name in list(managed):
        if name == "lyra":
            continue
        if name not in wanted:
            dst = target / name
            if dst.exists() and not sess.dry:
                sess.backup(dst)
                shutil.rmtree(dst)
            managed.pop(name, None)
            say(f"removed skill {name} (no longer exposed)")
    # Lyra's own skill
    dst = target / "lyra"
    if dst.exists() and "lyra" not in managed:
        warn(f"{dst} exists and is not Lyra's; skipped")
    elif not sess.dry:
        dst.mkdir(parents=True, exist_ok=True)
        for fn, src in lyra_skill_files().items():
            shutil.copy2(src, dst / fn)
        managed["lyra"] = {"source": f"lyra-4d@{VERSION}", "dir": "skills/lyra"}
    say(f"ok    {len(managed)} skills managed in {target}")


def uninstall_agents_skills(lock: dict, state: State, sess: Session):
    managed = state.current.get("agents_skills", {})
    by_source = {f"{e['name']}@{e['commit']}": e for e in lock["upstreams"]}
    for name, info in list(managed.items()):
        dst = agents_skills_dir() / name
        if not dst.exists():
            managed.pop(name)
            continue
        e = by_source.get(info["source"])
        if e:
            expected = {rel[len(info['dir']) + 1:]: v for rel, v in files_under(e, info["dir"]).items()}
            if verify_tree(dst, expected):
                warn(f"{dst} was modified after install; kept (delete it by hand if you want)")
                managed.pop(name)
                continue
        if sess.dry:
            say(f"would remove {dst}")
            continue
        sess.backup(dst)
        shutil.rmtree(dst)
        managed.pop(name)
    say("removed Lyra-managed skills from ~/.agents/skills")


# ---------------------------------------------------------------- Claude Code

def find_claude() -> str | None:
    forced = os.environ.get("LYRA_CLAUDE_BIN")
    if forced:
        return None if forced == "none" else forced
    p = shutil.which("claude")
    if p:
        return p
    pats = [
        str(home() / "Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude"),
        str(home() / ".local/bin/claude"),
        str(home() / ".claude/local/claude"),
    ]
    found = sorted(set(sum((glob.glob(p) for p in pats), [])))
    return found[-1] if found else None


def run_claude(args: list, dry: bool) -> subprocess.CompletedProcess | None:
    exe = find_claude()
    if not exe:
        return None
    if dry:
        say("would run: claude " + " ".join(shlex.quote(a) for a in args))
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.run([exe] + args, capture_output=True, text=True)


def build_claude_marketplace(lock: dict, stores: dict, opts, sess: Session) -> Path:
    mp = lyra_home() / "claude-marketplace"
    plugins = []
    if sess.dry:
        say(f"would build local Claude marketplace at {mp}")
        return mp
    if mp.exists():
        shutil.rmtree(mp)
    (mp / ".claude-plugin").mkdir(parents=True)
    # Lyra plugin (generated by tools/build.py)
    shutil.copytree(REPO_ROOT / "adapters" / "claude" / "lyra-4d", mp / "plugins" / "lyra-4d")
    plugins.append({"name": "lyra-4d", "source": "./plugins/lyra-4d", "description": "Lyra 4-D intake layer"})
    for entry in lock["upstreams"]:
        st = stores[entry["name"]]
        pname = entry.get("plugin_name") or entry["name"]
        pdir = mp / "plugins" / pname
        keep = [".claude-plugin/plugin.json", "LICENSE"]
        if entry["name"] == "superpowers" and opts.superpowers_bootstrap:
            keep += list(files_under(entry, "hooks"))
        for rel in keep:
            if rel in entry["files"]:
                copy_rel(st, rel, pdir)
        promoted_dirs = []
        for s in exposed_skills(entry, opts):
            bucket = s["dir"].split("/")[1] if entry["name"] == "mattpocock" else ""
            if entry["name"] == "mattpocock" and bucket in ("in-progress", "misc"):
                continue  # goes to the -extra plugin below
            for rel in files_under(entry, s["dir"]):
                copy_rel(st, rel, pdir)
            promoted_dirs.append(s["dir"])
        plugins.append({"name": pname, "source": f"./plugins/{pname}",
                        "description": f"Verbatim files from {entry['url']} @ {entry['commit'][:12]} ({', '.join(entry['tags']) or 'untagged'})"})
        if entry["name"] == "mattpocock" and opts.matt_extra:
            xname = f"{pname}-extra"
            xdir = mp / "plugins" / xname
            extra = [s for s in exposed_skills(entry, opts) if s["dir"].split("/")[1] in ("in-progress", "misc")]
            for s in extra:
                for rel in files_under(entry, s["dir"]):
                    copy_rel(st, rel, xdir)
            copy_rel(st, "LICENSE", xdir)
            write_json(xdir / ".claude-plugin" / "plugin.json", {
                "name": xname, "version": entry.get("plugin_version") or "0.0.0",
                "description": "Non-promoted skills (in-progress, misc) from mattpocock/skills, exposed on request by Lyra 4-D.",
                "license": "MIT", "skills": ["./" + s["dir"] for s in extra]})
            plugins.append({"name": xname, "source": f"./plugins/{xname}", "description": "mattpocock in-progress + misc skills"})
    write_json(mp / ".claude-plugin" / "marketplace.json", {
        "name": MARKETPLACE_NAME,
        "owner": {"name": "Lyra 4-D local installer"},
        "description": "Generated by lyra4d.py from upstream.lock.json; do not edit.",
        "plugins": plugins,
    })
    say(f"ok    local Claude marketplace at {mp}")
    return mp


def claude_installed_plugins() -> list:
    r = run_claude(["plugin", "list", "--json"], dry=False)
    if not r or r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else data.get("plugins", [])


def plugin_id(p: dict) -> str:
    return str(p.get("id") or p.get("name") or "")


def install_claude(lock: dict, stores: dict, opts, state: State, sess: Session):
    mp = build_claude_marketplace(lock, stores, opts, sess)
    exe = find_claude()
    names = ["lyra-4d"] + [(e.get("plugin_name") or e["name"]) for e in lock["upstreams"]]
    if opts.matt_extra:
        names.append("mattpocock-skills-extra")
    if not exe:
        warn("Claude Code CLI not found. Run these in Claude Code:")
        say(f"  /plugin marketplace add {mp}")
        for n in names:
            say(f"  /plugin install {n}@{MARKETPLACE_NAME}")
        return
    installed = {plugin_id(p) for p in claude_installed_plugins()}
    for pid in sorted(installed):
        base = pid.split("@")[0]
        if base in names and not pid.endswith("@" + MARKETPLACE_NAME):
            warn(f"Claude already has {pid} from another marketplace; skills would load twice. "
                 f"Disable it with: claude plugin disable {pid}")
    r = run_claude(["plugin", "marketplace", "add", str(mp)], sess.dry)
    if r and r.returncode != 0 and "already" not in (r.stdout + r.stderr).lower():
        warn((r.stdout + r.stderr).strip())
    run_claude(["plugin", "marketplace", "update", MARKETPLACE_NAME], sess.dry)
    for n in names:
        pid = f"{n}@{MARKETPLACE_NAME}"
        if pid in installed:
            run_claude(["plugin", "uninstall", pid], sess.dry)
        r = run_claude(["plugin", "install", pid], sess.dry)
        if r and r.returncode != 0:
            warn(f"claude plugin install {pid} failed: {(r.stdout + r.stderr).strip()[:400]}")
        else:
            say(f"ok    Claude plugin {pid}")
    state.current["claude"] = {"marketplace": str(mp), "plugins": names}


def uninstall_claude(state: State, sess: Session):
    info = state.current.get("claude")
    if not info:
        return
    for n in info.get("plugins", []):
        run_claude(["plugin", "uninstall", f"{n}@{MARKETPLACE_NAME}"], sess.dry)
    run_claude(["plugin", "marketplace", "remove", MARKETPLACE_NAME], sess.dry)
    mp = Path(info.get("marketplace", ""))
    if mp.exists() and not sess.dry:
        shutil.rmtree(mp)
    state.current.pop("claude", None)
    say("removed Lyra Claude plugins and local marketplace")


# ---------------------------------------------------------------- Codex / Gemini

def install_codex(state: State, sess: Session):
    upsert_block(codex_home() / "AGENTS.md", sess)
    install_hook_file(codex_home() / "hooks.json", "codex", sess)
    state.current["codex"] = {"agents_md": str(codex_home() / "AGENTS.md"), "hooks": str(codex_home() / "hooks.json")}
    say("NOTE  Codex runs a new or changed hook only after you trust it: open /hooks in the CLI, "
        "or Settings > Hooks in the app, and trust the 'Lyra intake' hook.")


def uninstall_codex(state: State, sess: Session):
    remove_block(codex_home() / "AGENTS.md", sess)
    remove_hook_file(codex_home() / "hooks.json", sess)
    state.current.pop("codex", None)


def install_gemini(state: State, sess: Session):
    upsert_block(gemini_home() / "GEMINI.md", sess)
    ok = install_hook_file(gemini_home() / "settings.json", "gemini", sess)
    state.current["gemini"] = {"gemini_md": str(gemini_home() / "GEMINI.md"), "settings": str(gemini_home() / "settings.json"), "hook": ok}
    ext = gemini_home() / "extensions" / "superpowers"
    if ext.exists():
        warn("Gemini extension 'superpowers' is installed: its GEMINI.md loads using-superpowers every session "
             "and its skills duplicate ~/.agents/skills. Consider: gemini extensions disable superpowers")


def uninstall_gemini(state: State, sess: Session):
    remove_block(gemini_home() / "GEMINI.md", sess)
    remove_hook_file(gemini_home() / "settings.json", sess)
    state.current.pop("gemini", None)


# ---------------------------------------------------------------- commands

HOSTS = ("claude", "codex", "gemini")


def resolve_hosts(arg: str) -> list:
    if arg in ("auto", "", None):
        found = []
        if find_claude() or (home() / ".claude").exists():
            found.append("claude")
        if codex_home().exists() or shutil.which("codex"):
            found.append("codex")
        if gemini_home().exists() or shutil.which("gemini"):
            found.append("gemini")
        return found
    hosts = [h.strip() for h in arg.split(",") if h.strip()]
    bad = [h for h in hosts if h not in HOSTS]
    if bad:
        raise SystemExit(f"unknown host(s): {bad}; choose from {HOSTS}")
    return hosts


def cmd_install(opts):
    lock = load_lock()
    hosts = resolve_hosts(opts.hosts)
    say(f"Lyra 4-D {VERSION}: install for {', '.join(hosts) or 'no host found'}")
    state = State()
    sess = Session("install", opts.dry_run)
    sources = dict(s.split("=", 1) for s in (opts.source or []))
    stores = {e["name"]: fetch_upstream(e, Path(sources[e["name"]]) if e["name"] in sources else None, opts.dry_run)
              for e in lock["upstreams"]}
    for e in lock["upstreams"]:
        say(f"ok    {e['repo']}@{e['commit'][:12]} {e['tags']} verified ({len(e['files'])} files)")
    install_runtime(sess)
    if "codex" in hosts or "gemini" in hosts:
        install_agents_skills(lock, stores, opts, state, sess)
    if "claude" in hosts:
        install_claude(lock, stores, opts, state, sess)
    if "codex" in hosts:
        install_codex(state, sess)
    if "gemini" in hosts:
        install_gemini(state, sess)
    state.current["options"] = {"matt_extra": opts.matt_extra, "superpowers_bootstrap": opts.superpowers_bootstrap}
    state.current["hosts"] = sorted(set(state.current.get("hosts", [])) | set(hosts))
    state.current["lock_digest"] = sha256_bytes(LOCK_PATH.read_bytes())
    if not opts.dry_run:
        state.save()
    sess.commit(state)
    say("done. Verify with: python3 installer/lyra4d.py status")


def cmd_uninstall(opts):
    lock = load_lock()
    state = State()
    hosts = resolve_hosts(opts.hosts) if opts.hosts != "all" else list(HOSTS)
    sess = Session("uninstall", opts.dry_run)
    if "claude" in hosts:
        uninstall_claude(state, sess)
    if "codex" in hosts:
        uninstall_codex(state, sess)
    if "gemini" in hosts:
        uninstall_gemini(state, sess)
    remaining = [h for h in state.current.get("hosts", []) if h not in hosts]
    if not any(h in remaining for h in ("codex", "gemini")):
        uninstall_agents_skills(lock, state, sess)
    state.current["hosts"] = remaining
    if not remaining and not opts.dry_run:
        shutil.rmtree(runtime_dir(), ignore_errors=True)
        if opts.purge:
            shutil.rmtree(store_dir(), ignore_errors=True)
    if not opts.dry_run:
        state.save()
    sess.commit(state)
    say("uninstall done" + (" (store purged)" if opts.purge else ""))


def cmd_rollback(opts):
    state = State()
    installs = state.data.get("installs", [])
    if not installs:
        raise SystemExit("nothing to roll back")
    rec = installs[-1]
    say(f"rolling back {rec['action']} {rec['id']}")
    for b in rec.get("backups", []):
        dst, src = Path(b["path"]), Path(b["copy"])
        if opts.dry_run:
            say(f"would restore {dst}")
            continue
        if dst.exists() or dst.is_symlink():
            shutil.rmtree(dst) if dst.is_dir() and not dst.is_symlink() else dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, symlinks=True) if src.is_dir() else shutil.copy2(src, dst)
        say(f"restored {dst}")
    for c in rec.get("created", []):
        p = Path(c)
        if p.exists() and not opts.dry_run:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            say(f"removed {p}")
    if not opts.dry_run:
        installs.pop()
        state.save()
    say("Claude plugins are not rolled back automatically; re-run install or uninstall for Claude if needed.")


def cmd_verify(opts):
    lock = load_lock()
    bad = 0
    for e in lock["upstreams"]:
        d = store_dir() / f"{e['name']}@{e['commit']}"
        if not d.exists():
            say(f"--    {e['repo']}: not fetched yet")
            continue
        problems = verify_tree(d, e["files"])
        bad += len(problems)
        say(f"{'ok  ' if not problems else 'FAIL'}  store {e['repo']}@{e['commit'][:12]} {e['tree_digest'][:12]}"
            + ("" if not problems else "\n      " + "\n      ".join(problems[:20])))
    state = State()
    by_source = {f"{e['name']}@{e['commit']}": e for e in lock["upstreams"]}
    for name, info in sorted(state.current.get("agents_skills", {}).items()):
        e = by_source.get(info["source"])
        dst = agents_skills_dir() / name
        if not e:
            continue
        expected = {rel[len(info['dir']) + 1:]: v for rel, v in files_under(e, info["dir"]).items()}
        problems = verify_tree(dst, expected) if dst.exists() else ["missing"]
        bad += len(problems)
        if problems:
            say(f"FAIL  {dst}: {problems[:5]}")
    cache = home() / ".claude" / "plugins" / "cache" / MARKETPLACE_NAME
    for e in lock["upstreams"]:
        pname = e.get("plugin_name") or e["name"]
        for vdir in glob.glob(str(cache / pname / "*")):
            vd = Path(vdir)
            for rel, v in e["files"].items():
                p = vd / rel
                if p.exists() and "sha256" in v and sha256_file(p) != v["sha256"]:
                    bad += 1
                    say(f"FAIL  Claude cache {p} differs from upstream")
    say("verify: all upstream files intact" if not bad else f"verify: {bad} problem(s)")
    return 1 if bad else 0


def cmd_status(opts):
    state = State()
    cur = state.current
    say(f"Lyra 4-D {VERSION}; state {state_path()}")
    say(f"hosts installed: {cur.get('hosts', [])}; options: {cur.get('options', {})}")
    say(f"enabled: {'no (disabled flag set)' if (lyra_home() / 'disabled').exists() else 'yes'}")
    if (lyra_home() / "metrics-off").exists():
        say("metrics: off")
    # Codex
    ch = codex_home()
    hooks = load_json(ch / "hooks.json", {}) if (ch / "hooks.json").exists() else {}
    agents = (ch / "AGENTS.md").read_text(encoding="utf-8") if (ch / "AGENTS.md").exists() else ""
    say(f"codex:  AGENTS.md block={'yes' if BLOCK_END in agents else 'no'}  lyra hooks={count_lyra_hooks(hooks.get('hooks', {}))}")
    # Gemini
    gs = gemini_home() / "settings.json"
    try:
        gset = load_json(gs, {})
    except json.JSONDecodeError:
        gset = {}
    gmd = (gemini_home() / "GEMINI.md").read_text(encoding="utf-8") if (gemini_home() / "GEMINI.md").exists() else ""
    say(f"gemini: GEMINI.md block={'yes' if BLOCK_END in gmd else 'no'}  lyra hooks={count_lyra_hooks(gset.get('hooks', {}))}")
    # skills dir
    managed = cur.get("agents_skills", {})
    present = sorted(p.name for p in agents_skills_dir().iterdir()) if agents_skills_dir().exists() else []
    foreign = [p for p in present if p not in managed]
    say(f"~/.agents/skills: {len(managed)} managed by Lyra, {len(foreign)} other: {foreign[:10]}")
    # Claude
    exe = find_claude()
    if exe:
        plugins = claude_installed_plugins()
        ids = sorted(plugin_id(p) for p in plugins)
        say(f"claude: CLI {exe}")
        say(f"claude: plugins {ids}")
    else:
        say("claude: CLI not found")
    say(f"duplicate Lyra hooks: codex={max(0, count_lyra_hooks(hooks.get('hooks', {})) - 1)} gemini={max(0, count_lyra_hooks(gset.get('hooks', {})) - 2)}")


def cmd_toggle(opts, enable: bool):
    flag = lyra_home() / "disabled"
    state = State()
    sess = Session("enable" if enable else "disable", opts.dry_run)
    hosts = state.current.get("hosts", [])
    if enable:
        if flag.exists() and not opts.dry_run:
            flag.unlink()
        if "codex" in hosts:
            upsert_block(codex_home() / "AGENTS.md", sess)
        if "gemini" in hosts:
            upsert_block(gemini_home() / "GEMINI.md", sess)
        say("Lyra enabled. Claude: `claude plugin enable lyra-4d@lyra-4d-local` if you disabled the plugin.")
    else:
        if not opts.dry_run:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("disabled\n")
        if "codex" in hosts:
            remove_block(codex_home() / "AGENTS.md", sess)
        if "gemini" in hosts:
            remove_block(gemini_home() / "GEMINI.md", sess)
        say("Lyra disabled: hooks stay silent, instruction blocks removed, skills kept. "
            "Claude: also `claude plugin disable lyra-4d@lyra-4d-local` to drop the plugin entirely.")
    sess.commit(state)


def cmd_metrics(opts):
    off = lyra_home() / "metrics-off"
    if opts.action == "off":
        off.parent.mkdir(parents=True, exist_ok=True)
        off.write_text("off\n")
        say("metrics off")
        return
    if opts.action == "on":
        if off.exists():
            off.unlink()
        say("metrics on (counts only, no prompt text)")
        return
    if opts.action == "clear":
        p = lyra_home() / "metrics.jsonl"
        if p.exists():
            p.unlink()
        say("metrics cleared")
        return
    p = lyra_home() / "metrics.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    by = {}
    for r in rows:
        k = (r.get("host"), r.get("event"))
        b = by.setdefault(k, {"n": 0, "chars": 0})
        b["n"] += 1
        b["chars"] += r.get("injected_chars", 0)
    say(f"{len(rows)} events in {p}")
    for (h, ev), b in sorted(by.items()):
        avg = b["chars"] / b["n"] if b["n"] else 0
        say(f"  {h:7} {ev:14} n={b['n']:5}  injected chars total={b['chars']:8}  avg={avg:7.1f}  (~{avg / 4:5.0f} tokens)")


def cmd_diag(opts):
    p = lyra_home() / "metrics.jsonl"
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    if not rows:
        say("no hook events logged yet (or metrics off). Intake evidence: none.")
        return
    sessions = {}
    for r in rows:
        sessions.setdefault(r.get("session"), []).append(r)
    last = sorted(sessions.items(), key=lambda kv: kv[1][-1]["ts"])[-opts.sessions:]
    for sid, evs in last:
        prompts = [e for e in evs if e["event"] == "prompt"]
        starts = [e for e in evs if e["event"] == "session-start"]
        skills = [e.get("skill") for e in evs if e["event"] == "post-tool" and e.get("skill")]
        say(f"session {sid} host={evs[-1]['host']} last={evs[-1]['ts']}")
        say(f"  intake hook fired on {len(prompts)} turn(s); session-start core injections: {len(starts)}; core via hook fallback: {sum(1 for e in prompts if e.get('core_fallback'))}")
        say(f"  skills invoked (host tool evidence): {skills or 'none logged'}")
        tp = next((e.get("transcript") for e in reversed(evs) if e.get("transcript")), None)
        if tp and Path(tp).exists():
            found = sorted(set(re.findall(r'[\\/]skills[\\/]([A-Za-z0-9_.-]+)[\\/]SKILL\.md', Path(tp).read_text(errors="ignore"))))
            say(f"  SKILL.md files referenced in transcript: {found or 'none'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lyra4d.py", description="Lyra 4-D installer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--dry-run", action="store_true", help="show what would change")

    p = sub.add_parser("install", help="install or repair Lyra and the pinned upstream skills")
    p.add_argument("--hosts", default="auto", help="claude,codex,gemini or auto (default)")
    p.add_argument("--matt-extra", action="store_true", help="also expose mattpocock in-progress/ and misc/ skills")
    p.add_argument("--superpowers-bootstrap", action="store_true",
                   help="also expose using-superpowers and its SessionStart hook (Claude); not recommended with Lyra")
    p.add_argument("--source", action="append", metavar="NAME=DIR", help="use a local checkout instead of downloading (verified against the lock)")
    common(p)
    p = sub.add_parser("update", help="same as install: re-apply the current lock, keep other config")
    p.add_argument("--hosts", default="auto")
    p.add_argument("--matt-extra", action="store_true")
    p.add_argument("--superpowers-bootstrap", action="store_true")
    p.add_argument("--source", action="append", metavar="NAME=DIR")
    common(p)
    p = sub.add_parser("uninstall", help="remove Lyra hooks, blocks, plugins and managed skills")
    p.add_argument("--hosts", default="all")
    p.add_argument("--purge", action="store_true", help="also delete the downloaded upstream store")
    common(p)
    p = sub.add_parser("rollback", help="undo the most recent install/uninstall file changes")
    common(p)
    sub.add_parser("verify", help="check upstream files against the lock")
    sub.add_parser("status", help="show what is installed per host")
    p = sub.add_parser("enable")
    common(p)
    p = sub.add_parser("disable")
    common(p)
    p = sub.add_parser("metrics", help="show|on|off|clear the local hook counters")
    p.add_argument("action", nargs="?", default="show", choices=["show", "on", "off", "clear"])
    p = sub.add_parser("diag", help="show host evidence for recent sessions")
    p.add_argument("--sessions", type=int, default=3)
    p = sub.add_parser("lock", help="maintainers: pin upstreams, e.g. mattpocock=mattpocock/skills@v1.3.2")
    p.add_argument("specs", nargs="+")
    p.add_argument("--out", default=str(LOCK_PATH))

    opts = ap.parse_args(argv)
    if opts.cmd in ("install", "update"):
        if getattr(opts, "superpowers_bootstrap", False):
            warn("--superpowers-bootstrap re-enables an upstream start-up rule that runs before Lyra's intake.")
        return cmd_install(opts)
    if opts.cmd == "uninstall":
        return cmd_uninstall(opts)
    if opts.cmd == "rollback":
        return cmd_rollback(opts)
    if opts.cmd == "verify":
        return cmd_verify(opts)
    if opts.cmd == "status":
        return cmd_status(opts)
    if opts.cmd == "enable":
        return cmd_toggle(opts, True)
    if opts.cmd == "disable":
        return cmd_toggle(opts, False)
    if opts.cmd == "metrics":
        return cmd_metrics(opts)
    if opts.cmd == "diag":
        return cmd_diag(opts)
    if opts.cmd == "lock":
        return build_lock(opts.specs, Path(opts.out))


if __name__ == "__main__":
    sys.exit(main() or 0)
