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

Exit 0: no FAIL. Exit 1: a FAIL line for each find. Exit 2: a read that could not run (git did not start), as
`check_artifact_cites: unknown: ...`; never a pass. Cost: one pass over the record files, and two git processes
for the steps; no network, no timer.
"""
import argparse
import json
import os
import re
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


def step_files(root):
    """[(path, text)] of each step on the record branch: the local ref, else origin's. [] when neither ref is there."""
    branch = layout.record_branch(root)
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
    return []


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
    fails, listed = [], []
    try:
        known = {entry["id"] for entry in layout.artifacts(root, tree_only=True)}  # the checkout's own registry, not origin's
    except layout.LayoutError as err:
        return [FAIL + "the artifacts registry cannot be read: %s" % err], listed
    for kind in ("decisions", "debts"):
        for rel, text in record_files(root, kind):
            fails.extend("%s%s:%d: %s" % (FAIL, rel, number, what) for number, what in findings(text, known))
    for rel, text in step_files(root):
        lines = ["%s: %s" % (rel, what) for _, what in step_findings(text, known)]
        if steps_mode == "refuse":
            fails.extend(FAIL + line for line in lines)
        else:
            listed.extend(LIST + line for line in lines)
    return fails, listed


def main(argv):
    ap = argparse.ArgumentParser(description="Refuse a bare claude.ai artifact link and an unregistered artifact:<id> cite.")
    ap.add_argument("--root", default=os.path.dirname(HERE), help="the repo to check (default: this checkout)")
    ap.add_argument("--steps", choices=("refuse", "list"), default="refuse", help="a find in a roadmap step is a FAIL, or only listed")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    try:
        fails, listed = check(root, args.steps)
    except Unknown as err:
        print("check_artifact_cites: unknown: %s" % err)
        return 2
    except layout.LayoutError as err:
        print(FAIL + "the layout cannot be read: %s" % err)
        return 1
    for line in fails + listed:
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
