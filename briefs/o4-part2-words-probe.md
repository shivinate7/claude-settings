# Brief: o4 part 2, compliance-check reports retired words (the one-time word conversion)

Repo: shivinate7/claude-settings, from main 60216ac9 (batch 13 carries o13 lane B, #780). Plan: roadmap step o4 note. One lane: builder (sonnet), then a fresh reviewer (sonnet), because a skill's behaviour changes. Reads and reports only.

## Task
1. skills/compliance-check/SKILL.md and probes.md: add a words step (or group) that lists each retired word found in a checked repo.
2. lint/compliance_probes.py: a probe that calls o13's widened glossary check (lint/check_glossary.py) and reports each hit as word, file, line. Never copy the retired list or its logic (building-one-home-per-capability); if the check cannot be called as a function or CLI, say so in the report instead of copying.
3. Then run it once on claude-settings and list each retired word it finds.

## Rulings that govern
- shiv, Oct 28 14:48 CDT (waiting-page item 49, a): the check reads the eight everyday words in paths, rule anchors and record slugs only, never in code names.
- shiv, Oct 28 16:15 CDT (item 51, a): claim, try and gap come back as plain words, "(this sense)" is restored, and one prose lane (session_013NEJL434NgJChskGXSUvAL, under o13) fixes the leftovers. So the retired list is moving: read it from the check each run, hold no list of your own, and say in the report which list state you ran against (main commit).
- compliance-check never edits a child repo and never pushes to one.

## Failure classes
- The probe holds its own copy of the retired words, so it drifts from the check.
- A word reported that the glossary has since brought back (claim, try, gap): a false alarm.
- A fixture that proves only the happy case: no red on a planted retired word.

## Check that proves it done
Red on a fixture with a planted retired word in a path, rule anchor or record slug (the probe lists word, file, line); green on a clean fixture. Run the checks through `verdict`: the skill's tests, `python3 bin/ci-job checks --lint --base origin/main` and `bin/ste-changed origin/main`; name any step red on main too.

## Report
At most 15 lines: PR (draft), head, red run, green run, review verdict, and the list of retired words found on claude-settings. Do not rebase onto main after review and do not merge.
