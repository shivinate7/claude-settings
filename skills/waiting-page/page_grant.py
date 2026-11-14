#!/usr/bin/env python3
"""Say whether a page answer a session fetched is the owner's grant (skill waiting-page, "Read the answers" and "Route and close").

A receiving session reads the owner's answer itself and never trusts a peer's relay text. A script cannot call
ArtifactData, so the session makes a fetch folder, fetches into it, then runs this checker:

    python3 ~/.claude/skills/waiting-page/page_grant.py --new-fetch PARENT   (prints `fetch DIR`)
    ArtifactData get collection=answers doc_id=ID out_dir=DIR   (an absent doc saves no file)
    ArtifactData get collection=items   doc_id=ID out_dir=DIR
    python3 ~/.claude/skills/waiting-page/page_grant.py --root REPO_ROOT --page-url URL --item ID --fetched DIR [--pick KEY]

DIR holds `answers/ID.json` and `items/ID.json`, the data object of each doc. `--new-fetch` makes DIR empty and writes
the stamp `DIR.stamp` beside it, outside DIR. A check uses the stamp up (renames it `DIR.stamp.used`), so each fetch
folder is checked once. REPO_ROOT is the repo of the page; its
extras file holds the artifacts registry (lint/layout.py `artifacts()`). --pick is the pick the peer relayed: a key,
or `a+c` for a multi item; the page's choice must equal it exactly. A decision is never counted without it.

Verdict, one line on stdout, then exit:
  counted item=ID n=N choice=C at=T label=L [note=JSON]  exit 0. Choice of a multi item: keys joined by `+`.
                                                 L is the picked option's label as one JSON string, a JSON list of
                                                 labels for a multi item, or null for an overturn. It names the act.
  not counted: REASON                            exit 1. REASON names the failed rule.
  held: REASON                                   exit 3. The answer names an option the item no longer holds at that key;
                                                 the owner confirms in words. It is never a grant.
  unknown: REASON                                exit 2. No readable registry or waiting-page entry, a fetched file that is
                                                 not one JSON object, or a crash.
Counted only when all hold:
  1. Rule 2's stamp is used up first. Then --page-url is the same artifact (layout.artifact_id) as the registry's `waiting-page` entry.
  2. DIR came from this fetch: `--new-fetch` made it (its stamp names DIR), no check used it before, it holds nothing
     but answers/ID.json and items/ID.json, and no file in it is older than the stamp. A folder made by hand, a reused
     folder (an answer the owner withdrew stays in it, as a re-fetch of an absent doc saves no file), or a file copied
     with its old time (`cp -p`) is not counted. A plain copy gets a new time, so the checker cannot see it.
     A check uses the folder up first, so every verdict uses it up: a retry fetches again into a new folder.
     answers/ID.json and items/ID.json exist. Relay text alone never counts.
  3. The answer's `item` is --item (the item is read by its key, which is its id), and the answer's `n` is the item's `n`.
  4. The item is open: `status` is `open`, or absent (the page hides only `closed`, page.html `state.items`). A closed
     item takes no answer, except an arbiter ruling (`arbiter` true, written closed) answered `overturn`, and a routed
     close: `status` is `closed`, `lane` and `home` are strings non-empty after strip, `arbiter` is not true, and
     `lastAnswer.at` equals the answer's `at`. Routing closes the item at once and keeps `lastAnswer` and answers/ID.
  5. The answer's `at` is later than the item's `added`: an earlier answer belongs to an earlier ask. Both carry a
     time zone (`Z` or an offset); one without is not counted.
  6. A decision (`kind` absent or `decision`): `choice` is the key of one option, or `overturn` when the item's `arbiter`
     is true. `none` never counts: it asks for new options, and the routing session judges a direction. A `multi` item
     takes a non-empty list of distinct keys; a list on a pick-one item or a string on a multi item does not count.
  7. --pick is given and the choice equals it.
Held, not counted (ruling R60, decision option-keys-are-letters): an answer that names an option the item no longer holds
at that key. The line is `held: REASON`, exit 3, and the REASON says the owner confirms in words. It is judged after
rule 7, so a pick that differs from the choice stays `not counted`. It applies when:
  8. The answer carries `optionId` and it is not the id of the item's option at the choice key. With no `optionId`, a
     `label` ("A: Red") whose letter is not that option's position letter, or whose text is not that option's label.
     An answer with neither field is judged by its choice alone, as before.
  9. The choice is a key the item does not hold, and equals --pick (a letter that moved, or an option that was removed).
A task (`kind: task`) is never counted, with or without `done`: a task answer grants no act.

Cost: one python process per call. `--new-fetch` makes one folder and writes one stamp file. A check reads the extras
file, the stamp and two fetched files, and renames the stamp once. No git, no network, no timer.
"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))

COUNTED, NOT_COUNTED, UNKNOWN, HELD = 0, 1, 2, 3

# The check's flags, the command and the counted line. settings.json's "Relayed Grant" auto-mode entry quotes
# COMMAND and COUNTED_LINE; hooks/test_auto_mode_allow.py pins the entry to them. The parser and the printed line
# are built from these, so a renamed flag or a reworded line breaks that pin.
CHECK_FLAGS = (("--root", "<repo>", "repo root of the page (holds the extras file)"),
               ("--page-url", "<url>", "the page URL the session was given"),
               ("--item", "<id>", "the item id"),
               ("--fetched", "<dir>", "the --new-fetch folder with answers/<id>.json and items/<id>.json"),
               ("--pick", "<key>", "the pick a peer relayed: a key, or a+c for several"))
COMMAND = " ".join(["python3 ~/.claude/skills/waiting-page/page_grant.py"] +
                   ["%s %s" % (flag, value) for flag, value, _ in CHECK_FLAGS])
COUNTED_LINE = "counted item=<id> n=<n> choice=<key> at=<time> label=<label>"
STAMP, USED = ".stamp", ".stamp.used"


class Verdict(Exception):
    def __init__(self, line, code):
        super().__init__(line)
        self.line, self.code = line, code


def not_counted(reason):
    return Verdict("not counted: " + reason, NOT_COUNTED)


def unknown(reason):
    return Verdict("unknown: " + reason, UNKNOWN)


def held(reason):
    return Verdict("held: %s: the owner confirms in words which option he meant" % reason, HELD)


def load_layout():
    """lint/layout.py, from the repo that holds this script or from the installed ~/.claude layout."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "lint"))
    sys.path.insert(1, os.path.join(os.path.expanduser("~"), ".claude", "lint"))
    import layout
    return layout


