#!/usr/bin/env python3
"""Cases for the owner feedback inbox: the capture hook and the Stop guard. Standard library only,
and no test runner.

Run it from the repository root:

    python hooks/test_feedback_inbox.py

Every case runs the real script as a child process, the way the harness does. The payload goes in
on stdin as UTF-8 bytes. PYTHONUTF8 and PYTHONIOENCODING are unset in the child. CLAUDE_CONFIG_DIR,
HOME and USERPROFILE all point into a scratch folder, so no case touches the owner's ~/.claude.
Each case reads back the exit code, stdout, stderr and the files written.

Seams.

Capture: hooks/local_time.py (env LOCAL_TIME_UNDER_TEST overrides the path). A UserPromptSubmit
  hook. Stdin is one JSON object: hook_event_name, session_id, prompt, cwd. Stdout is one
  "Local time: ..." line. Exit 0. A write failure adds one stdout line; see below.
  - Every owner prompt is captured verbatim, in order. No word opens or closes capture: `fb`,
    `fb:` and `fb done` are plain text.
  - A notice is never captured: a prompt that starts with `<task-notification>` or
    `<system-reminder>` (shared_names.MACHINE_TAGS). A tag quoted mid-message is owner text.
  - A lone surrogate in the text (JSON escape `\\ud800`) is either saved with U+FFFD (the
    replacement character) in its place, or stdout carries a line that says `not saved`. Never
    silent. The inbox stays strict UTF-8.
  - State is per session_id. Another session's prompts are never captured.
  - `--agent` (a SubagentStart payload) prints the hookSpecificOutput JSON and never captures.
  - Fail open: empty stdin, non-JSON stdin, or a payload with no session_id gives exit 0, one
    Central line, and no file written.
  - Write failure: when the inbox cannot be written (a directory at its path, for example), stdout
    keeps the Local time line and adds one line that contains `not saved`. Exit 0.

Inbox: <CLAUDE_CONFIG_DIR>/handoffs/<session_id>.inbox.md, outside git. Format:

    ### 2026-10-13 10:04 CDT (UTC-05:00)
    ````
    owner prompt, verbatim, lines unchanged
    ````
    - fb-0958-2 [task] -> handoff
    - fb-0958-3 [note] -> noted

  - A block starts at a header line, outside a fence. The hook's header is `### ` and the Central
    stamp, for example `### 2026-10-13 10:04 CDT (UTC-05:00)`, or CST with `(UTC-06:00)`. Any other
    `### ` line, such as `### Notes`, is plain text: it starts no block, and it is no message with
    no items. The hook writes the header, the opener fence, the verbatim text and the closer fence.
    The session writes the item lines.
  - The fence is at least three backticks and longer than the longest backtick run in the text.
    Opener and closer are bare backtick lines. Lines inside a fence are never headers or items.
  - An item line starts with `- fb-` and follows its block's closer, before the next header.
    Shape: `- <id> [<kind>] -> <home>`. kind is one of ruling, task, question, note, standing.
    home is any non-empty text after `->`. For ruling and task, the home's first word is a path.

Guard: hooks/feedback_guard.py (env FEEDBACK_GUARD_UNDER_TEST overrides the path). A Stop hook. Stdin
  is one JSON object: hook_event_name, session_id, stop_hook_active, cwd. It reads the inbox and the
  handoff <CLAUDE_CONFIG_DIR>/handoffs/<session_id>.md. Exit 0 in every case. Stdout is one JSON
  object or nothing.
  - Bursts. A turn's messages are the ones captured since the last guard run. They are a burst when
    they are two or more, or one message with three or more non-blank lines or two or more bullet
    lines (`- `, `* `, `+ `, `1. `, `1) `). Only a burst's messages need items. A lone message of
    one or two plain lines never blocks, in any turn. A burst message with no items keeps blocking
    at later turn ends until it is jotted. The guard keeps its turn state beside the inbox, in
    <session_id>.inbox.turns. With no state file, every captured message counts as this turn's.
  - stop_hook_active true: exit 0, nothing on stdout. It still counts the turn's messages.
  - No inbox, or an empty inbox: nothing on stdout.
  - A block is {"decision": "block", "reason": ...}. The reason names each offending id, or the
    message by its Central stamp or the start of its text. Offences: a burst message with no
    items; an item with no kind, an unknown kind, or no home; an open standing item whose id is
    not in the handoff as a whole token. A missing handoff file means every open id is missing.
  - Tracked homes (decision owner-feedback-inbox, "Kinds and homes"). A ruling or task item, open
    or closed, names a path: relative to the repo of the payload's cwd, or absolute. The file sits
    under a home of its kind in lint/layout.json, read through lint/layout.py: ruling under the
    keys decisions, rules, claude-md or agents-md; task under todo, debts or
    debt-notes. Some branch's tree in that file's repo holds it. Else the reason names the id. The
    handoff never counts for these two kinds. A repo with no home of the kind gets a reason that
    names the layout keys, todo first for a task.
  - Fail open: when the cwd is not in a git repo, or the layout or the repo's extras file cannot
    be read, ruling and task homes pass unchecked and stdout carries one systemMessage line that
    starts "Feedback guard: ruling and task homes not checked".
  - A malformed item line is an offence: a `- fb-` line whose id is not a token, such as
    `- fb- [task] -> x` or a bare `- fb-`. The reason quotes the line's text after the leading
    `- `, for example `fb- [task] -> x`. The guard does not crash on it.
  - An item line that ends with `[closed]` is closed. Its id is not required in the handoff. Its
    kind and home are still checked, a ruling's or task's tracked home too.
  - An unreadable inbox (a directory at its path, or bytes that are not UTF-8) gives one block that
    names the inbox file. Why: a Stop hook's stderr does not reach the owner, so a silent pass would
    drop feedback. stop_hook_active still gives nothing, so the block costs one turn at most.
  - Another session's inbox is never read.

Reorient: hooks/precompact_handoff.py `--reorient` (env PRECOMPACT_HANDOFF_UNDER_TEST overrides the
  path). Each of its two messages ends with an inbox note, or with nothing:
  - open ids (ruling, task, standing) in the inbox:
    " Open feedback items: <ids>. Keep each standing item in the handoff, and give each ruling
    and task its tracked home: a decision record or rule, or the repo's todo or debt store."
  - None: the message is unchanged. An unreadable inbox gives no note, one stderr line, and the
    message still prints.
  - A malformed item line is never listed as an id. The other ids still print.

The expected strings are hardcoded here. The reader in this file follows the format above.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
REPO = os.path.dirname(HERE)
LT_PATH =os.environ.get("LOCAL_TIME_UNDER_TEST") or os.path.join(HERE, "local_time.py")
GUARD_PATH = os.environ.get("FEEDBACK_GUARD_UNDER_TEST") or os.path.join(HERE, "feedback_guard.py")
PRECOMPACT_PATH = os.environ.get("PRECOMPACT_HANDOFF_UNDER_TEST") or os.path.join(
    HERE, "precompact_handoff.py")
ROOT = tempfile.mkdtemp(prefix="feedback_inbox_cases_")
FAILED = []
RED_CASES = []
CASE_COUNT = [0]

CENTRAL = re.compile(r"Local time: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (CDT|CST) \(UTC-0[56]:00\)")
HEADER = re.compile(r"### (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (CDT|CST) \(UTC-0[56]:00\)")
STAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

# Owner text with the scanner traps: comment openers inside a string, a fake header, a fake item,
# an inner fence, a lone quote, several lines, and characters outside cp1252.
SCANNER = (
    "fb: scanner text, verbatim\n"
    "/* a comment opener inside a string */ and // a line comment opener\n"
    "# a line that starts with a hash\n"
    "### 2026-01-01 00:00 CST (UTC-06:00)\n"
    "- fb-0999-1 [task] -> handoff\n"
    "```\n"
    "Don't stop: a lone quote, then a fence above.\n"
    "Unicode: → and ✓ and café"
)
BLOCK_HEADER = "2026-10-13 10:04 CDT (UTC-05:00)"
JOTTED_ITEMS = (
    "- fb-0958-1 [ruling] -> decisions/a-ruling.md",
    "- fb-0958-2 [task] -> debts/a-task.md",
    "- fb-0958-3 [question] -> answered",
    "- fb-0958-4 [note] -> noted",
    "- fb-0958-5 [standing] -> handoff: process-only",
)
JOTTED_HANDOFF = "# Handoff\n- fb-0958-5 standing\n"



def check(name, cond, detail=""):
    if cond:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, " ".join(str(detail).split())[:600]))


# --------------------------------------------------------------------------- harness helpers

class Proc:
    def __init__(self, code, out, err):
        self.code, self.out, self.err = code, out, err

    def desc(self):
        return "rc=%s stdout=%r stderr=%r" % (self.code, self.out[-300:], self.err[-300:])


def new_cfg():
    CASE_COUNT[0] += 1
    base = os.path.join(ROOT, "case-%03d" % CASE_COUNT[0])
    cfg = os.path.join(base, "cfg")
    os.makedirs(cfg)
    return cfg


def run(path, raw, cfg, args=()):
    """Runs one hook script the way the harness does. Returns a Proc."""
    home = os.path.join(os.path.dirname(cfg), "home")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ)
    for name in ("PYTHONUTF8", "PYTHONIOENCODING", "CLAUDE_CONFIG_DIR", "LOCAL_TIME_NOW"):
        env.pop(name, None)
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=home, USERPROFILE=home)
    try:
        cp = subprocess.run([sys.executable, path, *args], input=raw, capture_output=True,
                            env=env, cwd=home, timeout=30)
    except subprocess.TimeoutExpired:
        return Proc(-1, "", "timed out after 30 s")
    return Proc(cp.returncode, cp.stdout.decode("utf-8", "replace"),
                cp.stderr.decode("utf-8", "replace"))


def payload(obj):
    """UTF-8 bytes, as the harness sends them. ensure_ascii is off, so the bytes are real UTF-8."""
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def capture(cfg, sid, prompt):
    return run(LT_PATH, payload({"hook_event_name": "UserPromptSubmit", "session_id": sid,
                                 "prompt": prompt, "cwd": cfg}), cfg)


def guard(cfg, sid, stop_active=False, cwd=None):
    """Runs the guard. `cwd` is the session's folder in the payload: the shared fixture repo unless
    a case names another."""
    return run(GUARD_PATH, payload({"hook_event_name": "Stop", "session_id": sid,
                                   "stop_hook_active": stop_active,
                                   "cwd": cwd or fixture_repo()}), cfg)


GIT_ID = ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
          "-c", "init.defaultBranch=main")


def git(where, *args):
    cp = subprocess.run(["git", *GIT_ID, "-C", where, *args], capture_output=True, timeout=30)
    if cp.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), cp.stderr.decode("utf-8", "replace")))


def make_repo(name, tracked=(), untracked=(), extras=None):
    """A git repo under this run's scratch folder. `tracked` files are committed on main, with
    the text "x"; `untracked` files are written and never added. `extras` (a string) is the
    repo's .claude/layout-extras.json, committed."""
    root = os.path.join(ROOT, "repos", name)
    os.makedirs(root)
    git(root, "init", "-q")
    files = list(tracked) + ([".claude/layout-extras.json"] if extras is not None else [])
    for rel in files:
        write_file(os.path.join(root, *rel.split("/")),
                   extras if rel == ".claude/layout-extras.json" else "x\n")
    write_file(os.path.join(root, "README.md"), "fixture\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixture")
    for rel in untracked:
        write_file(os.path.join(root, *rel.split("/")), "x\n")
    return root


