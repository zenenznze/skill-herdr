# Herdr Agent skill

Public source-only snapshot of the author's Herdr operation/configuration skill used as design evidence for [ultra-build](https://github.com/zenenznze/ultra-build). Pinned source commit: `3908c6513844c4191a934cd0e3094ebfb9644633`.

The skill provides explicit workspace/tab/pane operations, bounded Agent interaction, per-directory sessions and optional shell wrappers. It is not the Herdr terminal application.

## Install and use

Clone `https://github.com/zenenznze/skill-herdr.git`, then expose its root `SKILL.md` in your Agent client's skill directory. Install [herdrdev/herdr](https://github.com/herdrdev/herdr) separately; its own Apache-2.0 license applies to that upstream application. Read `SKILL.md` and the relevant `modules/*/MODULE.md` before use. Resolve the external `asm` freshness gate placeholder to your environment; ASM is not bundled.

Control commands require `HERDR_ENV=1`. Optional `install.sh` modifies shell configuration and installs wrappers: review it and back up configuration before explicitly running it. Public release verification runs isolated mock tests only, not installation into the user's home or live pane operations.

## Scope and licensing

Author-owned skill/scripts/configuration: MIT (`LICENSE`). Herdr application: external Apache-2.0 dependency, **not redistributed here**. CLI integration does not relicense Herdr.

Private history, process/handoff documents, feedback reports, machine-specific freeze/shell-recovery scripts and LightOS WebShell patches are excluded. WebShell patches referenced in the development source are **not shipped** because their redistribution boundary was not established here. This repository is a curated reference snapshot, not a full mirror or live-backend compatibility guarantee.
