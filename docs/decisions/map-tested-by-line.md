# The map names a file's tests on a checked tested-by line

## The question

How does the shared plain-English map say which tests reach a code file, and what proves the link?

## The ruling

Lane `map-tested-by-line`, 2026-11-05. Banchi's retired `docs/map.py` held `tested_by` links on 81 records. It lost them when the file retired. The shared map had no line for them.

- **The line.** `  - Tested by: ` + test paths from the repository root, each in backticks, joined by `, `. It sits under a code-file map line, like the decisions line. Paths only, never registry ids: a second form would go against decision `uniform-over-variants` (a repo matches a shared format).
- **Optional.** A map line with no tested-by line passes. The line is a claim, and MAP11 checks claims only. Requiring it on every file would fail each repo's untested files.
- **MAP11.** Each named test is a tracked file and loads the mapped file:
  - It imports the file, through the import reader that MAP9 uses. A type-only import does not count.
  - Or it imports one `__init__.py` or `index.*` that re-exports the file (one hop).
  - Or a string in its code is the file's path, from the test's folder or the repository root. This covers a test that runs the file as a subprocess. Comments and docstrings never count (rule `building-scanner-respects-strings`).
  - A test in another language, or a run with no `python3`, is an unknown read and fails.
- **No new config key.** The line names its tests.
- **Format version 5.** The step from 4 to 5 changes no file. It makes an older copy of the skill refuse the map.

## Departs from banchi

Banchi checked two things. Each id was in its harness `TESTS` registry. And the test, or a helper one level down, imported the record's top-level package. MAP11 judges each file, with one hop through a re-export. Package reach let one import vouch for a whole package. Banchi's registry check stays in banchi: no other repo has that registry.

## What it does not prove

- That the test asserts anything about the file.
- That a path named in a string is run, and not only read as data.
- That a file is untested: the old empty `tested_by: []` has no form here.

## Cost

No new process. MAP11's reads join the one `readFacts` call of a check run, so one `python3` start at most.

## Safety holes, named

Debt `map-tested-by-no-shell` (MAP11 cannot read a shell test, so a tested-by line naming one fails).

Kind: process
Home: skills/plain-english-map/SKILL.md
