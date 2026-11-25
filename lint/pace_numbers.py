#!/usr/bin/env python3
"""Pace numbers two and three, read from the session transcript.

    python3 lint/pace_numbers.py --transcript FILE --between START END

START and END are ISO 8601 times with a UTC offset, as lint/guard_log_report.py takes them. Git, GitHub
and guard.log hold no agent spans; the transcript does, so this reader is their one home. It prints

    agents run: N, most at once: M[ (P still running)]
    minutes with no agent running: K

An agent's span opens at its Agent (or Task) tool_use and closes at the first task-notification for its
task-id with an ending status. A SendMessage to the agent after the close opens a new span. Spans are
clipped to the window. A file it cannot read, an empty file, or a window holding no record prints one
`unknown: <reason>` line and exits 0.
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
NOTICE = re.compile(r"<task-notification>(.*?)</task-notification>", re.S)
TASK_ID = re.compile(r"<task-id>\s*([^<\s]+)\s*</task-id>")
STATUS = re.compile(r"<status>\s*([^<\s]+)\s*</status>")


def stamp(rec):
    value = rec.get("timestamp")
    return _transcript.parse_utc_timestamp(value) if isinstance(value, str) else None


def notice_texts(rec):
    """The task-notification texts a record carries as its own message: a queue-operation's content, or text
    in a user record's content. A tool_result block, a blob copy and an attachment carry none: a notice quoted
    there is somebody's text about a notice, not a notice."""
    kind = rec.get("type")
    if kind == "queue-operation":
        content = rec.get("content")
    elif kind == "user":
        content = (rec.get("message") or {}).get("content")
    else:
        return []
    if isinstance(content, list):
        content = "\n".join(b["text"] for b in content if isinstance(b, dict)
                            and b.get("type") == "text" and isinstance(b.get("text"), str))
    return NOTICE.findall(content) if isinstance(content, str) else []


def launches(records):
    """(spawn time by tool_use id, agent id by tool_use id). A refused spawn has no agent id, so it has no span."""
    spawned, agent_of = {}, {}
    for rec in records:
        when = stamp(rec)
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
    return spawned, agent_of


def agent_events(records, starts):
    """Per agent id, its time-ordered events after its start: ("send", t) and ("end", t)."""
    failed = _transcript.failed_tool_use_ids(records)
    events = {agent: [] for agent in starts}
    for rec in records:
        when = stamp(rec)
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
                events[task.group(1)].append((when, "end"))
    return events


def spans_of(start, events):
    """The agent's [open, close] pairs; close is None while it runs. A send while open changes nothing, and an
    end while closed (the notice is logged twice) changes nothing."""
    spans = [[start, None]]
    for when, kind in sorted((e for e in events if e[0] >= start), key=lambda e: e[0]):
        if kind == "end" and spans[-1][1] is None:
            spans[-1][1] = when
        elif kind == "send" and spans[-1][1] is not None:
            spans.append([when, None])
    return spans


def numbers(records, begin, finish):
    spawned, agent_of = launches(records)
    starts = {}
    for use_id, agent in agent_of.items():
        if use_id in spawned:
            starts.setdefault(agent, spawned[use_id])
    events = agent_events(records, starts)
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


def window_time(text):
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError("a window time needs a UTC offset, such as 2026-11-01T16:55:00-06:00")
    return moment.timestamp()


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--between", nargs=2, metavar=("START", "END"), required=True)
    args = ap.parse_args(argv)
    try:
        begin, finish = (window_time(t) for t in args.between)
    except ValueError as err:
        ap.error(str(err))
    try:
        records = _transcript.read_transcript(args.transcript)
    except OSError as err:
        print("unknown: cannot read the transcript (%s)" % err.strerror)
        return 0
    if not records:
        print("unknown: the transcript holds no record")
        return 0
    if not any(begin <= (stamp(r) or float("-inf")) <= finish for r in records):
        print("unknown: the transcript holds no record in the window")
        return 0
    agents, most, still, idle = numbers(records, begin, finish)
    print("agents run: %d, most at once: %d%s" % (agents, most, " (%d still running)" % still if still else ""))
    print("minutes with no agent running: %d" % idle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