def moment(text, what):
    """An ISO timestamp as an aware datetime; not counted when it is none or has no time zone."""
    if not isinstance(text, str):
        raise not_counted("%s is not a timestamp" % what)
    try:
        when = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        raise not_counted("%s is not an ISO timestamp" % what)
    if when.tzinfo is None:
        raise not_counted("%s has no time zone: write it with Z or an offset" % what)
    return when


def read_doc(fetched, collection, item_id):
    """The one JSON object in <fetched>/<collection>/<item_id>.json, or None when the file is absent."""
    path = os.path.join(fetched, collection, item_id + ".json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as err:
        raise unknown("%s is not readable JSON: %s" % (path, err))
    if not isinstance(doc, dict):
        raise unknown("%s is not one JSON object" % path)
    return doc


def new_fetch(parent):
    """Make an empty fetch folder under parent, and its stamp beside it; return the folder."""
    os.makedirs(parent, exist_ok=True)
    folder = os.path.realpath(tempfile.mkdtemp(prefix="page-grant-", dir=parent))
    with open(folder + STAMP, "x", encoding="utf-8") as handle:
        json.dump({"folder": folder}, handle)
    return folder


def use_stamp(fetched):
    """Use up the stamp of `fetched`, a --new-fetch folder no check used, and return (folder, stamp time). The first
    step of every check, so any verdict, even one for a wrong --root, URL or pick, uses the folder up."""
    folder = os.path.realpath(fetched)
    stamp = folder + STAMP
    if not os.path.isfile(stamp):
        if os.path.exists(folder + USED):
            raise not_counted("fetch folder already checked once: make a new one with --new-fetch and fetch again")
        raise not_counted("fetch folder has no stamp: make it with --new-fetch, then fetch into it")
    try:
        with open(stamp, encoding="utf-8") as handle:
            named = json.load(handle).get("folder")
    except (OSError, ValueError, AttributeError):
        named = None
    if named != folder:
        raise not_counted("stamp names another folder: make this one with --new-fetch, then fetch into it")
    os.replace(stamp, folder + USED)  # a rename keeps the stamp's mtime
    return folder, os.stat(folder + USED).st_mtime_ns


def prove_fresh(folder, made, item_id):
    """Not counted unless `folder` holds only this item's two docs, each no older than the stamp."""
    allowed = {"answers", "items", os.path.join("answers", item_id + ".json"), os.path.join("items", item_id + ".json")}
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, folder)
            if rel not in allowed or os.path.islink(path):
                raise not_counted("fetch folder holds %s: it holds only this item's answer and item" % json.dumps(rel))
            if name in filenames and os.stat(path).st_mtime_ns < made:
                raise not_counted("%s is older than the fetch folder: it came from an earlier fetch" % rel)


