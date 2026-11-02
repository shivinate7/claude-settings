# Env-file rule refuses some safe commands

- **What.** The env-file rule (decision `env-file-stays-unread`, the environment file stays unread) refuses commands that read no file's contents. At base commit 9743a81, by reading `hooks/guard_env.py`, none of these forms is fixed:
  - `ag -f` and `ack -f` are refused. `-f` is a boolean flag in both tools. The guard reads it as naming a file, so no word is taken as the search pattern. A search for `.env` is judged as a path. The mechanism is read from code. The note's exact commands were not run.
  - `grep -r --exclude=.env` is refused. The guard judges the value after `=` in a `--flag=value` word. It skips such a value only for pattern flags.
  - `rg -t py .env` is refused. `t` is not in `ENV_VALUE_SHORT`, so the guard takes `py` as the pattern and judges `.env` as a path.
  - A folder whose name starts with `.env`, such as `.envs`, is refused as a word for `mkdir`, `git add`, `cat` and `cd`. Files inside it pass the shell form, because only the basename is judged. The Read and Edit deny list (`**/.env*` in `settings.json`) also refuses files inside it. Whether the pattern covers every file inside a folder is unmeasured.
  - `jq .environment f.json`, `jq .envFrom f.json` and `yq .envs f.yaml` are refused. Commands outside the search and script lists judge every word. `names_env_file` holds any `.env` prefix by design, and its docstring names `.environment`. A jq or yq filter is not a path, so these are false alarms. `jq .env` is refused too. Main allowed these.
  - Incident 1 prose forms pass after PR 1057 (lane `env-file-scope`, the env-name predicate rewrite). Reported, not re-run here.
  - Incidents, both refusals of commands that wrote text. No environment file was read or written:
    - Incident 1, 2026-11-01 23:41 CST, on main. The rule refused a triage session's Bash command. The command wrote a roadmap JSON note. The note named an env folder inside a Python heredoc string.
    - Incident 2, 2026-11-01 23:38 CST. The rule refused the coordinator's `cat > <scratchpad>/brief.md <<'EOF' ... EOF`. The brief named env-file forms.
  - Cause, as found. `INTERPRETER_HEREDOC` in `hooks/guard_core.py` matches an interpreter word and `<<` on one line. It reads the whole command, body lines included. `strip_heredoc_bodies` keeps the body when it matches. A body line that names `node`, `python` or a shell, with `<<` after it on the same line, keeps the body in view, so its env names are judged. Lane `env-heredoc-false-alarm` changes this when it lands.
  - Open residue, kept here:
    - A header file name that ends in `.sh`, such as `cat > x.sh <<'EOF'`, reads as a shell and keeps the body.
    - A Python body string that is exactly an env name, such as a JSON value, is refused.
    - An interpreter body that reads the file through Python (`open(...)`, `os.system`) passes. The guard reads shell words only.
- **Where.** `hooks/guard_env.py` (`names_env_file`, `_pattern_words`, `_env_flat`). `hooks/guard_core.py` (`INTERPRETER_HEREDOC`, `strip_heredoc_bodies`). `hooks/guard.py` (`judge_shell`, the env-file step). `settings.json` (the Read and Edit deny entries).
- **Decision.** `env-file-stays-unread` (the environment file stays unread: no session reads, writes or commits its contents).
- **Retire.** Add one case per form to `hooks/test_guard.py`. Each case goes red on the current guard, then green after the fix. The heredoc cause closes when lane `env-heredoc-false-alarm` lands with its own cases. The residue stays in this record until a fix covers it or the owner accepts it. The fix PR deletes this file and rewrites decision `env-file-stays-unread` in place, so it no longer names this debt. The check is the `hooks/test_guard.py` run.
