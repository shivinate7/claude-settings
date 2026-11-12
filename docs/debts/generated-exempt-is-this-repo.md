# The generated-file exemption is this repo's list

**What.** `generated_pages`, called by `brief_scope_hit`, reads the catalog page, the records page and the `docs/map` folder through `_layout_module`. That loads the lint folder beside the guard, so in every repo the exemption is claude-settings' list, not that repo's. A file another repo's tool writes, such as `package-lock.json` after `npm install`, is refused when it existed at base and the brief does not name it.

**Where.** `hooks/guard.py`, `generated_pages` and `_layout_module`; `lint/layout.py`, `LAYOUT_PATH` (the layout file the list is read from).

**Decision.** `agent-commit-file-scope` (an agent's commit touches only the files its brief names).

**Retire.** Closed when a case in `hooks/test_guard.py` (family `brief-scope`) shows a `package-lock.json` that a fixture repo's tool rewrites judged by that repo's own generated files, not claude-settings' list.
