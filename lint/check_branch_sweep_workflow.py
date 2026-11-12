#!/usr/bin/env python3
"""Lints .github/workflows/branch-sweep.yml, the workflow that deletes branches with GitHub's own token.

    python3 lint/check_branch_sweep_workflow.py --workflow PATH

Prints `clean` (exit 0), or one line per finding, `<rule>: line <n>: <text>` (exit 1). An unreadable file exits 2.
Rules:
  permissions  only the contents scope is named; the top level is contents read; a job may request contents write
  secrets      no evaluated expression reads the secrets context; the token is github.token
  triggers     only push to main and workflow_dispatch
  pin          each uses: is pinned by a full commit SHA, except a ./ local action
  checkout     each actions/checkout step sets persist-credentials: false under its with:
  timeout      each job sets timeout-minutes
  read         the step that reads open pull requests cannot fail silently: no || true, || echo, or continue-on-error
  injection    no ${{ }} expression inside a run block, comments of the block included
  concurrency  a concurrency block is set at the top level
  condition    each job has an if: that limits it to refs/heads/main
  argv         --open-head takes its value as --open-head=VALUE, so a value that starts with - is no option
  tip          each DELETE call has a gh api read of a tip path that names the same branch variable earlier in the
               same loop; a comment or a quoted string is no call. It does not check the value, the read's exit
               handling or the compare
  budget       the run block that deletes reads the request budget with gh api rate_limit before its delete loop, and
               takes the reserve from sweep.py --budget-reserve; in that block a comparison against a number literal,
               quoted or in (( )), is a copy of the reserve. A comment or a quoted string, one that spans lines
               included, is no call

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
SILENT_FAIL = re.compile(r"\|\|\s*(true|:|exit\s+0|echo)\b|\bset\s+\+e\b")
MAIN_ONLY = re.compile(r"^(\$\{\{\s*)?github\.ref\s*==\s*['\"]refs/heads/main['\"](\s*\}\})?$")
SPLIT_ARG = re.compile(r"--open-head(?!=)")
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
    """(structure, evaluated, runs). structure: (n, indent, text) of each key or list line outside a block scalar,
    comments cut. evaluated: (n, text) of every line GitHub evaluates, a block scalar's raw lines included.
    runs: (n, text) of each line of a run: value, a block's comment lines included."""
    structure, evaluated, runs, block, in_run = [], [], [], None, False
    for n, raw in enumerate(text.splitlines(), 1):
        indent = len(raw) - len(raw.lstrip(" "))
        if block is not None and (not raw.strip() or indent > block):
            evaluated.append((n, raw))
            if in_run:
                runs.append((n, raw))
            continue
        block = None
        line = strip_comment(raw.strip()) if raw.strip() else ""
        if not line:
            continue
        structure.append((n, indent, line))
        evaluated.append((n, line))
        m = KEY.match(line)
        in_run = False
        if m and m.group(3) and BLOCK_SCALAR.match(m.group(3)):
            block = indent + (len(m.group(1)) if m.group(1) else 0)
            in_run = unquote(m.group(2)) == "run"
        elif m and m.group(3) and unquote(m.group(2)) == "run":
            runs.append((n, line))
    return structure, evaluated, runs


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


def under_with(structure, k):
    """True when structure[k] sits directly under a with: key."""
    j = k - 1
    while j >= 0 and structure[j][1] >= structure[k][1]:
        j -= 1
    return j >= 0 and key_of(structure[j][2])[0] == "with"


def sets_persist_false(structure, bounds):
    for k in bounds:
        ck, cv = key_of(structure[k][2])
        if ck == "persist-credentials" and cv == "false" and under_with(structure, k):
            return True
        if ck == "with" and cv and (inline_pairs(cv) or {}).get("persist-credentials") == "false":
            return True
    return False


def step_span(structure, i, last):
    """(first line, last line) of the step holding structure[i], block scalar lines included."""
    bounds = step_bounds(structure, i)
    end = structure[bounds[-1] + 1][0] - 1 if bounds[-1] + 1 < len(structure) else last
    return structure[bounds[0]][0], end


def check_read(structure, evaluated, runs, found, last):
    """The step that runs gh api on the pulls endpoint. A failed read must fail the job: a sweep that cannot see
    open pull requests could delete a head and close its pull request."""
    run_lines = {n for n, _ in runs}
    for i, (n, _, line) in enumerate(structure):
        if not line.startswith("- "):
            continue
        first, end = step_span(structure, i, last)
        body = [(m, t) for m, t in evaluated if first <= m <= end]
        if not any("pulls" in t and "gh api" in t for m, t in body):
            continue
        for m, t in body:
            if m in run_lines and not t.strip().startswith("#") and SILENT_FAIL.search(t):
                found.append((m, "read", t.strip()))
            key, value = key_of(t.strip())
            if key == "continue-on-error" and value != "false":
                found.append((m, "read", t.strip()))
        return
    found.append((1, "read", "no step reads the open pull requests with gh api"))


