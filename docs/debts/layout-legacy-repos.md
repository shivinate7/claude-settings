# The layout keeps a per-repo place for two repos' todo files

**What.** The layout's `legacy-repos` map lets two named repos keep their `todo` kind in a place of their own: q_max at `specs/todo.md`, home at `records`. Every shared tool that asks the layout accepts that second form for those repos only.

**Where.** `lint/layout.json` key `legacy-repos`, read by `lint/layout.py` (`legacy_repos()`, `unmoved()`, `path()`), `lint/check_layout.py` and `lint/compliance_probes.py`.

**Decision.** `uniform-over-variants`, a repo matches a shared format and the shared tool never grows a second form (topic t18). `one-layout-every-repo`, the same folders in every repo, names this map as one the last roll-out deletes.

**Retire.** q_max and home each move their todo file to the layout's `docs/todo.md` in their own roll-out. Then delete the `legacy-repos` map, its readers and its tests. `grep -r legacy-repos lint/` finds nothing.
