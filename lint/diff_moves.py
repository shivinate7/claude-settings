"""The one home of "a moved line is not an added line" for the checks that read a diff by line number.

A line counts as moved only when the SAME diff deletes that exact text: every character, indentation too.
Each deleted copy excuses at most one added copy, so one deleted line never excuses two added ones. The diff
must be a unified diff of the whole change, deletes included.

A move into an untracked file has no diff, so it is no move: the file is read whole and stays checked.

Readers of a diff that use this home: check_comment_narration.added_lines and check_glossary.patch_lines.
Cost: one pass over a diff text the caller already holds. No process, no file.
"""
from collections import Counter


def deleted_texts(diff):
    """A Counter of each deleted line's text, without its `-`, over every file of `diff`.

    A `--- ` row is a file header only between `diff --git` and the first `@@`. Past that, it is a deleted
    line that starts with `--`."""
    left, header = Counter(), False
    for row in diff.split("\n"):
        if row.startswith("diff --git "):
            header = True
        elif row.startswith("@@"):
            header = False
        elif not header and row.startswith("-"):
            left[row[1:]] += 1
    return left


def take_move(left, text):
    """True when `left` still holds a deleted copy of the added line `text`, and uses that copy up."""
    if left[text] > 0:
        left[text] -= 1
        return True
    return False
