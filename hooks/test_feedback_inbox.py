#!/usr/bin/env python3
"""Cases for the owner feedback inbox: the capture hook and the Stop gate. Standard library only,
and no test runner.

Run it from the repository root:

    python hooks/test_feedback_inbox.py

Every case runs the real script as a child process, the way the harness does. The payload goes in
on stdin as UTF-8 bytes. PYTHONUTF8 and PYTHONIOENCODING are unset in the child. CLAUDE_CONFIG_DIR,
HOME and USERPROFILE all point into a scratch folder, so no case touches the owner's ~/.claude.
Each case reads back the exit code, stdout, stderr and the files written.

Stub runs: FEEDBACK_INBOX_STUB=always-pass-gate runs the cases against a gate that always passes.
The block cases must then go red. FEEDBACK_INBOX_STUB=always-capture-hook runs them against a hook
that captures every prompt. The closed-state cases must then go red. Each stub is written into this
run's scratch folder, never into the repo.

Seams the builder codes against.

Capture: hooks/local_time.py (env LOCAL_TIME_UNDER_TEST overrides the path). A UserPromptSubmit
  hook. Stdin is one JSON object: hook_event_name, session_id, prompt, cwd. Stdout is one
  "Local time: ..." line. Exit 0. A write failure adds one stdout line; see below.
  - While closed, a prompt whose first word is `fb` or `fb:` opens capture, and the opening prompt
    is captured. Near-misses of the close form open nothing: `fb: done`, `fb  done` (two spaces),
    a tab in place of the space in `fb done`, and `fb - done`. Plain `fb done` opens nothing.
  - While open, a prompt that is only `fb done` closes capture and is not captured. `fb: done` and
    `fb  done` (two spaces) close too. Surrounding whitespace and trailing punctuation are ignored,
    and letter case does not matter: `fb done.`, `fb done!` and `FB done` all close. `fb done now`
    does not close.
  - While open, every owner prompt is captured verbatim, including `x fb`, `fbi ...` and
    `fb done now`. Neither closes capture. Only the close forms above close it.
  - While closed, only the opener is captured; every other prompt is dropped.
  - While open, a lone surrogate in the text (JSON escape `\\ud800`) is either saved with U+FFFD
    (the replacement character) in its place, or stdout carries a line that says `not saved`.
    Never silent. Capture stays open, and the inbox stays strict UTF-8.
  - State is per session_id and survives across runs. Another session's prompts are never captured.
  - `--subagent` (a SubagentStart payload) prints the same hookSpecificOutput JSON and never opens,
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
    home is any non-empty text after `->`.

Gate: hooks/feedback_gate.py (env FEEDBACK_GATE_UNDER_TEST overrides the path). A Stop hook. Stdin
  is one JSON object: hook_event_name, session_id, stop_hook_active, cwd. It reads the inbox and the
  handoff <CLAUDE_CONFIG_DIR>/handoffs/<session_id>.md. Exit 0 in every case. Stdout is one JSON
  object or nothing.
  - stop_hook_active true: exit 0, nothing on stdout, at once.
  - No inbox, or an empty inbox: nothing on stdout.
  - A block is {"decision": "block", "reason": ...}. The reason names each offending id, or the
    message by its Central stamp or the start of its text. Offences: a captured message with no
    items; an item with no kind, an unknown kind, or no home; an open item (ruling, task, standing)
    whose id is not in the handoff as a whole token. A missing handoff file means every open id is
    missing.
  - A malformed item line is an offence: a `- fb-` line whose id is not a token, such as
    `- fb- [task] -> x` or a bare `- fb-`. The reason quotes the line's text after the leading
    `- `, for example `fb- [task] -> x`. The gate does not crash on it.
  - An item line that ends with `[closed]` is closed. Its id is not required in the handoff. Its
    kind and home are still checked.
  - An unreadable inbox (a directory at its path, or bytes that are not UTF-8) gives one block that
    names the inbox file. Why: a Stop hook's stderr does not reach the owner, so a silent pass would
    drop feedback. stop_hook_active still gives nothing, so the block costs one turn at most.
  - While capture is open, stdout carries "systemMessage" (the universal hook field) naming
    `fb done`. It rides on a pass and on a block. While capture is closed, there is no systemMessage.
  - Another session's inbox is never read.

Reorient: hooks/precompact_handoff.py `--reorient` (env PRECOMPACT_HANDOFF_UNDER_TEST overrides the
  path). Each of its two messages ends with an inbox note, or with nothing:
  - open ids (ruling, task, standing) in the inbox:
    " Open feedback items: <ids>. Keep each in the handoff."
  - the open marker <session>.inbox.open exists: " Feedback capture is still open: the owner has not
    sent `fb done`."
  - both, items first. Neither: the message is unchanged. An unreadable inbox gives no note, one
    stderr line, and the message still prints.
  - A malformed item line is never listed as an id. The other ids and the capture line still print.
  Stub kinds for the reorient cases: FEEDBACK_INBOX_STUB=empty-inbox-note (inbox_note returns
  "") and always-capture-line (inbox_note always returns the capture line). Each is a copy of the
  real file with that one body swapped, written into this run's scratch folder, never the repo.

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
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LT_PATH = os.environ.get("LOCAL_TIME_UNDER_TEST") or os.path.join(HERE, "local_time.py")
GATE_PATH = os.environ.get("FEEDBACK_GATE_UNDER_TEST") or os.path.join(HERE, "feedback_gate.py")
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
    "- fb-0958-1 [ruling] -> handoff: NO HOME YET",
    "- fb-0958-2 [task] -> handoff: next steps",
    "- fb-0958-3 [question] -> answered",
    "- fb-0958-4 [note] -> noted",
    "- fb-0958-5 [standing] -> handoff: process-only",
)
JOTTED_HANDOFF = ("# Handoff\n- fb-0958-1 ruling, NO HOME YET\n- fb-0958-2 task\n"
                  "- fb-0958-5 standing\n")


STUB_SOURCES = {
    "always-pass-gate": "import sys\nsys.exit(0)\n",
    "always-capture-hook": '''import json, os, sys
try:
    d = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    p = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "handoffs", d["session_id"] + ".inbox.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write("### stub\\n" + d["prompt"] + "\\n")
except Exception:
    pass
print("Local time: 2026-10-13 10:04 CDT (UTC-05:00)")
''',
}


# Each replaces the body of inbox_note in a copy of precompact_handoff.py. The real file is read
# only. A mutant must go red on the reorient cases it names, or the case is not guarding anything.
PRECOMPACT_MUTANTS = {
    "empty-inbox-note": '    return ""',
    "always-capture-line":
        '    return " Feedback capture is still open: the owner has not sent `fb done`."',
}


def write_precompact_mutant(kind):
    """Writes the mutant copy into this run's scratch folder and returns its path. HERE goes on
    sys.path first, so the copy still imports the real local_time and feedback_gate."""
    with open(os.path.join(HERE, "precompact_handoff.py"), encoding="utf-8") as f:
        src = f.read()
    head = "def inbox_note(session_id):\n"
    if src.count(head) != 1:
        raise SystemExit("cannot mutate inbox_note: its def line appears %d times"
                         % src.count(head))
    path = os.path.join(ROOT, kind, "precompact_handoff.py")
    write_file(path, "import sys\nsys.path.insert(0, %r)\n" % HERE
               + src.replace(head, head + PRECOMPACT_MUTANTS[kind] + "\n", 1))
    return path


def install_stub():
    """Points one module at a stub written into this run's scratch folder. No env var: real paths."""
    global LT_PATH, GATE_PATH, PRECOMPACT_PATH
    kind = os.environ.get("FEEDBACK_INBOX_STUB", "")
    if not kind:
        return
    if kind in PRECOMPACT_MUTANTS:
        PRECOMPACT_PATH = write_precompact_mutant(kind)
        return
    if kind not in STUB_SOURCES:
        raise SystemExit("FEEDBACK_INBOX_STUB must be one of: %s"
                         % ", ".join(list(STUB_SOURCES) + list(PRECOMPACT_MUTANTS)))
    path = os.path.join(ROOT, kind + ".py")
    write_file(path, STUB_SOURCES[kind])
    if kind == "always-pass-gate":
        GATE_PATH = path
    else:
        LT_PATH = path


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
    for name in ("PYTHONUTF8", "PYTHONIOENCODING", "CLAUDE_CONFIG_DIR"):
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


