---
name: plain-english-map
description: Use only in a repository that has `map.config.json` at its root. Use when a change adds, moves or deletes a tracked code file, a migration table or a screen key, when a MAP check fails, or when the user says "update the map" or "plain-english map", and before answering how code in this repo works. Keeps the plain-English map in `docs/map/` in sync with the code, and builds the map page.
---

`docs/map/` is the plain-English map of the code. A check holds it in sync. This skill says how to
change the map, and how to build its picture.

The skill runs in the host repository, and the root of every run is the working directory. Start each
command at the repository root. The skill finds no config when `map.config.json` is missing there, so
do not use this skill in that repository.

The repository values live in `map.config.json` at the repository root. The keys are `title`,
`codeExtensions`, `formatVersion`, `mapPaths`, `screenKeys`, `modelSeam`, `workerStage`, `migrationsDir` and `requireAllKeys`.
`mapPaths` is a list of path prefixes: MAP1 asks for a map line only for the code files under them. With no `mapPaths`, MAP1 covers the whole repository.
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
Version 2 to 3 changes no file: version 3 adds the fact line, the `## Homes` section and MAP9, and it makes an older copy of the skill refuse the map.
Version 1 to 2 removes the line references (`:26-36`) that version 1 map lines carried. It strips a `:N` after a file name only when its extension is in `codeExtensions`: `example.com:3000` stays.

## Steps

1. **Scout.** Read the diff. Run `node ~/.claude/skills/plain-english-map/scripts/map-check.mjs` from the
   repository root. Each failed line names the file, table or screen key that has no map entry. The
   command binds no model-call reader, so it skips the `modelSeam` call-site check and prints a note.
   A host that has its own check may run the same check bodies there.
2. **Build.** Add a map line for each new code file, table or screen key. Add a trace step for each new
   step in a screen's path. Fix each line that names a file the change moved or deleted.
3. **Review.** Run the same command until it is green. Then run
   `node ~/.claude/skills/plain-english-map/scripts/map-picture.mjs` from the repository root and read the page.
   It writes `map.html` in a new folder under the system temp folder and prints the path.
   Give a path to write there instead. The command refuses a path inside the repository.

## Formats

- **A map line.** In an area file, `docs/map/<area-id>.md`, under `## Code files`:
  `- ` + backtick path + ` — ` + one plain sentence that says what the file does.
- **A table line.** Under `## Tables`: `- ` + backtick table name + ` — ` + what the table holds.
- **A screen line.** Under `## Screens`: `- ` + backtick screen key + ` — ` + title + ` — ` + what the screen does.
- **A fact line.** Indented under a map line, and it starts with a word, never a backtick:
  `  - ` + one plain sentence + ` — ` + one backtick cite. A cite is `[file: ]SYMBOL = LITERAL` (the file is the map line's file when left out,
  the literal is JSON, `{…}` is a set and `[…]` a list) or `uses FILE[:SYMBOL]` (the map line's file imports FILE, and uses SYMBOL).
  The sentence shows each number of the cite, and names each item of a set or a list. A number outside backticks anywhere else in the map fails MAP9.
- **A home.** Under `## Homes`: `- ` + the capability in words + ` — ` + backtick `FILE:SYMBOL`. Read this section before you build, and extend the home.
- **A trace step.** In `docs/map/traces/<screen-key>.md`, under a `## <path name>` heading, a numbered line:
  `1. ` + backtick path + ` — ` + what the step does. Each step must be reached from an earlier step,
  by an import or by a web call to the route that answers it.

## Files

- `scripts/map-check.mjs` reads the map and the code, and holds the bodies of the 9 MAP checks. Run it from a repository root, and it runs the 9 checks there. It prints one line for each check, and exits non-zero on a FAIL.
- `scripts/map-picture.mjs` builds the picture data and the page, and it is the page command. It reads no decision records, so the rulings tab is empty.
- `scripts/map-upgrade.mjs` is the upgrade command, and holds the list of upgrade steps.
- `scripts/lib/map-config.mjs` reads and checks `map.config.json`. It is the one home of the validator.
- `scripts/lib/` also holds `import-reader.mjs`, `lazy-typescript.mjs` and `source-text.mjs`.
- `scripts/lib/fact-readers.mjs` reads the value of each fact line: JSON, TypeScript and JavaScript by their parsers, Python through `py-facts.py` (one `python3` start for a run), and any other language by a line regex. MAP9 fails when a reader cannot run: an unknown read is never a pass.
- `scripts/lib/lazy-typescript.mjs` loads the `typescript` package from the `node_modules` of claude-settings, which `install.sh` and `install.ps1` fill with `npm ci`. Through the install link, the host installs nothing. A copy of the skill outside the clone finds no `typescript`: the error says to run the skill from its install link, or to install `typescript` in the host.
- `assets/page.html` is the page template.
- `tests/` holds the skill's tests and a small fixture repository. Run `node --test` in that folder.

## What a host repository may add

A host may register the 9 check bodies with its own check, and it may bind its own readers. The model-call
readers go in through `bindConfig` and `bindSeamReader`, and the page readers go in through `bindReaders`.
With no model-call reader bound, the AI calls tab is empty. A host pins the install link, never a copy of this folder.