FIXTURE = []


def fixture_repo():
    """The shared fixture repo: not rolled out to the layout, so its homes sit at the legacy
    paths claude-settings uses (decisions/, debts/), with a tracked decision and debt."""
    if not FIXTURE:
        FIXTURE.append(make_repo("fixture", tracked=(
            "decisions/a-ruling.md", "debts/a-task.md", "CLAUDE.md")))
    return FIXTURE[0]


def state_of(cfg, sid):
    return os.path.join(cfg, "state", "handoff", sid + ".json")


def state_tag(ok_state):
    return "ok state" if ok_state else "no state"


def reorient(cfg, sid, ok_state=False):
    """Runs `precompact_handoff.py --reorient` as SessionStart does. ok_state writes the state of a
    passing PreCompact run, so the message names a digest; otherwise the digest is missing."""
    if ok_state:
        digest = os.path.join(cfg, "state", "handoff", sid + ".digest.md")
        write_file(state_of(cfg, sid), json.dumps({"ok": True, "digest": digest}))
    return run(PRECOMPACT_PATH, payload({"hook_event_name": "SessionStart", "session_id": sid,
                                         "source": "compact", "cwd": cfg}), cfg,
               args=("--reorient",))


def ends_with_note(p, note):
    """Exit 0, one reorient message, and the message ends with `note` ("" when there is none)."""
    out = p.out.rstrip()  # Windows prints CRLF, so strip all trailing whitespace, not only "\n"
    return p.code == 0 and out.count("Context was compacted") == 1 and out.endswith(
        "continue the last task." + note)


