#!/usr/bin/env python3
"""The page writer's one splice: put a fresh roadmap block into the live page (skill waiting-page).

    python3 ~/.claude/skills/waiting-page/splice.py --page LIVE.html --block FILE --out OUT.html
    python3 ~/.claude/skills/waiting-page/splice.py --page TEMPLATE.html --carry LIVE.html --out OUT.html

The first form replaces the roadmap block. The second, --carry, is for a republish of a changed
template: OUT.html is TEMPLATE.html with the live page's designData block, roadmap block and <title>
text put in, byte for byte, in place of the template's own (a live page with no title leaves the
template's). A live title of an old form (Queue, <X> Queue, <X> Queue \u00b7 Status, Roadmap, <X> Roadmap) is
renamed to "<X> Cockpit" (PAGE_NAME); every other title carries as is. A live page with no roadmap marker outside script text
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
prune_designs(text, items) is the one home of dropping a closed item's mockups (not a parked item's) from a page's designData block;
the prune re-serialises the block, so the kept mockups' values stay equal and their bytes may differ
(stale_pages.py --write --items calls it after carry; carry and --block never prune).
Cost: one read of each file and one write; no process starts.
"""
import argparse
import json
import re
import sys

OPEN, CLOSE = "roadmap:data", "/roadmap:data"
DESIGN = "designData"
TITLE = "title"
PAGE_NAME = "Cockpit"  # the one home of the page's name: its title is "<repo> Cockpit"
# A live title of an old form: an optional "<X> " prefix, then Queue, Queue · Status or Roadmap.
OLD_TITLE = re.compile("(?P<prefix>.* )?(?:Queue(?: \u00b7 Status)?|Roadmap)", re.S)
SVG_OPEN, SVG_CLOSE = "svg-open", "svg-close"
SVG_TAG = re.compile(r"<(/?)svg(?=[\s/>])", re.I)
DESIGN_ID = re.compile(r"""\bid\s*=\s*["']?designData["']?(?=[\s/>"'])""", re.I)
DESIGN_ELEMENT = re.compile(r"""(<script(?:[^>"']|"[^"]*"|'[^']*')*>)(.*)(</script[^>]*>)""", re.S | re.I)
RAW = ("script", "style", "textarea", "title")
TAG = re.compile(r"<(%s)(?=[\s/>])" % "|".join(RAW), re.I)


def scan(text):
    """[(name, start, end)] in the markup, outside raw-text elements: each roadmap marker comment, each
    designData script element (start of its opening tag to the end of its closing tag), each
    title element's text (TITLE, the raw text between its tags), and each svg tag (SVG_OPEN, SVG_CLOSE)."""
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
        svg = SVG_TAG.match(text, at)
        if svg:
            found.append((SVG_CLOSE if svg.group(1) else SVG_OPEN, at, at))
            at += 1
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


def named_slugs(item):
    """The mockup slugs one item names: each `designs[].slug`, and each `options[].design` (an older item names them there only)."""
    slugs = set()
    if not isinstance(item, dict):
        return slugs
    for key, field in (("designs", "slug"), ("options", "design")):
        for entry in item.get(key) or []:
            if isinstance(entry, dict) and isinstance(entry.get(field), str):
                slugs.add(entry[field])
    return slugs


def parked(item):
    """True when `item` was closed by a Park."""
    answer = item.get("lastAnswer")
    return isinstance(answer, dict) and answer.get("act") == "park"


def prune_designs(text, items):
    """`text` with the mockups of closed items dropped from its designData block; every byte outside the block stays.
    A slug goes only when each item that names it is closed (status "closed"), is not an arbiter ruling (`arbiter` true),
    since an Overturn reopens a ruling, and was not parked (`lastAnswer.act` "park"), since an Unpark reopens it with no
    design restore. A slug no item names stays: the writer publishes a mockup before its item. A slug named
    by an open item as well stays. The block is rewritten only when a slug goes, as one JSON object (the kept mockups' values
    stay equal, their bytes may differ) with each `<` written as \\u003c (so no string can close the script); an unreadable block, or one that is no object, is left as is. SystemExit
    when `text` has no single designData block. The caller passes a complete items list: a cut-short one would keep too little."""
    start, end = design_span(text, "the page")
    parts = DESIGN_ELEMENT.fullmatch(text[start:end])
    try:
        designs = json.loads(parts.group(2))
    except (ValueError, AttributeError):
        return text
    if not isinstance(designs, dict):
        return text
    kept, dropped = set(), set()
    for item in items:
        done = isinstance(item, dict) and item.get("status") == "closed" and item.get("arbiter") is not True and not parked(item)
        (dropped if done else kept).update(named_slugs(item))
    gone = {slug for slug in dropped - kept if slug in designs}
    if not gone:
        return text
    rest = {slug: html for slug, html in designs.items() if slug not in gone}
    return text[:start] + parts.group(1) + json.dumps(rest).replace("<", "\\u003c") + parts.group(3) + text[end:]


def title_span(text):
    """(start, end) of the text of the page's own document title, or None when there is none: the last title
    element in the markup that is not inside an svg. A host's skeleton title comes before the page's."""
    depth, span = 0, None
    for name, start, end in scan(text):
        if name == SVG_OPEN:
            depth += 1
        elif name == SVG_CLOSE:
            depth = max(depth - 1, 0)
        elif name == TITLE and not depth:
            span = (start, end)
    return span


def renamed_title(text):
    """The live title text; an old-form title becomes its prefix and PAGE_NAME. Built by slicing, so live text is never a replacement string."""
    found = OLD_TITLE.fullmatch(text)
    if not found:
        return text
    return text[:found.end("prefix")] + PAGE_NAME if found.group("prefix") else PAGE_NAME


def carry(template, live):
    """`template` with the live page's designData block, roadmap block and title text in place of its own, byte for byte.
    A live title of an old form (Queue, <X> Queue, <X> Queue · Status, Roadmap, <X> Roadmap) is renamed to <X> PAGE_NAME; any other title is copied as is.
    A live page with no roadmap marker in its markup predates the block: it gives only its designData block,
    and the template keeps its empty roadmap block. A live page with no title keeps the template's."""
    t_design, l_design = design_span(template, "the template"), design_span(live, "the live page")
    t_block = block_span(template, "the template")
    swaps = [(t_design, live[l_design[0]:l_design[1]])]
    t_title, l_title = title_span(template), title_span(live)
    if t_title and l_title:
        swaps.append((t_title, renamed_title(live[l_title[0]:l_title[1]])))
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
