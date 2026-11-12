#!/usr/bin/env python3
"""Fails when a hook script that any settings.json version on main called is gone from HEAD.

A running session keeps the hook list it read at start. If a later commit deletes a script
that list still names, the wrapper exits 2 and the session loses the tool it guards. A session
can be older than any day count, so no window applies: a script that any settings.json version
on HEAD's first-parent history named stays, as an exit-0 stub if retired. The check never reads
the clock (owner ruling R37, 2026-11-11, fixed numbers that refuse are retired; the old 14-day
window was unmeasured).

Versions in scope: every settings.json on HEAD's first-parent history, HEAD's own included. The
check does not read a stub's content.

    python3 lint/check_hook_stubs.py [--repo DIR]     # DIR defaults to this script's repo
"""
import json
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

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
    scope = []  # (sha, date), oldest first
    for line in git(repo, "log", "--first-parent", "--format=%H %cI", "HEAD", "--", SETTINGS).splitlines():
        sha, iso = line.split()
        scope.append((sha, iso[:10]))
    scope.reverse()
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
        print("%s: FAIL: %s is gone, but settings.json at %s (%s) named it. "
              "Keep an exit-0 stub." % (NAME, path, sha[:7], date))
        bad += 1
    if bad:
        return 1
    print("%s: OK (%d scripts, %d settings versions)" % (NAME, len(scripts), len(scope)))
    return 0


sys.exit(main(sys.argv[1:]))
