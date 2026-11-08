#!/usr/bin/env python3
"""Fails when a decision record's Cost sentence names a file that no test pins. It also fails on a count with no
reader, in a Cost sentence or in a debt note.

    python3 lint/check_cost_pins.py [--root DIR]

A Cost paragraph starts at a line whose first word is `Cost` followed by a character that is not a letter
(`Cost:`, `Cost.`, `Cost, per`, `Cost of`, `**Cost**:`), bare or after a list marker (`-`, `*`, `8.`, `3)`) or bold
marks. `Costs` and `Costly` start none. A sentence that starts in any of these forms after the stop of an earlier sentence on
its line starts one too, from that sentence. It runs until a blank line, a list item at the same or a lesser indent than the
Cost line, a heading (one to six `#` and a space) or a code fence. A deeper line or list item stays in it. Fenced code is not read. A paragraph with
an unclosed backtick span cannot be read: it is one finding on its first line.

A heading of any level whose text starts with that word (`## Cost`, `### Cost per call`) opens a cost section. Its body
up to the next heading is cost text: each paragraph in it is read as a Cost paragraph, whatever its first word. The
heading line itself is not read.

Each sentence of a paragraph is read alone. A sentence ends at ". ", "! " or "? " outside backticks, or at the
paragraph end. `e.g.` and `i.e.` end none. A run of backticks opens a code span and the next run of the same
length closes it. Closing marks `)`, `*`, `"` and `'` after the stop belong to the sentence it ends.

A file token is a backticked name that ends in a known file extension (EXTENSIONS, any case), or starts with `~/` or
`.git/`. A trailing `:<digits>` (a line number) is dropped before the test, and the token is reported as written. A
token whose name is a test file (`test_*`, `*_test.*`, `*.test.*`, `*Tests.swift`, and `*.spec.*` ending in js, jsx, ts, tsx, mjs, cjs, mts or cts) is a pin candidate, not a file token. A token is
flagged whether or not its file exists. It is pinned when a candidate in the same sentence exists under the root and
holds the token's name as a whole name: its basename, or the folder before a `<placeholder>` basename, with no letter,
digit, `_`, `-` or `.`-and-name character beside it. A sentence that says "not pinned", "unpinned", "unmeasured" or
"no test" pins nothing and flags nothing: the writer has said so.

A count claim is a count word (zero to six, ten, single, or digits) with at most three words between it and a cost
noun (read, call, process, spawn, `ps`, write, file, run, start, times, line, command, request, lookup, query; plural
too). Once, twice, thrice and Nx ("2x") count only after a verb of work (read, run, call, start, spawn, write, fetch,
stat, check, open, scan, load, parse) with at most three words between, never before a noun. Code spans, dates
(YYYY-MM-DD), times (HH:MM), versions (x.y.z), decimals, a number with a time unit (s, ms, sec, second, min, minute,
hour) or a size unit (B, KB, MB, GB), line references (`name.ext:123`), "Round N of M", "PR N" and ids (`ruling`,
`item`, `rule`, `step` or `decision` and a number; `#` and a number) are not read as part of a claim, and "one" before
"of" is no count. A claim passes when its sentence holds a bound (at most, up to, no more than, never more than, capped
at, max, fewer, at least), says
"not pinned", "unpinned", "unmeasured" or "no test", or holds a test-name candidate that exists under the root and
holds, as a whole name, the code span nearest the count word. A test-name span is never the nearest span. A sentence
with no other code span passes on no test: it needs a bound or a mark. A sentence with a claim that passes none of
these is one finding, on the line of its count word: `<record>:<line>: count in a Cost sentence with no reader`.

A debt note is one list item of the debt notes file (kind `debt-notes` in lint/layout.json), with its continuation
lines. A note is read sentence by sentence, with the same sentence split and code-span blanking as a Cost paragraph.
A run of backticks that nothing closes is plain text in a note, so it makes no finding and the read goes on after it.
A note's count claim is `among` and a count word (one to six, or digits), or digits, `of`, and a number of two or more
digits (`406 of 8000`). A number may carry thousands separators (`1,406 of 8,000`). The first number of an `N of M`
claim is not read after the word `Round` or `Try`, or in a decimal (`20.2 of 28`). Dates, times and ids are
blanked first, as in a Cost sentence, so `item 3 of 40` and `step 2 of 12` make no claim. Words match in any case.
A claim passes on the Cost rule's passes: a bound, an exempt word, or a test-name candidate that holds the nearest code
span. It also passes when its sentence holds a date (YYYY-MM-DD), or `run` and digits that `of` does not follow
(`run 40 of 543` is a count). A count in a note is a dated past observation, not a standing fact. A sentence with a claim that passes none of these is one finding, on the line of its
claim: `<notes path>:<line>: count in a debt note with no reader`. A note's cost-noun counts are not read. A Cost
sentence in a decision record keeps the Cost rule alone.

The report is one line per token and line: `<record>:<line>: <token> named in a Cost sentence with no pin`.
Exit 1 when there is a finding, 0 when there is none. The decision records (kind `decisions` in lint/layout.json) and
the debt notes file are read. A debt record's Cost line is not read. Each test file is read once per run.
Cost: per run, one read of the notes file and one read of each test file a Cost sentence or a note names, cached.
The number of test files read is not pinned. lint/layout.py reads lint/layout.json and its extras file again on each
record-kind lookup, with no cache, and reads git files to name the repo. Those layout reads are not pinned.
"""
import argparse
import collections
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COST_START = re.compile(r"^\s*(?:(?:[-*]|\d+[.)])\s+)?(?:\*\*)?Cost(?![A-Za-z])")
COST_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?:\*\*)?Cost(?![A-Za-z])")
LIST_ITEM = re.compile(r"^(\s*)(?:[-*]|\d+[.)])\s")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+\S")
FENCE = re.compile(r"^\s*(?:```|~~~)")
EXEMPT = re.compile(r"\b(?:not pinned|unpinned|unmeasured|no test)", re.IGNORECASE)
PLACEHOLDER = re.compile(r"<[^<>]*>")
# A bare `tool.call` or `e.g.` has a dot and no file, so only these extensions mark a file.
EXTENSIONS = ("md py mjs js ts tsx json jsonl sh ps1 cmd bat html css yml yaml toml txt log csv tmpl sql cfg ini "
              "lock xml swift jsx cjs mts cts").split()
