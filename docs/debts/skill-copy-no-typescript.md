# A copy of the map skill outside the clone finds no typescript

- **What.** A copy of the skill folder outside the clone finds no `node_modules`, so `map-check.mjs` and `map-picture.mjs` cannot load `typescript` there. Two cases make such a copy: a cloud install, and a local install that cannot make a symlink. The cloud installer skips `npm ci`. `lazy-typescript.mjs` prints what to do: run the skill from its install link, or install `typescript` in the host.
- **Also.** `npm ci` deletes `node_modules` before it installs. An offline re-install that fails leaves the clone with no `node_modules`, so the skill cannot load `typescript` until `npm ci` passes again. Both installers print the end of the `npm ci` output when it fails.
- **Where.** `skills/plain-english-map/scripts/lib/lazy-typescript.mjs`, and the `npm ci` command of `install.sh` and `install.ps1`.
- **Decision.** `map-skill-lives-here` (the map skill lives in claude-settings, and a host pins the install link).
- **Retire.** The skill finds `typescript` in a copy outside the clone. A bundled copy of the parser is one way. An offline re-install also keeps the old `node_modules`. A test that runs the check command from a copied folder with no `node_modules` goes green.
