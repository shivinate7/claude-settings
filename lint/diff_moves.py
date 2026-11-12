"""The one home of "a moved line is not an added line" for the checks that read a diff by line number.

A line counts as moved only when the SAME diff deletes that exact text: every character, indentation too,
from a file the calling check scans. A line deleted from a file the check never reads (a doc, a generated
file) excuses nothing, so the caller passes its own "is this file scanned" test in.
Each deleted copy excuses at most one added copy, so one deleted line never excuses two added ones. The caller
asks `take_move` for every added line, in a scanned file or not, so a copy in a file the check skips uses up
the deleted copy too. The diff must be a unified diff of the whole change, deletes included.

A move into an untracked file has no diff, so it is no move: the file is read whole and stays checked.

Readers of a diff that use this home: check_comment_narration.added_lines and check_glossary.patch_lines.
Cost: one pass over a diff text the caller already holds. No process, no file.
"""
import ast
from collections import Counter


def unquote(name):
    """A path as git printed it, unquoted when git quoted it; None when it cannot be read."""
    if name.startswith('"'):
        try:
            return ast.literal_eval(name).encode("latin-1").decode("utf-8")
        except (SyntaxError, ValueError, UnicodeError):
            return None
    return name


def deleted_texts(diff, scanned):
    """A Counter of each deleted line's text, without its `-`, over each file of `diff` that `scanned` accepts.

    `scanned(path)` takes the file's old path, as the repo names it, and says whether the calling check reads
    that file. A `--- ` row is a file header only between `diff --git` and the first `@@`. Past that, it is a
    deleted line that starts with `--`."""
    left, header, keep = Counter(), False, False
    for row in diff.split("\n"):
        if row.startswith("diff --git "):
            header, keep = True, False
        elif header and row.startswith("--- "):
            old = unquote(row[4:].split("\t")[0])
            keep = bool(old) and old != "/dev/null" and scanned(old[2:] if old.startswith("a/") else old)
        elif row.startswith("@@"):
            header = False
        elif not header and keep and row.startswith("-"):
            left[row[1:]] += 1
    return left


def take_move(left, text):
    """True when `left` still holds a deleted copy of the added line `text`, and uses that copy up."""
    if left[text] > 0:
        left[text] -= 1
        return True
    return False
