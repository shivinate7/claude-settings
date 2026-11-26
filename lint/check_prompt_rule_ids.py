#!/usr/bin/env python3
"""CI check: a rule id that a model prompt names has an anchor.

    python3 lint/check_prompt_rule_ids.py [--root DIR]

A model judge's prompt names the rule ids it may file a finding under. An id with no
`<!-- rule:<id> -->` anchor in a RULE_FILES file (lint/rule_audit.py) files its findings under a
dead id. The case that started this: JUDGED_RULES held `measure-before-priority`, and the anchor
was `style-measure-before-priority`.

WHAT IT READS. hooks/*.py, with `ast` and `tokenize`, in two places. A test file (`test_*.py`,
`*_test.py`) holds fixtures and is not read.
  - a prompt constant in PROMPT_CONSTANTS. A name it is built from (INSTRUCTIONS = "..." + GH_PART)
    is read through, in the same module.
  - the string a function returns, when its name has `prompt` in it: a plain, f-string, implicitly
    joined or plus-joined string, or a local name that the function assigns and returns.
A comment, a docstring and any other string are not read.

WHICH IDS. An id is read only from an id position, never from free prose, and its first word may be
any word. A family of anchors plays no part. The positions:
  - an item of an `ids` constant (JUDGED_RULES): the whole item is the id.
  - a rule-list line: an id that opens a string piece, or follows a newline inside one, then a colon.
  - a rule mention: the word "rule", an optional colon, then the id.
  - a backticked id.
A string piece is one quoted string in the source. Implicit joining makes one ast value of several
pieces, so the pieces come from the tokenizer.

WHAT IT CANNOT SEE. A prompt constant that is not in PROMPT_CONSTANTS, a prompt built across
functions or files, a function whose name lacks `prompt`, and an id in free prose.

Exit 0 when each id has an anchor. Exit 1 and one line per bad id otherwise, or when no id was
read at all: a reader that sees nothing must not print ok.
"""
from __future__ import annotations

import ast
import bisect
import glob
import io
import os
import re
import sys
import tokenize

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import rule_audit  # noqa: E402  the one home of the anchor pattern and the anchor files

# hooks/ file -> {prompt constant: how its strings read}. `ids`: each string is an id. `prose`: ids
# are read from id positions.
PROMPT_CONSTANTS = {
    "reply_judge.py": {"JUDGED_RULES": "ids", "INSTRUCTIONS": "prose"},
    "call_judge.py": {
        "OPUS_ASK_PROMPT": "prose",
        "OVERRIDE_ASK_PROMPT": "prose",
        "OPUS_SCOPE_PROMPT": "prose",
        "SPAWN_PROMPT": "prose",
        "PAST_RULING_ITEM": "prose",
        "JUDGE_ITEMS": "prose",
        "QUESTION_PROMPT": "prose",
        "PAGE_PROMPT": "prose",
        "NONE_DIRECTION_RULE": "prose",
        "WIDENING_TEMPLATE": "prose",
    },
    "decision_watch.py": {"JUDGE_INSTRUCTIONS": "prose"},
    "feedback_guard.py": {"PROMPT": "prose"},
    "sendmessage_state.py": {"WORDING_PROMPT": "prose"},
    "prose_judge.py": {"COMMON": "prose", "RULES": "prose"},
}
ID = r"[a-z0-9]+(?:-[a-z0-9]+)+"
NOT_WORD = r"(?![\w-])"
LIST_LINE = re.compile(r"(?:\A|\n)[ \t]*(%s)%s:" % (ID, NOT_WORD))
MENTION = re.compile(r"(?<![\w-])(?i:rule):?\s+(%s)%s" % (ID, NOT_WORD))
BACKTICKED = re.compile(r"`(%s)`" % ID)
FIELD = "\0"  # stands for an f-string field in a piece's text
# Python 3.12 and later tokenize an f-string into parts; before that it is one STRING token.
STARTS = {getattr(tokenize, n) for n in ("FSTRING_START", "TSTRING_START") if hasattr(tokenize, n)}
ENDS = {getattr(tokenize, n) for n in ("FSTRING_END", "TSTRING_END") if hasattr(tokenize, n)}


def is_test_file(name):
    return name.startswith("test_") or name.endswith("_test.py")


def module_assignments(tree):
    """{name: [value node, ...]} for each module-level assignment."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            names = [node.target.id]
        else:
            continue
        for name in names:
            out.setdefault(name, []).append(node.value)
    return out


def own_nodes(fn):
    """Each node of a function's body, not those of a function, lambda or class nested in it."""
    stack = list(fn.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def function_parts(fn):
    """(local assignments {name: [value]}, returned values) of a function."""
    assigns, returns = {}, []
    for node in own_nodes(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            returns.append(node.value)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns.setdefault(t.id, []).append(node.value)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name) and node.value is not None:
            assigns.setdefault(node.target.id, []).append(node.value)
    return assigns, returns


def atoms_of(value, assigns, seen):
    """Each string atom (a str Constant, or an f-string) under `value`, through a name in `assigns` that it uses."""
    if isinstance(value, ast.JoinedStr) or (isinstance(value, ast.Constant) and isinstance(value.value, str)):
        return [value]
    found = []
    if isinstance(value, ast.Name):
        if value.id in assigns and value.id not in seen:
            seen.add(value.id)
            for part in assigns[value.id]:
                found.extend(atoms_of(part, assigns, seen))
        return found
    for child in ast.iter_child_nodes(value):
        found.extend(atoms_of(child, assigns, seen))
    return found


def byte_col(lines, row, col):
    """ast counts a column in UTF-8 bytes, tokenize in characters."""
    return len(lines[row - 1][:col].encode("utf-8"))


def piece_text(src):
    """The decoded text of one quoted string in the source, an f-string field as FIELD; None for bytes."""
    body = ast.parse(src, mode="eval").body
    if isinstance(body, ast.Constant):
        return body.value if isinstance(body.value, str) else None
    return "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else FIELD
                   for v in getattr(body, "values", []))


