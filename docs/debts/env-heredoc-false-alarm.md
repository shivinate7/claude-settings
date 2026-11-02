# Env-file guard refuses heredoc text that names env forms

**What.** The env-file guard refuses some shell commands only because an env form appears as text. The text sits in a heredoc body or a quoted string.

- (1) 2026-11-01 CST, 23:41. Triage 5's Bash command only wrote a roadmap JSON note. It was refused. The note text named an env folder inside a python heredoc string. The exact command was not kept. The fix lane reproduces it as a backtick span inside a python string under a quoted delimiter (inferred reproduction).
- (2) 2026-11-01 CST, 23:38. The coordinator ran `cat > <scratchpad>/brief.md <<'EOF' ... EOF` to write a lane brief. It was refused. The brief text named env-file forms.
- A third live case on 2026-11-01, in lane env-heredoc-false-alarm's own probes.
- No env file was read or written in either incident.

**Kind.** Named incident. Two incidents on 2026-11-01 CST, and a third case the same day.

**Causes.**

- The interpreter-heredoc check reads the whole command, body lines included. A data body that mentions an interpreter header keeps every body under the shell scan. So does any interpreter heredoc elsewhere in the same call.
- In a quoted-delimiter interpreter body, backticks and `$( )` in the interpreter's strings were read as shell substitutions.

**Where.** hooks/guard_env.py, hooks/guard_core.py.

**Decision.** `env-file-stays-unread`, the environment file stays unread. No session reads, writes or commits its contents.

**Retire.**

- Fix: lane env-heredoc-false-alarm (env layer only). A body stays under the shell scan only when its own header feeds it to a shell or an interpreter. A quoted body fed to a non-shell interpreter opens no substitutions.
- Closed when the lane's red cases for both incidents go green. Each case is red before the fix and green after it.
- Still open. The fix does not cover these. No fix lane is named yet. Each one closes when a red case for it goes green.
  - `ag -f` and `ack -f`, and `grep -r --exclude=.env` and `rg -t py .env`: the guard refuses all four. `-f` is a boolean flag in `ag` and `ack`. All four are safe. None reads a file's contents.
  - A folder whose name starts with .env, such as `.envs`: the guard refuses mkdir, git add, cat and cd on it. The shell guard allows files inside it. The Read and Edit deny list refuses files inside it too.
  - A word that starts with .env and names no file: `jq .environment f.json`, `jq .envFrom f.json` and `yq .envs f.yaml` are refused. Main allowed these. `jq .env` was already refused.
