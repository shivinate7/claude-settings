"""Read a GitHub workflow's jobs and steps by line, stdlib only: no YAML library on a fresh runner or Mac.

The one home of the step parser. lint/test_windows_split.py reads the Windows split with it, and
bin/ci-job runs a job's steps locally with it. It reads the layout gates.yml keeps: jobs at 2 spaces,
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


def run_body(step):
    """A step's `run:` text: the one line, or a block scalar with its 10-space indent removed. None if absent.
    A literal block (`|`, `|-`, `|+`) keeps its lines. A folded block (`>`, `>-`, `>+`) joins each paragraph's
    lines with a space, as YAML folds them."""
    lines = step.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r"^(?:      - |        )run:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        style = re.fullmatch(r"([|>])[+-]?", m.group(1))
        if not style:
            return m.group(1)
        body = []
        for ln in lines[i + 1:]:
            if ln.strip() and not ln.startswith("          "):
                break
            body.append(ln[10:] if ln.strip() else "")
        text = "\n".join(body).strip("\n")
        if style.group(1) == ">":
            text = "\n".join(" ".join(p.split("\n")) for p in re.split(r"\n\s*\n", text))
        return text + "\n"
    return None


def step_env(step):
    """A step's own `env:` block as {name: raw value}, or {} when it has none."""
    env, inside = {}, False
    for line in step.split("\n"):
        if re.match(r"^(?:      - |        )env:[ \t]*$", line):
            inside = True
        elif inside and (m := re.match(r"^          ([\w-]+):[ \t]*(.*?)[ \t]*$", line)):
            env[m.group(1)] = m.group(2)
        elif inside and line.strip() and not line.startswith("          "):
            inside = False
    return env
