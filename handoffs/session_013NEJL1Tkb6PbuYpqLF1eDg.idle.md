# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1Tkb6PbuYpqLF1eDg

## Reply at 2026-11-10T17:26:10Z UTC

IDLE (B)
Goal: lane parked-line-id-guard (roadmap step: refuse a parked line with no id at write time). Owner page comment 2026-11-03 19:26 CST.
Repo shivinate7/claude-settings, branch parked-line-id-guard, draft PR #1170, head 792cc445. Nothing is unpushed.
State: the PR has main d70ebd14 merged in. Lane lint passes, the guard mutation test kills 534 of 534 mutants, and review round 2 passed. It is handed to batch runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) and waits for its merge.
What it does: guard rule parked-line-id in hooks/question_form.py, wired in hooks/guard.py. It refuses a meta/page write whose parked list has a line with no id, a non-slug id, or a duplicate id. The id pattern lives once, in a parkId block in skills/waiting-page/page.html, which the page and the guard both read. SKILL waiting-page has a "To park a line" step. Decision record docs/decisions/parked-line-id.md. Debt note parked-id-pattern-anchors.
Left: if main moves before the merge, merge main in, rerun `merge --lane-lint 1170` and hooks/mutate_guard.py, and send the new head to the runner. The runner rebuilds docs/records.md at merge.
Notes, not debts: no test covers the page's missing-block path or the guard's re.ASCII.
My scratch worktree, /tmp/claude-0/-home-user-claude-settings/8ccd800d-6536-5890-8d8f-ce4f4165cbfa/scratchpad/plig, is detached at 792cc445 and needs no keeping.

