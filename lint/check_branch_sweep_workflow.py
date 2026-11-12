#!/usr/bin/env python3
"""Lints .github/workflows/branch-sweep.yml, the workflow that deletes branches with GitHub's own token.

    python3 lint/check_branch_sweep_workflow.py --workflow PATH

Prints `clean` (exit 0), or one line per finding, `<rule>: line <n>: <text>` (exit 1). An unreadable file exits 2.
Rules:
  permissions  only the contents scope is named; the top level is contents read; a job may request contents write
  secrets      no evaluated expression reads the secrets context; the token is github.token
  triggers     only push to main and workflow_dispatch
  pin          each uses: is pinned by a full commit SHA, except a ./ local action
  checkout     each actions/checkout step sets persist-credentials: false
  timeout      each job sets timeout-minutes

The reader is line based, with no YAML library: CI installs none for lint. It needs only the block style this
repo's workflows use. GitHub evaluates an expression in a quoted value, a plain value, or a run: block, even after a
`#`; it does not in a YAML comment. So a comment is cut only where YAML makes one: a `#` outside a quote that opens
a value, after whitespace. A quote inside a plain value (don't) opens nothing.
"""
import argparse
import re
import sys

KEY = re.compile(r"^(-\s+)?([A-Za-z0-9_.\"'-]+):(?:\s+(.*))?$")
BLOCK_SCALAR = re.compile(r"^[|>][+-]?\d*$")
EXPR = re.compile(r"\$\{\{(.*?)\}\}")
SECRETS = re.compile(r"(?<![\w.-])secrets(?![\w-])")
SHA_PIN = re.compile(r"@[0-9a-f]{40}$")
ALLOWED_TRIGGERS = ("push", "workflow_dispatch")


def strip_comment(text):
    """The line without its YAML comment. A quote opens only where a value starts, so `don't` is plain text."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or text[i - 1] in " \t:-,[{"):
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
    return text.rstrip()


def read_lines(text):
    """(structure, evaluated). structure: (n, indent, text) of each key or list line outside a block scalar,
    comments cut. evaluated: (n, text) of every line GitHub evaluates, a block scalar's raw lines included."""
    structure, evaluated, block = [], [], None
    for n, raw in enumerate(text.splitlines(), 1):
        indent = len(raw) - len(raw.lstrip(" "))
        if block is not None and (not raw.strip() or indent > block):
            evaluated.append((n, raw))
            continue
        block = None
        line = strip_comment(raw.strip()) if raw.strip() else ""
        if not line:
            continue
        structure.append((n, indent, line))
        evaluated.append((n, line))
        m = KEY.match(line)
        if m and m.group(3) and BLOCK_SCALAR.match(m.group(3)):
            block = indent + (len(m.group(1)) if m.group(1) else 0)
    return structure, evaluated


def unquote(value):
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def key_of(line):
    m = KEY.match(line)
    return (unquote(m.group(2)), unquote(m.group(3))) if m else (None, None)


def children(structure, i):
    """Indices of the lines nested under structure[i]."""
    indent = structure[i][1]
    j = i + 1
    while j < len(structure) and structure[j][1] > indent:
        j += 1
    return range(i + 1, j)


def inline_pairs(value):
    """{k: v} of a flow mapping `{a: b, c: d}`, else None."""
    if not (value.startswith("{") and value.endswith("}")):
        return None
    pairs = {}
    for part in value[1:-1].split(","):
        k, _, v = part.partition(":")
        if k.strip():
            pairs[unquote(k.strip())] = unquote(v.strip())
    return pairs


def scopes(structure, i):
    """(pairs, bad) for the permissions key at structure[i]: {scope: value} and an inline value that is no mapping."""
    _, value = key_of(structure[i][2])
    if value:
        flow = inline_pairs(value)
        return (flow, None) if flow is not None else ({}, value)
    pairs = {}
    for j in children(structure, i):
        k, v = key_of(structure[j][2])
        if k is not None:
            pairs[k] = (v, structure[j][0], structure[j][2])
    return pairs, None


def check_permissions(structure, i, top, found):
    n, _, text = structure[i]
    pairs, bad = scopes(structure, i)
    if bad:
        found.append((n, "permissions", text))
        return
    for scope in sorted(pairs):
        entry = pairs[scope]
        value, ln, ltext = entry if isinstance(entry, tuple) else (entry, n, text)
        if scope != "contents":
            found.append((ln, "permissions", ltext))
        elif value != "read" and not (value == "write" and not top):
            found.append((ln, "permissions", ltext))


