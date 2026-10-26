#!/usr/bin/env python3
"""Fails when a hook script that a recent settings.json called is gone from HEAD.

A running session keeps the hook list it read at start. If a later commit deletes a script
that list still names, the wrapper exits 2 and the session loses the tool it guards. So a script
that any settings.json version on main called in the last 14 days stays, as an exit-0 stub if
retired. The window ends at HEAD's committer date, not at the clock.

Versions in scope, on HEAD's first-parent history: every settings.json committed inside the
window, the one current at window start, and HEAD's own. The check does not read a stub's content.

    python3 lint/check_hook_stubs.py [--repo DIR]     # DIR defaults to this script's repo
"""
import datetime
import json
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

WINDOW_DAYS = 14
SETTINGS = "settings.json"
CALL = re.compile(r"\$\{CLAUDE_CONFIG_DIR:-\$HOME/\.claude\}/([^\s\"';|&]+\.(?:py|sh|mjs|js|ps1))")
NAME = "check_hook_stubs"


def unknown(reason):
    print("%s: UNKNOWN, %s" % (NAME, reason))
    sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there


def git(repo, *args):
    r = _nowindow.run(["git", "-C", repo, *args], capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def main(argv):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--repo" and args:
            repo = args.pop(0)
        else:  # an unknown option must never read as a pass
            print("%s: FAIL: unknown option: %s" % (NAME, a))
            return 1
    if git(repo, "rev-parse", "--is-shallow-repository").strip() == "true":
        unknown("shallow clone, settings history is cut")
    head = datetime.datetime.fromisoformat(git(repo, "log", "-1", "--format=%cI", "HEAD").strip())
    start = head - datetime.timedelta(days=WINDOW_DAYS)
    versions = []  # (sha, date), oldest first
    for line in git(repo, "log", "--first-parent", "--format=%H %cI", "HEAD", "--", SETTINGS).splitlines():
        sha, iso = line.split()
        versions.append((sha, datetime.datetime.fromisoformat(iso)))
    versions.reverse()
    before = [v for v in versions if v[1] <= start]
    scope = before[-1:] + [v for v in versions if v[1] > start]
    present = set(git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    calls = []  # per version: set of script paths
    for sha, _ in scope:
        text = git(repo, "show", "%s:%s" % (sha, SETTINGS))
        try:
            hooks = json.loads(text).get("hooks", {})
        except (ValueError, AttributeError):
            unknown("settings.json at %s does not parse" % sha[:7])
        calls.append({m for s in strings(hooks) for m in CALL.findall(s)})
    scripts = set().union(*calls) if calls else set()
    bad = 0
    for path in sorted(scripts - present):
        i = max(k for k, c in enumerate(calls) if path in c)
        sha, date = scope[i]
        if i + 1 < len(scope):
            until = (scope[i + 1][1] + datetime.timedelta(days=WINDOW_DAYS)).date().isoformat()
        else:
            until = "settings.json stops calling it, plus %d days" % WINDOW_DAYS
        print("%s: FAIL: %s is gone, but settings.json at %s (%s) still calls it. "
              "Keep an exit-0 stub until %s." % (NAME, path, sha[:7], date.date().isoformat(), until))
        bad += 1
    if bad:
        return 1
    print("%s: OK (%d scripts, %d settings versions)" % (NAME, len(scripts), len(scope)))
    return 0


sys.exit(main(sys.argv[1:]))