EXTENSION = re.compile(r"^.+\.(?:%s)$" % "|".join(EXTENSIONS), re.IGNORECASE)
LINE_SUFFIX = re.compile(r"(?::\d+)+$")
TEST_NAME = re.compile(r"^(?:test_.*|.*_test\..*|.*\.test\..*|.*Tests\.swift|.*\.spec\.(?:js|jsx|ts|tsx|mjs|cjs|mts|cts))$")
CLOSERS = ")*\"'"
UNBALANCED = "unbalanced backtick in a Cost paragraph"
NO_READER = "count in a Cost sentence with no reader"
NOTE_NO_READER = "count in a debt note with no reader"
WORD = re.compile(r"\w+(?:['\u2019-]\w+)*")
COUNT_WORD = re.compile(r"(?:zero|one|two|three|four|five|six|ten|single|once|twice|thrice|\d+x?)", re.IGNORECASE)
WORK_VERB = re.compile(r"(?:reads?|runs?|calls?|called|starts?|spawns?|writes?|fetch(?:es)?|stats?|checks?|opens?|scans?|loads?|parses?)", re.IGNORECASE)
TIMES_WORD = re.compile(r"(?:once|twice|thrice|\d+x)", re.IGNORECASE)
COST_NOUN = re.compile(r"(?:reads?|calls?|process(?:es)?|spawns?|ps|writes?|files?|runs?|starts?|times|lines?|commands?"
                       r"|requests?|lookups?|quer(?:y|ies))", re.IGNORECASE)
