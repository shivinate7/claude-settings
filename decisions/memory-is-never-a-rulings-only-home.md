# Memory is never a ruling's only home

The owner's rulings must reach a tracked file. An orchestrator's auto-memory may point to a
ruling. It may never be the ruling's only home.

## The finding

On 2026-09-24 the Banchi orchestrator ("Photo issues analysis") held owner rulings and facts in
its auto-memory handoff file and nowhere in the repo. The owner found this. The orchestrator
did not. Its own report gave six rows:

| Row | Item | Where it lived | In the repo? |
|---|---|---|---|
| 1 | Owner ruling on Review search: show all matched rows, or "show 10 more" | memory, a worker's brief | No, until the owner asked |
| 2 | The live migration's result counts | memory, the chat report | No, until the owner asked |
| 3 | D258's promise that `set_state` "waits on a later lane" | the decision entry | Yes, but no lane or debt owns it |
| 4 | The owner's request to turn more presses into icons | memory ("queued") | No |
| 5 | The owner's iconography ruling | another session's scratchpad | Only after a "records lane" |
| 6 | "Listed as / Read as" | the spec | Yes, because a lane's brief carried it |

The pattern: a ruling reached the repo when a worker's brief told the worker to write it
down. A ruling that the orchestrator only noted went to memory and stayed there.

`rule:building-land-design-or-abandon` already forbids this: "A design living only in chat is
not done." It had no mechanism.

## How often: the census, 2026-09-25

The owner ran `lint/ruling_census.py` on the machine that holds the transcripts. Totals:

| Count | Value |
|---|---|
| Worker transcripts | 1,079 |
| Answers to questions | 3,185 |
| Memory writes | 37 |
| Scratchpad writes | 3,008 |
| Lines that say "ruling" | 1,073 |
| `home: process-only` lines | 0 |
| Reach: found in the repo | 7 |
| Reach: not found | 762 |
| Reach: unknown | 1,175 |

The largest project is the old iCloud pkmnscan path: 52 sessions, 379 answers and 58
"ruling" lines.

What the numbers show:

- **Memory is a small channel.** There are 37 memory writes against 3,185 answers. The hook
  guards the channel that leaked in Banchi, but most rulings never pass through memory.
- **Chat answers are the large channel.** `rule:output-answer-has-a-home` covers them. It has
  no mechanism yet.
- **The reach ratio undercounts.** The reach test takes only items of 8 words or more. Most
  answers are an option label, and a label is never in a repo word for word, even when the
  ruling landed. So 7 found against 762 not found measures verbatim reach, not loss.
- **Unknown is mostly old paths.** The census cannot open a repo at a path that moved, such
  as the old iCloud path. It counts those items as unknown, never as lost.
- **Zero process-only lines is expected.** The hook merged on 2026-09-25. It was not installed
  on that machine when the census ran.

So the rate of loss is still unmeasured. The census measured the size of each channel. A
measure of loss needs a judged sample: pick answers, and read whether each ruling reached a
tracked file in any words.

On 2026-09-25 the owner chose the judged sample as the next step, before any answer check is
built. `lint/ruling_census.py --sample` prints a sample of answers, with the question, the
repo and the date. The owner runs it and hands the output over. The output stays out of the
repo, because a transcript can hold private text. A Sonnet lane then judges each answer
against the repo it names.

## The causes

1. **Memory costs nothing, and nothing checks it.** A worker's only lasting output is a commit,
   and a reviewer reads it. The orchestrator can write memory with no branch, no PR and no CI
   wait. Nobody reviews what it chose not to write. This cause carries the most weight.
2. **The global CLAUDE.md names context as a home for rulings.**
   `rule:tokens-compacting-keep-essentials` says "When compacting, keep the files, the
   commands, and the rulings." It tells the orchestrator to keep a ruling in context. It does
   not tell it to write the ruling down.
3. **A cloud session has no auto-memory.** The same defect then takes a second form: the
   ruling lives only in chat or in a PR body.
4. **No rule names the branch for a record.** The orchestrator "writes records". In a PR-only
   repo each record is a commit on a branch. Nothing says which branch, or when.

## The mechanism

