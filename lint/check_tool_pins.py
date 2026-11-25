#!/usr/bin/env python3
"""Fails when a tool on this machine is not the version the repo's own `.tool-versions` pins.

    python3 lint/check_tool_pins.py [--file F] [--local]
    python3 lint/check_tool_pins.py --behind ROOT

F defaults to `.tool-versions` at the root of the git repo the check runs in. Each repo owns its file, and the
check compares the tools of the machine it runs on with that file alone.

One line per pin: `<tool> <version>`. Blank lines are skipped. A comment sits on its own line: actions/setup-python
reads this file with a strict pattern, so a comment after a pin is refused. `# read: <tool> = <command>` gives a tool
a version command other than `<tool> --version`; the command takes shell-style quoting and runs with no shell. A tool
may have several `# read:` lines: they are tried in order, and the first that runs and prints a version wins.
`# match: <tool> = <regex>` names the version for a tool: the regex has one group, and the group is the version.
Both words are case-insensitive. The check runs each command once and takes the first dotted number in its output
(a bare number only when there is no dotted one); a token with a slash or backslash is a path and never holds the version.
It compares the version to the pin at the precision the pin states: `3.15` accepts 3.15.2, `2.105` rejects 2.10.5,
`3` accepts 3.2.1. A pre-release (3.15.0rc1) matches only a pin that states it. No tool is named here, so a new
tool is one more line in the file.

`# fix: <tool> <macos|windows|linux> = <command>` gives the command that brings the tool up to its pin on one platform. A
malformed fix line is refused, never skipped; a fix line names a pinned tool once per platform.

A program that resolves under a `WindowsApps` folder is the Store's app alias, not an install, so it counts as not found.

Exit 1 on a mismatch, on a refused file, or on a file that holds no pin; a mismatch line starts `FAIL`. A tool that cannot be
found or read prints `unknown` and exits 1. With `--local` a mismatch is a note and the exit is 3, for a machine that runs
a different tool version than CI: 0 is a match, 3 a mismatch, 1 an unknown or a refused file (unknown wins over a mismatch).

`--behind ROOT` reads the `.tool-versions` at ROOT for the session start and the ready run (decision tool-pins): a tool older
than its pin prints a `BEHIND` line with the version found, the path it ran from and this platform's fix, and the exit is 3; a
tool newer than its pin is no failure (exit 0). An unreadable tool prints `unknown` and exits 1 (unknown wins over behind). All
reads share one time budget, BEHIND_BUDGET seconds (the CS_TOOL_PINS_BUDGET variable sets it): a read the budget cuts reads as unknown.
Cost: one version command per pin, none past the budget; no network, no file written.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

PIN_FILE = ".tool-versions"
LOCAL_MISMATCH = 3  # `--local` on a mismatch: lane lint tells it from a match (0) and an unknown (1)
RUN_TIMEOUT = 30  # a version command that takes longer is hung, so its tool reads as unknown
BEHIND_BUDGET = 5  # seconds all of one `--behind` run's reads share: the session start hook ends at 10 s (settings.json); CS_TOOL_PINS_BUDGET overrides
BUDGET_ENV = "CS_TOOL_PINS_BUDGET"
PLATFORMS = ("macos", "windows", "linux")  # the platforms a `# fix:` line may name
# A release (`3.15.0`) and an optional pre-release (`rc1`, `a2`, `dev1`, `.dev1`); the pre-release ends at a word edge,
# so a hash such as `a1b2c3` is not one.
VERSION = re.compile(r"(?P<rel>\d+(?:\.\d+)*)(?:[-.]?(?P<pre>(?:alpha|beta|rc|dev|pre)\d*|[abc]\d+)(?![A-Za-z0-9]))?", re.I)
READ_LINE = re.compile(r"#\s*read:\s*(\S+)\s*=\s*(\S.*)$", re.I)
MATCH_LINE = re.compile(r"#\s*match:\s*(\S+)\s*=\s*(\S.*)$", re.I)
FIX_WORD = re.compile(r"#\s*fix:", re.I)
FIX_LINE = re.compile(r"#\s*fix:\s*(\S+)\s+(\S+)\s*=\s*(\S.*)$", re.I)


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
    """Returns what parse_text returns for the file at `path`."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except UnicodeDecodeError:
        raise PinFileError("%s: not UTF-8 text; save the file as UTF-8" % path)
    return parse_text(text, path)


