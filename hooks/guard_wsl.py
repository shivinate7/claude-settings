"""The guard's WSL family: the one allowed way to launch Linux tests through WSL.

guard.py is the only entry point. Owner ruling 2026-10-13: an
agent may run only a fixed list of test commands through WSL. Every other WSL form is refused,
whatever the role.
"""
import fnmatch
import re

from guard_core import QUOTE_MARKS, basename, command_indexes, nested_script, segment_tokens, split_segments

WSL_REASON = (
    "WSL runs only a fixed list of Linux test commands. Allowed forms, each with -e or --exec, "
    "alone on the line, and optionally behind `python bin/verdict`: "
    "`wsl -e node --test <file>.test.mjs ...`, `wsl -e node <file>.test.mjs` (one file, no glob), "
    "`wsl -e pwsh -NoProfile -File <file>.test.ps1`, and `wsl -e python3 <dir>/test_<name>.py`. "
    "Not allowed: a shell program, -u, -d, --cd, --system, --shell-type, a management verb, a "
    "WSLENV prefix, or a pipe, redirect, `;`, `&` or newline after the wsl part."
)

# A test path is relative, climbs nowhere, and may hold a glob (`mods/*/x.test.mjs`).
_PATH = r"[\w./*?\[\]-]*"
NODE_TEST = re.compile(r"^" + _PATH + r"[\w*?-]\.test\.mjs$")
PWSH_TEST = re.compile(r"^" + _PATH + r"[\w*?-]\.test\.ps1$")
PY_TEST = re.compile(r"^" + _PATH + r"test_[\w*?-]+\.py$")
# A launcher other than the wsl command: a distro launcher (ubuntu, debian, kali), or the System32 bash.exe (Git bash
# is not one). shlex eats a backslash, so `C:\Windows\System32ash.exe` reads `C:WindowsSystem32bash.exe`.
DISTRO_LAUNCHER = re.compile(r"(?:ubuntu|debian|kali)[\w.-]*\.exe$")
# A WSLENV assignment: `WSLENV=` bare or after export/set/env, `$env:WSLENV =`, an env: provider
# path, or the quoted name an API call takes. WSLENV named as plain text is not one.
WSLENV_SET = re.compile(
    r"(?:(?<![\w$:.\-])|\$\{?env:)WSLENV\}?\s*\+?=|(?<!\$)\benv:[\\/]?WSLENV\b|[\"']WSLENV[\"']",
    re.I)


# The names `_launcher` reads, as text: `wsl`, `wsl.exe`, `ubuntu*.exe`, `debian*.exe`, `kali*.exe`, the System32 `bash.exe`.
_LAUNCHER_TEXT = re.compile(r"wsl|ubuntu|debian|kali|bash\.exe", re.I)


def _climbs(seg: str) -> bool:
    """True when a path segment is `..`, or a dot-led glob that can expand to it (`.*`, `[.][.]`).
    A glob led by `*` or `?` never matches a leading dot, so `mods/*/x` stays allowed."""
    return seg == ".." or (seg[:1] in ".[" and fnmatch.fnmatchcase("..", seg))


def _test_path(path: str, pattern) -> bool:
    return bool(pattern.match(path)) and not path.startswith("/") and not any(map(_climbs, path.split("/")))


def _launcher(word: str) -> str:
    """'wsl' for the wsl command (bare or by any path), 'other' for another WSL launcher, else ''."""
    low = word.lower()
    if basename(word) == "wsl" or low.endswith("wsl.exe"):
        return "wsl"
    if DISTRO_LAUNCHER.search(low) or (low.endswith("bash.exe") and ("system32" in low or "sysnative" in low)):
        return "other"
    return ""


def _allowed(args) -> bool:
    """True when the words after `wsl` are exactly one allowed test form."""
    if len(args) < 3 or args[0] not in ("-e", "--exec"):
        return False
    prog, rest = args[1], args[2:]
    if prog == "node":
        if rest[0] == "--test":
            return len(rest) > 1 and all(_test_path(p, NODE_TEST) for p in rest[1:])
        # Plain node runs only its first file, so more would be a false green: one literal path.
        return len(rest) == 1 and not set("*?") & set(rest[0]) and _test_path(rest[0], NODE_TEST)
    if prog == "pwsh":
        return len(rest) == 3 and rest[:2] == ["-NoProfile", "-File"] and _test_path(rest[2], PWSH_TEST)
    if prog == "python3":
        return len(rest) == 1 and _test_path(rest[0], PY_TEST)
    return False


def _judge(tokens, closed: str, env_set: bool) -> str:
    """Return the matched text when this segment runs wsl outside the allowed list, else ''.
    A script handed to another interpreter (`bash -c`, `cmd /c`, `iex`) is judged as a command, and
    so is the command after each `$(` or `(`."""
    script = nested_script(tokens)
    if script:
        hit = wsl_hit(script, env_set or bool(closed))
        if hit:
            return hit
    for at in command_indexes(tokens):
        kind = _launcher(tokens[at])
        if not kind:
            continue
        if kind == "other" or closed or env_set or any(t.upper().startswith("WSLENV=") for t in tokens[:at]):
            return " ".join(tokens[:at + 3])
        args = tokens[at + 1:]
        while args and not args[-1].strip(")"):
            args.pop()   # the `)` that closes a subshell is no part of a path
        if args:
            args[-1] = args[-1].rstrip(")")
        if not _allowed(args):
            return " ".join(tokens[at:at + 3])
    return ""


def wsl_hit(cmd: str, env_set: bool = False) -> str:
    """Return the matched text when any segment of the command runs wsl outside the allow list.
    `env_set` is true when an outer statement set WSLENV or piped the call onward."""
    if not _LAUNCHER_TEXT.search(QUOTE_MARKS.sub("", cmd)):
        return ""   # no launcher name in the text, so no token is one (see _launcher)
    ends = []
    env_set = env_set or bool(WSLENV_SET.search(cmd))   # set in any statement of the same command
    for segment, closed in zip(split_segments(cmd, ends), ends):
        tokens = segment_tokens(segment)
        if tokens is not None:
            hit = _judge(tokens, closed, env_set)
            if hit:
                return hit
            continue
        # An unparsable segment (a lone quote in text): cut it on the shell's own delimiters,
        # quotes ignored, so the quote cannot hide a wsl call after it.
        pieces = re.split(r"(;|\||&|\n)", segment)
        for i in range(0, len(pieces), 2):
            words = pieces[i].split()
            closed_piece = pieces[i + 1] if i + 1 < len(pieces) else closed
            hit = _judge(words, closed_piece, env_set) if words else ""
            if hit:
                return hit
    return ""

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
