"""The guard's browser-keychain rule: a Chromium launched by a script or a command with no mock keychain.

guard.py is the only entry point. Decision `render-browser-no-keychain` holds the incident and the ruling.

A Playwright or Puppeteer Chromium on macOS asks for the owner's login keychain ("Chromium Safe Storage").
Two switches keep it away: `--use-mock-keychain` and `--password-store=basic`. This file finds a launch
that carries neither or only one, in a shell command or in the text a Write or Edit would leave in a script.
"""
import collections
import os
import re

from guard_core import (
    _split_heredocs, basename, inline_script, resolve_command, segment_tokens, split_segments,
)
from guard_kill import _PW_RUNNERS, _pw_name   # the one home of "this token names the Playwright CLI"

# The two switches. bin/shoot and skills/waiting-page/check_designs.mjs each spell them as a literal.
BROWSER_FLAGS = ("--use-mock-keychain", "--password-store=basic")

BROWSER_KEYCHAIN_REASON = (
    "Rule (browser-keychain): this launches a Chromium without both `--use-mock-keychain` and "
    "`--password-store=basic`. On macOS a test browser then asks for the owner's keychain password "
    "(\"Chromium Safe Storage\"), and a click on Allow hands it the owner's stored secrets. "
    "Remedy: render with the built-in browser pane, or run `shoot --file <html file> --out <folder>` or `shoot --url <url> --out <folder>` "
    "(the shared tool). A script that must launch a Chromium passes "
    "`args: [\"--use-mock-keychain\", \"--password-store=basic\"]` (Python: `args=[...]`). "
    "(decision render-browser-no-keychain)"
)

_JS_EXT = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx"}
_PY_EXT = {".py"}
_SH_EXT = {".sh", ".bash", ".zsh"}
# A file with none (a bin/ tool) is a script when its first line is a shebang; the write reads it to know.
BROWSER_SCRIPT_EXTENSIONS = _JS_EXT | _PY_EXT | _SH_EXT | {""}
_INTERPRETERS = {
    "node": "js", "nodejs": "js", "bun": "js", "deno": "js", "tsx": "js", "ts-node": "js",
}
_PYTHON = re.compile(r"python[\d.]*$")
# A package runner carries the real program after its own words and flags: `npx -p playwright node -e`, `pnpm exec tsx -e`,
# `uv run python -c`, `python3 -m playwright open`. These are the runners beside the Playwright ones in guard_kill.
_RUNNERS = set(_PW_RUNNERS) | {"uv", "uvx", "pipx"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}

# The launch call of the two libraries. Python's `launch_persistent_context` is the same call.
_LAUNCH = re.compile(r"\b(?:chromium|puppeteer)\s*\.\s*(?:launch|launchPersistentContext|launch_persistent_context)\s*\(")
# `require('puppeteer').launch(`: the module name is a string, so it is read in the plain text, and counts only
# where the same spot is live code in the masked text.
_REQUIRE_LAUNCH = re.compile(
    r"\brequire\s*\(\s*['\"](?:puppeteer|puppeteer-core)['\"]\s*\)\s*\.\s*launch\s*\(")
# A literal `args` list. A call with none and an argument (`launch(opts)`, `launch({ ...base })`) takes its switches from a
# constant beside it, so both switches in the text pass it.
_LITERAL_ARGS = re.compile(r"\bargs\b\s*[:=]\s*\[")
# The Playwright CLI commands that open Chromium by default. The CLI takes no Chromium switches.
_PW_CHROMIUM_COMMANDS = {"screenshot", "pdf", "open", "codegen", "cr", "chromium"}
_PW_OTHER_BROWSERS = {"firefox", "ff", "webkit", "wk"}
# A Chromium binary run by hand: Chrome for Testing, Playwright's cache build, a system Chromium or Chrome.
_BINARY = re.compile(
    r"(?:google[ -]chrome(?:[ -]for[ -]testing|[ -]stable)?|chromium(?:-browser)?|chrome|chrome-headless-shell|headless_shell)$")
_DEPTH = 3


def _blank(buf, start, end):
    for at in range(start, end):
        if buf[at] != "\n":
            buf[at] = " "


