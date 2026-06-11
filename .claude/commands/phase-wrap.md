---
description: Finish a phase — run tests, update the phase log, commit on main
allowed-tools: Bash(pytest:*), Bash(git add:*), Bash(git commit:*), Bash(git status:*), Bash(git branch:*)
---
0. Confirm we are on `main` (`git branch --show-current`). If not, STOP and tell me.
1. Run `pytest -q`. If anything fails, STOP — do not commit.
2. Append a dated entry to docs/phase-log.md: what this phase did, key decisions and why, outputs produced (paths), open questions.
3. Show `git status` + a one-line change summary, then make ONE commit with a conventional message (e.g. `feat(engine_c): connectivity-constrained greedy seed-and-extend`). Do not push. Do not create branches.