#!/usr/bin/env python3
"""Fails when a change adds a comment or docstring line that narrates history or review.

    python3 lint/check_comment_narration.py --base origin/main [--exclude PREFIX ...]

Rule: building-comments-say-why. A comment says what complex code does and why.
Only lines the diff against the merge base adds can fail, so old lines never do.
--exclude PREFIX (repeatable) drops each path that starts with PREFIX, a folder prefix such as `vendor/`.
Languages come from the rows of actions/code-check/standard.json (extensions, and shebangs for a file with no
extension): python, typescript, javascript, astro, swift and shell. Python comments come from `tokenize`, docstrings
from `ast`. JS, TS and Astro comments come from one lint/comment_scan.mjs process that parses with the pinned
TypeScript. Swift and shell comments come from one-pass scanners in this file. The same words in any string, and in
a shell heredoc body, never fail.

Exit 0 clean. Exit 1 on a hit, printed as `path:line: pattern: matched text`.
Exit 2 when the base or a file cannot be read: an unread diff is never a clean one. An unread file does not stop
the scan: every other file is read, every hit prints, and the run then exits 2.
Exit 3 when the node tool for JS, TS and Astro cannot run (no npx, an npx error, comment_scan.mjs missing,
typescript not found). Every Python, Swift and shell hit prints first. Exit 3 wins over exit 2.
"""
import argparse
import ast
import bisect
import io
import itertools
import json
import os
import re
import sys
import tokenize
HERE = os.path.dirname(os.path.abspath(__file__))
PINNED_ROOT = os.path.normpath(os.path.join(HERE, ".."))  # the claude-settings copy that holds this check
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, HERE)
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import layout  # noqa: E402  the one home of where a repo keeps its decisions (lint/layout.py)

class DatedText:
    """A date pattern that skips a date a rule or a limit runs on: the word effective, valid, until or expires,
    an optional `date`, `on`, `from` or `through`, and an optional colon come right before it. Such a date says
    why, so it is not history. A phrase check on the text before the date does what a lookbehind cannot:
    take a variable run of spaces and any case. A ruling cite is exempt too: the word owner (any case) and a
    comma right before the date, and a time and a zone right after it. The owner word must open the comment's
    text (after its `#`, `///`, `//!`, `//`, `/*`, `*`, `<!--`, `\"\"\"` or `'''` marker and spaces) or follow a `(`. The time is
    an hour of 0 to 23 with one or two digits, a colon and two minute digits. The zone is one of ZONES, in any case.
    A cite without the time, with another lead word, or with another zone stays flagged. A cite in parentheses
    after history wording still passes, as in "Changed from None to 0 (owner, 2026-11-01 16:30 CST)"."""
    ZONES = ("CST", "CDT", "CT", "EST", "EDT", "ET", "MST", "MDT", "MT", "PST", "PDT", "PT", "UTC", "GMT")
    DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
    EXEMPT = re.compile(r"\b(?:effective|valid|until|expires?)(?:\s+(?:date|on|from|through))?(?:\s*:)?\s*$", re.I)
    # Each opener run matches one way only: `//+(?!/)!?` takes a whole slash run, and no space is left for a
    # second `\s*` to share. Overlapping alternatives here backtrack exponentially on a long slash run.
    CITE_BEFORE = re.compile(r"(?:^(?:\s|#|//+(?!/)!?|/\*|\*|<!--|\"\"\"|''')*|\(\s*)owner\s*,\s*$", re.I)
    CITE_AFTER = re.compile(r"\s+(?:2[0-3]|[01]?\d):[0-5]\d\s+(?:%s)\b" % "|".join(ZONES), re.I)

    def finditer(self, text):
        return (m for m in self.DATE.finditer(text) if not self.exempt(text, m))

    def exempt(self, text, m):
        if self.EXEMPT.search(text[:m.start()]):
            return True
        return bool(self.CITE_BEFORE.search(text[:m.start()]) and self.CITE_AFTER.match(text, m.end()))


