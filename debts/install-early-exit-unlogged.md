# Installer refusals and lock timeouts log nothing

- **What.** Refusals and lock timeouts exit before the start line. A run that stops there writes no start line and no end line to the install log.
- **Where.** The early `exit 1` calls in `install.sh`, before `take_install_lock`, and the `exit 1` inside `take_install_lock`. In `install.ps1`, the refusal `exit 1` calls before the lock section, and its lock-timeout `exit 1`.
- **Decision.** `merge-reinstalls-from-main` (each installer path logs start and end with a unique id and pid).
- **Retire.** Log the start line before any exit, and the end line on every exit. Check: a refusal run and a lock-timeout run each leave one start line and one end line with the same id.
