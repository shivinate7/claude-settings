# o8 build, lanes 1 to 3: the roadmap builder for every repo

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main 7ce2d89 (or
newer). Never rebase onto main after review. claude-settings only; read other repos, never push to
them. Push roadmap edits to the branch only; only Triage the roadmap (3) republishes.

## Contract

plans/o8-living-roadmap-plan.md on the roadmap branch (6651d48 or later), section 6, lanes 1 to 3.
Read sections 1 to 6 only. Section 7 is parked for shiv: build nothing for live worker state.

## Task: one PR, one commit per lane, in order

1. Builder takes a repo: skills/roadmap/ holds the builder (moved from the roadmap branch's
   roadmap/build.py, keeping c72's conflict-marker refusal and the c55 upkeep list), `--repo`,
   homes read through lint/layout.py, "read at" stamps, "unknown" for an unreadable home.
2. Merge marks a step: a `Step:` commit trailer marks "landed in #N"; a trailer naming no step is
   listed for triage. Triage still closes steps.
3. Records and health panels: counts, newest five, repo map from the extras file.
Leave the roadmap branch's own build.py in place; switching the branch to the skill is a later step.

## Failure classes and proof (from the plan)

- Lane 1: on claude-settings the page equals today's page apart from the stamps (diff test); a
  missing home renders "unknown" (red first).
- Lane 2: a fixture repo with one trailer commit marks only that step; a trailer naming no step is
  listed.
- Lane 3: built on banchi and q_max checkouts (read-only clones), counts equal `ls | wc -l` of
  each home.
- Run every gates.yml step locally before sending. A fresh Sonnet reviewer reads the diff.

## Report

Cap 20 lines: Done, Deviations, Next, and "Port to other repos: yes or no, and why". Send the green,
reviewed head and branch to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft.
