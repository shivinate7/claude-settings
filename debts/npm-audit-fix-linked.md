# npm audit fix, prune and kin pass through a linked node_modules

- **What.** The rule judges only npm install, i, ci, update, uninstall and their aliases. `npm prune`, `dedupe`, `audit fix`, `rebuild` and `link` also write into `node_modules`, and they pass.
- **Where.** The npm command list in the `linked-node-modules` rule, `hooks/guard_push_delete.py` and `hooks/guard.py`.
- **Decision.** `guard-linked-node-modules` (refuse an install or recursive delete through a linked node_modules).
- **Retire.** Lane `npm-readonly-allowlist` (owner ruling 2026-10-20) replaces the command list with a read-only allow list. Tests for each command above, run in a folder with a linked `node_modules`, are refused.
