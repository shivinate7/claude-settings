# A red mods/plain-diff/check.mjs passes CI

- **What.** `mods/plain-diff/check.mjs` is a self-check script, and the glob skips it. A red `check.mjs` passes CI.
- **Where.** The mod test glob in the `gates` job of `.github/workflows/gates.yml`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The file is renamed to `*.test.mjs` or is recorded as out of scope, and a case pins the choice.
