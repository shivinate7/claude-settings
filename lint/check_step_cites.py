#!/usr/bin/env python3
"""The pure scan of `step:<slug>` cites, for merge --lane-lint (merge/merge.py, lane_lint). Standard library only.

cites(text) -> the sorted unique slugs one text cites. missing(texts, known) -> the sorted slugs the texts cite that `known` lacks, each once.
A cite is MISTAKE_STEP_RE's match (lint/report_guard.py, the one home of the cite form), in inline code or bare prose. A row inside a fenced
block is no cite (stale_cites.fenced_lines, the one home of the fence rule). A placeholder such as `step:<slug>` and prose such as
"next step: foo" match nothing. Cost: one pass over the texts; no git, no file, no process.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from report_guard import MISTAKE_STEP_RE  # noqa: E402  the one home of the cite form
from stale_cites import fenced_lines  # noqa: E402  the one home of the fence rule


def cites(text):
    rows = text.replace("\r\n", "\n").split("\n")
    fenced = fenced_lines(rows)
    found = set()
    for number, row in enumerate(rows, 1):
        if number not in fenced:
            found.update(m.group(0)[len("step:"):] for m in MISTAKE_STEP_RE.finditer(row))
    return sorted(found)


def missing(texts, known):
    return sorted({slug for text in texts for slug in cites(text)} - set(known))
