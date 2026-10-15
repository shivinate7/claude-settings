# The mod test runner's Node version is unknown

- **What.** The runner's Node version is unknown. The tests need `register` from `node:module`, which needs Node 20.6 or later. An older Node cannot run them.
- **Where.** The mod test step in the `gates` job of `.github/workflows/gates.yml`.
- **Decision.** `mods-tests-run-in-gates` (mod tests run as the last step of the gates job).
- **Retire.** The step reads the Node version and fails below 20.6, or the step sets the version.
