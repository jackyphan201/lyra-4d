# Changelog

## 0.1.1 (2026-11-27)
- DETAIL gate: the core defines "complex" (builds or changes a system, process, team or operating model; several roles, phases or deliverables; complete or end-to-end work), treats advice on building or running one as design, adds a pre-send check, and refines the host default "act when you have enough information" instead of yielding to it.
- The DETAIL message starts with a visible `Lyra · DETAIL` line, so the mode can be checked in the transcript.
- The per-turn note names the complexity signals; the hook adds one hint line when the prompt matches them (regex in memory; only `complex_hint: true/false` is logged).
- Host-provided skill kits: a routing line in the core, a `host_kits` section in the skill map, and a private overlay `~/.lyra-4d/host-kits.json` that the installer adds to installed copies only.
- The Claude hook also logs MCP tool calls (server name only, never input or output; matcher `^Skill$|^mcp__`); `lyra diag` and `lyra4d.py diag` report them.
- Examples 10 (consulting request) and 11 (domain kit with MCP); live case `9-ba-consulting`.

## 0.1.0 (2026-11-26)
- First release: Lyra 4-D core, `lyra` skill, installer for Claude Code, Codex and Gemini CLI, Project files for ChatGPT, Claude and Gemini.
- Upstreams pinned: mattpocock/skills v1.3.2 (`d1478fc`), obra/superpowers v7.0.2 (`22f0b46`).
