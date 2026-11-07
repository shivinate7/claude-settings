# The env-file check reads basenames only

**What.** The env-file check judges each word's last path part and ignores the working directory. These forms read or open an env file and pass: `cd .envs && cat config.json`, `pushd .env && cat x`, `cat .envs/x`, `cat .env/x/secret`, `ag -G .env K`, `ag --file-search-regex .env K`, `grep --incl .env K .` (a shortened long flag) and `yq -n 'load(".env")'`. A session that has entered an env-named folder, or names a file inside one, is likely to hit this in normal work. No incident is on record.

**Where.** `hooks/guard_env.py`: `_env_flat` (the per-word judge) and `_pattern_words` (the flag reader). Folder commands (`cd`, `pushd`, `mkdir`) are allowed on an env-prefixed folder, so the folder form is open by design until the working directory is followed.

**Decision.** `env-file-stays-unread`, no session reads an environment file.

**Retire.** Judge a path through an env-named folder, follow `cd` and `pushd` within a command, and judge the abbreviated long flags and a `load(...)` call in a jq or yq program. Closed when a red case for each listed form in `hooks/test_guard.py` is refused and `hooks/test_guard.py` is green.