def inbox_of(cfg, sid):
    return os.path.join(cfg, "handoffs", sid + ".inbox.md")


def handoff_of(cfg, sid):
    return os.path.join(cfg, "handoffs", sid + ".md")


def read_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_or_empty(path):
    return read_file(path) if os.path.exists(path) else ""


def write_file(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def append_file(path, text):
    current = read_file(path)
    if current and not current.endswith("\n"):
        current += "\n"
    write_file(path, current + text)


def ran_central(p):
    """The hook ran: exit 0 and one Central line on stdout. Every negative case needs this."""
    line = p.out.strip()
    return p.code == 0 and "\n" not in line and CENTRAL.fullmatch(line) is not None


def longest_run(text):
    return max((len(r) for r in re.findall(r"`+", text)), default=0)


def render_block(text, header=BLOCK_HEADER, items=()):
    """Writes one block in the format. Test fixtures use it, so the fence rule is exercised."""
    fence = "`" * max(3, longest_run(text) + 1)
    lines = ["### " + header, fence] + text.split("\n") + [fence] + list(items)
    return "\n".join(lines) + "\n"


def read_blocks(text):
    """Test-side reader of the inbox format. Returns [{header, fence, text, items}]."""
    blocks, cur, fence, body = [], None, None, []
    for line in text.split("\n"):
        if fence is not None:
            if re.fullmatch(r"`+", line) and len(line) >= len(fence):
                cur["text"], fence = "\n".join(body), None
            else:
                body.append(line)
        elif line.startswith("### "):
            cur = {"header": line, "fence": None, "text": None, "items": []}
            blocks.append(cur)
        elif cur is not None and cur["text"] is None and re.fullmatch(r"`{3,}", line):
            cur["fence"], fence, body = line, line, []
        elif cur is not None and cur["text"] is not None and line.startswith("- fb-"):
            cur["items"].append(line)
    return blocks


def captured_texts(cfg, sid):
    return [b["text"] for b in read_blocks(read_or_empty(inbox_of(cfg, sid)))]


def guard_json(p):
    try:
        obj = json.loads(p.out)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def is_block(obj):
    return obj is not None and obj.get("decision") == "block"


def block_reason(p):
    obj = guard_json(p)
    if is_block(obj) and isinstance(obj.get("reason"), str):
        return obj["reason"]
    return None


def stamp_of(header):
    return STAMP.search(header).group(0)


def names_message(reason, stamp, text):
    """A block names its message by the Central stamp in its header, or by the start of its text."""
    return stamp in reason or text[:20] in reason


def expect_silent(name, p):
    check(name, p.code == 0 and p.out.strip() == "", p.desc())


def expect_block(name, p, named=(), unnamed=()):
    reason = block_reason(p) or ""
    check(name + ": blocks", p.code == 0 and block_reason(p) is not None, p.desc())
    for n in named:
        check("%s: names %s" % (name, n), n in reason, reason)
    for n in unnamed:
        check("%s: does not name %s" % (name, n), n not in reason, reason)


# --------------------------------------------------------------------------- capture cases

def case_verbatim_scanner_text_is_fenced():
    cfg, sid = new_cfg(), "scanner"
    p = capture(cfg, sid, SCANNER)
    check("scanner text: hook ran", ran_central(p), p.desc())
    blocks = read_blocks(read_or_empty(inbox_of(cfg, sid)))
    check("scanner text: one block, text byte-exact",
          len(blocks) == 1 and blocks[0]["text"] == SCANNER, blocks)
    if not blocks:
        return
    check("scanner text: no phantom items from inside the fence", blocks[0]["items"] == [],
          blocks[0]["items"])
    fence = blocks[0]["fence"] or ""
    check("scanner text: fence is longer than the longest backtick run in the text",
          len(fence) > longest_run(SCANNER), fence)


def case_fail_open_writes_nothing():
    cases = (
        ("empty stdin", lambda cfg: b""),
        ("non-JSON stdin", lambda cfg: b"not json {"),
        ("no session_id", lambda cfg: payload({"hook_event_name": "UserPromptSubmit",
                                               "prompt": "fb: no session id", "cwd": cfg})),
    )
    for label, raw_of in cases:
        cfg = new_cfg()
        p = run(LT_PATH, raw_of(cfg), cfg)
        check("fail open, %s: exit 0 and one Central line" % label, ran_central(p), p.desc())
        files = [os.path.join(d, f) for d, _, fs in os.walk(cfg) for f in fs]
        check("fail open, %s: no file written" % label, files == [], files)


def not_saved_check(name, p):
    """Stdout is the Local time line, then a line that says the message was not saved."""
    lines = [ln.strip() for ln in p.out.splitlines() if ln.strip()]
    check("%s: exit 0, Local time line first" % name,
          p.code == 0 and bool(lines) and CENTRAL.fullmatch(lines[0]) is not None, p.desc())
    check("%s: a further stdout line says the message was not saved" % name,
          any("not saved" in ln.lower() for ln in lines[1:]), p.desc())


def case_capture_write_failure_says_not_saved():
    cfg, sid = new_cfg(), "write-fail"
    os.makedirs(inbox_of(cfg, sid))  # a directory at the inbox path: no write can land
    not_saved_check("write failure", capture(cfg, sid, "a message the inbox cannot take"))


# A lone surrogate, as the payload's JSON escape. json.dumps writes the escape: the bytes are ASCII.
LONE_SURROGATE = "a lone \ud800 surrogate in the middle of the burst"
SURROGATE_SAVED = "a lone \ufffd surrogate in the middle of the burst"


def case_lone_surrogate_is_saved_or_said_not_saved():
    cfg, sid = new_cfg(), "lone-surrogate"
    first = "the message before the surrogate"
    check("lone surrogate: the first message ran", ran_central(capture(cfg, sid, first)))
    raw = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": sid,
                      "prompt": LONE_SURROGATE, "cwd": cfg}).encode("ascii")
    p = run(LT_PATH, raw, cfg)
    lines = [ln.strip() for ln in p.out.splitlines() if ln.strip()]
    check("lone surrogate: exit 0, Local time line first",
          p.code == 0 and bool(lines) and CENTRAL.fullmatch(lines[0]) is not None, p.desc())
    inbox = inbox_of(cfg, sid)
    strict = True
    if os.path.exists(inbox):
        try:
            with open(inbox, "rb") as f:
                f.read().decode("utf-8")
        except UnicodeDecodeError:
            strict = False
    check("lone surrogate: an inbox that is written is strict UTF-8", strict, ascii(inbox))
    texts = captured_texts(cfg, sid) if strict else None
    saved = texts == [first, SURROGATE_SAVED]
    told = any("not saved" in ln.lower() for ln in lines[1:])
    check("lone surrogate: saved with U+FFFD, or stdout says not saved (never silent)",
          saved or told, "saved=%s told=%s captured=%s %s"
          % (saved, told, ascii(texts), p.desc()))