def check_triggers(structure, i, found):
    n, _, text = structure[i]
    _, value = key_of(text)
    if value:
        # An inline list names no branches, so a push there is not limited to main.
        listed = value.strip("[]").split(",") if value.startswith("[") else [value]
        for name in (unquote(x.strip()) for x in listed if x.strip()):
            if name == "push" or name not in ALLOWED_TRIGGERS:
                found.append((n, "triggers", text))
        return
    body = list(children(structure, i))
    for j in body:
        if structure[j][1] != structure[body[0]][1]:
            continue
        name = key_of(structure[j][2])[0]
        if name not in ALLOWED_TRIGGERS:
            found.append((structure[j][0], "triggers", structure[j][2]))
        elif name == "push":
            branches = None
            for k in children(structure, j):
                bk, bv = key_of(structure[k][2])
                if bk == "branches":
                    if bv:
                        branches = [unquote(x.strip()) for x in bv.strip("[]").split(",")]
                    else:
                        branches = [unquote(structure[m][2][1:].strip()) for m in children(structure, k)]
            if branches != ["main"]:
                found.append((structure[j][0], "triggers", structure[j][2]))


def step_bounds(structure, i):
    """Indices of the step that holds structure[i]: from its `- ` line to the line before the next step."""
    start = i
    while start >= 0 and not structure[start][2].startswith("- "):
        start -= 1
    if start < 0:
        return range(i, i + 1)
    dash = structure[start][1]
    end = start + 1
    while end < len(structure) and structure[end][1] > dash:
        end += 1
    return range(start, end)


def check(text):
    structure, evaluated = read_lines(text)
    found = []

    top_permissions = None
    jobs_index = None
    for i, (n, indent, line) in enumerate(structure):
        if indent != 0:
            continue
        key, _ = key_of(line)
        if key == "permissions":
            top_permissions = i
        elif key in ("on", "true"):
            check_triggers(structure, i, found)
        elif key == "jobs":
            jobs_index = i
    if top_permissions is None:
        found.append((1, "permissions", "no top-level permissions block"))
    else:
        pairs, bad = scopes(structure, top_permissions)
        if bad or pairs.get("contents") is None:
            found.append((structure[top_permissions][0], "permissions", structure[top_permissions][2]))
        else:
            check_permissions(structure, top_permissions, True, found)

    if jobs_index is not None:
        job_indent = structure[jobs_index + 1][1] if jobs_index + 1 < len(structure) else 0
        for j in children(structure, jobs_index):
            if structure[j][1] != job_indent:
                continue
            body = list(children(structure, j))
            keys = {}
            for k in body:
                if structure[k][1] == structure[body[0]][1]:
                    keys.setdefault(key_of(structure[k][2])[0], k)
            if "timeout-minutes" not in keys:
                found.append((structure[j][0], "timeout", structure[j][2]))
            if "permissions" in keys:
                check_permissions(structure, keys["permissions"], False, found)

    for i, (n, indent, line) in enumerate(structure):
        key, value = key_of(line)
        if key != "uses":
            continue
        action = unquote(value)
        if action.startswith("./"):
            continue
        if not SHA_PIN.search(action):
            found.append((n, "pin", line))
        if action.startswith("actions/checkout@"):
            pinned = False
            for k in step_bounds(structure, i):
                ck, cv = key_of(structure[k][2])
                if ck == "persist-credentials" and cv == "false":
                    pinned = True
            if not pinned:
                found.append((n, "checkout", line))

    for n, line in evaluated:
        for m in EXPR.finditer(line):
            if SECRETS.search(m.group(1)):
                found.append((n, "secrets", line.strip()))
        key, value = key_of(line.strip())
        if key == "if" and value and "${{" not in value and SECRETS.search(value):
            found.append((n, "secrets", line.strip()))

    return sorted(set(found))


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args(argv)
    try:
        with open(args.workflow, encoding="utf-8") as f:
            text = f.read()
    except OSError as err:
        print("check_branch_sweep_workflow: %s" % err, file=sys.stderr)
        return 2
    found = check(text)
    if not found:
        print("clean")
        return 0
    for n, rule, line in found:
        print("%s: line %d: %s" % (rule, n, line.strip()))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
