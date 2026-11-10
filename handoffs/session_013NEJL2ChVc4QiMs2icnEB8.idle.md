# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL2ChVc4QiMs2icnEB8

## Reply at 2026-11-10T17:26:55Z UTC

IDLE (B). Handoff for lane fix-none-cite-check:
- Goal: a `Fix: none` reason that names a commit or a cost must show the check that ran. This is step fix-none-cite-check, plus follow-up step fix-none-cite-pr-body.
- #2088: branch fix-none-cite-check-2, head 855783080. It adds the notes-side rule: `cite_problem` in lint/check_record_slugs.py and a Cite part in decision notes-name-their-fix. Merge after #1516. Fresh review chain: round 1 FAIL (haiku), round 2 FAIL (sonnet), round 3 PASS (sonnet), net value positive. Lane lint PASS. Review record posted.
- #2089: branch fix-none-cite-pr-body-2, head 044e01082. It adds the PR-body rule: the body reader plus `cite_claim` in check_record_slugs.py, `body_prose` in lint/check_silent_undo.py, and PR_BODY passed to the checks.yml step. Merge after #1969 and #2088. Round 1 FAIL (haiku), round 2 FAIL (sonnet), round 3 PASS (sonnet), net value positive. Lane lint PASS, with --lint-unknown-ok because main's ci-job lacks #1969's body expression. Review record posted.
- Both PRs are with batch runner 8 and are open and unmerged as of 09:56 CST today. Nothing is unpushed.
- Left to do:
  - Runner 8 merges #1516, then #2088, then #2089, after #1969.
  - #2089 adds `Until: 2026-11-21` to note text-rules-str-replace-unseen. Without it, #1969 and #1516 clash.
  - Once #2089 lands, the descriptions of #1651, #2006, #2010 and #2021 refuse. Triage told those lanes.
  - The cite-* notes in docs/debts/notes.md expire 2026-11-21.
- Steps filed elsewhere: record-matches-code, and red-run-pre-push (#1582).
- Handoff file: /root/.claude/handoffs/4c407888-082a-5f41-9658-3c824486fa71.md

