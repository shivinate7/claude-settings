#!/usr/bin/env python3
"""Cases for the owner feedback inbox: the capture hook and the Stop gate. Standard library only,
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
  - While closed, a prompt whose first word is `fb` or `fb:` opens capture, and the opening prompt
    is captured. Near-misses of the close form open nothing: `fb: done`, `fb  done` (two spaces),
    a tab in place of the space in `fb done`, and `fb - done`. Plain `fb done` opens nothing.
  - While closed, a prompt that starts with `fb done` or `fb: done` opens nothing, even with more
    text after it (`fb done, more text`). That text is a new message to the session, not feedback.
  - A prompt that opens with `fb` and ends with a line `fb done` saves the note and closes capture
    in that same prompt: no open marker remains, and the next prompt is not saved.
  - While open, a prompt that starts with `fb done` or `fb: done` closes capture and is not
    captured, and neither is any text after those words. Surrounding
    whitespace, trailing punctuation and letter case do not matter: `fb done.`, `FB done`,
    `fb done now` and `fb done, also we should ...` all close. `fb  done` (two spaces) closes too.
    `fb - done` does not close.
  - While open, every owner prompt is captured verbatim, including `x fb` and `fbi ...`. Neither
    closes capture.
  - While closed, only the opener is captured; every other prompt is dropped.
  - A notice is never captured: a prompt that starts with `<task-notification>` or
    `<system-reminder>` (shared_names.MACHINE_TAGS). A notice is not judged, does not close
    capture, and is not an owner message. A tag quoted mid-message is owner text.
  - Quiet time: an open capture closes when the last captured owner message is more than 10
    minutes old. The prompt after that gap is not captured, and makes no judge call. The gap runs
    from the last captured message, not from the opener. A fb opener after the gap opens again.
    LOCAL_TIME_NOW (env, an ISO-8601 instant with an offset, such as 2026-10-14T18:00:00+00:00)
    replaces the hook's clock when set: it drives the Local time line, the header stamp and the
    gap. Tests set it. Nothing sleeps.
  - Judge: every owner prompt is saved first. While open, each owner prompt that is not a close
    form and not a notice is judged by the detached child hooks/feedback_judge.py, which the hook
    starts and does not wait for. The child calls decision_watch.invoke_model with model
    claude-sonnet-5-5 (the Sonnet row in decisions/agent-model-cap.md) and shape
    {"feedback": (True, False)}. {"feedback": false} appends a note item,
    `- fb-auto-<time> [note] -> judged not feedback`, under that message and closes capture, but
    only while that message is still the last captured one. {"feedback": true}, a timeout, a
    non-zero exit and an answer outside the shape change nothing. The opener, the close forms and
    notices make no judge call.
  - Seam: FEEDBACK_JUDGE_INLINE=1 makes the hook run the child in the foreground and wait for it to
    exit. Tests set it. Without it the child runs detached, and the hook returns first. The child
    inherits the hook's environment (PYTHONPATH and FB_JUDGE_* for the stub).
  - While open, a lone surrogate in the text (JSON escape `\\ud800`) is either saved with U+FFFD
    (the replacement character) in its place, or stdout carries a line that says `not saved`.
    Never silent. Capture stays open, and the inbox stays strict UTF-8.
  - State is per session_id and survives across runs. Another session's prompts are never captured.
  - `--agent` (a SubagentStart payload) prints the same hookSpecificOutput JSON and never opens,
    closes or captures.
  - Fail open: empty stdin, non-JSON stdin, or a payload with no session_id gives exit 0, one
    Central line, and no file written.
  - Write failure: when the inbox cannot be written (a directory at its path, for example), stdout
    keeps the Local time line and adds one line that contains `not saved`. The message is not
    captured. The session jots it by hand. Exit 0.

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

Gate: hooks/feedback_gate.py (env FEEDBACK_GATE_UNDER_TEST overrides the path). A Stop hook. Stdin
  is one JSON object: hook_event_name, session_id, stop_hook_active, cwd. It reads the inbox and the
  handoff <CLAUDE_CONFIG_DIR>/handoffs/<session_id>.md. Exit 0 in every case. Stdout is one JSON
  object or nothing.
  - stop_hook_active true: exit 0, nothing on stdout, at once.
  - No inbox, or an empty inbox: nothing on stdout.
  - A block is {"decision": "block", "reason": ...}. The reason names each offending id, or the
    message by its Central stamp or the start of its text. Offences: a captured message with no
    items; an item with no kind, an unknown kind, or no home; an open standing item whose id is
    not in the handoff as a whole token. A missing handoff file means every open id is missing.
  - Tracked homes (decision owner-feedback-inbox, "Kinds and homes"). A ruling or task item, open
    or closed, names a path: relative to the repo of the payload's cwd, or absolute. The file sits
    under a home of its kind in lint/layout.json, read through lint/layout.py: ruling under the
    keys decisions, rules, claude-md or agents-md; task under todo (a repo's extras key), debts or
    debt-notes. Some branch's tree in that file's repo holds it. Else the reason names the id. The
    handoff never counts for these two kinds. A repo with no home of the kind gets a reason that
    names the layout keys, todo first for a task.
  - Fail open: when the cwd is not in a git repo, or the layout or the repo's extras file cannot
    be read, ruling and task homes pass unchecked and stdout carries one systemMessage line that
    starts "Feedback gate: ruling and task homes not checked".
  - A malformed item line is an offence: a `- fb-` line whose id is not a token, such as
    `- fb- [task] -> x` or a bare `- fb-`. The reason quotes the line's text after the leading
    `- `, for example `fb- [task] -> x`. The gate does not crash on it.
  - An item line that ends with `[closed]` is closed. Its id is not required in the handoff. Its
    kind and home are still checked, a ruling's or task's tracked home too.
  - An unreadable inbox (a directory at its path, or bytes that are not UTF-8) gives one block that
    names the inbox file. Why: a Stop hook's stderr does not reach the owner, so a silent pass would
    drop feedback. stop_hook_active still gives nothing, so the block costs one turn at most.
  - While capture is open, stdout carries "systemMessage" (the universal hook field) naming
    `fb done`. It rides on a pass and on a block. While capture is closed, there is no systemMessage.
  - Another session's inbox is never read.

Reorient: hooks/precompact_handoff.py `--reorient` (env PRECOMPACT_HANDOFF_UNDER_TEST overrides the
  path). Each of its two messages ends with an inbox note, or with nothing:
  - open ids (ruling, task, standing) in the inbox:
    " Open feedback items: <ids>. Keep each standing item in the handoff, and give each ruling
    and task its tracked home: a decision record or rule, or the repo's todo or debt store."
  - the open marker <session>.inbox.open exists: " Feedback capture is still open: the owner has not
    sent `fb done`."
  - both, items first. Neither: the message is unchanged. An unreadable inbox gives no note, one
    stderr line, and the message still prints.
  - A malformed item line is never listed as an id. The other ids and the capture line still print.

Readings taken here, where the record says "every owner message between the two":
  the opening prompt is captured; `x fb` and `fbi ...` are captured while open; the gate's jotting
  checks apply to a closed inbox too, because those messages were still captured.

The expected strings are hardcoded here. The reader in this file follows the format above.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LT_PATH =os.environ.get("LOCAL_TIME_UNDER_TEST") or os.path.join(HERE, "local_time.py")
GATE_PATH = os.environ.get("FEEDBACK_GATE_UNDER_TEST") or os.path.join(HERE, "feedback_gate.py")
PRECOMPACT_PATH = os.environ.get("PRECOMPACT_HANDOFF_UNDER_TEST") or os.path.join(
    HERE, "precompact_handoff.py")
ROOT = tempfile.mkdtemp(prefix="feedback_inbox_cases_")
JUDGE_STUB_DIR = os.path.join(ROOT, "judge-stub")
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
JUDGE_MODEL = "claude-sonnet-5-5"  # the Sonnet id in the model table of decisions/agent-model-cap.md
CLOCK_START = datetime(2026, 10, 14, 18, 0, tzinfo=timezone.utc)  # 13:00 CDT, far from a DST edge
JUDGE_PATH = os.path.join(HERE, "feedback_judge.py")  # the detached judge child
SLOW = "2"  # seconds the stub judge takes, in the cases that read the child's outcome
NOTE_ITEM = re.compile(r"- fb-auto-\S+ \[note\] -> judged not feedback")

JOTTED_ITEMS = (
    "- fb-0958-1 [ruling] -> decisions/a-ruling.md",
    "- fb-0958-2 [task] -> debts/a-task.md",
    "- fb-0958-3 [question] -> answered",
    "- fb-0958-4 [note] -> noted",
    "- fb-0958-5 [standing] -> handoff: process-only",
)
JOTTED_HANDOFF = "# Handoff\n- fb-0958-5 standing\n"


# Judge seam. Every run of local_time.py and of feedback_judge.py loads this sitecustomize first
# (PYTHONPATH, inherited by the detached child). It wraps subprocess.run and answers only calls
# whose program is `claude`. The real invoke_model runs on top of it, so its argv (--model) and its
# parse are exercised. After FB_JUDGE_DELAY seconds (default 0) it records the call, with the
# script that made it, in the case's judge-calls.jsonl, and then answers. FB_JUDGE_ANSWER picks
# the answer: still (default), not, timeout, exit1 or bad-shape. A loaded file says the stub ran.
# A zero-call check counts only with a live call elsewhere in the same case.
JUDGE_STUB_SOURCE = r'''
import json
import os
import subprocess
import sys
import time

_real_run = subprocess.run


def _is_claude(argv):
    if not isinstance(argv, (list, tuple)) or not argv:
        return False
    return os.path.basename(str(argv[0])).lower() in ("claude", "claude.exe", "claude.cmd")


def _fake_run(argv, **kwargs):
    if not _is_claude(argv):
        return _real_run(argv, **kwargs)
    stdin = kwargs.get("input")
    if isinstance(stdin, bytes):
        stdin = stdin.decode("utf-8", "replace")
    time.sleep(float(os.environ.get("FB_JUDGE_DELAY") or 0))  # a real judge answers late
    record = {"argv": list(argv), "prompt": stdin, "timeout": kwargs.get("timeout"),
              "script": os.path.basename(sys.argv[0])}
    with open(os.environ["FB_JUDGE_RECORD"], "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    answer = os.environ.get("FB_JUDGE_ANSWER", "still")
    if answer == "timeout":
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
    if answer == "exit1":
        return subprocess.CompletedProcess(argv, 1, b"", b"stub judge exited 1")
    if answer == "bad-shape":
        text = json.dumps({"feedback": "maybe"})
    else:
        text = json.dumps({"feedback": answer != "not"})
    envelope = json.dumps({"result": text})
    return subprocess.CompletedProcess(argv, 0, envelope.encode("utf-8"), b"")


with open(os.environ["FB_JUDGE_LOADED"], "w", encoding="utf-8") as f:
    f.write("loaded")
subprocess.run = _fake_run
'''


def install_judge_stub():
    """Writes the judge stub into this run's scratch folder. Never into the repo."""
    write_file(os.path.join(JUDGE_STUB_DIR, "sitecustomize.py"), JUDGE_STUB_SOURCE)


