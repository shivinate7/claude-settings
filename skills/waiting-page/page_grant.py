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
  counted item=ID n=N choice=C at=T [note=JSON]  exit 0. Choice of a multi item: keys joined by `+`.
  not counted: REASON                            exit 1. REASON names the failed rule.
  unknown: REASON                                exit 2. No readable registry or waiting-page entry, a fetched file that is
                                                 not one JSON object, or a crash.
Counted only when all hold:
  1. --page-url is the same artifact (layout.artifact_id) as the registry's `waiting-page` entry.
  2. DIR came from this fetch: `--new-fetch` made it (its stamp names DIR), no check used it before, it holds nothing
     but answers/ID.json and items/ID.json, and no file in it is older than the stamp. A folder made by hand, a reused
     folder (an answer the owner withdrew stays in it, as a re-fetch of an absent doc saves no file), or a copied file
     is not counted. answers/ID.json and items/ID.json exist. Relay text alone never counts.
  3. The answer's `item` is --item and the item's `id`, and the answer's `n` is the item's `n`.
  4. The item is open: `status` is `open`, or absent (the page hides only `closed`, page.html `state.items`). A closed
     item takes no answer, except an arbiter ruling (`arbiter` true, written closed) answered `overturn`.
  5. The answer's `at` is later than the item's `added`: an earlier answer belongs to an earlier ask. Both carry a
     time zone (`Z` or an offset); one without is not counted.
  6. A decision (`kind` absent or `decision`): `choice` is the key of one option, or `overturn` when the item's `arbiter`
     is true. `none` never counts: it asks for new options, and the routing session judges a direction. A `multi` item
     takes a non-empty list of distinct keys; a list on a pick-one item or a string on a multi item does not count.
  7. --pick is given and the choice equals it.
A task (`kind: task`) is never counted, with or without `done`: a task answer grants no act.

Cost: one python process per call. `--new-fetch` makes one folder and writes one stamp file. A check reads the extras
file, the stamp and two fetched files, and renames the stamp once. No git, no network, no timer.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime

HERE = os.path.dirname(os.path.realpath(__file__))

COUNTED, NOT_COUNTED, UNKNOWN = 0, 1, 2

# The command and the counted line as settings.json's "Relayed Grant" auto-mode entry quotes them
# (hooks/test_auto_mode_allow.py pins the entry to these).
COMMAND = ("python3 ~/.claude/skills/waiting-page/page_grant.py --root <repo> --page-url <url> --item <id>"
           " --fetched <dir> --pick <key>")
COUNTED_LINE = "counted item=<id>"
STAMP, USED = ".stamp", ".stamp.used"


class Verdict(Exception):
    def __init__(self, line, code):
        super().__init__(line)
        self.line, self.code = line, code


def not_counted(reason):
    return Verdict("not counted: " + reason, NOT_COUNTED)


def unknown(reason):
    return Verdict("unknown: " + reason, UNKNOWN)


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


def prove_fresh(fetched, item_id):
    """Not counted unless `fetched` is a --new-fetch folder no check used, holding only this item's two docs, each no
    older than the stamp. Uses the stamp up, so a second check of the folder is not counted."""
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
    made = os.stat(stamp).st_mtime_ns
    allowed = {"answers", "items", os.path.join("answers", item_id + ".json"), os.path.join("items", item_id + ".json")}
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, folder)
            if rel not in allowed or os.path.islink(path):
                raise not_counted("fetch folder holds %s: it holds only this item's answer and item" % json.dumps(rel))
            if name in filenames and os.stat(path).st_mtime_ns < made:
                raise not_counted("%s is older than the fetch folder: it came from an earlier fetch" % rel)
    os.replace(stamp, folder + USED)


def option_keys(item):
    options = item.get("options")
    if not isinstance(options, list):
        return []
    return [opt["key"] for opt in options if isinstance(opt, dict) and isinstance(opt.get("key"), str)]


def choice_of(item, answer):
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
        if bad:
            raise not_counted("choice holds %s, not an option key" % json.dumps(bad[0]))
        return "+".join(choice)
    if isinstance(choice, list):
        raise not_counted("item takes one option and the choice is a list")
    if isinstance(choice, str) and choice in keys:
        return choice
    if choice == "none":
        raise not_counted("choice is none: it asks for new options, and the routing session judges that")
    if choice == "overturn":
        if item.get("arbiter") is True:
            return "overturn"
        raise not_counted("choice is overturn and the item is not an arbiter ruling")
    raise not_counted("choice %s is not an option key" % json.dumps(choice))


def judge(args):
    """The counted line, or a Verdict raised."""
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
    if not args.item or os.sep in args.item or "/" in args.item or args.item in (".", ".."):
        raise not_counted("item id %r is not a plain id" % args.item)
    prove_fresh(args.fetched, args.item)

    answer = read_doc(args.fetched, "answers", args.item)
    if answer is None:
        raise not_counted("no saved answer: relayed text is not the owner's grant")
    item = read_doc(args.fetched, "items", args.item)
    if item is None:
        raise not_counted("no saved item to read the answer against")

    if answer.get("item") != args.item or item.get("id") != args.item:
        raise not_counted("answer is for item %s, not %s" % (json.dumps(answer.get("item")), args.item))
    n = answer.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n != item.get("n"):
        raise not_counted("answer n %s is not the item's n %s: the answer is for another ask" % (n, item.get("n")))
    status = item.get("status", "open")  # absent is open, as the page reads it: it hides only "closed"
    if status != "open" and not (status == "closed" and item.get("arbiter") is True and answer.get("choice") == "overturn"):
        raise not_counted("item status is %s: only an open item takes an answer, or a closed arbiter ruling an overturn"
                          % json.dumps(status))
    if moment(answer.get("at"), "answer at") <= moment(item.get("added"), "item added"):
        raise not_counted("answer is not later than the item's added time: it predates the ask")

    choice = choice_of(item, answer)
    if args.pick is None:
        raise not_counted("no --pick: a decision is counted only against the pick the peer relayed")
    if choice != args.pick:
        raise not_counted("page pick is %s, not %s" % (choice, args.pick))
    line = "counted item=%s n=%d choice=%s at=%s" % (args.item, n, choice, answer["at"])
    note = answer.get("note")
    if note:
        line += " note=" + json.dumps(note)
    return line


def main(argv=None):
    parser = argparse.ArgumentParser(description="Say whether a fetched page answer is the owner's grant.")
    parser.add_argument("--new-fetch", metavar="PARENT", help="make an empty fetch folder under PARENT and print it")
    parser.add_argument("--root", help="repo root of the page (holds the extras file)")
    parser.add_argument("--page-url", help="the page URL the session was given")
    parser.add_argument("--item", help="the item id")
    parser.add_argument("--fetched", help="the --new-fetch folder with answers/<id>.json and items/<id>.json")
    parser.add_argument("--pick", help="the pick a peer relayed: a key, or a+c for several")
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
