#!/usr/bin/env python3
"""The compliance-check probes that need code: folder shape, screen readiness and lane caps.

    python3 lint/compliance_probes.py layout  <child root>
    python3 lint/compliance_probes.py design  <child root>
    python3 lint/compliance_probes.py lanecap <child root>
    python3 lint/compliance_probes.py playwright <child root>
    python3 lint/compliance_probes.py ios <child root>
    python3 lint/compliance_probes.py words <child root>
    python3 lint/compliance_probes.py scorecard <child root> < group-lines

Each group reads only: tracked files (`git ls-files`), and the files it names. One line per item,
then one verdict line. Exit 0: in shape, not rolled out, or n/a. Exit 1: a gap. Exit 2: the probe
cannot run, so the group is unknown.

layout: lint/layout.json through lint/layout.py, plus the child's extras file. It names each
  folder that is neither a layout kind nor an extra, and each core kind the child lacks. A child
  with no extras file, or none marked "rolled-out": true, is "not rolled out": it exits 0, and
  lists the same findings as a preview.
design: screen readiness against docs/design/. The shoot config names the screens, sizes and themes. The
  shared `bin/shoot` is the screenshot command, and a config it would refuse is a gap. One token
  file: a `tokens.*` file (the layout's tokens path is one), tests and generated files aside. Each item
  has its own grade.
lanecap: a guessed lane cap in a brief or a plan (rule parallelism-no-guessed-lane-cap). A line that
  cites its owner or ruling source, "(owner, ...)" or "owner ... <date>", passes. A cap inside a pair
  of quotes is cited, and passes.
playwright: a Playwright install that also runs apt (`--with-deps`, `install-deps`) in a workflow, an
  action, a Makefile, a shell script, a Dockerfile, a justfile, a Taskfile, a dev container file or a
  package.json script. The runner image already has Chromium's libraries, and that apt step once
  timed a job out on a slow mirror. The shared actions/playwright-setup runs no apt for Chromium.
  WebKit and Firefox opt in through its `system-deps` input, which this probe does not flag.
  Comments do not count.
ios: drift from the iOS standard of skills/ios-apps, one item per line: the make targets, the ship
  path, the project file, the Kit package, Swift 6, the CI runner, the CI checks, slow tests on each
  pull request, test diagnostics (each `xcodebuild test` run in a workflow, the Makefile or a tracked
  shell script sets `-collect-test-diagnostics never`), and account IDs in the repo. A repo with no
  iOS app is n/a. Comments do not count.
words: each retired word in a checked repo, one item per line: `  <word>: <file>:<line> <detail>`, with `-` for
  the line of a path hit. The word list is read live from lint/check_glossary.py and the GLOSSARY.md beside
  it: its path, identifier, rule anchor, record slug and hook message reads, run on the child's tracked
  files. The probe holds no list. A glossary that cannot be read, or has no rows, or a file that does not
  parse, makes the group unknown. It prints the claude-settings commit whose glossary it read.
scorecard: not a probe. It reads the group lines from stdin and rewrites the layout's scorecard kind file in
  the child, in place: one table, columns Group, Score, Gold standard, Gap, Source. It adds the row
  for the STE lint's gap on UI files, a known gap.
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
# The pinned CI image of the iOS standard (skills/ios-apps). The starter writes the same name; its test pins the two equal.
IOS_RUNNER = "macos-26"
# The account values bin/ios-ship reads from ~/.config/ios-ship/account.json. A test pins them to bin/ios-ship.
ACCOUNT_KEYS = ("team_id", "device_udid", "asc_key_path", "asc_key_id", "asc_issuer_id")
# Claude Code's own folders in .claude. Claude Code fixes their names, so no repo chooses them.
CLAUDE_CODE_DIRS = {"agents", "commands", "hooks", "skills", "output-styles", "worktrees"}
TOKEN_FILE = re.compile(r"^(design[-_]?)?tokens\.(json|css|scss|ts|js|swift)$", re.I)
# Screen files beyond the copy suffixes: SwiftUI, Astro and Svelte views.
SCREEN_SUFFIXES = set(UI_SUFFIXES) | {".swift", ".astro", ".svelte"}
SCREENSHOT_SCRIPT = re.compile(r"(^|/)[^/]*(screenshot|shoot)[^/]*\.(sh|mjs|js|ts|py)$", re.I)
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|fixtures?|spec)/|(^|/)test_[^/]*$|\.(test|spec)\.[^/]+$", re.I)
GENERATED = re.compile(r"(?<!not )\bgenerated\b|\bdo not edit\b", re.I)
MAKE_TARGET = re.compile(r"^(screenshot|shoot)[\w-]*\s*:", re.M)
NUM = r"(\d+|one|two|three|four|five|six)"
RANGE = NUM + r"( ?(-|to|or) ?" + NUM + r")?"
WHO = r"((parallel|concurrent|build|open|running|workflow|cloud|at once) ){0,2}(lanes?|threads?|agents?|workers?|builders?)\b"
LANE_CAP = re.compile(
    r"\b(at most|no more than|up to|max(imum)?( of)?|cap(ped)? (at|of)|limit(ed)? (to|of|at)) " + RANGE + " " + WHO
    + r"|\b" + RANGE + " " + WHO + r"( max(imum)?\b| at a time\b| at once\b| in parallel\b)"
    + r"|\b" + NUM + r" or " + NUM + r" at a time\b", re.I)
# An owner-named cap carries its source, as the repos write a ruling: "(owner, <date>)".
OWNER_NAMED = re.compile(r"\((owner|ruling)\b|\b(owner|ruling)\b[^.]*\d{4}-\d{2}-\d{2}", re.I)
QUOTES = {"\"": "\"", "'": "'", "`": "`", "\u201c": "\u201d", "\u2018": "\u2019"}  # a cap in quotes is cited, not set


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
    # The group line comes first, as the skill writes it: scorecard files each item under the group line above it.
    print("%s: %s" % (group, verdict))
    for line in lines:
        print(line)
    return code


def probe_layout(root):
    try:
        rolled = layout.rolled_out(root)
        kinds = layout.kinds(root)
        extras = layout.layout().get("extras", "")
        kept = layout.unmoved(root)  # a kind legacy-repos keeps where this repo holds it now
    except layout.LayoutError as err:
        raise CannotRun(str(err))
    homes = {k["path"].strip("/") for k in kinds.values()} | set(kept.values())
    above = {h.rsplit("/", i)[0] for h in homes for i in range(1, h.count("/") + 1)}
    legacy = {layout.legacy(n): n for n in kinds if kinds[n].get("set") != "extra" and layout.legacy(n) not in homes}

    def covered(folder):
        return folder in above or any(folder == h or folder.startswith(h + "/") for h in homes)

    files = tracked(root)
    stray = set()
    for rel in files:
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
        home = kept.get(name, kind["path"].strip("/"))
        if kind.get("set") == "core" and not any(f == home or f.startswith(home + "/") for f in files):
            lines.append("  missing core kind %s: %s" % (name, kind["path"]))
    if not rolled:
        lines = ["  preview" + line[1:] for line in lines]
        return finish("layout", lines, "not rolled out (no %s with rolled-out: true); %d preview finding(s)" % (extras, len(lines)), 0)
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
    if not isinstance(data, dict):
        return None, "%s is not an object" % SHOOT_CONFIG
    # The refusals bin/shoot makes, so a config shoot would refuse is never a pass.
    routes, sizes, themes = data.get("routes"), data.get("sizes", [1]), data.get("themes", ["light"])
    if not isinstance(data.get("baseUrl"), str) or not data["baseUrl"]:
        return None, "%s needs baseUrl" % SHOOT_CONFIG
    if not isinstance(routes, list) or not routes or not all(isinstance(r, str) or (isinstance(r, dict) and isinstance(r.get("path"), str)) for r in routes):
        return None, "%s needs a list of routes" % SHOOT_CONFIG
    if not isinstance(sizes, list) or not sizes or not all(isinstance(w, int) and not isinstance(w, bool) and w > 0 for w in sizes):
        return None, "%s: sizes is not a list of widths" % SHOOT_CONFIG
    if not isinstance(themes, list) or not themes or not all(t in ("light", "dark") for t in themes):
        return None, "%s: themes holds light and dark only" % SHOOT_CONFIG
    if "ignoreHTTPSErrors" in data and not isinstance(data["ignoreHTTPSErrors"], bool):
        return None, "%s: ignoreHTTPSErrors is true or false" % SHOOT_CONFIG
    for route in routes:
        if not isinstance(route, dict):
            continue
        if "steps" in route and not shoot_steps_ok(route["steps"]):
            return None, "%s: steps is a non-empty list; each route step is {click: css} or {wait: css, state: visible or hidden}" % SHOOT_CONFIG
        stored = route.get("localStorage", {})
        if not isinstance(stored, dict) or not all(isinstance(v, str) for v in stored.values()):
            return None, "%s: localStorage is an object of strings" % SHOOT_CONFIG
    return data, ""


def shoot_steps_ok(steps):
    """True for a non-empty list of route steps: {click: css} and {wait: css, state?: visible|hidden}."""
    def selector(v):
        return isinstance(v, str) and v.strip() != ""

    def step_ok(step):
        if not isinstance(step, dict):
            return False
        if "click" in step:
            return list(step) == ["click"] and selector(step["click"])
        if "wait" in step:
            return set(step) <= {"wait", "state"} and selector(step["wait"]) and step.get("state", "visible") in ("visible", "hidden")
        return False
    return isinstance(steps, list) and bool(steps) and all(step_ok(s) for s in steps)


def own_screenshot_command(root, files):
    # A dot folder holds a tool's copy (a vendored skill), not the repo's own command.
    found = [f for f in files if SCREENSHOT_SCRIPT.search(f) and not TEST_PATH.search(f)
             and not re.search(r"(^|/)(\.|node_modules/|vendor/)", f)]
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
        item("screens named", "pass", "%d route(s) in %s" % (len(config["routes"]), SHOOT_CONFIG))
        for key in ("sizes", "themes"):
            item(key + " named", "pass", ("%s in %s" % (config[key], SHOOT_CONFIG)) if key in config else "shoot's default")
    own = own_screenshot_command(root, files)
    if config is not None:
        item("screenshot command", "pass", "the shared shoot reads %s" % SHOOT_CONFIG)
    elif own and why.startswith("no "):
        item("screenshot command", "partial", "own command, not the shared shoot: %s" % "; ".join(own))
    else:
        item("screenshot command", "gap", why if not why.startswith("no ") else "none found")
    tokens = [f for f in files if TOKEN_FILE.match(f.rsplit("/", 1)[-1]) and not TEST_PATH.search(f)]
    sources = [f for f in tokens if not GENERATED.search((read(root, f) or "")[:400])]
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


def cited(text, match):
    """True when the cap sits inside a pair of quotes, so the line quotes it."""
    start, end = match.start(), match.end()
    before = text[start - 1] if start else ""
    return before in QUOTES and text[end:end + 1] == QUOTES[before]


def probe_lanecap(root):
    try:
        plans = layout.candidates(root, "plans")
    except (layout.LayoutError, KeyError) as err:
        raise CannotRun(str(err))
    where = [f for f in tracked(root) if f.endswith(".md") and (f.startswith(tuple(p + "/" for p in plans)) or re.search(r"(^|/)[^/]*brief", f, re.I))]
    hits, owned = [], []
    for rel in where:
        for number, text in enumerate((read(root, rel) or "").splitlines(), 1):
            if any(not cited(text, m) for m in LANE_CAP.finditer(text)):
                (owned if OWNER_NAMED.search(text) else hits).append("%s:%d: %s" % (rel, number, text.strip()[:160]))
    lines = ["  guessed cap? %s" % h for h in hits] + ["  owner-named, passes: %s" % h for h in owned]
    if hits:
        return finish("lanecap", lines, "out - %d cap(s) to read in %d brief or plan file(s)" % (len(hits), len(where)), 1)
    return finish("lanecap", lines, "in shape - %d brief or plan file(s) read" % len(where), 0)


PW_FILE = re.compile(r"(^|/)(\.github/workflows/[^/]+\.ya?ml|action\.ya?ml|(GNU)?[Mm]akefile|[^/]+\.sh"
                     r"|Dockerfile[^/]*|[^/]+\.Dockerfile|[Jj]ustfile|Taskfile[^/]*\.ya?ml|\.devcontainer/[^/]+)$")
FOLDED = re.compile(r"^(\s*)(- )?[\w-]+:\s*>[+-]?\d?\s*$")
PW_APT = re.compile(r"\bplaywright\b[^\n;&|]*\s(--with-deps\b|install-deps\b)")


def uncommented(text):
    """`text` with each `#` comment cut, one pass that skips quoted strings. Backslash-continued
    lines join, so a flag on a continuation line stays with its command."""
    out = []
    for line in text.replace("\\\n", " ").splitlines():
        quote, cut = None, len(line)
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'" and not (i and line[i - 1].isalnum()):
                quote = ch  # a quote after a letter is an apostrophe in text, as in "don't"
            elif ch == "#" and (i == 0 or line[i - 1].isspace()):
                cut = i
                break
        out.append(line[:cut])
    return folded(out)


def folded(lines):
    """A YAML folded scalar (`run: >`) is one command over several lines, so its lines join onto
    the key's line, and the line count stays the same."""
    out, key, indent = [], None, 0
    for line in lines:
        if key is not None and (not line.strip() or len(line) - len(line.lstrip()) > indent):
            out[key] += " " + line.strip()
            out.append("")
            continue
        key, match = None, FOLDED.match(line)
        if match:
            key, indent = len(out), len(match[1])
        out.append(line)
    return out