def _mask(text: str, lang: str):
    """Return (masked, plain), both as long as `text`. Both blank each comment. `masked` also blanks the inside of
    each string, so a call named in a string or a comment is no call. `plain` keeps the strings, which is where
    the switches are read. `js` has `//`, `/* */` and backtick strings. `py` has `#` and triple quotes. A
    quoted string ends at its line end (a lone apostrophe in JSX text then spoils one line, never the rest)."""
    size = len(text)
    masked, plain = list(text), list(text)
    at = 0
    while at < size:
        char, two = text[at], text[at:at + 2]
        if (lang == "js" and two == "//") or (lang == "py" and char == "#"):
            end = text.find("\n", at)
            end = size if end < 0 else end
            _blank(masked, at, end)
            _blank(plain, at, end)
            at = end
        elif lang == "js" and two == "/*":
            end = text.find("*/", at + 2)
            end = size if end < 0 else end + 2
            _blank(masked, at, end)
            _blank(plain, at, end)
            at = end
        elif lang == "py" and text[at:at + 3] in ('"""', "'''"):
            close = text.find(text[at:at + 3], at + 3)
            end = size if close < 0 else close + 3
            _blank(masked, at + 3, max(at + 3, end - 3))
            at = end
        elif char in "'\"`":
            end = at + 1
            while end < size:
                if text[end] == "\\":
                    end += 2
                    continue
                if text[end] == char or (text[end] == "\n" and char != "`"):
                    break
                end += 1
            _blank(masked, at + 1, min(end, size))
            at = end + 1
        else:
            at += 1
    return "".join(masked), "".join(plain)


def _code_hits(text: str, lang: str) -> list:
    """Every launch in script text whose call carries no both switches. Each hit reads as the call and its start of args."""
    masked, plain = _mask(text, lang)
    hits = []
    found_all = list(_LAUNCH.finditer(masked))
    found_all += [f for f in _REQUIRE_LAUNCH.finditer(plain) if masked[f.start():f.start() + 7] == "require"]
    for found in found_all:
        depth, end = 1, found.end()
        while end < len(masked) and depth:
            depth += (masked[end] in "([{") - (masked[end] in ")]}")
            end += 1
        inside = slice(found.end(), end - 1 if depth == 0 else end)
        span = plain[inside]
        if all(flag in span for flag in BROWSER_FLAGS):
            continue
        if (masked[inside].strip() and not _LITERAL_ARGS.search(masked[inside])
                and all(flag in plain for flag in BROWSER_FLAGS)):
            continue
        hits.append(re.sub(r"\s+", " ", found.group(0) + span.strip()[:60]))
    return hits


def _lang_of(path: str, text: str) -> str:
    """The language of a script file by its extension, or by the shebang of a file with none (bin/ tools). '' when none."""
    ext = os.path.splitext(path)[1].lower()
    if ext in _JS_EXT:
        return "js"
    if ext in _PY_EXT:
        return "py"
    if ext in _SH_EXT:
        return "sh"
    if not ext and text.startswith("#!"):
        first = text.split("\n", 1)[0]
        for word, lang in (("node", "js"), ("bun", "js"), ("deno", "js"), ("python", "py"),
                           ("bash", "sh"), ("zsh", "sh"), ("/sh", "sh")):
            if word in first:
                return lang
    return ""


def _interpreter_lang(word: str) -> str:
    return "py" if _PYTHON.match(word) else _INTERPRETERS.get(word, "")


def _program(tokens, index) -> int:
    """The index of the program a package runner starts, else `index`. `npx tsx -e`, `pnpm exec node -e` and
    `npx -p playwright node -e` start an interpreter. The first later token that is one is read as the program, so a
    flag's value never hides it. A runner that starts no interpreter keeps its own index."""
    if basename(tokens[index]) not in _RUNNERS:
        return index
    for at in range(index + 1, len(tokens)):
        word = basename(tokens[at])
        if _interpreter_lang(word) or word in _SHELLS:
            return at
    return index


def _cli_hit(tokens, index) -> str:
    """The Playwright CLI command that opens Chromium (it takes no Chromium switch), or the Puppeteer launch command."""
    word = basename(tokens[index])
    rest = tokens[index:]
    if not (word in _RUNNERS or word.startswith("node") or _PYTHON.match(word) or _pw_name(word)):
        return ""
    for at, token in enumerate(rest):
        if token.lstrip("-").startswith("@puppeteer/browsers") and rest[at + 1:at + 2] == ["launch"]:
            return "@puppeteer/browsers launch"
        if not _pw_name(token) or at + 1 >= len(rest) or rest[at + 1] not in _PW_CHROMIUM_COMMANDS:
            continue
        values = [rest[i + 1] for i, t in enumerate(rest[:-1]) if t in ("-b", "--browser")]
        values += [t.split("=", 1)[1] for t in rest if t.startswith("--browser=")]
        if any(v in _PW_OTHER_BROWSERS for v in values):
            continue
        return "playwright " + rest[at + 1]
    return ""


