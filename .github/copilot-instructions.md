# GitHub Copilot Instructions

## Required: Read This Before Every Task

Before writing, editing, or reviewing any code in this project, you must:

1. **Read the ai-standards files at `~/.github/skills/ai-standards/` first.**
   - Start with `~/.github/skills/ai-standards/SKILL.md` — it maps task types to the relevant standards and pattern files.
   - Load the files listed in the SKILL.md's "What to Load for Each Task" table before proceeding.

## Minimum Required Loads by Task

| Task | Files to load |
|---|---|
| Fixing a bug | `~/.github/skills/ai-standards/standards/general/debugging.md` |
| Writing or reviewing tests | `~/.github/skills/ai-standards/standards/general/testing.md` |
| Writing or extending Flask code | `~/.github/skills/ai-standards/standards/frameworks/flask.md` |
| Any debugging task | Check `~/.github/skills/ai-standards/patterns/debugging/` for a matching pattern first |

## Non-Negotiable Rules

- Never skip the ai-standards read, even for small tasks.
- Always cite the relevant standard when making a standards-driven decision.
- When fixing a bug, follow the full workflow in `standards/general/debugging.md`.
- When writing tests, follow `standards/general/testing.md`.