def probe_playwright(root):
    files = tracked(root)
    hits, seen = [], False
    for rel in files:
        if PW_FILE.search(rel):
            lines = list(enumerate(uncommented(read(root, rel) or ""), 1))
        elif rel == "package.json" or rel.endswith("/package.json"):
            try:
                scripts = json.loads(read(root, rel) or "{}").get("scripts") or {}
            except (ValueError, AttributeError):
                continue
            lines = [("script " + k, v) for k, v in scripts.items() if isinstance(v, str)]
        else:
            continue
        for where, text in lines:
            seen = seen or "playwright" in text
            if PW_APT.search(text):
                hits.append("  apt install: %s:%s: %s" % (rel, where, text.strip()[:160]))
    if hits:
        return finish("playwright", hits, "out - %d install(s) run apt; use actions/playwright-setup" % len(hits), 1)
    return finish("playwright", [], "in shape - no apt step" if seen else "n/a - no Playwright install", 0)


IOS_TARGETS = ("phone", "testflight", "native-check")
WORKFLOW = re.compile(r"^\.github/workflows/[^/]+\.ya?ml$")
PBXPROJ = re.compile(r"(^|/)[^/]+\.xcodeproj/project\.pbxproj$")
XCODEGEN = re.compile(r"(^|/)project\.yml$")
SWIFT_VERSION = re.compile(r"\bSWIFT_VERSION\s*[:=]\s*\"?([0-9][0-9.]*)")
TOOLS_VERSION = re.compile(r"^//\s*swift-tools-version:\s*([0-9][0-9.]*)", re.M)
MODE_5 = re.compile(r"\bswift(LanguageModes|LanguageVersions)\s*:\s*\[[^\]]*\.v(ersion\(\"?)?5|\.swiftLanguageMode\(\s*\.v5\b")
# A macOS image on a runs-on line, or in a matrix `os:` or a `labels:` value. A job name is not an image.
MACOS_IMAGE = re.compile(r"^\s*(?:-\s*)?(?:runs-on|os|labels)\s*:.*?(?<![\w.-])(macos-[\w.-]+)", re.M)
RUNS_ON = re.compile(r"\bruns-on:")
PACKAGE_TESTS = re.compile(r"\bswift\s+test\b|\bmake\s+(\S+\s+)*kit-test\b|\bmake\s+(\S+\s+)*native-check\b")
APP_COMPILE = re.compile(r"\bxcodebuild\b(?!\s+-version)|\bmake\s+(\S+\s+)*(app-build|native-check)\b")
XCODEBUILD_TEST = r"\bxcodebuild\b[^\n|;&]*\s(test|test-without-building)(?![-\w.])"
UI_ON_PR = re.compile(XCODEBUILD_TEST + r"|\bmake\s+(\S+\s+)*(ui-test|native-check)\b|\bsim-test\b")
PULL_REQUEST = re.compile(r"^\s*(on:\s*\[?[^\n]*\bpull_request\b|pull_request\s*:)", re.M)
XCODEBUILD_TEST_RE = re.compile(XCODEBUILD_TEST)
NO_DIAGNOSE = re.compile(r"(?<![\w-])-collect-test-diagnostics\s+never(?![-\w.])")
DEV_TEAM = re.compile(r"\bDEVELOPMENT_TEAM\s*[:=]\s*[\"']?[A-Z0-9]")


