# The link step parses a CommonJS target as an ES module

- **What.** The opt-in link step of code-check (`mjs-link`) parses every local target as an ES module. A `.cjs` target, or a `.js` file in a package with no `"type": "module"`, fails the link, though Node loads it: `import cfg from "./cfg.cjs"` reads "does not provide an export named 'default'".
- **Where.** `actions/code-check/link_check.mjs`, the module build step.
- **Decision.** none
- **Retire.** A local CommonJS target links as a synthetic module with Node's CommonJS export names, and a test in `actions/code-check/test_action.py` class `LinkStep` shows a `.cjs` default import green.
