#!/usr/bin/env python3
"""Write the live file that build.py's live_work reads (skills/roadmap/SKILL.md, "Live work").

    python3 publish_live.py --sessions S.json --pulls P.json --held H.json [--read-at ISO] [--out live.json]

Inputs are files, or "-" for stdin (one of them); the script makes no network call. Triage reads them first:
  --sessions  list_sessions rows, every page: a JSON list, or {"sessions": [...]}.
  --pulls     the open pull rows: [{"number", "title", "branch"?, "draft"?, "createdAt"?, "head"?, "url"?, "checks"?}].
  --held      the pulls the batch runner's hold or hand-in list names: [N, "#N", ...].
Output: {"readAt", "pulls", "sessions"}. Each pull gets `held` (true when named). Each session keeps id,
session_status, tags and status_bucket; an IDLE row gets `idle_since` from its updated_at, and a row's
`unarchived_epoch` is copied only when the input has it. It writes no `reviewLog` and no threads or items list.
"""
import argparse
import datetime
import json
import pathlib
import sys

IDLE = "SESSION_STATUS_IDLE"
SESSION_KEYS = ("id", "session_status", "tags", "status_bucket", "unarchived_epoch")
PULL_KEYS = ("number", "title", "branch", "draft", "createdAt", "head", "url", "checks")


def load(path):
    text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def held_numbers(held):
    """The pull numbers a held list names; an entry that is neither an int nor "#N" is an error, never skipped."""
    numbers = set()
    for entry in held:
        text = entry.lstrip("#") if isinstance(entry, str) else entry
        if isinstance(text, str) and text.isdigit():
            text = int(text)
        if type(text) is not int:
            raise ValueError("held entry %r is not a pull number" % (entry,))
        numbers.add(text)
    return numbers


def build(sessions, pulls, held, read_at):
    if isinstance(sessions, dict):
        sessions = sessions.get("sessions")
    if not isinstance(sessions, list) or not all(isinstance(r, dict) for r in sessions):
        raise ValueError("--sessions is not a list of session rows")
    if not isinstance(pulls, list) or not all(isinstance(r, dict) for r in pulls):
        raise ValueError("--pulls is not a list of pull rows")
    if not isinstance(held, list):
        raise ValueError("--held is not a list")
    named = held_numbers(held)
    out_sessions = []
    for row in sessions:
        kept = {k: row[k] for k in SESSION_KEYS if k in row}
        if row.get("session_status") == IDLE and isinstance(row.get("updated_at"), str):
            kept["idle_since"] = row["updated_at"]
        out_sessions.append(kept)
    out_pulls = [dict({k: row[k] for k in PULL_KEYS if k in row}, held=row.get("number") in named) for row in pulls]
    return {"readAt": read_at, "pulls": out_pulls, "sessions": out_sessions}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessions", required=True)
    parser.add_argument("--pulls", required=True)
    parser.add_argument("--held", required=True)
    parser.add_argument("--read-at", help="ISO time of the reads; default now (UTC)")
    parser.add_argument("--out", default="live.json")
    args = parser.parse_args(argv)
    read_at = args.read_at or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        result = build(load(args.sessions), load(args.pulls), load(args.held), read_at)
    except (OSError, ValueError) as err:
        sys.exit("publish_live: %s" % err)
    pathlib.Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
