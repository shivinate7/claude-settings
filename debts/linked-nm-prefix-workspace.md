# The -w and --prefix flags are not read for a linked node_modules

- **What.** `-w`, `--workspace` and `--prefix` change the folder npm works in. The rule ignores them. `npm ci --prefix real/` passes in a folder with a linked `node_modules` (false alarm: it is refused). `npm ci --prefix linked/` from a folder with a real one passes (bypass).
- **Where.** The `npm_prefix` walk in the `linked-node-modules` rule, `hooks/guard_push_delete.py`.
- **Decision.** `guard-linked-node-modules` (refuse an install or recursive delete through a linked node_modules).
- **Retire.** Read the value of `--prefix`, `-w` and `--workspace` when it picks the folder. Tests for both cases above pass.
