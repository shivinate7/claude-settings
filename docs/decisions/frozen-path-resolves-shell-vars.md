# Rule 7 resolves shell variables before it matches a write target

## The ruling

Before rule 7 (frozen-path) matches the target of a shell write, it reads the command left to right. It keeps a table of variable assignments: POSIX `VAR=value` (also after `export`, `declare`, `typeset`, `readonly` or `local`) and PowerShell `$VAR = value`.

- The last assignment wins. `unset` clears. A value it cannot resolve clears the older one.
- `$HOME` reads as `~`, also where the guard runs with no `HOME` set.

Each `$VAR` or `${VAR}` reads as its value at that point. Inside single quotes nothing expands. A write whose resolved target is frozen is refused. A variable with no known value at its use stays unresolved, and rule 7 allows it.

Why this option: it refuses only when the resolved target is frozen, so ordinary commands that write to `$OUT` stay allowed. Refusing any write to an unresolved variable when a frozen path is mentioned would fire on a read that writes nowhere frozen, and a guard that cries wolf is spent.

Interpreter code. A python or node script that a heredoc body, `-c` or `-e` hands to the interpreter writes files the shell never names. Rule 7 reads it with guard_core `code_paths` (`frozen_interpreter_hit`, a mode of `interpreter_write_hit` in hooks/guard_frozen.py) and refuses a string literal that is a frozen path when its mode is `write` or `unknown`. `unknown` is refused because the reader cannot tell what the call does with a name it does not know (a symlink, `os.open`, `codecs.open`, a mode held in a variable, a name built from parts). A call that only respells its one path (`os.path.expanduser`, `expandvars`, `abspath`, `realpath`, `normpath`, `normcase`, `fspath`) passes the mode of the call around it, as `os.path.join` does, so `open(os.path.expanduser(p), "w")` is a `write` and `print(os.path.expanduser(p))` is `text`. A `read`, an `exists` check and a `text` use (printed, written as content, compared) stay allowed. Code behind `uv run` and its kin is read too. Node code nested past `JS_DEPTH` names no path and is not refused (a form only an attacker would write). Cost: a command with no interpreter word reads nothing; any other costs one tokenize per segment and one parse per script. It starts no process and writes no file.

Rule 7 is a fence, not a wall. `settings.json` deny rules still refuse a direct Write or Edit. Owner, 2026-10-07: a value built from another env var, as `D="$CLAUDE_CONFIG_DIR/state/x"`, stays open. A `cp` with a frozen source is refused (`MUTATING_COMMAND` over-refuses `cp` and `mv` on purpose).

Kind: process
Home: hooks/guard_frozen.py
