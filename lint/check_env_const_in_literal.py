#!/usr/bin/env python3
"""Fails when a test file writes a constant's name between two quotes inside one string literal.

    python3 lint/check_env_const_in_literal.py [--root DIR]

A test-author once wrote a quote, `+`, ENV, `+` and a quote inside one literal, meaning to join strings. The text
stayed one string, so eight guard cases never named the env file and passed while testing nothing. A hit is a
quote, `+`, a NAME or dotted NAME, `+` and a quote, all inside the body of ONE string literal. A real
concatenation outside a literal, and the same words in a comment, never hit. A literal can also hold the source
of another program, such as a stub script, where `"a" + x + "b"` is a real concatenation. There the first quote
of the match closes a string that opened earlier in the body (an odd count of that quote before it), so the
match is skipped. In the incident the first quote opens a string.

Scans only the direct children hooks/test_*.py and lint/test_*.py of DIR (default: the current directory).
It reads each file with `tokenize`, so a comment opener, a lone quote or a multi-line string inside a literal
never moves a line. Python 3.11 and earlier tokenize an f-string as one STRING token; 3.12 and later split it
into FSTRING_START, FSTRING_MIDDLE and FSTRING_END, and the literal text is in the MIDDLE tokens.

Cost: no process starts, each scanned file is read once, nothing is written. Stdlib only.

Exit 0 clean. Exit 1 on a hit, one line per hit: `path:line: env-const-in-literal: matched text`.
Exit 2 when a scanned file cannot be read or tokenized: an unread file is never clean. An unread file does not
stop the scan: every other file is read, every hit prints, and the run then exits 2.
"""
import argparse
import glob
import io
import os
import re
import sys
import tokenize

SCANNED = ("hooks", "lint")
RULE = "env-const-in-literal"
QUOTE = "[\"']"
NAME = r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*"
PATTERN = re.compile(r"%s\s*\+\s*%s\s*\+\s*%s" % (QUOTE, NAME, QUOTE))
UNESCAPED = {q: re.compile(r"(?<!\\)" + q) for q in "\"'"}
STRING_PREFIX = re.compile(r"^[A-Za-z]*(\"\"\"|'''|\"|')")
FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", None)


def literal_bodies(source):
    """Yield (first line, body text) for each string literal body in the source. Raises on an untokenizable file."""
    tokens = list(tokenize.tokenize(io.BytesIO(source).readline))
    for tok in tokens:
        if tok.type == tokenize.STRING:
            head = STRING_PREFIX.match(tok.string)
            if head is None:
                continue
            opener = head.group(1)
            yield tok.start[0], tok.string[head.end():len(tok.string) - len(opener)]
        elif FSTRING_MIDDLE is not None and tok.type == FSTRING_MIDDLE:
            yield tok.start[0], tok.string


def hits_in(source):
    """Return (line, matched text) for each hit, the line being the one the match starts on."""
    found = []
    for line, body in literal_bodies(source):
        for m in PATTERN.finditer(body):
            if len(UNESCAPED[m.group(0)[0]].findall(body, 0, m.start())) % 2:
                continue
            found.append((line + body.count("\n", 0, m.start()), " ".join(m.group(0).split())))
    return found


def scan(root):
    """Return (printed hit lines, unreadable file count) for the scanned test files under root."""
    out, unknown = [], 0
    for folder in SCANNED:
        for path in sorted(glob.glob(os.path.join(glob.escape(root), folder, "test_*.py"))):
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            try:
                with open(path, "rb") as f:
                    found = hits_in(f.read())
            except (OSError, SyntaxError, UnicodeError, tokenize.TokenError) as exc:
                print("%s: unknown: %s" % (rel, exc), file=sys.stderr)
                unknown += 1
                continue
            out.extend("%s:%d: %s: %s" % (rel, line, RULE, text) for line, text in found)
    return out, unknown


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=".", help="the tree to scan (default: the current directory)")
    args = parser.parse_args(argv)
    lines, unknown = scan(args.root)
    for line in lines:
        print(line)
    if unknown:
        return 2
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
