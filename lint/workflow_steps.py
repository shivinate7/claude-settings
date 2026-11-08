"""Read a GitHub workflow's jobs and steps by line, stdlib only: no YAML library on a fresh runner or Mac.

The one home of the step parser. lint/test_windows_split.py reads the Windows split with it, and
bin/ci-job runs a job's steps locally with it. It reads the layout checks.yml keeps: jobs at 2 spaces,
`      - ` steps, step keys at 8 spaces, `env:` keys and `run: |` bodies at 10.
"""
import re

# A `uses:` of one of this repo's own actions at a ref: `<owner>/claude-settings/actions/<name>@<ref>`.
SETTINGS_ACTION = re.compile(r"[\w.-]+/claude-settings/actions/([\w-]+)@([\w.+/-]+)")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")

# The Linux jobs that hold the suites of the one old `checks` job, split for wall time. merge/merge.py reads suites from each.
CHECKS_SUITE_JOBS = ("checks", "checks-merge-install")


def job_block(text, name):
    """Raw text of one job: from its `  name:` line to the next job line. None when the job is absent."""
    m = re.search(rf"^  {re.escape(name)}:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def step_blocks(block):
    """Each `      - ` step of a job block, as raw text. Block scalars stay whole."""
    return [p for p in re.split(r"^(?=      - )", block or "", flags=re.M) if p.startswith("      - ")]


def step_key(step, key):
    """A step's own `key:` value (`        key:` or inline `      - key:`), or None. Body lines sit deeper."""
    m = re.search(rf"^(?:      - |        ){re.escape(key)}:[ \t]*(.*?)[ \t]*$", step, re.M)
    return m.group(1) if m else None


def step_lines(step):
    """A step's real lines. A step from step_blocks ends in a newline, and a plain split would add an empty line after it,
    which a block scalar counts as its own: a `run: |` body would then run one line into the next step."""
    lines = step.split("\n")
    return lines[:-1] if len(lines) > 1 and not lines[-1] else lines


def block_lines(lines, floor):
    """The leading lines of `lines` that a block scalar owns: the blank lines and the lines indented `floor` spaces or deeper."""
    body = []
    for ln in lines:
        if ln.strip() and len(ln) - len(ln.lstrip(" ")) < floor:
            break
        body.append(ln)
    return body


def block_scalar(style, lines, floor):
    """The text of a block scalar whose header is `style` (`|` or `>`, with an optional `-` or `+`) and whose body is
    `lines`, the lines after the header. The body is the blank lines and the lines indented `floor` spaces or deeper;
    its indent is that of its first non-blank line, as in YAML, and is removed. A literal block keeps its lines. A folded
    block joins the lines of a paragraph with a space; a blank line between two lines is a newline, and a line indented
    deeper than the body keeps its own line. `-` drops the final newline and `+` keeps the blank lines at the end;
    otherwise the text ends in one newline. None when `style` is not a block header."""
    kind = re.fullmatch(r"([|>])([+-]?)", style)
    if not kind:
        return None
    body = block_lines(lines, floor)
    first = next((ln for ln in body if ln.strip()), None)
    if first is None:
        return ""
    indent = len(first) - len(first.lstrip(" "))
    body = [ln[indent:] if ln.strip() else "" for ln in body]
    trailing = 0
    while not body[-1]:
        body.pop()
        trailing += 1
    while not body[0]:
        body.pop(0)
    if kind.group(1) == ">":
        text, gap, prev = "", 0, None
        for ln in body:
            if not ln:
                gap += 1
                continue
            if prev is not None:
                deeper = ln.startswith(" ") or prev.startswith(" ")
                text += "\n" * (gap + 1 if deeper else gap) if (gap or deeper) else " "
            text, gap, prev = text + ln, 0, ln
    else:
        text = "\n".join(body)
    return text + {"-": "", "": "\n", "+": "\n" * (1 + trailing)}[kind.group(2)]


def run_body(step):
    """A step's `run:` text: the one line, or a block scalar with its 10-space indent removed. None if absent."""
    lines = step_lines(step)
    for i, line in enumerate(lines):
        m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        text = block_scalar(m.group(1), lines[i + 1:], 10)
        return m.group(1) if text is None else text
    return None


def drop_comment(value):
    """A map value without its inline comment. A comment is a `#` at the start or after a space or tab, outside
    quotes. A quote opens only at the start of the value, as in YAML, so a lone `'` in `don't/ # x` is text."""
    quote = value[:1] if value[:1] in ("'", '"') else ""
    i = 1 if quote else 0
    while quote and i < len(value):  # skip to the closing quote: `\x` in double quotes, `''` in single quotes
        if quote == '"' and value[i] == "\\":
            i += 2
            continue
        if value[i] == quote:
            if quote == "'" and value[i + 1:i + 2] == "'":
                i += 2
                continue
            i += 1
            break
        i += 1
    for j in range(i, len(value)):
        if value[j] == "#" and (j == 0 or value[j - 1] in " \t"):
            return value[:j].rstrip()
    return value


def step_map(step, key):
    """A step's own `key:` block (`env:` or `with:`) as {name: value}, or {} when it has none. A `|` or `>` value reads
    as its lines (block_scalar, indented past the 10-space keys); other values lose an inline comment."""
    found, inside = {}, False
    lines = step_lines(step)
    for i, line in enumerate(lines):
        if re.match(rf"^(?:      - |        ){re.escape(key)}:[ \t]*$", line):
            inside = True
        elif inside and (m := re.match(r"^          ([\w-]+):[ \t]*(.*?)[ \t]*$", line)):
            value = drop_comment(m.group(2))
            text = block_scalar(value, lines[i + 1:], 11)
            found[m.group(1)] = value if text is None else text
        elif inside and line.strip() and not line.startswith("          "):
            inside = False
    return found


def step_env(step):
    """A step's own `env:` block as {name: raw value}, or {} when it has none."""
    return step_map(step, "env")


def step_with(step):
    """A step's own `with:` block as {name: raw value}, or {} when it has none."""
    return step_map(step, "with")


def settings_pins(text):
    """[(action, ref, line)] for each `<owner>/claude-settings/actions/<name>@<ref>` in a workflow, in file order, `line` being
    its 1-based line. It reads every line, so a pin in a flow-style step (`- {uses: ...}`) or a steps list at another indent is
    found; a line loses its comment (a `#` at the start or after a space, so `# v1` and `# - uses:` are no pin) and a step's
    `run:` text is skipped, since it is a script and not a `uses:`. A pin-like token the parser cannot place as a step key is
    still reported, never dropped. The ref is the characters after `@` up to a space, quote, comma or brace: a caller that
    needs a commit checks it against COMMIT_SHA."""
    lines = text.split("\n")
    skip, at = set(), 0
    for st in step_blocks(text):
        at = text.index(st, at)  # the blocks are slices of `text` in order, so each search starts at the last
        first = text.count("\n", 0, at)
        body = step_lines(st)
        for i, ln in enumerate(body):
            m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", ln)
            if m:
                skip.update(range(first + i, first + i + 1 + (len(block_lines(body[i + 1:], 10)) if re.fullmatch(
                    r"[|>][+-]?", m.group(1)) else 0)))
                break
    found = []
    for n, ln in enumerate(lines):
        if n not in skip:
            for m in SETTINGS_ACTION.finditer(re.sub(r"(^|\s)#.*", "", ln)):
                found.append((m.group(1), m.group(2), n + 1))
    return found