def mask_shell(text):
    """The line with each shell comment cut and each quoted span blanked, so only commands outside quotes remain.
    Quote state resets per line, and a quote opens only where a word starts, so `don't` and a quote left open on
    one line hide nothing on the next."""
    out, quote = [], None
    for i, ch in enumerate(text):
        if quote:
            out.append(" ")
            if ch == quote:
                quote = None
        elif ch in "\"'" and (i == 0 or text[i - 1] in " \t=;&|(<>"):
            quote = ch
            out.append(" ")
        elif ch == "#" and (i == 0 or text[i - 1] in " \t;&|("):
            break
        else:
            out.append(ch)
    return "".join(out)


def run_blocks(runs):
    """Lists of (n, text) lines, one per run: value. A block scalar's lines are contiguous; a one-line run: opens its own."""
    blocks, last = [], None
    for n, text in runs:
        starts = re.match(r"^(-\s+)?run:", text.strip())
        if last is None or n != last + 1 or starts:
            blocks.append([])
        blocks[-1].append((n, text))
        last = n
    return blocks


def logical_lines(block):
    """(n, text) per shell command line, a line that ends in a backslash joined to the next."""
    joined, pending = [], None
    for n, text in block:
        if pending:
            n, text = pending[0], pending[1] + " " + text.strip()
            pending = None
        if text.rstrip().endswith("\\"):
            pending = (n, text.rstrip()[:-1])
        else:
            joined.append((n, text))
    if pending:
        joined.append(pending)
    return joined


GH_API = re.compile(r"\bgh\s+api\b")
DELETE_CALL = re.compile(r"(-X\s*|--method[\s=]+)DELETE\b", re.I)
READ_BRANCH = re.compile(r"git/ref/heads/([^\s\"'?]+)")
DELETE_BRANCH = re.compile(r"git/refs/heads/([^\s\"'?]+)")
LOOP_OPEN = re.compile(r"^\s*(while|until|for)\b")
LOOP_CLOSE = re.compile(r"^\s*done\b")
LOOP_ONE_LINE = re.compile(r"\bdo\b.*\bdone\b")


def branch_of(pattern, segment):
    """The branch text in a ref path, `${name}` read as `$name`, or None when the segment has no such path."""
    m = pattern.search(segment)
    return re.sub(r"\$\{(\w+)\}", r"$\1", m.group(1)) if m else None


def check_tip(runs, found):
    """Each DELETE call has a gh api read of the same branch variable's tip earlier in its loop. Between a read and
    the DELETE a push moves the tip, and the verdict was computed on the old one. A call is a `gh api` outside
    quotes and comments; a commented-out call or one named in a string is text. A one-line `do ... done` is its own
    scope. The lint compares the branch text of the two paths, as `$name`, not what the variable holds."""
    for block in run_blocks(runs):
        scopes_read = [set()]  # one set per open loop, the run block itself first: branch texts whose tip it read
        for n, text in logical_lines(block):
            masked = mask_shell(text)
            one_line = bool(LOOP_OPEN.match(masked) and LOOP_ONE_LINE.search(masked))
            if one_line:
                scopes_read.append(set())
            elif LOOP_CLOSE.match(masked) and len(scopes_read) > 1:
                scopes_read.pop()
            starts = [m.start() for m in GH_API.finditer(masked)]
            for k, start in enumerate(starts):
                end = starts[k + 1] if k + 1 < len(starts) else len(masked)
                if DELETE_CALL.search(masked[start:end]):
                    branch = branch_of(DELETE_BRANCH, text[start:end])
                    read = scopes_read[-1]
                    if not read or (branch is not None and branch not in read):
                        found.append((n, "tip", text.strip()))
                else:
                    branch = branch_of(READ_BRANCH, text[start:end])
                    if branch is not None:
                        scopes_read[-1].add(branch)
            if one_line:
                scopes_read.pop()
            elif LOOP_OPEN.match(masked):
                scopes_read.append(set())


