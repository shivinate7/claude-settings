# c186-note-sends-task

Status: reviewed and green. Draft PR #803, head 8d9a42e4. Branch c186-note-sends-task.
- A task with a note and no Mark done sends a note-only answer, with no `done`. The ready line, notice and Copy line say "note, not done". The receipt says "Not marked done." and keeps its "Note: …" line, so "Note" shows once.
- SKILL.md: a task answer with no `done` is never a grant. The session revises the item (step 4) and keeps it open.
- Review: round 1 FAIL (reviewer haiku): fixed. Round 2 PASS (reviewer sonnet). Design: one receipt FAIL in round 1, then PASS (design-reviewer opus).
- Gates on 8d9a42e4: waiting-page tests, ste-changed, check_silent_undo --strict, and ci-job checks --lint: all pass.
- Merge with c202-chat-first: clean (git merge-tree).
- Builder ran Opus, not Sonnet: it was spawned with no model, before the coordinator's 14:48 CDT rule.
Notes, not blocking:
- page.html:994: the sent panel says a blocking item "can move again once read" for any answered `holds` item. A note-only task answer, or a `none` answer, leaves the item open.
- page.html:637: the "Not marked done." receipt keeps the green done check, which means "answer sent" on every receipt.
