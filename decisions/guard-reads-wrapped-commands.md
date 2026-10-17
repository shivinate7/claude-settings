# The stream and delete guards read the command a wrapper runs

Kind: build
Home: hooks/guard_core.py

The guard audit (findings 2, 3 and 4) found three gaps. The delete guard matched raw text, so it
denied a quoted `rm -rf /` in an `echo` and missed `rm -rf ~/` and `rm -rf ./*`. The kill guard
missed `kill $(lsof -ti:PORT)`, `fuser -k`, `kill-port` and `kill -9 -1`. The stream guard
denied a quoted `tail -f` in a commit message.

## The change

- `inner_commands` in `hooks/guard_core.py` reads the command inside a nested shell, `ssh`, and
  the runners `docker`/`podman exec`, `kubectl exec --`, `find -exec`, `su -c`, `flock`,
  `stdbuf`, `unbuffer` and `caffeinate`.
- `bare_words` reads a segment's unquoted words. The stream and delete guards deny the danger
  pattern at any unquoted position, so a runner left off the list is still caught. A quoted
  pattern in `echo`, a commit message, `sed` or `awk` passes.
- One wide-target set serves the delete guard, its fallback, the PowerShell pattern and the
  `cmd.exe` pattern.
- The kill guard reads `lsof -t` substitution, `fuser -k`, `kill-port` and pid -1 after a signal.

Rule `guard-guards-mistakes-only` (guards stop Claude's mistakes, not an attacker) sets the bar.

## Net safety value

Review round 3 probed about 300 forms on main and the branch. The value is positive.

- Closed: `rm -rf ${HOME}`, `~/`, `/*`, `./*`, `-Rf`, long flags, `--`, and subshell braces.
  Kills by `lsof -ti`, `fuser -k`, `kill-port` and `kill -9 -1`. `tail -f` inside `sh -c`,
  `su -c`, `eval`, `ssh` and PowerShell `-Command`.
- Opened: holes 3 below. Main denies them by raw text. Each is less likely to be written by
  mistake than the closed forms.

## Holes, named

1. The search-tool exemption in `bare_words` keys on `ENV_PATTERN_COMMANDS`, which the env-file
   rule shares. A tool added there for that rule is silently exempt from both guards. No test
   pins the coupling. Debt: `bare-words-shares-env-list`, the exemption list is shared.
2. `git rm -rf --cached .` and `--cached *` now deny. Main allowed them, and they touch only the
   index. Debt: `git-rm-cached-false-alarm`, an index-only delete denies.
3. `rm -rf` on a wide target, or `tail -f` not first, inside a quoted script handed to an unnamed
   runner passes: `docker run ... sh -c 'rm -rf /'`, `watch '...'`, `echo '...' | sh`. Debt:
   `quoted-script-unnamed-runner`, a quoted script for an unnamed runner is unread.
4. A subshell with `)` glued to the last word passes: `(rm -rf .)`, `x=$(tail -f y)`. This is
   unchanged from main. Debt: `glued-subshell-unread`, a glued subshell is unread.
5. `kill_hit` reads only the command word: `gtimeout 5 pkill -f node` and `watch pkill` pass on
   main and the branch. Debt: `kill-guard-word-only`, the kill guard reads one word.
6. `guard_stream.py` slices the words once per bare word, which is quadratic. A 20,000-word
   segment takes 8.2 s, against 2.2 s on main. Debt: `stream-guard-quadratic`, a long segment is
   slow.
7. Commit 106f785 relabelled a mutant's witness case in `hooks/mutate_guard.py`. A new mutant
   covers the token reader. CI runs the harness. Debt: none.
