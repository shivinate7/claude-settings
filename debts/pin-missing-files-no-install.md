# A pin at main with missing files stops the install

**What.** `merge/install_from_main.sh` treats a pin at main that has only missing tracked files as dirty: it exits 1 and installs nothing. Main's helper installed. A killed first pin add or an antivirus quarantine can leave such a pin, and then every later merge's install fails until someone restores it.

**Where.** `merge/install_from_main.sh`, the dirty-pin check in `move_pin` and `at_main`.

**Decision.** merge-reinstalls-from-main (the pin follows local main and is reinstalled after each merge).

**Retire.** Restore a deletions-only pin before the dirty check, as the helper already does for a `<clone>-live-<sha>` tree. A case: a pin at main with one tracked file deleted; after the helper, the file is back and the installer ran.
