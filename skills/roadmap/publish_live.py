#!/usr/bin/env python3
"""Write the live file that build.py's live_work reads (skills/roadmap/SKILL.md, "Live work").

    python3 publish_live.py --dir READS --landed-since ISO [--out READS/live.json]

It makes no network call. Triage saves each tool result verbatim into READS first:
  pages.json        {"open": N, "closed": N, "sess": N}: how many pages triage read of each list. Required.
  open_p<N>.json    list_pull_requests (open, base main) pages, raw arrays. Pages count 1..N, N as in pages.json.
  closed_p<N>.json  the same tool, state closed. Adds merged_at and closed_at.
  sess_p<N>.json    list_sessions pages, raw arrays, until has_more is false.
  items/**/*.json   ArtifactData list of the waiting page, each doc a bare object or {"data": {...}}. Optional.
  prev.json         the previous live file: landedPulls, keepSessions, each session's unarchived_epoch.
  held.txt          one pull number per line, "#" comments allowed; a line ALL holds every open pull. Optional.
  readat.txt        the ISO time, with zone, of the reads.
A missing, gapped or short page list (against pages.json), a held.txt line that is not a number, #N, ALL or a
comment ("#" then a space, or a bare "#"), an idle_since with no
zone, an unarchived_epoch that is not a JSON int, or an item or pull number that is not an int stops the run with a
message and writes nothing. No held.txt means no holds. No items/ folder leaves `items` out of the file, so the
build reads the items as unknown, never as none.
Output: {readAt, pulls, branches, sessions, items, landedPulls, keepSessions}. A pull row has `held`. A session
row has `tags` (never absent), and `idle_since` on an IDLE row: its updated_at, which stands in for "last did
anything". `unarchived_epoch` is carried from prev.json only (a row with none stays without the key). landedPulls
is prev.json's rows plus the closed pulls (base main) with closed_at at or after --landed-since; the fresh read
wins. Each row carries `closed_at`; a prev row with none is stamped with this read's time. A row whose closed_at is
more than 14 days before readAt is dropped. `branches` is always [] (no input lists lane branches with no pull). It writes no `reviewLog` (part 2 of step stale-draft-reads-runner-holds). The idle-lanes joint line
(`merge --idle-lanes`) reads `idle_since` and `unarchived_epoch`, so their names and types stay as written here.
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

IDLE = "SESSION_STATUS_IDLE"
PAGE_LISTS = ("open", "closed", "sess")
LANDED_DAYS = 14
ITEM_KEYS = ("n", "status", "home", "lane", "owner")


class Stop(Exception):
    """A read that cannot be trusted; its text is the message."""


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise Stop("%s could not be read: %s" % (path.name, err))


def pages(folder, stem, count):
    """The rows of every <stem>_p<N>.json page, in page order. Pages must be exactly 1..count, the number triage read."""
    found = {}
    for path in folder.glob(stem + "_p*.json"):
        match = re.fullmatch(re.escape(stem) + r"_p(\d+)\.json", path.name)
        if match:
            found[int(match.group(1))] = path
    if not found:
        raise Stop("no %s_p<N>.json pages in %s" % (stem, folder))
    missing = sorted(set(range(1, count + 1)) - set(found))
    if missing:
        raise Stop("%s pages missing: %s" % (stem, ", ".join(map(str, missing))))
    if max(found) > count:
        raise Stop("%s has page %d but pages.json says %d were read" % (stem, max(found), count))
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
    """The held pull numbers as text, or "ALL". A line is a number, "#N", ALL, or a comment starting "# "."""
    path = folder / "held.txt"
    held = set()
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines() if path.exists() else [], 1):
        if re.match(r"#(\s|$)", line.strip()):
            continue
        word = re.sub(r"^#(?=\d)", "", line.split(" #")[0].strip())
        if not word:
            continue
        if word != "ALL" and not word.isdigit():
            raise Stop("held.txt line %d is not a number, ALL or a comment: %r" % (n, line))
        held.add(word)
    return held


def instant(text, what):
    """An ISO time with a zone as an aware datetime; a bad or zoneless time stops the run."""
    try:
        at = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise Stop("%s is not an ISO time: %r" % (what, text))
    if at.tzinfo is None:
        raise Stop("%s has no time zone: %r" % (what, text))
    return at


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
    since_at = instant(since, "--landed-since")
    counts = load(folder / "pages.json")
    if not isinstance(counts, dict) or not all(type(counts.get(k)) is int and counts[k] >= 1 for k in PAGE_LISTS):
        raise Stop("pages.json must give a page count of 1 or more for %s" % ", ".join(PAGE_LISTS))
    opens = {need(p, "number"): p for p in pages(folder, "open", counts["open"])}
    if not all(type(n) is int for n in opens):
        raise Stop("an open pull number is not an int")
    pulls = [{"number": p["number"], "title": need(p, "title"), "branch": need(p, "head", "ref"),
              "draft": bool(p.get("draft")), "createdAt": need(p, "created_at"), "head": need(p, "head", "sha"),
              "held": "ALL" in held or str(p["number"]) in held} for p in opens.values()]
    read_dt = instant(read_at, "readat.txt")
    landed = {r["number"]: dict(r, closed_at=r.get("closed_at") or read_at) for r in prev.get("landedPulls", [])}
    for p in pages(folder, "closed", counts["closed"]):
        if need(p, "base", "ref") == "main" and p.get("closed_at") and instant(p["closed_at"], "closed_at") >= since_at:
            landed[p["number"]] = {"number": p["number"], "branch": need(p, "head", "ref"),
                                   "head": need(p, "head", "sha"), "merged": bool(p.get("merged_at")),
                                   "closed_at": p["closed_at"]}
    epochs = {s["id"]: s["unarchived_epoch"] for s in prev.get("sessions", []) if "unarchived_epoch" in s}
    if not all(type(e) is int for e in epochs.values()):
        raise Stop("a prev.json unarchived_epoch is not a JSON int")
    sessions = {}
    cut = read_dt - datetime.timedelta(days=LANDED_DAYS)
    landed = {n: r for n, r in landed.items() if instant(r["closed_at"], "a landedPulls closed_at") >= cut}
    for s in pages(folder, "sess", counts["sess"]):
        row = {"id": need(s, "id"), "session_status": need(s, "session_status"), "tags": s.get("tags") or [],
               "status_bucket": s.get("status_bucket")}
        if row["session_status"] == IDLE and s.get("updated_at"):
            instant(s["updated_at"], "idle_since")
            row["idle_since"] = s["updated_at"]
        if row["id"] in epochs:
            row["unarchived_epoch"] = epochs[row["id"]]
        sessions[row["id"]] = row
    items = []
    for path in sorted((folder / "items").glob("**/*.json")) if (folder / "items").is_dir() else []:
        doc = load(path)
        if isinstance(doc, dict) and "data" in doc and "n" not in doc:
            doc = doc["data"]
        if not isinstance(doc, dict):
            raise Stop("%s is not an item" % path.name)
        if type(doc.get("n")) is not int:
            raise Stop("%s: an item's n is not an int" % path.name)
        items.append({k: doc[k] for k in ITEM_KEYS if k in doc})
    result = {"readAt": read_at, "pulls": pulls, "branches": [], "sessions": list(sessions.values()),
              "landedPulls": list(landed.values()), "keepSessions": prev.get("keepSessions", [])}
    if (folder / "items").is_dir():
        result["items"] = items
    return result


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
