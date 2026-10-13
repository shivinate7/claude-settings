"""The guard's WSL family: the one allowed way to launch Linux tests through WSL.

guard.py is the only entry point (decision guard-split-by-family). Owner ruling 2026-10-13: an
agent may run only a fixed list of test commands through WSL. Every other WSL form is refused,
whatever the role.
"""
import re

from guard_core import basename, resolve_command, segment_tokens, split_segments

WSL_REASON = (
    "WSL runs only a fixed list of Linux test commands. Allowed forms, each with -e or --exec, "
    "alone on the line, and optionally behind `python bin/verdict`: "
    "`wsl -e node --test <file>.test.mjs ...`, "
    "`wsl -e pwsh -NoProfile -File <file>.test.ps1`, and `wsl -e python3 <dir>/test_<name>.py`. "
    "Not allowed: a shell program, -u, -d, --cd, --system, --shell-type, a management verb, a "
    "WSLENV prefix, or a pipe, redirect, `;`, `&` or newline after the wsl part."
)

_PATH = r"[\w./-]*"
NODE_TEST = re.compile(r"^" + _PATH + r"[\w-]\.test\.mjs$")
PWSH_TEST = re.compile(r"^" + _PATH + r"[\w-]\.test\.ps1$")
PY_TEST = re.compile(r"^" + _PATH + r"test_[\w-]+\.py$")


def _allowed(args) -> bool:
    """True when the words after `wsl` are exactly one allowed test form."""
    if len(args) < 3 or args[0] not in ("-e", "--exec"):
        return False
    prog, rest = args[1], args[2:]
    if prog == "node":
        return rest[0] == "--test" and len(rest) > 1 and all(NODE_TEST.match(p) for p in rest[1:])
    if prog == "pwsh":
        return len(rest) == 3 and rest[:2] == ["-NoProfile", "-File"] and bool(PWSH_TEST.match(rest[2]))
    if prog == "python3":
        return len(rest) == 1 and bool(PY_TEST.match(rest[0]))
    return False


def _judge(tokens, closed: str) -> str:
    """Return the matched text when this segment runs wsl outside the allowed list, else ''."""
    at = resolve_command(tokens)
    if at is None or basename(tokens[at]) not in ("wsl", "wsl.exe"):
        return ""
    if closed or any(t.upper().startswith("WSLENV=") for t in tokens[:at]):
        return " ".join(tokens[:at + 3])
    return "" if _allowed(tokens[at + 1:]) else " ".join(tokens[at:at + 3])


def wsl_hit(cmd: str) -> str:
    """Return the matched text when any segment of the command runs wsl outside the allow list."""
    ends = []
    for segment, closed in zip(split_segments(cmd, ends), ends):
        tokens = segment_tokens(segment)
        if tokens is not None:
            hit = _judge(tokens, closed)
            if hit:
                return hit
            continue
        # An unparsable segment (a lone quote in text): cut it on the shell's own delimiters,
        # quotes ignored, so the quote cannot hide a wsl call after it.
        pieces = re.split(r"(;|\||&|\n)", segment)
        for i in range(0, len(pieces), 2):
            words = pieces[i].split()
            closed_piece = pieces[i + 1] if i + 1 < len(pieces) else closed
            hit = _judge(words, closed_piece) if words else ""
            if hit:
                return hit
    return ""
