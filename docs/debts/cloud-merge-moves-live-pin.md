# Cloud merge can move the live pin

- **What.** In a cloud session, `merge/install_from_main.sh` runs `bash "$pin/install.sh"` without a pipe, after each coordinator merge. `CLAUDE_CODE_REMOTE=true` sets `CLOUD=1` (`install.sh` line 30). `SRC` is the pin, taken from `SCRIPT_DIR`, so the live-pin swap in the candidate loop never runs. The cloud own-checkout block then runs `git checkout --detach` on `origin/main` in the pin. That is a git write in the pin. It can move the pin past local main. The next `pin_off_main` check then refuses. Found by review of PR #915 (branch `setup-leaves-pin-cwd`). Not yet seen in a log.
- **Where.** `install.sh` (the `SCRIPT_DIR` source branch and the cloud own-checkout block), `merge/install_from_main.sh`.
- **Decision.** `merge-reinstalls-from-main` (each merge reinstalls from the main checkout; ruling 1: no work runs in the pin).
- **Retire.** A cloud run of `install.sh` from inside a pin never moves the pin. Either the swap runs after every source pick, or the cloud move block skips a live pin. A test proves it red, then green.
