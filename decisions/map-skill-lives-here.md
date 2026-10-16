# The map skill lives in claude-settings, and a host pins a copy

## The question

Where does the plain-English map skill live, so that any repository can use it?

## The ruling

Owner, 2026-10-16: `skills/plain-english-map/` in claude-settings is the one home of the skill.
The install links it whole into `~/.claude/skills/plain-english-map`.

- A host repository is the root of every run. The default root is the working directory, and
  never the skill's own folder.
- The skill fires only in a repository that has `map.config.json` at its root. Its
  `description` says so.
- `typescript` installs once, in claude-settings. `package.json` pins it to `~5.8.2`, and
  `package-lock.json` locks it. `install.sh` and `install.ps1` run `npm ci` in the clone root.
  `scripts/lib/lazy-typescript.mjs` resolves the package from its own real path, so it finds
  the `node_modules` of claude-settings and never the host's.
- A host may pin a copy of the skill folder, and it need not stay byte-equal to this one.
  A host may bind its own readers. With none bound, the AI calls tab is empty.
- The skill's tests live in `skills/plain-english-map/tests/`, with a small fixture
  repository. The `gates` workflow runs them after `npm ci`.

## Named limit

A cloud install copies a skill outside the clone. That copy finds no `node_modules`, so the
check and page commands cannot load `typescript` there. The installer skips `npm ci` in cloud.

Kind: process
Home: skills/plain-english-map/SKILL.md
