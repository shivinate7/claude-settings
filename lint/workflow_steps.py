"""Read a GitHub workflow's jobs and steps by line, stdlib only: no YAML library on a fresh runner or Mac.

The one home of the step parser. lint/test_windows_split.py reads the Windows split with it, and
bin/ci-job runs a job's steps locally with it. It reads the layout checks.yml keeps: jobs at 2 spaces,
`      - ` steps, step keys at 8 spaces, `env:` keys and `run: |` bodies at 10.
"""
import re

# The Linux jobs that hold the suites of the one old `checks` job, split for wall time. merge/merge.py reads suites from each.
CHECKS_SUITE_JOBS = ("checks", "checks-merge-install")
SUITE_LINE = re.compile(r"python3 ((?:hooks|lint|merge)/test_[\w.-]+\.py)(?: [^|&;`<>]*)?")  # a CI step's suite line, arguments allowed
# The unknown text bin/ci-job gives a step whose env NODE_PATH names an install that a skipped uses: step makes, and the reader of it
# that merge --lane-lint uses to print one `not run` line for it, not unknown.
MISSING_INSTALL = ("env NODE_PATH names {entry}, which is not installed here: the step that installs it (a uses: action) is not run locally, "
                   "so the suite cannot run")
MISSING_INSTALL_LINE = re.compile(r"unknown\s+.*?: env NODE_PATH names (\S+), which is not installed here")
# The one line bin/ci-job prints for the picked suites of another job, and the reader of it that merge --lane-lint uses.
NOT_RUN_JOB = "job {job}: picked {suites}; job {job} runs them, not {linted}"
NOT_RUN_JOB_LINE = re.compile(r"not run\s+job ([\w-]+): picked (\S.*?); job \1 runs them, not ([\w-]+)\s*$")


def job_block(text, name):
    """Raw text of one job: from its `  name:` line to the next job line. None when the job is absent."""
    m = re.search(rf"^  {re.escape(name)}:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def job_runs_on(block):
    """A job's `runs-on:` as one literal label, quotes stripped and a one-item flow list unwrapped, or None. None means the
    label is no single literal this reader can name: an expression (`${{ ... }}`), a map, a list of several, an empty or
    absent key. The caller reads None as unknown, never as a guess."""
    m = re.search(r"^    runs-on:[ \t]*(.*?)[ \t]*$", block or "", re.M)
    if not m:
        return None
    value = drop_comment(m.group(1)).strip()
    flow = re.fullmatch(r"\[\s*([^,\[\]{}]*?)\s*,?\s*\]", value)
    if flow:
        value = flow.group(1)
    quoted = re.fullmatch(r"""(["'])(.*)\1""", value)
    if quoted:
        value = quoted.group(2).strip()
    if not value or "${{" in value or re.match(r"[\[\]{}|>&*!,]", value):
        return None
    return value


def step_blocks(block):
    """Each `      - ` step of a job block, as raw text. Block scalars stay whole."""
    return [p for p in re.split(r"^(?=      - )", block or "", flags=re.M) if p.startswith("      - ")]


def step_key(step, key):
    """A step's own `key:` value (`        key:` or inline `      - key:`), or None. Body lines sit deeper."""
    m = re.search(rf"^(?:      - |        ){re.escape(key)}:[ \t]*(.*?)[ \t]*$", step, re.M)
    return m.group(1) if m else None


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
    body = []
    for ln in lines:
        if ln.strip() and len(ln) - len(ln.lstrip(" ")) < floor:
            break
        body.append(ln)
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
    lines = step.split("\n")
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
    lines = step.split("\n")
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


def run_lines(step):
    """The step's run: lines, with no blank line and no comment."""
    return [ln.strip() for ln in (run_body(step) or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]


def suite_paths(step):
    """The suites a CI step runs: the path of each of its run: lines that is `python3 hooks|merge|lint/test_<name>.py`, with
    arguments allowed. Any other line of the step stays in it, so a picked step runs whole, as CI runs it."""
    return [m.group(1) for ln in run_lines(step) if (m := SUITE_LINE.fullmatch(ln))]
