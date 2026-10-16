# The pin move switches in place when symlinks are refused

- **What.** Without symlink rights, the pin move runs `git switch --detach` in `<clone>-live`. That writes the files one at a time. A session can read a mix of the old and the new main while the switch runs.
- **Where.** The in-place branch of `move_pin` in `merge/install_from_main.sh`.
- **Decision.** `merge-reinstalls-from-main` (the pin move and the install switch; this is its named hole).
- **Retire.** Move the pin without writing its files in place, on a machine with no symlink rights. Check: a test refuses symlinks, runs the move under a reader loop, and fails on any mixed read.
