#!/usr/bin/env python3
"""Fails when a step note claims an owner pick that the page did not record. Stdlib only.

    python3 lint/check_pick_claims.py --steps <steps dir> --answers <answers file>

Reads two things and nothing else:
  steps    the roadmap's step json files (one per step, slug = file stem). A step's `note` may say
           "Owner picked b on item 279", "... on page item 279", or "Owner picked 279 b on the page".
  answers  one JSON file, {"read": <ISO time with offset>, "answers": {"<item n>": <choice, list of choices, or null>}}.
           A multi-choice item holds a list; a claim matches when its key is in the list.

The page's database is the one store of the owner's answers. The check never reads a git copy of the page, so a
session must feed it the page:
  1. read the page's items with ArtifactData: each item's `n` and its answer choice (null when unanswered);
  2. write them to a file in the shape above, `read` set to the time of the read;
  3. run this check with --steps on the roadmap's steps folder and --answers on that file.
The answers path is required: no path is built in.

Findings:
  mismatch    the page recorded a different choice than the note claims
  unrecorded  the page has no answer for the item (absent or null)

A sentence that says "in chat" claims no page answer and is skipped.

Exit 0 clean, 1 findings, 2 unknown: a file could not be read, or an input is not in the shape above (an answers
file, a steps folder with no step json, a step file that is not an object, a note that is not text).
Unknown is never clean, because a check that could not read the page proves nothing about the notes.
A clean line prints the answers' read time, so a reader sees how old the page copy is.
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

KEY = r"([a-z])(?![A-Za-z0-9])"
LABEL = r"(?:\s+(?:\"[^\"]*\"|“[^”]*”))?"
# Two forms: "picked KEY [label] on [page] item N" and "picked N KEY". The item number is what ties a claim to the
# page, so a pick with no number (and "until item N picks") matches neither. A time in parentheses follows the
# claim and is never part of it.
# The noun "owner pick" counts too, but "picks" never does: it is a future or conditional pick, not a recorded one.
CLAIM = re.compile(
    r"\bowner\s+(picked|pick(?![A-Za-z]))\s+(?:" + KEY + LABEL + r"\s+on\s+(?:page\s+)?item\s+(\d+)\b|(\d+)\s+" + KEY + r")",
    re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
IN_CHAT = re.compile(r"\bin\s+chat\b", re.IGNORECASE)
IF_WORD = re.compile(r"\bif\b", re.IGNORECASE)


class Unknown(Exception):
    """An input could not be read, so the notes are not known to match the page."""


class Finding:
    def __init__(self, kind, slug, item, key, page, text):
        self.kind, self.slug, self.item, self.key, self.page, self.text = kind, slug, item, key, page, text

    def __repr__(self):
        return "Finding(%s, %s, item %d, claimed %s, page %r)" % (self.kind, self.slug, self.item, self.key, self.page)

    def line(self):
        if self.kind == "mismatch":
            return "mismatch: %s says \"%s\"; the page recorded %s" % (self.slug, self.text, _show(self.page))
        return "unrecorded: %s says \"%s\"; the page has no answer for item %d" % (self.slug, self.text, self.item)


def _sentence(note, m):
    """(start, end) of the sentence that holds match `m`."""
    start = 0
    for e in SENTENCE_END.finditer(note, 0, m.start()):
        start = e.end()
    e = SENTENCE_END.search(note, m.end())
    return start, (e.end() if e else len(note))


def _scan(note):
    """(item, key, matched text) for each claim in `note` that names the page."""
    found = []
    for m in CLAIM.finditer(note):
        verb, key1, item1, item2, key2 = m.groups()
        start, end = _sentence(note, m)
        if IN_CHAT.search(note, start, end):
            continue  # an answer given in chat was never on the page
        if verb.lower() == "pick" and IF_WORD.search(note, start, m.start()):
            continue  # "if the owner pick ..." is a condition, not a record
        found.append((int(item1 or item2), (key1 or key2).lower(), m.group(0)))
    return found


def claims(note):
    """[(item, key)] for each owner pick that `note` claims."""
    return [(item, key) for item, key, _ in _scan(note)]


def _load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise Unknown("%s could not be read: %s (%s)" % (what, path, e))


def _read_answers(path):
    doc = _load_json(path, "the answers file")
    if not isinstance(doc, dict):
        raise Unknown("the answers file is not a JSON object: %s" % path)
    stamp = doc.get("read")
    try:
        when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise Unknown("the answers file has no ISO read time: %s" % path)
    if when.tzinfo is None:
        raise Unknown("the answers file's read time has no offset: %s" % path)
    answers = doc.get("answers")
    if not isinstance(answers, dict):
        raise Unknown("the answers value is not an object: %s" % path)
    for n, choice in answers.items():
        listed = isinstance(choice, list) and all(isinstance(c, str) for c in choice)
        if choice is not None and not isinstance(choice, str) and not listed:
            raise Unknown("item %s has a choice that is not text, a list of text, or null: %s" % (n, path))
    return stamp, answers


def _read_notes(steps_dir):
    """[(slug, note)] in slug order, for each step json that has a text note."""
    if not os.path.isdir(steps_dir):
        raise Unknown("the steps folder is not a folder: %s" % steps_dir)
    paths = sorted(glob.glob(os.path.join(steps_dir, "*.json")))
    if not paths:
        raise Unknown("the steps folder has no step json: %s" % steps_dir)  # a wrong folder must not pass as clean
    notes = []
    for path in paths:
        step = _load_json(path, "a step file")
        if not isinstance(step, dict):
            raise Unknown("a step file is not a JSON object: %s" % path)
        note = step.get("note")
        if note is None:
            continue
        if not isinstance(note, str):
            raise Unknown("a step's note is not text: %s" % path)
        notes.append((os.path.splitext(os.path.basename(path))[0], note))
    return notes


def _show(choice):
    return "[%s]" % ", ".join(choice) if isinstance(choice, list) else str(choice)


def _findings(steps_dir, recorded):
    findings = []
    for slug, note in _read_notes(steps_dir):
        for item, key, text in _scan(note):
            page = recorded.get(str(item))
            if page is None:
                findings.append(Finding("unrecorded", slug, item, key, None, text))
                continue
            held = [c.lower() for c in page] if isinstance(page, list) else [page.lower()]
            if key not in held:
                findings.append(Finding("mismatch", slug, item, key, page, text))
    return findings


def check(steps_dir, answers):
    """Findings for each claim whose item the page did not record with that choice. `answers` is a file path."""
    return _findings(steps_dir, _read_answers(answers)[1])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail when a step note claims an owner pick the page did not record.")
    ap.add_argument("--steps", required=True, help="folder of step json files")
    ap.add_argument("--answers", required=True, help="answers file a session wrote from the page")
    args = ap.parse_args(argv)
    try:
        stamp, recorded = _read_answers(args.answers)
        findings = _findings(args.steps, recorded)
    except Unknown as e:
        print("unknown: %s" % e)
        return 2
    for f in findings:
        print(f.line())
    if findings:
        print("%d pick claim(s) do not match the page (answers read %s)" % (len(findings), stamp))
        return 1
    print("pick claims match the page (answers read %s)" % stamp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
