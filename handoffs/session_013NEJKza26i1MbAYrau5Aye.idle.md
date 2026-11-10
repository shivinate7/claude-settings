# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJKza26i1MbAYrau5Aye

## Reply at 2026-11-10T17:23:56Z UTC

IDLE (B)
Goal: roadmap step answers-write-guard. Guard rule page-answers-write refuses an ArtifactData set, update or str_replace to collection `answers`, as a single call or as a batch entry, when the url is the cwd repo's registered waiting page. Deletes, reads, other collections and the rebuild path (writes to a page not yet registered) stay allowed.
State: PR #1379 (guard refuses a session's answers write) is an open draft on branch answers-write-guard, head 798e6b01, a merge of main. It went to batch runner 8 on Nov 6. Nothing is unpushed.
Proof: 9 deny cases were red on main and are green on the branch. The new mutant is killed. Review round 1 passed (reviewer haiku), and its two findings are fixed in commit e2d06cee (mutant and two known limits).
Files: hooks/guard.py (page_answers_hit), hooks/question_form.py (call_entries, the shared entry parser, and WAITING_ANSWERS), hooks/test_guard.py (family page-answers-write; 8 bystander cases moved to groups), hooks/mutate_guard.py, docs/decisions/page-answers-write.md, skills/waiting-page/SKILL.md.
Left: (1) a batch runner merges #1379 on green CI. docs/records.md is not committed, so the merge must rebuild it; lint/test_hook_catalog.py is red until then. (2) Step page-answer-delete-guard is NOT built: the hook cannot see live item state on a delete, and the roadmap copy goes stale between page-writer runs. The step stays open and needs a design that can read the item's state.

