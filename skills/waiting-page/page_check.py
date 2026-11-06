#!/usr/bin/env python3
"""The one home that runs the waiting page's picture check (skill waiting-page, rule page-item-design).

`run_check_designs` starts skills/waiting-page/check_designs.mjs, which runs the page's own `pictureProblem` in Chromium, so
the sentence a miss quotes is the page's. hooks/guard.py (the write of an item) and export_page.py (the export, and --check)
both call it here. `check_items` picks the fetched items that carry a picture and that the page draws as open decisions, and
runs the check on each.

Cost: one node and one Chromium start per pictured open item. No git, no network, no timer.
"""
import json
import os
import re
import shutil
import subprocess  # TimeoutExpired only; the child starts through _nowindow
import sys
import time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(HERE, "..", "..", "hooks"))
sys.path.append(os.path.join(os.path.expanduser("~"), ".claude", "hooks"))

CHECK_DESIGNS = "check_designs.mjs"
CHECK_DESIGNS_CAP = 25  # seconds for one run; the checker caps itself at 20
CHECK_BUDGET = 100  # seconds for every item of one export or --check run


def run_check_designs(page_file, item, cap=CHECK_DESIGNS_CAP):
    """(code, text) from the checker on `item` (a dict) against `page_file`: code 0 pass, 1 miss with the page's
    sentence as text, 3 unknown with the reason as text. The one place that starts node."""
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
        try:
            run = _nowindow.run([node, script, "--page", page_file, "--item", item_file],
                                capture_output=True, text=True, timeout=cap)
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


def answered_on_page(item, answers):
    """True when the page draws `item` as answered. Mirrors page.html `isAnswered` for an open item: `isSaved` (an answers
    record under its id; `isRuling` items are closed, so never reach here) or `isByWait` (`answeredByWait`: valid `waitsOf`
    and a `lastOf` object). The page's `state.changing` is a click in the browser, so it is not read here."""
    if item.get("id") in answers:
        return True
    waits, last = item.get("waits"), item.get("lastAnswer")
    if not isinstance(last, dict) or not isinstance(waits, dict) or not isinstance(waits.get("repo"), str):
        return False
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", waits["repo"]):
        return False

    def num(value):  # page.html waitsOf `num`
        return (isinstance(value, int) and not isinstance(value, bool) and value > 0) or (
            isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value) is not None)
    return num(waits.get("run")) or num(waits.get("pr"))


def check_items(page_file, items, answers):
    """([(n, sentence)], why) for the fetched `items` and `answers` ({doc id: doc}) against `page_file`. Only an item that
    carries a picture (hooks/question_form.py design_writes, the one home of that test) and that the page draws as an open
    decision is run: design_writes drops a closed item, so a ruling (page.html `isRuling`: closed and arbiter) and any closed
    item are skipped, and answered_on_page drops an answered one. `why` is the first reason a run was unknown, else None.
    One item's unknown never hides another's hold."""
    try:
        import question_form
    except Exception as err:
        return [], "the picture test is not found (%s)" % type(err).__name__
    pictured = []
    for doc_id, doc in sorted(items.items()):
        if not isinstance(doc, dict):
            continue
        item = dict(doc, id=doc_id)  # the page keys an item on its database key, not on its id field
        if question_form.design_writes([("set", {"doc_id": doc_id, "data": item})]) and not answered_on_page(item, answers):
            pictured.append(item)
    held, why = [], None
    deadline = time.monotonic() + CHECK_BUDGET
    for done, item in enumerate(pictured):
        left = deadline - time.monotonic()
        if left < 1:
            why = why or "the %d s budget is spent, %d item(s) not checked" % (CHECK_BUDGET, len(pictured) - done)
            break
        try:
            code, text = run_check_designs(page_file, item, min(CHECK_DESIGNS_CAP, left))
        except Exception as err:
            code, text = 3, type(err).__name__ + ": " + str(err)
        if code == 1:
            n = item.get("n") if isinstance(item.get("n"), int) else item["id"]
            held.append((n, " ".join(text.split())))
        elif code != 0:
            why = why or " ".join(text.split())[:200]
    return held, why
