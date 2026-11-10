# Idle handoff (reply to ACTIVE/IDLE ask, 2026-11-10)

Session: session_013NEJL1DTMYoLhbUX1pHGkU

## Reply at 2026-11-10T17:25:48Z UTC

IDLE (B) — lane records-gloss-link-sweep, repo shivinate7/claude-settings.
Goal: owner page pick 365 b: every record glosses its ids at first cite, and every debt links its decision (rules speak-cite-id-plus-gloss, roles-findings-are-debts-or-notes).
State: all built, reviewed and handed to runner 8 (session_013NEJL2vsmyKzJm8jUDt6za) as one batch; none merged as of 09:53 CST Nov 10. Nothing unpushed; no agents running.
PRs and heads:
- #1587 claude/records-gloss-check @ 94bea84a4: `lint/check_record_slugs.py --tree` (GLOSS001, DEBT001-004), shared `has_gloss` in lint/report_guard.py, new CI step. Review r1 FAIL, r2 PASS.
- #1621 claude/records-gloss-bare-ids @ be18e0ca3, base #1587: bare ids in prose are cites (any case); the gloss window is the paragraph (coordinator ruling 16:02 CST Nov 7). Review r1 FAIL, r2 PASS.
- #1588 claude/records-gloss-debts @ ba7636dc4; #1589 claude/records-gloss-decisions @ 5c029ae49; #1590 claude/records-gloss-rules @ 0fe5c3b4b (docs only).
Left: runner 8 merges all five together. #1587 and #1621 alone turn the new CI step red on main; with the three record PRs the tree check gives 0 findings (checked on a local merge). If main has moved, re-run `python3 lint/check_record_slugs.py --tree` on the batch and gloss any new records. Open notes (Fix: none, Until 2026-11-21): tree-check-scope-literal, quoted-gloss-not-read, underscore-italic-cite-missed, table-and-ref-link-cites. Step record requested from triage 14:51 CST Nov 7.