def agent_ok(p):
    try:
        hso = json.loads(p.out)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return False
    return (p.code == 0 and hso.get("hookEventName") == "SubagentStart"
            and CENTRAL.fullmatch(str(hso.get("additionalContext", ""))) is not None)


def sub_payload(sid, prompt, cfg):
    return payload({"hook_event_name": "SubagentStart", "session_id": sid,
                    "agent_type": "test-author", "prompt": prompt, "cwd": cfg})


def case_agent_never_captures():
    cfg, sid = new_cfg(), "sub"
    check("agent: owner prompt ran", ran_central(capture(cfg, sid, "owner prompt")))
    before = read_or_empty(inbox_of(cfg, sid))
    p = run(LT_PATH, sub_payload(sid, "an agent's own prompt", cfg), cfg, args=("--agent",))
    check("agent: prints the SubagentStart JSON", agent_ok(p), p.desc())
    check("agent: the inbox is unchanged by an agent prompt",
          before != "" and read_or_empty(inbox_of(cfg, sid)) == before, "changed")
    q = run(LT_PATH, sub_payload("sub-only", "an agent's prompt, no owner yet", cfg), cfg,
            args=("--agent",))
    check("agent: a second payload prints the SubagentStart JSON", agent_ok(q), q.desc())
    check("agent: an agent prompt alone writes no inbox",
          not os.path.exists(inbox_of(cfg, "sub-only")), "inbox exists")


def case_sessions_are_isolated():
    cfg = new_cfg()
    check("isolation: session a ran", ran_central(capture(cfg, "iso-a", "a's message")))
    check("isolation: session b ran", ran_central(capture(cfg, "iso-b", "b's message")))
    check("isolation: each message lands in its own session's inbox only",
          captured_texts(cfg, "iso-a") == ["a's message"]
          and captured_texts(cfg, "iso-b") == ["b's message"],
          (captured_texts(cfg, "iso-a"), captured_texts(cfg, "iso-b")))


# --------------------------------------------------------------------------- guard cases

def case_guard_no_inbox_and_empty_inbox_pass_silently():
    cfg = new_cfg()
    expect_silent("guard: no inbox file passes silently", guard(cfg, "no-inbox"))
    write_file(inbox_of(cfg, "empty-inbox"), "")
    expect_silent("guard: empty inbox passes silently", guard(cfg, "empty-inbox"))


def case_guard_all_jotted_passes_silently():
    cfg, sid = new_cfg(), "jotted"
    write_file(inbox_of(cfg, sid), render_block("fb: a jotted burst\nsecond line",
                                                items=JOTTED_ITEMS))
    write_file(handoff_of(cfg, sid), JOTTED_HANDOFF)
    expect_silent("guard: all jotted, open ids in the handoff, passes silently", guard(cfg, sid))


def case_guard_message_without_items_blocks_and_names_it():
    cfg, sid = new_cfg(), "no-items"
    text_b = "second message, no items jotted"
    write_file(inbox_of(cfg, sid),
               render_block("first message", header="2026-10-13 10:04 CDT (UTC-05:00)",
                            items=("- fb-0958-2 [standing] -> handoff",))
               + render_block(text_b, header="2026-10-13 10:09 CDT (UTC-05:00)"))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    p = guard(cfg, sid)
    reason = block_reason(p) or ""
    expect_block("guard: message with no items", p)
    check("guard: the reason names the message with no items",
          names_message(reason, "2026-10-13 10:09", text_b), reason)
    check("guard: the reason does not name the jotted first message",
          "2026-10-13 10:04" not in reason, reason)


BAD_ITEMS = (
    ("no kind", "- fb-0958-4 -> handoff", "fb-0958-4"),
    ("unknown kind", "- fb-0958-5 [bug] -> handoff", "fb-0958-5"),
    ("no home", "- fb-0958-6 [task]", "fb-0958-6"),
    ("empty home", "- fb-0958-7 [note] ->", "fb-0958-7"),
)


def case_guard_item_without_kind_or_home_blocks():
    for label, item, item_id in BAD_ITEMS:
        cfg, sid = new_cfg(), "bad-" + item_id
        write_file(inbox_of(cfg, sid), render_block("item with %s" % label, items=(item,)))
        expect_block("guard: item with %s" % label, guard(cfg, sid), named=(item_id,))


def case_guard_open_item_missing_from_handoff_blocks():
    cfg, sid = new_cfg(), "open-missing"
    items = ("- fb-0958-2 [standing] -> handoff", "- fb-0958-3 [standing] -> handoff",
             "- fb-0958-4 [standing] -> handoff")
    write_file(inbox_of(cfg, sid), render_block("open ids burst", items=items))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 standing\n")
    expect_block("guard: open standing items missing from the handoff", guard(cfg, sid),
                 named=("fb-0958-3", "fb-0958-4"), unnamed=("fb-0958-2",))
    expect_silent("guard: stop_hook_active gives nothing, even with missing open ids",
                  guard(cfg, sid, stop_active=True))


def case_guard_id_match_is_a_whole_token():
    cfg, sid = new_cfg(), "boundary"
    write_file(inbox_of(cfg, sid),
               render_block("boundary", items=("- fb-0958-2 [standing] -> handoff",)))
    write_file(handoff_of(cfg, sid), "- fb-0958-20 task, a different item\n")
    expect_block("guard: fb-0958-20 in the handoff does not count for fb-0958-2", guard(cfg, sid),
                 named=("fb-0958-2",))


def case_guard_handoff_rewrite_that_drops_an_item_blocks():
    cfg, sid = new_cfg(), "rewrite"
    write_file(inbox_of(cfg, sid), render_block(
        "two open items", items=("- fb-0958-2 [standing] -> handoff",
                                 "- fb-0958-3 [standing] -> handoff")))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 standing, kept\n")
    expect_block("guard: a handoff rewrite that drops fb-0958-3 blocks", guard(cfg, sid),
                 named=("fb-0958-3",), unnamed=("fb-0958-2",))


