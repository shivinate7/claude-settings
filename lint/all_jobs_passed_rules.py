#!/usr/bin/env python3
"""The one home of the all-jobs-passed wiring rules. lint/test_all_jobs_passed.py runs them on checks.yml.

The cs rules (all_problems) check .github/workflows/checks.yml. The child rules (child_problems) check a child
repo's workflow that pins the shared action. They need no scope job, no ci-done and no checkout step.

A child job's own if decides whether it blocks a PR, so a push-only job stays out of needs.

Stdlib only, no PyYAML. Check a child workflow with:
python3 lint/all_jobs_passed_rules.py --workflow PATH
It prints each problem. It exits 1 on any problem, 0 when clean, and 2 when the file cannot be read.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_windows_split import (ALL_JOBS_PASSED_JOB, MACOS_JOBS, NIGHTLY_SKIP_JOB, all_jobs, eval_if, push_guard_only,  # noqa: E402  the one home of the scope condition and scalar parsers
                                schedule_only, shard_base, yaml_scalar)
from workflow_steps import job_block, step_blocks, step_key  # noqa: E402  the one home of the step parser

ALL_JOBS_PASSED_USES = "$/actions/all-jobs-passed"
ALL_JOBS_PASSED_IF = "${{ always() && github.event_name == 'pull_request' && !github.event.pull_request.draft }}"
ALL_JOBS_PASSED_RUNS_ON = "ubuntu-latest"
TO_JSON = "${{ toJSON(needs) }}"
FAN_IN = "ci-done"  # comments on a red run; it needs all-jobs-passed, and all-jobs-passed never needs it
CHECKOUT_PIN = re.compile(r"actions/checkout@[0-9a-f]{40}")
STEP_KEYS_BARRED = ("if", "continue-on-error")  # either one lets a failed needed job leave the action step green
REMOTE_ACTION = "shivinate7/claude-settings/actions/all-jobs-passed"  # how a child repo names the shared action
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


def job_key(block, key):
    """A job-level key's value (4 spaces under the job), comment removed, or None when the job lacks the key."""
    m = re.search(rf"^    {re.escape(key)}:[ \t]*(.*?)[ \t]*$", block or "", re.M)
    return yaml_scalar(m.group(1)) if m else None


def steps_part(block):
    """A job block from its `steps:` key (a trailing comment allowed) on, so a block-list needs is never read as steps."""
    m = re.search(r"^    steps:[ \t]*(?:#.*)?$", block or "", re.M)
    return block[m.end():] if m else ""


def step_with(step, key):
    """A step's `with:` value (10 spaces under the step), comment removed, or None."""
    m = re.search(rf"^          {re.escape(key)}:[ \t]*(.*?)[ \t]*$", step, re.M)
    return yaml_scalar(m.group(1)) if m else None


def needs_of(block):
    """The job names a job block needs: a flow list (on one line or several), one scalar, or a block list whose items sit at
    the key's indent or deeper. It stops at the first line that is not an item, such as the next key. Comment lines are
    skipped. None when the block has no needs key."""
    m = re.search(r"^    needs:[ \t]*(.*?)[ \t]*$", block or "", re.M)
    if not m:
        return None
    inline = yaml_scalar(m.group(1))
    if inline.startswith("["):
        flow = inline
        if "]" not in flow:
            for line in block[m.end():].split("\n")[1:]:
                flow += " " + yaml_scalar(line)
                if "]" in line:
                    break
        return [yaml_scalar(n) for n in flow.split("]")[0].lstrip("[").split(",") if n.strip()]
    if inline:
        return [inline]
    names = []
    for line in block[m.end():].split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^ {4,}- (.*)$", line)
        if not item:
            break
        names.append(yaml_scalar(item.group(1)))
    return names


def split_jobs(text):
    """(needed, off, problems) over the jobs of checks.yml. A job is off all-jobs-passed when its job-level if is false on a
    non-draft pull_request with every scope flag true. all-jobs-passed and ci-done are neither needed nor off."""
    needed, off, problems = [], [], []
    for name, job in all_jobs(text).items():
        if name in (ALL_JOBS_PASSED_JOB, FAN_IN):
            continue
        if job["if"] is None:
            needed.append(name)
            continue
        try:
            on = eval_if(yaml_scalar(job["if"]), "pull_request", "true")
        except Exception as ex:  # an if this reader cannot evaluate counts as needed, and is named
            problems.append(f"{name}: job-level if is unreadable ({ex!r}): {job['if']}")
            on = True
        (needed if on else off).append(name)
    return sorted(needed), sorted(off), problems