def _binary_hit(tokens, index) -> str:
    """A Chromium or Chrome binary run with no both switches. `--version` and `--help` open no browser."""
    word = basename(tokens[index])
    if not _BINARY.match(word.lower().replace(".exe", "")):
        return ""
    rest = tokens[index + 1:]
    if any(t in ("--version", "--help", "-v", "-h") for t in rest):
        return ""
    if all(any(t == flag or t.startswith(flag + "=") for t in rest) for flag in BROWSER_FLAGS):
        return ""
    return word


def _redirect_target(tokens) -> str:
    """The file a segment writes with `>` or `>>`, or the first file `tee` takes, when it is a script file, else ''."""
    names = [tokens[i + 1] for i, t in enumerate(tokens[:-1]) if t in (">", ">>", "1>", "1>>")]
    index = resolve_command(tokens)
    if index is not None and basename(tokens[index]) == "tee":
        names += [t for t in tokens[index + 1:] if not t.startswith("-")]
    return next((n for n in names if _lang_of(n, "")), "")


def command_hit(command: str, depth: int = 0) -> str:
    """Return the matched text when a shell command launches a Chromium with no mock keychain, else ''.

    Only a command position counts: an interpreter's script text (`node -e`, `python3 -c`, a heredoc fed to one),
    a script file the command writes (`cat > a.mjs <<EOF`, `echo ... > a.py`), the Playwright CLI, or a Chromium
    binary. `grep chromium.launch`, `echo` and a commit message name the text and run nothing. A script file
    that the command only runs is not read: the Write or Edit that made it was judged.
    """
    if depth > _DEPTH or not command:
        return ""
    kept, bodies = _split_heredocs(command)
    for _quote, body, header in bodies:
        for segment in split_segments(header):
            tokens = segment_tokens(segment) or []
            index = resolve_command(tokens) if tokens else None
            index = _program(tokens, index) if index is not None else None
            lang = _interpreter_lang(basename(tokens[index])) if index is not None else ""
            lang = lang or (_lang_of(_redirect_target(tokens), "") if tokens else "")
            if lang == "sh":
                hit = command_hit(body, depth + 1)
            elif lang:
                hit = next(iter(_code_hits(body, lang)), "")
            else:
                hit = ""
            if hit:
                return hit
    for segment in split_segments("\n".join(kept)):
        tokens = segment_tokens(segment) or []
        index = resolve_command(tokens) if tokens else None
        if index is None:
            continue
        hit = _cli_hit(tokens, index) or _binary_hit(tokens, index)
        if hit:
            return hit
        index = _program(tokens, index)
        word = basename(tokens[index])
        lang = _interpreter_lang(word)
        written = _redirect_target(tokens)
        if word in _SHELLS or word in ("eval",):
            inner = inline_script(tokens)
            hit = command_hit(inner, depth + 1) if inner else ""
        elif lang or written:
            lang = lang or _lang_of(written, "")
            hit = next((h for t in tokens[index + 1:] for h in _code_hits(t, lang)), "") if lang != "sh" else ""
        else:
            hit = ""
        if hit:
            return hit
    return ""


def file_hits(path: str, text: str) -> list:
    """The launches with no mock keychain that script text holds, for the file at `path`. A shell script is read as commands."""
    lang = _lang_of(path, text)
    if lang == "sh":
        hit = command_hit(text)
        return [hit] if hit else []
    return _code_hits(text, lang) if lang else []


def write_hit(path: str, old, new: str) -> str:
    """The first launch a write adds. `old` is the text the file holds now (None for a new file), `new` the text the
    call leaves. A launch that the file already held, spelled the same, is no addition: an edit elsewhere in the
    file passes, and so does an edit that gives the launch its switches."""
    added = collections.Counter(file_hits(path, new)) - collections.Counter(file_hits(path, old or ""))
    return next(iter(added), "")
