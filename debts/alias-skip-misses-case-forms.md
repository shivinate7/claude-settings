# The alias skip misses mixed-case and backslash paths

- **What.** The alias skip matches `/WindowsApps/` in the POSIX path Git Bash prints. A mixed-case or backslash form is not skipped. Git Bash prints the canonical form, so this is theoretical.
- **Where.** The python wrappers' alias skip.
- **Decision.** `gate-hooks-fail-closed` (a gate whose script or python is missing refuses the call).
- **Retire.** A test passes the mixed-case and backslash forms through the skip, and the skip matches both.