def parse_text(text, path):
    """Returns (pins, commands, matchers, fixes): pins is a list of (tool, version, line number); commands maps tool to its
    read commands, in file order; matchers maps tool to its compiled `# match:` regex; fixes maps (tool, platform) to its
    `# fix:` command. `path` only names the file in a refusal."""
    if text.startswith("\ufeff"):  # a byte-order mark at the start is not part of the first tool name (`parse` drops it as it reads)
        text = text[1:]
    pins, commands, matchers, fixes = [], {}, {}, {}
    lines = text.splitlines()
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            read = READ_LINE.match(line)
            if read:
                if "\x00" in read.group(2):
                    raise PinFileError("%s line %d: the read command holds a NUL byte" % (path, number))
                commands.setdefault(read.group(1), []).append(read.group(2).strip())
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
            if FIX_WORD.match(line):
                fix = FIX_LINE.match(line)
                if fix is None:
                    raise PinFileError("%s line %d: expected `# fix: <tool> <%s> = <command>`, got %r"
                                       % (path, number, "|".join(PLATFORMS), line))
                platform = fix.group(2).lower()
                if platform not in PLATFORMS:
                    raise PinFileError("%s line %d: the `# fix:` platform %r is none of %s" % (path, number, fix.group(2), ", ".join(PLATFORMS)))
                if "\x00" in fix.group(3):
                    raise PinFileError("%s line %d: the fix command holds a NUL byte" % (path, number))
                if (fix.group(1), platform) in fixes:
                    raise PinFileError("%s line %d: a second `# fix:` line for %s on %s" % (path, number, fix.group(1), platform))
                fixes[(fix.group(1), platform)] = fix.group(3).strip()
                continue
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
    for tool, _ in fixes:
        if tool not in pinned:
            raise PinFileError("%s: `# fix:` names %s, which no line pins" % (path, tool))
    return pins, commands, matchers, fixes


