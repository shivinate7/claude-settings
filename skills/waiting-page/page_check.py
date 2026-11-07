#!/usr/bin/env python3
"""The one home that runs the waiting page's picture check (skill waiting-page, rule page-item-design).

`run_check_designs` starts skills/waiting-page/check_designs.mjs, which runs the page's own `pictureProblem` in Chromium, so
the sentence a miss quotes is the page's. hooks/guard.py (the write of an item) and export_page.py (the export, and --check)
both call it here. `check_items` picks the fetched items that carry a picture and that are not closed or rulings, and runs the
check on each, with the fetched answers: the page's own `isAnswered` skips an answered item, so no copy of it lives here.

Cost: one node and one Chromium start per pictured open item. No git, no network, no timer.
"""
import json
import os
import shutil
import subprocess  # TimeoutExpired only; the child starts through _nowindow
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(HERE, "..", "..", "hooks"))
sys.path.append(os.path.join(os.path.expanduser("~"), ".claude", "hooks"))

CHECK_DESIGNS = "check_designs.mjs"
CHECK_DESIGNS_CAP = 25  # seconds for one run; the checker caps itself at 20


def run_check_designs(page_file, item, cap=CHECK_DESIGNS_CAP, answers=None):
    """(code, text) from the checker on `item` (a dict) against `page_file`: code 0 pass, 1 miss with the page's
    sentence as text, 3 unknown with the reason as text. `answers` ({doc id: doc}) goes to the checker as --answers, so the
    page's own `isAnswered` decides; None passes none (the guard: every verdict stays). The one place that starts node."""
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
    import tempfile
    node = shutil.which("node")
    script = os.path.join(HERE, CHECK_DESIGNS)
    if node is None or not os.path.isfile(script):
        return 3, "node is not installed" if node is None else CHECK_DESIGNS + " not found"
    with tempfile.TemporaryDirectory() as scratch:
        item_file = os.path.join(scratch, "item.json")
        with open(item_file, "w", encoding="utf-8") as handle:
            json.dump(item, handle)
        command = [node, script, "--page", page_file, "--item", item_file]
        if answers is not None:
            answers_file = os.path.join(scratch, "answers.json")
            with open(answers_file, "w", encoding="utf-8") as handle:
                json.dump(answers, handle)
            command += ["--answers", answers_file]
        try:
            run = _nowindow.run(command, capture_output=True, text=True, timeout=cap)
        except subprocess.TimeoutExpired:
            return 3, "no answer in %d s" % cap
        except OSError as err:
            return 3, str(err.strerror or err)
    lines = run.stdout.strip().splitlines()
    try:
        problem = json.loads(lines[-1]).get("problem") if lines else None
    except ValueError:
        return 3, "no answer line; exit %d" % run.returncode
    if run.returncode == 1 and isinstance(problem, str) and problem:
        return 1, problem
    if run.returncode == 0:
        return 0, ""
    return 3, (run.stderr.strip().splitlines() or ["exit %d" % run.returncode])[-1]


def pictured_items(items):
    """([item dicts], why) for the fetched `items` ({doc id: doc}): each that carries a picture (hooks/question_form.py
    design_writes, the one home of that test), which drops a closed item and so a ruling (page.html `isRuling`: closed and
    arbiter). `why` is the reason the test could not load, else None. Needs no page."""
    try:
        import question_form
    except Exception as err:
        return [], "the picture test is not found (%s)" % type(err).__name__
    pictured = []
    for doc_id, doc in sorted(items.items()):
        if not isinstance(doc, dict):
            continue
        item = dict(doc, id=doc_id)  # the page keys an item on its database key, not on its id field
        if question_form.design_writes([("set", {"doc_id": doc_id, "data": item})]):
            pictured.append(item)
    return pictured, None


def check_items(page_file, items, answers):
    """([(n, sentence)], why) for the fetched `items` and `answers` ({doc id: doc}) against `page_file`. Each pictured item
    (pictured_items) is run, with `answers`: the checker skips an item the page draws as answered, by the page's own
    `isAnswered`. `why` is the first reason a run was unknown, else None. One item's unknown never hides another's hold.
    No time budget spans the items: no hook timeout applies, and each run has its own cap."""
    pictured, why = pictured_items(items)
    held = []
    for item in pictured:
        try:
            code, text = run_check_designs(page_file, item, CHECK_DESIGNS_CAP, answers)
        except Exception as err:
            code, text = 3, type(err).__name__ + ": " + str(err)
        if code == 1:
            n = item.get("n") if isinstance(item.get("n"), int) else item["id"]
            held.append((n, " ".join(text.split())))
        elif code != 0:
            why = why or " ".join(text.split())[:200]
    return held, why
