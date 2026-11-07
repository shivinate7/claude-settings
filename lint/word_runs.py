"""The one home of word-run matching: normalize Markdown to words, then find runs of words that two texts share.

Standard library only, and no side effects on import (the copy finder, the stale-cites check and the `restates` probe
of lint/compliance_probes.py all import it). Rule building-one-home-per-capability.

Two normal forms read the same spans in one left-to-right pass, so a mark inside one span never opens another:
- probe form (`keep=False`): HTML comments and code spans are dropped, and so is any word that holds a digit. The
  `restates` probe compares prose with records in this form.
- copy form (`keep=True`): HTML comments are dropped, a code span keeps its text, a link keeps its text and not its
  address, a parenthesised gloss right after a code span that is one id becomes a gap no run crosses, and digits are words. The copy finder and the reword check compare a rule sentence with a file in this form.
Both lowercase, keep letters as words, and turn a line break into a space. A comment opener inside a code span, a lone
quote and a `//` in text change no word.

`units` cuts a Markdown text into the places a rule id may exempt a copy: a paragraph, a list item, a table row, a
blockquote, a heading and a fenced block.
"""
import re

# One pass, left to right: a code span (the closer is a run of the same length) or an HTML comment. An opener with no
# closer is plain text. A comment may run over lines, so the dot matches a line break (re.S). A code span stops at a
# blank line, as in Markdown, so a lone backtick pairs with none in a later paragraph. A parenthesised gloss right after
# a code span is matched with it, so the copy form can drop the gloss of an id (see ID_SPAN).
SPANS = re.compile(r"(?P<tick>`+)(?!`)(?P<inner>(?:(?!\n[ \t]*\n).)*?)(?<!`)(?P=tick)(?!`)"
                   r"(?P<gloss>[ \t]*\([^()\n]*\))?|<!--.*?-->", re.S)
# The whole span forms, for the checks that blank or find them on a paragraph (rule_audit, stale_cites).
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
# A sentence ends at . ! or ? before a space or the end. "e.g.", "i.e.", "vs." and "cf." end none, so a paren group
# such as "(e.g. read hooks/x.py:2)" stays in one sentence.
SENTENCE_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bcf)[.!?](?=\s|\Z)")
GAP = " \0 "
COPY_FLOOR = 8  # words in a row of a rule sentence that make a copy; a stock phrase under it passes. Also the length at which a gloss is text
ID_SPAN = re.compile(r"[\w.:/-]+\Z")  # a code span that is one id; "`hold-unsafe-x` (net-value hold)" glosses an id
NUMBERED = re.compile(r"\S*\d\S*")
LINK = re.compile(r"\[([^\]\n]*)\]\([^)\n]*\)")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")  # the raw pattern, any indent; ask is_fence whether a line is a fence
TABLE_ROW = re.compile(r"^[ \t]{0,3}\|")
QUOTE = re.compile(r"^[ \t]{0,3}>")
HEADING = re.compile(r"^[ \t]{0,3}#{1,6}(?:[ \t]|$)")
LIST_ITEM = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")


def _blank_keeping_lines(match):
    """A blank for the span, its line breaks kept, and a gloss kept after a code span (probe form)."""
    span = match.group(0)
    gloss = match.group("gloss") or ""
    return " " + "\n" * span[:len(span) - len(gloss)].count("\n") + gloss


def _copy_form_span(match):
    """The copy form of a span: a comment goes, a code span keeps its text, and the gloss of an id under COPY_FLOOR words
    becomes GAP, because a rule cites its own decision that way and the gloss is no sentence of the rule. A gloss of
    COPY_FLOOR words or more is text, so a rule sentence pasted as a gloss is a copy. GAP is a word no text holds, so a
    run of words never crosses it, and a gap on both sides still matches itself."""
    if not match.group("tick"):
        return _blank_keeping_lines(match)
    inner, gloss = match.group("inner"), match.group("gloss") or ""
    short = len(re.findall(r"[a-z0-9]+", gloss.lower())) < COPY_FLOOR
    return inner + (GAP if gloss and short and ID_SPAN.match(inner) else gloss)


def tokens(text, keep=False):
    """[(word, line offset)] of `text`: the words in the form above, each with the 0-based line of the text it sits on."""
    if keep:
        text = SPANS.sub(_copy_form_span, text)
        text = LINK.sub(r"\1", text)
        pattern = r"[a-z0-9]+|\0"
    else:
        text = NUMBERED.sub(" ", SPANS.sub(_blank_keeping_lines, text))
        pattern = r"[a-z]+"
    return [(word, number) for number, line in enumerate(text.lower().split("\n"), 0)
            for word in re.findall(pattern, line)]


def words(text, keep=False):
    return [word for word, _ in tokens(text, keep)]


def windows(word_list, size):
    """Each run of `size` words in a row, as a tuple. None when the list is shorter."""
    return [tuple(word_list[at:at + size]) for at in range(len(word_list) - size + 1)]


def added_words(short, long):
    """The words of `long` that are not part of `short`, when `long` holds every word of `short` in the same order (other
    words between); None when it does not."""
    rest = iter(short)
    pending, added = next(rest, None), []
    for word in long:
        if pending is not None and word == pending:
            pending = next(rest, None)
        else:
            added.append(word)
    return added if pending is None else None


def run_index(owners, size):
    """{run of `size` words: [owner, ...]} for `owners`, a {owner: [word list, ...]}. Each owner's list of words under
    `size` words holds no run, so it is never a match."""
    index = {}
    for owner, lists in owners.items():
        for word_list in lists:
            for run in windows(word_list, size):
                holders = index.setdefault(run, [])
                if owner not in holders:
                    holders.append(owner)
    return index