class ReviewRound:
    """The pattern group for round numbers, kept as a class for its exemption. A round number after "in", "after" or
    "from" is narration, and a bare one is narration unless a numeric unit follows it, as in "2 decimals",
    which is arithmetic. The word "review" before "round", "finding" or "point" is narration too.
    A comment that quotes a rule glosses a decision id holding `round-N`, such as hold-unsafe-after-round-N.
    A round number with the same N passes only in a gloss, and only when the id names a decision file. That file is
    in a decisions folder that the layout gives for the checked repo, or in the one of the claude-settings copy that
    holds this check, so a pinning repo can cite a claude-settings decision. A folder that cannot be read holds nothing.
    The gloss is one of two forms. The parentheses open with the id and a comma, as in "(decision <id>, ...)",
    "(see decision <id>, ...)" or "(`<id>`, ...)". Or the parentheses come right after the id, as in
    "Decision <id> (...)". The "review" form passes inside either one.
    Anything else stays flagged: the same words outside the gloss, an id with no decision file, an id holding
    another number, a bare id with no marker, a colon after the id, a round number right before parentheses that
    hold the id, and parentheses that hold the id later on."""
    ROUND = re.compile(r"\b(?:in|after|from)\s+round\s*\d+"
                       r"|\bround\s*\d+(?!\d)(?!\s*(?:decimals?|places?|digits?)\b)"
                       r"|\breview\s+(?:round|finding|points?)\b", re.I)
    ID = r"(?P<id>[a-z0-9][a-z0-9-]*)"
    # The opening form needs a marker: "decision" with optional backticks, or backticks alone.
    OPENS = re.compile(r"\s*(?:(?:see\s+)?decision\s+(?P<q>`?)|`)" + ID + r"(?(q)(?P=q)|`)\s*,", re.I)
    BEFORE = re.compile(r"(?:\b(?:see\s+)?decision\s+(?P<q>`?)|(?<![\w`-])`)" + ID + r"(?(q)(?P=q)|`)\s*$", re.I)
    NUMBER_AFTER = re.compile(r"\s*(\d+)")

    def __init__(self):
        self.top, self.known = None, {}

    def real(self, ident, n):
        """True when ident holds `round-n` and names a decision file in the repo being checked or in claude-settings."""
        if not re.search(r"(?:^|-)round-%s(?:-|$)" % n, ident, re.I):
            return False
        if ident not in self.known:
            if self.top is None:
                try:
                    self.top = git("rev-parse", "--show-toplevel").strip()
                except Unread:
                    self.top = ""
            self.known[ident] = any(root and self.has_decision(root, ident) for root in (self.top, PINNED_ROOT))
        return self.known[ident]

    @staticmethod
    def has_decision(root, ident):
        """True when any decisions folder the layout allows for the repo at root holds ident.md. A layout
        that does not read says nothing is real, so the round stays flagged."""
        try:
            return any(os.path.isfile(os.path.join(root, *folder.split("/"), ident + ".md"))
                       for folder in layout.candidates(root, "decisions"))
        except (layout.LayoutError, KeyError, OSError):
            return False

    def number(self, text, m):
        """The round number a match names: its own digits, or the digits after the "review" form. None for the rest."""
        found = re.search(r"round\s*(\d+)", m.group(0), re.I)
        if not found and re.fullmatch(r"review\s+round", m.group(0), re.I):
            found = self.NUMBER_AFTER.match(text, m.end())
        return found.group(1) if found else None

    @staticmethod
    def paren_spans(text):
        spans, stack = [], []
        for k, c in enumerate(text):
            if c == "(":
                stack.append(k)
            elif c == ")" and stack:
                spans.append((stack.pop(), k))
        return spans

    def gloss_ids(self, text, lo):
        """The ids the parentheses at lo gloss: the one they open with, and the one right before them."""
        for m in (self.OPENS.match(text, lo + 1), self.BEFORE.search(text[:lo])):
            if m:
                yield m.group("id")

    def finditer(self, text):
        spans = self.paren_spans(text)
        for m in self.ROUND.finditer(text):
            n = self.number(text, m)
            if n and any(lo < m.start() < hi and self.real(ident, n)
                         for lo, hi in spans for ident in self.gloss_ids(text, lo)):
                continue
            yield m


