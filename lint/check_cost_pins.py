#!/usr/bin/env python3
"""Fails when a decision record's Cost sentence names a file that no test pins.

    python3 lint/check_cost_pins.py [--root DIR]

A Cost paragraph starts at a line whose first word is `Cost` followed by a character that is not a letter
(`Cost:`, `Cost.`, `Cost, per`, `Cost of`, `**Cost**:`), bare or after a list marker or bold marks. `Costs` and `Costly`
start none. It runs until a blank line, a list item at the same or a lesser indent than the Cost line, a heading or a
code fence. A deeper list item stays in it. Fenced code is not read. A paragraph with an odd number of backticks cannot
be read: it is one finding on its first line.

Each sentence of a paragraph is read alone. A sentence ends at ". ", "! " or "? " outside backticks, or at the
paragraph end. Closing marks `)`, `*`, `"` and `'` after the stop belong to the sentence it ends.

A file token is a backticked name that ends in a known file extension (EXTENSIONS, any case), or starts with `~/` or
`.git/`. A trailing `:<digits>` (a line number) is dropped before the test, and the token is reported as written. A
token whose name is a test file (`test_*`, `*_test.*`, `*.test.*`) is a pin candidate, not a file token. A token is
flagged whether or not its file exists. It is pinned when a candidate in the same sentence exists under the root and
holds the token's name as a whole name: its basename, or the folder before a `<placeholder>` basename, with no letter,
digit, `_`, `-` or `.`-and-name character beside it. A sentence that says "not pinned", "unpinned", "unmeasured" or
"no test" pins nothing and flags nothing: the writer has said so.

The report is one line per token and line: `<record>:<line>: <token> named in a Cost sentence with no pin`.
Exit 1 when there is a finding, 0 when there is none. Only the decision records (kind `decisions` in lint/layout.json)
are read: a debt's Cost line is not. Each test file is read once per run.
"""
import argparse
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COST_START = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?Cost(?![A-Za-z])")
LIST_ITEM = re.compile(r"^(\s*)(?:[-*]|\d+[.)])\s")
HEADING = re.compile(r"^\s{0,3}#")
FENCE = re.compile(r"^\s*(?:```|~~~)")
EXEMPT = re.compile(r"\b(?:not pinned|unpinned|unmeasured|no test)", re.IGNORECASE)
PLACEHOLDER = re.compile(r"<[^<>]*>")
# A bare `tool.call` or `e.g.` has a dot and no file, so only these extensions mark a file.
EXTENSIONS = ("md py mjs js ts tsx json jsonl sh ps1 cmd bat html css yml yaml toml txt log csv tmpl sql cfg ini "
              "lock xml").split()
EXTENSION = re.compile(r"^.+\.(?:%s)$" % "|".join(EXTENSIONS), re.IGNORECASE)
LINE_SUFFIX = re.compile(r"(?::\d+)+$")
TEST_NAME = re.compile(r"^(?:test_.*|.*_test\..*|.*\.test\..*)$")
CLOSERS = ")*\"'"
UNBALANCED = "unbalanced backtick in a Cost paragraph"


def indent_of(text):
    return len(text) - len(text.lstrip(" \t"))


def paragraphs(lines):
    """Each Cost paragraph of `lines` as a list of (line number, text)."""
    found, current, fenced, base = [], None, False, 0
    for number, text in enumerate(lines, 1):
        if FENCE.match(text):
            fenced = not fenced
            current = None
            continue
        if fenced:
            continue
        item = LIST_ITEM.match(text)
        if COST_START.match(text):
            current, base = [(number, text)], indent_of(text)
            found.append(current)
        elif (current is not None and text.strip() and not HEADING.match(text)
              and not (item and indent_of(text) <= base)):
            current.append((number, text))
        else:
            current = None
    return found


def read_paragraph(paragraph):
    """(sentences, balanced) of one paragraph, from one pass over its backticks.

    A sentence is (text, spans): spans is [(code span text, line number)]. A backtick holds the sentence open,
    so a stop inside a code span ends nothing, and each span lies wholly inside one sentence."""
    chars = [(number, c) for number, text in paragraph for c in text + "\n"]
    sentences, text, spans, inside, opened, i = [], [], [], False, 0, 0
    while i < len(chars):
        c = chars[i][1]
        text.append(c)
        if c == "`":
            if inside:
                spans.append(("".join(ch for _, ch in chars[opened + 1:i]), chars[opened + 1][0]))
            else:
                opened = i
            inside = not inside
        elif c in ".!?" and not inside:
            j = i + 1
            while j < len(chars) and chars[j][1] in CLOSERS:
                j += 1
            if j == len(chars) or chars[j][1].isspace():
                text.extend(ch for _, ch in chars[i + 1:j])
                sentences.append(("".join(text), spans))
                text, spans, i = [], [], j - 1
        i += 1
    if "".join(text).strip():
        sentences.append(("".join(text), spans))
    return sentences, not inside


def basename(token):
    return token.rstrip("/").rsplit("/", 1)[-1]


def bare(token):
    """The token without a trailing line number."""
    return LINE_SUFFIX.sub("", token)


def is_test_name(token):
    return bool(TEST_NAME.match(basename(bare(token))))


def is_file(token):
    plain = PLACEHOLDER.sub("X", bare(token))
    if re.search(r"\s", plain) or is_test_name(token):
        return False
    return plain.startswith(("~/", ".git/")) or bool(EXTENSION.search(basename(plain)))


def pin_name(token):
    """What a test must hold to pin the token: its basename, or the folder before a placeholder basename."""
    parts = [p for p in bare(token).split("/") if p]
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


def pinned(token, candidates, root, texts):
    name = pin_name(token)
    if not name:
        return False
    # The name stands alone: no name character before it, and none after it but a stop that ends the word.
    whole = re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(name) + r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-])")
    for candidate in candidates:
        rel = bare(candidate)
        if rel not in texts:
            texts[rel] = read(os.path.join(root, *rel.split("/")))
        if texts[rel] is not None and whole.search(texts[rel]):
            return True
    return False


def check(root):
    """The findings of the records under `root` as (record, line, token, message), in file order.
    `token` is None for a finding that names no token."""
    findings, texts = [], {}
    # the first folder that exists: a repo not yet rolled out to the layout keeps its records at the legacy path
    homes = layout.candidates(root, "decisions")
    home = next((h for h in homes if os.path.isdir(os.path.join(root, *h.split("/")))), homes[0])
    for path in sorted(glob.glob(os.path.join(root, *home.split("/"), "*.md"))):
        record = home + "/" + os.path.basename(path)
        text = read(path)
        if text is None:
            continue
        for paragraph in paragraphs(text.splitlines()):
            sentences, balanced = read_paragraph(paragraph)
            if not balanced:
                findings.append((record, paragraph[0][0], None, UNBALANCED))
                continue
            for sentence, spans in sentences:
                if EXEMPT.search(sentence):
                    continue
                candidates = [t for t, _ in spans if is_test_name(t) and EXTENSION.search(basename(bare(t)))]
                for token, number in spans:
                    row = (record, number, token, "%s named in a Cost sentence with no pin" % token)
                    if is_file(token) and row not in findings and not pinned(token, candidates, root, texts):
                        findings.append(row)
    return findings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=ROOT)
    args = parser.parse_args(argv)
    findings = check(args.root)
    for record, number, _token, message in findings:
        print("%s:%d: %s" % (record, number, message))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
