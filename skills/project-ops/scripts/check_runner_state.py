#!/usr/bin/env python3
"""Checks the batch runner's state file, the message that carries it, and the handoff that points to it.

    python3 check_runner_state.py state <file>      # plans/runner-state.json, or a seed
    python3 check_runner_state.py message <file> <committed file>   # the text a runner sends triage; triage
                                                    # passes `git show origin/roadmap:plans/runner-state.json`
    python3 check_runner_state.py message <file> --first   # only when that file is absent: accepts version 1 only
    python3 check_runner_state.py handoff <file>    # a runner handoff: points to the file, copies no list
    python3 check_runner_state.py recover <handoff file> <state file>   # the state file is `git show <ref>` saved to a file

A message with no committed file and no `--first` is unknown (exit 2), and so is a committed file with `--first`.

The runner's merge queue, folds, gos, holds and archive pass live in one file on the record branch, so a
compaction cannot drop them (decision runner-state-on-record). Triage is the one writer of that branch
(rule roadmap-one-writer), so the runner sends the whole file in one message per merge and triage commits it.
Exit 0 ok, 1 a problem (each printed), 2 a bad argument or an unreadable file.
"""
import datetime
import json
import re
import string
import sys

HOME = "origin/roadmap:plans/runner-state.json"
FIELDS = ("schema", "repo", "version", "writtenAt", "runner", "afterMerge", "queue", "folds", "gos", "holds",
          "archivePass")
HEADER = re.compile(r"^RUNNER-STATE (\S+/\S+) v(\d+) after merge #(\d+)[ \t]*$")
POINTER = re.compile(r"^Runner state: ((?:origin/)?roadmap:plans/runner-state\.json), last sent version (\d+)\.?[ \t]*$",
                     re.M)
# A copy of the state is a list label that ends in a colon (after a bullet, bold or quote mark, with an
# optional count), whose line or bullet block carries a PR ref; or a line that runs PR refs as a sequence.
# Prose with no label and colon passes, so "Holds were reviewed at 23:10" or "Go merge PR 3359 first." is no copy.
LABEL = re.compile(r"^[ \t>*_`-]*(?:Merge queue|Queue|Folds?|Gos?|Holds?|Held|Archive pass)"
                   r"[ \t]*(?:\(\d+\))?[*_`]*:(?P<rest>[^\n]*)$", re.I)
# A PR ref: `#N`, `PR N`, or a bare number of 2+ digits that is not part of a time, date, path or word.
REF = r"(?:#\d+|\bPR[ \t]*\d+|(?<![\w:./#-])\d{2,}(?![\w:/-]|\.\d))"
HAS_REF = re.compile(REF, re.I)
SEQUENCE = re.compile(r"(?:#\d+|\bPR[ \t]*\d+)\b[^\n]*?(?:,|\bthen\b|\band\b)[ \t]*(?:(?:then|and)[ \t]+)?"
                      r"(?:#\d+|\bPR[ \t]*\d+|(?<![\w:./#-])\d{3,}(?![\w:/-]|\.\d))", re.I)
