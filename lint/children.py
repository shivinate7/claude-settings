#!/usr/bin/env python3
"""The one reader of the child list: the repos that registered with claude-settings (docs/children.txt).

    python3 lint/children.py [--file PATH] list [--active]
    python3 lint/children.py [--file PATH] add owner/name since
    python3 lint/children.py [--file PATH] scan

The file holds one line per child, sorted by name: `owner/name <since YYYY-MM-DD>`. `#` lines and blank lines
are allowed. The name is the key. The file is public, so it holds no GitHub repo id. A renamed repo is unknown to
the reader until its line is fixed by pull request.

list           prints each name in file order. It reads no network.
list --active  asks GitHub for each child by name. It leaves out an archived child. A child GitHub cannot answer
               for, a renamed one included, prints `unknown: owner/name` on stderr, and the exit code is 3; the
               readable children are still listed.
add            writes one line at its sorted place and keeps every other line. It refuses a duplicate name, an
               extra or missing argument, a malformed argument, and claude-settings itself in any letter case
               (exit 2).
scan           prints each repo of the token's owner that carries .github/stamp.json and is not in the file
               (matched by name; never claude-settings). It writes nothing.

Every subcommand refuses a malformed line with its number (exit 2). The real fetch runs `gh api`, so the token
stays in gh and is never an argument or output. A read that failed is unknown, never clear or absent. A stamp
read is "no file" only when its HTTP status is 404; the status is read from the end of gh's error line, never
searched for in text that may hold it elsewhere, such as a repo name.
Cost: one read of the file; list --active adds one GitHub read per child; scan adds one listing page per 100
repos and one stamp read per unlisted repo. No file is written except by add.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

DEFAULT_FILE = os.path.join(os.path.dirname(HERE), "docs", "children.txt")
SELF = "shivinate7/claude-settings"
# A segment never starts with a dash and is never only dots: `..` would climb a path, a leading dash reads as an option.
SEGMENT = r"(?!-)(?!\.+(?:/|\Z))[A-Za-z0-9_.-]+"
NAME = re.compile(SEGMENT + "/" + SEGMENT)
LINE = re.compile(r"(\S+) (\d{4}-\d{2}-\d{2})")
HTTP_STATUS = re.compile(r"\(HTTP (\d{3})\)\s*$")
PAGE = 100


class Refused(Exception):
    """The input is wrong. The message is one line for stderr; the exit code is 2."""


def check_since(since):
    try:
        datetime.date.fromisoformat(since)
    except ValueError:
        raise Refused("since is not a date YYYY-MM-DD: %s" % since)


def check_entry(name, since):
    if not NAME.fullmatch(name):
        raise Refused("name is not owner/name: %s" % name)
    check_since(since)
    if name.casefold() == SELF.casefold():
        raise Refused("%s is not a child" % SELF)


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    except OSError as e:
        raise Refused("cannot read %s: %s" % (path, e.strerror))


def parse(path, lines):
    """[(name, since)] for each entry line. A malformed line raises Refused naming its number."""
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        found = LINE.fullmatch(line)
        try:
            if not found:
                raise Refused("not `owner/name YYYY-MM-DD`")
            check_entry(*found.groups())
        except Refused as e:
            raise Refused("%s line %d: %s" % (path, number, e))
        rows.append(found.groups())
    return rows


class OneLineParser(argparse.ArgumentParser):
    """A usage error is one line on stderr, exit 2, like every other refusal."""

    def error(self, message):
        self.exit(2, "%s: %s\n" % (self.prog, message))


def gh_fetch(path):
    """The parsed JSON of one GitHub REST read. gh holds the token; it is never in an argument or output.
    A failed read raises with gh's last error line at the end: it carries `(HTTP <status>)` for an HTTP failure."""
    env = {k: v for k, v in os.environ.items() if k not in ("AI_AGENT", "CLAUDECODE")}
    try:
        done = _nowindow.run(["gh", "api", path], capture_output=True, text=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("gh api %s: %s" % (path, type(e).__name__))
    if done.returncode != 0:
        said = done.stderr.strip().splitlines()
        raise RuntimeError("gh api %s: %s" % (path, said[-1] if said else "no error line"))
    return json.loads(done.stdout)


def http_status(error):
    """The HTTP status a failed read ended with, or None. Read from the end of the message only: the path before
    it holds a repo name, and a name may hold digits such as 404."""
    found = HTTP_STATUS.search(str(error))
    return int(found.group(1)) if found else None


def cmd_list(rows, fetch, active):
    if not active:
        for name, _ in rows:
            print(name)
        return 0
    unknown = 0
    for name, _ in rows:
        try:
            found = fetch("repos/%s" % name)
            # GitHub redirects a renamed repo's old name to the new one; a different name is a rename, not an answer.
            if found["full_name"].casefold() != name.casefold():
                raise RuntimeError("GitHub answered for another name")
            archived = found["archived"]
        except Exception:
            print("unknown: %s" % name, file=sys.stderr)
            unknown += 1
            continue
        if not archived:
            print(name)
    return 3 if unknown else 0


def cmd_add(path, lines, rows, fields):
    if len(fields) != 2:
        raise Refused("add takes owner/name and since, got %d: %s" % (len(fields), " ".join(fields)))
    name, since = fields
    check_entry(name, since)
    if any(r[0].casefold() == name.casefold() for r in rows):
        raise Refused("%s is already in the list" % name)
    new = "%s %s" % (name, since)
    at = len(lines)
    for number, line in enumerate(lines):
        found = LINE.fullmatch(line)
        if found and found.group(1) > name:
            at = number
            break
    lines = lines[:at] + [new] + lines[at:]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(temp, path)
    return 0


def owner_repos(fetch):
    repos, page = [], 1
    while True:
        batch = fetch("user/repos?affiliation=owner&per_page=%d&page=%d" % (PAGE, page))
        repos.extend(batch)
        if len(batch) < PAGE:
            return repos
        page += 1


def cmd_scan(rows, fetch):
    known = {r[0].casefold() for r in rows} | {SELF.casefold()}
    unknown = 0
    try:
        repos = owner_repos(fetch)
    except Exception:
        print("unknown: the owner's repo listing could not be read", file=sys.stderr)
        return 3
    for repo in repos:
        name = repo["full_name"]
        if name.casefold() in known:
            continue
        try:
            fetch("repos/%s/contents/.github/stamp.json" % name)
        except Exception as e:
            if http_status(e) != 404:
                print("unknown: %s" % name, file=sys.stderr)
                unknown += 1
            continue
        print(name)
    return 3 if unknown else 0


def main(argv=None, fetch=None):
    fetch = fetch or gh_fetch
    parser = OneLineParser(prog="children.py", description="The child list reader.")
    parser.add_argument("--file", default=DEFAULT_FILE)
    sub = parser.add_subparsers(dest="cmd", required=True, parser_class=OneLineParser)
    sub.add_parser("list").add_argument("--active", action="store_true")
    sub.add_parser("add").add_argument("fields", nargs="*", metavar="owner/name since")
    sub.add_parser("scan")
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    try:
        lines = read_lines(args.file)
        rows = parse(args.file, lines)
        if args.cmd == "list":
            return cmd_list(rows, fetch, args.active)
        if args.cmd == "add":
            return cmd_add(args.file, lines, rows, args.fields)
        return cmd_scan(rows, fetch)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