class HistoryPhrase:
    """The `history phrase` group: wording that tells how the code used to be, or how a run came out.
    FORMS hold the wording that is history anywhere. RUN holds a run's colour or result named on the head, on
    main or on the base, or red or green before a change: history whatever word comes before it ("is", "are",
    a label). RUN is logic, and so skipped, when `when`, `if`, `unless`, `until`, `while` or `once` stands
    earlier in the same clause, since the phrase then names a condition. A check on the clause before the
    match does what a lookbehind cannot: take a variable run of words."""
    # Each form names the words around it, so a mid-sentence "previously" and "the user changed the value" stay
    # clean. The "previously" form needs the start of a sentence, since only there it opens a history clause.
    # A "changed from" form whose noun is a snapshot or run is change detection, not history: the noun after
    # the adjective decides, so the same form with any other noun still flags.
    # "the old behaviour expected by ..." is a participle naming who relies on it, not a past-tense verb.
    FORMS = re.compile(
        r"(?:^[\s#/*\"']*|[.;:]\s+)previously\b,?\s+(?:this|it|they|we|was|were|returned|used|did|had)\b"
        r"|\bchanged\s+from\s+(?:the\s+(?:old|previous|original|former)\b(?!\s+(?:snapshot|run)\b)|an?\s+\w+\s+to\b|\w+ing\s+\w+\s+to\b)"
        r"|\badded\s+after\s+(?:code\s+)?review\b"
        r"|\bformerly\b"
        r"|\bthe\s+old\s+behaviou?r\s+(?:(?!\w+ed\s+(?:by|for|on|in|at|with|from)\b)\w+ed|was|were|had|did|used|let|ran|took|gave|made|kept)\b", re.I)
    # A pass or fail verb also names code: "fails on the main thread", "pass on the base class", "passes on the
    # head of the list", "fails on main()", "fails on HEAD~1". So after head, main or base a pass or fail verb
    # refuses `(`, a git ref suffix, "of" and a code noun. "was passed before the loop" is code too, so the
    # bare before-form takes a colour or an -ing result only.
    COLOUR = r"(?:red|green)"
    VERB = r"(?:pass(?:es|ed|ing)?|fail(?:s|ed|ing)?)"
    PLACE = r"\s+(?:on|at)\s+(?:the\s+)?(?:origin/)?(?:head|main|base)\b(?![/-]|\.\w)"
    CODE_AFTER = r"(?![(~^]|\s+(?:of|thread|queue|class|node)s?\b)"
    RUN = re.compile(
        r"\b" + COLOUR + PLACE
        + r"|\b" + VERB + PLACE + CODE_AFTER
        + r"|\b(?:was|were|went|been|turned|stayed)\s+(?:red|green|passing|failing)\s+before\b"
        r"|\b(?:" + COLOUR + "|" + VERB + r")\s+before\s+(?:this|the)\s+(?:change|fix)\b", re.I)
    CONDITION = re.compile(r"\b(?:when|if|unless|until|while|once)\b", re.I)

    def finditer(self, text):
        run = (m for m in self.RUN.finditer(text)
               if not self.CONDITION.search(re.split(r"[.;:!?,]", text[:m.start()])[-1]))
        return itertools.chain(self.FORMS.finditer(text), run)


PATTERNS = {
    # A round number is narration, except as a unit ("2 decimals") or inside a decision id's gloss (ReviewRound).
    "review round": ReviewRound(),
    "pr number": re.compile(r"\bPR\s*#?\s*\d{3,}"),
    "commit hash": re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b"),
    "status word": re.compile(r"\b(?:MEASURED|CORRECTED)\b|\bADDED\s+\d"),
    "date": DatedText(),
    "history phrase": HistoryPhrase(),
    "owner order": re.compile(r"\bowner(?:'s)?\s+(?:ruling|order|request|ask)\b", re.I),
}
REMEDY = "say what and why; the history goes in git or the decision"
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")
STANDARD = os.path.join(HERE, "..", "actions", "code-check", "standard.json")
SCAN_SCRIPT = os.path.join(HERE, "comment_scan.mjs")
NODE_LANGUAGES = ("typescript", "javascript", "astro")
SCANNED = ("python", "swift", "shell") + NODE_LANGUAGES


class Unread(Exception):
    pass


class NodeToolFailed(Exception):
    """The node tool could not run at all, as opposed to one file it could not read."""


