---
name: plain-english-map
description: Use only in a repository that has `map.config.json` at its root. Use when a change adds, moves or deletes a tracked code file or a file that a decision or debt record names, a migration table or a screen key, when a MAP check fails, or when the user says "update the map" or "plain-english map", and before answering how code in this repo works. Keeps the plain-English map in `docs/map/` in sync with the code, and builds the map page.
---

`docs/map/` is the plain-English map of the code. A check holds it in sync. This skill says how to
change the map, and how to build its picture.

The skill runs in the host repository, and the root of every run is the working directory. Start each
command at the repository root. The skill finds no config when `map.config.json` is missing there, so
do not use this skill in that repository.

The repository values live in `map.config.json` at the repository root. The keys are `title`,
`codeExtensions`, `formatVersion`, `mapPaths`, `screenKeys`, `modelSeam`, `workerStage`, `migrationsDir`, `decisionsDir`, `decisionIdPattern` and `requireAllKeys`.
`mapPaths` is a list of path prefixes: MAP1 asks for a map line only for the code files under them, and MAP7 reads only those files. With no `mapPaths`, MAP1 and MAP7 cover the whole repository.
`decisionsDir` is a folder prefix, and `decisionIdPattern` a regex string for one decision id, such as `D\d+`. Set both or neither: one alone is an error.
`scripts/lib/map-config.mjs` checks the whole shape.

## The format version

`formatVersion` in `map.config.json` is a whole number: the format of the map files. The skill holds
the version it reads in `MAP_FORMAT_VERSION`, in `scripts/lib/map-config.mjs`. A config with no
`formatVersion` is version 1.

- **Same version.** The commands run as usual.
- **Older map.** The check command and the picture command fail, and the message names the upgrade command.
  They never rewrite a file. Run `node ~/.claude/skills/plain-english-map/scripts/map-upgrade.mjs` from the
  repository root. It brings the map up in place, one step at a time, keeps every sentence, and sets
  `formatVersion`. A second run changes no file. Then run the check command again.
- **Newer map.** Every command refuses, and the message says to update the skill. No command writes a downgrade.

To change the map format: raise `MAP_FORMAT_VERSION`, and add one step to the list in `scripts/map-upgrade.mjs`.
Version 5 to 6 changes no file: version 6 lets a decision or debt record name any file, adds the debts line, and extends MAP1 and MAP10. It makes an older copy of the skill refuse the map.
Version 4 to 5 changes no file: version 5 adds the tested-by line and MAP11. It makes an older copy of the skill refuse the map.
Version 3 to 4 changes no file: version 4 adds the two decision keys, the decisions line and MAP10. It makes an older copy of the skill refuse the map.
Version 2 to 3 changes no file: version 3 adds the fact line, the `## Homes` section and MAP9, and it makes an older copy of the skill refuse the map.
Version 1 to 2 removes the line references (`:26-36`) that version 1 map lines carried. It strips a `:N` after a file name only when its extension is in `codeExtensions`: `example.com:3000` stays.

## Steps

1. **Scout.** Read the diff. For each changed file, run `node ~/.claude/skills/plain-english-map/scripts/map-show.mjs <path|area|folder/|decision-id> [--full]` to read its map line first. Run `node ~/.claude/skills/plain-english-map/scripts/map-check.mjs` from the
   repository root. Each failed line names the file, table or screen key that has no map entry. The
   command binds no model-call reader, so it skips the `modelSeam` call-site check and prints a note.
   A host that has its own check may run the same check bodies there.
2. **Build.** Add a map line for each new code file, table or screen key. Add a trace step for each new
   step in a screen's path. Fix each line that names a file the change moved or deleted.
