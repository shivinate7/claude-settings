# Memory is never a ruling's only home

## The ruling

The owner's rulings must reach a tracked file. An orchestrator's auto-memory may point to a
ruling. It may never be the ruling's only home. Reason: a ruling that only memory held was lost
to the repo (`rule:building-land-design-or-abandon` had no mechanism).

`hooks/ruling_home.py`, a Stop hook, enforces it. It keys on an act, not on prose
(predicate-is-the-act).

- Each section of a memory file that this session wrote needs a `home:` line. The value is
  `process-only`, or a repo-relative path to a file that the tree of some branch holds now. A brief is
  not a home, because it is not tracked. `MEMORY.md`, the index, is exempt.
- The hook checks only that the value resolves. It never compares text, so a paraphrase cannot
  make it cry wolf.
- When git or the transcript cannot be read, the hook stands down with no refusal
  (recovery-independent-of-state).

Process state stays in memory with `home: process-only`: merge order, which agent holds which
branch, a merge grant for one act, a personal preference. `lint/ruling_census.py` counts those lines.

## The owner's rulings

- `rule:tokens-compacting-keep-essentials` keeps each ruling's home, not the ruling.
- "A memory entry may point to a ruling. It is never the ruling's only home." `hooks/ruling_home.py`
  enforces it, so its prose left CLAUDE.md (claude-md-shrink).
- Each answer to a question gets a home (`rule:output-answer-has-a-home`). The report is a
  scratchpad: each ruling in it moves to its decision or a debt's Ruling section.
- No standing `records/<session>` branch for the orchestrator's records, until a measure shows the
  cost of a record is the cause.
- `docs/debts/` is the one home for deferred work, one file per item (owner, 2026-10-17 23:46 CDT). The question reviewer hook judges the box alone and does not read `docs/debts/` (`question-reviewer-agent-hook`, one Opus agent hook on each question).
- Auto-memory stays on, as short-term notes. When a fact or ruling has a tracked home on main,
  delete its memory file and its `MEMORY.md` line (`rule:building-memory-is-short-term`).

Kind: process
Home: hooks/ruling_home.py
