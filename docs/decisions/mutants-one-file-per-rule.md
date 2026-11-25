---
id: pending
slug: mutants-one-file-per-rule
---

# New mutant rows go in one file per rule

## The ruling

A new mutant row goes in `hooks/mutants/<rule-slug>.py`, one file per rule. The literal `MUTATIONS` table in `hooks/mutate_guard.py` takes deletes only. This is the consultant's reading of the owner's question of 2026-11-25 10:07 CST, which asked whether agents can work on one area from different angles without conflicts. It is not an owner ruling.

- Each row file defines `ROWS`, a list of 5- or 6-field tuples in the table's row shape. The file name is a rule slug. The loader does not check that the slug names a real rule.
- The loader reads each `*.py` directly in the folder, in sorted slug order. A subfolder adds no rows. A missing or empty folder leaves the list equal to the table.
- The list every reader gets is the table, then each file's rows in file order. `hooks/mutate_guard.py` rebinds `MUTATIONS` to that list before any reader uses it. So the census and the single-mutant run (`MUTATE_ONLY`) see the file rows.
- Any of these fails the run and names the file: a file that does not load, a file with no `ROWS` list, a row of the wrong shape, or a label that repeats one in the table or in an earlier file. A repeat names both places.
- A test-author writes a row file. The guard refuses a builder's write (`hooks/guard.py` `MUTANT_FILE_REL`, `is_mutation_test_rel`). A workflow step that runs a row file is a test run (`hooks/guard.py` `workflow_runs_test`), so a builder cannot delete it or make it ignore failure.

## Why and harm

Mistake, reported: two lanes each added a mutant to the one long list and conflicted when they merged main. A plan agent measured on 2026-11-25 that 4 of 56 conflicted merges of main since 2026-11-18 were in that file. No test checks this figure.

Harm: a conflict in that list stops the lane at its merge until someone resolves it by hand.

Cost: unmeasured, not pinned. The folder is listed, and each row file is compiled and run, when `mutate_guard` loads. The census loads it the same way. No process starts, and no bytecode is written beside a row file.

## Not built

- No row file exists in `hooks/mutants/` yet. The live guard on `stable` refuses a test-author's write there until the guard change is installed. The first two row files, for the guard change itself, follow in their own pull request.
- The literal table is not moved into row files. Its rows stay where they are.

## Limits

- "Deletes only" is prose. No check refuses a new row in the literal table (`lint/check_mutant_anchors.py` reads anchors only).
- The red-run trailer check (`red-run-trailer-on-test-commits`) reads only `is_test_rel`. A commit that adds a row file needs no trailer.

Check: `hooks/test_mutate_mutants.py`, run as step "Mutant folder fixture suite" of `.github/workflows/checks.yml`. Its control case pins the table with an empty folder.

Kind: process
Home: hooks/mutate_shared.py
