# An install removes only what it recorded

## The ruling

Coordinator brief, lane install-drops-retired-files (2026-11-01): each install removes a file it landed earlier that main no longer ships. It never removes a file it did not land.

- Both installers keep one manifest, `backups/install-manifest.txt` under the config dir. Each line is one landed entry, `<dir>/<name>`, and what it was: a link target or a content hash. Skills use the tree hash in `backups/skill-copies/`.
- Shipped: git lists at least one file there that it does not ignore. A clone folder that holds only ignored files is not shipped, and is not landed.
- Removed: an entry in the manifest that is not shipped, and that still matches its record. A changed entry stays on disk and leaves the manifest, and the install logs it.
- Nothing is removed from a folder when the run failed there, or when that folder ships nothing.
- With no manifest yet, the install acts only on names in `retired-files.txt` at the repo root. A listed link into the clone is removed. Any other listed entry (a real file or folder, or a link that points elsewhere) moves to `backups/retired/`, so nothing is lost.
- The post-merge hook that `install.ps1` writes lands copies of shipped entries only and removes no entry main stopped shipping. The next install removes those.

Why: copy mode (cloud, and Windows with no link rights) left every removed file in place, and a link into a folder git no longer tracks was landed again. Incident: the owner's PC kept `skills/tile-windows` and `hooks/config_report.py` (owner's local audit, 2026-11-01).

Cost: one manifest file written per install, read once at the next install. No process, no timer.

Kind: product
Home: install.sh
