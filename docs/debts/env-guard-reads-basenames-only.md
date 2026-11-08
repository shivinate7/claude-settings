# The env-file guard reads basenames only

**What.** The env-file guard judges each folder part of a path word, and ignores the working directory. These forms read or open an env file and pass: `grep --incl .env K .` (a shortened long flag) and `yq -n 'load(".env")'`. The Bash folder forms `cat .envs/x` and `cat .env/x/secret` now refuse, and have no test case yet. A session that names a file inside an env-named folder is likely to hit this in normal work. No incident is on record.

**Where.** `hooks/guard_env.py`: `_env_flat` (the per-word judge) and `_pattern_words` (the flag reader). `mkdir` is allowed on an env-prefixed folder. `cd` and `pushd` into one are refused, because the shell keeps its folder between calls.

**Decision.** `env-file-stays-unread`, no session reads an environment file.

**Retire.** Judge the abbreviated long flags and a `load(...)` call in a jq or yq program. Closed when a red case for each listed form in `hooks/test_guard.py` is refused and `hooks/test_guard.py` is green.
