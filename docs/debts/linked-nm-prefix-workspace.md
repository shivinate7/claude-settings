# The -w flag and --no-workspaces are not read for a linked node_modules

- **What.** `-w` and `--workspace` change the folder npm works in, and the rule reads them for `npm version` only. `npm ci -w sub` writes the workspace root's `node_modules` and passes when that root's link is not the folder judged (bypass). `--no-workspaces` stops npm from moving the prefix up to a workspace root, and the rule still moves it (false alarm).
- **Where.** The `npm_walk` walk and the `install` judge in the `linked-node-modules` rule, `hooks/guard_push_delete.py`.
- **Decision.** `guard-linked-node-modules` (refuse an install or recursive delete through a linked node_modules).
- **Retire.** Read `-w` and `--workspace` when it picks the folder, and read `--no-workspaces` when it stops the workspace walk. Tests for the cases above pass.