BOUND = re.compile(r"\b(?:at\s+most|up\s+to|no\s+more\s+than|never\s+more\s+than|capped\s+at|max|fewer|at\s+least)\b", re.IGNORECASE)
# A number beside a cost noun that counts nothing: a line reference (`name.ext:123`), a date, a time, an id.
NOT_COUNTS = [re.compile(r"[\w/.-]+\.[A-Za-z]+(?::\d+)+"), re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
              re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"), re.compile(r"\b\d+\.\d+\.\d+\b"), re.compile(r"\b\d+\.\d+\b"),
              re.compile(r"\b\d+\s*(?:ms|sec|seconds?|min|minutes?|hours?|s)\b", re.IGNORECASE),
              re.compile(r"\b\d+\s*[KMG]?B\b"),
              re.compile(r"\bRound\s+\d+\s+of\s+\d+\b", re.IGNORECASE), re.compile(r"\bPR\s+#?\d+\b"),
              re.compile(r"\b(?:ruling|item|rule|step|decision)\s+\d+\b", re.IGNORECASE), re.compile(r"#\d+\b")]
# A number, with thousands separators (`1,406`) or without.
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)"
# A debt note's count claim: `among` and a count word, or `N of M` with M of two or more digits. The lookbehind drops
# a number after Try. NOT_COUNTS blanks `Round N of M` and a decimal (`20.2 of 28`) before this reads the text.
NOTE_CLAIM = re.compile(r"\bamong\s+(?:" + NUMBER + r"|one|two|three|four|five|six)\b"
                        r"|(?<!\btry )\b" + NUMBER + r"\s+of\s+(?:\d{1,3}(?:,\d{3})+|\d{2,})(?!\d)",
                        re.IGNORECASE)
# A date, or `run` and digits that `of` does not follow: `run 40 of 543` is a count, not a run id.
NOTE_DATED = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\brun\s+\d+\b(?!\s+of\b)", re.IGNORECASE)
# text, [(code span text, line)], line of the first character, text with code spans blanked, [(start, end)] of each span
Sentence = collections.namedtuple("Sentence", "text spans line blanked holes")


def indent_of(text):
    return len(text) - len(text.lstrip(" \t"))


def paragraphs(lines):
    """Each Cost paragraph of `lines` as a list of (line number, text)."""
    found, current, fenced, base, section = [], None, False, 0, False
    for number, text in enumerate(lines, 1):
        if FENCE.match(text):
            fenced = not fenced
            current = None
            continue
        if fenced:
            continue
        if HEADING.match(text):
            # each heading ends the section before it; only a Cost heading opens a new one
            section, current = bool(COST_HEADING.match(text)), None
            continue
        if not text.strip():
            current = None
            continue
        outdented = bool(LIST_ITEM.match(text)) and indent_of(text) <= base
        if COST_START.match(text) or (section and (current is None or outdented)):
            current, base = [(number, text)], indent_of(text)
            found.append(current)
        elif current is not None and not outdented:
            current.append((number, text))
        else:
            current = mid_line_start(number, text)
            if current:
                base = indent_of(text)
                found.append(current)
    return found


def unpadded(code):
    """A code span's text with one space off each end when both ends hold one and the span is not all spaces."""
    if len(code) >= 2 and code[0] == code[-1] == " " and code.strip():
        return code[1:-1]
    return code


def abbreviation(text):
    """True when the characters so far end in `e.g.` or `i.e.`, which end no sentence."""
    tail = "".join(text[-5:]).lower()
    return tail[-4:] in ("e.g.", "i.e.") and (len(tail) < 5 or not tail[0].isalnum())