def source_between(lines, start, end):
    """The source text from (row, column) `start` to `end`, a column in characters."""
    (r0, c0), (r1, c1) = start, end
    if r0 == r1:
        return lines[r0 - 1][c0:c1]
    return lines[r0 - 1][c0:] + "".join(lines[r0:r1 - 1]) + lines[r1 - 1][:c1]


def string_pieces(lines):
    """[(start, end, text)] for each quoted string in the source, in order; a position is (row, byte column).
    Implicit joining merges pieces into one ast value, so the pieces come from the tokenizer."""
    pieces, depth, first = [], 0, None
    for tok in tokenize.generate_tokens(iter(lines).__next__):
        if tok.type in STARTS:
            if depth == 0:
                first = tok.start
            depth += 1
            continue
        if tok.type in ENDS:
            depth -= 1
            if depth == 0:
                start, end, src = first, tok.end, source_between(lines, first, tok.end)
            else:
                continue
        elif tok.type == tokenize.STRING and depth == 0:
            start, end, src = tok.start, tok.end, tok.string
        else:
            continue
        text = piece_text(src)
        if text is not None:
            pieces.append(((start[0], byte_col(lines, *start)), (end[0], byte_col(lines, *end)), text))
    return pieces


def id_hits(texts):
    """[(piece index, id)] for each id at an id position in an atom's piece texts."""
    offsets, total = [], 0
    for text in texts:
        offsets.append(total)
        total += len(text)
    joined = "".join(texts)
    at = []
    for text, base in zip(texts, offsets):
        at.extend((base + m.start(1), m.group(1)) for m in LIST_LINE.finditer(text))
    for pattern in (MENTION, BACKTICKED):
        at.extend((m.start(1), m.group(1)) for m in pattern.finditer(joined))
    return [(bisect.bisect_right(offsets, pos) - 1, rid) for pos, rid in at]


def physical_line(first, last, rid, lines):
    """The 1-based line in first..last that holds the whole word `rid`; `first` when none does."""
    word = re.compile(r"(?<![\w-])%s%s" % (re.escape(rid), NOT_WORD))
    for n in range(first, last + 1):
        if word.search(lines[n - 1]):
            return n
    return first


def prompt_ids(root):
    """[(path, line, id)] for each rule id a prompt names, sorted. path is `hooks/<file>.py`."""
    found = set()
    for path in sorted(glob.glob(os.path.join(root, "hooks", "*.py"))):
        base = os.path.basename(path)
        if is_test_file(base):
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        assigns = module_assignments(tree)
        jobs = []  # (kind, atom)
        for name, kind in PROMPT_CONSTANTS.get(base, {}).items():
            for value in assigns.get(name, []):
                jobs.extend((kind, atom) for atom in atoms_of(value, assigns, {name}))
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and "prompt" in fn.name.lower():
                local, returns = function_parts(fn)
                for value in returns:
                    jobs.extend(("prose", atom) for atom in atoms_of(value, local, set()))
        if not jobs:
            continue
        lines = io.StringIO(source).readlines()
        pieces = string_pieces(lines) if any(kind == "prose" for kind, _ in jobs) else []
        rel = "hooks/" + base
        for kind, atom in jobs:
            if kind == "ids":
                if isinstance(atom, ast.Constant) and atom.value:
                    found.add((rel, physical_line(atom.lineno, atom.end_lineno, atom.value, lines), atom.value))
                continue
            span = ((atom.lineno, atom.col_offset), (atom.end_lineno, atom.end_col_offset))
            mine = [p for p in pieces if span[0] <= p[0] and p[1] <= span[1]]
            for index, rid in id_hits([p[2] for p in mine]):
                found.add((rel, physical_line(mine[index][0][0], mine[index][1][0], rid, lines), rid))
    return sorted(found)


def problems(root):
    """One message per id with no anchor, naming its file, line and id."""
    anchored = set(rule_audit.claude_md_anchors(rule_audit.rule_text(root)))
    where = " or ".join(p.replace(os.sep, "/") for p in rule_audit.RULE_FILES)
    return ["%s:%d: the prompt names rule id %s, which has no anchor in %s" % (path, line, rid, where)
            for path, line, rid in prompt_ids(root) if rid not in anchored]


def main(argv):
    root = rule_audit.ROOT
    if argv[:1] == ["--root"] and len(argv) == 2:
        root = os.path.abspath(argv[1])
    elif argv:
        print("usage: check_prompt_rule_ids.py [--root DIR]")
        return 2
    try:
        read = prompt_ids(root)
        bad = problems(root)
    except (OSError, SyntaxError, ValueError, tokenize.TokenError) as e:
        print("check_prompt_rule_ids: FAIL, could not read: %s" % e)
        return 1
    if not read:
        print("check_prompt_rule_ids: FAIL, no rule id read from any prompt constant (the reader sees nothing)")
        return 1
    for message in bad:
        print("check_prompt_rule_ids: FAIL, " + message)
    if bad:
        return 1
    print("check_prompt_rule_ids: ok, %d prompt rule ids, each anchored" % len(read))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