def case_guard_missing_handoff_counts_every_open_id_missing():
    cfg, sid = new_cfg(), "no-handoff"
    write_file(inbox_of(cfg, sid), render_block("no handoff yet",
                                                items=("- fb-0958-2 [standing] -> handoff",)))
    expect_block("guard: open standing item with no handoff file blocks", guard(cfg, sid),
                 named=("fb-0958-2",))


def case_guard_scanner_text_yields_no_phantom_block_or_item():
    cfg, sid = new_cfg(), "scanner-guard"
    write_file(inbox_of(cfg, sid), render_block(SCANNER, header=BLOCK_HEADER, items=()))
    p = guard(cfg, sid)
    reason = block_reason(p) or ""
    expect_block("guard: scanner text with no items blocks", p)
    check("guard: the reason names the scanner message by its stamp or text",
          names_message(reason, "2026-10-13 10:04", SCANNER), reason)
    check("guard: the fake item inside the fence is not an open item", "fb-0999-1" not in reason,
          reason)
    check("guard: the fake header inside the fence is not a block", "2026-01-01" not in reason,
          reason)


def case_guard_scanner_text_with_real_items_passes_silently():
    cfg, sid = new_cfg(), "scanner-real"
    write_file(inbox_of(cfg, sid), render_block(SCANNER, items=("- fb-0958-2 [standing] -> handoff",)))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    expect_silent("guard: scanner text with real items passes (fake fb-0999-1 is not read)",
                  guard(cfg, sid))


def case_guard_malformed_item_line_blocks_and_names_it():
    cfg, sid = new_cfg(), "malformed-item"
    write_file(inbox_of(cfg, sid), render_block("malformed item beside a good one", items=(
        "- fb- [task] -> x", "- fb-0958-2 [standing] -> handoff")))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 standing\n")
    expect_block("guard: malformed `- fb- [task] -> x` beside a handed-off item", guard(cfg, sid),
                 named=("fb- [task] -> x",), unnamed=("fb-0958-2",))
    cfg, sid = new_cfg(), "malformed-bare"
    write_file(inbox_of(cfg, sid), render_block("a bare fb- line", items=("- fb-",)))
    expect_block("guard: bare `- fb-` line", guard(cfg, sid), named=("fb-",))


def case_guard_closed_item_is_not_required_in_handoff():
    cfg, sid = new_cfg(), "closed-item"
    write_file(inbox_of(cfg, sid), render_block("closed standing, task and ruling", items=(
        "- fb-0958-1 [standing] -> handoff: done [closed]",
        "- fb-0958-2 [task] -> debts/a-task.md [closed]",
        "- fb-0958-3 [ruling] -> decisions/a-ruling.md [closed]")))
    write_file(handoff_of(cfg, sid), "# Handoff\n")
    expect_silent("guard: closed items with good homes, missing from the handoff, pass silently",
                  guard(cfg, sid))
    cfg, sid = new_cfg(), "closed-and-open"
    write_file(inbox_of(cfg, sid), render_block("one closed, one open", items=(
        "- fb-0958-2 [standing] -> handoff: done [closed]", "- fb-0958-4 [standing] -> handoff")))
    write_file(handoff_of(cfg, sid), "# Handoff\n")
    expect_block("guard: open standing item still required beside a closed one", guard(cfg, sid),
                 named=("fb-0958-4",), unnamed=("fb-0958-2",))


def case_guard_notes_heading_is_plain_text():
    cfg, sid = new_cfg(), "notes-heading"
    write_file(inbox_of(cfg, sid), render_block("jotted burst", items=(
        "- fb-0958-2 [standing] -> handoff",)) + "### Notes\nsome notes the session wrote by hand\n")
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    expect_silent("guard: a ### Notes heading after a jotted message passes silently",
                  guard(cfg, sid))
    cfg, sid = new_cfg(), "notes-only"
    write_file(inbox_of(cfg, sid), "### Notes\nno captured message here\n")
    expect_silent("guard: an inbox with only a ### Notes heading passes silently", guard(cfg, sid))


def case_guard_unreadable_inbox_blocks_and_names_the_file():
    cfg, sid = new_cfg(), "unreadable-dir"
    os.makedirs(inbox_of(cfg, sid))
    expect_block("guard: unreadable inbox (a directory) blocks", guard(cfg, sid),
                 named=(os.path.basename(inbox_of(cfg, sid)),))

    cfg, sid = new_cfg(), "unreadable-bytes"
    os.makedirs(os.path.dirname(inbox_of(cfg, sid)), exist_ok=True)
    with open(inbox_of(cfg, sid), "wb") as f:
        f.write(b"### 2026-10-13 10:04 CDT (UTC-05:00)\n\xff\xfe\x80 not UTF-8\n")
    expect_block("guard: unreadable inbox (bytes that are not UTF-8) blocks", guard(cfg, sid),
                 named=(os.path.basename(inbox_of(cfg, sid)),))
    expect_silent("guard: unreadable inbox with stop_hook_active gives nothing",
                  guard(cfg, sid, stop_active=True))


def case_guard_reads_only_its_own_session():
    cfg = new_cfg()
    write_file(inbox_of(cfg, "own"),
               render_block("own jotted", items=("- fb-0958-2 [standing] -> handoff",)))
    write_file(handoff_of(cfg, "own"), "- fb-0958-2 task\n")
    write_file(inbox_of(cfg, "other"),
               render_block("other incomplete", items=("- fb-0958-9 [ruling] -> NO HOME YET",)))
    os.makedirs(inbox_of(cfg, "other-bad"))
    expect_silent("guard: own session passes; other sessions' inboxes do not block it",
                  guard(cfg, "own"))


# --------------------------------------------------------------------------- tracked homes

FAIL_OPEN = "Feedback guard: ruling and task homes not checked"


def homed(cfg, sid, items, handoff_ids=(), cwd=None):
    """Writes one jotted message and a handoff that holds `handoff_ids`, then runs the guard."""
    write_file(inbox_of(cfg, sid), render_block("homes burst", items=items))
    write_file(handoff_of(cfg, sid), "# Handoff\n" + "".join("- %s\n" % i for i in handoff_ids))
    return guard(cfg, sid, cwd=cwd)


def fail_open_line(p):
    obj = guard_json(p)
    msg = (obj or {}).get("systemMessage") or ""
    return [ln for ln in msg.splitlines() if ln.startswith(FAIL_OPEN)]


