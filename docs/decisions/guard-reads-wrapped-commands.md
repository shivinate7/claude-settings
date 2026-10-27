# The stream and delete guards read the command a wrapper runs

## The ruling

The guards judge the command a wrapper runs, not the raw text. Rule `guard-guards-mistakes-only` (guards stop Claude's mistakes, not an attacker) sets the bar. The owner allowed the merge (2026-10-17 09:13 CDT, "yes merge guard fixes"), because net safety value is positive.

- `inner_commands` in `hooks/guard_core.py` reads the command inside a nested shell, `ssh`, and the runners `docker`/`podman exec`, `kubectl exec --`, `find -exec`, `su -c`, `flock`, `stdbuf`, `unbuffer` and `caffeinate`.
- `bare_words` reads a segment's unquoted words. The stream and delete guards refuse the danger pattern at any unquoted position, so a runner left off the list is still caught. A quoted pattern in `echo`, a commit message, `sed` or `awk` passes.
- One wide-target set serves the delete guard, its fallback, the PowerShell pattern and the `cmd.exe` pattern.
- The kill guard reads `lsof -t` substitution, `fuser -k`, `kill-port` and pid -1 after a signal.

Why: the delete guard refused a quoted `rm -rf /` in an `echo` and missed `rm -rf ~/`. The kill guard missed `kill $(lsof -ti:PORT)`. The stream guard refused a quoted `tail -f` in a commit message.

Kind: build
Plan: docs/decisions/guard-reads-wrapped-commands.md#the-ruling (all)
Home: hooks/guard_core.py
