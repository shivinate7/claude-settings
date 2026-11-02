# An install removes only what it recorded

## The ruling

Coordinator brief, lane install-drops-retired-files (2026-11-01): each install removes a file it landed earlier that main no longer ships. It never removes a file it did not land.

- `install.sh` keeps one manifest, `backups/install-manifest.txt` under the config dir. Each line is one landed entry, `<dir>/<name>`, and what it was: a link target or a content hash. A skill line carries its tree hash.
- Shipped: git lists at least one file there that it does not ignore. A clone folder that holds only ignored files is not shipped, and is not landed.
- Removed: an entry in the manifest that is not shipped, and that still matches its record. A changed entry stays on disk and leaves the manifest, and the install logs it.
- Nothing is removed from a folder when the run failed there, or when that folder ships nothing.
- With no manifest yet, the install acts only on names in `retired-files.txt` at the repo root. A listed link into the clone is removed. Any other listed entry (a real file or folder, or a link that points elsewhere) moves to `backups/retired/`, so nothing is lost.
- `install.ps1` follows in lane install-ps1-manifest. Until then it keeps its old behaviour and reads neither the manifest nor `retired-files.txt`.

Why: copy mode (cloud) left every removed file in place, and a link into a folder git no longer tracks was landed again. Incident: the owner's PC kept `skills/tile-windows` and `hooks/config_report.py` (owner's local audit, 2026-11-01).

Cost: per install, one `git ls-files` start per landed folder and one manifest file written, read once at the next install. No new long-lived process, no timer. A removal that fails keeps its manifest line, so the next install retries it.

Kind: build
Home: install.sh
Plan: docs/decisions/install-manifest-prunes.md#the-ruling (all)