`hooks/ruling_home.py`, a Stop hook. It keys on an act, not on prose, as
`decisions/predicate-is-the-act.md` requires.

1. It finds each memory file that this session's own tool uses wrote since the last human
   message. That is a Write, Edit or MultiEdit on the file, or a Bash command that names the
   memory folder. The memory folder is the `memory` folder beside the session's own
   transcript.
2. All sessions of one project share the memory folder. So the hook reads mtime only for a
   file that this session's own Bash command named. Such a file counts only when its mtime is
   after the last human message. A read does not change mtime, so a Bash read does not block.
   A peer session's write that this session never named does not block.
3. A Bash command names the folder when its text holds the folder's absolute path, its `~`
   form or its `$HOME` form. A write through `cd` and a relative path, a shell variable, a
   script or `python -c` is out of reach. The hook does not catch it.
4. It splits each file into sections at its markdown headings. A heading inside a fenced code
   block is not a heading. `MEMORY.md`, the index, is exempt.
5. Each section must carry a `home:` line in its body. A line inside a fenced code block does
   not count. For the section before the first heading, a `home:` key in the frontmatter also
   counts.
6. The value is `process-only`, or a repo-relative path to a file that the tree of some
   branch holds now. A directory does not count. A local branch that is not pushed counts. A deleted path does not count. A path that
   leaves the repo does not count.
7. A brief does not count. A brief is not tracked, and Row 1 below lived in a brief and still
   did not reach the repo.
8. The hook checks only that the value resolves. It never compares text, so a paraphrase
   cannot make it cry wolf.
9. When git cannot resolve one value, that value does not resolve. A missing git, a timeout,
   a repo that git cannot read or an unreadable transcript makes the hook stand down, with no
   block. A memory file that the hook cannot read is skipped, and the other files are still
   checked. A control must not depend on the state it checks
   (`decisions/recovery-must-not-gate-on-its-own-state.md`).

Process state stays in memory by design, with `home: process-only`. This covers merge order,
which agent holds which branch, a merge approval for one act, and a personal preference.

## What the mechanism covers, and what it does not

- Rows 1, 2 and 4 are memory writes. The hook catches each one. Row 1's brief is not a home,
  so the hook catches Row 1 too.
- Row 6 is the correct case. The hook stays silent.
- Row 3 is a different defect: a promise in a record that no lane or debt owns. That check
  belongs in Banchi's own record lint. This change does not touch Banchi.
- Row 5 is a scratchpad write. The census counts scratchpad writes first, in worker
  transcripts too. It counts writes, not reads. A check follows only if the count shows the
  need.
- A Bash write that does not name the memory folder is out of reach (mechanism item 3). One
  rare false block stays: this session's Bash command reads the folder while a peer session
  writes a file in it.
- A memory write that this session did not make is out of scope. A peer session's hook checks
  its own writes.
- A ruling typed in chat that nobody writes anywhere leaves no act to key on. A cloud session
  with no memory folder is the same case. The hook does not catch either one.
- An AskUserQuestion answer is a ruling with a clear act. A check for it needs a place in the
  report for each answer's home. That changes `rule:reports-order-of-labels`, so it waits for
  the owner's word.

## Known risk

A `home: process-only` line can become a reflex. The census counts `process-only` lines, so a
reader can see if the label hides rulings.

## The owner's rulings, 2026-09-25

These change CLAUDE.md text. The owner answered each one:

- Reword `rule:tokens-compacting-keep-essentials` to keep each ruling's home, not the ruling.
  Adopted.
- Add the rule "A memory entry may point to a ruling. It is never the ruling's only home."
  Adopted, as `rule:building-memory-never-only-home`. `hooks/ruling_home.py` is its
  mechanism.
- Give each answer to a question a home. Adopted, as `rule:output-answer-has-a-home`. In the
  owner's view, the report is a scratchpad. Each ruling in it moves to its real home, a
  decision entry or a deferred item. Nothing checks this rule yet.
- A standing `records/<session>` branch for the orchestrator's records. Not yet. This
  session landed each record on a work branch with no trouble. The census must first show
  that the cost of a record is the real cause.

The owner also named the home for a deferred item: the `deferred/` folder, one file per item.
Some repos call this kind "debts".