BUDGET_READ = re.compile(r"\brate_limit\b")
BUDGET_RESERVE_CALL = re.compile(r"\bsweep\.py\s+--budget-reserve\b")
# A test-command compare (-lt 300, -lt "300") or an arithmetic compare, `(( remaining < 300 ))` or `(( 300 > remaining ))`, against a number.
LITERAL_COMPARE = re.compile(r"-(?:lt|le|gt|ge)\s+([\"']?)\d+\1(?=\s|\]|;|$)")
ARITH_COMPARE = re.compile(r"\(\((?:(?!\)\)).)*?(?:(?<![\w$])\d+\s*[<>]|[<>]=?\s*\d+(?!\w))")


def mask_block(block):
    """[(n, masked)] for a run block's lines: each shell comment cut and each quoted span blanked, like mask_shell,
    but a quote left open at the end of a line stays open on the next, so text inside a multi-line string is no
    command. A quote opens only where a word starts, so `don't` opens nothing. A backslash in double quotes skips
    the next character. A span on one line that holds only digits, such as "300", is kept: it is a number literal
    in a compare, not text."""
    out, quote = [], None
    for n, text in block:
        chars, skip, opened = [], False, None
        for i, ch in enumerate(text):
            if quote:
                chars.append(" ")
                if skip:
                    skip = False
                elif ch == "\\" and quote == '"':
                    skip = True
                elif ch == quote:
                    if opened is not None and text[opened + 1:i].isdigit():
                        chars[opened:i + 1] = text[opened:i + 1]
                    quote = None
            elif ch in "\"'" and (i == 0 or text[i - 1] in " \t=;&|(<>"):
                quote = ch
                opened = i
                chars.append(" ")
            elif ch == "#" and (i == 0 or text[i - 1] in " \t;&|("):
                break
            else:
                chars.append(ch)
        out.append((n, "".join(chars)))
    return out


def check_budget(runs, found):
    """The run block that deletes with gh api -X DELETE reads the budget before the loop that holds the first DELETE,
    and gets the reserve from sweep.py, not from a literal. Without the read the loop spends the shared request
    pool down to nothing, and other runs in the repo then fail."""
    for block in run_blocks(runs):
        masked = mask_block(block)
        reads, reserves, compares, first_delete = [], [], [], None
        stack = []  # open loops' first lines
        for n, text in logical_lines(masked):
            one_line = bool(LOOP_OPEN.match(text) and LOOP_ONE_LINE.search(text))
            if LOOP_CLOSE.match(text) and stack and not one_line:
                stack.pop()
            starts = [m.start() for m in GH_API.finditer(text)]
            for k, start in enumerate(starts):
                end = starts[k + 1] if k + 1 < len(starts) else len(text)
                if DELETE_CALL.search(text[start:end]):
                    if first_delete is None:
                        first_delete = (n, stack[0] if stack else n)
                elif BUDGET_READ.search(text[start:end]):
                    reads.append(n)
            if BUDGET_RESERVE_CALL.search(text):
                reserves.append(n)
            if LITERAL_COMPARE.search(text) or ARITH_COMPARE.search(text):
                compares.append((n, "budget", text.strip()))
            if LOOP_OPEN.match(text) and not one_line:
                stack.append(n)
        if first_delete is None:
            continue
        found.extend(compares)  # a number compare in a block with no delete, such as the pulls step, copies no reserve
        n, loop_start = first_delete
        if not any(r < loop_start for r in reads):
            found.append((n, "budget", "no gh api rate_limit read before the delete loop"))
        if not any(r < loop_start for r in reserves):
            found.append((n, "budget", "the reserve does not come from sweep.py --budget-reserve before the delete loop"))


def check(text):
    structure, evaluated, runs = read_lines(text)
    last = len(text.splitlines())
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
    if "concurrency" not in {key_of(line)[0] for _, indent, line in structure if indent == 0}:
        found.append((1, "concurrency", "no top-level concurrency block"))
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
            condition = unquote(key_of(structure[keys["if"]][2])[1]) if "if" in keys else ""
            if not MAIN_ONLY.match(condition.strip()):
                found.append((structure[j][0], "condition", structure[j][2]))
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
            if not sets_persist_false(structure, step_bounds(structure, i)):
                found.append((n, "checkout", line))

    for n, line in evaluated:
        for m in EXPR.finditer(line):
            if SECRETS.search(m.group(1)):
                found.append((n, "secrets", line.strip()))
        key, value = key_of(line.strip())
        if key == "if" and value and "${{" not in value and SECRETS.search(value):
            found.append((n, "secrets", line.strip()))

    for n, line in runs:
        if "${{" in line:
            found.append((n, "injection", line.strip()))
        if SPLIT_ARG.search(line) and not line.strip().startswith("#"):
            found.append((n, "argv", line.strip()))
    check_read(structure, evaluated, runs, found, last)
    check_tip(runs, found)
    check_budget(runs, found)

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
