#!/usr/bin/env python3
"""Fails when a decision record that a change adds or edits declares no kind for its ruling.

Each ruling declares its kind, one line per item, outside fenced text:

    Kind: build                          or      Kind: process
    Plan: <path>#<slug> (<platform>)             Home: rule:<id>   (a CLAUDE.md rule marker)
    Plan: <path>#<slug> (<platform>)             Home: <path>      (an existing file)

A build ruling has one Plan line per platform. `<slug>` is the GitHub slug of a heading in the
plan file. Only records the diff adds or changes are checked. An old record is checked on its
next touch, so the next touch brings its Kind line.

NAMED LIMIT. The lint cannot know which platforms a ruling needs, so it cannot check that
every platform has a Plan line. It checks each line that is there.

    python3 lint/check_ruling_kind.py [--base REF] [file ...]   # files given: check those, skip git
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = "decisions/"
RULE_FILES = ("CLAUDE.md", "output-styles/shiv-stylisms.md")
ANCHOR_RE = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
HEADING_RE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
PLAN_RE = re.compile(r"^(\S+)#(\S+) \(([^()\s][^()]*)\)$")


def read(rel):
    try:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8", newline="") as f:
            return f.read().replace("\r\n", "\n")
    except OSError:
        return None


def unfenced(text):
    """Yield the lines outside fenced text."""
    fence = None
    for line in text.split("\n"):
        m = FENCE_RE.match(line)
        if m and fence in (None, m.group(1)):
            fence = None if fence else m.group(1)
        elif not fence:
            yield line


def slugs(text):
    """GitHub heading slugs: lowercase, drop punctuation, spaces to hyphens, repeats get -N."""
    seen, out = {}, set()
    for line in unfenced(text):
        m = HEADING_RE.match(line)
        if m:
            s = re.sub(r"[^\w\- ]", "", m.group(1).lower()).replace(" ", "-")
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if not n else "%s-%d" % (s, n))
    return out


def rule_ids():
    return {i for rel in RULE_FILES for i in ANCHOR_RE.findall(read(rel) or "")}


def field(lines, name):
    return [m.group(1).strip() for m in (re.match(name + r":(.*)$", x) for x in lines) if m]


def problems(rel):
    text = read(rel)
    if text is None:
        return ["cannot read the record"]
    lines = list(unfenced(text))
    kinds = field(lines, "Kind")
    if len(kinds) != 1:
        return ["needs exactly one Kind line (Kind: build or Kind: process), found %d" % len(kinds)]
    kind = kinds[0]
    if kind == "build":
        plans = field(lines, "Plan")
        if not plans:
            return ["Kind: build needs a Plan line: Plan: <path>#<slug> (<platform>)"]
        return [p for p in map(plan_problem, plans) if p]
    if kind == "process":
        homes = field(lines, "Home")
        if not homes:
            return ["Kind: process needs a Home line: Home: rule:<id> or Home: <path>"]
        ids = rule_ids()
        return [p for p in (home_problem(h, ids) for h in homes) if p]
    return ["Kind must be build or process, not '%s'" % kind]


def plan_problem(plan):
    m = PLAN_RE.match(plan)
    if not m:
        return "Plan line '%s' is not <path>#<slug> (<platform>)" % plan
    path, slug, _platform = m.groups()
    body = read(path)
    if body is None:
        return "Plan file %s does not exist" % path
    if slug not in slugs(body):
        return "Plan slug %s is not a heading in %s" % (slug, path)


def home_problem(home, ids):
    if home.startswith("rule:"):
        if home[5:] not in ids:
            return "Home %s is not a rule marker in CLAUDE.md" % home
    elif not home or read(home) is None:
        return "Home '%s' is not an existing file or rule:<id>" % home


def changed(base):
    r = subprocess.run(["git", "diff", "--name-only", "--diff-filter=d", base + "...HEAD"],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        print("check_ruling_kind: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there
    return r.stdout.split("\n")


args = sys.argv[1:]
base = "origin/main"
if "--base" in args:
    i = args.index("--base")
    base = args[i + 1]
    del args[i:i + 2]
files = args or changed(base)
bad = 0
for f in files:
    f = f.strip()
    if f.startswith(DIR) and f.endswith(".md"):
        for p in problems(f):
            bad = 1
            print("check_ruling_kind: FAIL: %s: %s" % (f, p))
sys.exit(bad)
