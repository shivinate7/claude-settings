# The map names a file's tests on a checked tested-by line

## The question

How does the shared plain-English map say which tests reach a code file, and what proves the link?

## The ruling

Lane `map-tested-by-line`, 2026-11-05. Banchi's retired `docs/map.py` held `tested_by` links on 81 records. It lost them when the file retired. The shared map had no line for them.

- **The line.** `  - Tested by: ` + test paths from the repository root, each in backticks, joined by `, `. It sits under a map line directly in `## Code files`, with no deeper heading between. A tested-by line anywhere else fails MAP11. Paths only, never registry ids: a second form would go against decision `uniform-over-variants` (a repo matches a shared format).
- **Optional.** A map line with no tested-by line passes. The line is a claim, and MAP11 checks claims only. Requiring it on every file would fail each repo's untested files.
- **MAP11.** Each named test is a tracked file and loads the mapped file:
  - It imports the file, through the import reader that MAP9 uses. A type-only import does not count.
  - Or it imports one `__init__.py` or `index.*` that re-exports the file (one hop).
  - Or a string in its code is the file's path, from the test's folder or the repository root. This covers a test that runs the file as a subprocess. Comments and docstrings never count (rule `building-scanner-respects-strings`).
  - A Python import of a package loads its `__init__.py`. MAP9 `uses` facts read the same way.
  - A shell test (`.sh`, `.bash`, `.zsh`) is read through `blankShell` (`scripts/lib/source-text.mjs`), by its words: a run between blanks and `;&|()<>` outside quotes, quote marks removed, a leading `NAME=` dropped. A comment or a heredoc body yields no word. A word with a `\`, a newline or a leading `/` is skipped. A word with no `$` counts when it is the file's path. A word with one leading variable anchor (`$NAME/` or `${NAME}/`) and a tail with no further `$` counts when the tail is the path, read from the test's folder or the root. The anchor is never resolved, and a tail with a variable counts for nothing (lane orchestrator pick, 2026-11-07 14:13 CST, the same anchor rule as branch `map11-path-joins`, which reads a path built by a join).
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

Opened: a `.sh` test that holds the path as a word without running it passes MAP11, such as `echo src/retry.py`, `[ -f src/retry.py ]`, `cat`, `grep` or `ls` on it. The reader takes a word without its command.

Debts:
- `map-import-alias-unread` (a test that imports by a path alias, such as `@/src/y`, fails MAP11).
- `map-tested-by-path-pieces` (a test that builds the path by `os.path.join` or `path.join` fails MAP11).
- `map-py-base-name-match` (a test with stdlib `import queue` passes for a mapped `jobs/queue.py`; MAP9 shares the reader).
- `map-shell-subst-in-quotes` (a shell test that runs a file inside `$(...)` in double quotes fails MAP11, a false fail).

Kind: process
Home: skills/plain-english-map/SKILL.md
