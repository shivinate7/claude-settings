"""Read a GitHub workflow's jobs and steps by line, stdlib only: no YAML library on a fresh runner or Mac.

The one home of the step parser. lint/test_windows_split.py reads the Windows split with it, and
bin/ci-job runs a job's steps locally with it. It reads the layout checks.yml keeps: jobs at 2 spaces,
`      - ` steps, step keys at 8 spaces, `env:` keys and `run: |` bodies at 10.
"""
import os
import re

# The Linux jobs that hold the suites of the one old `checks` job, split for wall time. merge/merge.py reads suites from each.
CHECKS_SUITE_JOBS = ("checks", "checks-merge-install")


def job_block(text, name):
    """Raw text of one job: from its `  name:` line to the next job line. None when the job is absent."""
    m = re.search(rf"^  {re.escape(name)}:\s*$(.*?)(?=^  [\w-]+:\s*$|\Z)", text, re.M | re.S)
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


def step_map(step, key):
    """A step's own `key:` block (`env:` or `with:`) as {name: raw value}, or {} when it has none."""
    found, inside = {}, False
    for line in step.split("\n"):
        if re.match(rf"^(?:      - |        ){re.escape(key)}:[ \t]*$", line):
            inside = True
        elif inside and (m := re.match(r"^          ([\w-]+):[ \t]*(.*?)[ \t]*$", line)):
            found[m.group(1)] = m.group(2)
        elif inside and line.strip() and not line.startswith("          "):
            inside = False
    return found


def step_env(step):
    """A step's own `env:` block as {name: raw value}, or {} when it has none."""
    return step_map(step, "env")


def step_with(step):
    """A step's own `with:` block as {name: raw value}, or {} when it has none."""
    return step_map(step, "with")