NO_KEY = ("none", "overturn")  # the choices that name no option


def option_keys(item):
    options = item.get("options")
    if not isinstance(options, list):
        return []
    return [opt["key"] for opt in options if isinstance(opt, dict) and isinstance(opt.get("key"), str)]


def choice_of(item, answer, pick=None):
    """The counted choice text of a decision or a task answer; not counted when the answer is no clear one."""
    kind = item.get("kind", "decision")
    if kind == "task":
        raise not_counted("item is a task: a task answer grants no act, done or not")
    if kind != "decision":
        raise not_counted("item kind %r is neither decision nor task" % (kind,))
    keys = option_keys(item)
    choice = answer.get("choice")
    if item.get("multi") is True:
        if not isinstance(choice, list):
            raise not_counted("item takes several options and the choice is not a list")
        if not choice:
            raise not_counted("choice is an empty list")
        if len(set(map(str, choice))) != len(choice):
            raise not_counted("choice repeats a key")
        bad = [c for c in choice if not (isinstance(c, str) and c in keys)]
        if bad and pick == "+".join(map(str, choice)) and all(isinstance(c, str) and c not in NO_KEY for c in choice):
            raise held("choice holds %s, a key the item no longer holds" % json.dumps(bad[0]))
        if bad:
            raise not_counted("choice holds %s, not an option key" % json.dumps(bad[0]))
        return "+".join(choice)
    if isinstance(choice, list):
        raise not_counted("item takes one option and the choice is a list")
    if isinstance(choice, str) and choice in keys:
        return choice
    if isinstance(choice, str) and choice not in NO_KEY and choice == pick:
        raise held("choice %s is a key the item no longer holds" % json.dumps(choice))
    if choice == "none":
        raise not_counted("choice is none: it asks for new options, and the routing session judges that")
    if choice == "overturn":
        if item.get("arbiter") is True:
            return "overturn"
        raise not_counted("choice is overturn and the item is not an arbiter ruling")
    raise not_counted("choice %s is not an option key" % json.dumps(choice))


LABEL_PARTS = re.compile(r"^([A-Za-z]): (.*)$", re.S)


def moved_reason(item, answer, choice):
    """Why the answer names an option the item no longer holds at its choice key, or "" when it matches or says nothing.
    The page saves `optionId` (the id of the option picked) and `label` ("A: Red"). With `optionId` the id decides; with
    none, the label's letter must be the option's position letter and its text the option's label. An overturn names no
    option. A field of the wrong shape for the item (a list on a pick-one answer) is not read, as before."""
    if choice == "overturn":
        return ""
    options = [o for o in item.get("options") or [] if isinstance(o, dict) and isinstance(o.get("key"), str)]
    keys = choice.split("+") if item.get("multi") is True else [choice]
    ids, labels = answer.get("optionId"), answer.get("label")
    multi = item.get("multi") is True
    for at, key in enumerate(keys):
        position = next(i for i, o in enumerate(options) if o["key"] == key)
        stored = options[position]
        if "optionId" in answer:
            got = ids[at] if multi and isinstance(ids, list) and at < len(ids) else None if multi else ids
            if got != stored.get("id"):
                return "answer option id %s is not option %s's id" % (json.dumps(got), key)
            continue
        text = labels[at] if multi and isinstance(labels, list) and at < len(labels) else None if multi else labels
        if not isinstance(text, str):
            continue
        parts = LABEL_PARTS.match(text)
        if not parts or parts.group(1).lower() != chr(97 + position % 26) or parts.group(2).strip() != str(stored.get("label") or "").strip():
            return "answer label %s is not option %s's label" % (json.dumps(text), key)
    return ""


