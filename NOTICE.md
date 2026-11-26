# Notices and third-party components

## This project

The files written for Lyra 4-D (installer, hook, core instructions, adapters, docs, tests) are licensed under the MIT License, see [LICENSE](LICENSE).

The original Lyra prompt (the 4-D method, BASIC/DETAIL modes, response formats and activation message) is the starting point for `core/` and `skills/lyra/`. Its activation message is reproduced verbatim in `skills/lyra/SKILL.md` as the method requires.

## Upstream skill sets (not redistributed in this repository)

This repository does **not** contain copies of the upstream skills. `installer/lyra4d.py` downloads them from the original repositories at the commits pinned in [`upstream.lock.json`](upstream.lock.json), checks every file against its SHA-256, and installs the files unchanged. The installer also places each upstream `LICENSE` file next to the installed files.

| Component | Source | Pinned | License | Copyright |
|---|---|---|---|---|
| mattpocock/skills | https://github.com/mattpocock/skills | `v1.3.2` = `d1478fcb140db0b93c0c8df17bcfd311844749d0` | MIT | Copyright (c) 2026 Matt Pocock |
| obra/superpowers | https://github.com/obra/superpowers | `v7.0.2` = `22f0b463e7a5e579904dd6211a520321035526f7` | MIT | Copyright (c) 2025 Jesse Vincent |

The full license texts are in [`third_party/`](third_party/).

What this means in practice:
- The MIT terms of each upstream apply to the upstream files on your machine. When you redistribute them (for example the ZIP files `tools/build.py --zips` creates for web uploads), keep their copyright and license notice. The ZIP builder adds `LICENSE-UPSTREAM` to each ZIP for this reason.
- The MIT license of Lyra 4-D covers only the files written for this project. It does not relicense the upstream skills.
- Upstream names (`superpowers`, `mattpocock-skills`) appear only to identify the source. This project is not affiliated with or endorsed by the upstream authors.
