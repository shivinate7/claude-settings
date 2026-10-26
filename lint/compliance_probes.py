#!/usr/bin/env python3
"""The compliance-check probes that need code: folder shape, screen readiness and lane caps.

    python3 lint/compliance_probes.py layout  <child root>
    python3 lint/compliance_probes.py design  <child root>
    python3 lint/compliance_probes.py lanecap <child root>

Each group reads only: tracked files (`git ls-files`), and the files it names. One line per item,
then one verdict line. Exit 0: in shape, not rolled out, or n/a. Exit 1: a gap. Exit 2: the probe
cannot run, so the group is unknown.

layout: lint/layout.json through lint/layout.py, plus the child's extras file. It names each
  folder that is neither a layout kind nor an extra, and each core kind the child lacks. A child
  with no extras file is "not rolled out": it exits 0, and lists the same findings as a preview.
design: screen readiness against ux/. The shoot config names the screens, sizes and themes. The
  shared `bin/shoot` is the screenshot command. One token file. Each item has its own grade.
lanecap: a guessed lane cap in a brief or a plan (rule parallelism-no-guessed-lane-cap). A line that
  names the owner or a ruling is an owner-named cap, and passes. A cap in quotes is cited, and passes.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
import layout  # noqa: E402  the one home of every kind's path
import _nowindow  # noqa: E402  the one home of a no-window child start
from ui_suffixes import UI_SUFFIXES  # noqa: E402  the files ste_lint reads as front-end copy

# bin/shoot holds the same default; lint/test_compliance_probes.py pins the two equal.
SHOOT_CONFIG = ".claude/shoot.json"
# Claude Code's own folders in .claude. Claude Code fixes their names, so no repo chooses them.
CLAUDE_CODE_DIRS = {"agents", "commands", "hooks", "skills", "output-styles", "worktrees"}
TOKEN_FILE = re.compile(r"^(design[-_]?)?tokens\.(json|css|scss|ts|js|swift)$", re.I)
# Screen files beyond the copy suffixes: SwiftUI, Astro and Svelte views.
SCREEN_SUFFIXES = set(UI_SUFFIXES) | {".swift", ".astro", ".svelte"}
SCREENSHOT_SCRIPT = re.compile(r"(^|/)[^/]*(screenshot|shoot)[^/]*\.(sh|mjs|js|ts|py)$", re.I)
MAKE_TARGET = re.compile(r"^(screenshot|shoot)[\w-]*\s*:", re.M)
NUM = r"(\d+|one|two|three|four|five|six)"
WHO = r"(lanes?|threads?|agents?|workers?|builders?|sessions?)"
LANE_CAP = re.compile(
    r"\b(at most|no more than|up to|max(imum)?( of)?|cap(ped)? (at|of)) " + NUM
    + r" (parallel |concurrent |build |open |running )?" + WHO + r"\b"
    r"|\b" + NUM + r" or " + NUM + r" (" + WHO + r" )?at a time\b"
    r"|\b" + NUM + r" " + WHO + r" at a time\b", re.I)
OWNER_NAMED = re.compile(r"\b(owner|ruling|ruled)\b", re.I)
QUOTES = "\"'`\u201c\u2018"  # a cap in quotes is cited, not set


class CannotRun(Exception):
    pass


def tracked(root):
    """Tracked file paths of `root`, `/` separated."""
    try:
        done = _nowindow.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
    except OSError as err:
        raise CannotRun("git: %s" % err)
    if done.returncode != 0:
        raise CannotRun("git ls-files: %s" % done.stderr.decode(errors="replace").strip())
    return [p for p in done.stdout.decode("utf-8", "replace").split("\0") if p]


def read(root, rel):
    try:
        with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as handle:
            return handle.read()
    except (OSError, UnicodeDecodeError):
        return None


def finish(group, lines, verdict, code):
    for line in lines:
        print(line)
    print("%s: %s" % (group, verdict))
    return code


def probe_layout(root):
    try:
        rolled = layout.rolled_out(root)
        kinds = layout.kinds(root)
        extras = layout.layout().get("extras", "")
    except layout.LayoutError as err:
        raise CannotRun(str(err))
    homes = {k["path"].strip("/") for k in kinds.values()}
    above = {h.rsplit("/", i)[0] for h in homes for i in range(1, h.count("/") + 1)}
    legacy = {layout.legacy(n): n for n in kinds if kinds[n].get("set") != "extra" and layout.legacy(n) not in homes}

    def covered(folder):
        return folder in above or any(folder == h or folder.startswith(h + "/") for h in homes)

    stray = set()
    for rel in tracked(root):
        parts = rel.split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            folder = "/".join(parts[:depth])
            parent = "/".join(parts[:depth - 1])
            if covered(folder):
                if folder in above:
                    continue
                break
            if depth == 1 and folder.startswith("."):
                break  # a tool's own folder (.github, .vscode), not a repo choice
            if parent == ".claude" and parts[depth - 1] in CLAUDE_CODE_DIRS:
                break
            stray.add(folder)
            break
    lines = []
    for folder in sorted(stray):
        note = " (legacy home of %s, moves to %s)" % (legacy[folder], kinds[legacy[folder]]["path"]) if folder in legacy else ""
        lines.append("  folder %s/: neither a layout kind nor an extra%s" % (folder, note))
    for name, kind in kinds.items():
        if kind.get("set") == "core" and not os.path.exists(os.path.join(root, *kind["path"].strip("/").split("/"))):
            lines.append("  missing core kind %s: %s" % (name, kind["path"]))
    if not rolled:
        lines = ["  preview" + line[1:] for line in lines]
        return finish("layout", lines, "not rolled out (no %s); %d preview finding(s)" % (extras, len(lines)), 0)
    if lines:
        return finish("layout", lines, "out - %d finding(s)" % len(lines), 1)
    return finish("layout", lines, "in shape", 0)


def shoot_config(root):
    """(config dict or None, why not)."""
    text = read(root, SHOOT_CONFIG)
    if text is None:
        return None, "no %s" % SHOOT_CONFIG
    try:
        data = json.loads(text)
    except ValueError as err:
        return None, "%s does not parse: %s" % (SHOOT_CONFIG, err)
    return (data, "") if isinstance(data, dict) else (None, "%s is not an object" % SHOOT_CONFIG)


def own_screenshot_command(root, files):
    # A dot folder holds a tool's copy (a vendored skill), not the repo's own command.
    found = [f for f in files if SCREENSHOT_SCRIPT.search(f) and not re.search(r"(^|/)(\.|node_modules/|vendor/)", f)]
    for make in ("Makefile", "makefile", "GNUmakefile"):
        text = read(root, make) if make in files else None
        if text:
            found += ["%s target %s" % (make, m.group(0).rstrip(": ")) for m in MAKE_TARGET.finditer(text)]
    for pkg in (f for f in files if f == "package.json" or f.endswith("/package.json")):
        try:
            scripts = json.loads(read(root, pkg) or "{}").get("scripts") or {}
        except (ValueError, AttributeError):
            continue
        found += ["%s script %s" % (pkg, k) for k in scripts if re.search("screenshot|shoot", k, re.I)]
    return found


def probe_design(root):
    files = tracked(root)
    screens = [f for f in files if os.path.splitext(f)[1].lower() in SCREEN_SUFFIXES]
    if not screens:
        return finish("design", [], "n/a - no screen files", 0)
    grades, lines = [], []

    def item(name, grade, why):
        grades.append(grade)
        lines.append("  %s: %s - %s" % (name, grade, why))

    config, why = shoot_config(root)
    if config is None:
        for name in ("screens named", "sizes named", "themes named"):
            item(name, "gap", why)
    else:
        routes = config.get("routes")
        if isinstance(routes, list) and routes:
            item("screens named", "pass", "%d route(s) in %s" % (len(routes), SHOOT_CONFIG))
        else:
            item("screens named", "gap", "%s has no routes" % SHOOT_CONFIG)
        for key in ("sizes", "themes"):
            item(key + " named", "pass", ("%s in %s" % (config[key], SHOOT_CONFIG)) if key in config else "shoot's default")
    own = own_screenshot_command(root, files)
    if config is not None:
        item("screenshot command", "pass", "the shared shoot reads %s" % SHOOT_CONFIG)
    elif own:
        item("screenshot command", "partial", "own command, not the shared shoot: %s" % "; ".join(own))
    else:
        item("screenshot command", "gap", "none found")
    tokens = [f for f in files if TOKEN_FILE.match(f.rsplit("/", 1)[-1]) and "test" not in f.lower()]
    sources = [f for f in tokens if "generated" not in (read(root, f) or "")[:400].lower()]
    if len(sources) == 1:
        item("token file", "pass", "%s%s" % (sources[0], "" if len(tokens) == 1 else ", plus %d generated" % (len(tokens) - 1)))
    elif not sources:
        item("token file", "gap", "no tokens file")
    else:
        item("token file", "partial", "%d token sources: %s" % (len(sources), ", ".join(sources)))
    copy = sum(1 for f in screens if os.path.splitext(f)[1].lower() in UI_SUFFIXES)
    lines.append("  ui copy: known gap - CI's STE step reads Markdown only, so %d UI file(s) get no sentence, bloat or double-negative check" % copy)
    worst = "out" if "gap" in grades else "partial" if "partial" in grades else "in shape"
    return finish("design", lines, worst, 0 if worst == "in shape" else 1)


def probe_lanecap(root):
    try:
        plans = layout.candidates(root, "plans")
    except (layout.LayoutError, KeyError) as err:
        raise CannotRun(str(err))
    where = [f for f in tracked(root) if f.endswith(".md") and (f.startswith(tuple(p + "/" for p in plans)) or re.search(r"(^|/)[^/]*brief", f, re.I))]
    hits, owned = [], []
    for rel in where:
        for number, text in enumerate((read(root, rel) or "").splitlines(), 1):
            if any(m.start() == 0 or text[m.start() - 1] not in QUOTES for m in LANE_CAP.finditer(text)):
                (owned if OWNER_NAMED.search(text) else hits).append("%s:%d: %s" % (rel, number, text.strip()[:160]))
    lines = ["  guessed cap? %s" % h for h in hits] + ["  owner-named, passes: %s" % h for h in owned]
    if hits:
        return finish("lanecap", lines, "out - %d cap(s) to read in %d brief or plan file(s)" % (len(hits), len(where)), 1)
    return finish("lanecap", lines, "in shape - %d brief or plan file(s) read" % len(where), 0)


GROUPS = {"layout": probe_layout, "design": probe_design, "lanecap": probe_lanecap}


def main(argv):
    if len(argv) != 2 or argv[0] not in GROUPS:
        print("usage: compliance_probes.py {%s} <child root>" % ",".join(GROUPS), file=sys.stderr)
        return 2
    root = os.path.abspath(argv[1])
    try:
        return GROUPS[argv[0]](root)
    except CannotRun as err:
        print("%s: unknown - %s" % (argv[0], err))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
