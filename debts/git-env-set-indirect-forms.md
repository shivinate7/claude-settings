# Indirect sets of a git location variable pass the guard

- **What.** The guard reads literal set forms only. These pass: a shell function around the set, `set -a` with `read` or `for`, and a name built at run time. So do `iex`, `-EncodedCommand` and `os.environ` in `python -c`. A name split by a backtick, a single-quoted `sh -c` body, or printf directives after `builtin`, `command`, `env`, `printf.exe`, `awk` or `echo -e` also passes. The guard targets accidental sets, not an attacker.
- **Where.** `git_env_command_hit` in `hooks/guard_kill.py`.
- **Decision.** `git-env-set-denied` (a command that sets a git location variable is denied).
- **Retire.** A child-env scrub in the test helpers that run `git init`, or a PostToolUse check of `core.worktree` after each call, closes the outcome for every form. A test sets the variable through a function and the check reports it.