def mid_line_start(number, text):
    """[(number, text from the sentence)] for the first sentence after the first, in one line, that starts like a
    Cost line, else None. The sentence split is read_paragraph's, so a stop inside a code span or after `e.g.` ends
    nothing."""
    sentences, _ = read_paragraph([(number, text)])
    offset = 0
    for k, sentence in enumerate(sentences):
        if k and COST_START.match(sentence.text):
            return [(number, text[offset:].lstrip())]
        offset += len(sentence.text)
    return None


def sentence_of(text, spans, line, holes):
    blanked = list(text)
    for start, end in holes:
        blanked[start:end] = "_" * (end - start)
    return Sentence("".join(text), spans, line, "".join(blanked), holes)


def read_paragraph(paragraph, lone_is_text=False):
    """(sentences, balanced) of one paragraph, from one pass over its backticks.

    A sentence is a `Sentence`: spans is [(code span text, line number)]. A backtick holds the sentence open,
    so a stop inside a code span ends nothing, and each span lies wholly inside one sentence. With `lone_is_text`,
    a run of backticks that nothing closes is plain text: the read goes back to just after it, and the paragraph
    is balanced."""
    chars = [(number, c) for number, text in paragraph for c in text + "\n"]
    sentences, text, spans, holes, inside, opened, width, i = [], [], [], [], False, 0, 0, 0
    begin, hole = 0, 0
    while True:
        if i == len(chars):
            if not (inside and lone_is_text):
                break
            # while a span is open no sentence ends and no span closes, so only the text after the run is undone
            del text[hole + width:]
            inside, i = False, opened
            continue
        if not text:
            begin = chars[i][0]
        c = chars[i][1]
        if c == "`":
            # a run of backticks opens a span, and the next run of the same length closes it
            n = 1
            while i + n < len(chars) and chars[i + n][1] == "`":
                n += 1
            if not inside:
                hole = len(text)
            text.extend("`" * n)
            if inside and n == width:
                spans.append((unpadded("".join(ch for _, ch in chars[opened:i])), chars[opened][0]))
                holes.append((hole, len(text)))
                inside = False
            elif not inside:
                inside, opened, width = True, i + n, n
            i += n
            continue
        text.append(c)
        if c in ".!?" and not inside and not abbreviation(text):
            j = i + 1
            while j < len(chars) and chars[j][1] in CLOSERS:
                j += 1
            if j == len(chars) or chars[j][1].isspace():
                text.extend(ch for _, ch in chars[i + 1:j])
                sentences.append(sentence_of(text, spans, begin, holes))
                text, spans, holes, i = [], [], [], j - 1
        i += 1
    if "".join(text).strip():
        sentences.append(sentence_of(text, spans, begin, holes))
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
    if not parts:
        return None
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


def held(candidate, root, texts):
    """The text of a test file under the root, read once per run, or None when it is absent."""
    rel = bare(candidate)
    if rel not in texts:
        texts[rel] = read(os.path.join(root, *rel.split("/")))
    return texts[rel]


def pinned(token, candidates, root, texts):
    name = pin_name(token)
    if not name:
        return False
    # The name stands alone: no name character before it, and none after it but a stop that ends the word.
    whole = re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(name) + r"(?![A-Za-z0-9_-]|\.[A-Za-z0-9_-])")
    for candidate in candidates:
        text = held(candidate, root, texts)
        if text is not None and whole.search(text):
            return True
    return False


def trailing(words):
    """True when a verb of work stands among `words`, the words before once, twice or thrice ("it reads the list
    once"). A plain noun before the count is no claim ("a mutating command or `sed` once redirects")."""
    return any(WORK_VERB.fullmatch(word.group()) for word in words)


