# Handoff: lane questions-reach-page

## Goal

A question for the owner reaches the waiting page by a check, not by a promise. Incident (owner,
2026-11-01 23:26 CST): a coordinator wrote "send after 5 min" in each report from 22:25, and sent
nothing until 23:25. Lane sessions left their picks in their own chat. Cause: the report guard
(`lint/report_guard.py`) passed a reply that only named the 5-minute wait and the waiting page.

## Owner rulings

- 2026-11-01 23:31 CST, pick a (fb-2331-1): every question for the owner goes to the page writer in
  the same turn it is asked. An owner answer in chat closes the page item. No clock. This replaces the
  5-minute chat-first wait (decision questions-go-to-owner, "Chat first, then the page", 2026-10-28
  15:10 CDT).
- 2026-11-02 12:31 CST: wind down, and do not fix PR #1070 now.

## Scope set by the coordinator, not the owner

- 2026-11-01 23:34 CST: any Input Needed sentence that ends in "?" outside quotes or code counts as a
  question. Example: "Close q_max #969 as replaced by #1010?".

## Picks the lane took (each can be undone)

- A send to `@parent` passes in any session, record or not.
- Only the Input Needed item is scanned for a question.
- A peer message from the session the turn sent to is an ack, and does not start a new turn.
- An ArtifactData items write counts only when it goes to this repo's page. An agent's write never
  counts.
- A repo with no waiting page gets a systemMessage, not a block.

## State

- PR #1070, draft, "Questions reach the waiting page in the same turn they are asked".
- Branch `questions-reach-page`, head `7373ce61`. It holds main `74be1279`.
- Review: 3 rounds done. Round 3 verdict merge, net safety value positive.
- Debt filed: `lane-ack-skips-every-reply` (a lane's second question can ride on the first send).
  Three notes are in `docs/debts/notes.md`.
- The PR edits root `CLAUDE.md` (rule questions-go-to-owner) under the 23:31 ruling. The owner checks
  the wording.

## Red job

- Batch runner 7 dropped #1070 from batch 69 at 2026-11-02 12:32 CST.
- CI job `checks-mutate-guard` is red: "ERROR stale mutation, anchor text not found:
  roadmap-one-writer: a set_session_tags call on another session voids the own proof"
  (`hooks/mutate_guard.py`, about line 1996).
- Cause: PR #1095 (now on main) added that mutation, with its anchor in `hooks/guard_merge.py`. The
  merge `7373ce61` moved #1095's rule (a set_session_tags call counts only when it names the own
  session, or when its ids are unreadable) into `hooks/own_session.py`, the one home of the
  own-record read. The anchor text is no longer in `guard_merge.py`.

## Next step

1. Re-point that mutation in `hooks/mutate_guard.py` at the rule in `hooks/own_session.py`. Keep the
   same mutant. A test-author owns this edit; if the guard refuses it as product code, give it to a
   builder.
2. Run `~/.claude/bin/verdict python3 hooks/mutate_guard.py` in full. It must kill every mutant and
   find no stale anchor.
3. Run `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`. It must
   return rc 0.
4. Merge main first if it moved. A test-file conflict goes to a test-author (rule
   builders-cannot-edit-tests).
5. Send the PR number and the new head to the batch runner (list_sessions, tag
   cs-build:batch-runner, cs-repo shivinate7/claude-settings).

## Files

- `lint/report_guard.py`: `asks_a_question`, `question_problem`, `_turn_acts`.
- `lint/_transcript.py`: the send predicates, `peer_sender`, `last_incoming_index`.
- `hooks/own_session.py`: the own-record read, with the parent and #1095's rule.
- `lint/test_report_guard.py`: the cases, with `SameTurnWriter` holding the writer-send fixture.
