# The guard leaves env-file reads by Read and Grep to the deny list

- **What.** The guard's env rule allows the Read and Grep tools on an environment file. Only the deny list in `settings.json` refuses them. Two pins of this were cut in lane cut-tests-guard.
- **Where.** The env rule in `hooks/guard_env.py`; the deny list in `settings.json`.
- **Decision.** `test-strategy-reset` (a hole pin becomes a debt).
- **Retire.** The env rule refuses Read and Grep on an environment file too, or a record says the deny list alone is enough.
