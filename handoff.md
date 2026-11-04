# Handoff: prose-path-check-whole-tree

- PR 1144 (opt-in whole-tree mode for stale_cites), draft, head db955007. Base main 72034d9a.
- Lane lint: `merge --lane-lint 1144` PASS at db955007.
- Review: 3 rounds. Round 3 PASS, net safety value positive (opt-in only, range mode unchanged).
- Record: docs/decisions/stale-cites-whole-tree.md. Notes: four stale-cites-tree-* lines in docs/debts/notes.md.
- Measured on main: tree run gives 70 STALE003, 0 STALE004. claude-settings does not opt in.

## Child removal lanes (each later, only on the owner's ask)

From the child-guard promotion plan, lane 1:

- banchi rows 39, 40 (docs-audit line anchors and paths). Keep row 40's allowlist and doc hygiene.
- degen row 8a (paths_check parts 1-2) and its copy of the hook catalog records list. Keep the records list check.
- joyous row 11 (marked ?).
- mailaudit row 13 (marked ?). Keep its code-name and link checks.
- q_max rows 23 (marked ?) and 24.

Each child sets `tree-cites: "true"` on its ste-lint pin first, then removes its copy. Locally, export TREE_CITES=true to match CI.