3. **Review.** Run the same command until it is green. Then run
   `node ~/.claude/skills/plain-english-map/scripts/map-picture.mjs` from the repository root and read the page.
   It writes `map.html` in a new folder under the system temp folder and prints the path.
   Give a path to write there instead. The command refuses a path inside the repository.
   Then run `node ~/.claude/skills/plain-english-map/scripts/map-stale.mjs` to rank the map lines whose file
   changed after the line. Read the worst ones first. It is advice: it always exits 0.

Before you answer how code in this repo works, run `node ~/.claude/skills/plain-english-map/scripts/map-show.mjs <path|area|folder/|decision-id> [--full]` from
the repository root. It is the cheap read: it prints the map, and you open no file. A file path prints its area, its map line, its fact lines, its tested-by line,
its Homes lines and its trace steps. A test path also prints the files whose tested-by line names it. An area id prints its map lines. A folder, with a `/` at the end, prints every map line under it.
With no match it prints `no map line for <arg>` and exits 1.

## Formats

- **A map line.** In an area file, `docs/map/<area-id>.md`, under `## Code files`:
  `- ` + backtick path + ` — ` + one plain sentence that says what the file does.
- **A table line.** Under `## Tables`: `- ` + backtick table name + ` — ` + what the table holds.
- **A screen line.** Under `## Screens`: `- ` + backtick screen key + ` — ` + title + ` — ` + what the screen does.
- **A fact line.** Indented under a map line, and it starts with a word, never a backtick:
  `  - ` + one plain sentence + ` — ` + one backtick cite. A cite is `[file: ]SYMBOL = LITERAL` (the file is the map line's file when left out,
  the literal is JSON, `{…}` is a set and `[…]` a list) or `uses FILE[:SYMBOL]` (the map line's file imports FILE, and uses SYMBOL).
  The sentence shows each number of the cite, and names each item of a set or a list. A number outside backticks anywhere else in the map fails MAP9.
- **A decisions line.** Indented under a map line: `  - Decisions: ` + each id in backticks, joined by `, `. An id names a record, a `.md` file directly in `decisionsDir`,
  when the file name without `.md` is the id or starts with the id and `-`. A run of digits compares by value: `D7` names `D007-x.md`.
- **A non-code map line.** A decision record or a debt record (a `.md` file directly in `decisionsDir` or in the debts folder, except `notes.md` and `README.md`) names a file by a backticked token that equals a tracked path exactly.
  A bare name, a prefix or a suffix names nothing. A tracked non-code file that a record names needs a map line under `## Code files`, like a code file (MAP1, still filtered by `mapPaths`).
  A record, a `docs/map/` page and `map.config.json` need none, and a code file needs no ids. Its decisions line carries the id of each naming decision record: the leading match of `decisionIdPattern` on the record's file name.
  A record whose file name has no such id adds none. Its debts line is `  - Debts: ` + the slug (the file name without `.md`) of each debt record that names it, in backticks, joined by `, `. A slug that names no debt record fails.
  The debts folder is the `debts` kind of `lint/layout.json` in the claude-settings root: no config key sets it. The skill reads the file in its own process and starts no `python3`.
- **A tested-by line.** Indented under a map line directly in `## Code files`, with no deeper heading between: `  - Tested by: ` + each test path from the repository root in backticks, joined by `, `.
  The line is optional: a map line with no tested-by line passes. MAP11 checks each test the line names.
- **A home.** Under `## Homes`: `- ` + the capability in words + ` — ` + backtick `FILE:SYMBOL`. Read this section before you build, and extend the home.
- **A trace step.** In `docs/map/traces/<screen-key>.md`, under a `## <path name>` heading, a numbered line:
  `1. ` + backtick path + ` — ` + what the step does. Each step must be reached from an earlier step,
  by an import or by a web call to the route that answers it.

## Files

- `scripts/map-check.mjs` reads the map and the code, and holds the bodies of the 11 MAP checks. Run it from a repository root, and it runs the 11 checks there. It prints one line for each check, and exits non-zero on a FAIL.
- MAP1 fails for a tracked code file with no map line, and for a tracked non-code file that a decision or debt record names and that has no map line.
- MAP10 runs when both decision keys are set or the debts folder exists, and otherwise it passes with a skip note. It fails in these cases.
  A mapped code file's comments cite an id that names a record, and the file's decisions line lacks it. Or an id on a decisions line names no record.
  A mapped non-code file lacks the id of a decision record that names it, or the slug of a debt record that names it.
  Or a debts line lists a slug that names no debt record. The non-code file's bytes are never read.
  With no decision keys, only the debts part runs. Comments are read through `scripts/lib/source-text.mjs`: JS and TS by `blankComments`, Python by `blankPython`, shell by `blankShell`. A string is no cite, a Python triple-quoted string included. A file of any other extension is read as JS.
- MAP11 fails when a test on a tested-by line is not a tracked file, or does not load the map line's file. A test loads a file in one of two ways.
  It imports the file (a type-only import does not count), or one `__init__.py` or `index.*` that it imports re-exports the file. Or a string in its code, never in a comment or a docstring, is the file's path, from the test's folder or the repository root.
  JS and TS are read by the TypeScript parser, and Python by `ast` in `py-facts.py`. A test in any other language, or a run with no `python3`, is an unknown read, and MAP11 fails: an unknown read is never a pass.
  A tested-by line under a table line, a screen line or a home fails.
- `scripts/map-fix.mjs` adds the ids and slugs that MAP10 finds missing, and never removes or reorders one. With no flag it prints each file and id it would add and writes nothing. With `--write` it adds them, and creates the decisions line (and the debts line after it) right under the map line when there is none. A second `--write` changes no byte.
- `scripts/map-picture.mjs` builds the picture data and the page, and it is the page command. It reads no decision records, so the rulings tab is empty.
- `scripts/map-show.mjs` is the show command. It prints the map for one file, area, folder or decision id (`--full` adds the record line for an id), through the readers of `map-check.mjs`. A non-code file prints its map line, and its decisions line and debts line when it has them, only when a record names it or its map line has either. A decision id also lists the non-code files whose decisions line holds it.
- `scripts/map-stale.mjs` is the stale command. It runs 1 `git rev-parse`, 1 `git blame` for each map page and 1 `git log` for all files, never a `git log` for each file. A shallow clone, no repository or no git prints an unknown line, never "nothing stale".
- `scripts/map-upgrade.mjs` is the upgrade command, and holds the list of upgrade steps.
- `scripts/lib/map-config.mjs` reads and checks `map.config.json`. It is the one home of the validator.
- `scripts/lib/` also holds `decisions.mjs` (which record an id names, which ids a file cites, and which files a record names), `import-reader.mjs`, `lazy-typescript.mjs` and `source-text.mjs`.
- `scripts/lib/fact-readers.mjs` reads the value of each fact line: JSON, TypeScript and JavaScript by their parsers, Python through `py-facts.py` (one `python3` start for a run), and any other language by a line regex. It also answers MAP11's `loads` read: the files a test imports (no type-only import) and the files a string in its code equals. MAP9 and MAP11 share the one call of a run. Each fails when a reader cannot run: an unknown read is never a pass.
- `scripts/lib/lazy-typescript.mjs` loads the `typescript` package from the `node_modules` of claude-settings, which `install.sh` and `install.ps1` fill with `npm ci`. Through the install link, the host installs nothing. A copy of the skill outside the clone finds no `typescript`: the error says to run the skill from its install link, or to install `typescript` in the host.
- `assets/page.html` is the page template.
- `tests/` holds the skill's tests and a small fixture repository. Run `node --test` in that folder.

## What a host repository may add

A host may register the 11 check bodies with its own check, and it may bind its own readers. The model-call
readers go in through `bindConfig` and `bindSeamReader`, and the page readers go in through `bindReaders`.
With no model-call reader bound, the AI calls tab is empty. A host pins the install link, never a copy of this folder.
