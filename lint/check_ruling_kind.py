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

    python3 lint/check_ruling_kind.py [--base REF] [--root DIR] [--rules-file PATH ...] [--dir FOLDER] [file ...]
        # files given: check those, skip git
        # --rules-file (repeatable): the files whose rule markers a Home may name, instead of the
        # RULE_FILES under --root. A missing file is skipped. None readable: a rule: Home is red.
        # --dir: the records folder, relative to --root. Default decisions. Only .md files under it are checked.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = "decisions/"  # the records folder; --dir replaces it
RULE_FILES = ("CLAUDE.md", "output-styles/shiv-stylisms.md")
ANCHOR_RE = re.compile(r"<!--\s*rule:([a-z0-9][a-z0-9-]*)\s*-->")
HEADING_RE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
PLAN_RE = re.compile(r"^(\S+)#(\S+) \(([^()\s][^()]*)\)$")


def read_path(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return f.read().replace("\r\n", "\n")
    except OSError:
        return None


def read(rel):
    return read_path(os.path.join(ROOT, *rel.split("/")))


def unfenced(text):
    """Yield the lines outside fenced text and HTML comments (CommonMark fence rules)."""
    fence, comment = None, False
    for line in text.split("\n"):
        if comment:
            end = line.find("-->")
            if end < 0:
                continue
            line, comment = line[end + 3:], False
        elif fence:
            m = FENCE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) and not m.group(2).strip():
                fence = None
            continue
        else:
            m = FENCE_RE.match(line)
            if m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
                fence = m.group(1)
                continue
        # Comment openers inside an inline code span are prose, so scan a masked copy.
        masked = re.sub(r"`[^`]*`", lambda m: "x" * len(m.group()), line)
        kept, pos = [], 0
        while True:
            a = masked.find("<!--", pos)
            if a < 0:
                kept.append(line[pos:])
                break
            kept.append(line[pos:a])
            b = masked.find("-->", a + 4)
            if b < 0:
                comment = True
                break
            pos = b + 3
        yield "".join(kept)


def slugs(text):
    """GitHub heading slugs: lowercase, drop punctuation, spaces to hyphens, repeats get -N."""
    seen, out = {}, set()
    for line in unfenced(text):
        m = HEADING_RE.match(line)
        if m:
            s = re.sub(r"[^\w\- ]", "", LINK_RE.sub(lambda k: k.group(1), m.group(1)).lower()).replace(" ", "-")
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if not n else "%s-%d" % (s, n))
    return out


RULES_FILES = []  # --rules-file paths; when set, they replace the RULE_FILES under ROOT


def rule_ids():
    texts = [read_path(p) for p in RULES_FILES] if RULES_FILES else [read(rel) for rel in RULE_FILES]
    return {i for t in texts for i in ANCHOR_RE.findall(t or "")}


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
    path, slug, platform = m.groups()
    if platform.strip().lower() == "none":
        return "Plan line '%s' names platform none" % plan
    body = read(path)
    if body is None:
        return "Plan file %s does not exist" % path
    if slug not in slugs(body):
        return "Plan slug %s is not a heading in %s" % (slug, path)


def home_problem(home, ids):
    if home.startswith("rule:"):
        if RULES_FILES and all(read_path(p) is None for p in RULES_FILES):
            return "Home %s cannot be checked: no --rules-file can be read" % home
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
if "--root" in args:  # the checkout to judge, for a caller whose repo is not this one
    i = args.index("--root")
    ROOT = os.path.abspath(args[i + 1])
    del args[i:i + 2]
while "--rules-file" in args:
    i = args.index("--rules-file")
    RULES_FILES.append(args[i + 1])
    del args[i:i + 2]
if "--dir" in args:  # the records folder, for a repo that keeps its records elsewhere
    i = args.index("--dir")
    DIR = os.path.normpath(args[i + 1]).replace("\\", "/").rstrip("/") + "/"
    del args[i:i + 2]
files = args or changed(base)
bad = 0
for f in files:
    f = f.strip()
    if os.path.normpath(f).replace("\\", "/").startswith(DIR) and f.endswith(".md"):
        for p in problems(os.path.normpath(f).replace("\\", "/")):
            bad = 1
            print("check_ruling_kind: FAIL: %s: %s" % (f, p))
sys.exit(bad)
