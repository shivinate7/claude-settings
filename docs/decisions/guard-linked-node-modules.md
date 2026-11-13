# Refuse an install or recursive delete through a linked node_modules

## The question

Should the guard refuse npm installs and recursive deletes that would wipe a `node_modules` that is a link into another checkout (main's)?

## The ruling

Yes. Rule `linked-node-modules`, in `hooks/guard_push_delete.py` and `hooks/guard.py`.

- Every npm subcommand off a read-only allow list is judged in the folder `npm prefix` would use. So is `npm audit` with `fix` after it. The list (`NPM_READ_ONLY`, from npm 10.9.9) holds the canonical names of the commands that never rewrite `node_modules`. It fails closed: a new npm command, a typo that names no command and an ambiguous abbreviation are refused, not passed. The guard finds the folder with the `npm_walk` walk: up from the working folder to the first folder with a `package.json` or a `node_modules`. When that folder has a `package.json`, the walk goes on up, as npm does, to the first folder whose `workspaces` field lists it, and that root is the folder. The rule refuses when the folder's `node_modules` is a link (a junction or a symlink). Owner rulings 2026-10-20 (the allow list) and 2026-11-07 13:20 CST.
- The guard reads a subcommand by npm's own name (`npm_deref`: an alias, an abbreviation or a camelCase spelling resolves as in npm 10.9.9). The read-only list judges the dereferenced name, so `npm pac` and `npm publ` are read as pack and publish, and the alias tables have one home, `npm_deref`. The dereferenced name decides two things. `npm version`, by any spelling, is refused when it takes the workspace path: with `-w`, `-ws` or `--workspace`, or from a workspace folder. `--no-workspaces-update` or `--workspaces-update=false` turns that off, as npm then skips the reify. A `--dry-run` exempts only the commands on `NPM_DRY_RUN_SAFE` (install, ci, update, uninstall, dedupe, prune, link, install-test, install-ci-test, audit, version). A dry-run `npm version` does not reify, in a workspace or with `-w`; it still bumps `package.json` (measured, npm 10.9.9), which leaves `node_modules` alone. `rebuild`, `edit`, `explore` and an unknown name are refused with it.
- The `workspaces` field is read close to how npm reads it (`_workspace_member`). A brace set (`packages/{a,b}`) expands (`_brace_expand`). `*` and `**` skip a dot folder. The last entry that matches a folder decides, so `["!packages/a", "packages/*", "packages/a"]` makes packages/a a member and `["packages/*", "!packages/a"]` does not. Known limits, each needing an unusual `workspaces` field already in the repo: a leading negation (`["!p/b", "p/*"]`) is read as a member where npm excludes it; a re-include under a negated `**`, `!!x`, `{1..3}` ranges and extglobs (`!(a)`, `@(a|b)`) are not matched where npm matches them; `**` entering `node_modules` counts where npm ignores it; the walk stops at the first workspace root where npm keeps walking past a nested one.
- A recursive delete into a linked `node_modules` is refused.
- A bare delete of the link itself is allowed. Measured: `Remove-Item` on a junction removes only the link, not the target.
- The refusal names the real folder to make. It names neither `npm ci` nor `rm -rf`.

Outcome protected: a worktree's linked `node_modules` points at main's install. A hand-run `npm ci` through that link empties main's install, and every other worktree that shares it breaks.

## The incident

A request from the q_max worklist session. A hand-run `npm ci` through a junction to another checkout's install empties that install (measured on npm 12.0.2). 24 of 219 q_max worktrees hold such a link.

## Review

Three rounds. Round 3 passed. Net safety value is positive: the change adds one refusal and weakens nothing on main.

Kind: process
Home: hooks/guard_push_delete.py

## Safety holes, named

- (b) `--prefix` is read: its folder is the one judged. `-w` or `--workspace` on every command but `npm version` is not read, and `--no-workspaces` does not stop the workspace walk. A bypass and a false alarm both. `npm version` with a workspace flag is refused. Debt: `linked-nm-prefix-workspace`.
- (d) `pnpm`, `yarn`, `bun`, `npx` and `npm.exe` are not judged. Note: `linked-nm-other-managers`.
- (e) `find -delete`, `Get-ChildItem | Remove-Item`, `cmd rmdir /s`, `rimraf`, `cd node_modules && rm -rf x` and `-Recurse:$true` are not read as recursive deletes into the link. Note: `linked-nm-other-deletes`.
- (f) An inner `cd` inside `bash -c` or `sh -c` is not tracked. Note: `linked-nm-shell-c-cd`.

Two false alarms are accepted, as notes: `linked-nm-bare-word-false-alarms` (`echo npm ci`, `git rm -r --cached node_modules/x`), and `linked-nm-ancestor-link` (a stray linked `node_modules` in an ancestor folder).