def run_version_command(command, deadline=None):
    """(output, program): the command's output and the program path it ran from, or (None, None) when it cannot run, exits non-zero
    or has no time left. No shell runs the line. `deadline` is a time.monotonic() value: a read starts only before it and ends by it;
    None gives the read RUN_TIMEOUT."""
    try:
        words = shlex.split(command, posix=(os.name != "nt"))
    except ValueError:
        return None, None
    if os.name == "nt":  # a non-POSIX split keeps the quote marks
        words = [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "\"'" else w for w in words]
    program = shutil.which(words[0]) if words else None  # `which` resolves a Windows .cmd shim by PATHEXT
    if program is None or "windowsapps" in re.split(r"[\\/]", program.lower()):
        return None, None
    timeout = RUN_TIMEOUT if deadline is None else deadline - time.monotonic()
    if timeout <= 0:
        return None, None
    try:
        # nowindow: other repos run this file alone, so hooks/_nowindow.py is not beside it; a version command runs in a CI or terminal console
        proc = subprocess.run([program] + words[1:], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, None
    return (proc.stdout, program) if proc.returncode == 0 else (None, None)


def read_tool(commands, matcher, deadline=None):
    """(version, program) from the first command that runs and prints one, or (None, None) when none does."""
    for command in commands:
        output, program = run_version_command(command, deadline)
        number = read_version(output, matcher) if output is not None else None
        if number is not None:
            return number, program
    return None, None


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


def behind(pin, found):
    """True when `found` is older than `pin`, compared number by number at the precision `pin` states: `2.9.0` is behind `2.10`,
    `2.9.9` behind `3`, and `3.15.0rc1` behind `3.15`. A version newer than the pin, or equal to it, is not behind."""
    want, have = VERSION.fullmatch(pin), VERSION.fullmatch(found)
    if want is None or have is None:
        return False
    wanted = [int(n) for n in want.group("rel").split(".")]
    got = [int(n) for n in have.group("rel").split(".")][:len(wanted)]
    got += [0] * (len(wanted) - len(got))
    if got != wanted:
        return got < wanted
    want_pre = (want.group("pre") or "").lower()
    have_pre = (have.group("pre") or "").lower()
    if want_pre == have_pre:
        return False
    if not want_pre:  # a pre-release comes before its release
        return True
    return bool(have_pre) and have_pre < want_pre


def platform_key():
    """The platform a `# fix:` line names for this machine."""
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def budget_seconds():
    """The time all of one `--behind` run's reads share: CS_TOOL_PINS_BUDGET when it holds a positive number, else BEHIND_BUDGET."""
    try:
        value = float(os.environ.get(BUDGET_ENV, ""))
    except ValueError:
        return BEHIND_BUDGET
    return value if value > 0 else BEHIND_BUDGET


def machine_rows(path, timeout=None, text=None):
    """One row per pin, read on this machine: (tool, pin, found, program, verdict, fix). verdict is `matched`, `ahead`, `behind` or
    `unknown` (found and program are None then); fix is this platform's `# fix:` command, or None when the file has none for it.
    The file is `text` when given (`path` then only names it), else the one at `path`. `timeout` is the time all the reads share
    (default budget_seconds()): a read it cuts reads as unknown, and no version command starts after it. Raises PinFileError or OSError
    when the file cannot be read as pins. The one home of the per-machine read: the session start hook and the ready run call it."""
    pins, commands, matchers, fixes = parse(path) if text is None else parse_text(text, path)
    deadline = time.monotonic() + (budget_seconds() if timeout is None else timeout)
    rows = []
    for tool, pin, _ in pins:
        found, program = read_tool(commands.get(tool, [tool + " --version"]), matchers.get(tool), deadline)
        fix = fixes.get((tool, platform_key()))
        if found is None:
            verdict = "unknown"
        elif matches(pin, found):
            verdict = "matched"
        else:
            verdict = "behind" if behind(pin, found) else "ahead"
        rows.append((tool, pin, found, program, verdict, fix))
    return rows


def behind_line(row):
    """The one line that tells the owner what a tool needs; None for a row that is no problem. A BEHIND line holds the version found,
    the path it ran from and this platform's fix, or says the file has none."""
    tool, pin, found, program, verdict, fix = row
    if verdict == "unknown":
        return "tool-pins: %s unknown: its version command did not run, ran out of time or printed no version" % tool
    if verdict != "behind":
        return None
    head = "BEHIND tool-pins: %s pinned %s, found %s at %s;" % (tool, pin, found, program)
    if fix is None:
        return "%s %s has no `# fix: %s %s` line in %s, so name the fix by hand" % (head, platform_key(), tool, platform_key(), PIN_FILE)
    return "%s the owner runs this fix: %s" % (head, fix)


def run_behind(root):
    """`--behind ROOT`: print each row, exit 3 on a tool behind, 1 on an unknown or a refused file, else 0. Problem lines print as
    `BEHIND ...` or `tool-pins: <tool> unknown ...`; a line for a tool at or ahead of its pin starts `ok `, so a caller that shows only
    problems drops those."""
    path = os.path.join(root, PIN_FILE)
    try:
        rows = machine_rows(path)
    except (OSError, PinFileError) as e:
        print("tool-pins: unknown: %s" % e)
        return 1
    unknowns = lates = 0
    for row in rows:
        line = behind_line(row)
        tool, pin, found, _, verdict, _ = row
        if line is not None:
            print(line)
            unknowns += verdict == "unknown"
            lates += verdict == "behind"
        elif verdict == "ahead":
            print("ok tool-pins: %s pinned %s, found %s: ahead of the pin, no failure" % (tool, pin, found))
        else:
            print("ok tool-pins: %s pinned %s, found %s: matched" % (tool, pin, found))
    if unknowns:
        return 1
    return LOCAL_MISMATCH if lates else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare the tools on this machine with a repo's .tool-versions.")
    parser.add_argument("--file", help="the pin file; default: .tool-versions at the root of the repo this runs in")
    parser.add_argument("--local", action="store_true", help="note a mismatch and exit 3")
    parser.add_argument("--behind", metavar="ROOT", help="read ROOT/.tool-versions: BEHIND lines with the fix, exit 3 when a tool is behind its pin, 0 when none is, 1 on an unknown")
    args = parser.parse_args(argv)
    if args.behind is not None:
        return run_behind(args.behind)

    path = args.file
    if path is None:
        root = repo_root(os.getcwd())
        if root is None:
            print("tool-pins: unknown: no git repo here, so no %s to read; pass --file" % PIN_FILE)
            return 1
        path = os.path.join(root, PIN_FILE)
    try:
        pins, commands, matchers, _ = parse(path)
    except (OSError, PinFileError) as e:
        print("tool-pins: %s" % e)
        return 1

    mismatches = unknowns = 0
    for tool, pin, _ in pins:
        number, _ = read_tool(commands.get(tool, [tool + " --version"]), matchers.get(tool))
        if number is None:
            print("tool-pins: %s unknown: its version command did not run or printed no version" % tool)
            unknowns += 1
        elif matches(pin, number):
            print("tool-pins: %s pinned %s, found %s: matched" % (tool, pin, number))
        else:
            print("%stool-pins: %s pinned %s, found %s; move the pin or the tool" % ("" if args.local else "FAIL ", tool, pin, number))
            mismatches += 1
    if unknowns:
        return 1
    if mismatches:
        return LOCAL_MISMATCH if args.local else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
