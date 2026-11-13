#!/usr/bin/env python3
"""Write the live file that build.py's live_work reads (skills/roadmap/SKILL.md, "Live work").

    python3 publish_live.py --dir READS --landed-since ISO [--out READS/live.json]

It makes no network call. Triage saves each tool result verbatim into READS first:
  open_p<N>.json    list_pull_requests (open, base main) pages, raw arrays. Pages count 1..N with no gap.
  closed_p<N>.json  the same tool, state closed. Adds merged_at and closed_at.
  sess_p<N>.json    list_sessions pages, raw arrays, until has_more is false.
  items/**/*.json   ArtifactData list of the waiting page, each doc a bare object or {"data": {...}}. Optional.
  prev.json         the previous live file: landedPulls, keepSessions, each session's unarchived_epoch.
  held.txt          one pull number per line, "#" comments allowed; a line ALL holds every open pull. Optional.
  readat.txt        the ISO time, with zone, of the reads.
A missing or gapped page list, or a row of the wrong shape, stops the run with a message and writes nothing.
Output: {readAt, pulls, branches, sessions, items, landedPulls, keepSessions}. A pull row has `held`. A session
row has `tags` (never absent), and `idle_since` on an IDLE row: its updated_at, which stands in for "last did
anything". `unarchived_epoch` is carried from prev.json only (a row with none stays without the key). landedPulls
is prev.json's rows plus the closed pulls (base main) with closed_at at or after --landed-since; the fresh read
wins. It writes no `reviewLog` (part 2 of step stale-draft-reads-runner-holds); it pairs with the reader of
`idle_since` and `unarchived_epoch` in draft PR 3142.
"""
import argparse
import json
import pathlib
import re
import sys

IDLE = "SESSION_STATUS_IDLE"
ITEM_KEYS = ("n", "status", "home", "lane", "owner")


class Stop(Exception):
    """A read that cannot be trusted; its text is the message."""


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise Stop("%s could not be read: %s" % (path.name, err))


def pages(folder, stem):
    """The rows of every <stem>_p<N>.json page, in page order. Pages must be 1..N."""
    found = {}
    for path in folder.glob(stem + "_p*.json"):
        match = re.fullmatch(re.escape(stem) + r"_p(\d+)\.json", path.name)
        if match:
            found[int(match.group(1))] = path
    if not found:
        raise Stop("no %s_p<N>.json pages in %s" % (stem, folder))
    missing = sorted(set(range(1, max(found) + 1)) - set(found))
    if missing:
        raise Stop("%s pages missing: %s" % (stem, ", ".join(map(str, missing))))
    rows = []
    for n in sorted(found):
        page = load(found[n])
        if not isinstance(page, list) or not all(isinstance(r, dict) for r in page):
            raise Stop("%s is not a list of rows" % found[n].name)
        rows.extend(page)
    return rows


def need(row, *path):
    """row[path[0]][path[1]]...; a missing step stops the run."""
    value = row
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise Stop("a row lacks %s: %r" % (".".join(path), row.get("number", row.get("id"))))
        value = value[key]
    return value


def held_set(folder):
    path = folder / "held.txt"
    if not path.exists():
        return set()
    return {line.split("#")[0].strip() for line in path.read_text(encoding="utf-8").splitlines()} - {""}


def build(folder, since):
    folder = pathlib.Path(folder)
    read_path = folder / "readat.txt"
    read_at = read_path.read_text(encoding="utf-8").strip() if read_path.exists() else ""
    if not read_at:
        raise Stop("readat.txt is missing or empty")
    prev = load(folder / "prev.json")
    if not isinstance(prev, dict):
        raise Stop("prev.json is not an object")
    held = held_set(folder)
    opens = {need(p, "number"): p for p in pages(folder, "open")}
    pulls = [{"number": p["number"], "title": need(p, "title"), "branch": need(p, "head", "ref"),
              "draft": bool(p.get("draft")), "createdAt": need(p, "created_at"), "head": need(p, "head", "sha"),
              "held": "ALL" in held or str(p["number"]) in held} for p in opens.values()]
    landed = {r["number"]: r for r in prev.get("landedPulls", [])}
    for p in pages(folder, "closed"):
        if need(p, "base", "ref") == "main" and p.get("closed_at") and p["closed_at"] >= since:
            landed[p["number"]] = {"number": p["number"], "branch": need(p, "head", "ref"),
                                   "head": need(p, "head", "sha"), "merged": bool(p.get("merged_at"))}
    epochs = {s["id"]: s["unarchived_epoch"] for s in prev.get("sessions", []) if "unarchived_epoch" in s}
    sessions = {}
    for s in pages(folder, "sess"):
        row = {"id": need(s, "id"), "session_status": need(s, "session_status"), "tags": s.get("tags") or [],
               "status_bucket": s.get("status_bucket")}
        if row["session_status"] == IDLE and s.get("updated_at"):
            row["idle_since"] = s["updated_at"]
        if row["id"] in epochs:
            row["unarchived_epoch"] = epochs[row["id"]]
        sessions[row["id"]] = row
    items = []
    for path in sorted((folder / "items").glob("**/*.json")):
        doc = load(path)
        if isinstance(doc, dict) and "data" in doc and "n" not in doc:
            doc = doc["data"]
        if not isinstance(doc, dict):
            raise Stop("%s is not an item" % path.name)
        items.append({k: doc[k] for k in ITEM_KEYS if k in doc})
    return {"readAt": read_at, "pulls": pulls, "branches": [], "sessions": list(sessions.values()), "items": items,
            "landedPulls": list(landed.values()), "keepSessions": prev.get("keepSessions", [])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", required=True, help="the folder of saved reads")
    parser.add_argument("--landed-since", required=True, help="ISO time: keep closed pulls closed at or after it")
    parser.add_argument("--out", help="default: <dir>/live.json")
    args = parser.parse_args(argv)
    try:
        result = build(args.dir, args.landed_since)
    except Stop as err:
        sys.exit("publish_live: %s" % err)
    out = pathlib.Path(args.out) if args.out else pathlib.Path(args.dir) / "live.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
