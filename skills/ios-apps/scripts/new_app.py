#!/usr/bin/env python3
"""Writes a new iOS app at the standard of the ios-apps skill into a folder.

    python3 new_app.py <dest> --name <App> --bundle-id <reverse.dns.id> --repo-url <https URL>

Each file under templates/ lands at the same path under <dest>, with its `.tmpl` suffix dropped,
`__APP__` in the path and the text filled, and `.gitignore.tmpl` as `.gitignore`. The starter then
writes the Kit package's Tokens.swift with the generated tools/gen-tokens.py. It prints each path it
writes. When any target path exists, it prints each one, writes nothing, and exits 1. A write that
fails midway removes the files and folders this run made, and exits 1. A bad argument exits 2.

<dest> may be an empty folder or a repo that has none of these paths. The starter never runs git.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "templates")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "lint"))
from compliance_probes import IOS_RUNNER  # noqa: E402  the probe and the starter name one runner

NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]{0,39}$")
BUNDLE_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
URL_RE = re.compile(r"^https://[^\s/\"\\]+/[^\s\"\\]+$")  # no quote or backslash: it lands in a JSON string
# Modules every app imports. An app or Kit of the same name shadows them.
TAKEN_NAMES = {"SwiftUI", "Foundation", "UIKit", "Combine", "Observation", "XCTest", "Testing", "Swift"}
GEN_TOKENS = "tools/gen-tokens.py"
TOKENS = "tokens/tokens.json"


def plan(app, bundle_id, repo_url):
    """Returns (relative path, text) for each file to write, in a fixed order."""
    fill = {"__APP__": app, "__BUNDLE_ID__": bundle_id, "__BUNDLE_PREFIX__": bundle_id.rsplit(".", 1)[0],
            "__REPO_URL__": repo_url, "__RUNNER__": IOS_RUNNER}
    out = []
    for base, dirs, files in os.walk(ROOT):
        dirs.sort()
        for name in sorted(files):
            src = os.path.join(base, name)
            rel = os.path.relpath(src, ROOT).replace(os.sep, "/")
            rel = rel[: -len(".tmpl")] if rel.endswith(".tmpl") else rel
            with open(src, encoding="utf-8") as f:
                text = f.read()
            for key, value in fill.items():
                rel, text = rel.replace(key, value), text.replace(key, value)
            out.append((rel, text))
    files = dict(out)
    gen = {"__name__": "gen_tokens"}
    exec(compile(files[GEN_TOKENS], GEN_TOKENS, "exec"), gen)
    out.append((gen["OUTPUT"], gen["render"](json.loads(files[TOKENS]))))
    return out


def main(argv):
    parser = argparse.ArgumentParser(description="Write a new iOS app at the ios-apps standard.")
    parser.add_argument("dest")
    parser.add_argument("--name", required=True, help="the app, scheme and Swift type name, such as Tally")
    parser.add_argument("--bundle-id", required=True, help="such as dev.example.tally")
    parser.add_argument("--repo-url", required=True, help="the https clone URL that ios-ship install clones")
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return stop.code
    if args.name in TAKEN_NAMES:
        print("new_app: --name: %s is a system module" % args.name, file=sys.stderr)
        return 2
    for value, pattern, what in ((args.name, NAME_RE, "--name: a Swift type name, such as Tally"),
                                 (args.bundle_id, BUNDLE_RE, "--bundle-id: lower-case reverse DNS, such as dev.example.tally"),
                                 (args.repo_url, URL_RE, "--repo-url: an https URL")):
        if not pattern.match(value):
            print("new_app: " + what, file=sys.stderr)
            return 2
    files = plan(args.name, args.bundle_id, args.repo_url)
    taken = [rel for rel, _ in files if os.path.lexists(os.path.join(args.dest, *rel.split("/")))]
    if taken:
        for rel in taken:
            print("new_app: exists, not overwritten: %s" % rel, file=sys.stderr)
        return 1
    wrote, made = [], []
    try:
        for rel, text in files:
            path = os.path.join(args.dest, *rel.split("/"))
            missing, folder = [], os.path.dirname(path)
            while not os.path.isdir(folder):
                missing.append(folder)
                folder = os.path.dirname(folder)
            for folder in reversed(missing):
                os.mkdir(folder)
                made.append(folder)
            with open(path, "x", encoding="utf-8", newline="\n") as f:
                wrote.append(path)
                f.write(text)
            print(rel)
    except OSError as err:
        for path in wrote + made[::-1]:
            try:
                (os.rmdir if path in made else os.remove)(path)
            except OSError:
                pass
        print("new_app: write failed, removed this run's files and folders: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
