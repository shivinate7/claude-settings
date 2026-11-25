#!/usr/bin/env python3
"""The one reader of the child list: the repos that registered with claude-settings (docs/children.txt).

    python3 lint/children.py [--file PATH] list [--active]
    python3 lint/children.py [--file PATH] add owner/name id since
    python3 lint/children.py [--file PATH] scan

The file holds one line per child, sorted by name: `owner/name <GitHub repo id> <since YYYY-MM-DD>`. `#`
lines and blank lines are allowed. The id is the key. A rename changes the name, never the id, and an
archived or renamed repo stays in the file, so the list never fails on a repo's state.

list           prints each name in file order. It reads no network.
list --active  asks GitHub for each child by id. It leaves out an archived child and prints a renamed
               child's current name. A child GitHub cannot answer for prints `unknown: owner/name` on stderr,
               and the exit code is 3; the readable children are still listed.
add            writes one line at its sorted place and keeps every other line. It refuses a duplicate name
               or id, a malformed argument, and claude-settings itself (exit 2).
scan           prints each repo of the token's owner that carries .github/stamp.json and is not in the file
               (matched by id; never claude-settings). It writes nothing.

Every subcommand refuses a malformed line with its number (exit 2). The real fetch runs `gh api`, so the token
stays in gh and is never an argument or output. A read that failed is unknown, never clear or absent.
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
DEFAULT_FILE = os.path.join(os.path.dirname(HERE), "docs", "children.txt")
SELF = "shivinate7/claude-settings"
NAME = re.compile(r"[^\s/]+/[^\s/]+")
LINE = re.compile(r"([^\s/]+/[^\s/]+) (\d+) (\d{4}-\d{2}-\d{2})")
PAGE = 100


class Refused(Exception):
    """The input is wrong. The message is one line for stderr; the exit code is 2."""


def check_since(since):
    try:
        datetime.date.fromisoformat(since)
    except ValueError:
        raise Refused("since is not a date YYYY-MM-DD: %s" % since)


def check_entry(name, ident, since):
    if not NAME.fullmatch(name):
        raise Refused("name is not owner/name: %s" % name)
    if not re.fullmatch(r"\d+", ident):
        raise Refused("id is not digits: %s" % ident)
    check_since(since)
    if name == SELF:
        raise Refused("%s is not a child" % SELF)


def read_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    except OSError as e:
        raise Refused("cannot read %s: %s" % (path, e.strerror))


def parse(path, lines):
    """[(name, id, since)] for each entry line. A malformed line raises Refused naming its number."""
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.startswith("#"):
            continue
        found = LINE.fullmatch(line)
        try:
            if not found:
                raise Refused("not `owner/name id YYYY-MM-DD`")
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
    """The parsed JSON of one GitHub REST read. gh holds the token; it is never in an argument or output."""
    env = {k: v for k, v in os.environ.items() if k not in ("AI_AGENT", "CLAUDECODE")}
    try:
        done = subprocess.run(["gh", "api", path], capture_output=True, text=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError("gh api failed: %s" % type(e).__name__)
    if done.returncode != 0:
        raise RuntimeError("gh api %s: %s" % (path, done.stderr.strip()[:200]))
    return json.loads(done.stdout)


def cmd_list(rows, fetch, active):
    if not active:
        for name, _, _ in rows:
            print(name)
        return 0
    unknown = 0
    for name, ident, _ in rows:
        try:
            found = fetch("repositories/%s" % ident)
            if str(found["id"]) != ident:
                raise RuntimeError("GitHub answered with another id")
            archived, current = bool(found.get("archived")), found["full_name"]
        except Exception:
            print("unknown: %s" % name, file=sys.stderr)
            unknown += 1
            continue
        if not archived:
            print(current)
    return 3 if unknown else 0


def cmd_add(path, lines, rows, name, ident, since):
    check_entry(name, ident, since)
    if any(r[0] == name for r in rows):
        raise Refused("%s is already in the list" % name)
    if any(r[1] == ident for r in rows):
        raise Refused("id %s is already in the list under %s" % (ident, next(r[0] for r in rows if r[1] == ident)))
    new = "%s %s %s" % (name, ident, since)
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
    known = {r[1] for r in rows}
    unknown = 0
    try:
        repos = owner_repos(fetch)
    except Exception:
        print("unknown: the owner's repo listing could not be read", file=sys.stderr)
        return 3
    for repo in repos:
        name = repo["full_name"]
        if str(repo["id"]) in known or name == SELF:
            continue
        try:
            fetch("repositories/%s/contents/.github/stamp.json" % repo["id"])
        except Exception as e:
            if "404" not in str(e):
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
    add = sub.add_parser("add")
    for field in ("name", "id", "since"):
        add.add_argument(field)
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
            return cmd_add(args.file, lines, rows, args.name, args.id, args.since)
        return cmd_scan(rows, fetch)
    except Refused as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
