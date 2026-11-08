# Plan: the pointer system

A pointer is a prose cite: a line in a tracked Markdown file that names a repo path, a code name, a
script flag or a value. The check reads the code at the pull request's head. It fails the pull request
when a cite no longer matches the code. Each lane below adds one kind of cite.

## Status

- Built on main: `stale-names-bound` (STALE002, range mode), `stale-flags` (STALE007, range mode) and `value-cites` (STALE008, range mode). Tree mode, opt-in through the ste-lint input
  `tree-cites`, with the dead-path check (STALE003) and the bad-anchor check (STALE004), per decision
  `stale-cites-whole-tree` (the whole-tree record). The cited-by report, per the Report step of decision
  `stale-cites-at-merge` (the range check record).
- Planned: the route-claim check. The records-only lane for value cites landed with `value-cites`.
- New codes start at STALE005, which the route-claim check takes (decision `claims-carry-backing`, the
  route-row record). `stale-flags` is STALE007. `value-cites` took STALE008.

## Lanes

No planned lane has a slug yet.
The built lanes are `stale-names-bound`, `stale-flags`, `value-cites` and `cited-by-report`. The source notes numbered these steps L1
to L4. The slugs replace the numbers.

| Lane | What it checks | Status |
|---|---|---|
| `stale-names-bound` | A cited Python name that the pull request removed (STALE002) | Built on main |
| `stale-flags` | A cited command-line flag that the pull request removed (STALE007) | Built on main |
| `value-cites` | A cited value that the pull request changed (STALE008) | Built on main |
| `cited-by-report` | A report of the checks that hold each rule | Built on main (the Report step of decision `stale-cites-at-merge`) |
| Route-claim check (no slug yet) | A changed line that states a capability by route with no backing (STALE005) | Planned (decision `claims-carry-backing`, the route-row record) |
| Records-only lane for value cites (no slug yet) | The GLOSSARY.md row "value cite" | Built with `value-cites` |

### stale-names-bound (built on main)

- Fires when the pull request removes a module-level name that a line cites as "`file.py` `name`" or
  "(file.py name)".
- Bound names: def, class, import, and assignment to a plain name (py-facts `defined_names`). Also
  tuple, list, starred, for, with-as and walrus targets (`target_bindings`). A def directly in a
  module-level class counts. A def nested in a function does not.
- `READERS` in `lint/stale_cites.py` holds one entry per check. Each later lane adds one entry.
- Red cases: a removed module-level `X = 1` cited as "`a.py` `X`" fires. `def f` replaced by `f = h`
  does not fire. A name moved away but re-imported does not fire. A touched `.py` that removes nothing
  starts 4 git processes and reads no `.md`.
- Cost: no new process and no new file read. The decision `stale-cites-at-merge` has the full cost line.
- Known gaps: the `stale-cites-*` notes in `docs/debts/notes.md`.

### stale-flags (built on main)

- Cite: a script path and a `--flag` inside one backticked code span.
- Flag set: for a `.py` script, the `add_argument` string literals, read with `ast`. For shell, a
  whole-word token in the file.
- Fires only when the pull request removed the flag from that file.
- Red cases: a removed `--between` in a cited span fires. No fire for: a kept flag; `git push --force`;
  a flag in another script's span; a shim path (`bin/merge`, whose flags live in `merge/merge.py`).
- A flag that another touched `.py` file declares as an `add_argument` literal at head, or another touched
  `.sh` file holds as a whole word, moved there and does not fire.
- Cost: no new process beyond the one `cat-file`, and no `ls-tree` of the Markdown tree unless a flag was removed. A touched `.py`
  or `.sh` adds that `cat-file`; the flag reader reads blobs through it. The decision `stale-cites-at-merge`
  has the full cost line and the named limits.

### value-cites (built on main)

- Cite: inline `` `file: NAME = literal` `` in the map's cite grammar (MAP9) in
  `skills/plain-english-map/scripts/map-check.mjs`.
- Value: Python only, from py-facts `assigned` in `skills/plain-english-map/scripts/lib/py-facts.py`.
  JSON is not a value source (see the 20:26 CST ruling below).
- Fires when the pull request changed the value and the cite still equals the base value. Also fires
  when the pull request adds a cite line that is wrong.
- A `.mjs` value prints "unknown".
- The Python copy of the grammar has a stated reason: the action runs Python only. A parity fixture
  that both test suites read holds the two copies together.
- Red cases: 4 to 5 fires. An unchanged value does not fire. A line wrong at base and untouched does
  not fire. A new wrong line fires.
- Cost: every tracked `.md` is read only when a module-level literal changed. Else only a touched `.md` with
  an added line that cites a `.py` file is read.

### cited-by-report (built on main)

- Report only. The exit code never changes. `lint/stale_cites.py` prints to stdout, and
  `actions/ste-lint/run.sh` adds the report to the step summary.
- Anchor section: each rule anchor (`<!-- rule:id -->`) whose sentence changed between base and head
  in RULE_FILES. For each, it lists the anchor's row in `lint/rule_mechanisms.json` (kind, ref, test)
  and the files the range changed under RULE_DIRS, or "none".
- Code section: each changed code file. For each, it lists the decisions whose Home line names that
  file, and the rows whose ref or test is that file.
- A child repo with no `rule_mechanisms.json` gets the Home part only, with no error.
- Red cases: an anchor edit whose guard row is untouched names that guard. A code change lists both
  decisions whose Home names the file. A repo with no `rule_mechanisms.json` gets no anchor section and
  no error. The exit code is unchanged.
- Cost: 2 blob reads and 1 JSON read when RULE_FILES change. The Home lines of every decision record when
  code changes.
- Named readers: the lane reviewer and the batch runner.

### Records-only lane for value cites (built with `value-cites`)

- Adds the GLOSSARY.md row "value cite", whose home is decision `stale-cites-at-merge`.
- The source notes define steps L1 to L4 only. Scope and slug need a ruling.

## Rulings

The coordinator's picks live in the Scope line of decision `stale-cites-at-merge`. The two
process-only rulings live here.

- Coordinator picks, 2026-11-03 19:48 CST:
  - The planned lanes are in scope.
  - A value cite matches the code as written.
  - Python only. A JavaScript value prints "unknown".
  - The reverse list (code that nothing in prose cites) is report-only, the same form as decision
    `claude-md-change-is-flagged` (a CLAUDE.md change is reported, never held).
- Orchestrator, 2026-11-03 20:04 CST, process-only: a lone touched `.mjs` passes silently. The early
  return in `scan()` already does this in `stale-names-bound`.
- Orchestrator, 2026-11-03 20:26 CST, process-only: JSON value cites are dropped. `value-cites` reads
  Python only, so `lint/rule_audit.py` is not a value source.
