"""Read a GitHub workflow's jobs and steps by line, stdlib only: no YAML library on a fresh runner or Mac.

The one home of the step parser. lint/test_windows_split.py reads the Windows split with it, and
bin/ci-job runs a job's steps locally with it. It reads the layout checks.yml keeps: jobs at 2 spaces,
`      - ` steps, step keys at 8 spaces, `env:` keys and `run: |` bodies at 10.
"""
import os
import re
import sys

# A `uses:` of one of this repo's own actions at a ref: `<owner>/claude-settings/actions/<name>@<ref>`.
SETTINGS_ACTION = re.compile(r"[\w.-]+/claude-settings/actions/([\w-]+)@([\w.+/-]+)")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
BLOCK_HEADER = re.compile(r"([|>])([+-]?)")  # a block scalar's header: `|` or `>`, with an optional `-` or `+`

# The Linux jobs that hold the suites of the one old `checks` job, split for wall time. merge/merge.py reads suites from each.
CHECKS_SUITE_JOBS = ("checks", "checks-merge-install")


def job_re(name):
    """The pattern of one job: group 1 is the text from its `  name:` line to the next job line. `name` is a regex."""
    return re.compile(rf"^  {name}:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", re.M | re.S)


def job_block(text, name):
    """Raw text of one job: from its `  name:` line to the next job line. None when the job is absent."""
    m = job_re(re.escape(name)).search(text)
    return m.group(1) if m else None


def job_workflow(top, job):
    """The one workflow file in `<top>/.github/workflows/` (*.yml, *.yaml) that holds `job`. -> (path, None), or
    (None, why) when the folder is unreadable or no file, or more than one file, holds it. The file name is the repo's
    own (checks.yml, check.yml), so the job is the key."""
    folder = os.path.join(top, ".github", "workflows")
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith((".yml", ".yaml")))
    except OSError as e:
        return None, "cannot read %s: %s" % (folder, e)
    found = []
    for n in names:
        try:
            with open(os.path.join(folder, n), encoding="utf-8") as f:
                if job_block(f.read(), job) is not None:
                    found.append(n)
        except (OSError, UnicodeError):
            continue  # a file it cannot read names no job; the job is found in another file, or none
    if len(found) == 1:
        return os.path.join(folder, found[0]), None
    if not found:
        return None, "no workflow file in %s has a `%s` job" % (folder, job)
    return None, "more than one workflow file in %s has a `%s` job: %s" % (folder, job, ", ".join(found))


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
    kind = BLOCK_HEADER.fullmatch(style)
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


def run_header(lines):
    """(i, raw, style) for the `run:` line of a step's `lines`: its index, the text after `run:`, and that text without its
    inline comment when it is a block header (`|` or `>`), else None. None when the step has no `run:`. The one test for
    where a run block starts: run_body reads its text and settings_pins skips its lines, both from this."""
    for i, line in enumerate(lines):
        m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", line)
        if m:
            style = drop_comment(m.group(1))  # a comment after the header is no script
            return i, m.group(1), style if BLOCK_HEADER.fullmatch(style) else None
    return None


def run_body(step):
    """A step's `run:` text: the one line, or a block scalar with its 10-space indent removed. None if absent."""
    lines = step_lines(step)
    head = run_header(lines)
    if head is None:
        return None
    i, raw, style = head
    return raw if style is None else block_scalar(style, lines[i + 1:], 10)


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


def yaml_scalar(text):
    """A YAML scalar's value: the inline comment cut (drop_comment), one pair of matching outer quotes removed and their escapes
    undone (`''` in single quotes, `\\"` and `\\\\` in double), so a `#` inside quotes stays text."""
    value = drop_comment((text or "").strip())
    if len(value) < 2 or value[0] != value[-1] or value[0] not in "'\"":
        return value
    inner = value[1:-1]
    return inner.replace("''", "'") if value[0] == "'" else re.sub(r'\\(["\\])', r"\1", inner)  # `''` and `\"`, `\\` are escapes


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


def line_without_comment(line):
    """A workflow line without its comment. A comment is a `#` at the start or after a space or tab, outside quotes. A quote
    opens only at the start of a token (the line start, or after a space, `{`, `[`, `,`, `:` or `-`) and only when its closer
    is on the line, so a `#` inside '...' or "..." is text, and a lone `'` in `don't` or `it's` opens nothing."""
    i = 0
    while i < len(line):
        c = line[i]
        if c in "'\"" and (i == 0 or line[i - 1] in " \t{[,:-"):
            j = i + 1
            while j < len(line):
                if c == '"' and line[j] == "\\":
                    j += 2
                    continue
                if line[j] == c:
                    if c == "'" and line[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            if j < len(line):
                i = j + 1
                continue
        elif c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
        i += 1
    return line


def settings_pins(text):
    """[(action, ref, line)] for each `<owner>/claude-settings/actions/<name>@<ref>` in a workflow, in file order, `line` being
    its 1-based line. It reads every line, so a pin in a flow-style step (`- {uses: ...}`) or a steps list at another indent is
    found; a line loses its comment (a `#` at the start or after a space, outside quotes, so `# v1` and `# - uses:` are no pin) and a step's
    `run:` text is skipped, since it is a script and not a `uses:`. A pin-like token the parser cannot place as a step key is
    still reported, never dropped. The ref is the characters after `@` up to a space, quote, comma or brace: a caller that
    needs a commit checks it against COMMIT_SHA."""
    lines = text.split("\n")
    skip, at = set(), 0
    for st in step_blocks(text):
        at = text.index(st, at)  # the blocks are slices of `text` in order, so each search starts at the last
        first = text.count("\n", 0, at)
        body = step_lines(st)
        head = run_header(body)
        if head:
            i, _, style = head  # the `run:` line is skipped, and its block lines after it
            skip.update(range(first + i, first + i + 1 + (len(block_lines(body[i + 1:], 10)) if style else 0)))
    found = []
    for n, ln in enumerate(lines):
        if n not in skip:
            for m in SETTINGS_ACTION.finditer(line_without_comment(ln)):
                found.append((m.group(1), m.group(2), n + 1))
    return found


GATING_KEYS = ("continue-on-error", "if")


def disables(key, value):
    """True when a `key:` value makes its step or job unable to fail a pull request: `continue-on-error: true`, or an
    `if:` that is always false. The value loses its inline comment first. hooks/guard.py's WORKFLOW_DISABLE_STEP is the
    one home of the disabling forms, so it decides; the import is lazy because guard.py is large and bin/ci-job loads
    this file."""
    hooks = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    import guard
    return guard.workflow_step_disables(f"{key}: {drop_comment(value).strip()}")


def gating_text(text):
    """The workflow text without each step or job that cannot fail a pull request (see `disables`), so a read of what
    CI runs counts only what can fail. A job's own keys sit at 4 spaces; a step's, by step_key. A comment, a block
    scalar body or a quoted run is never the key."""
    def disabled(own_value):
        return any(disables(key, own_value(key)) for key in GATING_KEYS if own_value(key) is not None)

    def keep(job):
        body = job.group(1)
        if disabled(lambda key: next((m.group(1) for m in re.finditer(rf"^    {key}:[ \t]*(.*?)[ \t]*$", body, re.M)), None)):
            return ""
        first = re.search(r"^      - ", body, re.M)
        if not first:
            return job.group(0)
        live = "".join(s for s in step_blocks(body) if not disabled(lambda key: step_key(s, key)))
        return job.group(0)[:job.start(1) - job.start(0)] + body[:first.start()] + live
    return job_re(r"[\w-]+").sub(keep, text)