BULLET = re.compile(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+")
PLACEHOLDER = {"tbd", "n/a", "na", "none", "unknown", "?", "todo", "later", "soon", "pending", "x", "-"}


class Unknown(Exception):
    """The state could not be read or is not valid: the caller must treat it as unknown, never empty."""


class Stale(Exception):
    """The committed file is older than the last version the runner sent."""


def _zoned(value):
    if not isinstance(value, str):
        return False
    try:
        return datetime.datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _named_event(value):
    """True when value names an end event: not empty and not a placeholder, trailing punctuation ignored."""
    if not isinstance(value, str):
        return False
    word = value.strip().lower()
    core = word.rstrip(string.punctuation + " \t")
    return bool(core) and word not in PLACEHOLDER and core not in PLACEHOLDER


def state_problems(s):
    """-> the problems of a state object, one string each. An empty list is ok."""
    if not isinstance(s, dict):
        return ["The state is not a JSON object."]
    out = [f"Missing field `{k}`." for k in FIELDS if k not in s]
    if out:
        return out
    if s["schema"] != 1:
        out.append("`schema` must be 1.")
    if not (isinstance(s["repo"], str) and "/" in s["repo"]):
        out.append("`repo` must be `owner/name`.")
    if not _int(s["version"]) or s["version"] < 0:
        out.append("`version` must be an integer, 0 or more.")
    if not _zoned(s["writtenAt"]):
        out.append("`writtenAt` must be an ISO time with a zone.")
    if not (isinstance(s["runner"], str) and s["runner"]):
        out.append("`runner` must name the runner session.")
    am = s["afterMerge"]
    if not (isinstance(am, dict) and (am.get("pr") is None or _int(am.get("pr")))
            and (am.get("commit") is None or isinstance(am.get("commit"), str)) and "pr" in am and "commit" in am):
        out.append("`afterMerge` needs `pr` (integer) and `commit` (string), both null before the first merge.")
    folds = s["folds"] if isinstance(s["folds"], list) else None
    queue = s["queue"] if isinstance(s["queue"], list) else None
    gos = s["gos"] if isinstance(s["gos"], list) else None
    holds = s["holds"] if isinstance(s["holds"], list) else None
    for name, val in (("folds", folds), ("queue", queue), ("gos", gos), ("holds", holds)):
        if val is None:
            out.append(f"`{name}` must be a list.")
    fold_ids = set()
    for f in folds or []:
        if not (isinstance(f, dict) and isinstance(f.get("id"), str) and f["id"] and _int(f.get("pr"))
                and isinstance(f.get("base"), str) and isinstance(f.get("members"), list)
                and all(_int(m) for m in f["members"])):
            out.append(f"A fold needs `id`, `pr`, `base` and an integer `members` list: {f!r}.")
        else:
            fold_ids.add(f["id"])
    seen = set()
    for q in queue or []:
        if not (isinstance(q, dict) and _int(q.get("pr")) and isinstance(q.get("head"), str) and q["head"]
                and isinstance(q.get("path"), str)):
            out.append(f"A queue row needs `pr`, `head` and `path`: {q!r}.")
            continue
        if q["pr"] in seen:
            out.append(f"PR {q['pr']} is twice in the queue.")
        seen.add(q["pr"])
        if q["path"] != "alone" and not (q["path"].startswith("fold:") and q["path"][5:] in fold_ids):
            out.append(f"Queue row for PR {q['pr']} has path `{q['path']}`: use `alone` or `fold:<id of a fold>`.")
    for g in gos or []:
        if not (isinstance(g, dict) and _int(g.get("pr")) and isinstance(g.get("by"), str) and g["by"]
                and _zoned(g.get("at"))):
            out.append(f"A go needs `pr`, `by` and a zoned `at`: {g!r}.")
    for h in holds or []:
        if not (isinstance(h, dict) and _int(h.get("pr")) and isinstance(h.get("reason"), str) and h["reason"]
                and _named_event(h.get("endsOn"))):
            out.append(f"A hold needs `pr`, `reason` and a named end event `endsOn`: {h!r}.")
    ap = s["archivePass"]
    if not (isinstance(ap, dict) and (ap.get("lastRunAt") is None or _zoned(ap.get("lastRunAt")))
            and isinstance(ap.get("pending"), list) and all(isinstance(x, str) for x in ap["pending"])):
        out.append("`archivePass` needs `lastRunAt` (zoned time or null) and a `pending` list.")
    return out


def _split(text):
    """-> (header line, body). A body wrapped in one code fence (``` or ```json) loses the fence."""
    head, _, body = text.replace("\r\n", "\n").partition("\n")
    lines = body.strip().split("\n")
    if len(lines) >= 2 and re.fullmatch(r"```[ \t]*(?:json)?[ \t]*", lines[0], re.I) and lines[-1].strip() == "```":
        body = "\n".join(lines[1:-1])
    return head, body


def message_problems(text, committed=None, first=None):
    """-> the problems of a runner-to-triage message: a header line, then the whole file as JSON.

    committed is the text of the file now on the record branch, which triage reads with `git show`. With it, the
    message must be the next version and its merged PR must have left the queue, so a runner that lost its state
    and starts from the seed cannot overwrite the live file. Raises Unknown when committed is not a valid state.

    first says whether the file is absent on the record branch. None judges the message alone. False with no
    committed file raises Unknown: an unread file is unknown, never "no state yet". True accepts only version 1,
    and raises Unknown when a committed file is given too.
    """
    if first is False and committed is None:
        raise Unknown("no committed file was given: pass the file on the record branch, or --first when it is absent")
    if first is True and committed is not None:
        raise Unknown("--first was given with a committed file: a first send is only for an absent file")
    head, body = _split(text)
    m = HEADER.match(head)
    if not m:
        return ["The first line must be `RUNNER-STATE <owner/repo> v<N> after merge #<PR>`."]
    try:
        s = json.loads(body)
    except ValueError as e:
        return [f"The body is not JSON: {e}."]
    out = state_problems(s)
    if out:
        return out
    if s["repo"] != m.group(1):
        out.append(f"Header repo {m.group(1)} differs from the file's {s['repo']}.")
    if s["version"] != int(m.group(2)):
        out.append(f"Header version v{m.group(2)} differs from the file's {s['version']}.")
    if s["afterMerge"]["pr"] != int(m.group(3)):
        out.append(f"Header PR #{m.group(3)} differs from the file's afterMerge PR {s['afterMerge']['pr']}.")
    if any(q["pr"] == s["afterMerge"]["pr"] for q in s["queue"]):
        out.append(f"PR {s['afterMerge']['pr']} merged but is still in the queue.")
    if first is True and s["version"] != 1:
        out.append(f"Version v{s['version']} is sent as the first state: the first state is v1.")
    if committed is not None:
        try:
            old = json.loads(committed)
        except ValueError as e:
            raise Unknown(f"the committed file is not JSON: {e}")
        if state_problems(old):
            raise Unknown(f"the committed file is not a valid state: {state_problems(old)[0]}")
        if s["version"] != old["version"] + 1:
            out.append(f"Version v{s['version']} is not the next after the committed v{old['version']}: "
                       "the runner read an old file, or skipped one. Do not commit; tell the runner to re-read.")
    return out


def handoff_problems(text):
    """-> the problems of a runner handoff: one pointer line to the file, and no copy of its lists."""
    out = []
    if not POINTER.search(text):
        out.append(f"No pointer line. Add `Runner state: {HOME}, last sent version <N>.`")
    lines = text.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if POINTER.match(line):
            continue
        m = LABEL.match(line)
        copied = False
        if m:
            copied = bool(HAS_REF.search(m.group("rest")))
            for below in lines[i + 1:]:  # the bullet block right under the label
                if copied or not BULLET.match(below):
                    break
                copied = bool(HAS_REF.search(below))
        if copied or SEQUENCE.search(line):
            out.append(f"The handoff copies a list of the state: \"{line.strip()}\". Name the file, never copy it.")
    return out


def recover(handoff_text, read_ref):
    """What a successor does after a compaction: find the pointer, read the file, check it. -> the state.

    read_ref(ref) -> the file's text, or None when it could not be read.
    Raises Unknown when the pointer, the read or the file is bad, and Stale when the committed version is older
    than the last one the runner sent (the runner then resends its state to triage).
    """
    m = POINTER.search(handoff_text)
    if not m:
        raise Unknown("the handoff holds no `Runner state:` pointer line")
    ref, sent = m.group(1), int(m.group(2))
    text = read_ref(ref)
    if text is None:
        raise Unknown(f"could not read {ref}")
    try:
        s = json.loads(text)
    except ValueError as e:
        raise Unknown(f"{ref} is not JSON: {e}")
    bad = state_problems(s)
    if bad:
        raise Unknown(f"{ref} is not a valid state: {bad[0]}")
    if s["version"] < sent and s["afterMerge"]["commit"] is None:
        raise Stale(f"committed v{s['version']} is older than the last sent v{sent}, and no merge recorded yet: send "
                    f"the first state as v{s['version'] + 1}, and read triage's answer before the next merge")
    if s["version"] < sent:
        raise Stale(f"committed v{s['version']} is older than the last sent v{sent}: the merge after commit "
                    f"{s['afterMerge']['commit']} is not in the file. Read main's merges since that commit, apply them "
                    f"to the file, send v{s['version'] + 1}, and read triage's answer before the next merge")
    return s


def main(argv):
    first = "--first" in argv[2:]
    argv = argv[:2] + [a for a in argv[2:] if a != "--first"]
    if first and argv[1:2] != ["message"]:
        print(__doc__)
        return 2
    if len(argv) < 3 or argv[1] not in ("state", "message", "handoff", "recover"):
        print(__doc__)
        return 2
    try:
        with open(argv[2], encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        print(f"unknown: cannot read {argv[2]}: {e}")
        return 2
    if argv[1] == "recover":
        if len(argv) < 4:
            print(__doc__)
            return 2
        try:
            with open(argv[3], encoding="utf-8") as f:
                state_text = f.read()
        except OSError:
            state_text = None
        try:
            s = recover(text, lambda ref: state_text)
        except (Unknown, Stale) as e:
            print(f"{type(e).__name__.lower()}: {e}")
            return 1
        print(f"ok: v{s['version']}, {len(s['queue'])} queued, {len(s['holds'])} held")
        return 0
    if argv[1] == "state":
        try:
            problems = state_problems(json.loads(text))
        except ValueError as e:
            problems = [f"Not JSON: {e}."]
    elif argv[1] == "message":
        committed = None
        if len(argv) > 3:
            try:
                with open(argv[3], encoding="utf-8") as f:
                    committed = f.read()
            except OSError as e:
                print(f"unknown: cannot read {argv[3]}: {e}")
                return 2
        try:
            problems = message_problems(text, committed, first=first)
        except Unknown as e:
            print(f"unknown: {e}")
            return 2
    else:
        problems = handoff_problems(text)
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