def counts(sentence):
    """(start, end) in the sentence text of each count word that makes a claim. A span, a date, a time and an id
    are blanked first, so none counts as a word of the claim; a span stays one word between count and noun."""
    blanked = blank_not_counts(sentence.blanked)
    words = list(WORD.finditer(blanked))
    found = []
    for i, word in enumerate(words):
        if not COUNT_WORD.fullmatch(word.group()):
            continue
        # once, twice and thrice count only after a verb of work ("reads it once"); "one of" is a pronoun
        leading = not TIMES_WORD.fullmatch(word.group()) and not (
            word.group().lower() == "one" and words[i + 1:i + 2] and words[i + 1].group().lower() == "of")
        after = leading and any(COST_NOUN.fullmatch(w.group()) for w in words[i + 1:i + 5])
        before = TIMES_WORD.fullmatch(word.group()) and trailing(words[max(0, i - 4):i])
        if after or before:
            found.append((word.start(), word.end()))
    return found


def has_reader(sentence, start, end, candidates, root, texts):
    """True when a bound, or a test that holds the code span nearest the count word, backs the count."""
    if BOUND.search(sentence.blanked):
        return True
    near = [(min(abs(a - end), abs(start - b)), k) for k, (a, b) in enumerate(sentence.holes)
            if not is_test_name(sentence.spans[k][0])]
    if not near:
        return False
    return pinned(sentence.spans[min(near)[1]][0], candidates, root, texts)


def blank_not_counts(text):
    """`text` with each date, time and id overwritten by underscores of the same length, so no offset moves."""
    for pattern in NOT_COUNTS:
        text = pattern.sub(lambda m: "_" * len(m.group()), text)
    return text


def note_paragraphs(lines):
    """Each debt note of `lines`, as a list of (line number, text) pairs. A note is a list item and its continuation
    lines. A blank line, a heading or a code fence ends it. Fenced code is not read."""

    found, current, fenced = [], None, False
    for number, text in enumerate(lines, 1):
        if FENCE.match(text):
            fenced, current = not fenced, None
        elif fenced or HEADING.match(text) or not text.strip():
            current = None

        elif LIST_ITEM.match(text):
            current = [(number, text)]
            found.append(current)
        elif current is not None:
            current.append((number, text))
    return found


def note_claim(sentence, candidates, root, texts):
    """The offset in the sentence text of its first note count claim that has no reader, else None.
    A bound, an exempt word, a date or run id in the sentence passes it. So does a test that holds the nearest span.
    """
    if EXEMPT.search(sentence.text) or NOTE_DATED.search(sentence.blanked):
        return None
    for m in NOTE_CLAIM.finditer(blank_not_counts(sentence.blanked)):
        if not has_reader(sentence, m.start(), m.end(), candidates, root, texts):
            return m.start()
    return None


def check_notes(root, texts):
    """The findings of the debt notes file under `root`, as `check` makes them. A file that is absent has none."""
    homes = layout.candidates(root, "debt-notes")
    home = next((h for h in homes if os.path.isfile(os.path.join(root, *h.split("/")))), None)
    text = read(os.path.join(root, *home.split("/"))) if home else None
    findings = []
    for paragraph in note_paragraphs((text or "").splitlines()):
        sentences, _ = read_paragraph(paragraph, lone_is_text=True)
        for sentence in sentences:
            candidates = [t for t, _ in sentence.spans if is_test_name(t) and EXTENSION.search(basename(bare(t)))]
            start = note_claim(sentence, candidates, root, texts)
            if start is not None:
                findings.append((home, sentence.line + sentence.text.count("\n", 0, start), None, NOTE_NO_READER))
    return findings


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
            for sentence in sentences:
                if EXEMPT.search(sentence.text):
                    continue
                candidates = [t for t, _ in sentence.spans if is_test_name(t) and EXTENSION.search(basename(bare(t)))]
                for token, number in sentence.spans:
                    row = (record, number, token, "%s named in a Cost sentence with no pin" % token)
                    if is_file(token) and row not in findings and not pinned(token, candidates, root, texts):
                        findings.append(row)
                for start, end in counts(sentence):
                    if not has_reader(sentence, start, end, candidates, root, texts):
                        line = sentence.line + sentence.text.count("\n", 0, start)
                        findings.append((record, line, None, NO_READER))
                        break
    return findings + check_notes(root, texts)


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