def make_recipes(text):
    """{target: recipe text} of a Makefile with comments cut. A rule line may name several targets, and
    may carry its recipe after a `;`."""
    out, names = {}, []
    for line in uncommented(text):
        match = re.match(r"^([\w. -]+?)\s*:(?!=)([^;]*)(;(.*))?$", line)
        if match and not line.startswith("\t"):
            names = match.group(1).split()
            for name in names:
                out.setdefault(name, "")
                if match.group(3):
                    out[name] += match.group(4) + "\n"
        elif line.startswith("\t") and names:
            for name in names:
                out[name] += line + "\n"
        elif line.strip():
            names = []
    return out


def probe_ios(root):
    files = tracked(root)
    pbx = [f for f in files if PBXPROJ.search(f)]
    specs = [f for f in files if XCODEGEN.search(f) and re.search(r"\biOS\b", read(root, f) or "")]
    if not pbx and not specs:
        return finish("ios", [], "n/a - no iOS app (no project.yml for iOS, no .xcodeproj)", 0)
    grades, lines = [], []

    def item(name, grade, why):
        grades.append(grade)
        lines.append("  %s: %s - %s" % (name, grade, why))

    text = {f: "\n".join(uncommented(read(root, f) or "")) for f in files
            if f in pbx or f in specs or WORKFLOW.search(f) or f.endswith("Package.swift") or f in ("tools/ios-ship.json", "Makefile")}
    make = make_recipes(read(root, "Makefile") or "") if "Makefile" in files else None
    if make is None:
        item("make targets", "gap", "no Makefile with %s" % ", ".join(IOS_TARGETS))
        item("ship path", "gap", "no Makefile, so no phone or testflight target")
    else:
        missing = [t for t in IOS_TARGETS if t not in make]
        item("make targets", "gap" if missing else "pass", "Makefile lacks %s" % ", ".join(missing) if missing else "Makefile has %s" % ", ".join(IOS_TARGETS))
        # A recipe may name the tool through a variable, as in `$(SHIP) install`.
        wrapped = [t for t, job in (("phone", "install"), ("testflight", "testflight"))
                   if t in make and not re.search(r"(\bios-ship|\$[({]\w+[)}])\s+%s\b" % job, make[t])]
        item("ship path", "gap" if wrapped else "pass",
             "Makefile target does not call ios-ship: %s" % ", ".join(wrapped) if wrapped else "phone and testflight call ios-ship")
    item("project file", "partial" if pbx else "pass",
         "%s is tracked; use a project.yml and XcodeGen" % ", ".join(pbx) if pbx else "XcodeGen: %s" % ", ".join(specs))
    packages = [f for f in files if f == "Package.swift" or f.endswith("/Package.swift")]
    item("kit package", "pass" if packages else "partial",
         "in-repo package: %s" % ", ".join(packages) if packages else "no tracked Package.swift; app logic lives in the app target")
    old = []
    for f in pbx + specs:
        versions = sorted(set(SWIFT_VERSION.findall(text[f])))
        old += ["%s: SWIFT_VERSION %s" % (f, v) for v in versions if not v.startswith("6")]
        if not versions:
            old.append("%s: no SWIFT_VERSION, so Xcode builds in Swift 5 mode" % f)
    for f in packages:
        tools = TOOLS_VERSION.search(read(root, f) or "")
        if tools and not tools.group(1).startswith("6"):
            old.append("%s: swift-tools-version %s" % (f, tools.group(1)))
        if MODE_5.search(text[f]):
            old.append("%s: language mode 5" % f)
    item("swift 6", "gap" if old else "pass", "; ".join(old) if old else "Swift 6 language mode")
    flows = [f for f in files if WORKFLOW.search(f)]
    # The pinned image, or a larger runner of it (macos-26-xlarge).
    floating = ["%s: %s" % (f, r) for f in flows for r in sorted(set(MACOS_IMAGE.findall(text[f])))
                if r != IOS_RUNNER and not r.startswith(IOS_RUNNER + "-")]
    pinned = any(RUNS_ON.search(text[f]) and MACOS_IMAGE.search(text[f]) for f in flows)
    if floating:
        item("ci runner", "gap", "; ".join(floating) + " (want %s)" % IOS_RUNNER)
    else:
        item("ci runner", "pass" if pinned else "gap", IOS_RUNNER if pinned else "no workflow runs on macOS")
    wants = (("runs the package tests", PACKAGE_TESTS),) * bool(packages) + (("compiles the app", APP_COMPILE),)
    on_pr = [f for f in flows if PULL_REQUEST.search(text[f])]
    lacks = ([] if on_pr else ["no pull_request workflow"]) + [
        "no workflow " + what for what, pattern in wants if not any(pattern.search(text[f]) for f in on_pr)]
    item("ci checks", "gap" if lacks else "pass",
         "; ".join(lacks) if lacks else "%s on each pull request" % ("package tests and an app compile" if packages else "an app compile"))
    slow = [f for f in flows if UI_ON_PR.search(text[f])]
    item("slow tests", "gap" if slow else "pass",
         "%s runs UI tests; they run once per batch on the Mac, through sim-test" % ", ".join(slow) if slow else "no UI suite in CI")
    # Each run of xcodebuild test, split at `&&`, `;` and `|`, needs the flag itself. sim-test adds its own.
    diag = [f for f in files if f == "Makefile" or f.endswith(".sh") or WORKFLOW.search(f)
            if any(XCODEBUILD_TEST_RE.search(run) and not NO_DIAGNOSE.search(run)
                   for line in uncommented(read(root, f) or "") for run in re.split(r"[;&|]+", line))]
    item("test diagnostics", "gap" if diag else "pass",
         "%s runs xcodebuild test without -collect-test-diagnostics never" % ", ".join(diag) if diag
         else "every xcodebuild test run sets -collect-test-diagnostics never")
    ids, overrides = [], []
    if "tools/ios-ship.json" in text:
        try:
            config = json.loads(read(root, "tools/ios-ship.json") or "{}")
        except ValueError:
            config = {}
        if isinstance(config, dict):
            # Decision ios-ship-is-one-shared-tool allows a repo override, so it is partial, not a gap.
            overrides += ["tools/ios-ship.json overrides %s" % k for k in ACCOUNT_KEYS if k in config]
    # ios-ship passes the team to xcodebuild itself, so a team in the build files is a copy.
    ids += ["%s sets DEVELOPMENT_TEAM" % f for f in specs + pbx + flows + ["Makefile"] if f in text and DEV_TEAM.search(text[f])]
    if ids or overrides:
        item("account ids", "gap" if ids else "partial",
             "; ".join(ids + overrides) + "; the default home is ~/.config/ios-ship/account.json")
    else:
        item("account ids", "pass", "none in the repo")
    worst = "out" if "gap" in grades else "partial" if "partial" in grades else "in shape"
    return finish("ios", lines, worst, 0 if worst == "in shape" else 1)


