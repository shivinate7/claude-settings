#!/usr/bin/env python3
"""Says whether a change to a Python or shell file touches comments only.

    python3 lint/comment_only.py OLD_REF NEW_REF PATH [PATH ...]

Exit 0 when every PATH holds the same code at OLD_REF and NEW_REF once its comments are stripped. Exit 1 in every other case:
a code change, a path that is not .py or .sh, a path missing at either ref, a file that does not parse, an unreadable ref. An
unread file is never comment-only, so the caller keeps its suites on. Used by .github/scripts/ci-scope.sh to skip the code
suites for a comment-only delta from a fully green head (owner, 10:56 CST Nov 24 2026: a change that touches only comments in
a .py or .sh file skips the code suites; a docstring counts as code; the daily run is the net).

What stays code, and what goes:
- A docstring is a string token, so its text is code: the suites read it (the hook catalog, the reinstall and session-role suites).
- A shebang (line 1) and an encoding cookie (line 1 or 2) are comments to the tokenizer but pick the interpreter and the text
  decoder, so a change to one is code.
- A `# noqa`, `# type:`, `# pragma`, `# shellcheck` or other tool directive is a comment here, and a change to one reads as
  comment-only. The tools that read them (Ruff, mypy, ShellCheck) run in the `Code check` step of the `checks` job, which no flag
  turns off and which starts on every comment-only run, so a directive that breaks a tool still turns the run red.
- A string that holds a `#`, a `#` in a parameter expansion, a line that starts with `#` inside a multi-line string or a heredoc,
  and a lone quote in a comment are read by the language's own scan, so none is mistaken for a comment.
- Python compares the `tokenize` tokens with each comment and blank-line token dropped; whitespace inside a line is no token. Shell
  strips the comment spans that lint/check_comment_narration.py shell_comment_spans finds. A line holding only a comment is dropped,
  and a trailing comment takes the blank before it. A comment line that follows a line ending in a `\\` continuation is code: it
  ends the command, so the line after it runs as a new command. It leaves a marker line in its place.
"""
import ast
import bisect
import io
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, HERE)
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
import check_comment_narration as narration  # noqa: E402  the one home of the shell comment scan

COOKIE = re.compile(r"coding[:=]\s*[-\w.]+")
CONTINUATION = re.compile(r"(?<!\\)(?:\\\\)*\\$")  # an odd run of backslashes ends the line: the next line joins it
CONTINUED_COMMENT = "# comment after a continuation"  # stands in for the dropped comment line, so adding or removing one reads as code


def py_code(data):
    """The (type, text) tokens of Python source with comments and blank-line tokens dropped. A docstring stays: it is a string
    token, and suites read its text. Raises narration.Unread when the source does not parse."""
    try:
        ast.parse(data)
        tokens = list(tokenize.tokenize(io.BytesIO(data).readline))
    except (SyntaxError, ValueError, tokenize.TokenError) as e:
        raise narration.Unread("cannot read: %s" % e)
    out = []
    for tok in tokens:
        if tok.type in (tokenize.ENCODING, tokenize.NL):
            continue
        if tok.type == tokenize.COMMENT:
            if tok.start[0] == 1 and tok.string.startswith("#!") or tok.start[0] <= 2 and COOKIE.search(tok.string):
                out.append((tok.type, tok.string))
            continue
        out.append((tok.type, tok.string))
    return out


def sh_code(path, data):
    """The lines of shell source with each comment dropped: a line of only a comment goes, a trailing comment takes
    the blanks before it. Raises narration.Unread on an unclosed quote, expansion or heredoc."""
    try:
        src = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise narration.Unread("%s: cannot read: %s" % (path, e))
    src = re.sub(r"\r\n|\r", "\n", src)
    spans = narration.shell_comment_spans(path, src)
    starts = [0] + [m.end() for m in re.finditer("\n", src)]
    hit = set()
    for start, end in spans:
        if "\n" in src[start:end]:
            raise narration.Unread("%s: a comment spans a line end" % path)
        hit.add(bisect.bisect_right(starts, start) - 1)
    for start, end in reversed(spans):
        src = src[:start] + src[end:]
    lines = []
    for n, line in enumerate(src.split("\n")):
        if n in hit:
            line = line.rstrip()
            if not line:
                if lines and CONTINUATION.search(lines[-1]):
                    lines.append(CONTINUED_COMMENT)
                continue
        lines.append(line)
    return lines


def blob(ref, path):
    r = _nowindow.run(["git", "cat-file", "blob", "%s:%s" % (ref, path)], capture_output=True)
    if r.returncode:
        raise narration.Unread("%s:%s is not readable" % (ref, path))
    return r.stdout


def comment_only(old_ref, new_ref, path):
    """True when `path` differs between the refs in comments only (a docstring is code, for Python)."""
    ext = os.path.splitext(path)[1]
    if ext not in (".py", ".sh"):
        return False
    old, new = blob(old_ref, path), blob(new_ref, path)
    if ext == ".py":
        return py_code(old) == py_code(new)
    return sh_code(path, old) == sh_code(path, new)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    old_ref, new_ref, paths = argv[0], argv[1], argv[2:]
    try:
        return 0 if all(comment_only(old_ref, new_ref, p) for p in paths) else 1
    except narration.Unread as e:
        print("comment_only: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
