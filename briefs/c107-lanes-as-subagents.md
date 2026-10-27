# c107 step 2: an orchestrator starts its lanes with no click from shiv

Record-writer lane, claude-settings, from main. Report cap: 20 lines.

## What is settled (local liaison, Oct 27, from the start_session contract; see c107's note)

- `start_session` with kind `offer` always waits on shiv's card.
- Kind `user_asked` starts at once, but only on a turn shiv started, for work he asked for in words.
- Kind `own_initiative` leaves a card for a week.
- On a turn started by another session's message, the app refuses a start.

So no setting removes the card. An orchestrator that starts lanes with `start_session` makes
shiv click for each one, as the degen orchestrator did on Oct 26 21:13 CDT.

## The task

Write one decision record, slug `lanes-start-as-subagents` (32 characters or fewer, `id: pending`
if the repo's records carry ids), under `docs/decisions/`, in the shape the folder's other records
use (ruling, why, limits, risk kind, cost, Kind and Plan lines). Its ruling:

1. An orchestrator starts each lane as a background Agent spawn with `isolation: 'worktree'`
   (`lanes-start-in-tool-worktrees`, lanes start only in the tool's own worktrees). This needs no click.
2. It uses `start_session` only when shiv's own message, on the current turn, asked for a
   separate session in words. Then the kind is `user_asked`. It never uses `user_asked` for work
   shiv did not ask for, and never starts a session on a turn another session's message started.
3. A lane `parallelism-keep-going` (keep going) lets start with no question is a background
   spawn, never a session.

Name the limits: a background spawn shares the orchestrator's machine and the load brake
(`machine-load-brake`); it dies with the orchestrator's session; a lane that must outlive it is
shiv's ask for a session.

Risk kind: incident (Oct 26 21:13 CDT, four accept clicks). Mechanized: no. Say what a check
would have to see (the turn's starter, which no hook payload carries).

Add the record to any index the repo keeps (`docs/catalog.md` if it lists decisions; run the
record checks). Change no code, no CLAUDE.md and no settings.

## Done when

`bin/ci-job gates --base origin/main` passes (record slug, STE lint, record shape). Commit trailers
as the project requires. Push the lane branch, send the green, reviewed head to the build advisor,
and never merge.
