# A change to only .gitignore skips the map skill tests

- **What.** `ci-scope.sh` turns on only `code` for a `.gitignore` change. The map skill test `typescript-home.test.mjs` reads `.gitignore` and expects `node_modules/` in it. So a pull request that changes only `.gitignore` does not run that test. A push to main runs every job, so main goes red after the merge, not before it.
- **Where.** The `.gitignore` arm of `.github/scripts/ci-scope.sh`, and `skills/plain-english-map/tests/typescript-home.test.mjs`.
- **Decision.** `map-skill-lives-here` (the map skill lives in claude-settings, and a host pins a copy).
- **Retire.** A `.gitignore` change also turns on `mods`, and a case in `lint/test_ci_scope.py` holds it.
