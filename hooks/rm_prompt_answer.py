#!/usr/bin/env python3
"""At a permission request for Bash in bypass mode, answers allow for a guarded delete of a safe, bound path. Prints nothing for any other command.

Deferred item rm-prompt-answer-hook, decision rm-on-a-variable-needs-a-guard (owner, 2026-10-11).
It answers allow only when all of these hold, and prints nothing otherwise:
- `permission_mode` is "bypassPermissions";
- the command is only simple assignments and `rm` calls, with no pipe, and it binds no name
  that an rm target does not expand;
- each `rm` target is one `${NAME:?}` plus plain folder names;
- NAME is assigned once, before the rm, to a plain literal that guard.py's `_rm_target_bad`
  does not read as /, home, the cwd or a parent of either.
The shell reading (`split_segments`, `segment_tokens`) and the critical-path reading come from
guard.py. Any error gives no output and exit 0.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guard  # noqa: E402

ALLOW = {"hookSpecificOutput": {"hookEventName": "PermissionRequest",
                                "decision": {"behavior": "allow"}}}
# After shlex: no expansion, glob, brace, tilde, quote, space, redirect or `..`.
_PLAIN = r"[\w.#@%+=:,'-]+"
_VALUE = re.compile(r"(?!.*(?:^|/)\.\.(?:/|$))[\w./#@%+=:,-]+")
_TARGET = re.compile(r"\$\{([A-Za-z_]\w*):\?\}((?:/%s)*)" % _PLAIN)
_REFUSED = {"IFS", "PATH"}   # word splitting and command lookup: never bound, never expanded
_FLAG = re.compile(r"-[A-Za-z]+|--")


def allowed(command: str, cwd: str) -> bool:
    ends = []
    segments = guard.split_segments(command, ends)
    if "|" in ends or "||" in ends:
        return False
    bound, used, deletes = {}, set(), 0
    for segment in segments:
        tokens = guard.segment_tokens(segment)
        if tokens is None:
            return False
        if not tokens:
            continue
        if tokens[0] == "rm":
            words = tokens[1:]
            while words and _FLAG.fullmatch(words[0]) and words.pop(0) != "--":
                pass
            if not words:
                return False
            for word in words:
                m = _TARGET.fullmatch(word)
                if not m or m.group(1) not in bound or m.group(1) in _REFUSED or any(
                        p in (".", "..") for p in m.group(2).split("/")[1:]):
                    return False
                if guard._rm_target_bad(bound[m.group(1)] + m.group(2), cwd):
                    return False
                used.add(m.group(1))
            deletes += 1
            continue
        for token in tokens:
            if not guard.ASSIGNMENT.match(token):
                return False
            name, value = token.split("=", 1)
            if (name in bound or name in _REFUSED or not _VALUE.fullmatch(value)
                    or guard._rm_target_bad(value, cwd)):
                return False
            bound[name] = value
    return deletes > 0 and used == set(bound)   # a stray binding (IFS, PATH, T=) can redirect the rm


def main() -> None:
    try:
        data = json.load(sys.stdin)
        command, cwd = data["tool_input"]["command"], data["cwd"]
        if (data.get("permission_mode") == "bypassPermissions" and data.get("tool_name") == "Bash"
                and isinstance(command, str) and isinstance(cwd, str) and cwd
                and allowed(command, cwd)):
            print(json.dumps(ALLOW))
    except Exception:
        return


if __name__ == "__main__":
    main()
