# Triage: notes still owed to docs/debts/notes.md on main

Checked Nov 2 12:58 CST: none of these is in docs/debts/notes.md on main. Triage writes only the roadmap branch, so the next lane that edits notes.md lands them.

- ci-gate-stale-base (orchestrator, Oct 28 07:49 CDT): the lint gate passed on c122's head 1ea8c877 but failed STE001 at docs/debts/notes.md:606 on the batch 9 tree. Cause unmeasured; one guess is a stale origin/main in the lane.
- shared-branch-stale-index (orchestrator, Oct 28 07:58 CDT): incident against rule shared-trees-one-checkout-per-agent: in c179's lane two builders shared one branch, and a stale index dropped install.sh's hunk inside d99be389; 23b4ff58 restored it.
- code-check-exclude-unchecked (c127, Oct 28 09:53 CDT, from banchi #993's review): the rule that a repo's code-check exclude holds only vendored or generated files lives only as a comment in check.yml. A debt after a real incident.
- qmax-tsc-pin-drift (c127, Oct 28 09:55 CDT): q_max pins tsc 5.8.3 while actions/code-check uses 5.9.3; they differ on one TS2322 case. A debt if they disagree on a PR.
- code-check-exclude-fork-point (c182, PR #777 round 2): the exclude list is compared against main's entries plus the fork point's, so a branch can re-add an entry main removed after the fork.
- code-check-precommit-rename (c182): in a pre-commit run, an unstaged new file makes a rename read as a plain delete; CI is not affected.
- code-check-unknown-main-noise (c182): without --main, every run prints "unknown: main"; noise only.
