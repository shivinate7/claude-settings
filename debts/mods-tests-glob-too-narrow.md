# The mod test glob misses nested and .js test files

- **What.** The glob reaches only root-level `mods/<name>/*.test.mjs`. A test in `mods/<name>/tests/`, or named `*.test.js`, never runs, and nothing reports it.
- **Where.** The mod test loop in the `gates` job of `.github/workflows/gates.yml`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The glob reaches nested folders and `*.test.js`, and a case with a red test in each shape fails the step.
