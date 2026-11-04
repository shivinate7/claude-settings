# Lane handoff: merge-repo-dir-flag

Written by the lane session at wind-down, 2026-11-03, for its coordinator. This file is a snapshot: read the live PR first.

## State

- PR #1166 (draft), branch merge-repo-dir-flag, head adf07ae4. Lane lint PASS. Sent to the batch runner (claude-settings batch runner 8).
- Review: 3 rounds. Round 3 PASS (reviewer sonnet), net safety value positive.
- Source: the coordinator's lane brief after the 2026-11-03 16:15 CST incident (mailaudit #185 could not merge).

## Built

- merge/merge.py: `-C PATH` / `--repo-dir PATH` names the checkout a merge acts in. Every read uses that root. The parser is one function (build_parser), with abbreviations off.
- New guard clause merge-confirm-repo: in a cloud session, a merge-tool `--confirm` into a repo that no cs-repo tag of the session's own record names is denied. Record: docs/decisions/merge-confirm-repo.md.
- lint/workflow_steps.job_workflow: lane lint and bin/ci-job find the workflow that holds the `checks` job, whatever its file name (banchi uses check.yml).

## Rulings

- Process-only, measured 16:56 CST: a foreground `~/.claude/bin/merge N --confirm` matches the allow rule. With run_in_background, the auto-mode classifier refuses it. Home: docs/decisions/merge-confirm-repo.md, and the README and the project-ops operating model.

## Open

- A foreground Bash call has a 10-minute cap, so a merge whose CI wait runs longer is cut off in the shell. No fix proposed.
- Notes: lane lines in docs/debts/notes.md, each citing merge-confirm-repo.
