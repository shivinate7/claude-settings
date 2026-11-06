#!/usr/bin/env python3
"""Check that a record cites a claude.ai artifact as `artifact:<id>`, never by its link (decision waiting-data-in-repo).

A link breaks when a page moves to another account or org, and each record that holds one must then be found and
rewritten. The registry (the "artifacts" key of the extras file, `layout.artifacts()`) maps each id to the current
link, so a move edits one entry. This check refuses two things:

  1. a bare `claude.ai/artifact/<id>` or `claude.ai/code/artifact/<id>` link, even for a registered page and even
     inside a code fence, a span or a comment: no context makes a link safe;
  2. an `artifact:<id>` cite whose id is not in the registry.

It reads the decisions folder and the debts folder of the working tree (each `.md`, any depth), and every string of
each roadmap step (`roadmap/data/steps/*.json`) on the record branch, from the local ref, else origin's. Briefs,
handoffs and every other folder are working files and are not read. A registry that cannot be read is a FAIL.

    python3 lint/check_artifact_cites.py [--root DIR] [--steps refuse|list]

--steps refuse (the default) treats a step like a decision. --steps list prints each find in a step as a LIST line and
leaves the exit code to the decisions and debts: the mode for a repo whose steps still hold links that triage has not
yet moved, because lanes never write the roadmap.

Exit 0: no FAIL. Exit 1: a FAIL line for each find. A read that could not run (a decisions or debts path that is
no folder, git that did not start, a step git cannot read, no record branch under --steps refuse) prints `check_artifact_cites: UNKNOWN, ...`
and exits 0, or 1 when env CI is set (decision ci-unknown-is-red). Cost: one pass over the record files, and two git
processes for the steps; one fetch of the record branch only when neither the checkout nor origin's ref has it; no
timer.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))
import layout  # noqa: E402  the one home of the registry and of every kind's path
import _nowindow  # noqa: E402  the one home of a no-window child start

BARE_LINK = re.compile(r"claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]", re.I)
CITE = re.compile(r"(?<![A-Za-z0-9_-])artifact:([A-Za-z0-9_-]+)")
STEP_FOLDER = "roadmap/data/steps"  # the record branch's steps, as skills/project-ops/scripts/scaffold.py makes them
FAIL, LIST = "check_artifact_cites: FAIL: ", "check_artifact_cites: LIST: "


class Unknown(Exception):
    """A read that could not run."""


def findings(text, known):
    """[(line number, what)] for each bare link and each unregistered cite in `text`."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if BARE_LINK.search(line):
            found.append((number, "a bare artifact link; cite it as artifact:<id> and register the page"))
        for cite in CITE.finditer(line):
            if cite.group(1) not in known:
                found.append((number, "artifact:%s is not in the artifacts registry" % cite.group(1)))
    return found


