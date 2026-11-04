"""Read a GitHub workflow's jobs and steps by line, stdlib only: no YAML library on a fresh runner or Mac.

The one home of the step parser. lint/test_windows_split.py reads the Windows split with it, and
bin/ci-job runs a job's steps locally with it. It reads the layout checks.yml keeps: jobs at 2 spaces,
`      - ` steps, step keys at 8 spaces, `env:` keys and `run: |` bodies at 10.
"""
import re


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


def block_scalar(style, lines, indent):
    """The text of a block scalar whose header is `style` (`|` or `>`, with an optional `+` or `-`) and whose body is
    `lines`, the lines after the header. The body is every following line indented `indent` spaces or deeper, or blank;
    the indent is removed. A literal block (`|`, `|-`, `|+`) keeps its lines. A folded block (`>`, `>-`, `>+`) joins
    each paragraph's lines with a space, as YAML folds them. None when `style` is not a block header."""
    kind = re.fullmatch(r"([|>])[+-]?", style)
    if not kind:
        return None
    body = []
    for ln in lines:
        if ln.strip() and not ln.startswith(" " * indent):
            break
        body.append(ln[indent:] if ln.strip() else "")
    text = "\n".join(body).strip("\n")
    if kind.group(1) == ">":
        text = "\n".join(" ".join(p.split("\n")) for p in re.split(r"\n\s*\n", text))
    return text + "\n"


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
