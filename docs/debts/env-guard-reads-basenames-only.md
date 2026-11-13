# The env-file guard reads basenames only

**What.** The guard passes these forms, which read or open an env file: `cat .envs/x`, `cat .env/x/secret`, `grep --incl .env K .` (a shortened long flag), `yq -n 'load(".env")'` and `cd .envs/x && cat config.json`. A session that has entered an env-named folder, or names a file inside one, is likely to hit this in normal work; no incident is on record.

**Where.** `hooks/guard_env.py`: `_env_flat` (the per-word judge: it reads each word's last path part and ignores the working directory) and `_pattern_words` (the flag reader). `mkdir` is allowed on an env-prefixed folder. `cd` and `pushd` into one are refused, because the shell keeps its folder between calls.

**Decision.** `env-file-stays-unread`, no session reads an environment file.

**Retire.** Judge a path through an env-named folder, and judge the abbreviated long flags and a `load(...)` call in a jq or yq program. Closed when a red case for each listed form in `hooks/test_guard.py` is refused and `hooks/test_guard.py` is green.
