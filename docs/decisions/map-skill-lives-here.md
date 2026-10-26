# The map skill lives in claude-settings, and a host pins a copy

## The question

Where does the plain-English map skill live, so that any repository can use it?

## The ruling

Owner, 2026-10-16: `skills/plain-english-map/` in claude-settings is the one home of the skill.
The install links it whole into `~/.claude/skills/plain-english-map`.

- A host repository is the root of every run. The default root is the working directory, and
  never the skill's own folder.
- The skill's `description` asks for use only in a repository that has `map.config.json` at its
  root. No code enforces this. A run in another repository finds no config and stops.
- `typescript` installs once, in claude-settings. `package.json` pins it to `~5.8.2`, and
  `package-lock.json` locks it. `install.sh` and `install.ps1` run `npm ci` in the clone root.
  `scripts/lib/lazy-typescript.mjs` resolves the package from its own real path. Through the
  install link, that path is inside the clone, so the skill finds the `node_modules` of
  claude-settings, and the host installs nothing.
- A host may pin a copy of the skill folder, and it need not stay byte-equal to this one.
  A host may bind its own readers. With none bound, the AI calls tab is empty.
- The skill's tests live in `skills/plain-english-map/tests/`, with a small fixture
  repository. The `gates` workflow runs them after `npm ci`.

## Safety holes, named

Debts: `skill-copy-no-typescript` (a copy of the skill outside the clone finds no `typescript`: a cloud install, or a refused symlink. An offline `npm ci` re-install also wipes `node_modules`), `gitignore-skips-map-tests` (a change to only `.gitignore` skips the map skill tests), `upgrade-strips-name-port` (the version 2 upgrade strips a port after a code-file name, such as `node.js:18`).

Kind: process
Home: skills/plain-english-map/SKILL.md
