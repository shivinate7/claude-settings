# A spawn brief never orders a working-tree discard

## The ruling

Rule `brief-destructive-git` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a writing role whose brief orders a working-tree discard (rule `shared-trees-no-destructive-git`). Its home is `brief_destructive_hit`, called at step 9e2, after the brief-claim check at step 9e. Layer: the coordinator's lane brief, 2026-11-08 CST.

- The mistake: a lane's brief ordered an agent to run `git reset --hard` (lane reviewed-sends-back). No guard read a brief for destructive git.
- The harm: the agent obeys in a shared tree and loses another session's uncommitted work, or stalls on the shell guard's refusal and works around it.
- What is read: backtick spans, fenced lines, and lines led by `$ `. Each runs through the shell guard's own `split_segments` (`hooks/guard_core.py`) and `shared_tree_match` (`hooks/guard_shared_tree.py`), so the verb list is the shell guard's constant, never a copy (rule `building-allow-list-is-the-constant`). No subject read: a brief has no tree.
- Judged: working-tree discards only. Branch delete, worktree remove and worktree prune are left to the shell guard.
- Passes:
  - a read-only role, from `READ_ONLY` in `hooks/agent_brief.py`, plugin prefix stripped; a missing module judges every role (fail closed)
  - a segment whose `git -C` or `cd` target is under any session scratchpad (coordinator ruling, 2026-11-08 11:42 CST: mirror the shell guard's scratchpad allow)
  - a line with `Must deny:` or `Add a case:` before the span (case data)
  - a prohibition: a negator in the same clause, within 4 words before the span; `avoid` and `without` only as the word right before it; emphasis marks stripped
  - a heading with a negator then a run verb within 2 words ("Never run:") covers its bullet run, across blank lines and into a fence under it
- The override lifts it (`owner-override`).
- Accepted limits, in `docs/debts/notes.md`. A `$ ` line under "Never run:" is denied. Gerund prohibitions ("avoid running", "instead of") are denied. An earlier negated sentence on a heading line covers an order list. An unread Workflow prompt passes. Claude is unlikely to write these forms by mistake (`guard-guards-mistakes-only`).
- By design, not a limit: an order with no backticks passes here and meets the shell guard at run time.
- Cost: pure text work inside the guard call already running. No process start, no file written.

Protected by the `brief-destructive-git:` cases in `hooks/test_guard.py` (56 cases and 2 override checks), red before the rule landed, and one mutant in `hooks/mutate_guard.py`.

Kind: process
Home: hooks/guard.py