def shape_problems(text):
    """The all-jobs-passed job: no name (its job key is the required check's name), ubuntu-latest, a timeout, and the exact if."""
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in checks.yml"]
    problems = []
    if re.search(r"^    name:", block, re.M):
        problems.append(f"{ALL_JOBS_PASSED_JOB} sets name:, but its job key is the required check's name")
    if job_key(block, "runs-on") != ALL_JOBS_PASSED_RUNS_ON:
        problems.append(f"{ALL_JOBS_PASSED_JOB} runs on {job_key(block, 'runs-on')}, want {ALL_JOBS_PASSED_RUNS_ON}")
    if not (job_key(block, "timeout-minutes") or "").isdigit():
        problems.append(f"{ALL_JOBS_PASSED_JOB} has no timeout-minutes number: {job_key(block, 'timeout-minutes')!r}")
    if job_key(block, "if") != ALL_JOBS_PASSED_IF:
        problems.append(f"{ALL_JOBS_PASSED_JOB} if is {job_key(block, 'if')}, want {ALL_JOBS_PASSED_IF}")
    return problems


def needs_problems(text):
    """all-jobs-passed needs each job that runs on a non-draft PR once, and nothing else: not a shard, not ci-done."""
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in checks.yml"]
    needed, _, problems = split_jobs(text)
    got = needs_of(block)
    if got is None:
        return problems + [f"{ALL_JOBS_PASSED_JOB} has no needs key"]
    if not needed:
        problems.append("the reader derived no needed job: an empty match would prove nothing")
    if FAN_IN in got:
        problems.append(f"{ALL_JOBS_PASSED_JOB} needs {FAN_IN}, which needs it: a cycle")
    if len(set(got)) != len(got):
        problems.append(f"{ALL_JOBS_PASSED_JOB} lists a job twice: {sorted(got)}")
    if sorted(set(got)) != needed:
        problems.append(f"{ALL_JOBS_PASSED_JOB} needs differ from the jobs that run on a PR: "
                        f"missing {sorted(set(needed) - set(got))}, extra {sorted(set(got) - set(needed))}")
    return problems


def step_key_problems(step):
    """The action step may not set its own if or continue-on-error: a failed needed job would otherwise read green."""
    return [f"the action step sets {key}:, so a failed needed job could read green"
            for key in STEP_KEYS_BARRED if step_key(step, key) is not None]


def steps_problems(text):
    """all-jobs-passed's steps in order: a checkout pinned to a commit with persist-credentials false, then the action fed
    toJSON(needs)."""
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in checks.yml"]
    steps = step_blocks(steps_part(block))
    if len(steps) != 2:
        return [f"{ALL_JOBS_PASSED_JOB} has {len(steps)} steps, want 2: a pinned checkout, then the action"]
    checkout, fan = steps
    problems = []
    uses = yaml_scalar(step_key(checkout, "uses") or "")
    if not CHECKOUT_PIN.fullmatch(uses):
        problems.append(f"all-jobs-passed's checkout is not pinned to a commit: {uses!r}")
    if step_with(checkout, "persist-credentials") != "false":
        problems.append("all-jobs-passed's checkout keeps its token: persist-credentials must be false")
    if yaml_scalar(step_key(fan, "uses") or "") != ALL_JOBS_PASSED_USES:
        problems.append(f"the second step uses {step_key(fan, 'uses')}, want {ALL_JOBS_PASSED_USES}")
    if step_with(fan, "needs") != TO_JSON:
        problems.append(f"the action gets needs {step_with(fan, 'needs')!r}, want {TO_JSON}")
    problems += step_key_problems(fan)
    return problems


def off_problems(text):
    """Only a shard job, and the schedule-only nightly skip job, may stay off all-jobs-passed. A needed job has no job-level if,
    except scope (its draft rule) and a macOS job (the push guard)."""
    jobs = all_jobs(text)
    needed, off, problems = split_jobs(text)
    for name in off:
        if name == NIGHTLY_SKIP_JOB and schedule_only(jobs[name]["if"]):  # R61 part 3: the skip job runs on a schedule only
            continue
        if not shard_base(name):
            problems.append(f"{name} is off all-jobs-passed but is not a shard: its job-level if skips it on a PR")
    for name in needed:
        if shard_base(name):
            problems.append(f"shard {name} is in all-jobs-passed's needs: a shard runs only off pull_request")
        elif name in MACOS_JOBS and push_guard_only(jobs[name]["if"] or ""):
            continue  # R61 part 1: the push guard is true on a PR, so the macOS job stays needed and runs there
        elif name != "scope" and jobs[name]["if"] is not None:
            problems.append(f"{name} is needed and keeps a job-level if: all-jobs-passed reads its skip as red, "
                            "so its scope condition belongs in its steps")
    return problems


