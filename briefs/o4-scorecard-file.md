# Brief: o4, compliance-check writes its scorecard to one file

Repo: shivinate7/claude-settings, from main 43d9af20. One lane: builder (sonnet), then reviewer (sonnet). Plan: roadmap step o4 note.

## Task
1. skills/compliance-check/SKILL.md, section "4. Scorecard": the scorecard is written to one file, `docs/health/compliance.md` in the checked repo, rewritten in place on each run (no dated copies). Name its shape (rule group, score, gold-standard column, gap) so the roadmap page (o8 lane 4) can read it. Use lint/layout.json for the folder if it names a health kind; if it does not, say so in the report rather than adding a second home.
2. The skill reports the STE lint's gap on UI files (UI text the lint does not read) as a known gap in the scorecard, never by building a UI linter.
3. If the skill has a script that writes output, it writes that file; if it is prose only, the prose says so.

## Rulings
- speak-rewrite-superseded-in-place; style-table-gold-column (any comparing table carries a gold-standard column).

## Failure classes
- A scorecard written beside an old one instead of over it.
- A table with no gold-standard column.

## Check that proves it done
A test (or a compliance probe case) that is red on main (no fixed file, or no gold column) and green on the branch. `python3 bin/ci-job gates --lint --base origin/main` and `bin/ste-changed origin/main` pass (the silent-undo gitlink fixture is red on main 43d9af2 too; batch #700 fixes it).

## Report
At most 12 lines: PR (draft), head, red run, green run, review verdict. Send the green, reviewed head to the build advisor thread "Advise the claude-settings build (9)". Do not rebase onto main and do not merge.
