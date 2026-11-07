# A push beside a failed commit is refused

## The ruling

A `git push` is refused when a `git commit` sent in the same response failed or has not returned.
That push would send the head the commit was meant to fix. Rule id: `push-after-failed-commit` (deny).
The owner's typed override lets it through (`owner-override`).

| Case | Outcome |
|---|---|
| A sibling `git commit` whose tool result has `is_error: true` | deny |
| A sibling `git commit` with no tool result yet | deny |
| A sibling commit that went through | allow |
| A failed commit in an earlier response, the push in a later one | allow |
| A push alone in its response | allow |
| A failed call that is not a commit, such as `ls` or an `echo` that quotes one | allow |
| No `tool_use_id` in the payload, no record that holds it, or a transcript that cannot be read | allow |

- A sibling is an earlier `tool_use` record with the same `message.id` as the push's own record. The
  guard finds the push's record by the payload's `tool_use_id`. A probe at 14:36 CST showed the
  PreToolUse payload carries `tool_use_id` (CLI 2.1.319, headless run).
- The transcript is the payload's `transcript_path`. For a call with an `agent_id` it is
  `<transcript minus .jsonl>/subagents/agent-<agent_id>.jsonl`.
- The commit is read with `git_calls`, the same segment parser as the push path, for Bash and PowerShell.
  A `git -C dir commit` and a commit after `git add x &&` count. A quoted `git commit`, a dry run and
  `--help` do not.
- The refusal says the commit failed or has not finished, and to run the push alone in the next
  response after reading the commit's result. It names no target.

## Why not the index check

A failed `git commit -am ""` leaves nothing staged, and a clean index also reads as "nothing to
commit". The index cannot tell a commit that failed from a commit that never ran. The result of the
commit tells.

## Known false alarm

A same-response `git commit -am` with nothing to commit returns an error, so a push beside it is
refused. Cost: one retry, with the push alone.

- A call that commits, then runs a command that fails, returns an error. A push beside it is
  refused as if the commit failed.
- A failed `git -C <other repo> commit` refuses a push in this repo, because the guard does not
  compare folders.

## Misses

- A single-call chain, `git commit ...; git push`. Both run in one tool call, so no sibling record
  exists. Noted in `docs/debts/notes.md` as `push-after-failed-commit-chain-unread`.
- A commit that fails mid-call, before a command that passes, such as `git commit -m ""; git status`.
  The call's `is_error` is false. Tracked as the mid-call debt, `push-after-failed-commit-mid`.
- A commit inside `bash -c '...'`. The parser reads the quoted string as one token. Noted in
  `docs/debts/notes.md` as `push-after-failed-commit-bash-c`.
- A transcript that cannot be read, or an error in the guard's own code. The guard passes, because a
  guard defect must never brick a session.
- A commit more than 1 MiB of transcript before its push. Not seen in one response.

Cost: one bounded tail read (1 MiB) of the transcript per `git push`. No file written, no process
started. A call that is not a push never opens the transcript. `push_seq_no_open_case` in
`hooks/test_guard.py` proves that.

## The mistake

- 13:52 CST incident: a session ran `git commit` with an empty message and `git push` in parallel.
  The commit failed. The push went out with the unfixed head.

Harm: the remote and the review hold a head the session believed was fixed. Fixing it costs another
commit and push, and a bad head can reach CI.

Risk: incident (13:52 CST, parallel commit and push, empty message).

Kind: process
Home: hooks/guard_push_delete.py
