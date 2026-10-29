#!/usr/bin/env python3
"""The waiting-page writer's one splice: put a fresh roadmap block into the live page (skill waiting-page).

    python3 ~/.claude/skills/waiting-page/splice.py --page LIVE.html --block FILE --out OUT.html

LIVE.html is the page as Artifact `read` returned it. FILE is the block that
`skills/roadmap/build.py --block` wrote. OUT.html is LIVE.html with its roadmap block (from
`<!-- roadmap:data -->` to `<!-- /roadmap:data -->`, markers included) replaced by FILE's text. Every
other byte stays, the designData block among them, so the answers' page keeps its mockups.

A marker counts only as a comment in the page's markup. Text inside <script>, <style>, <textarea> and
<title> is raw text, so a marker written in a JS string or a template literal is not a block marker.
The splice refuses, and writes no file, when the live page has no block, an unclosed block, or more
than one block, and when FILE is not one marked block. The message names the roadmap block.
Cost: one read of each file and one write; no process starts.
"""
import argparse
import re
import sys

OPEN, CLOSE = "roadmap:data", "/roadmap:data"
RAW = ("script", "style", "textarea", "title")
TAG = re.compile(r"<(%s)(?=[\s/>])" % "|".join(RAW), re.I)


def markers(text):
    """[(name, start, end)] for each roadmap marker comment in the markup, outside raw-text elements."""
    found, at = [], 0
    while True:
        at = text.find("<", at)
        if at < 0:
            return found
        if text.startswith("<!--", at):
            shut = text.find("-->", at + 4)
            end = len(text) if shut < 0 else shut + 3
            body = text[at + 4:end if shut < 0 else shut].strip()
            if body in (OPEN, CLOSE):
                found.append((body, at, end))
            at = end
            continue
        tag = TAG.match(text, at)
        if not tag:
            at += 1
            continue
        quote = None
        for i in range(at + 1, len(text)):  # the end of the opening tag: a ">" inside a quoted value does not count
            c = text[i]
            if quote:
                quote = None if c == quote else quote
            elif c in "\"'":
                quote = c
            elif c == ">":
                end = i
                break
        else:
            return found
        close = re.compile(r"</%s(?=[\s/>])" % tag.group(1), re.I).search(text, end)
        if not close:
            return found
        at = close.end()


def block_span(text, what):
    """(start, end) of the one roadmap block in `text`; SystemExit when there is not exactly one."""
    found = markers(text)
    names = [m[0] for m in found]
    if names != [OPEN, CLOSE]:
        if not found:
            why = "has no roadmap block (no marker outside script text)"
        elif names.count(OPEN) != names.count(CLOSE) or names[0] != OPEN:
            why = "has an unclosed or unpaired roadmap block"
        else:
            why = "has more than one roadmap block"
        raise SystemExit("splice: %s %s, so nothing was written." % (what, why))
    return found[0][1], found[1][2]


def splice(page, block):
    """`page` with its roadmap block replaced by `block`, every other byte kept."""
    start, end = block_span(page, "the live page")
    b0, b1 = block_span(block, "the block file")
    if block[:b0].strip() or block[b1:].strip():
        raise SystemExit("splice: the block file holds more than the roadmap block, so nothing was written.")
    return page[:start] + block[b0:b1] + page[end:]


def main(argv):
    ap = argparse.ArgumentParser(description="Splice a roadmap block into the live waiting page.")
    ap.add_argument("--page", required=True, help="the live page, as read")
    ap.add_argument("--block", required=True, help="the block file from roadmap/build.py --block")
    ap.add_argument("--out", required=True, help="the page to write")
    args = ap.parse_args(argv)
    with open(args.page, encoding="utf-8", newline="") as f:
        page = f.read()
    with open(args.block, encoding="utf-8", newline="") as f:
        block = f.read()
    result = splice(page, block)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
