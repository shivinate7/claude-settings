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
  - Or a join call builds that path (lane `map11-path-joins`, 2026-11-07; anchor rule by lane orchestrator pick, 2026-11-07 15:04 CST, in review round 2). The callee is `os.path.join` or `posixpath.join` (Python, named through the file's imports), a pathlib `/` chain, or in JS `path.join`, `path.resolve`, `path.posix.join`, or a bare `join` or `resolve` imported from `path` or `node:path`. Every piece after the first argument (the anchor) is a plain string literal: no name, spread, star or substitution. A piece that starts with `/` drops a call that resets on it (`os.path.join`, `posixpath.join`, a `/` chain and `path.resolve`); `path.join` and `path.posix.join` keep it. A call with no literal after the anchor is dropped. A literal anchor is the first piece, and the joined text is tried from the test's folder, then the root. Any other anchor must name a known place of the repository, read from the test file alone. A known place is `__dirname`, or `os.path.dirname(__file__)` with `abspath` or `realpath` around either part (`posixpath` the same). It is also `Path(__file__).parent`, with more `.parent`, `.resolve()` or `.absolute()`. It is also, in JS, `__filename`, `import.meta.dirname`, `import.meta.filename`, `fileURLToPath(import.meta.url)` (`url.fileURLToPath` too), `path.dirname(...)` of any of those (a bare `dirname` from `path` too), and `fileURLToPath(new URL('<literal>', import.meta.url))`, which resolves a relative literal from the test's folder. In Python it is `os.path.normpath` of a known place, and `Path(__file__).parents[n]` with a literal `n`, which goes up `n + 1` folders (`.parent.parent` the same). The file itself is a place for a join in both languages, with one rule per language. In JS, `path.join(fileURLToPath(import.meta.url), "..", x)` names `x` beside the test, because node normalizes the join and the file name is one segment. `fileURLToPath(new URL('', import.meta.url))` is the test file, not its folder. In Python, a join from a file place (`__file__`, `abspath(__file__)`, `Path(__file__)` or a name bound to one), by `os.path.join` or a `/` chain, names nothing unless `normpath`, `abspath` or `realpath` wraps the join (lane pick, 2026-11-07 16:38 CST): both keep `..` as written, and `<file>/../x` cannot be opened. Wrapped, `..` resolves and one `..` reaches the test's folder. It is also a module-level name bound once in the file to one of those, through joins or `/` with literal pieces too (`..` included). A module-level name is a Python module-scope name or a JS top-level `const`. The join then resolves from that place only, normalized; a path outside the repository names nothing. Any other anchor names nothing. That covers an imported name, a parameter, a temp folder such as `tmp_path` or `Path(tmp_path)`, and a `mkdtemp()` or helper result. It also covers a name set in a function or a `beforeEach`, a name bound twice or shadowed anywhere in the file, a spread and a star. The match is exact, never a suffix. Named hole from anchors: none known after the Python wrap rule. A wrapped join is read as the string it makes, so a wrapper other than `normpath`, `abspath` or `realpath` (`.resolve()` on a `/` chain, say) is a miss, never a false pass. What still passes: an all-literal join tried from the test's folder or the root, which may name a root file the test never reads, as any code string may.
  - A Python import of a package loads its `__init__.py`. MAP9 `uses` facts read the same way.
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

Debts:
- `map-tested-by-no-shell` (MAP11 cannot read a shell test, so a tested-by line naming one fails).
- `map-import-alias-unread` (a test that imports by a path alias, such as `@/src/y`, fails MAP11).
- `map-py-base-name-match` (a test with stdlib `import queue` passes for a mapped `jobs/queue.py`; MAP9 shares the reader).

Kind: process
Home: skills/plain-english-map/SKILL.md
