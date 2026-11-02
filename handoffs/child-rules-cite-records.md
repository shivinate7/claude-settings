# Handoff: lane child-rules-cite-records

Lane session session_013NEJL3FwFMSE67d4pu8Sz4, child of coordinator session_013NEJL2pASwRjgJDnsvnpNe. Wound down on the coordinator's instruction, owner 2026-11-02 12:31 CST.

## Goal

Owner ruling fb-1041-2, 2026-11-02 10:41 CST, "Stop rule churn and drift in the other repos":

1. A child repo's CLAUDE.md names a claude-settings record and never copies its text.
2. Several rulings on one question in one sitting are held 30 minutes, then land as one rewrite.
3. A shared check, run by child CI, refuses a CLAUDE.md line that restates a record.
4. Hand-off briefs for home, degen and ios-adblock.

## Rulings in this lane

- Orchestrator, 2026-11-02 11:20 CST: the slug-plus-ruling-time test is dropped. It refused a 495-word repo-only rule in degen that only cited its source. Only the shared-words test stays.
- Orchestrator, 2026-11-02 11:55 CST: a copy in double quotes, straight or curly, is still a copy. Code spans, headings and HTML comments stay stripped.

## State

- Branch `child-rules-cite-records`. Draft PR #1098. Read the branch head on origin; this file's commit is the last one.
- Review: round 1 asked for changes (reviewer haiku). Round 2 approved with no blocker (reviewer sonnet). The round 2 notes were fixed in commits after a80c2ee60.
- Records: decisions `child-cites-not-copies` and `rulings-land-once-per-sitting`; debts `short-copy-passes` and `record-code-spans-unindexed`; two lines in the debt notes file.
- Check: probe group `restates` in `lint/compliance_probes.py`; action `actions/claude-md-cites`.
- Briefs: `docs/plans/child-cites-briefs/home-cites-records.md`, `degen-cites-records.md`, `ios-adblock-cites-records.md`.
- Red proof, measured locally on 2026-11-02: restates refuses home CLAUDE.md:29 (28 of 43 words) and ios-adblock CLAUDE.md:5 (28 of 48 words). It passes degen and a fixed copy of home's CLAUDE.md. The child repos are private, so no child text is in the tests.

## Next

1. The round 2 fixes are on origin: test comments (5401d30f1) and the docstring (eff12ccde). The agents ran `ci-job checks --lint` and got PASS just before their last rebases. The orchestrator has not run the lane lint below on the final head.
2. Run the lane lint on the head: `~/.claude/bin/verdict ~/.claude/bin/ci-job checks --lint`, `python3 lint/check_silent_undo.py --upstream origin/main --head HEAD --strict`, `~/.claude/bin/merge --lane-lint 1098`.
3. Send batch runner 7 (session_013NEJKyjt96cx7d1uCdtb8U) and the coordinator the PR number, head and verdict "round 2 approve".
4. Triage puts the three briefs in the roadmap outbox. Each child PR needs the claude-settings merge commit of #1098 as its action pin.

## Open items

- A stray empty session, session_013NEJL2ADRZmTmGqap9Vryt, made by mistake by a record-writer agent. It has no repo and no work. The archive guard refused the archive twice, because it could not see the get_session read. Owner: coordinator.
- Not covered by the check: a reworded copy (degen CLAUDE.md:7, fixed by its brief only), and copies of root CLAUDE.md rule text.
- Agent commit trailers name Haiku or Opus. Builder agents ran Sonnet, as their spawn named it. The Opus trailer came from the brief's attribution text, not from the model that ran.
