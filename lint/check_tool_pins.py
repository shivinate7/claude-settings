#!/usr/bin/env python3
"""Fails when a tool on this machine is not the version the repo's own `.tool-versions` pins.

    python3 lint/check_tool_pins.py [--file F] [--local]

F defaults to `.tool-versions` at the root of the git repo the check runs in. Each repo owns its file, and the
check compares the tools of the machine it runs on with that file alone.

One line per pin: `<tool> <version>`. Blank lines are skipped. A comment sits on its own line: actions/setup-python
reads this file with a strict pattern, so a comment after a pin is refused. `# read: <tool> = <command>` gives a tool
a version command other than `<tool> --version`; the command takes shell-style quoting. The check runs each
command once, takes the first dotted number in its output, and compares it to the pin at the precision the pin
states: `3.15` accepts 3.15.2, `2.105` rejects 2.10.5. No tool is named here, so a new tool is one more line in the file.

Exit 1 on a mismatch, or on a refused file. A tool that cannot be found or read prints `unknown` and exits 1. With
`--local` a mismatch is a note and exit 0, for a machine that runs a different tool version than CI.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys

PIN_FILE = ".tool-versions"
RUN_TIMEOUT = 30  # a version command that takes longer is hung, so its tool reads as unknown
VERSION_IN_OUTPUT = re.compile(r"\d+(?:\.\d+)+")
PIN_VERSION = re.compile(r"\d+(?:\.\d+)*")
READ_LINE = re.compile(r"#\s*read:\s*(\S+)\s*=\s*(\S.*)$")


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
    """Returns (pins, commands): pins is a list of (tool, version, line number); commands maps tool to its read command."""
    pins, commands = [], {}
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            read = READ_LINE.match(line)
            if read:
                commands[read.group(1)] = read.group(2).strip()
            continue
        if "#" in line:
            raise PinFileError("%s line %d: a comment after a pin is refused; put the comment on its own line" % (path, number))
        parts = line.split()
        if len(parts) != 2 or not PIN_VERSION.fullmatch(parts[1]):
            raise PinFileError("%s line %d: expected `<tool> <version>`, got %r" % (path, number, line))
        pins.append((parts[0], parts[1], number))
    pinned = {tool for tool, _, _ in pins}
    for tool in commands:
        if tool not in pinned:
            raise PinFileError("%s: `# read:` names %s, which no line pins" % (path, tool))
    return pins, commands


def run_version_command(command):
    """The command's output, or None when it cannot run or exits non-zero."""
    try:
        words = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        return None
    if not words or shutil.which(words[0]) is None:
        return None
    try:
        # A Windows .cmd shim runs only through a shell.
        proc = subprocess.run(command if os.name == "nt" else words, shell=(os.name == "nt"), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                              timeout=RUN_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def matches(pin, found):
    """True when `found` equals `pin` at the precision `pin` states, number by number."""
    wanted = pin.split(".")
    return found.split(".")[:len(wanted)] == wanted


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
        pins, commands = parse(path)
    except (OSError, PinFileError) as e:
        print("tool-pins: %s" % e)
        return 1

    mismatches = unknowns = 0
    for tool, pin, _ in pins:
        output = run_version_command(commands.get(tool, tool + " --version"))
        number = VERSION_IN_OUTPUT.search(output) if output is not None else None
        if number is None:
            print("tool-pins: %s unknown: its version command did not run or printed no version" % tool)
            unknowns += 1
        elif matches(pin, number.group()):
            print("tool-pins: %s pinned %s, found %s: matched" % (tool, pin, number.group()))
        else:
            print("tool-pins: %s pinned %s, found %s; move the pin or the tool" % (tool, pin, number.group()))
            mismatches += 1
    if unknowns or (mismatches and not args.local):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
