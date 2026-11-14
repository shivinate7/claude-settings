# The batch runner's working state lives in one file on the record branch, sent by message to triage

## The ruling

The batch runner's working state (merge queue order, folds and their members, gos, holds with their end events, archive pass) lives in one file, `plans/runner-state.json` on branch `roadmap`. The runner cannot push to that branch, and it gets no push access: triage is the one writer (decision `session-tiers`, rule `roadmap-one-writer`). After each merge the runner sends triage one message, `RUNNER-STATE <owner/repo> v<N> after merge #<PR>`, then the whole file as JSON. Triage checks it with `skills/project-ops/scripts/check_runner_state.py message <file> <committed file>`, which also refuses a message that is not the next version after the committed file or that leaves the merged PR in the queue (so a runner that lost its state cannot overwrite the live file). Triage commits it whole, pushes it, and answers with the commit. The runner reads the answer before its next merge. At start and after each compaction the runner reads `git show origin/roadmap:plans/runner-state.json` first. Its handoff holds one line, `Runner state: origin/roadmap:plans/runner-state.json, last sent version <N>.`, and never the list (handoff prompt, step 4).

Sources: owner ruling `own-runner-handoff-resilient` (22:47 CST, 2026-11-13; relayed by the consultant; the batch runner seemed to have no memory after a compaction); the coordinator's pick of the message route, 22:59 CST (undoable; a push grant would widen what a session may write and needs the owner).

## Past rulings read, and none contradicted

- Decision `session-tiers`: "Triage is the only writer of the roadmap" (owner, 2026-10-28), and "Not built: the route from a lane to triage". This ruling builds that route for the runner. The writer stays triage.
- Guard rule `roadmap-one-writer` (incident, lane commit 87a9d9c9, 2026-11-01): it denies a push to the record branch from any session but triage. The route adds no push, so the guard is untouched.
- Decision `standing-merge-grant`: the runner merges; it holds no write grant on the record branch. Unchanged.
- Decision `precompact-handoff`: not edited. Only the prompt text `hooks/precompact_handoff_prompt.md` gains one line, which the lane `handoff-written-by-hook` leaves alone (it edits `hooks/precompact_handoff.py`).

## The fields

`schema` (1), `repo`, `version` (one higher at each send), `writtenAt` (zoned time), `runner` (session id), `afterMerge` (`pr`, `commit`), `queue` (rows of `pr`, `head`, `path`: `alone` or `fold:<id>`), `folds` (`id`, `pr`, `base`, `members`), `gos` (`pr`, `by`, `at`), `holds` (`pr`, `reason`, `endsOn`: the named event that ends it), `archivePass` (`lastRunAt`, `pending`). A hold with no end event is refused. The seed is `skills/project-ops/templates/runner-state.json`; triage commits the first copy.

## The check

- Red first: `skills/project-ops/tests/test_runner_state.py` failed on main with the check missing (verdict log recorded in the PR), then went green.
- A compaction case drops everything but the handoff, and the successor rebuilds every field from the file alone. A committed version older than the last sent one reads as stale (the runner resends). An unreadable or invalid file reads as unknown, never empty. The handoff holding a list copy is refused.

## Cost

- One message per merge, and one triage commit per message. No timer, no process, no log. The runner reads the file at start and after a compaction only.
- Ceiling: the file is as fresh as the last message. A merge whose message was lost leaves the file one merge behind. The runner reads triage's answer before the next merge, so a lost message shows at once. After a compaction, a committed version below the last sent one reads as stale: the successor rebuilds the missing merge from main's log since the file's `afterMerge.commit` and sends the next version.
- Writers and readers: the runner writes the message and triage reads it; triage writes the file and the runner reads it at start and after each compaction; the runner writes the handoff pointer and its successor reads it.

Kind: process
Home: skills/project-ops/scripts/check_runner_state.py
