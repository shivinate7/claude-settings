# A spawn brief never orders a working-tree discard

## The ruling

Rule `brief-destructive-git` in `hooks/guard.py` refuses an Agent, Task or Workflow spawn to a writing role whose brief orders a working-tree discard (rule `shared-trees-no-destructive-git`). Read-only roles pass; the rule judges writing roles. Its home is `brief_destructive_hit`, called at step 9e2, after the brief-claim check at step 9e. Layer: the coordinator's lane brief, 2026-11-08 CST.

- The mistake: a lane's brief ordered an agent to run `git reset --hard` (lane reviewed-sends-back). No guard read a brief for destructive git.
- The false alarms: the rule refused briefs that only forbade or reported an act. Measured on 2026-11-25 at 08:40 CST by a grep of guard.log: six refusals of that kind, two logged as false alarms.
- The harm: the agent obeys in a shared tree and loses another session's uncommitted work, or stalls on the shell guard's refusal and works around it.
- What is read: backtick spans, fenced lines, and lines led by `$ `. Each runs through the shell guard's own `split_segments` (`hooks/guard_core.py`) and `shared_tree_match` (`hooks/guard_shared_tree.py`), so the verb list is the shell guard's constant, never a copy (rule `building-allow-list-is-the-constant`). No subject read: a brief has no tree.
- Each Workflow `agent()` call is read for its prompt and `agentType`, whatever its model. An unread `agentType` is judged as a writing role. An unread prompt passes.
- Judged: working-tree discards only. Branch delete, worktree remove and worktree prune are left to the shell guard.
- Passes:
  - a read-only role, from `READ_ONLY` in `hooks/agent_brief.py`, plugin prefix stripped; a missing module judges every role (fail closed)
  - a segment whose `git -C` or `cd` target is under any session scratchpad (coordinator ruling, 2026-11-08 11:42 CST: mirror the shell guard's scratchpad allow)
  - a line with `Must deny:` or `Add a case:` before the span (case data)
  - a prohibition: the clause before the span ends in a negator and a run verb ("Never run", "Do not use", "You cannot run"), or in `avoid`, `without` or `no`; a span it covers must be a list of git commands; emphasis marks stripped
  - each later span of a prohibition list, where a comma joins two spans ("Never run `a`, `b`, or `c`.")
  - a heading with a negator then a run verb within 2 words ("Never run:") covers its bullet run, across blank lines and into a fence under it
  - a backtick span that is, whole, a negator, a run verb and a list of git commands (items joined only by commas, or, and, nor; one final period)
  - a backtick span of `git` and one subcommand word, followed directly by "-free"
  - a backtick span reported as done: the clause before it is, whole, an optional article, one to three words naming who acted, and "ran", "had run" or "has run"; a clause that opens with a condition or instruction word (if, once, then, now, make, ensure) or holds "you" is no report
- The override lifts it (`owner-override`).
- Accepted limits, in `docs/debts/notes.md`. A `$ ` line under "Never run:" is denied. Gerund prohibitions ("avoid running", "instead of") are denied. An earlier negated sentence on a heading line covers an order list. An unread Workflow prompt passes. A list with an aside between spans is denied at the later span. The window crosses a colon. A `~~~` fence is not read. A case-data marker exempts the rest of its line. Claude is unlikely to write these forms by mistake (`guard-guards-mistakes-only`).
- By design, not a limit: an order with no backticks passes here and meets the shell guard at run time.
- Each pass above is a whole-shape match, so a pass never reads one word and skips the rest of the span or clause. Known limits, each refused as an order: any other wording that only names the act; a prohibition with words between the negator and the run verb ("Never, under any circumstance, run"); a prohibited span with a shell joiner or a plain word list that is not git commands (`cd x && git reset --hard`). A negator outside the span that negates another act ("Do not hesitate to" then a span) is now refused too.
- Cost: pure text work inside the guard call already running. No process start, no file written.

Protected by the `rule9` test family under `tests/guard/` (80 `brief-destructive-git:` cases and 2 override checks, counted 2026-11-25), red before the rule landed, and one mutant in `hooks/mutate_guard.py`.

Kind: process
Home: hooks/guard.py