def gate(cfg, sid, stop_active=False):
    return run(GATE_PATH, payload({"hook_event_name": "Stop", "session_id": sid,
                                   "stop_hook_active": stop_active, "cwd": cfg}), cfg)


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
    check("fb done now: does not close; it is captured and capture stays open",
          os.path.exists(marker_of(cfg, sid))
          and captured_texts(cfg, sid) == ["fb: open the burst", "fb done now"],
          captured_texts(cfg, sid))


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


def subagent_ok(p):
    try:
        hso = json.loads(p.out)["hookSpecificOutput"]
    except (ValueError, KeyError, TypeError):
        return False
    return (p.code == 0 and hso.get("hookEventName") == "SubagentStart"
            and CENTRAL.fullmatch(str(hso.get("additionalContext", ""))) is not None)


def sub_payload(sid, prompt, cfg):
    return payload({"hook_event_name": "SubagentStart", "session_id": sid,
                    "agent_type": "test-author", "prompt": prompt, "cwd": cfg})


def case_subagent_never_opens_closes_or_captures():
    cfg = new_cfg()
    p0 = capture(cfg, "sub-open", "fb: opened by the owner")
    check("subagent: owner opener ran", ran_central(p0), p0.desc())
    before = read_or_empty(inbox_of(cfg, "sub-open"))
    p = run(LT_PATH, sub_payload("sub-open", "fb done", cfg), cfg, args=("--subagent",))
    check("subagent: fb done payload prints the SubagentStart JSON", subagent_ok(p), p.desc())
    check("subagent: an open inbox is unchanged by a subagent fb done",
          before != "" and read_or_empty(inbox_of(cfg, "sub-open")) == before, "changed")
    p2 = capture(cfg, "sub-open", "still open after the subagent")
    check("subagent: next owner prompt ran", ran_central(p2), p2.desc())
    check("subagent: capture is still open, the next owner prompt is captured",
          captured_texts(cfg, "sub-open") == ["fb: opened by the owner",
                                              "still open after the subagent"],
          captured_texts(cfg, "sub-open"))
    q = run(LT_PATH, sub_payload("sub-closed", "fb: subagent opener", cfg), cfg,
            args=("--subagent",))
    check("subagent: fb: payload prints the SubagentStart JSON", subagent_ok(q), q.desc())
    p3 = capture(cfg, "sub-closed", "plain owner prompt after a subagent opener")
    check("subagent: owner prompt after a subagent opener ran", ran_central(p3), p3.desc())
    check("subagent: a subagent opener does not open capture (no inbox file)",
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
                            items=("- fb-0958-2 [task] -> handoff",))
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
    items = ("- fb-0958-2 [ruling] -> NO HOME YET", "- fb-0958-3 [task] -> handoff",
             "- fb-0958-4 [standing] -> handoff")
    write_file(inbox_of(cfg, sid), render_block("open ids burst", items=items))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 ruling, NO HOME YET\n")
    expect_block("gate: open task and standing missing from the handoff", gate(cfg, sid),
                 named=("fb-0958-3", "fb-0958-4"), unnamed=("fb-0958-2",))
    expect_silent("gate: stop_hook_active gives nothing, even with missing open ids",
                  gate(cfg, sid, stop_active=True))


