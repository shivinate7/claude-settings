# The export-all fetch step nests each collection one folder too deep

- **What.** `ArtifactData list` with `out_dir` writes each doc to `<out_dir>/<collection>/<doc_id>.json`. The skill's "Before you switch Claude accounts" step 2 sets `out_dir` to `<folder>/<id>/<collection>`, so docs land in `<folder>/<id>/<collection>/<collection>/`. The export then finds a folder where it wants `<doc_id>.json` files and says unknown, exit 2, for each artifact with a non-empty collection. It writes nothing, so no data is lost, but no export lands. Measured 2026-11-04 02:40 CST: one list of the waiting page's `answers` saved 18 docs under `answers/answers/`.
- **Where.** `skills/waiting-page/SKILL.md`, "Before you switch Claude accounts", step 2. `export_page.py` `docs_in` gives the unknown.
- **Decision.** `waiting-data-in-repo` (a copy of the page lives in the repo; the scan runs before any write).
- **Retire.** Step 2 sets `out_dir` to `<folder>/<id>`, and the `.complete` marker stays in `<folder>/<id>/<collection>`. One `--all` run on a fresh fetch that follows the step says changed or same, not unknown.
