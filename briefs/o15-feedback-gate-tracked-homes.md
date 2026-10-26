# o15: tasks and rulings land in tracked files, not only the handoff

Cloud build thread brief. Build advisor (4), Oct 26, against claude-settings main 3b96ce8.
Base: main 3b96ce8 (or the newest main when you start); never rebase onto main after review.
claude-settings only. Push roadmap edits to the branch only; only Triage the roadmap (3) republishes.

## Rulings

- shiv, Oct 26 (page item 9, a): re-point it. Memory and handoffs hold only short-term, in-flight
  notes; decisions, debts and anything decided in a session go to tracked homes.
- Rules: output-answer-has-a-home, building-memory-is-short-term, outcomes-mechanize-rules.

## Task

Read plans/o5b-memory-hooks-audit.md on the roadmap branch (the feedback_gate and
precompact_handoff rows) first.
1. hooks/feedback_gate.py (and feedback_judge.py, local_time.py's fb capture as needed): a `task`
   item's home must be a tracked file (the repo's todo or debt store); a `ruling` item's home must be
   a decision record or a rule. The handoff no longer counts for those two kinds. `standing` and
   in-flight kinds keep the handoff. Each closed item is checked against the home it names (the file
   exists and is tracked by git).
2. hooks/precompact_handoff_prompt.md: trim the "Rulings with NO HOME YET" and "rulings with a home"
   sections to what is still in-flight. Keep branch, head, PRs, pids, ports, agents.
3. Find the repo's todo and decision homes from the layout file o2 landed (layout.json), never a
   hard-coded path. A repo with no todo home: say so in the refusal, naming the layout key.

## Failure classes and proof

- Test-author first, red on main: a ruling homed to the handoff is refused; a task homed to an
  untracked file is refused; a ruling homed to a tracked decision passes; a standing item homed to
  the handoff passes (false-alarm case); a repo with no layout file fails open with one line.
- Run every gates.yml step locally before sending (lint fixtures copy file lists; c69 not landed).
- A fresh Sonnet reviewer reads the diff (it changes a gate's verdict).

## Report

Cap 20 lines: Done, Deviations, Next. Include "Port to other repos: yes or no, and why".
Send the green, reviewed head and branch to "Advise the claude-settings build (4)"
(cmsg_01DoF7thf3iq2Srr1UsfXgh2EyHwiKacoTT56k4JHuc2RT). Keep the PR a draft. No question for shiv:
park any in the PR body.
