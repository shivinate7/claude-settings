# c146: how banchi's docs/map.py works (ruling 26 a)

Read-only. banchi at `1523820` (main). Citations are `file:line` at that commit, with the symbol named beside each.

## Headline

**banchi's map has no fact-line syntax.** No `docs/map.py` entry cites a constant and has its value checked. The map's prose (`does`, `note`) is checked by nothing. Only its structured fields are checked: paths, status, `governed_by` ids, `tested_by` names, and full orphan coverage. The nearest working "fact line" in banchi is a separate audit row, `server concurrency` (2b below). That row is the model MAP9 should copy.

## 1. Fact syntax

- The whole file is Python literals, with no imports and no computation (`docs/map.py:39-42`, docstring "Pure literals only").
- Top-level names: `SHIPPED` (`docs/map.py:79`), `OPEN` (`:289`), `GATES` (`:329`, empty on purpose), `COMPONENTS` (`:351`), `TRACKS` (`:10532`). The `map sections` row requires each name to have a reader (`docs/map.py:20-27`; `scripts/docs_audit/env_map.py:1317` `check_map_sections`).
- The COMPONENTS field legend is at `docs/map.py:337-349`. Entry: `{"path", "status": built|stub|planned, "step", "does", "governed_by": [D<n>], "tested_by": [T<n>], "note", "modules": {name: {same keys}}}`. The first entry, `cli/`, is at `docs/map.py:352`.
- `governed_by` ⊇ the `D<n>` ids the file's own comments cite. Curated extras are allowed (`docs/map.py:34-37`).
- TRACKS row: `{"name", "owns": <path prefix>, "decisions", "rules", "status", "note"}` (`docs/map.py:10532-10547`).
- Values written in `does`/`note` prose ("887 photographs", "900 s") are unanchored. Nothing reads them back.

## 2. How values are read

- The map is never imported. `ast.parse`, then `ast.literal_eval` per module-level `Assign`. A non-literal is skipped silently (`scripts/docs_audit/core.py:652-667` `literals_from_module`; a second copy is at `scripts/decision-context.py:79-92` `literals`).
- **2a. The repo-map row** (`env_map.py:732` `check_map`, registered at `scripts/docs_audit/rows.py:211`):
  - each `governed_by` id has a heading in docs/decisions/ (`env_map.py:766-769`)
  - each `tested_by` name is in `harness/run.py:TESTS` (`env_map.py:771-786`)
  - planned-but-exists, and built-but-missing (`env_map.py:794-804`); a listed module is missing (`:819`)
  - code against map: `cited_decisions(module)` (comment regex, `env_map.py:350`) minus `governed_by` must be empty (`:824-833`)
  - orphan: a source file under an entry that the entry does not name (`:839-858`). Per its docstring (`:735-738`), this rule does most of the work.
  - SHIPPED/OPEN id invariants (`:869-895`)
- **2b. The value check (the fact-line analogue)**, outside the map: `scripts/docs_audit/code_invariants.py:1090` `check_server_concurrency`. Its table `_CONCURRENCY_FACTS` (`code_invariants.py:44-55`) has one tuple per fact: `(what, pattern-over-code, shape, anchor-over-prose, published-form)`, e.g. `REQUEST_SLOTS = <n>`. It reads the code and both prose homes, `docs/debts/` §11 and `CLAUDE.md` (`:1162-1176`), and compares them (`:1178-1235`).
  - The lesson (`:1191-1210`): a substring test passed a 15→5 timeout retune, and a word-boundary test passed two swapped constants. Only an **attributed** `NAME = value` in prose tells agreement from coincidence.
  - One fact is a name, not a number: the method that sends `Connection: close`, found by an AST walk (`_close_header_owner`; check at `:1238-1262`).

## 3. Failure text

Render: `scripts/docs_audit/core.py:262-298` (`Report.render`) prints `FAIL <row> N problems`, then each finding's `where` and its indented message. Footer: "N mechanical failures — a reference above is provably wrong. Fix the reference, or the code it points at. Do not edit a doc purely to unblock a commit" (`:291-293`). `Finding = (where, message)` (`core.py:83-85`). A row that examined nothing prints `none … examined nothing` and is not a silent pass (`core.py:270-275`).

- "`{path}` is marked planned but exists now (build-order step {n}). Update the entry to built and list its modules." `env_map.py:796-802`
- "`{path}` is marked {status} but does not exist." `:804`; "`{path}{name}` is listed but does not exist." `:819`
- "governed_by cites {D}, which has no heading in docs/decisions/." `:769`
- "tested_by cites {T}, which is not registered in harness/run.py:TESTS. …" `:776-785`
- "{file} cites {ids} in its own comments but the map does not list it under governed_by." `:828-832`
- "`{owner}{orphan}` exists but no entry describes it. Add it to modules, with what it does and what governs it." `:855-856`
- value mismatch: "{called} publishes {what} as `{NAME = said}` and `server/capture_server.py` says `{value}`. The code is the authority; the document … is now describing one that is gone." `code_invariants.py:1224-1232`
- unattributed: "{called} never attributes a value to {what}. It has to publish one as `{published}` …" `:1214-1222`
- pattern lost: "{what} no longer matches `{shape}`, so this row cannot read what §11 claims. Re-point the pattern …" `:1180-1188`

## 4. What decision-context links

`scripts/decision-context.py`: an advisory PreToolUse hook on Edit/Write (`.claude/settings.json:63`), plus `--reset` on SessionStart (`:43`). It never blocks and always exits 0 (`decision-context.py:15-18`, `:343-348`).

- file → map entry: `lookup` (`:187-217`). It takes the module entry first and falls back to the longest COMPONENTS.path prefix. It never merges the package's governed_by into a module's (`:200-204`).
- entry → decisions: `render` (`:220-263`) prints `does`, then each `governed_by` id with its title, read from the docs/decisions/ headings by `decision_gists` (`:95-150`, heading regex `:121-124`). It prints id + title only. Rulings were cut for token cost (`:221-230`).
- entry → tests: "Covered by: {tested_by}. Run `make harness`…" (`:249-251`)
- path → track: `track_for` (`:166-184`), the longest TRACKS.owns prefix. For `codes/` it adds the track's decisions file, its rules file and the C-id titles (`:252-260`).
- entry → note: "Also: {note}" (`:261-262`). It ends with a pointer to `make map ARGS="D<n> --full"` (`:263`).
- It prints once per file per session (`:23-27`). `--check <path>` previews what a file would show (`:303-307`).

## What this means for c146's plan

1. Copy the attributed form, not presence. A fact line states `SYMBOL = value`, and the check compares the value read from code with the value read from the line. banchi measured both weaker forms passing a real inversion.
2. Make "pattern lost" and "unattributed" failures of their own. They mean "cannot read the subject", which is different from "the values disagree".
3. Fail on an orphan. That is what keeps banchi's map complete. MAP9's ~6-file pilot should keep it, or gain it.
4. Never run the code being described (banchi: literal_eval, never import).
5. banchi itself has two copies of `literals` (`core.py:652`, `decision-context.py:79`). That is a small case of the t18/r5 shared-home problem.