def label_of(item, answer, choice):
    """The label the counted line prints: the picked option's label, a list of them for a multi item, None for an overturn.
    json.dumps keeps it on one line and escapes quotes and newlines, so a label cannot forge a token on the line."""
    if choice == "overturn":
        return None
    labels = {opt["key"]: opt.get("label") for opt in item.get("options") or []
              if isinstance(opt, dict) and isinstance(opt.get("key"), str)}
    if item.get("multi") is True:
        return [labels.get(key) for key in answer["choice"]]
    return labels.get(choice)


def routed_close(item, answer):
    """Rule 4's routed close: the item closed at routing, with `lane` and `home` set, and still holds this answer as `lastAnswer`."""
    last = item.get("lastAnswer")
    return (item.get("status") == "closed"
            and all(isinstance(item.get(key), str) and item[key].strip() for key in ("lane", "home"))
            and item.get("arbiter") is not True
            and isinstance(last, dict) and last.get("at") == answer.get("at"))


def judge(args):
    """The counted line, or a Verdict raised."""
    folder, made = use_stamp(args.fetched)
    if not args.item or os.sep in args.item or "/" in args.item or args.item in (".", ".."):
        raise not_counted("item id %r is not a plain id" % args.item)
    prove_fresh(folder, made, args.item)
    layout = load_layout()
    try:
        entries = layout.artifacts(args.root)
    except layout.LayoutError as err:
        raise unknown("the artifacts registry cannot be read: %s" % err)
    pages = [e for e in entries if e["role"] == layout.WAITING_ROLE]
    if not pages:
        raise unknown("%s has no waiting-page entry in its artifacts registry" % args.root)
    page_id = layout.artifact_id(args.page_url)
    if not page_id or page_id != layout.artifact_id(pages[0]["url"]):
        raise not_counted("page URL is not the registered waiting page")

    answer = read_doc(args.fetched, "answers", args.item)
    if answer is None:
        raise not_counted("no saved answer: relayed text is not the owner's grant")
    item = read_doc(args.fetched, "items", args.item)
    if item is None:
        raise not_counted("no saved item to read the answer against")

    if answer.get("item") != args.item:
        raise not_counted("answer is for item %s, not %s" % (json.dumps(answer.get("item")), args.item))
    n = answer.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n != item.get("n"):
        raise not_counted("answer n %s is not the item's n %s: the answer is for another ask" % (n, item.get("n")))
    status = item.get("status", "open")  # absent is open, as the page reads it: it hides only "closed"
    if status != "open" and not (status == "closed" and item.get("arbiter") is True and answer.get("choice") == "overturn") \
            and not routed_close(item, answer):
        raise not_counted("item status is %s: only an open item takes an answer, or a closed arbiter ruling an overturn"
                          % json.dumps(status))
    if moment(answer.get("at"), "answer at") <= moment(item.get("added"), "item added"):
        raise not_counted("answer is not later than the item's added time: it predates the ask")

    choice = choice_of(item, answer, args.pick)
    if args.pick is None:
        raise not_counted("no --pick: a decision is counted only against the pick the peer relayed")
    if choice != args.pick:
        raise not_counted("page pick is %s, not %s" % (choice, args.pick))
    moved = moved_reason(item, answer, choice)
    if moved:
        raise held(moved)
    line = (COUNTED_LINE.replace("<id>", args.item).replace("<n>", str(n)).replace("<key>", choice)
            .replace("<time>", answer["at"]).replace("<label>", json.dumps(label_of(item, answer, choice))))
    note = answer.get("note")
    if note:
        line += " note=" + json.dumps(note)
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(description="Say whether a fetched page answer is the owner's grant.")
    parser.add_argument("--new-fetch", metavar="PARENT", help="make an empty fetch folder under PARENT and print it")
    for flag, _, text in CHECK_FLAGS:
        parser.add_argument(flag, help=text)
    args = parser.parse_args(argv)
    if args.new_fetch is not None:
        print("fetch " + new_fetch(args.new_fetch))
        return COUNTED
    missing = [flag for flag, value in (("--root", args.root), ("--page-url", args.page_url), ("--item", args.item),
                                        ("--fetched", args.fetched)) if value is None]
    if missing:
        parser.error("the check needs " + ", ".join(missing))
    try:
        line, code = judge(args), COUNTED
    except Verdict as verdict:
        line, code = verdict.line, verdict.code
    except Exception as err:  # a crash is unknown, never a grant
        line, code = "unknown: the checker crashed: %s: %s" % (type(err).__name__, err), UNKNOWN
    print(" ".join(line.splitlines()))
    return code


if __name__ == "__main__":
    sys.exit(main())
