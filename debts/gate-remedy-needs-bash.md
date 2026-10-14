# The gate remedy names a command Bash cannot run

- **What.** The remedy names `sh install.sh`. A missing guard refuses Bash too, so the owner has to run the installer in a terminal of their own.
- **Where.** The remedy line of the gate wrappers, pinned in `hooks/test_wrappers.py`.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** The remedy names a step that runs with Bash refused, and `hooks/test_wrappers.py` pins that text.