def git(*args):
    r = _nowindow.run(["git", "-c", "core.quotepath=off", *args], capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise Unread("git %s failed: %s" % (" ".join(args[:2]), r.stderr.strip() or r.returncode))
    return r.stdout


def load_standard():
    try:
        with open(STANDARD, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Unread("%s: cannot read: %s" % (os.path.normpath(STANDARD), e))


def shebang_word(path):
    """The interpreter a file's shebang names, version digits dropped, or None (the rule of code_check.interpreter)."""
    try:
        with open(path, "rb") as f:
            first = f.readline(200).decode("utf-8", "replace").strip()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    words = [w for w in first[2:].split() if not w.startswith("-") and os.path.basename(w) != "env"]
    return re.sub(r"[\d.]+$", "", os.path.basename(words[0])) if words else None


def language_of(path, std):
    """The language row name for a path, or None when it is not a scanned language."""
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower() or (base.lower() if base.startswith(".") else "")
    rows = std["languages"]
    if ext:
        return next((n for n in SCANNED if ext in rows.get(n, {}).get("extensions", [])), None)
    word = shebang_word(path)
    return next((n for n in SCANNED if word and word in rows.get(n, {}).get("shebangs", [])), None)


def added_lines(base, std):
    """Map each changed path in a scanned language to (language, the set of line numbers the diff adds)."""
    git("rev-parse", "--verify", "--quiet", base + "^{commit}")
    fork = git("merge-base", base, "HEAD").strip()
    diff = git("diff", "-U0", "-M", "--no-color", "--no-ext-diff", fork)
    added, path = {}, None
    for row in diff.split("\n"):
        if row.startswith("+++ "):
            path = None if row == "+++ /dev/null" else row[6:].split("\t")[0]
            lang = language_of(path, std) if path else None
            if lang is None:
                path = None
            else:
                added.setdefault(path, (lang, set()))
        elif path and (m := HUNK.match(row)):
            start, count = int(m.group(1)), int(m.group(2) or 1)
            added[path][1].update(range(start, start + count))
    return added


def narrated_lines(path):
    """Yield (line, text) for each comment token and each docstring line of a file."""
    try:
        with open(path, "rb") as f:
            data = f.read()
        tree = ast.parse(data)
        tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
    except (OSError, SyntaxError, ValueError, tokenize.TokenError) as e:
        raise Unread("%s: cannot read: %s" % (path, e))
    for tok in tokens:
        if tok.type == tokenize.COMMENT:
            yield tok.start[0], tok.string
    rows = re.split(r"\r\n|\r|\n", data.decode("utf-8", "replace"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            doc = body[0]
            if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant) and isinstance(doc.value.value, str):
                for n in range(doc.lineno, doc.end_lineno + 1):
                    yield n, rows[n - 1]


def swift_block_end(src, i):
    """Index after the nested block comment that opens at i; the end of the file when it never closes."""
    depth, j = 0, i
    while j < len(src):
        if src.startswith("/*", j):
            depth += 1
            j += 2
        elif src.startswith("*/", j):
            depth -= 1
            j += 2
            if depth == 0:
                return j
        else:
            j += 1
    return j


def swift_string_end(src, i, hashes, triple, spans):
    """Index after the string whose body starts at i. An interpolation inside it is code, so it may hold comments and
    strings of its own; swift_code_end adds those comments to spans. A raw string takes `#` marks on its escapes."""
    close = ('"' * (3 if triple else 1)) + "#" * hashes
    escape = "\\" + "#" * hashes
    while i < len(src):
        if src.startswith(close, i):
            return i + len(close)
        if src.startswith(escape, i):
            i += len(escape)
            if src.startswith("(", i):
                i = swift_code_end(src, i + 1, spans, True)
            else:
                i += 1
        elif src[i] == "\n" and not triple:
            return i + 1
        else:
            i += 1
    return i


def swift_code_end(src, i, spans, in_interpolation=False):
    """Scan code from i, adding each comment as (start, end) to spans. In an interpolation, stop after its `)`."""
    depth = 0
    while i < len(src):
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = len(src) if end < 0 else end
            spans.append((i, end))
            i = end
        elif src.startswith("/*", i):
            end = swift_block_end(src, i)
            spans.append((i, end))
            i = end
        elif src[i] in '"#':
            k = i
            while k < len(src) and src[k] == "#":
                k += 1
            if k < len(src) and src[k] == '"':
                triple = src.startswith('"""', k)
                i = swift_string_end(src, k + (3 if triple else 1), k - i, triple, spans)
            else:
                i = k + 1  # a `#if` or `#warning` directive, not a raw string
        elif src[i] == "(":
            depth += 1
            i += 1
        elif src[i] == ")":
            if in_interpolation and depth == 0:
                return i + 1
            depth -= 1
            i += 1
        else:
            i += 1
    return i


def swift_comments(path):
    """Yield (line, text) for each line of each comment in a Swift file."""
    try:
        with open(path, "rb") as f:
            src = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Unread("%s: cannot read: %s" % (path, e))
    src = re.sub(r"\r\n|\r", "\n", src)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    spans = []
    swift_code_end(src, 0, spans)
    for start, end in spans:
        line = bisect.bisect_right(starts, start)
        for k, text in enumerate(src[start:end].split("\n")):
            yield line + k, text


SH_WORD_END = " \t\n;&|()<>"


def sh_quote_end(src, i):
    """Index after the single-quoted string whose body starts at i."""
    j = src.find("'", i)
    if j < 0:
        raise Unread("single quote never closes")
    return j + 1


def sh_ansi_end(src, i):
    """Index after the $'...' string whose body starts at i; a backslash escapes a quote there."""
    while i < len(src):
        if src[i] == "\\":
            i += 2
        elif src[i] == "'":
            return i + 1
        else:
            i += 1
    raise Unread("$' string never closes")


def sh_dollar_end(src, i, spans, pending, in_dq=False):
    """Index after the expansion that starts at the `$` at i. Inside a double quote, `$'` and `$"` are a plain `$`."""
    nxt = src[i + 1:i + 2]
    if nxt == "{":
        return sh_param_end(src, i + 2, spans, pending, in_dq)
    if src.startswith("$((", i):
        j = sh_try_arith(src, i + 3, spans, pending)
        if j is not None:
            return j
    if nxt == "(":
        return sh_code_end(src, i + 2, spans, pending, ")")
    if nxt == "'" and not in_dq:
        return sh_ansi_end(src, i + 2)
    if nxt == '"' and not in_dq:
        return sh_dquote_end(src, i + 2, spans, pending)
    return i + 2 if nxt and nxt in "#?!$@*-" else i + 1


def sh_param_end(src, i, spans, pending, in_dq):
    """Index after the ${...} whose body starts at i. A `#` inside is an operator, never a comment. In a double
    quote a single quote is a plain character, as it is in bash."""
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
        elif c == "}":
            return i + 1
        elif c == "'" and not in_dq:
            i = sh_quote_end(src, i + 1)
        elif c == '"':
            i = sh_dquote_end(src, i + 1, spans, pending)
        elif c == "`":
            i = sh_code_end(src, i + 1, spans, pending, "`")
        elif c == "$":
            i = sh_dollar_end(src, i, spans, pending, in_dq)
        else:
            i += 1
    raise Unread("${ never closes")


def sh_dquote_end(src, i, spans, pending):
    """Index after the double-quoted string whose body starts at i. $(...) and backticks inside hold code."""
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
        elif c == '"':
            return i + 1
        elif c == "$":
            i = sh_dollar_end(src, i, spans, pending, True)
        elif c == "`":
            i = sh_code_end(src, i + 1, spans, pending, "`")
        else:
            i += 1
    raise Unread("double quote never closes")


def sh_arith_end(src, i, spans, pending):
    """Index after the $(( or (( expression whose body starts at i. A `#` there is a base prefix, and `<<` a shift."""
    depth = 0
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
        elif c == "'":
            i = sh_quote_end(src, i + 1)
        elif c == '"':
            i = sh_dquote_end(src, i + 1, spans, pending)
        elif c == "$":
            i = sh_dollar_end(src, i, spans, pending)
        elif c == "(":
            depth += 1
            i += 1
        elif c == ")":
            if depth:
                depth -= 1
                i += 1
            elif src.startswith("))", i):
                return i + 2
            else:
                raise Unread("arithmetic expression ends with a lone )")
        else:
            i += 1
    raise Unread("arithmetic expression never closes")


def sh_try_arith(src, i, spans, pending):
    """Index after the arithmetic expression whose body starts at i, or None when it is not one. Like bash, a `((`
    or `$((` that does not close with `))` is a subshell or a command substitution that holds a subshell, as in
    `((cd /tmp; ls) | wc -l)`; the caller then reads it as code."""
    kept, saved = len(spans), list(pending)
    try:
        return sh_arith_end(src, i, spans, pending)
    except Unread:
        del spans[kept:]
        pending[:] = saved
        return None


def sh_comment_end(src, i, in_backticks):
    """Index of the end of the comment that opens at i: the line end, or inside backticks the first unescaped
    backtick, since the shell cuts the command at that backtick before it parses it."""
    n = len(src)
    while i < n and src[i] != "\n":
        if in_backticks and src[i] == "`":
            return i
        i += 2 if in_backticks and src[i] == "\\" and i + 1 < n and src[i + 1] != "\n" else 1
    return i


def sh_heredoc_word(src, i):
    """Read the delimiter after `<<` (i is just past it). Returns (index after the word, (delimiter, tab_strip)).
    The delimiter is the word with its quoting removed; a quoted word makes the body literal, which changes nothing
    here, since no heredoc body is read for comments."""
    strip = src.startswith("-", i)
    i += strip
    while i < len(src) and src[i] in " \t":
        i += 1
    word, start = [], i
    while i < len(src) and src[i] not in SH_WORD_END:
        c = src[i]
        if c in "'\"":
            j = src.find(c, i + 1)
            if j < 0:
                raise Unread("heredoc delimiter quote never closes")
            word.append(src[i + 1:j])
            i = j + 1
        elif c == "\\":
            word.append(src[i + 1:i + 2])
            i += 2
        else:
            word.append(c)
            i += 1
    if i == start:
        raise Unread("heredoc has no delimiter")
    return i, ("".join(word), strip)


def sh_heredoc_bodies(src, i, pending):
    """Index after the bodies of the pending heredocs, read in order from the line that starts at i. A body is
    data, so a `#` in it is never a comment."""
    for word, strip in pending:
        while True:
            if i >= len(src):
                raise Unread("heredoc %s never ends" % word)
            end = src.find("\n", i)
            end = len(src) if end < 0 else end
            line = src[i:end]
            i = min(end + 1, len(src))
            if (line.lstrip("\t") if strip else line) == word:
                break
    pending.clear()
    return i


SH_BOUNDARY = r"(?![^\s;&|()<>`])"
SH_CMD_WORD = re.compile(r"(?:case|esac|then|do|else|elif|if|while|until|time)" + SH_BOUNDARY + r"|[!{](?=\s)")
SH_FUNCTION = re.compile(r"function[ \t]+[^\s;&|()<>`]+")
SH_TEST_OPEN = re.compile(r"\[\[(?=\s)")
SH_TEST_CLOSE = re.compile(r"\]\]" + SH_BOUNDARY)
SH_BRACKET_EXPR = re.compile(r"\[[!^]?\]?(?:\[:\w+:\]|[^\]\s$`'\"\\])*\]")
SH_IN_WORD = re.compile(r"in" + SH_BOUNDARY)
SH_ESAC_WORD = re.compile(r"esac" + SH_BOUNDARY)


def sh_code_end(src, i, spans, pending, close=None):
    """Scan shell code from i, adding each comment as (start, end) to spans. With close `)` or a backtick, stop after
    the one that ends the command substitution. `ws` is True where a word may start, the only place a `#` opens a
    comment: a quote or an expansion ends a word that goes on, so `"a"#b` and `$(x)#b` hold no comment. `cmd` is
    True only at command position, the only place `case`, `esac` and the other reserved words count: after a newline,
    `;`, `&`, `|`, `$(`, a backtick, `{`, `then` or `do`, or a `(` that opens a subshell. `parens` holds one kind per
    open `(`: cmd for a subshell or a process substitution, list for an array, where a newline or `|` starts no
    command, and word for a paren that is part of a word, an extglob group (right after `?*+@!`), a regex group or a
    case pattern group, where `)#b` holds no comment. A bracket expression `[(]` inside `[[ ]]` or a case pattern is
    one word that pushes and pops no paren. Inside `[[ ... ]]` (`test`) nothing starts a command either.
    `<<` is a shift, not a heredoc, inside an array subscript `a[1<<2]` (`sub` counts the open `[`); `((` and `$((`
    are read by sh_try_arith. Each open `case` is one entry in `cases`, [state, paren depth where it opened]: word0
    and word1 before `in`, pat for the arm patterns, body for an arm's commands. A pattern's `)` ends the pattern,
    never the substitution."""
    ws, cmd, test, sub, parens, cases = True, True, False, 0, [], []

    def starts_cmd():
        return not test and (not parens or parens[-1] == "cmd")

    while i < len(src):
        c = src[i]
        st = cases[-1] if cases else None
        if st and st[0] == "word1" and ws and c not in " \t\n\\#":
            m = SH_IN_WORD.match(src, i)
            if not m:
                raise Unread("case word is not followed by in")
            st[0] = "pat"
            i, ws, cmd = m.end(), True, False
            continue
        if st and st[0] == "word0" and ws and c not in " \t\n\\#":
            st[0] = "word1"
        if st and st[0] == "pat" and ws and len(parens) == st[1]:
            if c == "(":
                i += 1  # a bare ( before a pattern
                continue
            if SH_ESAC_WORD.match(src, i):  # like POSIX, esac first in a pattern list ends the case
                cases.pop()
                i, ws, cmd = i + 4, False, False
                continue
        if test and ws and (m := SH_TEST_CLOSE.match(src, i)):
            test = False
            i, ws, cmd = m.end(), False, False
            continue
        if cmd and (not st or st[0] == "body") and (m := SH_TEST_OPEN.match(src, i)):
            test = True
            i, ws, cmd = m.end(), True, False
            continue
        if cmd and (not st or st[0] == "body") and (m := SH_FUNCTION.match(src, i)):
            i, ws = m.end(), False  # the name is read: `{` after it opens the body
            continue
        if cmd and (not st or st[0] == "body") and (m := SH_CMD_WORD.match(src, i)):
            word = m.group(0)
            if word == "case":
                cases.append(["word0", len(parens)])
                i, ws, cmd = m.end(), True, False
            elif word == "esac":
                if not st:
                    raise Unread("esac with no case")
                cases.pop()
                i, ws, cmd = m.end(), False, False
            else:
                i, ws = m.end(), False
            continue
        if st and st[0] == "body" and c == ";" and src[i + 1:i + 2] in (";", "&"):
            i += 3 if src.startswith(";;&", i) else 2
            st[0], ws, cmd = "pat", True, False
            continue
        if c == "\\":
            if src.startswith("\n", i + 1):
                i += 2  # a line break the shell removes: the next word starts where this one would have
            else:
                i += 2
                ws = cmd = False
        elif c == "'":
            i = sh_quote_end(src, i + 1)
            ws = cmd = False
        elif c == '"':
            i = sh_dquote_end(src, i + 1, spans, pending)
            ws = cmd = False
        elif c == "`":
            if close == "`":
                if cases:
                    raise Unread("case never ends with esac")
                return i + 1
            i = sh_code_end(src, i + 1, spans, pending, "`")
            ws = cmd = False
        elif c == "$":
            i = sh_dollar_end(src, i, spans, pending)
            ws = cmd = False
        elif c == "#" and ws:
            end = sh_comment_end(src, i, close == "`")
            spans.append((i, end))
            i = end
        elif c == "\n":
            i += 1
            if pending:
                i = sh_heredoc_bodies(src, i, pending)
            ws, sub, cmd = True, 0, starts_cmd()  # a line continuation is read by the backslash branch, so [[ ]] goes on
        elif src.startswith("<<<", i):
            i += 3  # a here-string, not a heredoc
            ws = True
        elif sub and src.startswith("<<", i):
            i += 2
            ws = True
        elif src.startswith("<<", i):
            i, entry = sh_heredoc_word(src, i + 2)
            pending.append(entry)
            ws = False
        elif ws and src.startswith("((", i) and (j := sh_try_arith(src, i + 2, spans, pending)) is not None:
            i = j
            ws = cmd = False
        elif c == "[" and (test or (st and st[0] == "pat" and len(parens) == st[1])) and (m := SH_BRACKET_EXPR.match(src, i)):
            i, ws, cmd = m.end(), False, False  # a bracket expression is one word: a ( or ) in it opens and closes nothing
        elif c == "[" and i and (src[i - 1].isalnum() or src[i - 1] in "_]"):
            sub += 1
            i += 1
            ws = cmd = False
        elif c == "]" and sub:
            sub -= 1
            i += 1
            ws = cmd = False
        elif c == "(":
            if test or (st and st[0] == "pat") or (i > 0 and src[i - 1] in "?*+@!"):
                kind = "word"
            elif cmd or (i > 0 and src[i - 1] in "<>"):
                kind = "cmd"
            else:
                kind = "list"
            parens.append(kind)
            ws, cmd = kind != "word", kind == "cmd"
            i += 1
        elif c == ")":
            i += 1
            base = st[1] if st else 0
            if st and st[0] == "pat" and len(parens) == base:
                st[0], ws, cmd = "body", True, True
            elif len(parens) > base:
                if parens.pop() == "word":
                    ws = cmd = False
                else:
                    ws, cmd = True, starts_cmd()  # starts_cmd keeps `f() {` a function body
            elif cases:
                raise Unread("case arm ends with a lone )")
            elif close == ")":
                return i
            else:
                ws = cmd = True  # a stray `)` at top level closes nothing
        else:
            redirect = c in "&|" and i > 0 and src[i - 1] in "<>"  # `>&2` and `>|` are redirections
            i += 1
            ws = c in " \t;&|<>"
            if c in ";&|" and not redirect:
                cmd = starts_cmd()
            elif c not in " \t":
                cmd = False
    if close:
        raise Unread("command substitution never closes")
    if cases:
        raise Unread("case never ends with esac")
    return i


def shell_comments(path):
    """Yield (line, text) for each comment in a shell file: sh and bash, the rows of standard.json. zsh is not read:
    no tracked file is zsh, and its quoting differs. No parser: shfmt is not installed in CI, so one pass reads the
    quoting a `#` can hide in. A comment inside $(...) or backticks counts; a heredoc body never does. An unclosed
    quote, expansion or heredoc raises Unread. The line `#!` on line 1 is not a comment."""
    try:
        with open(path, "rb") as f:
            src = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Unread("%s: cannot read: %s" % (path, e))
    src = re.sub(r"\r\n|\r", "\n", src)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    spans, pending = [], []
    try:
        first = src.find("\n") if src.startswith("#!") else 0
        sh_code_end(src, len(src) if first < 0 else first, spans, pending)
        if pending:
            raise Unread("heredoc %s never starts" % pending[0][0])
    except Unread as e:
        raise Unread("%s: cannot read: %s" % (path, e))
    for start, end in spans:
        yield bisect.bisect_right(starts, start), src[start:end]


def node_comments(paths, std):
    """Run comment_scan.mjs once over every JS, TS and Astro path, each named with its language row.
    Returns ({path: [(line, text)]}, [unread]); raises NodeToolFailed when the tool cannot run."""
    if not os.path.isfile(SCAN_SCRIPT):
        raise NodeToolFailed("%s is missing" % os.path.normpath(SCAN_SCRIPT))
    args = [SCAN_SCRIPT] + ["%s:%s" % (lang, p) for p, lang in paths]
    if os.environ.get("CODE_CHECK_TOOLS") == "path":
        cmd = ["node", *args]
    else:
        cmd = ["npx", "--yes", "-p", "typescript@" + std["tools"]["typescript"], "node", *args]
    try:
        r = _nowindow.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise NodeToolFailed("comment scan for JS, TS and Astro could not start: %s" % e)
    if r.returncode:
        reason = (r.stderr.strip().splitlines() or ["exit %d" % r.returncode])[-1]
        raise NodeToolFailed("comment scan for JS, TS and Astro failed: %s" % reason)
    found, unread = {}, []
    for row in r.stdout.splitlines():
        try:
            item = json.loads(row)
        except ValueError:
            raise NodeToolFailed("comment scan for JS, TS and Astro printed a row that is not JSON: %s" % row[:80])
        if "error" in item:
            unread.append("%s: cannot read: %s" % (item["path"], item["error"]))
        else:
            found.setdefault(item["path"], []).append((item["line"], item["text"]))
    return found, unread


READERS = {"python": narrated_lines, "swift": swift_comments, "shell": shell_comments}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="ref the change is measured against, such as origin/main")
    ap.add_argument("--exclude", action="append", default=[], metavar="PREFIX",
                    help="skip each path that starts with PREFIX (repeatable)")
    args = ap.parse_args(argv)
    try:
        std = load_standard()
        files = {p: v for p, v in added_lines(args.base, std).items() if not p.startswith(tuple(args.exclude))}
    except Unread as e:
        print("UNKNOWN: %s (base %s)" % (e, args.base), file=sys.stderr)
        return 2
    comments, unread = {}, []
    for path, (lang, _) in sorted(files.items()):
        if lang in READERS:
            try:
                comments[path] = list(READERS[lang](path))
            except Unread as e:
                unread.append(str(e))
    node_paths = [(p, lang) for p, (lang, _) in sorted(files.items()) if lang in NODE_LANGUAGES]
    node_failure = None
    if node_paths:
        try:
            found, bad = node_comments(node_paths, std)
            comments.update(found)
            unread += bad
        except NodeToolFailed as e:
            node_failure = str(e)
    hits = 0
    for path in sorted(comments):
        for n, text in sorted(set(comments[path])):
            if n in files[path][1]:
                for name, pat in PATTERNS.items():
                    for m in pat.finditer(text):
                        print("%s:%d: %s: %s (%s)" % (path, n, name, m.group(0), REMEDY))
                        hits += 1
    if unread:
        print("UNKNOWN: %s (base %s)" % ("; ".join(" ".join(u.split()) for u in unread), args.base), file=sys.stderr)
    if node_failure:
        print("COULD NOT RUN: %s (base %s)" % (" ".join(node_failure.split()), args.base), file=sys.stderr)
        return 3
    if unread:
        return 2
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
