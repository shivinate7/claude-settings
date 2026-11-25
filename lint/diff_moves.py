"""The one home of "a moved line is not an added line" for the checks that read a diff by line number.

A line counts as moved only when the SAME diff deletes that exact text: every character, indentation too,
from a file the calling check scans. A line deleted from a file the check never reads (a doc, a generated
file) excuses nothing, so the caller passes its own "is this file scanned" test in.
Each deleted copy excuses at most one added copy, so one deleted line never excuses two added ones. The caller
asks `take_move` for every added line, in a scanned file or not, so a copy in a file the check skips uses up
the deleted copy too. The diff must be a unified diff of the whole change, deletes included.

A move into an untracked file has no diff, so it is no move: the file is read whole and stays checked.

A reflow is a move too: a list line the diff only re-breaks, the same words now one per line. An added line is a
reflow when every token in it is a token of the lines that the same hunk deletes. A token is a run of characters
between whitespace, bars, commas, parentheses or backslashes, so `bundle|\\` and `bundle_old,` each hold one token.
A line with no token (a lone `)`) holds no word, so a hunk that deletes anything excuses it. The hunk is the unit:
the same file and the same `@@` block. A token deleted in another file or in another hunk excuses nothing, so a
reflow cannot hide a new word beside an old one. Each
deleted token excuses at most one added token. A caller opts in by passing `take_move` the number of the hunk it
is reading, counted from 1 over every `@@` row of the diff, in the order `deleted_texts` counts them; with no hunk
number a line is a move only when its whole text was deleted. A reflowed line does not use up an exact deleted
copy, and an exact copy does not use up tokens, so the two budgets are separate.

Readers of a diff that use this home: check_comment_narration.added_lines and check_glossary.patch_lines.
Cost: one pass over a diff text the caller already holds. No process, no file.
"""
import ast
import re
from collections import Counter

TOKEN_GAPS = re.compile(r"[\s|,()\\]+")  # what separates one token from the next, see the docstring


def tokens(text):
    """The tokens of one line, as the module docstring defines them."""
    return [t for t in TOKEN_GAPS.split(text) if t]


class Deleted:
    """What a diff deletes: `lines`, a Counter of each deleted text, and `hunks`, a dict of hunk number to a
    Counter of the tokens that hunk deletes (a hunk that deletes nothing has no entry)."""

    def __init__(self):
        self.lines = Counter()
        self.hunks = {}


def unquote(name):
    """A path as git printed it, unquoted when git quoted it; None when it cannot be read."""
    if name.startswith('"'):
        try:
            return ast.literal_eval(name).encode("latin-1").decode("utf-8")
        except (SyntaxError, ValueError, UnicodeError):
            return None
    return name


def deleted_texts(diff, scanned):
    """A `Deleted` of each deleted line's text, without its `-`, over each file of `diff` that `scanned` accepts.

    `scanned(path)` takes the file's old path, as the repo names it, and says whether the calling check reads
    that file. A `--- ` row is a file header only between `diff --git` and the first `@@`. Past that, it is a
    deleted line that starts with `--`."""
    left, header, keep, hunk = Deleted(), False, False, 0
    for row in diff.split("\n"):
        if row.startswith("diff --git "):
            header, keep = True, False
        elif header and row.startswith("--- "):
            old = unquote(row[4:].split("\t")[0])
            keep = bool(old) and old != "/dev/null" and scanned(old[2:] if old.startswith("a/") else old)
        elif row.startswith("@@"):
            header = False
            hunk += 1
        elif not header and keep and row.startswith("-"):
            left.lines[row[1:]] += 1
            left.hunks.setdefault(hunk, Counter()).update(tokens(row[1:]))
    return left


def take_move(left, text, hunk=None):
    """True when `left` still holds a deleted copy of the added line `text`, and uses that copy up.

    With a `hunk` number, a line that is a reflow of what that hunk deletes is a move too (module docstring),
    and uses up the tokens it holds."""
    if left.lines[text] > 0:
        left.lines[text] -= 1
        return True
    pool = left.hunks.get(hunk)
    if pool is None:
        return False
    need = Counter(tokens(text))
    if any(pool[t] < n for t, n in need.items()):
        return False
    pool.subtract(need)
    return True