def scope_if_problems(text):
    """scope skips a draft PR and runs everywhere else, so all-jobs-passed (which needs it) is skipped on a draft only."""
    job = all_jobs(text).get("scope")
    if job is None or job["if"] is None:
        return ["scope has no if: a draft PR would run every job"]
    expr = yaml_scalar(job["if"])
    try:
        problems = []
        if not eval_if(expr, "pull_request", "true", draft=False):
            problems.append("scope skips a ready PR")
        if eval_if(expr, "pull_request", "true", draft=True):
            problems.append("scope runs on a draft PR")
        if not eval_if(expr, "push", "false"):
            problems.append("scope skips a push")
        return problems
    except Exception as ex:
        return [f"scope if is unreadable ({ex!r}): {expr}"]


def ci_done_problems(text):
    """ci-done needs all-jobs-passed, so a red all-jobs-passed posts the comment."""
    block = job_block(text, FAN_IN)
    if block is None:
        return [f"no {FAN_IN} job in checks.yml"]
    if ALL_JOBS_PASSED_JOB not in (needs_of(block) or []):
        return [f"{FAN_IN} does not need {ALL_JOBS_PASSED_JOB}: a red all-jobs-passed would post no comment"]
    return []


def all_problems(text):
    return (shape_problems(text) + needs_problems(text) + steps_problems(text) + off_problems(text)
            + scope_if_problems(text) + ci_done_problems(text))


def child_if_problems(block):
    """A child's all-jobs-passed if, judged by meaning: true on a ready PR, false on a draft PR and on a push, and holds
    always(). Without always() GitHub skips the job when a needed job fails, and a skipped required check reads green."""
    raw = job_key(block, "if")
    if not raw:
        return [f"{ALL_JOBS_PASSED_JOB} has no if: without always() a red needed job would skip it, and a skip reads green"]
    problems = []
    if not re.search(r"\balways\(\)", raw):
        problems.append(f"{ALL_JOBS_PASSED_JOB} if lacks always(): GitHub skips it when a needed job fails, and a skip reads green")
    try:
        if not eval_if(raw, "pull_request", "true", draft=False):
            problems.append(f"{ALL_JOBS_PASSED_JOB} if is false on a ready pull_request")
        if eval_if(raw, "pull_request", "true", draft=True):
            problems.append(f"{ALL_JOBS_PASSED_JOB} if is true on a draft pull_request")
        if eval_if(raw, "push", "false"):
            problems.append(f"{ALL_JOBS_PASSED_JOB} if is true on a push")
    except Exception as ex:
        problems.append(f"{ALL_JOBS_PASSED_JOB} if is unreadable ({ex!r}): {raw}")
    return problems


def child_action_problems(block):
    """One step uses the shared action at a 40-hex commit, fed toJSON(needs). A tag or branch can move, so it is red."""
    uses = [(yaml_scalar(step_key(st, "uses") or ""), st) for st in step_blocks(steps_part(block))]
    ours = [(u, st) for u, st in uses if u.partition("@")[0] == REMOTE_ACTION]
    if len(ours) != 1:
        return [f"{ALL_JOBS_PASSED_JOB} has {len(ours)} steps that use {REMOTE_ACTION}, want 1"]
    ref, step = ours[0][0].partition("@")[2], ours[0][1]
    problems = []
    if not COMMIT_SHA.fullmatch(ref):
        problems.append(f"{REMOTE_ACTION} is pinned to {ref!r}, want a 40-hex commit: a tag or branch can move")
    if step_with(step, "needs") != TO_JSON:
        problems.append(f"the action gets needs {step_with(step, 'needs')!r}, want {TO_JSON}")
    return problems + step_key_problems(step)


def child_problems(text):
    """The generic rules for a child repo's workflow that pins the shared action."""
    text = text.replace("\r\n", "\n")  # the readers match on LF line ends
    block = job_block(text, ALL_JOBS_PASSED_JOB)
    if block is None:
        return [f"no {ALL_JOBS_PASSED_JOB} job in the workflow"]
    return child_if_problems(block) + needs_problems(text) + child_action_problems(block)


def check_workflow(path):
    """Print each child problem. Exit 1 on any, 0 when clean, 2 when the file cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as ex:
        print(f"cannot read {path}: {ex}")
        sys.exit(2)
    problems = child_problems(text)
    for problem in problems:
        print(problem)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--workflow":
        print("usage: all_jobs_passed_rules.py --workflow PATH")
        sys.exit(2)
    check_workflow(sys.argv[2])
