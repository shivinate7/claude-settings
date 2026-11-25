#!/usr/bin/env python3
"""Pace numbers two and three, read from the session transcript.

    python3 lint/pace_numbers.py --transcript FILE --between START END

START and END are ISO 8601 times with a UTC offset, as lint/guard_log_report.py takes them. Git, GitHub
and guard.log hold no agent spans; the transcript does, so this reader is their one home. It prints

    agents run: N, most at once: M[ (P still running)]
    minutes with no agent running: K

An agent's span opens at its Agent (or Task) tool_use. A background agent's span closes at the first
task-notification for its task-id with an ending status; a foreground agent's closes at its tool_result. One
stop is logged in up to three carriers (queue, user record, attachment): the earliest copy counts. A later
stop with no SendMessage since the first moves the close to the later stop. A SendMessage to the agent after
the close opens a new span. Spans are clipped to the window. A file it cannot read or decode, an empty file,
or a window holding no record prints one `unknown: <reason>` line and exits 0.

The covered span runs from the transcript's first to its last timestamped record. Window minutes outside it are
not idle: the idle line then ends with a note that says how many minutes were left out. A window with no
minute inside the span prints one `unknown:` line.
"""
import argparse
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _transcript  # noqa: E402  the shared readers: one home

SPAWN_TOOLS = ("Agent", "Task")
# A task that ended its work, whatever the cause. The notice carries no other ending status.
ENDING_STATUSES = ("completed", "failed", "killed")
# The record kinds that carry a notice as their own message. A tool_result block, a blob copy and a
# compaction summary only quote one.
QUEUE_KIND = "queue-operation"
USER_KIND = "user"
ATTACHMENT_KIND = "attachment"
QUEUED_ATTACHMENT = "queued_command"
NOTICE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
TASK_ID = re.compile(r"<task-id>\s*([^<\s]+)\s*</task-id>")
STATUS = re.compile(r"<status>\s*([^<\s]+)\s*</status>")


def record_time(rec):
    value = rec.get("timestamp")
    return _transcript.parse_utc_timestamp(value) if isinstance(value, str) else None


def notice_texts(rec):
    """The task-notification texts a record carries as its own message: a queue-operation's content, text in
    a user record's content, or a queued_command attachment's prompt. A tool_result block, a blob copy and a
    compaction summary carry none: a notice quoted there is somebody's text about a notice, not a notice."""
    kind = rec.get("type")
    if kind == QUEUE_KIND:
        content = rec.get("content")
    elif kind == USER_KIND and rec.get("isCompactSummary") is not True:
        content = (rec.get("message") or {}).get("content")
    elif kind == ATTACHMENT_KIND and (rec.get("attachment") or {}).get("type") == QUEUED_ATTACHMENT:
        content = rec["attachment"].get("prompt")
    else:
        return []
    if isinstance(content, list):
        content = "\n".join(b["text"] for b in content if isinstance(b, dict)
                            and b.get("type") == "text" and isinstance(b.get("text"), str))
    return NOTICE.findall(content) if isinstance(content, str) else []


def launches(records):
    """(spawn time by tool_use id, agent id by tool_use id, result time by foreground agent id). A refused spawn
    has no agent id, so it has no span. A background launch's result says isAsync; a foreground agent's result
    is its end."""
    spawned, agent_of, returned = {}, {}, {}
    for rec in records:
        when = record_time(rec)
        if when is None:
            continue
        for use in _transcript.tool_uses(rec):
            if use.get("name") in SPAWN_TOOLS and isinstance(use.get("id"), str):
                spawned[use["id"]] = when
        result = rec.get("toolUseResult")
        agent = result.get("agentId") if isinstance(result, dict) else None
        if isinstance(agent, str) and agent:
            for block in _transcript.tool_results(rec):
                if block.get("is_error") is not True and isinstance(block.get("tool_use_id"), str):
                    agent_of[block["tool_use_id"]] = agent
                    if result.get("isAsync") is not True:
                        returned.setdefault(agent, when)
    return spawned, agent_of, returned