SCORES = "in shape|partial|out|parent-covered|n/a|unknown|not rolled out"
GRADES = "pass|gap|known gap|" + SCORES  # an item line's grade, as item() in the probes prints it
# A probe's own group line may end at its score ("design: out"), or go on with no " - ".
GROUP_LINE = re.compile(r"^([^:\s-][^:]*): (%s)(?:(?: - | )(.*?))?(?: \(([^()]*)\))?$" % SCORES)
ITEM_LINE = re.compile(r"^\s+(?:- )?([^:]+): (%s) - (.*?)(?: \(([^()]*)\))?$" % GRADES)
# A finding line with no grade ("  folder src/: neither ..."): the name ends at the first ": ".
FINDING_LINE = re.compile(r"^\s+(?:- )?(.+?): (.*)$")
UI_GAP_ROW = ("STE lint on UI files", "partial", "UI text the lint does not read: known gap, no UI linter",
              "lint/ui_suffixes.py")


def scorecard(root):
    """Rewrite the one scorecard file from the group lines on stdin. Each item line belongs to the group
    line above it, as a probe prints it and as the skill writes it; an item above any group line is a note."""
    rows, notes, group = [], [], None

    def item_row(name, line):
        graded = ITEM_LINE.match(line)
        if graded:
            return ("%s: %s" % (name, graded.group(1)),) + graded.groups()[1:]
        finding = FINDING_LINE.match(line)
        return ("%s: %s" % (name, finding.group(1)), "finding", finding.group(2), None)

    for line in sys.stdin.read().splitlines():
        found = GROUP_LINE.match(line)
        if found:
            group = found.group(1)
            rows.append((group, found.group(2), found.group(3) or "", found.group(4)))
        elif ITEM_LINE.match(line) or FINDING_LINE.match(line):
            if group is None:
                notes.append(line.strip())
            else:
                rows.append(item_row(group, line))
        elif line.strip():
            notes.append(line.strip())
    rows.append(UI_GAP_ROW)
    text = "# Compliance scorecard\n\nRewritten in place on each run by compliance-check.\n\n"
    text += "| Group | Score | Gold standard | Gap | Source |\n| --- | --- | --- | --- | --- |\n"
    for name, score, gap, source in rows:
        cells = [c.replace("|", "\\|") for c in (name, score, "in shape", gap, source or "none cited")]
        text += "| " + " | ".join(cells) + " |\n"
    if notes:
        text += "\n## Notes\n\n" + "".join("- %s\n" % n for n in notes)
    try:
        rel = layout.path(root, "scorecard")
    except layout.LayoutError as err:
        raise CannotRun(str(err))
    target = os.path.join(root, *rel.split("/"))
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    except OSError as err:
        raise CannotRun(str(err))
    return finish("scorecard", [], "wrote %s (%d row(s), %d note(s))" % (rel, len(rows), len(notes)), 0)