def case_gate_id_match_is_a_whole_token():
    cfg, sid = new_cfg(), "boundary"
    write_file(inbox_of(cfg, sid),
               render_block("boundary", items=("- fb-0958-2 [task] -> handoff",)))
    write_file(handoff_of(cfg, sid), "- fb-0958-20 task, a different item\n")
    expect_block("gate: fb-0958-20 in the handoff does not count for fb-0958-2", gate(cfg, sid),
                 named=("fb-0958-2",))


def case_gate_handoff_rewrite_that_drops_an_item_blocks():
    cfg, sid = new_cfg(), "rewrite"
    write_file(inbox_of(cfg, sid), render_block(
        "two open items", items=("- fb-0958-2 [task] -> handoff",
                                 "- fb-0958-3 [ruling] -> NO HOME YET")))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task, kept\n")
    expect_block("gate: a handoff rewrite that drops fb-0958-3 blocks", gate(cfg, sid),
                 named=("fb-0958-3",), unnamed=("fb-0958-2",))


def case_gate_missing_handoff_counts_every_open_id_missing():
    cfg, sid = new_cfg(), "no-handoff"
    write_file(inbox_of(cfg, sid), render_block("no handoff yet",
                                                items=("- fb-0958-2 [ruling] -> NO HOME YET",)))
    expect_block("gate: open ruling with no handoff file blocks", gate(cfg, sid),
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
    write_file(inbox_of(cfg, sid), render_block(SCANNER, items=("- fb-0958-2 [task] -> handoff",)))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    expect_silent("gate: scanner text with real items passes (fake fb-0999-1 is not read)",
                  gate(cfg, sid))


def case_gate_malformed_item_line_blocks_and_names_it():
    cfg, sid = new_cfg(), "malformed-item"
    write_file(inbox_of(cfg, sid), render_block("malformed item beside a good one", items=(
        "- fb- [task] -> x", "- fb-0958-2 [task] -> handoff")))
    write_file(handoff_of(cfg, sid), "- fb-0958-2 task\n")
    expect_block("gate: malformed `- fb- [task] -> x` beside a handed-off item", gate(cfg, sid),
                 named=("fb- [task] -> x",), unnamed=("fb-0958-2",))
    cfg, sid = new_cfg(), "malformed-bare"
    write_file(inbox_of(cfg, sid), render_block("a bare fb- line", items=("- fb-",)))
    expect_block("gate: bare `- fb-` line", gate(cfg, sid), named=("fb-",))


def case_gate_closed_item_is_not_required_in_handoff():
    cfg, sid = new_cfg(), "closed-item"
    write_file(inbox_of(cfg, sid), render_block("closed task and ruling", items=(
        "- fb-0958-2 [task] -> handoff: done [closed]",
        "- fb-0958-3 [ruling] -> NO HOME YET [closed]")))
    write_file(handoff_of(cfg, sid), "# Handoff\n")
    expect_silent("gate: closed task and ruling missing from the handoff pass silently",
                  gate(cfg, sid))
    cfg, sid = new_cfg(), "closed-and-open"
    write_file(inbox_of(cfg, sid), render_block("one closed, one open", items=(
        "- fb-0958-2 [task] -> handoff: done [closed]", "- fb-0958-4 [task] -> handoff")))
    write_file(handoff_of(cfg, sid), "# Handoff\n")
    expect_block("gate: open task still required beside a closed one", gate(cfg, sid),
                 named=("fb-0958-4",), unnamed=("fb-0958-2",))


def case_gate_notes_heading_is_plain_text():
    cfg, sid = new_cfg(), "notes-heading"
    write_file(inbox_of(cfg, sid), render_block("jotted burst", items=(
        "- fb-0958-2 [task] -> handoff",)) + "### Notes\nsome notes the session wrote by hand\n")
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
               render_block("own jotted", items=("- fb-0958-2 [task] -> handoff",)))
    write_file(handoff_of(cfg, "own"), "- fb-0958-2 task\n")
    write_file(inbox_of(cfg, "other"),
               render_block("other incomplete", items=("- fb-0958-9 [ruling] -> NO HOME YET",)))
    os.makedirs(inbox_of(cfg, "other-bad"))
    expect_silent("gate: own session passes; other sessions' inboxes do not block it",
                  gate(cfg, "own"))