def check(name, cond, detail=""):
    if cond:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, " ".join(str(detail).split())[:600]))


# --------------------------------------------------------------------------- harness helpers

class Proc:
    def __init__(self, code, out, err, loaded=None):
        self.code, self.out, self.err, self.loaded = code, out, err, loaded  # loaded: judge stub ran

    def desc(self):
        return "rc=%s stdout=%r stderr=%r" % (self.code, self.out[-300:], self.err[-300:])


def new_cfg():
    CASE_COUNT[0] += 1
    base = os.path.join(ROOT, "case-%03d" % CASE_COUNT[0])
    cfg = os.path.join(base, "cfg")
    os.makedirs(cfg)
    return cfg


JUDGE_ENV = ("FB_JUDGE_ANSWER", "FB_JUDGE_DELAY", "FB_JUDGE_RECORD", "FB_JUDGE_LOADED",
             "LOCAL_TIME_NOW", "FEEDBACK_JUDGE_INLINE")


def run(path, raw, cfg, args=(), judge="still", now=None, inline=True, delay="0"):
    """Runs one hook script, or the judge child, the way the harness does. Returns a Proc. The hook
    and the child load the judge stub. `judge` picks its answer, `delay` is its latency in seconds,
    `now` (an ISO-8601 instant) is the hook's clock through LOCAL_TIME_NOW, and `inline` sets
    FEEDBACK_JUDGE_INLINE=1, so the hook waits for the child."""
    home = os.path.join(os.path.dirname(cfg), "home")
    os.makedirs(home, exist_ok=True)
    env = dict(os.environ)
    for name in ("PYTHONUTF8", "PYTHONIOENCODING", "CLAUDE_CONFIG_DIR", *JUDGE_ENV):
        env.pop(name, None)
    env.update(CLAUDE_CONFIG_DIR=cfg, HOME=home, USERPROFILE=home)
    loaded = None
    if path in (LT_PATH, JUDGE_PATH):
        loaded = os.path.join(os.path.dirname(cfg), "loaded-%s" % uuid.uuid4().hex)
        inherited = [os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else []
        env["PYTHONPATH"] = os.pathsep.join([JUDGE_STUB_DIR] + inherited)
        env.update(FB_JUDGE_ANSWER=judge, FB_JUDGE_DELAY=delay, FB_JUDGE_RECORD=judge_log(cfg),
                   FB_JUDGE_LOADED=loaded)
        if inline:
            env["FEEDBACK_JUDGE_INLINE"] = "1"
        if now:
            env["LOCAL_TIME_NOW"] = now
    try:
        cp = subprocess.run([sys.executable, path, *args], input=raw, capture_output=True,
                            env=env, cwd=home, timeout=30)
    except subprocess.TimeoutExpired:
        return Proc(-1, "", "timed out after 30 s")
    return Proc(cp.returncode, cp.stdout.decode("utf-8", "replace"),
                cp.stderr.decode("utf-8", "replace"),
                loaded=os.path.exists(loaded) if loaded else None)


def payload(obj):
    """UTF-8 bytes, as the harness sends them. ensure_ascii is off, so the bytes are real UTF-8."""
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def capture(cfg, sid, prompt, now=None, judge="still", inline=True, delay="0"):
    return run(LT_PATH, payload({"hook_event_name": "UserPromptSubmit", "session_id": sid,
                                 "prompt": prompt, "cwd": cfg}), cfg, judge=judge, now=now,
               inline=inline, delay=delay)


def judge_log(cfg):
    return os.path.join(os.path.dirname(cfg), "judge-calls.jsonl")


def judge_calls(cfg):
    """Every call the judge stub recorded in this case, oldest first."""
    path = judge_log(cfg)
    if not os.path.exists(path):
        return []
    return [json.loads(line) for line in read_file(path).splitlines() if line.strip()]


def model_of(call):
    argv = call.get("argv") or []
    return argv[argv.index("--model") + 1] if "--model" in argv[:-1] else None


def block_items(cfg, sid, text):
    """The item lines under the block whose verbatim text is `text`, or None when there is no such block."""
    for block in read_blocks(read_or_empty(inbox_of(cfg, sid))):
        if block["text"] == text:
            return block["items"]
    return None


def judged_notes(items):
    """The `judged not feedback` note items in a list of item lines."""
    return [item for item in (items or []) if NOTE_ITEM.fullmatch(item)]


def sonnet_ids():
    """The Sonnet model ids in the model table of decisions/agent-model-cap.md."""
    text = read_file(os.path.join(REPO, "docs", "decisions", "agent-model-cap.md"))
    return re.findall(r"\|\s*(claude-sonnet-[\w-]+)\s*\|", text)


def at(minutes):
    """The LOCAL_TIME_NOW value: CLOCK_START plus some minutes."""
    return (CLOCK_START + timedelta(minutes=minutes)).isoformat()


def gate(cfg, sid, stop_active=False, cwd=None):
    """Runs the gate. `cwd` is the session's folder in the payload: the shared fixture repo unless
    a case names another."""
    return run(GATE_PATH, payload({"hook_event_name": "Stop", "session_id": sid,
                                   "stop_hook_active": stop_active,
                                   "cwd": cwd or fixture_repo()}), cfg)


GIT_ID = ("-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
          "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main")


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


def marker_of(cfg, sid):
    return os.path.join(cfg, "handoffs", sid + ".inbox.open")


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


def minutes_apart(a, b):
    fmt = "%Y-%m-%d %H:%M"
    return abs((datetime.strptime(a, fmt) - datetime.strptime(b, fmt)).total_seconds()) / 60


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


def gate_json(p):
    try:
        obj = json.loads(p.out)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def is_block(obj):
    return obj is not None and obj.get("decision") == "block"


def block_reason(p):
    obj = gate_json(p)
    if is_block(obj) and isinstance(obj.get("reason"), str):
        return obj["reason"]
    return None


def reminder_of(obj):
    sm = obj.get("systemMessage") if obj else None
    if isinstance(sm, str) and "fb done" in sm and "capture" in sm.lower():
        return sm
    return None


def stamp_of(header):
    return STAMP.search(header).group(0)


def names_message(reason, stamp, text):
    """A block names its message by the Central stamp in its header, or by the start of its text."""
    return stamp in reason or text[:20] in reason


def opened(cfg, sid, opener):
    """Opens capture through the capture hook. False, with a red check, when that does not happen."""
    p = capture(cfg, sid, opener)
    ok = ran_central(p) and os.path.exists(inbox_of(cfg, sid))
    check("capture precondition: %r opens capture" % opener, ok, p.desc())
    return ok


def expect_silent(name, p):
    check(name, p.code == 0 and p.out.strip() == "", p.desc())


def expect_reminder(name, p):
    obj = gate_json(p)
    check(name, p.code == 0 and obj is not None and not is_block(obj)
          and reminder_of(obj) is not None, p.desc())


def expect_block(name, p, named=(), unnamed=(), reminder=None):
    reason = block_reason(p) or ""
    check(name + ": blocks", p.code == 0 and block_reason(p) is not None, p.desc())
    for n in named:
        check("%s: names %s" % (name, n), n in reason, reason)
    for n in unnamed:
        check("%s: does not name %s" % (name, n), n not in reason, reason)
    if reminder is not None:
        has = reminder_of(gate_json(p)) is not None
        check("%s: %s" % (name, "carries the reminder" if reminder else "no reminder"),
              has == reminder, p.desc())


# --------------------------------------------------------------------------- capture cases

def case_closed_by_default():
    cfg, sid = new_cfg(), "closed-default"
    for text in ("plain owner prompt", "fbi is not a trigger", "please x fb here", "fb done"):
        p = capture(cfg, sid, text)
        check("closed: hook ran for %r" % text, ran_central(p), p.desc())
    check("closed: plain, fbi, x fb and fb done capture nothing (no inbox file)",
          not os.path.exists(inbox_of(cfg, sid)), "inbox exists")


def case_opener_captured_with_central_time():
    cfg, sid = new_cfg(), "opener"
    text = "fb: the gate is too strict on Stop"
    p = capture(cfg, sid, text)
    check("opener: hook ran (one Central line, exit 0)", ran_central(p), p.desc())
    blocks = read_blocks(read_or_empty(inbox_of(cfg, sid)))
    check("opener: one block, and it holds the opener verbatim",
          len(blocks) == 1 and blocks[0]["text"] == text, blocks)
    if not blocks:
        return
    m = HEADER.fullmatch(blocks[0]["header"])
    local = CENTRAL.fullmatch(p.out.strip())
    check("opener: header is a Central stamp with CDT or CST",
          m is not None, blocks[0]["header"])
    check("opener: header time is within a minute of the Local time line, same zone",
          bool(m and local and m.group(2) == local.group(2)
               and minutes_apart(m.group(1), local.group(1)) <= 1),
          "header=%r stdout=%r" % (blocks[0]["header"], p.out))
    check("opener: no items yet (the session jots them)", blocks[0]["items"] == [],
          blocks[0]["items"])


def case_opener_forms():
    for sid, text in (("form-no-colon", "fb the gate is too strict"),
                      ("form-newline", "fb:\nline two of the burst")):
        cfg = new_cfg()
        p = capture(cfg, sid, text)
        check("opener form %r: hook ran" % sid, ran_central(p), p.desc())
        check("opener form %r: opens, and the prompt is captured verbatim" % sid,
              captured_texts(cfg, sid) == [text], captured_texts(cfg, sid))


def case_open_survives_across_runs():
    cfg, sid = new_cfg(), "open-run"
    texts = ["fb: first point", "second point, plain", "third point with x fb inside",
             "fbi fourth point"]
    for text in texts:
        p = capture(cfg, sid, text)
        check("open run: hook ran for %r" % text, ran_central(p), p.desc())
    check("open: every prompt captured in order, verbatim; x fb and fbi do not close",
          captured_texts(cfg, sid) == texts, captured_texts(cfg, sid))


def case_fb_done_closes_and_is_not_captured():
    cfg, sid = new_cfg(), "close"
    for text in ("fb: one", "fb done", "after close"):
        p = capture(cfg, sid, text)
        check("close: hook ran for %r" % text, ran_central(p), p.desc())
    check("close: fb done is not captured and nothing after it is",
          captured_texts(cfg, sid) == ["fb: one"], captured_texts(cfg, sid))
    cfg, sid = new_cfg(), "close-newline"
    for text in ("fb: two", "fb done\n", "after close two"):
        p = capture(cfg, sid, text)
        check("close with newline: hook ran for %r" % text, ran_central(p), p.desc())
    check("close with newline: fb done plus newline closes, and is not captured",
          captured_texts(cfg, sid) == ["fb: two"], captured_texts(cfg, sid))


def case_fb_done_forms_close_capture():
    for sid, closer in (("done-period", "fb done."), ("done-bang", "fb done!"),
                        ("done-caps", "FB done"), ("done-colon", "fb: done"),
                        ("done-two-spaces", "fb  done")):
        cfg = new_cfg()
        opened(cfg, sid, "fb: open the burst")
        p = capture(cfg, sid, closer)
        check("close form %r: hook ran" % closer, ran_central(p), p.desc())
        check("close form %r: closes capture, and is not captured" % closer,
              not os.path.exists(marker_of(cfg, sid))
              and captured_texts(cfg, sid) == ["fb: open the burst"], captured_texts(cfg, sid))
    cfg, sid = new_cfg(), "done-now"
    opened(cfg, sid, "fb: open the burst")
    p = capture(cfg, sid, "fb done now")
    check("fb done now: hook ran", ran_central(p), p.desc())
    check("fb done now: closes capture, and is not captured (owner ruling 2026-10-14)",
          not os.path.exists(marker_of(cfg, sid))
          and captured_texts(cfg, sid) == ["fb: open the burst"], captured_texts(cfg, sid))


def case_near_miss_closers_open_nothing_while_closed():
    for sid, text in (("near-colon", "fb: done"), ("near-two-spaces", "fb  done"),
                      ("near-tab", "fb\tdone"), ("near-dash", "fb - done")):
        cfg = new_cfg()
        p = capture(cfg, sid, text)
        check("near miss %r: hook ran" % text, ran_central(p), p.desc())
        check("near miss %r: does not open capture (no marker, no inbox)" % text,
              not os.path.exists(marker_of(cfg, sid))
              and not os.path.exists(inbox_of(cfg, sid)), p.desc())


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
    cfg, sid = new_cfg(), "write-fail-opener"
    os.makedirs(inbox_of(cfg, sid))  # a directory at the inbox path: no write can land
    not_saved_check("write failure, opener",
                    capture(cfg, sid, "fb: a message the inbox cannot take"))
    cfg, sid = new_cfg(), "write-fail-open"
    os.makedirs(inbox_of(cfg, sid))
    write_file(marker_of(cfg, sid), "")  # capture is already open
    not_saved_check("write failure, capture open",
                    capture(cfg, sid, "a later message in the burst"))


# A lone surrogate, as the payload's JSON escape. json.dumps writes the escape: the bytes are ASCII.
LONE_SURROGATE = "a lone \ud800 surrogate in the middle of the burst"
SURROGATE_SAVED = "a lone \ufffd surrogate in the middle of the burst"


def case_lone_surrogate_is_saved_or_said_not_saved():
    cfg, sid = new_cfg(), "lone-surrogate"
    opener = "fb: surrogate burst"
    if not opened(cfg, sid, opener):
        return
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
    check("lone surrogate: capture stays open", os.path.exists(marker_of(cfg, sid)), p.desc())
    texts = captured_texts(cfg, sid) if strict else None
    saved = texts == [opener, SURROGATE_SAVED]
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


def case_agent_never_opens_closes_or_captures():
    cfg = new_cfg()
    p0 = capture(cfg, "sub-open", "fb: opened by the owner")
    check("agent: owner opener ran", ran_central(p0), p0.desc())
    before = read_or_empty(inbox_of(cfg, "sub-open"))
    p = run(LT_PATH, sub_payload("sub-open", "fb done", cfg), cfg, args=("--agent",))
    check("agent: fb done payload prints the SubagentStart JSON", agent_ok(p), p.desc())
    check("agent: an open inbox is unchanged by an agent fb done",
          before != "" and read_or_empty(inbox_of(cfg, "sub-open")) == before, "changed")
    p2 = capture(cfg, "sub-open", "still open after the agent")
    check("agent: next owner prompt ran", ran_central(p2), p2.desc())
    check("agent: capture is still open, the next owner prompt is captured",
          captured_texts(cfg, "sub-open") == ["fb: opened by the owner",
                                              "still open after the agent"],
          captured_texts(cfg, "sub-open"))
    q = run(LT_PATH, sub_payload("sub-closed", "fb: agent opener", cfg), cfg,
            args=("--agent",))
    check("agent: fb: payload prints the SubagentStart JSON", agent_ok(q), q.desc())
    p3 = capture(cfg, "sub-closed", "plain owner prompt after an agent opener")
    check("agent: owner prompt after an agent opener ran", ran_central(p3), p3.desc())
    check("agent: an agent opener does not open capture (no inbox file)",
          not os.path.exists(inbox_of(cfg, "sub-closed")), "inbox exists")


def case_sessions_are_isolated():
    cfg = new_cfg()
    check("isolation: session a opener ran", ran_central(capture(cfg, "iso-a", "fb: a opener")))
    p = capture(cfg, "iso-b", "plain prompt from session b")
    check("isolation: session b plain prompt ran", ran_central(p), p.desc())
    check("isolation: session b plain prompt is in neither inbox and b has no inbox",
          not os.path.exists(inbox_of(cfg, "iso-b"))
          and "plain prompt from session b" not in read_or_empty(inbox_of(cfg, "iso-a")),
          read_or_empty(inbox_of(cfg, "iso-a")))
    check("isolation: session b opener ran", ran_central(capture(cfg, "iso-b", "fb: b opener")))
    check("isolation: b's opener lands in b's inbox only",
          captured_texts(cfg, "iso-b") == ["fb: b opener"]
          and captured_texts(cfg, "iso-a") == ["fb: a opener"],
          (captured_texts(cfg, "iso-a"), captured_texts(cfg, "iso-b")))


# --------------------------------------------------------------------------- gate cases

def case_gate_no_inbox_and_empty_inbox_pass_silently():
    cfg = new_cfg()
    expect_silent("gate: no inbox file passes silently", gate(cfg, "no-inbox"))
    write_file(inbox_of(cfg, "empty-inbox"), "")
    expect_silent("gate: empty inbox passes silently", gate(cfg, "empty-inbox"))


def case_gate_all_jotted_passes_silently():
    cfg, sid = new_cfg(), "jotted"
    write_file(inbox_of(cfg, sid), render_block("fb: a jotted burst\nsecond line",
                                                items=JOTTED_ITEMS))
    write_file(handoff_of(cfg, sid), JOTTED_HANDOFF)
    expect_silent("gate: all jotted, open ids in the handoff, passes silently", gate(cfg, sid))


def case_gate_message_without_items_blocks_and_names_it():
    cfg, sid = new_cfg(), "no-items"
    text_b = "second message, no items jotted"
    write_file(inbox_of(cfg, sid),
               render_block("first message", header="2026-10-13 10:04 CDT (UTC-05:00)",
                            items=("- fb-0958-2 [standing] -> handoff",))
               + render_block(text_b, header="2026-10-13 10:09 CDT (UTC-05:00)"))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    p = gate(cfg, sid)
    reason = block_reason(p) or ""
    expect_block("gate: message with no items", p)
    check("gate: the reason names the message with no items",
          names_message(reason, "2026-10-13 10:09", text_b), reason)
    check("gate: the reason does not name the jotted first message",
          "2026-10-13 10:04" not in reason, reason)


BAD_ITEMS = (
    ("no kind", "- fb-0958-4 -> handoff", "fb-0958-4"),
    ("unknown kind", "- fb-0958-5 [bug] -> handoff", "fb-0958-5"),
    ("no home", "- fb-0958-6 [task]", "fb-0958-6"),
    ("empty home", "- fb-0958-7 [note] ->", "fb-0958-7"),
)


def case_gate_item_without_kind_or_home_blocks():
    for label, item, item_id in BAD_ITEMS:
        cfg, sid = new_cfg(), "bad-" + item_id
        write_file(inbox_of(cfg, sid), render_block("item with %s" % label, items=(item,)))
        expect_block("gate: item with %s" % label, gate(cfg, sid), named=(item_id,))


def case_gate_open_item_missing_from_handoff_blocks():
    cfg, sid = new_cfg(), "open-missing"
    items = ("- fb-0958-2 [standing] -> handoff", "- fb-0958-3 [standing] -> handoff",
             "- fb-0958-4 [standing] -> handoff")
    write_file(inbox_of(cfg, sid), render_block("open ids burst", items=items))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 standing\n")
    expect_block("gate: open standing items missing from the handoff", gate(cfg, sid),
                 named=("fb-0958-3", "fb-0958-4"), unnamed=("fb-0958-2",))
    expect_silent("gate: stop_hook_active gives nothing, even with missing open ids",
                  gate(cfg, sid, stop_active=True))


def case_gate_id_match_is_a_whole_token():
    cfg, sid = new_cfg(), "boundary"
    write_file(inbox_of(cfg, sid),
               render_block("boundary", items=("- fb-0958-2 [standing] -> handoff",)))
    write_file(handoff_of(cfg, sid), "- fb-0958-20 task, a different item\n")
    expect_block("gate: fb-0958-20 in the handoff does not count for fb-0958-2", gate(cfg, sid),
                 named=("fb-0958-2",))


def case_gate_handoff_rewrite_that_drops_an_item_blocks():
    cfg, sid = new_cfg(), "rewrite"
    write_file(inbox_of(cfg, sid), render_block(
        "two open items", items=("- fb-0958-2 [standing] -> handoff",
                                 "- fb-0958-3 [standing] -> handoff")))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 standing, kept\n")
    expect_block("gate: a handoff rewrite that drops fb-0958-3 blocks", gate(cfg, sid),
                 named=("fb-0958-3",), unnamed=("fb-0958-2",))


def case_gate_missing_handoff_counts_every_open_id_missing():
    cfg, sid = new_cfg(), "no-handoff"
    write_file(inbox_of(cfg, sid), render_block("no handoff yet",
                                                items=("- fb-0958-2 [standing] -> handoff",)))
    expect_block("gate: open standing item with no handoff file blocks", gate(cfg, sid),
                 named=("fb-0958-2",))


def case_gate_scanner_text_yields_no_phantom_block_or_item():
    cfg, sid = new_cfg(), "scanner-gate"
    write_file(inbox_of(cfg, sid), render_block(SCANNER, header=BLOCK_HEADER, items=()))
    p = gate(cfg, sid)
    reason = block_reason(p) or ""
    expect_block("gate: scanner text with no items blocks", p)
    check("gate: the reason names the scanner message by its stamp or text",
          names_message(reason, "2026-10-13 10:04", SCANNER), reason)
    check("gate: the fake item inside the fence is not an open item", "fb-0999-1" not in reason,
          reason)
    check("gate: the fake header inside the fence is not a block", "2026-01-01" not in reason,
          reason)


def case_gate_scanner_text_with_real_items_passes_silently():
    cfg, sid = new_cfg(), "scanner-real"
    write_file(inbox_of(cfg, sid), render_block(SCANNER, items=("- fb-0958-2 [standing] -> handoff",)))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    expect_silent("gate: scanner text with real items passes (fake fb-0999-1 is not read)",
                  gate(cfg, sid))


def case_gate_malformed_item_line_blocks_and_names_it():
    cfg, sid = new_cfg(), "malformed-item"
    write_file(inbox_of(cfg, sid), render_block("malformed item beside a good one", items=(
        "- fb- [task] -> x", "- fb-0958-2 [standing] -> handoff")))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 standing\n")
    expect_block("gate: malformed `- fb- [task] -> x` beside a handed-off item", gate(cfg, sid),
                 named=("fb- [task] -> x",), unnamed=("fb-0958-2",))
    cfg, sid = new_cfg(), "malformed-bare"
    write_file(inbox_of(cfg, sid), render_block("a bare fb- line", items=("- fb-",)))
    expect_block("gate: bare `- fb-` line", gate(cfg, sid), named=("fb-",))


def case_gate_closed_item_is_not_required_in_handoff():
    cfg, sid = new_cfg(), "closed-item"
    write_file(inbox_of(cfg, sid), render_block("closed standing, task and ruling", items=(
        "- fb-0958-1 [standing] -> handoff: done [closed]",
        "- fb-0958-2 [task] -> debts/a-task.md [closed]",
        "- fb-0958-3 [ruling] -> decisions/a-ruling.md [closed]")))
    write_file(handoff_of(cfg, sid), "# Handoff\n")
    expect_silent("gate: closed items with good homes, missing from the handoff, pass silently",
                  gate(cfg, sid))
    cfg, sid = new_cfg(), "closed-and-open"
    write_file(inbox_of(cfg, sid), render_block("one closed, one open", items=(
        "- fb-0958-2 [standing] -> handoff: done [closed]", "- fb-0958-4 [standing] -> handoff")))
    write_file(handoff_of(cfg, sid), "# Handoff\n")
    expect_block("gate: open standing item still required beside a closed one", gate(cfg, sid),
                 named=("fb-0958-4",), unnamed=("fb-0958-2",))


def case_gate_notes_heading_is_plain_text():
    cfg, sid = new_cfg(), "notes-heading"
    write_file(inbox_of(cfg, sid), render_block("jotted burst", items=(
        "- fb-0958-2 [standing] -> handoff",)) + "### Notes\nsome notes the session wrote by hand\n")
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    expect_silent("gate: a ### Notes heading after a jotted message passes silently",
                  gate(cfg, sid))
    cfg, sid = new_cfg(), "notes-only"
    write_file(inbox_of(cfg, sid), "### Notes\nno captured message here\n")
    expect_silent("gate: an inbox with only a ### Notes heading passes silently", gate(cfg, sid))


def case_gate_reminder_follows_capture_state():
    cfg, sid = new_cfg(), "open-jotted"
    if opened(cfg, sid, "fb: reminder check, jotted"):
        append_file(inbox_of(cfg, sid), "- fb-0958-2 [note] -> noted\n")
        expect_reminder("open and jotted: reminder, no block", gate(cfg, sid))

    cfg, sid = new_cfg(), "open-unjotted"
    if opened(cfg, sid, "fb: reminder check, unjotted"):
        block = read_blocks(read_file(inbox_of(cfg, sid)))[0]
        p = gate(cfg, sid)
        expect_block("open and unjotted: blocks", p, reminder=True)
        reason = block_reason(p) or ""
        check("open and unjotted: the block names the message",
              names_message(reason, stamp_of(block["header"]), block["text"]), reason)

    cfg, sid = new_cfg(), "closed-jotted"
    if opened(cfg, sid, "fb: reminder check, closed and jotted"):
        append_file(inbox_of(cfg, sid), "- fb-0958-2 [note] -> noted\n")
        closed = capture(cfg, sid, "fb done")
        check("closed and jotted: fb done ran and is a close", ran_central(closed), closed.desc())
        expect_silent("closed and jotted: silent, no reminder", gate(cfg, sid))

    cfg, sid = new_cfg(), "closed-unjotted"
    if opened(cfg, sid, "fb: reminder check, closed and unjotted"):
        closed = capture(cfg, sid, "fb done")
        check("closed and unjotted: fb done ran and is a close", ran_central(closed), closed.desc())
        block = read_blocks(read_file(inbox_of(cfg, sid)))[0]
        p = gate(cfg, sid)
        expect_block("closed and unjotted: blocks, no reminder", p, reminder=False)
        reason = block_reason(p) or ""
        check("closed and unjotted: the block names the message",
              names_message(reason, stamp_of(block["header"]), block["text"]), reason)

    cfg, sid = new_cfg(), "open-stop-active"
    if opened(cfg, sid, "fb: reminder check, stop active"):
        expect_silent("open and unjotted, stop_hook_active: silent",
                      gate(cfg, sid, stop_active=True))


def case_gate_unreadable_inbox_blocks_and_names_the_file():
    cfg, sid = new_cfg(), "unreadable-dir"
    os.makedirs(inbox_of(cfg, sid))
    expect_block("gate: unreadable inbox (a directory) blocks", gate(cfg, sid),
                 named=(os.path.basename(inbox_of(cfg, sid)),))

    cfg, sid = new_cfg(), "unreadable-bytes"
    os.makedirs(os.path.dirname(inbox_of(cfg, sid)), exist_ok=True)
    with open(inbox_of(cfg, sid), "wb") as f:
        f.write(b"### 2026-10-13 10:04 CDT (UTC-05:00)\n\xff\xfe\x80 not UTF-8\n")
    expect_block("gate: unreadable inbox (bytes that are not UTF-8) blocks", gate(cfg, sid),
                 named=(os.path.basename(inbox_of(cfg, sid)),))
    expect_silent("gate: unreadable inbox with stop_hook_active gives nothing",
                  gate(cfg, sid, stop_active=True))


def case_gate_reads_only_its_own_session():
    cfg = new_cfg()
    write_file(inbox_of(cfg, "own"),
               render_block("own jotted", items=("- fb-0958-2 [standing] -> handoff",)))
    write_file(handoff_of(cfg, "own"), "- fb-0958-2 task\n")
    write_file(inbox_of(cfg, "other"),
               render_block("other incomplete", items=("- fb-0958-9 [ruling] -> NO HOME YET",)))
    os.makedirs(inbox_of(cfg, "other-bad"))
    expect_silent("gate: own session passes; other sessions' inboxes do not block it",
                  gate(cfg, "own"))


# --------------------------------------------------------------------------- tracked homes

FAIL_OPEN = "Feedback gate: ruling and task homes not checked"


def homed(cfg, sid, items, handoff_ids=(), cwd=None):
    """Writes one jotted message and a handoff that holds `handoff_ids`, then runs the gate."""
    write_file(inbox_of(cfg, sid), render_block("homes burst", items=items))
    write_file(handoff_of(cfg, sid), "# Handoff\n" + "".join("- %s\n" % i for i in handoff_ids))
    return gate(cfg, sid, cwd=cwd)


def fail_open_line(p):
    obj = gate_json(p)
    msg = (obj or {}).get("systemMessage") or ""
    return [ln for ln in msg.splitlines() if ln.startswith(FAIL_OPEN)]


def case_gate_ruling_homed_to_handoff_blocks():
    for label, item in (("NO HOME YET", "- fb-1 [ruling] -> handoff: NO HOME YET"),
                        ("the handoff path", "- fb-1 [ruling] -> handoff"),
                        ("closed, NO HOME YET", "- fb-1 [ruling] -> NO HOME YET [closed]")):
        cfg = new_cfg()
        expect_block("homes: a ruling homed to %s blocks, though its id is in the handoff" % label,
                     homed(cfg, "r-handoff", (item,), handoff_ids=("fb-1",)), named=("fb-1",))


def case_gate_task_homed_to_untracked_file_blocks():
    repo = make_repo("untracked", tracked=("debts/old.md",), untracked=("debts/new.md",))
    cfg = new_cfg()
    expect_block("homes: a task homed to an untracked debt file blocks",
                 homed(cfg, "t-untracked", ("- fb-2 [task] -> debts/new.md",),
                       handoff_ids=("fb-2",), cwd=repo), named=("fb-2",))
    cfg = new_cfg()
    expect_block("homes: a task homed to a missing file blocks",
                 homed(cfg, "t-missing", ("- fb-2 [task] -> debts/none.md",), cwd=repo),
                 named=("fb-2",))


def case_gate_home_outside_its_kind_blocks():
    cfg = new_cfg()
    expect_block("homes: a ruling homed to a tracked file outside the ruling homes blocks",
                 homed(cfg, "r-readme", ("- fb-3 [ruling] -> README.md",)), named=("fb-3",))
    cfg = new_cfg()
    expect_block("homes: a task homed to a decision record blocks",
                 homed(cfg, "t-decision", ("- fb-3 [task] -> decisions/a-ruling.md",)),
                 named=("fb-3",))


def case_gate_tracked_homes_pass_without_the_handoff():
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


def case_gate_standing_homed_to_handoff_passes():
    cfg = new_cfg()
    expect_silent("homes: a standing item homed to the handoff, id in it, passes (false alarm)",
                  homed(cfg, "s-handoff", ("- fb-7 [standing] -> handoff: process-only",),
                        handoff_ids=("fb-7",)))


def case_gate_task_home_from_extras_todo_key():
    extras = json.dumps({"kinds": {"todo": {"path": "specs/todo.md"}}})
    repo = make_repo("rolled", tracked=("specs/todo.md", "docs/decisions/r.md"), extras=extras)
    cfg = new_cfg()
    expect_silent("homes: a task homed to the extras file's todo key passes",
                  homed(cfg, "t-todo", ("- fb-8 [task] -> specs/todo.md",
                                        "- fb-9 [ruling] -> docs/decisions/r.md"), cwd=repo))
    bare = make_repo("no-task-home", tracked=("decisions/r.md",))
    cfg = new_cfg()
    p = homed(cfg, "t-none", ("- fb-8 [task] -> TODO.md",), cwd=bare)
    expect_block("homes: a repo with no task home blocks", p, named=("fb-8", "todo"))


def case_gate_unreadable_layout_fails_open_with_one_line():
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

NOTE_CAPTURE = " Feedback capture is still open: the owner has not sent `fb done`."
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


def case_reorient_capture_open_line():
    cfg = new_cfg()
    sid = "reo-marker"
    write_file(marker_of(cfg, sid), "")
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        tag = state_tag(ok_state)
        check("reorient capture (%s): the capture line ends the message" % tag,
              ends_with_note(p, NOTE_CAPTURE), p.desc())
        check("reorient capture (%s): no items line without an inbox" % tag,
              "Open feedback items" not in p.out, p.desc())


def case_reorient_items_and_capture_line_together():
    cfg = new_cfg()
    sid = "reo-both"
    write_file(inbox_of(cfg, sid), render_block("two open items", items=(
        "- fb-0958-2 [task] -> handoff", "- fb-0958-3 [ruling] -> NO HOME YET")))
    write_file(marker_of(cfg, sid), "")
    note = " Open feedback items: fb-0958-2, fb-0958-3." + KEEP + NOTE_CAPTURE
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        check("reorient both (%s): items line, then the capture line" % state_tag(ok_state),
              ends_with_note(p, note), p.desc())


def case_reorient_malformed_line_keeps_the_note():
    cfg, sid = new_cfg(), "reo-malformed"
    write_file(inbox_of(cfg, sid), render_block("burst with malformed lines", items=(
        "- fb- [task] -> x", "- fb-0958-2 [task] -> handoff", "- fb-",
        "- fb-0958-3 [ruling] -> NO HOME YET")))
    write_file(marker_of(cfg, sid), "")
    note = " Open feedback items: fb-0958-2, fb-0958-3." + KEEP + NOTE_CAPTURE
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        tag = state_tag(ok_state)
        check("reorient malformed (%s): good open ids and the capture line still print"
              % tag, ends_with_note(p, note), p.desc())
        check("reorient malformed (%s): the note does not fail on stderr" % tag,
              "inbox note failed" not in p.err, p.desc())


def case_reorient_nothing_when_no_open_items_and_no_marker():
    cfg = new_cfg()  # no inbox file at all
    sid = "reo-absent"
    for ok_state in (False, True):
        p = reorient(cfg, sid, ok_state)
        check("reorient absent (%s): the message is unchanged" % state_tag(ok_state),
              ends_with_note(p, ""), p.desc())
    cfg2 = new_cfg()  # an inbox with question and note items only, and no marker
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


# --------------------------------------------------------------------------- close, notice, quiet and judge cases

NOTICE_TASK = ("<task-notification>\n<task-id>a1b2c3</task-id>\n<status>completed</status>\n"
               "<summary>Agent \"lint sweep\" completed</summary>\n"
               "<result>All 12 files pass.</result>\n</task-notification>")
NOTICE_REMINDER = "<system-reminder>\nThe task tools have not been used recently.\n</system-reminder>"


def calls_so_far(cfg):
    return len(judge_calls(cfg))


def no_judge_call(cfg, before, p):
    """No judge call since `before`, and the stub ran, so zero really means the judge was not called."""
    return bool(p.loaded) and calls_so_far(cfg) == before


def case_fb_done_prefix_closes_and_drops_the_rest():
    for sid, closer in (("prefix-comma", "fb done, also we should add a check"),
                        ("prefix-colon", "fb: done, also one more point"),
                        ("prefix-newline", "fb done\nmore after a newline"),
                        ("prefix-caps", "FB DONE, don't save this")):
        cfg = new_cfg()
        opened(cfg, sid, "fb: open the burst")
        before = calls_so_far(cfg)
        p = capture(cfg, sid, closer)
        check("close prefix %r: hook ran" % closer, ran_central(p), p.desc())
        check("close prefix %r: closes capture, and the words and the rest are not saved" % closer,
              not os.path.exists(marker_of(cfg, sid))
              and captured_texts(cfg, sid) == ["fb: open the burst"], captured_texts(cfg, sid))
        check("close prefix %r: the closing prompt makes no judge call" % closer,
              no_judge_call(cfg, before, p), p.desc())


def case_fb_done_prefix_opens_nothing_while_closed():
    for sid, text in (("closed-prefix-comma", "fb done, more text"),
                      ("closed-prefix-colon", "fb: done, more text")):
        cfg = new_cfg()
        before = calls_so_far(cfg)
        p = capture(cfg, sid, text)
        check("closed prefix %r: hook ran" % text, ran_central(p), p.desc())
        check("closed prefix %r: opens nothing (no marker, no inbox), and makes no judge call" % text,
              not os.path.exists(marker_of(cfg, sid)) and not os.path.exists(inbox_of(cfg, sid))
              and no_judge_call(cfg, before, p), p.desc())


SAME_MSG_NOTE = "fb: the gate is too strict on Stop"


def case_fb_done_line_at_the_end_closes_in_the_same_message():
    """A message that ends with `fb done` saves the note and closes capture in that same
    message. The marker does not stay open, so the next message is not saved."""
    cfg, sid = new_cfg(), "same-msg"
    p = capture(cfg, sid, SAME_MSG_NOTE + "\nfb done", now=at(0))
    check("same message: hook ran", ran_central(p), p.desc())
    check("same message: the note is saved",
          any(SAME_MSG_NOTE in text for text in captured_texts(cfg, sid)),
          captured_texts(cfg, sid))
    check("same message: no open marker remains after the hook",
          not os.path.exists(marker_of(cfg, sid)), p.desc())
    saved = captured_texts(cfg, sid)
    p = capture(cfg, sid, "the owner's next message, after the close", now=at(1))
    check("next message: hook ran", ran_central(p), p.desc())
    check("next message: not saved, since the message before closed capture",
          bool(saved) and captured_texts(cfg, sid) == saved, captured_texts(cfg, sid))


def case_same_message_close_keeps_the_old_controls():
    """Controls: `fb: X` alone opens capture, `fb done` alone closes it, and `fb done` quoted
    mid-sentence does not close it (the close words count only at the start)."""
    cfg, sid = new_cfg(), "same-msg-controls"
    p = capture(cfg, sid, SAME_MSG_NOTE, now=at(0))
    check("control opener: hook ran", ran_central(p), p.desc())
    check("control opener: `fb: X` alone opens capture and is saved",
          os.path.exists(marker_of(cfg, sid)) and captured_texts(cfg, sid) == [SAME_MSG_NOTE],
          captured_texts(cfg, sid))
    quoted = "I typed fb done by mistake, so keep this message"
    p = capture(cfg, sid, quoted, now=at(1))
    check("control quote: hook ran", ran_central(p), p.desc())
    texts = [SAME_MSG_NOTE, quoted]
    check("control quote: a mid-sentence `fb done` does not close: saved, marker stays",
          os.path.exists(marker_of(cfg, sid)) and captured_texts(cfg, sid) == texts,
          captured_texts(cfg, sid))
    p = capture(cfg, sid, "fb done", now=at(2))
    check("control closer: hook ran", ran_central(p), p.desc())
    check("control closer: `fb done` alone closes capture and is not saved",
          not os.path.exists(marker_of(cfg, sid))
          and captured_texts(cfg, sid) == [SAME_MSG_NOTE, quoted], captured_texts(cfg, sid))


def case_close_words_count_only_as_a_last_line():
    """`fb done` closes only as the last line of a message. Inside a fence, in inline backticks, or
    on the same line as other text, it does not close (decision owner-feedback-inbox; `fb: X fb done`
    does not close either)."""
    for sid, text in (("fence-block", "fb: X\n```\nfb done\n```"),
                      ("fence-inline", "fb: X\n`fb done`"),
                      ("one-line", "fb: X fb done")):
        cfg = new_cfg()
        p = capture(cfg, sid, text, now=at(0))
        check("no close, opener %r: hook ran" % sid, ran_central(p), p.desc())
        check("no close, opener %r: capture stays open, whole message saved verbatim" % sid,
              os.path.exists(marker_of(cfg, sid)) and captured_texts(cfg, sid) == [text],
              captured_texts(cfg, sid))
    for sid, text in (("open-fence-block", "X\n```\nfb done\n```"),
                      ("open-fence-inline", "X\n`fb done`"),
                      ("open-one-line", "X fb done")):
        cfg = new_cfg()
        capture(cfg, sid, "fb: open the burst", now=at(0))
        p = capture(cfg, sid, text, now=at(1))
        check("no close, open %r: hook ran" % sid, ran_central(p), p.desc())
        check("no close, open %r: capture stays open, message saved verbatim" % sid,
              os.path.exists(marker_of(cfg, sid))
              and captured_texts(cfg, sid) == ["fb: open the burst", text],
              captured_texts(cfg, sid))


def case_open_last_line_fb_done_starts_no_judge():
    """With capture open, a message `X` plus a last line `fb done` saves X, closes capture, and
    starts no judge child. Guards the `and not closing` clause in local_time.py capture()."""
    cfg, sid = new_cfg(), "open-close-no-judge"
    capture(cfg, sid, "fb: open the burst", now=at(0))
    before = calls_so_far(cfg)
    p = capture(cfg, sid, "X\nfb done", now=at(1))
    check("open close: hook ran", ran_central(p), p.desc())
    texts = captured_texts(cfg, sid)
    check("open close: X is saved as the note, and capture closes",
          not os.path.exists(marker_of(cfg, sid)) and len(texts) == 2
          and texts[0] == "fb: open the burst" and texts[1].split("\n")[0] == "X", texts)
    check("open close: the closing message starts no judge child (no judge call)",
          no_judge_call(cfg, before, p), p.desc())


def case_notices_are_never_captured():
    for label, notice in (("task-notification", NOTICE_TASK), ("system-reminder", NOTICE_REMINDER)):
        cfg, sid = new_cfg(), "notice-" + label
        opened(cfg, sid, "fb: open the burst")
        before = calls_so_far(cfg)
        p = capture(cfg, sid, notice)
        check("notice %s: hook ran" % label, ran_central(p), p.desc())
        check("notice %s: not saved, capture stays open, and no judge call" % label,
              captured_texts(cfg, sid) == ["fb: open the burst"]
              and os.path.exists(marker_of(cfg, sid)) and no_judge_call(cfg, before, p),
              captured_texts(cfg, sid))
        before = calls_so_far(cfg)
        capture(cfg, sid, "owner reply after the notice", delay=SLOW)
        check("notice %s: the next owner prompt is saved, and judged once by the child" % label,
              captured_texts(cfg, sid) == ["fb: open the burst", "owner reply after the notice"]
              and calls_so_far(cfg) == before + 1, captured_texts(cfg, sid))
    cfg, sid = new_cfg(), "notice-quoted"
    opened(cfg, sid, "fb: open the burst")
    quoted = "the log shows a <task-notification> tag I did not expect; look into it"
    capture(cfg, sid, quoted)
    check("notice quoted mid-message: owner text, so it is captured",
          captured_texts(cfg, sid) == ["fb: open the burst", quoted], captured_texts(cfg, sid))


def case_quiet_gap_closes_capture():
    cfg, sid = new_cfg(), "quiet-gap"
    first = capture(cfg, sid, "fb: quiet burst", now=at(0))
    check("clock seam: LOCAL_TIME_NOW 18:00 UTC sets the Local time line to 13:00 CDT",
          first.out.strip() == "Local time: 2026-10-14 13:00 CDT (UTC-05:00)", first.desc())
    capture(cfg, sid, "second point, 8 minutes in", now=at(8), delay=SLOW)
    capture(cfg, sid, "third point, 16 minutes in", now=at(16), delay=SLOW)
    burst = ["fb: quiet burst", "second point, 8 minutes in", "third point, 16 minutes in"]
    check("quiet: prompts 8 and 16 minutes in are captured (the gap runs from the last capture)",
          captured_texts(cfg, sid) == burst, captured_texts(cfg, sid))
    check("quiet: prompts 8 and 16 minutes in are each judged once, by the child",
          calls_so_far(cfg) == 2, judge_calls(cfg))
    before = calls_so_far(cfg)
    p = capture(cfg, sid, "plain prompt after an 11 minute gap", now=at(27))
    check("quiet: the prompt after an 11 minute gap is not saved, capture closes, no judge call",
          ran_central(p) and not os.path.exists(marker_of(cfg, sid))
          and captured_texts(cfg, sid) == burst and no_judge_call(cfg, before, p), p.desc())
    capture(cfg, sid, "fb: new burst after the gap", now=at(28))
    check("quiet: an opener after the gap is captured and opens capture again",
          captured_texts(cfg, sid) == burst + ["fb: new burst after the gap"]
          and os.path.exists(marker_of(cfg, sid)), captured_texts(cfg, sid))


def case_quiet_gap_ignores_notices():
    cfg, sid = new_cfg(), "quiet-notice"
    opener, point = "fb: burst with a notice in it", "owner point at 2 minutes"
    capture(cfg, sid, opener, now=at(0))
    capture(cfg, sid, point, now=at(2), delay=SLOW)  # the last captured owner message, judged live
    check("quiet and notice: the owner point at 2 minutes is saved and judged once, by the child",
          captured_texts(cfg, sid) == [opener, point] and calls_so_far(cfg) == 1, judge_calls(cfg))
    before = calls_so_far(cfg)
    p = capture(cfg, sid, NOTICE_TASK, now=at(8))
    check("quiet and notice: a notice 8 minutes in is not saved, not judged, and does not close capture",
          captured_texts(cfg, sid) == [opener, point]
          and os.path.exists(marker_of(cfg, sid)) and no_judge_call(cfg, before, p), p.desc())
    before = calls_so_far(cfg)
    p = capture(cfg, sid, "owner prompt 11 minutes after the last owner message", now=at(13))
    check("quiet and notice: 11 minutes after the owner point at 2 closes capture; not saved, no judge call",
          ran_central(p) and not os.path.exists(marker_of(cfg, sid))
          and captured_texts(cfg, sid) == [opener, point] and no_judge_call(cfg, before, p), p.desc())


def case_judge_runs_once_per_open_prompt_with_the_sonnet_id():
    cfg, sid = new_cfg(), "judge-once"
    before = calls_so_far(cfg)
    p = capture(cfg, sid, "plain prompt before any burst")
    check("judge: a closed plain prompt makes no judge call", no_judge_call(cfg, before, p), p.desc())
    before = calls_so_far(cfg)
    opened(cfg, sid, "fb: judged burst")
    check("judge: the opener makes no judge call", calls_so_far(cfg) == before, judge_calls(cfg))
    text = "second point, plain"
    before = calls_so_far(cfg)
    p = capture(cfg, sid, text, delay=SLOW)
    calls = judge_calls(cfg)[before:]
    check("judge: an open plain prompt makes exactly one judge call",
          len(calls) == 1 and bool(p.loaded), p.desc())
    if calls:
        timeout = calls[0].get("timeout")
        check("judge: the call uses the Sonnet id from decisions/agent-model-cap.md",
              model_of(calls[0]) == JUDGE_MODEL and JUDGE_MODEL in sonnet_ids(), calls[0].get("argv"))
        check("judge: the call is made by feedback_judge.py, the detached child, not by the hook",
              calls[0].get("script") == "feedback_judge.py", calls[0].get("script"))
        check("judge: the prompt text reaches the judge",
              text in (calls[0].get("prompt") or ""), calls[0].get("prompt"))
        check("judge: its timeout is a positive number (the hook does not wait for it)",
              isinstance(timeout, (int, float)) and timeout > 0, "judge timeout=%r" % (timeout,))
    check("judge: the judged prompt is saved",
          captured_texts(cfg, sid) == ["fb: judged burst", text], captured_texts(cfg, sid))


def case_judge_not_feedback_keeps_the_prompt_and_closes():
    cfg, sid = new_cfg(), "judge-not"
    kept = ["fb: burst the judge will close", "second point, still feedback"]
    opened(cfg, sid, kept[0])
    capture(cfg, sid, kept[1], delay=SLOW)
    text = "ok, run the tests now"
    before = calls_so_far(cfg)
    p = capture(cfg, sid, text, judge="not", delay=SLOW)
    check("judge not feedback: hook ran, and the child judged the prompt once",
          ran_central(p) and calls_so_far(cfg) == before + 1, p.desc())
    check("judge not feedback: the prompt is saved, and capture closes (marker gone)",
          captured_texts(cfg, sid) == kept + [text] and not os.path.exists(marker_of(cfg, sid)),
          captured_texts(cfg, sid))
    check("judge not feedback: one note item under that message says judged not feedback, none elsewhere",
          len(judged_notes(block_items(cfg, sid, text))) == 1
          and not judged_notes(block_items(cfg, sid, kept[1])), block_items(cfg, sid, text))
    g = gate(cfg, sid)
    check("judge not feedback: the gate does not block on that message, and no capture reminder shows",
          g.code == 0 and text not in (block_reason(g) or "") and reminder_of(gate_json(g)) is None,
          g.desc())
    before = calls_so_far(cfg)
    p = capture(cfg, sid, "a later plain prompt")
    check("judge not feedback: the next plain prompt is not saved and makes no judge call",
          no_judge_call(cfg, before, p) and captured_texts(cfg, sid) == kept + [text], p.desc())
    capture(cfg, sid, "fb: a new burst")
    check("judge not feedback: an opener reopens capture",
          captured_texts(cfg, sid) == kept + [text, "fb: a new burst"]
          and os.path.exists(marker_of(cfg, sid)), captured_texts(cfg, sid))


def case_judge_failure_keeps_capture_open_and_saves():
    cfg, sid = new_cfg(), "judge-fail"
    opened(cfg, sid, "fb: burst before the failures")
    saved = ["fb: burst before the failures"]
    for answer in ("timeout", "exit1", "bad-shape"):
        text = "message while the judge answers %s" % answer
        before = calls_so_far(cfg)
        p = capture(cfg, sid, text, judge=answer, delay=SLOW)
        saved.append(text)
        check("judge %s: hook ran" % answer, ran_central(p), p.desc())
        check("judge %s: judged once, and the prompt is saved with capture still open" % answer,
              calls_so_far(cfg) == before + 1 and os.path.exists(marker_of(cfg, sid))
              and captured_texts(cfg, sid) == saved, captured_texts(cfg, sid))
        check("judge %s: no note item under the message" % answer,
              block_items(cfg, sid, text) == [] and not judged_notes(block_items(cfg, sid, text)),
              block_items(cfg, sid, text))


def case_judge_child_closes_only_the_last_captured_message():
    """The child closes capture only while the message it judged is still the last captured one.
    The child runs in the foreground here, the way the inline seam runs it."""
    cfg, sid = new_cfg(), "judge-last"
    first, second = "first owner point", "second owner point, the last captured"
    # The state is written directly. Setup captures would start detached children, and their late
    # calls would race the counts. The blocks use the hook's format; the marker holds 18:04 UTC.
    write_file(inbox_of(cfg, sid),
               render_block("fb: burst for the last-message rule",
                            header="2026-10-14 13:00 CDT (UTC-05:00)")
               + render_block(first, header="2026-10-14 13:02 CDT (UTC-05:00)")
               + render_block(second, header="2026-10-14 13:04 CDT (UTC-05:00)"))
    write_file(marker_of(cfg, sid), at(4))
    before = calls_so_far(cfg)
    p = run(JUDGE_PATH, b"", cfg, args=(sid, at(2), first), judge="not")
    check("last message: the child for an older message ran and made one judge call",
          p.code == 0 and calls_so_far(cfg) == before + 1, p.desc())
    check("last message: the older message gets no note, and capture stays open at the newer time",
          block_items(cfg, sid, first) == [] and os.path.exists(marker_of(cfg, sid))
          and read_or_empty(marker_of(cfg, sid)).strip() == at(4), read_or_empty(marker_of(cfg, sid)))
    p = run(JUDGE_PATH, b"", cfg, args=(sid, at(4), second), judge="not")
    check("last message: the child for the last captured message adds its note and closes capture",
          p.code == 0 and len(judged_notes(block_items(cfg, sid, second))) == 1
          and not os.path.exists(marker_of(cfg, sid)), p.desc())


def case_judge_child_is_detached_hook_returns_first():
    """Without the seam the judge child is detached: the hook returns before a slow judge answers."""
    cfg, sid = new_cfg(), "detached"
    opener = "fb: burst while the judge is slow"
    text = "a not-feedback prompt the slow judge will answer"
    opened(cfg, sid, opener)
    started = time.monotonic()
    p = capture(cfg, sid, text, judge="not", inline=False, delay="5")
    elapsed = time.monotonic() - started
    check("detached: the hook returns in under 3 s while the judge sleeps 5 s",
          ran_central(p) and elapsed < 3.0, "elapsed=%.2f s %s" % (elapsed, p.desc()))
    check("detached: the prompt is saved, and no note or close has happened yet",
          captured_texts(cfg, sid) == [opener, text] and os.path.exists(marker_of(cfg, sid))
          and not judged_notes(block_items(cfg, sid, text)), captured_texts(cfg, sid))


# Row tables. A row is one case body from above. A row that raises is red and names
# itself, so it cannot hide behind its table.
def run_rows(rows):
    for body in rows:
        try:
            body()
        except Exception as exc:
            check("%s: case ran" % body.__name__, False, "%s: %s" % (type(exc).__name__, exc))


def table_open_forms():
    run_rows((case_open_survives_across_runs, case_opener_forms))


def table_close_forms():
    run_rows((case_fb_done_closes_and_is_not_captured, case_fb_done_forms_close_capture,
              case_fb_done_prefix_closes_and_drops_the_rest))


def table_quiet_gap():
    run_rows((case_quiet_gap_closes_capture, case_quiet_gap_ignores_notices))


def table_gate_handoff_drops():
    run_rows((case_gate_open_item_missing_from_handoff_blocks,
              case_gate_handoff_rewrite_that_drops_an_item_blocks,
              case_gate_missing_handoff_counts_every_open_id_missing))


def table_gate_scanner_text():
    run_rows((case_gate_scanner_text_yields_no_phantom_block_or_item,
              case_gate_scanner_text_with_real_items_passes_silently))


def table_reorient_forms():
    run_rows((case_reorient_lists_open_items_only, case_reorient_capture_open_line,
              case_reorient_items_and_capture_line_together,
              case_reorient_malformed_line_keeps_the_note,
              case_reorient_nothing_when_no_open_items_and_no_marker))


CASES = (
    case_closed_by_default,
    case_opener_captured_with_central_time,
    table_open_forms,
    table_close_forms,
    case_near_miss_closers_open_nothing_while_closed,
    case_fb_done_prefix_opens_nothing_while_closed,
    case_fb_done_line_at_the_end_closes_in_the_same_message,
    case_same_message_close_keeps_the_old_controls,
    case_close_words_count_only_as_a_last_line,
    case_open_last_line_fb_done_starts_no_judge,
    case_notices_are_never_captured,
    table_quiet_gap,
    case_judge_runs_once_per_open_prompt_with_the_sonnet_id,
    case_judge_not_feedback_keeps_the_prompt_and_closes,
    case_judge_failure_keeps_capture_open_and_saves,
    case_judge_child_closes_only_the_last_captured_message,
    case_verbatim_scanner_text_is_fenced,
    case_fail_open_writes_nothing,
    case_capture_write_failure_says_not_saved,
    case_lone_surrogate_is_saved_or_said_not_saved,
    case_agent_never_opens_closes_or_captures,
    case_sessions_are_isolated,
    case_gate_no_inbox_and_empty_inbox_pass_silently,
    case_gate_all_jotted_passes_silently,
    case_gate_message_without_items_blocks_and_names_it,
    case_gate_item_without_kind_or_home_blocks,
    case_gate_malformed_item_line_blocks_and_names_it,
    table_gate_handoff_drops,
    case_gate_closed_item_is_not_required_in_handoff,
    case_gate_id_match_is_a_whole_token,
    table_gate_scanner_text,
    case_gate_notes_heading_is_plain_text,
    case_gate_reminder_follows_capture_state,
    case_gate_unreadable_inbox_blocks_and_names_the_file,
    case_gate_reads_only_its_own_session,
    case_gate_ruling_homed_to_handoff_blocks,
    case_gate_task_homed_to_untracked_file_blocks,
    case_gate_home_outside_its_kind_blocks,
    case_gate_tracked_homes_pass_without_the_handoff,
    case_gate_standing_homed_to_handoff_passes,
    case_gate_task_home_from_extras_todo_key,
    case_gate_unreadable_layout_fails_open_with_one_line,
    table_reorient_forms,
    case_reorient_unreadable_inbox_prints_message_and_one_stderr_line,
    case_judge_child_is_detached_hook_returns_first,  # last: it leaves a 5 s child running
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
        install_judge_stub()
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
