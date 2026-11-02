# Env-file rule refuses some safe commands

- **What.** The env-file rule (decision `env-file-stays-unread`, the environment file stays unread) refuses some commands that read no environment file. Its heredoc checks also miss a body that runs a command, and two refusals on Nov 1 hit normal work.
- **Where.** `hooks/guard_env.py` (`names_env_file`, `_pattern_words`, `_env_flat`). `hooks/guard_core.py` (`INTERPRETER_HEREDOC`, `strip_heredoc_bodies`). `hooks/guard.py` (`judge_shell`, the env-file step and the force-push check). `settings.json` (the Read and Edit deny entries).
- **Decision.** `env-file-stays-unread` (the environment file stays unread: no session reads, writes or commits its contents).
- **Retire.** When every item under Residue is fixed, the fix PR deletes this file and rewrites decision `env-file-stays-unread` in place, so it no longer names this debt. Until then, each item under Residue gets a case in `hooks/test_guard.py`, red first, then green after its fix.

## Residue

Open at base commit 9743a81, by reading code. The note's exact commands were not run.

- `ag -f` and `ack -f`: `-f` is a boolean flag, but the guard reads it as naming a file, so every plain word is judged as a path. `ag -f TODO src` is allowed. Only an env-name word is refused, after `-f` or before it.
- `grep -r --exclude=.env`: the guard judges the value after `=` in any `--flag=value` word. It skips such a value only for pattern flags.
- `rg -t py .env`: `t` is not in `ENV_VALUE_SHORT`, so the guard takes `py` as the pattern and judges `.env` as a path.
- A folder word that starts with `.env`, such as `.envs`, is refused for `mkdir`, `git add`, `cat` and `cd`. Files inside it pass the shell form, since only the basename is judged. The Read and Edit deny list (`**/.env*` in `settings.json`) also refuses files inside it. Whether it covers every such file is unmeasured.
- `jq .environment f.json`, `jq .envFrom f.json` and `yq .envs f.yaml` are refused. Commands outside the search and script lists judge every word, and `names_env_file` holds any `.env` prefix by design. A jq or yq filter is not a path. Main allowed these three. `jq .env` was already refused on main.
- Cause. `INTERPRETER_HEREDOC` in `hooks/guard_core.py` matches an interpreter word and `<<` on one line, body lines included. `strip_heredoc_bodies` keeps the body when it matches. So a body line that names `node`, `python` or a shell, with `<<` after it, keeps the body in view, and its env names are judged.
- An unquoted heredoc body whose `$(...)` runs a command other layers miss, such as `cat <<OUT` with `$(git push --force origin main)`. `strip_heredoc_bodies` drops the body of `cat`, so the force-push check never reads it. The body's substitutions are judged for env names and the impeccable rule only.
- A Python body string that holds a backticked env name refuses, because the guard reads an interpreter body as shell words. Example: ``print(json.dumps({"note": "keep secrets out of `.envs`"}))``.
- A Python body string that is exactly an env name, such as a JSON value, refuses.
- A header file name that ends in `.sh`, such as `cat > x.sh <<'EOF'`, reads as a shell and keeps the body.
- An interpreter body that reads the file through Python (`open(...)`, `os.system`) passes. The guard reads shell words only.
- Lane `env-heredoc-false-alarm` closes two run paths: an ssh heredoc body, and a file a heredoc writes then runs. Neither is fixed yet.
- Context. Incident 1, 2026-11-01 23:41 CST, on main: the rule refused a triage session's Bash command that wrote a roadmap JSON note, because the note named an env folder inside a Python heredoc string. Incident 2, 2026-11-01 23:38 CST: the rule refused the coordinator's `cat > <scratchpad>/brief.md <<'EOF' ... EOF`, whose brief named env-file forms. No environment file was read or written in either.
- Passing. Incident 1's prose forms pass after PR 1057 (lane `env-file-scope`, the env-name predicate rewrite). Reported, not re-run here.
