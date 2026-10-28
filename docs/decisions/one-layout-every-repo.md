# One layout for every repo

## The ruling

Every repo keeps each kind of file in the same place. One file in claude-settings, `lint/layout.json`,
names each place. Every shared tool reads its paths from that file through `lint/layout.py`. No tool
holds a record path of its own.

Three questions place a file:

1. Is it current truth or history? Git keeps history. A repo has no history folder (`FORMER/`,
   `RETIRED/`, `archive/`).
2. Does it die when its work ships? A plan dies. A spec stays.
3. Does every repo have one? Then it is a core kind. Only repos with screens have a screen kind. Only
   one repo has an extra kind.

The layout:

- Core, every repo: `CLAUDE.md`; `AGENTS.md`, a symlink to `CLAUDE.md`; `.claude/rules/`;
  `docs/decisions/`; `docs/debts/` with `README.md` and `notes.md`; `docs/plans/`, each plan deleted
  when its work ships; `docs/specs/`, how a shipped feature works now; `docs/records.md`, generated.
  Also `docs/todo.md`, the tasks a session catches.
- Repos with screens add: `docs/design/` (`DESIGN.md`, `mockups/`, `reference/`); `tokens/tokens.json`;
  `shots/`, ignored by git.
- A repo names its own extra kinds (home's `records/`) in its extras file, `.claude/layout-extras.json`.
  An extra kind never replaces a core or screen kind. The extras file also marks the repo as rolled out.

A repo that has not rolled out is read at its legacy folders, the ones each tool read before the
layout. So no tool changes its verdict on a repo before that repo moves its own files. A kind that one
repo keeps in a place of its own (q_max's `specs/todo.md`) is read there until that repo moves it.
The layout's `legacy-repos` map holds that place, keyed by the repo's GitHub name. A rolled-out repo's extras
file may repeat a path that map keeps for the kind, never name another. The last roll-out deletes both legacy maps.

- Owner ruling, 2026-10-22: the same folders in every repo, not a per-repo declaration.
- Owner ruling, 2026-10-17: claude-settings moves first. Each child repo moves in its own roll-out.
- Owner ruling, 2026-10-20: no copied `DESIGN.md` template. Each repo's `DESIGN.md` points at the shared
  design ideas.
- Owner ruling, 2026-10-26 (o15 answer a): the layout gets a core `todo` kind at `docs/todo.md`, with a
  legacy entry for each repo that keeps its tasks elsewhere.
- Owner ruling, 2026-10-28 (waiting-page item 3 a): a repo counts as rolled out only with `"rolled-out": true`
  in its `.claude/layout-extras.json`, a mark separate from its other keys.
- Owner ruling, 2026-10-28 (waiting-page item 32, answer c): home gets its mark at its own roll-out, not
  before. The mark change waits for that roll-out.
- A move keeps each file name. No record is renumbered or renamed (one-shared-record-stamp).

Reason: the tools disagreed on where records live. `lint/ste_lint.py` read `docs/decisions` by default,
and this repo keeps its records in `docs/decisions/`, so its gloss collapse never ran here. Four tools held
four copies of the path (building-allow-list-is-the-constant).

Kind: process
Home: lint/layout.json
Home: lint/check_layout.py
