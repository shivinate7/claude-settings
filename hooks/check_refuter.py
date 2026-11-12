#!/usr/bin/env python3
"""The check refuter: the one home of the blind read of a lane brief's Done check line (owner word "refuter").

hooks/call_judge.py calls it for a send_message whose first non-blank line carries the lane brief marker
(shared_names.LANE_BRIEF_MARKER). The refuter sees three lines only: the step's title and why, read from the record at
refs/remotes/origin/<record branch>, and the brief's Done check line. It is asked whether the check could pass while
the ask stays unmet. It never sees the brief body or the step's note, so the check is judged against the ask alone.

Cost: one model call through decision_watch.invoke_model (the one model caller) per lane brief, and one `git show`
of the local ref. No other message reaches this module. Standard library plus decision_watch and lint/layout.py.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
LINT = os.path.join(HERE, "..", "lint")
if LINT not in sys.path:
    sys.path.append(LINT)

import _nowindow  # noqa: E402
import decision_watch  # noqa: E402  the one model caller

# The one named setting; lane debate-model-tiers may change it. REFUTER_TIMEOUT stays under the call_judge hook's
# "timeout": 70 in settings.json, so the call ends before the hook does and its refusal is the verdict.
REFUTER_MODEL = "sonnet"
REFUTER_EFFORT = None  # the model's default effort, as the judges in call_judge.py pass
REFUTER_TIMEOUT = 45
GIT_TIMEOUT = 10  # the one git read; REFUTER_TIMEOUT + GIT_TIMEOUT stays under the hook's 70 s too

REFUTER_PROMPT = (
    "You read one line blind. A lane was asked to do the work below, and its brief ends with a Done check line: "
    "the check that will say the work is done. You see only the step's title, why, and that check line.\n"
    "Could the check pass while the ask stays unmet? Flag only a realistic case: one where a worker who follows the "
    "brief in good faith could still pass the check with the ask unmet. Ignore a gap that only deliberate cheating "
    "would use. Answer {\"verdict\": \"FLAG\", \"why\": \"<the realistic case: one concrete way the check passes "
    "with the ask unmet, one or two sentences>\"} when there is one. Answer "
    "{\"verdict\": \"ALLOW\"} when a pass of the check means the ask is met. Judge only the check against the ask. "
    "Reply JSON only.\n\nTitle: %s\nWhy: %s\nDone check: %s\n"
)
STEP_PATH = "roadmap/data/steps/%s.json"
# A Done check line at a line start: plain, bold (`**Done check:**`, `**Done check**:`), a bullet, or with a label in
# parentheses (`Done check (proof):`), in any case.
_DONE_LINE = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\**Done check\**(?:[ \t]*\([^)\n]*\))?[ \t]*:\**[ \t]*(?P<text>.*)$",
                        re.IGNORECASE)
_DONE_HEADING = re.compile(r"^[ \t]*#+[ \t]+Done check[ \t]*:?[ \t]*#*[ \t]*$", re.IGNORECASE)
_FENCE = re.compile(r"^[ \t]*(```|~~~)")
_PLACEHOLDER = re.compile(r"<[^<>]*>")
_STEP_ID = re.compile(r"[A-Za-z0-9_-]+")


def done_check_line(brief):
    """The text of the first Done check line of `brief` outside a fenced block, or None. A `## Done check` heading
    gives the next non-blank line."""
    if not isinstance(brief, str):
        return None
    fence = None  # the opener of the fenced block the scan is inside
    lines = brief.splitlines()
    for number, line in enumerate(lines):
        opener = _FENCE.match(line)
        if opener:
            fence = None if fence == opener.group(1) else (fence or opener.group(1))
            continue
        if fence:
            continue
        found = _DONE_LINE.match(line)
        if found:
            return found.group("text").strip().strip("*").strip() or None
        if _DONE_HEADING.match(line):
            following = next((v.strip() for v in lines[number + 1:] if v.strip()), "")
            return following.strip("*").strip() or None
    return None


def is_placeholder(check):
    """True for a check that is only a `<...>` placeholder, the brief template's unfilled line."""
    return isinstance(check, str) and _PLACEHOLDER.fullmatch(check.strip()) is not None


def fetch_hint(branch="<record branch>"):
    """The fetch command an unreadable step names: the one remedy for a ref that is missing or stale. With no checkout
    the record branch is unknown, so the placeholder stands for it."""
    return ("If the record branch is not fetched or is stale, run: git fetch origin +refs/heads/%s:refs/remotes/origin/%s"
            % (branch, branch))


def ask_for_step(root, step):
    """(title, why) of roadmap step `step`, read from the local ref refs/remotes/origin/<record branch> of the repo at
    `root`. Raises when the ref, the file or a field is missing, so a caller reads it as unknown. Each of those reasons
    names the fetch command, since a fetch of the record branch is the remedy for all of them."""
    import layout  # lint/layout.py, the one home of the record branch
    if not isinstance(step, str) or not _STEP_ID.fullmatch(step):
        raise ValueError("step %r is not a step id" % (step,))
    branch = layout.record_branch(root)
    ref = "refs/remotes/origin/%s" % branch
    run = _nowindow.run(["git", "show", "%s:%s" % (ref, STEP_PATH % step)], cwd=root, capture_output=True,
                        timeout=GIT_TIMEOUT)
    if run.returncode != 0:
        raise ValueError("git show %s failed: %s. %s" % (ref, run.stderr.decode("utf-8", "replace").strip()[:200],
                                                         fetch_hint(branch)))
    try:
        data = json.loads(run.stdout.decode("utf-8", "replace"))
    except ValueError as exc:
        raise ValueError("step %s on %s is not valid JSON (%s). %s" % (step, ref, exc, fetch_hint(branch)))
    title, why = (data.get("title"), data.get("why")) if isinstance(data, dict) else (None, None)
    if not all(isinstance(v, str) and v.strip() for v in (title, why)):
        raise ValueError("step %s on %s has no title or no why. %s" % (step, ref, fetch_hint(branch)))
    return title, why


def refute(title, why, check):
    """(verdict, case): ("met", "") when the model finds no gap, ("gap", its case) when it does, and ("unknown",
    why) on an error or an odd answer. Never "met" unless the model said ALLOW."""
    try:
        answer, error = decision_watch.invoke_model(
            REFUTER_PROMPT % (title, why, check), model=REFUTER_MODEL, timeout=REFUTER_TIMEOUT,
            shape=decision_watch.VERDICT_SHAPE, effort=REFUTER_EFFORT)
    except Exception as exc:
        return "unknown", "the model call raised %s: %s" % (type(exc).__name__, exc)
    if error:
        return "unknown", " ".join(str(error).split())
    verdict = answer.get("verdict") if isinstance(answer, dict) else None
    if verdict == "ALLOW":
        return "met", ""
    if verdict == "FLAG":
        case = answer.get("why")
        return "gap", case.strip() if isinstance(case, str) and case.strip() else "the model named no case"
    return "unknown", "the model's answer has no verdict"