def case_guard_ruling_homed_to_handoff_blocks():
    for label, item in (("NO HOME YET", "- fb-1 [ruling] -> handoff: NO HOME YET"),
                        ("the handoff path", "- fb-1 [ruling] -> handoff"),
                        ("closed, NO HOME YET", "- fb-1 [ruling] -> NO HOME YET [closed]")):
        cfg = new_cfg()
        expect_block("homes: a ruling homed to %s blocks, though its id is in the handoff" % label,
                     homed(cfg, "r-handoff", (item,), handoff_ids=("fb-1",)), named=("fb-1",))


def case_guard_task_homed_to_untracked_file_blocks():
    repo = make_repo("untracked", tracked=("debts/old.md",), untracked=("debts/new.md",))
    cfg = new_cfg()
    expect_block("homes: a task homed to an untracked debt file blocks",
                 homed(cfg, "t-untracked", ("- fb-2 [task] -> debts/new.md",),
                       handoff_ids=("fb-2",), cwd=repo), named=("fb-2",))
    cfg = new_cfg()
    expect_block("homes: a task homed to a missing file blocks",
                 homed(cfg, "t-missing", ("- fb-2 [task] -> debts/none.md",), cwd=repo),
                 named=("fb-2",))


def case_guard_home_outside_its_kind_blocks():
    cfg = new_cfg()
    expect_block("homes: a ruling homed to a tracked file outside the ruling homes blocks",
                 homed(cfg, "r-readme", ("- fb-3 [ruling] -> README.md",)), named=("fb-3",))
    cfg = new_cfg()
    expect_block("homes: a task homed to a decision record blocks",
                 homed(cfg, "t-decision", ("- fb-3 [task] -> decisions/a-ruling.md",)),
                 named=("fb-3",))


def case_guard_tracked_homes_pass_without_the_handoff():
    cfg = new_cfg()
    expect_silent("homes: a ruling homed to a tracked decision passes, id not in the handoff",
                  homed(cfg, "r-tracked", ("- fb-4 [ruling] -> decisions/a-ruling.md",)))
    cfg = new_cfg()
    expect_silent("homes: wrapped and anchored homes pass (backticks, #anchor, trailing text)",
                  homed(cfg, "r-forms", (
                      "- fb-4 [ruling] -> `CLAUDE.md#rule:some-anchor`",
                      "- fb-5 [task] -> debts/a-task.md: the second half",)))
    lane = make_repo("lane", tracked=("decisions/x.md",))
    git(lane, "checkout", "-q", "-b", "lane")
    write_file(os.path.join(lane, "decisions", "new-ruling.md"), "x\n")
    git(lane, "add", "-A")
    git(lane, "commit", "-q", "-m", "lane record")
    git(lane, "checkout", "-q", "main")
    cfg = new_cfg()
    expect_silent("homes: a record committed on a lane branch only, by absolute path, passes",
                  homed(cfg, "r-lane", ("- fb-6 [ruling] -> %s" % os.path.join(
                      lane, "decisions", "new-ruling.md"),)))


def case_guard_standing_homed_to_handoff_passes():
    cfg = new_cfg()
    expect_silent("homes: a standing item homed to the handoff, id in it, passes (false alarm)",
                  homed(cfg, "s-handoff", ("- fb-7 [standing] -> handoff: process-only",),
                        handoff_ids=("fb-7",)))


def case_guard_task_home_from_the_todo_kind():
    repo = make_repo("rolled", tracked=("docs/todo.md", "docs/decisions/r.md"), extras='{"kinds": {}, "rolled-out": true}')
    cfg = new_cfg()
    expect_silent("homes: a task homed to the layout's todo kind passes",
                  homed(cfg, "t-todo", ("- fb-8 [task] -> docs/todo.md",
                                        "- fb-9 [ruling] -> docs/decisions/r.md"), cwd=repo))
    kept = make_repo("q_max", tracked=("specs/todo.md",))
    git(kept, "remote", "add", "origin", "https://github.com/shivinate7/q_max.git")
    cfg = new_cfg()
    expect_silent("homes: a task homed to the todo path legacy-repos keeps for its repo passes",
                  homed(cfg, "t-kept", ("- fb-8 [task] -> specs/todo.md",), cwd=kept))
    moved = make_repo("extras-todo", tracked=("tasks.md",),
                      extras=json.dumps({"kinds": {"todo": {"path": "tasks.md"}}, "rolled-out": True}))
    cfg = new_cfg()
    p = homed(cfg, "t-moved", ("- fb-8 [task] -> tasks.md",), cwd=moved)
    check("homes: an extras file that moves the todo kind is a layout fault, so the check stands down",
          block_reason(p) is None and len(fail_open_line(p)) == 1, p.desc())
    bare = make_repo("no-task-home", tracked=("decisions/r.md",))
    cfg = new_cfg()
    p = homed(cfg, "t-none", ("- fb-8 [task] -> TODO.md",), cwd=bare)
    expect_block("homes: a repo with no task home blocks", p, named=("fb-8", "todo"))


def case_guard_unreadable_layout_fails_open_with_one_line():
    cfg = new_cfg()
    p = homed(cfg, "no-repo", ("- fb-10 [ruling] -> decisions/a.md",), cwd=cfg)
    check("homes: a cwd outside any git repo does not block", block_reason(p) is None, p.desc())
    check("homes: a cwd outside any git repo says so in one line", len(fail_open_line(p)) == 1,
          p.desc())
    repo = make_repo("bad-extras", tracked=("decisions/r.md",), extras="{not json")
    cfg = new_cfg()
    p = homed(cfg, "bad-extras", ("- fb-10 [ruling] -> decisions/r.md",), cwd=repo)
    check("homes: an unreadable extras file does not block", block_reason(p) is None, p.desc())
    check("homes: an unreadable extras file says so in one line", len(fail_open_line(p)) == 1,
          p.desc())
    cfg = new_cfg()
    p = homed(cfg, "no-repo-standing", ("- fb-11 [standing] -> handoff",), cwd=cfg)
    check("homes: no ruling or task item, no fail-open line", fail_open_line(p) == [], p.desc())


# --------------------------------------------------------------------------- reorient note

KEEP = (" Keep each standing item in the handoff, and give each ruling and task its tracked home:"
        " a decision record or rule, or the repo's todo or debt store.")