def strings(node):
    """Every string value and every key of parsed JSON `node`."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for child in node:
            yield from strings(child)
    elif isinstance(node, dict):
        for key, child in node.items():
            yield key
            yield from strings(child)


def record_files(root, kind):
    """[(path relative to root with `/`, text)] of each .md under the folder of layout kind `kind`."""
    top = os.path.join(root, *layout.path(root, kind).split("/"))
    if not os.path.lexists(top):  # an absent folder holds zero records
        return []
    if not os.path.isdir(top):  # os.walk yields nothing for it and raises nothing: it must not read as clean
        raise Unknown("the %s folder %s is not a folder" % (kind, os.path.relpath(top, root).replace(os.sep, "/")))
    found = []
    for folder, names, files in os.walk(top):
        names.sort()
        for name in sorted(files):
            if name.endswith(".md"):
                full = os.path.join(folder, name)
                with open(full, encoding="utf-8", errors="replace") as handle:
                    found.append((os.path.relpath(full, root).replace(os.sep, "/"), handle.read()))
    return found


def git(root, *args, data=None):
    try:
        return _nowindow.run(["git", "-C", root, *args], capture_output=True, input=data)
    except OSError as err:
        raise Unknown("git did not start (%s)" % type(err).__name__)


def fetch_record_branch(root, branch):
    """Fetch the record branch from origin into its remote-tracking ref, for a shallow or single-branch checkout that
    lacks it. A failed fetch is no error here: the caller finds the ref still absent and says UNKNOWN."""
    try:
        _nowindow.run(["git", "-C", root, "fetch", "-q", "--no-tags", "--depth=1", "origin",
                       "+refs/heads/%s:refs/remotes/origin/%s" % (branch, branch)],
                      capture_output=True, timeout=120, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.SubprocessError):
        pass


def step_files(root):
    """[(path, text)] of each step on the record branch: the local ref, else origin's, else origin's after a fetch.
    None when no ref is there, so a missing branch is never read as no steps."""
    branch = layout.record_branch(root)
    refs = ("refs/heads/" + branch, "refs/remotes/origin/" + branch)
    if all(git(root, "rev-parse", "--verify", "-q", ref + "^{commit}").returncode == 1 for ref in refs):
        fetch_record_branch(root, branch)
    for ref in ("refs/heads/" + branch, "refs/remotes/origin/" + branch):
        probe = git(root, "rev-parse", "--verify", "-q", ref + "^{commit}")
        if probe.returncode == 1:
            continue
        if probe.returncode != 0:
            raise Unknown("git cannot read %s" % ref)
        listed = git(root, "ls-tree", "-r", ref, "--", STEP_FOLDER)
        if listed.returncode != 0:
            raise Unknown("git cannot list %s" % ref)
        entries = []
        for line in listed.stdout.decode("utf-8", "replace").splitlines():
            meta, _, name = line.partition("\t")
            parts = meta.split()
            if len(parts) == 3 and parts[1] == "blob" and name.endswith(".json"):
                entries.append((name, parts[2]))
        if not entries:
            return []
        blobs = git(root, "cat-file", "--batch", data="".join(sha + "\n" for _, sha in entries).encode())
        if blobs.returncode != 0:
            raise Unknown("git cannot read the steps of %s" % ref)
        out, pos, found = blobs.stdout, 0, []
        for name, sha in entries:
            end = out.index(b"\n", pos)
            head = out[pos:end].split()
            if len(head) != 3 or head[0].decode() != sha:
                raise Unknown("git gave no blob for %s" % name)
            size = int(head[2])
            found.append((name, out[end + 1:end + 1 + size].decode("utf-8", "replace")))
            pos = end + 1 + size + 1
        return found
    return None


def step_findings(text, known):
    """The finds of one step: its parsed strings, so an escape such as \\u0068 is read as the character it is. A step that
    does not parse is read as raw text, so a broken file never hides a link."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return findings(text, known)
    return [(0, what) for piece in strings(parsed) for _, what in findings(piece, known)]


def check(root, steps_mode):
    """(fail lines, list lines) for the repo at `root`."""
    fails, listed, unknown = [], [], []
    try:
        known = {entry["id"] for entry in layout.artifacts(root)}
    except layout.LayoutError as err:
        return [FAIL + "the artifacts registry cannot be read: %s" % err], listed, unknown
    for kind in ("decisions", "debts"):
        try:
            records = record_files(root, kind)
        except Unknown as err:
            unknown.append(str(err))
            continue
        for rel, text in records:
            fails.extend("%s%s:%d: %s" % (FAIL, rel, number, what) for number, what in findings(text, known))
    try:
        steps = step_files(root)
    except Unknown as err:  # a step that cannot be read must not drop the finds made above
        unknown.append(str(err))
        steps = []
    if steps is None:
        if steps_mode == "refuse":
            unknown.append("the record branch %s is on neither the checkout nor origin, so its steps were not read"
                           % layout.record_branch(root))
        steps = []
    for rel, text in steps:
        lines = ["%s: %s" % (rel, what) for _, what in step_findings(text, known)]
        if steps_mode == "refuse":
            fails.extend(FAIL + line for line in lines)
        else:
            listed.extend(LIST + line for line in lines)
    return fails, listed, unknown


def main(argv):
    ap = argparse.ArgumentParser(description="Refuse a bare claude.ai artifact link and an unregistered artifact:<id> cite.")
    ap.add_argument("--root", default=os.path.dirname(HERE), help="the repo to check (default: this checkout)")
    ap.add_argument("--steps", choices=("refuse", "list"), default="refuse", help="a find in a roadmap step is a FAIL, or only listed")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        fails, listed, unknown = check(root, args.steps)
    except Unknown as err:
        fails, listed, unknown = [], [], [str(err)]
    except layout.LayoutError as err:
        print(FAIL + "the layout cannot be read: %s" % err)
        return 1
    for line in fails + listed:
        print(line)
    for what in unknown:
        print("check_artifact_cites: UNKNOWN, " + what)
    if fails:
        return 1
    return 1 if unknown and os.environ.get("CI") else 0  # the CI exit code is the verdict: unknown is red there


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
