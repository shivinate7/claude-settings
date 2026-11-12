# Brief: questions-reach-page

The coordinator sent this brief to the real lane. The text is word for word, so it sits in a code block.

```text
Lane brief: questions-reach-page. You are a lane session (one lane, Opus). Coordinator: session_013NEJL2pASwRjgJDnsvnpNe. Batch runner 7: session_013NEJKyjt96cx7d1uCdtb8U. Page writer (triage 5): by role: triage, see the roster in CLAUDE.md on the roadmap branch.

Incident (owner, 2026-11-01 23:26 CST): "this problem needs to be solved. along with that, tons of sessions have questions in their own and arent making it to the artifact. not sure how after it working for so long the ball got dropped without anything catching it except me".
What happened: the coordinator asked 5+ questions in chat from 22:25 on, wrote "send to triage after 5 min" in each report, and sent none until 23:25. Lane sessions put picks under Input Needed in their own chat; nothing forwarded them to the coordinator or the page writer.
Cause (read): lint/report_guard.py's pick guard passes when the reply only NAMES the 5-minute wait and the waiting page (PAGE_WORDS_RE, the clause after decisions-reach-a-clickable-pick). A promise satisfies it. Nothing later checks that the question was sent. Rule questions-go-to-owner and skill waiting-page say "no timer counts the 5 minutes; at each wake check the age" — prose only.

Task: make a question reach the page by mechanism, not promise. Keep chat-first (decision questions-go-to-owner, "Chat first, then the page") as the default behaviour.
1. Owner-facing session (one whose turns the owner types in): at Stop, record each open pick from Input Needed (session, time, text hash) in a per-session state file. At each later Stop, block when an item is older than 5 minutes, the owner has typed no message since it was asked, and the session has not sent it to the page writer (send_message to the writer named in layout meta/page, or an ArtifactData write to the page). The block names the item and the writer. An owner chat answer to the item, or a send to the writer, clears it. Decide and state how an owner message counts as answering; if a choice departs from the ruling, write it as a "Departs from:" question in your report, not a guess.
2. Lane session (tag cs-build:lane, or a parent_session_id): at Stop, a reply whose Input Needed offers a pick blocks unless the same turn sent it by send_message to the parent or the page writer. A lane's own chat is not a route to the owner.
3. Find where the hook reads session tags and parent today (session_start.sh, guard_core, local_time) and reuse that home. One home per capability.
Governing: questions-go-to-owner, decisions-reach-a-clickable-pick, outcomes-mechanize-rules (reads on demand inside a hook already running; state cost in the record: files written, how often; a test proves it), building-guard-needs-incident (this is a named incident; record it with the date), verification-trust-guard-after-red.
Failure classes: false alarm on a reply that only mentions a past question; a box question (AskUserQuestion) counted as unsent; a question re-blocked after it was sent; a session with no layout (no page) blocked with no way out — then it fails open and says so.
Done check: test-author writes red cases first (hooks/test_*.py or lint/test_report_guard.py), shows them red on main 49a41651; builder makes them green; P9 lane lint green: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint` and `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`. Update decision questions-go-to-owner and skill waiting-page in place to name the mechanism.
Models per agent-model-cap. No EnterWorktree, confirm_repository_trust, request_computer_folder or create_session. Never write the roadmap. Open a draft PR; send its number and head to batch runner 7 and to me. Report cap 20 lines, plus one Lessons line.
```

Note (Nov 12, 2026): the triage session id in the block was replaced by its role (restart-plan R22 point 3, which says a brief names a role, never a session id). The other ids in the block are the old respawn's and are not changed here.
