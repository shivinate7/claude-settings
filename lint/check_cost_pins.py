#!/usr/bin/env python3
"""Fails when a decision record's Cost sentence names a file that no test pins.

    python3 lint/check_cost_pins.py [--root DIR]

A Cost paragraph starts at a line that opens with `Cost:` or `Cost.`, bare or after a list marker or bold marks. It
runs until a blank line, a list item that is not a Cost line, a heading or a code fence. Fenced code is not read.
Each sentence of it is read alone. A sentence ends at ". ", "! " or "? " outside backticks, or at the paragraph end.

A file token is a backticked name that ends in a known file extension (EXTENSIONS) or starts with `~/` or `.git/`. A token whose
name is a test file (`test_*`, `*_test.*`, `*.test.*`) is a pin candidate, not a file token. A token is flagged
whether or not its file exists. It is pinned when a candidate in the same sentence exists under the root and holds the
token's name: its basename, or the folder before a `<placeholder>` basename. A sentence that says "not pinned",
"unpinned", "unmeasured" or "no test" pins nothing and flags nothing: the writer has said so.

The report is one line per token and line: `<record>:<line>: <token> named in a Cost sentence with no pin`.
Exit 1 when there is a finding, 0 when there is none. Only the decision records (kind `decisions` in lint/layout.json) are read: a debt's Cost line is not.
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COST_START = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Cost[:.]")
LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s")
HEADING = re.compile(r"^\s{0,3}#")
FENCE = re.compile(r"^\s*(?:```|~~~)")
EXEMPT = re.compile(r"\b(?:not pinned|unpinned|unmeasured|no test)", re.IGNORECASE)
PLACEHOLDER = re.compile(r"<[^<>]*>")
# A bare `tool.call` or `e.g.` has a dot and no file, so only these extensions mark a file.
EXTENSIONS = ("md py mjs js ts tsx json jsonl sh ps1 cmd bat html css yml yaml toml txt log csv tmpl sql cfg ini "
              "lock xml").split()
EXTENSION = re.compile(r"^.+\.(?:%s)$" % "|".join(EXTENSIONS))
TEST_NAME = re.compile(r"^(?:test_.*|.*_test\..*|.*\.test\..*)$")


def paragraphs(lines):
    """Each Cost paragraph of `lines` as a list of (line number, text)."""
    found, current, fenced = [], None, False
    for number, text in enumerate(lines, 1):
        if FENCE.match(text):
            fenced = not fenced
            current = None
            continue
        if fenced:
            continue
        if COST_START.match(text):
            current = [(number, text)]
            found.append(current)
        elif current is not None and text.strip() and not LIST_ITEM.match(text) and not HEADING.match(text):
            current.append((number, text))
        else:
            current = None
    return found


def sentences(paragraph):
    """The sentences of one paragraph as lists of (line number, character). A backtick holds the sentence open."""
    out, current, inside = [], [], False
    chars = [(number, c) for number, text in paragraph for c in text + "\n"]
    for i, (number, c) in enumerate(chars):
        current.append((number, c))
        if c == "`":
            inside = not inside
        elif c in ".!?" and not inside and (i + 1 == len(chars) or chars[i + 1][1].isspace()):
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def tokens(sentence):
    """(token, line number) for each backticked span of the sentence, in order."""
    text = "".join(c for _, c in sentence)
    found = []
    for m in re.finditer(r"`([^`\n]+)`", text):
        found.append((m.group(1), sentence[m.start() + 1][0]))
    return found


def basename(token):
    return token.rstrip("/").rsplit("/", 1)[-1]


def is_test_name(token):
    return bool(TEST_NAME.match(basename(token)))


def is_file(token):
    plain = PLACEHOLDER.sub("X", token)
    if re.search(r"\s", plain) or is_test_name(token):
        return False
    return plain.startswith(("~/", ".git/")) or bool(EXTENSION.search(basename(plain)))


def pin_name(token):
    """What a test must hold to pin the token: its basename, or the folder before a placeholder basename."""
    parts = [p for p in token.split("/") if p]
    base = parts[-1]
    if "<" not in base:
        return base
    literal = [p for p in parts[:-1] if "<" not in p and p not in ("~", ".")]
    return literal[-1] if literal else None


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def pinned(token, candidates, root):
    name = pin_name(token)
    if not name:
        return False
    for candidate in candidates:
        text = read(os.path.join(root, *candidate.split("/")))
        if text is not None and name in text:
            return True
    return False


def check(root):
    """The findings of the records under `root` as (record, line, token), in file order."""
    findings = []
    # the first folder that exists: a repo not yet rolled out to the layout keeps its records at the legacy path
    home = next((h for h in layout.candidates(root, "decisions") if os.path.isdir(os.path.join(root, *h.split("/")))),
                layout.path(root, "decisions"))
    for path in sorted(glob.glob(os.path.join(root, *home.split("/"), "*.md"))):
        record = home + "/" + os.path.basename(path)
        text = read(path)
        if text is None:
            continue
        for paragraph in paragraphs(text.splitlines()):
            for sentence in sentences(paragraph):
                if EXEMPT.search("".join(c for _, c in sentence)):
                    continue
                spans = tokens(sentence)
                candidates = [t for t, _ in spans if is_test_name(t) and EXTENSION.search(basename(t))]
                for token, number in spans:
                    row = (record, number, token)
                    if is_file(token) and row not in findings and not pinned(token, candidates, root):
                        findings.append(row)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=ROOT)
    args = parser.parse_args(argv)
    findings = check(args.root)
    for record, number, token in findings:
        print("%s:%d: %s named in a Cost sentence with no pin" % (record, number, token))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
