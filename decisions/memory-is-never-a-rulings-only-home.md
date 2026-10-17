# Memory is never a ruling's only home

## The ruling

The owner's rulings must reach a tracked file. An orchestrator's auto-memory may point to a
ruling. It may never be the ruling's only home. Reason: a ruling that only memory held was lost
to the repo (`rule:building-land-design-or-abandon` had no mechanism).

`hooks/ruling_home.py`, a Stop hook, enforces it. It keys on an act, not on prose
(predicate-is-the-act).

1. It finds each memory file that this session's own tool uses wrote since the last human message:
   a Write, Edit or MultiEdit on the file, or a Bash command that names the memory folder (the
   `memory` folder beside the session's transcript).
2. The hook reads mtime only for a file that this session's own Bash command named. Such a file
   counts only when its mtime is after the last human message. A read does not change mtime, so
   it does not block. A peer session's write that this session never named does not block.
3. A Bash command names the folder when its text holds the folder's absolute path, its `~` form or
   its `$HOME` form. A write through `cd` and a relative path, a shell variable, a script or
   `python -c` is out of reach.
4. It splits each file into sections at markdown headings. A heading inside a fenced code block is
   not a heading. `MEMORY.md`, the index, is exempt.
5. Each section needs a `home:` line in its body. A line inside a fenced code block does not count.
   For the section before the first heading, a `home:` key in the frontmatter counts.
6. The value is `process-only`, or a repo-relative path to a file that the tree of some branch
   holds now. A directory, a deleted path and a path outside the repo do not count. A local branch
   that is not pushed counts.
7. A brief is not a home. A brief is not tracked.
8. The hook checks only that the value resolves. It never compares text, so a paraphrase cannot
   make it cry wolf.
9. When git cannot resolve one value, that value does not resolve. A missing git, a timeout, an
   unreadable repo or an unreadable transcript makes the hook stand down, with no block. An
   unreadable memory file is skipped; the others are still checked
   (recovery-must-not-gate-on-its-own-state).

Process state stays in memory with `home: process-only`: merge order, which agent holds which
branch, a merge approval for one act, a personal preference.

## Limits

- A Bash write that does not name the memory folder is out of reach (item 3). One rare false block
  stays: this session's Bash reads the folder while a peer session writes a file in it.
- A ruling typed in chat that nobody writes anywhere, and a cloud session with no memory folder,
  leave no act to key on.
- A `home: process-only` line can become a reflex. `lint/ruling_census.py` counts those lines.
- A promise in a record that no lane or debt owns is a different defect. It belongs in the repo's
  own record lint.

## The owner's rulings

- `rule:tokens-compacting-keep-essentials` keeps each ruling's home, not the ruling.
- "A memory entry may point to a ruling. It is never the ruling's only home." `hooks/ruling_home.py`
  enforces it, so its prose left CLAUDE.md (claude-md-shrink).
- Each answer to a question gets a home (`rule:output-answer-has-a-home`). The report is a
  scratchpad: each ruling in it moves to its decision entry or a deferred item. Nothing checks this
  rule yet.
- No standing `records/<session>` branch for the orchestrator's records, until a measure shows the
  cost of a record is the cause.
- The home for a deferred item is the `deferred/` folder, one file per item. Some repos call this
  kind "debts".
- Auto-memory stays on, as short-term notes. When a fact or ruling has a tracked home on main,
  delete its memory file and its `MEMORY.md` line (`rule:building-memory-is-short-term`).

Kind: process
Home: hooks/ruling_home.py
