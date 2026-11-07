# The --prefix flag and --no-workspaces are not read for a linked node_modules

- **What.** `--prefix` changes the folder npm works in, and the rule ignores it. `npm ci --prefix real/` passes in a folder with a linked `node_modules` (false alarm: it is refused). `npm ci --prefix linked/` from a folder with a real one passes (bypass). `--no-workspaces` stops npm from moving the prefix up to a workspace root, and the rule still moves it (false alarm).
- **Where.** The `npm_walk` walk and the `install` judge in the `linked-node-modules` rule, `hooks/guard_push_delete.py`.
- **Decision.** `guard-linked-node-modules` (refuse an install or recursive delete through a linked node_modules).
- **Retire.** Read the value of `--prefix` when it picks the folder, and read `--no-workspaces` when it stops the workspace walk. Tests for the cases above pass.
