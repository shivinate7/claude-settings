# The CI wake misses some spellings of gh pr ready

- **What.** An obfuscated `gh pr re''ady` skips the wake. `gh pr ready 2>&1` reads the redirect as the PR selector.
- **Where.** The wake hook, `hooks/ci_wake.py`.
- **Decision.** `handoff-hooks-wave-2` (clear, fork, re-read and CI wake-up).
- **Retire.** Both spellings start a watch, and a case per spelling passes.