def case_reorient_lists_open_items_only():
    cfg = new_cfg()
    sid = "reo-items"
    write_file(inbox_of(cfg, sid), render_block(SCANNER, items=JOTTED_ITEMS))
    note = " Open feedback items: fb-0958-1, fb-0958-2, fb-0958-5." + KEEP
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        tag = state_tag(ok_state)
        check("reorient items (%s): open ids in file order, in the message" % tag,
              ends_with_note(p, note), p.desc())
        check("reorient items (%s): question and note ids are not listed" % tag,
              "fb-0958-3" not in p.out and "fb-0958-4" not in p.out, p.desc())
        check("reorient items (%s): the fenced fake item is not listed" % tag,
              "fb-0999-1" not in p.out, p.desc())


def case_reorient_malformed_line_keeps_the_note():
    cfg, sid = new_cfg(), "reo-malformed"
    write_file(inbox_of(cfg, sid), render_block("burst with malformed lines", items=(
        "- fb- [task] -> x", "- fb-0958-2 [task] -> handoff", "- fb-",
        "- fb-0958-3 [ruling] -> NO HOME YET")))
    note = " Open feedback items: fb-0958-2, fb-0958-3." + KEEP
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        tag = state_tag(ok_state)
        check("reorient malformed (%s): good open ids still print" % tag,
              ends_with_note(p, note), p.desc())
        check("reorient malformed (%s): the note does not fail on stderr" % tag,
              "inbox note failed" not in p.err, p.desc())


def case_reorient_nothing_when_no_open_items():
    cfg = new_cfg()  # no inbox file at all
    sid = "reo-absent"
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        check("reorient absent (%s): the message is unchanged" % state_tag(ok_state),
              ends_with_note(p, ""), p.desc())
    cfg2 = new_cfg()  # an inbox with question and note items only
    write_file(inbox_of(cfg2, sid), render_block("jotted only", items=(
        "- fb-0958-3 [question] -> answered", "- fb-0958-4 [note] -> noted")))
    p = reorient(cfg2, sid)
    check("reorient no open items (no state): the message is unchanged", ends_with_note(p, ""),
          p.desc())


def case_reorient_unreadable_inbox_prints_message_and_one_stderr_line():
    for label in ("a directory at its path", "bytes that are not UTF-8"):
        cfg = new_cfg()
        sid = "reo-unreadable"
        path = inbox_of(cfg, sid)
        if label.startswith("a directory"):
            os.makedirs(path)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(b"\xff\xfe- fb-0958-2 [task] -> handoff\n")
        for ok_state in (False, True):
            p = reorient(cfg, sid, ok_state)
            err = [ln for ln in p.err.splitlines() if ln.strip()]
            name = "reorient unreadable (%s, %s)" % (label, state_tag(ok_state))
            check("%s: the message prints, with no note" % name, ends_with_note(p, ""), p.desc())
            check("%s: one stderr line names the failure" % name,
                  len(err) == 1 and "inbox note failed" in err[0], p.desc())


# --------------------------------------------------------------------------- capture-all and burst cases

NOTICE_TASK = ("<task-notification>\n<task-id>a1b2c3</task-id>\n<status>completed</status>\n"
               "<summary>Agent \"lint sweep\" completed</summary>\n"
               "<result>All 12 files pass.</result>\n</task-notification>")
NOTICE_REMINDER = "<system-reminder>\nThe task tools have not been used recently.\n</system-reminder>"


def case_every_owner_message_is_captured():
    """No magic words: every owner prompt is saved, in order, verbatim. `fb` forms are plain text."""
    cfg, sid = new_cfg(), "every"
    texts = ["plain owner prompt", "fb: an old opener form", "fb done", "x fb and fbi",
             "fb done, more text"]
    for text in texts:
        p = capture(cfg, sid, text)
        check("every: hook ran for %r" % text, ran_central(p), p.desc())
    check("every: each prompt is captured in order, verbatim", captured_texts(cfg, sid) == texts,
          captured_texts(cfg, sid))
    blocks = read_blocks(read_or_empty(inbox_of(cfg, sid)))
    check("every: each header is a Central stamp", bool(blocks) and all(
        HEADER.fullmatch(b["header"]) for b in blocks), [b["header"] for b in blocks])
    check("every: no items yet (the session jots them)",
          bool(blocks) and all(b["items"] == [] for b in blocks), blocks)
    check("every: no open marker file is written",
          not os.path.exists(os.path.join(cfg, "handoffs", sid + ".inbox.open")), "marker exists")


def case_notices_are_never_captured():
    for label, notice in (("task-notification", NOTICE_TASK), ("system-reminder", NOTICE_REMINDER)):
        cfg, sid = new_cfg(), "notice-" + label
        p = capture(cfg, sid, notice)
        check("notice %s: hook ran" % label, ran_central(p), p.desc())
        check("notice %s: not saved" % label, not os.path.exists(inbox_of(cfg, sid)),
              captured_texts(cfg, sid))
        capture(cfg, sid, "owner reply after the notice")
        check("notice %s: the next owner prompt is saved" % label,
              captured_texts(cfg, sid) == ["owner reply after the notice"], captured_texts(cfg, sid))
        expect_silent("notice %s: a notice is not a second message of a burst" % label,
                      guard(cfg, sid))
    cfg, sid = new_cfg(), "notice-quoted"
    quoted = "the log shows a <task-notification> tag I did not expect; look into it"
    capture(cfg, sid, quoted)
    check("notice quoted mid-message: owner text, so it is captured",
          captured_texts(cfg, sid) == [quoted], captured_texts(cfg, sid))


def turn(cfg, sid, *prompts):
    """Captures each prompt, then runs the guard once, as one turn."""
    for text in prompts:
        p = capture(cfg, sid, text)
        check("turn: hook ran for %r" % text[:40], ran_central(p), p.desc())
    return guard(cfg, sid)


def case_one_line_messages_never_trigger_the_guard():
    for sid, text in (("one-plain", "please also run the lint"),
                      ("one-fb", "fb: the old opener on one line"),
                      ("one-fb-done", "fb: a note\nfb done"),
                      ("one-bullet", "- one bullet only"),
                      ("two-lines", "first line\n\n\nsecond line after blanks")):
        cfg = new_cfg()
        expect_silent("non-burst %s: a lone short message passes" % sid, turn(cfg, sid, text))
    cfg, sid = new_cfg(), "one-per-turn"
    for n in range(3):
        expect_silent("non-burst: one-line message %d, alone in its turn, passes" % n,
                      turn(cfg, sid, "one-line message %d" % n))