# --------------------------------------------------------------------------- reorient note

NOTE_CAPTURE = " Feedback capture is still open: the owner has not sent `fb done`."


def case_reorient_lists_open_items_only():
    cfg = new_cfg()
    sid = "reo-items"
    write_file(inbox_of(cfg, sid), render_block(SCANNER, items=JOTTED_ITEMS))
    note = " Open feedback items: fb-0958-1, fb-0958-2, fb-0958-5. Keep each in the handoff."
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
    note = " Open feedback items: fb-0958-2, fb-0958-3. Keep each in the handoff." + NOTE_CAPTURE
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
    note = " Open feedback items: fb-0958-2, fb-0958-3. Keep each in the handoff." + NOTE_CAPTURE
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


CASES = (
    case_closed_by_default,
    case_opener_captured_with_central_time,
    case_opener_forms,
    case_open_survives_across_runs,
    case_fb_done_closes_and_is_not_captured,
    case_fb_done_forms_close_capture,
    case_near_miss_closers_open_nothing_while_closed,
    case_verbatim_scanner_text_is_fenced,
    case_fail_open_writes_nothing,
    case_capture_write_failure_says_not_saved,
    case_lone_surrogate_is_saved_or_said_not_saved,
    case_subagent_never_opens_closes_or_captures,
    case_sessions_are_isolated,
    case_gate_no_inbox_and_empty_inbox_pass_silently,
    case_gate_all_jotted_passes_silently,
    case_gate_message_without_items_blocks_and_names_it,
    case_gate_item_without_kind_or_home_blocks,
    case_gate_malformed_item_line_blocks_and_names_it,
    case_gate_open_item_missing_from_handoff_blocks,
    case_gate_closed_item_is_not_required_in_handoff,
    case_gate_id_match_is_a_whole_token,
    case_gate_handoff_rewrite_that_drops_an_item_blocks,
    case_gate_missing_handoff_counts_every_open_id_missing,
    case_gate_scanner_text_yields_no_phantom_block_or_item,
    case_gate_scanner_text_with_real_items_passes_silently,
    case_gate_notes_heading_is_plain_text,
    case_gate_reminder_follows_capture_state,
    case_gate_unreadable_inbox_blocks_and_names_the_file,
    case_gate_reads_only_its_own_session,
    case_reorient_lists_open_items_only,
    case_reorient_capture_open_line,
    case_reorient_items_and_capture_line_together,
    case_reorient_malformed_line_keeps_the_note,
    case_reorient_nothing_when_no_open_items_and_no_marker,
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
        install_stub()
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
