# The linked node_modules rule judges the member folder for a workspace install

- **What.** `npm ci -w sub`, and a plain `npm ci` run inside a workspace member, write the root's `node_modules` (npm 10). The rule walks up only to the member's `package.json`, so a linked root `node_modules` passes (bypass).
- **Where.** The `npm_prefix` walk in the `linked-node-modules` rule, `hooks/guard_push_delete.py`.
- **Decision.** `guard-linked-node-modules` (refuse an install or recursive delete through a linked node_modules).
- **Retire.** Find the workspace root (a `package.json` above with a `workspaces` field that lists the member) and judge its `node_modules`. A test covers `-w sub` from the root and a plain install from a member.
