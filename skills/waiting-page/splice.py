#!/usr/bin/env python3
"""The waiting-page writer's one splice: put a fresh roadmap block into the live page (skill waiting-page).

    python3 ~/.claude/skills/waiting-page/splice.py --page LIVE.html --block FILE --out OUT.html
    python3 ~/.claude/skills/waiting-page/splice.py --page TEMPLATE.html --carry LIVE.html --out OUT.html

The first form replaces the roadmap block. The second, --carry, is for a republish of a changed
template: OUT.html is TEMPLATE.html with the live page's designData block, roadmap block and <title>
text put in, byte for byte, in place of the template's own (a live page with no title leaves the
template's). A live page with no roadmap marker outside script text
predates the block: only its designData block goes in, and the template keeps its empty roadmap block.
It refuses, and writes nothing, when the template lacks either block, when either file has an unclosed,
doubled or unpaired roadmap block or a doubled designData block, or when the live page has no designData
block.

In the first form, LIVE.html is the page as Artifact `read` returned it. FILE is the block that
`skills/roadmap/build.py --block` wrote. OUT.html is LIVE.html with its roadmap block (from
`<!-- roadmap:data -->` to `<!-- /roadmap:data -->`, markers included) replaced by FILE's text. Every
other byte stays, the designData block among them, so the answers' page keeps its mockups.

A marker counts only as a comment in the page's markup. Text inside <script>, <style>, <textarea> and
<title> is raw text, so a marker, or a designData script, written in a JS string or a template literal
is not a block.
The splice refuses, and writes no file, when the live page has no block, an unclosed block, or more
than one block, and when FILE is not one marked block. The message names the roadmap block.
Cost: one read of each file and one write; no process starts.
"""
import argparse
import re
import sys

OPEN, CLOSE = "roadmap:data", "/roadmap:data"
DESIGN = "designData"
TITLE = "title"
DESIGN_ID = re.compile(r"""\bid\s*=\s*["']?designData["']?(?=[\s/>"'])""", re.I)
RAW = ("script", "style", "textarea", "title")
TAG = re.compile(r"<(%s)(?=[\s/>])" % "|".join(RAW), re.I)


def scan(text):
    """[(name, start, end)] in the markup, outside raw-text elements: each roadmap marker comment, each
    designData script element (start of its opening tag to the end of its closing tag), and each
    title element's text (TITLE, the raw text between its tags)."""
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
        at_tag = at
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
        if tag.group(1).lower() == "title":
            found.append((TITLE, end + 1, close.start()))
        if tag.group(1).lower() == "script" and DESIGN_ID.search(text, at_tag, end):
            shut = text.find(">", close.end())
            at = len(text) if shut < 0 else shut + 1
            found.append((DESIGN, at_tag, at))


def markers(text):
    """[(name, start, end)] for each roadmap marker comment, as scan() finds it."""
    return [m for m in scan(text) if m[0] in (OPEN, CLOSE)]


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


def design_span(text, what):
    """(start, end) of the one designData script element in `text`; SystemExit when there is not exactly one."""
    spans = [m for m in scan(text) if m[0] == DESIGN]
    if len(spans) != 1:
        raise SystemExit("splice: %s has %s designData block, so nothing was written." % (what, "no" if not spans else "more than one"))
    return spans[0][1], spans[0][2]


def title_span(text):
    """(start, end) of the text of the first title element in the markup, or None when there is none."""
    spans = [m for m in scan(text) if m[0] == TITLE]
    return (spans[0][1], spans[0][2]) if spans else None


def carry(template, live):
    """`template` with the live page's designData block, roadmap block and title text in place of its own, byte for byte.
    A live page with no roadmap marker in its markup predates the block: it gives only its designData block,
    and the template keeps its empty roadmap block. A live page with no title keeps the template's."""
    t_design, l_design = design_span(template, "the template"), design_span(live, "the live page")
    t_block = block_span(template, "the template")
    swaps = [(t_design, live[l_design[0]:l_design[1]])]
    t_title, l_title = title_span(template), title_span(live)
    if t_title and l_title:
        swaps.append((t_title, live[l_title[0]:l_title[1]]))
    if markers(live):
        l_block = block_span(live, "the live page")
        swaps.append((t_block, live[l_block[0]:l_block[1]]))
    swaps.sort(reverse=True)
    for (start, end), text in swaps:  # the later block first, so the earlier offsets hold
        template = template[:start] + text + template[end:]
    return template


def splice(page, block):
    """`page` with its roadmap block replaced by `block`, every other byte kept."""
    start, end = block_span(page, "the live page")
    b0, b1 = block_span(block, "the block file")
    if block[:b0].strip() or block[b1:].strip():
        raise SystemExit("splice: the block file holds more than the roadmap block, so nothing was written.")
    return page[:start] + block[b0:b1] + page[end:]


def main(argv):
    ap = argparse.ArgumentParser(description="Splice a roadmap block into the live waiting page, or carry the live blocks into a template.")
    ap.add_argument("--page", required=True, help="the live page, as read; with --carry, the template")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--block", help="the roadmap block file from roadmap/build.py --block")
    group.add_argument("--carry", help="the live page whose designData and roadmap blocks go into --page")
    ap.add_argument("--out", required=True, help="the page to write")
    args = ap.parse_args(argv)
    with open(args.page, encoding="utf-8", newline="") as f:
        page = f.read()
    with open(args.block or args.carry, encoding="utf-8", newline="") as f:
        other = f.read()
    result = splice(page, other) if args.block else carry(page, other)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
