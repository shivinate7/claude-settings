#!/usr/bin/env python3
"""Reads the guard cases of a base branch against the head's, so a pull request cannot loosen a guard and the case
that pins it in one go and pass (decision guard-cases-from-base).

    python3 lint/check_guard_cases_from_base.py --base origin/main

Run it in a repository. It lists the cases of the base's tests/guard (from `git archive`) and of the head's, each
with this checkout's runner (hooks/test_guard.py under GUARD_LIST), so the two lists differ only by their section
files. It matches each base case to a head case by key, the hash of its payload, and prefers the one of the same
name. A name alone is no match: a case may be renamed. Lines it prints:

    RED <name>: ...      a loosening no trailer waives. The verdict drops (allow < ask < deny), or the key is gone
                         from the head (the case was removed, or its payload changed) and the base case was a deny
                         or an ask. Exit 1.
    WAIVED <name>: ...   the same, and a commit of BASE..HEAD carries the exact trailer `Guard-case-loosened: <name>`.
    REPORT <name>: ...   a tightening or a rename. Exit 0.
    UNKNOWN <reason>     a list cannot be read. Exit 1 (decision ci-unknown-is-red).

Only a case that the head's runner can list is read: a base section file that fails to load on the head's runner is
UNKNOWN, never a pass.
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(os.path.dirname(HERE), "hooks", "test_guard.py")
SECTIONS = "tests/guard"
RANK = {"allow": 0, "ask": 1, "deny": 2}
TRAILER = re.compile(r"^Guard-case-loosened:[ \t]*(.+?)[ \t]*$", re.M)
LIST_SECONDS = 900  # a listing builds the sections' eager fixtures and no case, which takes well under a minute


class Unknown(Exception):
    pass


def git(args, repo, binary=False):
    done = subprocess.run(["git", *args], cwd=repo, capture_output=True)
    if done.returncode:
        raise Unknown("git %s failed: %s" % (args[0], done.stderr.decode("utf-8", "replace").strip()[:200]))
    return done.stdout if binary else done.stdout.decode("utf-8", "replace")


def extract(repo, ref, into):
    """The tests/guard folder of ref, written under `into`. -> its path."""
    data = git(["archive", "--format=tar", ref, SECTIONS], repo, binary=True)
    root = os.path.realpath(into)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for member in tar.getmembers():
            target = os.path.realpath(os.path.join(root, member.name))
            if not target.startswith(root + os.sep) or not member.isfile():
                continue  # only plain files, and none that leaves `into`
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as out:
                out.write(tar.extractfile(member).read())
    folder = os.path.join(into, *SECTIONS.split("/"))
    if not os.path.isdir(folder):
        raise Unknown("%s has no %s" % (ref, SECTIONS))
    return folder


def list_cases(repo, ref, scratch, label):
    """The rows of the listing of ref's sections. Raises Unknown when the list cannot be read."""
    folder = extract(repo, ref, os.path.join(scratch, label))
    path = os.path.join(scratch, label + ".json")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("GUARD_", "MUTATE_ONLY"))}
    env.update(GUARD_LIST=path, GUARD_SECTION_DIR=folder)
    try:
        done = subprocess.run([sys.executable, RUNNER], cwd=repo, env=env, capture_output=True, text=True,
                              timeout=LIST_SECONDS)
    except subprocess.TimeoutExpired:
        raise Unknown("the %s list did not end in %d s" % (label, LIST_SECONDS))
    if done.returncode or not os.path.isfile(path):
        last = (done.stdout + done.stderr).strip().splitlines()[-1:] or ["no output"]
        raise Unknown("the %s list (%s) cannot be read, exit %s: %s" % (label, ref, done.returncode, last[0][:200]))
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        return [(r["name"], r["expected"], r["key"]) for r in rows]
    except (ValueError, KeyError, TypeError) as exc:
        raise Unknown("the %s list (%s) is not a case list: %s" % (label, ref, exc))


def waived_names(repo, base):
    """The case names that a commit of base..HEAD waives with `Guard-case-loosened: <name>`."""
    log = git(["log", "--format=%B%x00", base + "..HEAD"], repo)
    return {name for message in log.split("\0") for name in TRAILER.findall(message)}


def compare(base_rows, head_rows):
    """-> [(kind, name, text)] with kind RED, REPORT. A RED may be waived by the caller."""
    by_key = {}
    for name, expected, key in head_rows:
        by_key.setdefault(key, []).append((name, expected))
    out = []
    for name, expected, key in base_rows:
        found = by_key.get(key)
        if not found:
            if RANK.get(expected, 0) > RANK["allow"]:
                out.append(("RED", name, "the %s case has no case with its payload on the head (removed, or its "
                                         "payload changed)" % expected))
            else:
                out.append(("REPORT", name, "the allow case has no case with its payload on the head"))
            continue
        # The case of the same name, else the lowest verdict: a payload that two head cases hold reads as loosely as it can.
        same = [row for row in found if row[0] == name]
        head_name, head_verdict = same[0] if same else min(found, key=lambda row: RANK.get(row[1], 0))
        if RANK.get(head_verdict, 0) < RANK.get(expected, 0):
            out.append(("RED", name, "the verdict drops from %s to %s" % (expected, head_verdict)))
        elif RANK.get(head_verdict, 0) > RANK.get(expected, 0):
            out.append(("REPORT", name, "tightened from %s to %s" % (expected, head_verdict)))
        elif head_name != name:
            out.append(("REPORT", name, "renamed to %r" % head_name))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", required=True, help="the base ref, such as origin/main")
    args = parser.parse_args(argv)
    try:
        repo = git(["rev-parse", "--show-toplevel"], os.getcwd()).strip()
        with tempfile.TemporaryDirectory(prefix="guard-cases-") as scratch:
            results = {}

            def run(label, ref):
                try:
                    results[label] = list_cases(repo, ref, scratch, label)
                except Unknown as exc:
                    results[label] = exc

            threads = [threading.Thread(target=run, args=(label, ref)) for label, ref in
                       (("base", args.base), ("head", "HEAD"))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            for label in ("base", "head"):
                if isinstance(results[label], Unknown):
                    raise results[label]
            waived = waived_names(repo, args.base)
    except Unknown as exc:
        print("UNKNOWN %s" % exc)
        return 1
    red = 0
    for kind, name, text in compare(results["base"], results["head"]):
        if kind == "RED" and name in waived:
            kind = "WAIVED"
        red += kind == "RED"
        print("%s %s: %s" % (kind, name, text))
    print("guard cases from %s: %d base cases, %d head cases, %d RED" % (args.base, len(results["base"]),
                                                                       len(results["head"]), red))
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
