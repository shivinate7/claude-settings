#!/usr/bin/env python3
"""Fails when a lint code has two homes: a branch that adds a code the base already defines, or a head that adds a duplicate.

    python3 lint/check_lint_codes.py --base origin/main [--head HEAD] [--root .]

Codes are numbered on branches, so two lanes pick the same next number. A code has one definition site:
  STE   the first argument of a `_rule(` call in lint/ste_lint.py, read with `ast`.
  STALE a row of the module docstring table in lint/stale_cites.py: a line of leading spaces or tabs, the code, then
        one or more spaces, read with `ast`. A `code = "STALE002"` line in a reader class is a use, not a definition.
  MAP   a key of the body in skills/plain-english-map/scripts/map-check.mjs, written `MAP<n>: () => {`, `MAP<n>:() => {`,
        `async MAP<n>() {` or `MAP<n>() {`, read from the text with comments and strings blanked by that skill's one
        scanner (lib/source-text.mjs).
Exit 1 when
  (a) a code is in the head and not in the merge base of --base and the head, and the tip of --base defines it; or
  (b) the head defines a code more than once, and more times than the tip of --base does.
A duplicate that the tip of --base already holds does not fail the branch: it cannot fix that.
Exit 2 (UNKNOWN) when a git read, a parse or the node scan fails, when node is missing, or when a home file that the tip
of --base holds is absent at the head (a moved home would hide its codes). A home file that neither the tip nor the head
holds means no codes there.
Cost per run: at most 15 git starts (2 rev-parse, 1 merge-base, 1 ls-tree per revision, and 1 cat-file per distinct home
blob, at most 9). One node start, only when a MAP home exists. It writes no file and starts no long-lived process.
"""
import argparse
import ast
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

STALE = "lint/stale_cites.py"
STE = "lint/ste_lint.py"
MAP = "skills/plain-english-map/scripts/map-check.mjs"
HOMES = (STALE, STE, MAP)
SOURCE_TEXT = os.path.join(HERE, "..", "skills", "plain-english-map", "scripts", "lib", "source-text.mjs")
ROW = re.compile(r"^[ \t]+(STALE\d{3}) +", re.M)
# `MAP2: () => {`, `MAP2:() => {`, `MAP2: async () => {`, `async MAP3() {` and `MAP4() {`.
KEY = re.compile(r"^[ \t]*(?:async[ \t]+)?(MAP\d+)(?:[ \t]*:[ \t]*(?:async[ \t]*)?\(\)[ \t]*=>[ \t]*\{|[ \t]*\(\)[ \t]*\{)", re.M)
# Blanks comments and strings of each text of the JSON object on stdin, with the skill's scanner.
BLANK_JS = ("import {blankCommentsAndStrings as b} from process.argv[1];"
            "let s='';process.stdin.setEncoding('utf8');process.stdin.on('data',d=>s+=d).on('end',()=>{"
            "const t=JSON.parse(s);for(const k in t)t[k]=b(t[k],'map-check.mjs');process.stdout.write(JSON.stringify(t));});")


class Unknown(Exception):
    """A read failed, so the codes of a revision are not known."""


def git(root, *args):
    try:
        r = _nowindow.run(["git", "-C", root, *args], capture_output=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise Unknown("git could not start: %s" % e)
    if r.returncode:
        raise Unknown("git %s failed: %s" % (args[0], r.stderr.strip()))
    return r.stdout


def home_blobs(root, rev):
    """{home path: blob id at `rev`, or None when the revision has no such file}, from one ls-tree."""
    blobs = dict.fromkeys(HOMES)
    for line in git(root, "ls-tree", rev, "--", *HOMES).splitlines():
        meta, _, path = line.partition("\t")
        if path in blobs:
            blobs[path] = meta.split()[2]
    return blobs


def python_codes(text, path, find):
    try:
        return find(ast.parse(text))
    except (SyntaxError, ValueError) as e:
        raise Unknown("%s does not parse: %s" % (path, e))


def stale_rows(tree):
    doc = ast.get_docstring(tree, clean=False) or ""
    return ROW.findall(doc)


def ste_calls(tree):
    return [n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_rule"
            and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)]


def map_keys(texts):
    """The MAP keys of each text, scanned in one node process. `texts` maps a blob id to its text."""
    if not texts:
        return {}
    cmd = ["node", "--input-type=module", "-e", BLANK_JS.replace("process.argv[1]", json.dumps("file://" + SOURCE_TEXT.replace(os.sep, "/")))]
    try:
        r = _nowindow.run(cmd, input=json.dumps(texts), capture_output=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise Unknown("the MAP scan could not start node: %s" % e)
    if r.returncode:
        raise Unknown("the MAP scan failed: %s" % r.stderr.strip()[:300])
    try:
        return {blob: KEY.findall(text) for blob, text in json.loads(r.stdout).items()}
    except ValueError as e:
        raise Unknown("the MAP scan printed no JSON: %s" % e)


def codes_at(root, tip, head, revs):
    """{rev: Counter of code -> definitions} for each revision. A home the tip holds and the head lacks is Unknown."""
    blobs = {rev: home_blobs(root, rev) for rev in revs}
    for path in HOMES:
        if blobs[tip][path] and not blobs[head][path]:
            raise Unknown("%s is a home at the tip of the base and is absent at %s, so its codes are not known" % (path, head))
    texts = {}
    for found in blobs.values():
        for blob in found.values():
            if blob and blob not in texts:
                texts[blob] = git(root, "cat-file", "blob", blob)
    keys = map_keys({blob: texts[blob] for found in blobs.values() for blob in [found[MAP]] if blob})
    out = {}
    for rev, found in blobs.items():
        codes = []
        for path, find in ((STALE, stale_rows), (STE, ste_calls)):
            if found[path]:
                codes += python_codes(texts[found[path]], path, find)
        if found[MAP]:
            codes += keys[found[MAP]]
        out[rev] = collections.Counter(codes)
    return out


def check(root, base, head="HEAD"):
    """[problem line] for the head against the tip of `base`. Raises Unknown when a read fails."""
    tip = git(root, "rev-parse", "--verify", base + "^{commit}").strip()
    tip_head = git(root, "rev-parse", "--verify", head + "^{commit}").strip()
    fork = git(root, "merge-base", tip, tip_head).strip()
    counts = codes_at(root, tip, tip_head, list(dict.fromkeys([tip, tip_head, fork])))
    problems = []
    for code, n in sorted(counts[tip_head].items()):
        if n > 1 and n > counts[tip][code]:
            problems.append("%s is defined %d times in %s" % (code, n, head))
        if code not in counts[fork] and code in counts[tip]:
            problems.append("%s is added by %s and %s already defines it: take the next free number" % (code, head, base))
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--base", required=True, help="the ref whose tip must not already define a code the head adds")
    p.add_argument("--head", default="HEAD")
    p.add_argument("--root", default=".")
    a = p.parse_args(argv)
    try:
        problems = check(a.root, a.base, a.head)
    except Unknown as e:
        print("lint-codes: UNKNOWN, %s" % e)
        return 2
    for line in problems:
        print("lint-codes: " + line)
    if not problems:
        print("lint-codes: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