def agent_events(records, starts, returned):
    """Per agent id, its events after its start: ("send", t) and ("end", t). A foreground agent's result is an
    end. One stop's copies share their text, so each distinct notice text gives one end, at its earliest copy."""
    failed = _transcript.failed_tool_use_ids(records)
    events = {agent: [] for agent in starts}
    for agent, when in returned.items():
        if agent in events:
            events[agent].append((when, "end"))
    stops = {}
    for rec in records:
        when = record_time(rec)
        if when is None:
            continue
        for use in _transcript.tool_uses(rec):
            if use.get("id") in failed:
                continue
            for target in _transcript.send_targets(use):
                if target in events:
                    events[target].append((when, "send"))
        for text in notice_texts(rec):
            task, status = TASK_ID.search(text), STATUS.search(text)
            if task and task.group(1) in events and status and status.group(1) in ENDING_STATUSES:
                key = (task.group(1), text)
                stops[key] = min(when, stops.get(key, when))
    for (agent, _), when in stops.items():
        events[agent].append((when, "end"))
    return events


def spans_of(start, events):
    """The agent's [open, close] pairs; close is None while it runs. A send while open changes nothing. An end
    while closed, with no send since the last, is a later stop: it moves the close to it."""
    spans = [[start, None]]
    for when, kind in sorted((e for e in events if e[0] >= start), key=lambda e: e[0]):
        if kind == "end":
            spans[-1][1] = when
        elif kind == "send" and spans[-1][1] is not None:
            spans.append([when, None])
    return spans


def numbers(records, begin, finish):
    spawned, agent_of, returned = launches(records)
    starts = {}
    for use_id, agent in agent_of.items():
        if use_id in spawned:
            starts.setdefault(agent, spawned[use_id])
    events = agent_events(records, starts, returned)
    clipped, counted, still = [], set(), set()
    for agent, start in starts.items():
        for opened, closed in spans_of(start, events[agent]):
            lo, hi = max(opened, begin), min(finish if closed is None else closed, finish)
            if lo < hi:
                clipped.append((lo, hi))
                counted.add(agent)
                if closed is None:
                    still.add(agent)
    # Ends sort before starts at one instant, so back-to-back spans never count as overlapping.
    edges = sorted([(lo, 1) for lo, _ in clipped] + [(hi, -1) for _, hi in clipped], key=lambda e: (e[0], e[1]))
    now = most = 0
    for _, step in edges:
        now += step
        most = max(most, now)
    busy, reach = 0.0, begin
    for lo, hi in sorted(clipped):
        lo = max(lo, reach)
        if hi > lo:
            busy += hi - lo
            reach = hi
    return len(counted), most, len(still), int((finish - begin - busy) // 60)


def window_moment(text):
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError("a window time needs a UTC offset, such as 2026-11-01T16:55:00-06:00")
    return moment


def covered_span(records):
    """(earliest, latest) timestamp of the records that carry one, or None when none does."""
    moments = [t for t in map(record_time, records) if t is not None]
    return (min(moments), max(moments)) if moments else None


def edge_text(moment, zone):
    """A span edge written in the window's own offset, to the second."""
    return datetime.fromtimestamp(moment, zone).isoformat(timespec="seconds")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--between", nargs=2, metavar=("START", "END"), required=True)
    args = ap.parse_args(argv)
    try:
        first, last = (window_moment(t) for t in args.between)
        begin, finish = first.timestamp(), last.timestamp()
    except ValueError as err:
        ap.error(str(err))
    try:
        records = _transcript.read_transcript(args.transcript)
    except OSError as err:
        print("unknown: cannot read the transcript (%s)" % err.strerror)
        return 0
    except UnicodeDecodeError:
        print("unknown: the transcript is not valid UTF-8")
        return 0
    if not records:
        print("unknown: the transcript holds no record")
        return 0
    if not any(begin <= (record_time(r) or float("-inf")) <= finish for r in records):
        print("unknown: the transcript holds no record in the window")
        return 0
    # Only the part of the window inside the transcript's span can be judged idle; the rest is reported, not counted.
    cover_from, cover_to = covered_span(records)
    lo, hi = max(begin, cover_from), min(finish, cover_to)
    if lo >= hi:
        print("unknown: the window has no minute inside the transcript's span")
        return 0
    notes = []
    if cover_from - begin >= 60:
        notes.append("transcript covers from %s on; %d min before it not counted"
                     % (edge_text(cover_from, first.tzinfo), (cover_from - begin) // 60))
    if finish - cover_to >= 60:
        notes.append("transcript covers until %s; %d min after it not counted"
                     % (edge_text(cover_to, first.tzinfo), (finish - cover_to) // 60))
    agents, most, still, idle = numbers(records, lo, hi)
    print("agents run: %d, most at once: %d%s" % (agents, most, " (%d still running)" % still if still else ""))
    print("minutes with no agent running: %d%s" % (idle, "".join(" (%s)" % n for n in notes)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