def shared(word_list, index, size):
    """({owner: number of positions of `word_list` inside a run `index` holds for that owner}, the number of
    positions inside a run of any owner). The `restates` probe reads these counts."""
    per_owner, anywhere = {}, set()
    for at, run in enumerate(windows(word_list, size)):
        for owner in index.get(run, ()):
            per_owner.setdefault(owner, set()).update(range(at, at + size))
            anywhere.update(range(at, at + size))
    return {owner: len(hit) for owner, hit in per_owner.items()}, len(anywhere)


def first_lines(unit_text, index, size):
    """{owner: 0-based line of the first run of `size` words that the unit shares with that owner}, in the copy form."""
    pairs = tokens(unit_text, keep=True)
    found = {}
    for at in range(len(pairs) - size + 1):
        for owner in index.get(tuple(w for w, _ in pairs[at:at + size]), ()):
            found.setdefault(owner, pairs[at][1])
    return found


def names(unit_text, rule_id):
    """True when the unit holds `rule_id` as a whole name, as text or inside an anchor comment."""
    return re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(rule_id), unit_text) is not None


def _indent(line):
    """The width of the spaces and tabs that start `line`, a tab reaching the next multiple of four."""
    return len(line[:len(line) - len(line.lstrip(" \t"))].expandtabs(4))


def is_fence(line, in_list_item=False):
    """True when `line` is a fence line, as CommonMark reads it. A line indented four columns or more is indented code
    at the top level, so it is a fence only inside a list item (`in_list_item`, from `list_item_after`). FENCE is the raw
    pattern for the marker; the rule about a backtick in the info string stays with the reader that opens a fence."""
    found = FENCE.match(line)
    return bool(found) and (in_list_item or _indent(line) <= 3)


def list_item_after(line, in_list_item):
    """Whether the line after `line` sits in a list item, given whether `line` did. A list item line starts one (at the
    top level it is indented three columns at most); a blank line or a line indented two columns or more keeps the
    state; any other line ends it. A reader calls it on each line outside a fence and keeps the state it returns."""
    if not line.strip():
        return in_list_item
    if LIST_ITEM.match(line) and (in_list_item or _indent(line) <= 3):
        return True
    return in_list_item and _indent(line) >= 2


def fence_ranges(rows):
    """[(first, last)] 0-based row indexes of each fenced block, fence rows included. A closer is a run of the opener's
    character, at least as long, with nothing after it. An unclosed fence runs to the last row. Fence lines are those
    `is_fence` accepts; the closer reads the list context of its opener."""
    found, opener, first = [], None, 0
    in_item = opener_in_item = False
    for number, row in enumerate(rows):
        fence = FENCE.match(row) if is_fence(row, in_item if opener is None else opener_in_item) else None
        if opener is None:
            if fence and not (fence.group(1)[0] == "`" and "`" in row[fence.end():]):  # a span, not a fence
                opener, first, opener_in_item = fence.group(1), number, in_item
            else:
                in_item = list_item_after(row, in_item)
        elif fence and fence.group(1)[0] == opener[0] and len(fence.group(1)) >= len(opener) \
                and not row.strip()[len(fence.group(1)):].strip():
            found.append((first, number))
            opener = None
    if opener is not None:
        found.append((first, len(rows) - 1))
    return found


def mask_fences(text):
    """`text` with each fenced block's rows emptied, so the line count stays and a paragraph ends where a fence was."""
    rows = text.replace("\r\n", "\n").split("\n")
    for first, last in fence_ranges(rows):
        rows[first:last + 1] = [""] * (last + 1 - first)
    return "\n".join(rows)


def units(text):
    """[(line number of the unit's first line, 1-based, the unit's text)]: a fenced block is one unit, a table row one,
    a heading one, consecutive blockquote lines one, a list item one, and a paragraph runs to a blank line or to any
    of those."""
    rows = text.replace("\r\n", "\n").split("\n")
    fences = {first: last for first, last in fence_ranges(rows)}
    out, current, kind, in_item = [], [], None, False

    def flush():
        nonlocal current, kind
        if current:
            out.append((current[0][0], "\n".join(line for _, line in current)))
        current, kind = [], None

    at = 0
    while at < len(rows):
        line, number = rows[at], at + 1
        if at in fences:
            if line[:1] in (" ", "\t") and kind in ("item", "prose"):  # indented: it continues the item or paragraph
                current.extend((n + 1, rows[n]) for n in range(at, fences[at] + 1))
            else:
                flush()
                out.append((number, "\n".join(rows[at:fences[at] + 1])))
            at = fences[at] + 1
            continue
        at += 1
        item_before, in_item = in_item, list_item_after(line, in_item)
        if not line.strip():
            flush()
        elif kind is None and not item_before and FENCE.match(line):
            # No fence (fence_ranges said so) at the top level and not inside a paragraph: indented code, a unit of its own
            out.append((number, line))
        elif TABLE_ROW.match(line) or HEADING.match(line):
            flush()
            current.append((number, line))
            flush()
        elif QUOTE.match(line):
            if kind != "quote":
                flush()
            kind = "quote"
            current.append((number, line))
        elif LIST_ITEM.match(line):
            flush()
            kind = "item"
            current.append((number, line))
        else:
            if kind == "quote":
                flush()
            kind = kind or "prose"
            current.append((number, line))
    flush()
    return out
