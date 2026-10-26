# Refuse an install or recursive delete through a linked node_modules

## The question

Should the guard refuse npm installs and recursive deletes that would wipe a `node_modules` that is a link into another checkout (main's)?

## The ruling

Yes. Rule `linked-node-modules`, in `hooks/guard_push_delete.py` and `hooks/guard.py`.

- `npm install`, `i`, `ci`, `update` and `uninstall` (with their aliases) are judged in the folder `npm prefix` would use. The guard finds it with the `npm_prefix` walk: up from the working folder to the first folder with a `package.json` or a `node_modules`. The rule refuses when that folder's `node_modules` is a link (a junction or a symlink).
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

- (a) `npm prune`, `dedupe`, `audit fix`, `rebuild` and `link` are not judged. Owner ruling 2026-10-20: a follow-up lane `npm-readonly-allowlist` replaces the command list with a read-only allow list. Debt: `npm-audit-fix-linked`.
- (b) `-w`, `--workspace` and `--prefix` are not read. A bypass and a false alarm both. Debt: `linked-nm-prefix-workspace`.
- (c) `npm install-test` and its aliases are not judged. Note in `docs/debts/notes.md`: `linked-nm-install-test`.
- (d) `pnpm`, `yarn`, `bun`, `npx` and `npm.exe` are not judged. Note: `linked-nm-other-managers`.
- (e) `find -delete`, `Get-ChildItem | Remove-Item`, `cmd rmdir /s`, `rimraf`, `cd node_modules && rm -rf x` and `-Recurse:$true` are not read as recursive deletes into the link. Note: `linked-nm-other-deletes`.
- (f) An inner `cd` inside `bash -c` or `sh -c` is not tracked. Note: `linked-nm-shell-c-cd`.

Two false alarms are accepted, as notes: `linked-nm-bare-word-false-alarms` (`echo npm ci`, `git rm -r --cached node_modules/x`), and `linked-nm-ancestor-link` (a stray linked `node_modules` in an ancestor folder).
