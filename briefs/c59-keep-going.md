# c59: no session sits idle while ready work waits (parts 1 and 2)

Cloud build thread brief. Build advisor (3), Oct 26, against claude-settings main 3b96ce8.
Base: main 3b96ce8; never rebase onto main after review. Push roadmap edits to the branch only;
only "Triage the roadmap (3)" republishes the roadmap page.

## Ruling

shiv, Oct 26 (waiting page item 13, option a): parts 1 and 2 now. Part 3, a Stop check that
refuses a turn end, is built only after a repeat: do not build it.

## Task

1. Part 1, a global rule in CLAUDE.md (one anchored sentence or two, beside the roles or
   parallelism rules): when a lane ends and a queued item has every question answered, start it
   in the same turn. Stop only for an owner decision, a test only the owner can run, or the load
   brake. home-app's "Keep going" rule is the source (read /home/user/home-app/CLAUDE.md, never
   push there); say in the PR whether home-app's line can later point at the global rule.
2. Part 2, a report rule: an orchestrator's final report names the queue's ready items it left
   unstarted, with a reason per item, or "none". Put it with the reports rules
   (reports-order-of-labels family) and the shiv-stylisms output style only if that is the home
   for report shape; one home, never two.
3. Mechanize what can be checked cheaply (rule outcomes-mechanize-rules): if a lint already reads
   report shape, extend it to require the "unstarted ready items" line; if none exists, mark the
   rule NOT MECHANIZED with what a machine would need to see. Do not build a new hook.
4. Update GLOSSARY.md only if you add a term.

## Fences

- No Stop check, watcher or timer.
- Rule text in fewest words; no paragraph (rule speak-never-explain-in-paragraph).

## Failure classes and proof

- lint/rule_audit.py and the anchor checks must pass with the new anchors.
- Changes rules every session follows: a fresh Sonnet reviewer reads the diff (hunt for a
  wording that makes a session start work the owner did not approve, or that conflicts with
  questions-go-to-owner).
- ste-changed through `verdict`.

## Report

Add one line, "Port to other repos: yes or no, and why" (shiv's ruling on c52, Oct 26). Cap 15
lines: Done, Deviations, Next. Send the green, reviewed head and branch to "Advise the
claude-settings build (3)". Do not merge, and do not rebase onto main. No question for shiv:
park any in the PR body.
