# The mv retry has no test

- **What.** No case in `hooks/test_install_src.sh` makes `mv` fail and then succeed, or fail 25 times.
- **Where.** `install.sh`.
- **Decision.** `install-sh-mv-retries` (install.sh retries the final rename).
- **Retire.** Add a shim case for each path.
