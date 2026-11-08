#!/usr/bin/env python3
"""Fails if an agent or skill file sets a Haiku model in its frontmatter.

The guard's agent-model-floor rule reads the model a spawn names. An agent file's own
`model:` key names no model in the tool input, so the guard never sees it. This check reads
the files instead. Sonnet is the floor, except for the agent files named in
the guard's HAIKU_ROLES.

    python3 lint/check_agent_models.py [file ...]

With no argument it checks agents/*.md and skills/*/SKILL.md. Exits 0 and prints nothing when
clean. With no argument it also compares the guard's role lists with the role table (role_list_drift).
Exits 1 and names each file that sets a Haiku model, each agent file whose `model:` pin names a different
family than its role's row in the role table (pin_row_problem), each agent body that states the agent's own
model in fixed text or gives a report header a model slot with no line that names the source (body_problems),
and the model record
docs/decisions/agent-model-cap.md when its `lane session` row's effort cell does not start
with the guard's LANE_EFFORT.
"""
import glob
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
# One home for the role list: the guard's HAIKU_ROLES. Read it, never copy it.
_spec = importlib.util.spec_from_file_location("guard", os.path.join(ROOT, "hooks", "guard.py"))
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
HAIKU_ROLES = tuple(role.lower() for role in _guard.HAIKU_ROLES)
LANE_EFFORT = _guard.LANE_EFFORT
LANE_RECORD = os.path.join(*layout.path(ROOT, "decisions").split("/"), "agent-model-cap.md")
LANE_ROW = re.compile(r"^\|\s*lane session\b[^|]*\|[^|]*\|\s*([^|]*?)\s*\|\s*$", re.M)
MODEL_KEY = re.compile(r"^model\s*:\s*(.*)$", re.IGNORECASE)
# The self-model rules. An agent runs the model its spawn names, so its body must not state a model as its own. A
# sentence is a run of text up to `.`, `!` or `?` before a space, wrapped lines included. A chunk of sentences ends at
# a blank line or at a list, heading or table line, so one list item never joins the next.
MODEL_NAME = re.compile(r"\b(?:haiku|sonnet|opus)\b", re.IGNORECASE)
OWN_MODEL = re.compile(r"\byour\b(?:(?!\byour\b).)*?\bmodel\b", re.IGNORECASE | re.DOTALL)
HEADER_WORD = re.compile(r"\b(?:PASS|FAIL|PARTIAL|WIDE)\b")
MODEL_SLOT = re.compile(r"<model>|\bthe model\b", re.IGNORECASE)
# A backtick that opens straight onto the header word, with no backtick inside: a stray backtick earlier in the text
# opens no span here, as a pairing of backticks in order would have it.
HEADER_SPAN = re.compile(r"`(?:PASS|FAIL|PARTIAL|WIDE)\b[^`]*`")
SOURCE_PHRASE = re.compile(r"powered by the model named", re.IGNORECASE)
CHUNK_START = re.compile(r"\s*(?:[-*+]\s|\d+[.)]\s|#|\|)")
SENTENCE = re.compile(r"\S.*?(?:[.!?](?=\s|\Z)|\Z)", re.DOTALL)


def frontmatter(text: str):
    """Return the frontmatter lines, [] with no frontmatter, None when it never closes."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            return lines[1:end]
    return None


def haiku_model(text: str) -> str:
    for line in frontmatter(text) or []:
        found = MODEL_KEY.match(line)
        if found and "haiku" in found.group(1).lower():
            return found.group(1).strip()
    return ""


def scalar(raw: str) -> str:
    """A frontmatter value without its quotes or a trailing ` # comment`."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        close = raw.find(raw[0], 1)
        return raw[1:close] if close > 0 else raw[1:]
    return re.split(r"\s#", raw, maxsplit=1)[0].strip()


def pin_row_problem(text: str, table) -> str:
    """Why the file's `model:` pin differs from its role's row, or "" when it matches, has no pin, or its role has
    no row. The role is the frontmatter `name`, matched as the guard matches a spawn's role (role_name)."""
    keys = _guard.frontmatter_keys(frontmatter(text) or [])
    pin, name = scalar(keys.get("model", "")), scalar(keys.get("name", ""))
    row = table.get(_guard.role_name(table, name)) if table and name else None
    if not pin or row is None:
        return ""
    rank = _guard.role_model_rank(pin)
    if rank is not None and _guard.ROLE_MODEL_RANK[rank] == row:
        return ""
    return "model pin %r does not equal the role table's row %r for role %r (the pin must name the row's model)" % (
        pin, row, name)


