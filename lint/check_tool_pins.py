#!/usr/bin/env python3
"""Fails when a tool on this machine is not the version the repo's own `.tool-versions` pins.

    python3 lint/check_tool_pins.py [--file F] [--local]

F defaults to `.tool-versions` at the root of the git repo the check runs in. Each repo owns its file, and the
check compares the tools of the machine it runs on with that file alone.

One line per pin: `<tool> <version>`. Blank lines are skipped. A comment sits on its own line: actions/setup-python
reads this file with a strict pattern, so a comment after a pin is refused. `# read: <tool> = <command>` gives a tool
a version command other than `<tool> --version`; the command takes shell-style quoting and runs with no shell.
`# match: <tool> = <regex>` names the version for a tool: the regex has one group, and the group is the version.
Both words are case-insensitive. The check runs each command once and takes the first dotted number in its output
(a bare number only when there is no dotted one); a token with a slash or backslash is a path and never holds the version.
It compares the version to the pin at the precision the pin states: `3.15` accepts 3.15.2, `2.105` rejects 2.10.5,
`3` accepts 3.2.1. A pre-release (3.15.0rc1) matches only a pin that states it. No tool is named here, so a new
tool is one more line in the file.

Exit 1 on a mismatch, on a refused file, or on a file that holds no pin. A tool that cannot be found or read prints `unknown` and exits 1. With
`--local` a mismatch is a note and exit 0, for a machine that runs a different tool version than CI.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

PIN_FILE = ".tool-versions"
RUN_TIMEOUT = 30  # a version command that takes longer is hung, so its tool reads as unknown
# A release (`3.15.0`) and an optional pre-release (`rc1`, `a2`, `dev1`, `.dev1`); the pre-release ends at a word edge,
# so a hash such as `a1b2c3` is not one.
VERSION = re.compile(r"(?P<rel>\d+(?:\.\d+)*)(?:[-.]?(?P<pre>(?:alpha|beta|rc|dev|pre)\d*|[abc]\d+)(?![A-Za-z0-9]))?", re.I)
READ_LINE = re.compile(r"#\s*read:\s*(\S+)\s*=\s*(\S.*)$", re.I)
MATCH_LINE = re.compile(r"#\s*match:\s*(\S+)\s*=\s*(\S.*)$", re.I)


class PinFileError(Exception):
    """The file cannot be read as pins."""


def repo_root(start):
    """The nearest folder at or above `start` that holds `.git` (a folder, or a file in a worktree)."""
    here = os.path.abspath(start)
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def parse(path):
    """Returns (pins, commands, matchers): pins is a list of (tool, version, line number); commands maps tool to its
    read command; matchers maps tool to its compiled `# match:` regex."""
    pins, commands, matchers = [], {}, {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except UnicodeDecodeError:
        raise PinFileError("%s: not UTF-8 text; save the file as UTF-8" % path)
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            read = READ_LINE.match(line)
            if read:
                if "\x00" in read.group(2):
                    raise PinFileError("%s line %d: the read command holds a NUL byte" % (path, number))
                commands[read.group(1)] = read.group(2).strip()
                continue
            match = MATCH_LINE.match(line)
            if match:
                try:
                    regex = re.compile(match.group(2).strip())
                except re.error as e:
                    raise PinFileError("%s line %d: the `# match:` regex does not compile: %s" % (path, number, e))
                if regex.groups != 1:
                    raise PinFileError("%s line %d: the `# match:` regex needs exactly one group, the version; it has %d"
                                       % (path, number, regex.groups))
                matchers[match.group(1)] = regex
            continue
        if "#" in line:
            raise PinFileError("%s line %d: a comment after a pin is refused; put the comment on its own line" % (path, number))
        parts = line.split()
        if len(parts) != 2 or not VERSION.fullmatch(parts[1]):
            raise PinFileError("%s line %d: expected `<tool> <version>`, got %r" % (path, number, line))
        pins.append((parts[0], parts[1], number))
    if not pins:
        raise PinFileError("%s: no pin was read; add one `<tool> <version>` line" % path)
    pinned = {tool for tool, _, _ in pins}
    for word, named in (("read", commands), ("match", matchers)):
        for tool in named:
            if tool not in pinned:
                raise PinFileError("%s: `# %s:` names %s, which no line pins" % (path, word, tool))
    return pins, commands, matchers


def run_version_command(command):
    """The command's output, or None when it cannot run or exits non-zero. No shell runs the line."""
    try:
        words = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        return None
    if os.name == "nt":  # a non-POSIX split keeps the quote marks
        words = [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "\"'" else w for w in words]
    program = shutil.which(words[0]) if words else None  # `which` resolves a Windows .cmd shim by PATHEXT
    if program is None:
        return None
    try:
        proc = _nowindow.run([program] + words[1:], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace", timeout=RUN_TIMEOUT)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def read_version(output, matcher=None):
    """The version string in `output`, or None. A `# match:` regex names it; else the first dotted number, else the
    first bare number. A token with a path separator is skipped."""
    if matcher is not None:
        hit = matcher.search(output)
        if hit is None or hit.group(1) is None:
            return None
        output = hit.group(1)
    text = " ".join(t for t in output.split() if "/" not in t and "\\" not in t)
    found = [m for m in VERSION.finditer(text)]
    for m in found:
        if "." in m.group("rel"):
            return m.group()
    for m in found:
        before = text[m.start() - 1] if m.start() else " "
        after = text[m.end()] if m.end() < len(text) else " "
        if not (before.isalnum() or before in "_.-") and not (after.isalnum() or after in "_."):
            return m.group()
    return None


def matches(pin, found):
    """True when `found` equals `pin` at the precision `pin` states, number by number. A pre-release on either side
    needs the other side to state the same one."""
    want, have = VERSION.fullmatch(pin), VERSION.fullmatch(found)
    if want is None or have is None:
        return False
    wanted, got = want.group("rel").split("."), have.group("rel").split(".")
    want_pre = (want.group("pre") or "").lower()
    have_pre = (have.group("pre") or "").lower()
    if want_pre or have_pre:
        return wanted == got and want_pre == have_pre
    return got[:len(wanted)] == wanted


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare the tools on this machine with a repo's .tool-versions.")
    parser.add_argument("--file", help="the pin file; default: .tool-versions at the root of the repo this runs in")
    parser.add_argument("--local", action="store_true", help="note a mismatch and exit 0")
    args = parser.parse_args(argv)

    path = args.file
    if path is None:
        root = repo_root(os.getcwd())
        if root is None:
            print("tool-pins: unknown: no git repo here, so no %s to read; pass --file" % PIN_FILE)
            return 1
        path = os.path.join(root, PIN_FILE)
    try:
        pins, commands, matchers = parse(path)
    except (OSError, PinFileError) as e:
        print("tool-pins: %s" % e)
        return 1

    mismatches = unknowns = 0
    for tool, pin, _ in pins:
        output = run_version_command(commands.get(tool, tool + " --version"))
        number = read_version(output, matchers.get(tool)) if output is not None else None
        if number is None:
            print("tool-pins: %s unknown: its version command did not run or printed no version" % tool)
            unknowns += 1
        elif matches(pin, number):
            print("tool-pins: %s pinned %s, found %s: matched" % (tool, pin, number))
        else:
            print("tool-pins: %s pinned %s, found %s; move the pin or the tool" % (tool, pin, number))
            mismatches += 1
    if unknowns or (mismatches and not args.local):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
