# The map lists every file a decision or debt names

## The question

Should the shared plain-English map list every file a decision or debt names, not only code files?

## The ruling

Owner, Cockpit item 268 (`banchi-map-binary-hints`), choice a, 2026-11-06 13:08 CST: "Yes: list every file a decision or debt names." Not picked: "banchi only: map its 8 files", and "Accept the loss".

The owner's note on the item, 2026-11-06 11:22 CST: "fix our shared map too so that way the map can show files under a prose thing like a decision (or a debt etc)".

Why: in banchi, 8 non-code files lost 19 decision hints, because the map listed code files only.

- **Names.** A record names a file only by a backticked token that equals a tracked path exactly.
- **Records.** A decision record is an `.md` directly in `decisionsDir`. A debt record is an `.md` directly in the `debts` place of `lint/layout.json`. `README.md` and `notes.md` are no record. No new config key: decision `uniform-over-variants` (a repo matches a shared format) and decision `one-layout-every-repo` (tools read record paths from the layout).
- **MAP1.** A tracked file a record names needs a map line, of any type, still under `mapPaths`. Records, `docs/map/` pages and `map.config.json` never need one.
- **MAP10.** A non-code file's decisions line carries the id of each decision that names it. A `  - Debts: ` line carries the slug of each debt that names it. The check never reads the file's bytes.
- **Code files.** No change: comment cites only.
- **map-show.** Prints a non-code file's map line, decisions line and debts line when a record names it. A non-code file that no record names is out of scope.
- **Format version 6.** The step from 5 to 6 changes no file.

## Cost

No new process: the skill reads the records and `lint/layout.json` in the check run's own process (unmeasured). The file-read count is unmeasured.

## Safety holes, named

Debt: `js-layout-reader` (the skill reads the layout in JS, and skips `legacy-repos`).

Kind: process
Home: skills/plain-english-map/SKILL.md