def case_two_messages_in_a_turn_are_a_burst():
    cfg, sid = new_cfg(), "burst-two"
    p = turn(cfg, sid, "first short note", "second short note")
    expect_block("burst of two: blocks", p, named=("first short note", "second short note"))
    cfg, sid = new_cfg(), "burst-after-quiet"
    expect_silent("burst after a quiet turn: the quiet turn passes", turn(cfg, sid, "earlier note"))
    p = turn(cfg, sid, "burst one", "burst two")
    expect_block("burst after a quiet turn: the burst blocks", p, named=("burst one", "burst two"),
                 unnamed=("earlier note",))


def case_long_or_bulleted_message_is_a_burst():
    for sid, text in (("three-lines", "line one\nline two\nline three"),
                      ("dash-bullets", "two fixes\n- a\n- b"),
                      ("bullets-only", "- a\n* b"),
                      ("numbered", "1. first\n2) second")):
        cfg = new_cfg()
        p = turn(cfg, sid, text)
        expect_block("burst %s: blocks" % sid, p)
        block = read_blocks(read_file(inbox_of(cfg, sid)))[0]
        check("burst %s: the reason names the message" % sid,
              names_message(block_reason(p) or "", stamp_of(block["header"]), text), block_reason(p))


def case_burst_jotted_passes():
    cfg, sid = new_cfg(), "burst-jotted"
    for text in ("first short note", "second short note"):
        capture(cfg, sid, text)
    inbox = inbox_of(cfg, sid)
    s = read_file(inbox).split("\n")
    out, closers = [], 0
    for ln in s:
        out.append(ln)
        if ln == "```":
            closers += 1
            if closers % 2 == 0:
                out.append("- fb-%d [note] -> noted" % closers)
    write_file(inbox, "\n".join(out))
    expect_silent("burst jotted: every message has an item, so it passes", guard(cfg, sid))


def case_unjotted_burst_keeps_blocking_in_later_turns():
    cfg, sid = new_cfg(), "burst-later"
    expect_block("later: the burst blocks", turn(cfg, sid, "burst one", "burst two"))
    expect_silent("later: stop_hook_active passes", guard(cfg, sid, stop_active=True))
    p = turn(cfg, sid, "a short note in the next turn")
    expect_block("later: the unjotted burst still blocks", p, named=("burst one", "burst two"),
                 unnamed=("a short note in the next",))


def case_stop_hook_active_still_counts_the_turn():
    cfg, sid = new_cfg(), "active-counts"
    capture(cfg, sid, "one short note")
    expect_silent("active: stop_hook_active passes", guard(cfg, sid, stop_active=True))
    expect_silent("active: the next turn's one short note is not joined to the last turn's",
                  turn(cfg, sid, "another short note"))


def case_damaged_turn_state_counts_every_message():
    cfg, sid = new_cfg(), "damaged-state"
    expect_silent("damaged: a lone note passes", turn(cfg, sid, "first short note"))
    write_file(os.path.join(cfg, "handoffs", sid + ".inbox.turns"), "{not json")
    p = turn(cfg, sid, "second short note")
    expect_block("damaged: with no readable state, both messages count as one turn", p,
                 named=("first short note", "second short note"))


# Row tables. A row is one case body from above. A row that raises is red and names
# itself, so it cannot hide behind its table.
def run_rows(rows):
    for body in rows:
        try:
            body()
        except Exception as exc:
            check("%s: case ran" % body.__name__, False, "%s: %s" % (type(exc).__name__, exc))


def table_guard_handoff_drops():
    run_rows((case_guard_open_item_missing_from_handoff_blocks,
              case_guard_handoff_rewrite_that_drops_an_item_blocks,
              case_guard_missing_handoff_counts_every_open_id_missing))


def table_guard_scanner_text():
    run_rows((case_guard_scanner_text_yields_no_phantom_block_or_item,
              case_guard_scanner_text_with_real_items_passes_silently))


def table_reorient_forms():
    run_rows((case_reorient_lists_open_items_only, case_reorient_malformed_line_keeps_the_note,
              case_reorient_nothing_when_no_open_items))


CASES = (
    case_every_owner_message_is_captured,
    case_notices_are_never_captured,
    case_one_line_messages_never_trigger_the_guard,
    case_two_messages_in_a_turn_are_a_burst,
    case_long_or_bulleted_message_is_a_burst,
    case_burst_jotted_passes,
    case_unjotted_burst_keeps_blocking_in_later_turns,
    case_stop_hook_active_still_counts_the_turn,
    case_damaged_turn_state_counts_every_message,
    case_verbatim_scanner_text_is_fenced,
    case_fail_open_writes_nothing,
    case_capture_write_failure_says_not_saved,
    case_lone_surrogate_is_saved_or_said_not_saved,
    case_agent_never_captures,
    case_sessions_are_isolated,
    case_guard_no_inbox_and_empty_inbox_pass_silently,
    case_guard_all_jotted_passes_silently,
    case_guard_message_without_items_blocks_and_names_it,
    case_guard_item_without_kind_or_home_blocks,
    case_guard_malformed_item_line_blocks_and_names_it,
    table_guard_handoff_drops,
    case_guard_closed_item_is_not_required_in_handoff,
    case_guard_id_match_is_a_whole_token,
    table_guard_scanner_text,
    case_guard_notes_heading_is_plain_text,
    case_guard_unreadable_inbox_blocks_and_names_the_file,
    case_guard_reads_only_its_own_session,
    case_guard_ruling_homed_to_handoff_blocks,
    case_guard_task_homed_to_untracked_file_blocks,
    case_guard_home_outside_its_kind_blocks,
    case_guard_tracked_homes_pass_without_the_handoff,
    case_guard_standing_homed_to_handoff_passes,
    case_guard_task_home_from_the_todo_kind,
    case_guard_unreadable_layout_fails_open_with_one_line,
    table_reorient_forms,
    case_reorient_unreadable_inbox_prints_message_and_one_stderr_line,
)


def run_case(case):
    before = len(FAILED)
    try:
        case()
    except Exception as exc:  # a case that cannot run is red, never silently green
        check("%s: case ran" % case.__name__, False, "%s: %s" % (type(exc).__name__, exc))
    if len(FAILED) > before:
        RED_CASES.append(case.__name__)


def main():
    try:
        for case in CASES:
            run_case(case)
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if RED_CASES:
        print("test_feedback_inbox FAIL: %d of %d cases red" % (len(RED_CASES), len(CASES)))
        return 1
    print("test_feedback_inbox PASS: all %d cases green" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
