# Installers and the merge tool fall back to main when stable is missing

## The ruling

Orchestrator pick, not an owner ruling, recorded 2026-11-12 15:27 CST under R42 part 2. Installers and the merge tool run from `origin/stable` (decision `stable-branch`). When `origin/stable` is missing, they fall back to `origin/main` and print one WARN line.

State: target, not live. Installers are open pull request 2819. The stable mover is open pull request 2793. Both are open drafts. The merge tool's code is `merge/launch.py`, which runs from `origin/main` today.

- One WARN line per run, not one per call.
- The owner may overturn this pick. It is not a ruling.

Reason: a repo with no `stable` branch yet would otherwise fail to install or merge.

Kind: process
Home: docs/plans/restart-plan.md