def body_chunks(text: str):
    """The agent file's body as (first line number, text) chunks. The body starts after the closed frontmatter."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        start = next((n + 1 for n in range(1, len(lines)) if lines[n].strip() == "---"), 0)
    chunks, current = [], None
    for number in range(start, len(lines)):
        line = lines[number]
        if not line.strip():
            current = None
        elif current is None or CHUNK_START.match(line):
            current = [number + 1, [line]]
            chunks.append(current)
        else:
            current[1].append(line)
    return [(first, "\n".join(rows)) for first, rows in chunks]


def body_problems(text: str) -> list:
    """The (line, problem) pairs of an agent body that states the agent's own model in fixed text, or that has a report
    header with a model slot and no line that names where the model comes from (`powered by the model named`)."""
    found, slot_line = [], None
    sentences = [(first + chunk.count("\n", 0, hit.start()), hit.group())
                 for first, chunk in body_chunks(text) for hit in SENTENCE.finditer(chunk)]
    body = "\n".join(sentence for _, sentence in sentences)
    for line, sentence in sentences:
        own = OWN_MODEL.search(sentence)
        if own and MODEL_NAME.search(sentence):
            found.append((line + sentence.count("\n", 0, own.start()), "the body states the agent's own model "
                          "in fixed text. Name the model from the system prompt line, never from this file."))
        for span in HEADER_SPAN.finditer(sentence):
            if MODEL_NAME.search(span.group()):
                found.append((line + sentence.count("\n", 0, span.start()), "the report header %s names a model. "
                              "Use a <model> slot." % span.group()))
        word = HEADER_WORD.search(sentence)
        if slot_line is None and word and MODEL_SLOT.search(sentence):
            slot_line = line + sentence.count("\n", 0, word.start())
    if slot_line is not None and not SOURCE_PHRASE.search(" ".join(body.split())):
        found.append((slot_line, "the report header has a model slot, and no body line names the source with "
                      "`powered by the model named`."))
    return sorted(found)


def is_haiku_role(path: str) -> bool:
    return (os.path.basename(os.path.dirname(path)) == "agents"
            and os.path.splitext(os.path.basename(path))[0].lower() in HAIKU_ROLES)


def is_lane_record(path: str) -> bool:
    return os.path.abspath(path).endswith(os.sep + LANE_RECORD)


def lane_effort_problem(text: str) -> str:
    """Why the lane session row's effort cell is not the lane effort, or "" when it is."""
    rows = LANE_ROW.findall(text)
    if len(rows) != 1:
        return "needs one `lane session` row with a model and an effort cell, found %d" % len(rows)
    if not rows[0].startswith(LANE_EFFORT):
        return "the `lane session` row's effort cell must start with %r (the guard's LANE_EFFORT), found %r" % (
            LANE_EFFORT, rows[0])
    return ""


def role_list_problems() -> list:
    """The guard's role_list_drift lines for this repository, or one unknown line when the table or the agents
    folder cannot be read (verification-report-unknown-reads: unread is neither clear nor broken)."""
    try:
        list(_guard.role_agent_keys(ROOT))
        unread = _guard.role_model_table(ROOT) is None
    except OSError:
        unread = True
    if unread:
        return ["role lists: the role table or the agents folder could not be read, so drift is unknown."]
    return list(_guard.role_list_drift(ROOT))


def main(argv) -> int:
    files = argv or sorted(
        glob.glob(os.path.join(ROOT, "agents", "*.md"))
        + glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))
        + [os.path.join(ROOT, LANE_RECORD)]
    )
    bad = 0
    table = _guard.role_model_table(ROOT)  # None when unread: role_list_problems reports that, this rule stands down
    for path in files:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
        if is_lane_record(path):
            problem = lane_effort_problem(text)
            if problem:
                print("%s: %s." % (path, problem))
                bad = 1
        elif frontmatter(text) is None:
            print("%s: frontmatter never closes. Cannot read its model." % path)
            bad = 1
        elif haiku_model(text) and not is_haiku_role(path):
            print("%s: frontmatter sets a model below Sonnet. Sonnet is the floor." % path)
            bad = 1
        elif os.path.basename(os.path.dirname(path)) == "agents":
            problem = pin_row_problem(text, table)
            if problem:
                print("%s: %s." % (path, problem))
                bad = 1
            for line, problem in body_problems(text):
                print("%s:%d: %s" % (path, line, problem))
                bad = 1
    if not argv:  # the role lists belong to the whole repository, so a run on named files leaves them alone
        for line in role_list_problems():
            print(line)
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