# The word in a problem line of check_glossary, taken from its fixed tail: a message that quotes `uses 'x'` earlier is not read as the word.
WORD_HIT = re.compile(r"\buses '([^']+)'; the glossary name is")


def glossary_commit(root):
    """Short sha of the claude-settings commit that holds the glossary read, or None."""
    try:
        done = _nowindow.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True)
    except OSError:
        return None
    return done.stdout.decode().strip()[:7] if done.returncode == 0 and done.stdout.strip() else None


def glossary_uncommitted(root, name):
    """True when the glossary file differs from HEAD in `root`, or is untracked. False when git cannot say."""
    try:
        done = _nowindow.run(["git", "-C", root, "status", "--porcelain", "--", name], capture_output=True)
    except OSError:
        return False
    return done.returncode == 0 and bool(done.stdout.strip())


def probe_words(root):
    try:
        import check_glossary  # the one home of the retired words and of how a name is read
    except ImportError as err:
        raise CannotRun("check_glossary: %s" % err)
    text = check_glossary.read(check_glossary.GLOSSARY)
    if text is None:
        raise CannotRun("%s cannot be read beside lint/check_glossary.py" % check_glossary.GLOSSARY)
    table = check_glossary.rows(text)
    if not table:
        raise CannotRun("%s has no rows under '%s'" % (check_glossary.GLOSSARY, check_glossary.SECTION))
    found, unread, files = [], [], tracked(root)

    def add(rel, line, problem, detail):
        word = WORD_HIT.search(problem)
        item = (word.group(1) if word else "?", rel, line, " ".join(detail.split()))  # a message may hold a newline
        if item not in found:
            found.append(item)

    for rel in files:
        for problem in check_glossary.path_problems(rel, table):  # "<path> uses '<word>'; ..."
            add(rel, "-", problem, problem[len(rel):].strip())
        body = read(root, rel)
        if body is None:
            unread.append(rel)
            continue
        if rel.startswith(check_glossary.SKIP_CODE):
            continue
        if body.startswith("\ufeff"):  # the check's own read uses utf-8-sig; a BOM would fail the Python parse
            body = body[1:]
        try:
            problems = check_glossary.code_problems(rel, body, table, None)
        except SyntaxError as err:
            raise CannotRun("%s does not parse (%s)" % (rel, err.msg))
        for problem in problems:  # "<rel>:<line>: <where> uses '<word>'; ..."
            line, _, detail = problem[len(rel) + 1:].partition(": ")
            add(rel, line, problem, detail)
    note = "unread: %d files, %s" % (len(unread), ", ".join(unread[:3]) + (", ..." if len(unread) > 3 else ""))
    if not files:
        raise CannotRun("no tracked files")
    if len(unread) == len(files):
        raise CannotRun("no tracked file could be read (%s)" % note)
    sha = glossary_commit(check_glossary.ROOT)
    stale = glossary_uncommitted(check_glossary.ROOT, check_glossary.GLOSSARY)
    lines = ["  %s: %s:%s %s" % item for item in found]
    lines.append("glossary read at %s of claude-settings%s" % (sha or "an unknown commit", " (uncommitted)" if stale else ""))
    if unread:
        lines.append(note)
    if found:
        return finish("words", lines, "out", 1)
    return finish("words", lines, "in shape", 0)


GROUPS = {"layout": probe_layout, "design": probe_design, "lanecap": probe_lanecap, "playwright": probe_playwright,
          "ios": probe_ios, "words": probe_words, "scorecard": scorecard}


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
