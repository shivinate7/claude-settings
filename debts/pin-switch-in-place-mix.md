# A pin switched in place can show a live reader a mix

- **What.** A host can have no symlink rights. There, the afterMerge helper moves the pinned checkout with `git switch --detach` in place. git writes the files one at a time. A live session that reads through the pin during the switch can see some old files and some new ones. The risk is low. A host with no link rights installs copies, so `~/.claude` does not read the pin live.
- **Where.** `switch_in_place` in `merge/install_from_main.sh`.
- **Decision.** `merge-reinstalls-from-main` (the afterMerge step moves the pinned checkout to main, then installs from it).
- **Retire.** The no-link path builds the new tree aside and swaps it in with one rename. Or a check shows that the copy install never reads the pin live. A case in `merge/test_install_from_main.sh` pins it.
