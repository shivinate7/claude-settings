# Refuse an install or recursive delete through a linked node_modules

## The question

Should the guard refuse npm installs and recursive deletes that would wipe a `node_modules` that is a link into another checkout (main's)?

## The ruling

Yes. Rule `linked-node-modules`, in `hooks/guard_push_delete.py` and `hooks/guard.py`.

- Every npm subcommand off a read-only allow list is judged in the folder `npm prefix` would use. So is `npm audit` with `fix` after it. The list (`NPM_READ_ONLY`, from npm 10.9.9) holds the commands that never rewrite `node_modules`. It fails closed: a new npm command, an abbreviation or a typo is refused, not passed. The guard finds the folder with the `npm_prefix` walk: up from the working folder to the first folder with a `package.json` or a `node_modules`. The rule refuses when that folder's `node_modules` is a link (a junction or a symlink). Owner rulings 2026-10-20 (the allow list) and 2026-11-07 13:20 CST.
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

- (b) `--prefix` is read: its folder is the one judged. `-w` or `--workspace` on every command but `npm version`, and a plain install run inside a workspace member, are not read: npm writes the root's `node_modules`, and the walk stops at the member's `package.json`. A bypass and a false alarm both. `npm version` with a flag that turns workspaces on is refused; a `false` value, attached or as the next word, leaves them off. Debt: `linked-nm-prefix-workspace`.
- (d) `pnpm`, `yarn`, `bun`, `npx` and `npm.exe` are not judged. Note: `linked-nm-other-managers`.
- (e) `find -delete`, `Get-ChildItem | Remove-Item`, `cmd rmdir /s`, `rimraf`, `cd node_modules && rm -rf x` and `-Recurse:$true` are not read as recursive deletes into the link. Note: `linked-nm-other-deletes`.
- (f) An inner `cd` inside `bash -c` or `sh -c` is not tracked. Note: `linked-nm-shell-c-cd`.

Two false alarms are accepted, as notes: `linked-nm-bare-word-false-alarms` (`echo npm ci`, `git rm -r --cached node_modules/x`), and `linked-nm-ancestor-link` (a stray linked `node_modules` in an ancestor folder).
