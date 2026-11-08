#!/usr/bin/env python3
"""Cases for the pick-names-rulings guard (rule `pick-names-rulings`, step pick-ack-past-ruling). A pick that
departs from main, or a reply that agrees to one, names the decisions it checked, or the guard asks. The form of
a Departs from line is decision port-keeps-behaviour; hooks/question_form.py DEPARTS_LINE is its one pattern.
Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_pick_ack.py

Interface the code must match (hooks/guard_merge.py, beside brief_hit):
- pick_ack_hit(tool, tool_input, transcript, cwd="", own_id="") -> (matched, reason) when the send asks, else None.
  `transcript` is the path of the JSONL transcript. `cwd` and `own_id` are the payload's cwd and session_id, as
  hooks/guard.py passes them. The past-ruling check runs in the repo of `cwd`.
- Two id spaces. The payload session_id and each transcript record's sessionId are this session's local UUID. The
  get_session record's ccr.id is the remote id (session_<x>), and so is the peer frame's from-session. The env
  CLAUDE_CODE_REMOTE_SESSION_ID holds the same id as cse_<x>; hooks/override.py remote_session_id maps it back.
- Trigger A: the message has a line that starts `Departs from:`, outside a code fence. Bold, bulleted, numbered and
  `>`-quoted labels count too, as DEPARTS_LINE reads them.
- Trigger B: the newest inbound peer frame from the target session_id carries a Departs from line, and this send is
  the first send to that target since that frame. A frame is read in the real shape (a `user` record with no origin
  key, whose string content opens `<cross-session-message from-session="<id>">`) or in the origin shape.
- A send to session_id `@parent` goes to the parent_session_id that the own get_session record names (the reader is
  hooks/own_session.py own_session_read, matched on the remote id). With no transcript path, or with a parent that
  cannot be resolved, trigger B cannot be read: such a send passes, with one stderr line that starts
  `pick-names-rulings: `.
- A trigger that fires passes when the message has a `Checked: <id>[, <id>...]` line that names an id
  question_form.candidate_ids(question_form.past_rulings(...)) returns: `decisions/<slug>` or the bare slug.
- past_rulings runs only when a trigger fires.
- hooks/guard.py calls it for mcp__claude-code-remote__send_message. A refusal is decision "ask", and the printed
  reason starts with `pick-names-rulings: `.

A missing function fails each case by name (`missing function`), never by a crash.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  the git fixtures (make_repo, DECISIONS_REPO) and DEPARTS_LINE; its ROOT is this run's folder

RUN_FOLDER = tcj.ROOT
REPO = tcj.DECISIONS_REPO  # docs/decisions holds tcj.APPS_SLUG, the one real decision the cases cite
REAL_ID = "decisions/" + tcj.APPS_SLUG
MADE_UP_ID = "decisions/no-such-ruling-q7x"
TOOL = "mcp__claude-code-remote__send_message"
GET_SESSION = "mcp__claude-code-remote__get_session"
LANE_ENV = "CLAUDE_CODE_REMOTE_SESSION_ID"
OWN_UUID = "5d1e8c3a-2b6f-4e9a-8c07-3f4a1d9e6b28"  # this session's local id: the payload session_id, each sessionId
OWN_REMOTE = "session_PICKSELF01"  # this session's remote id: the get_session record's ccr.id
OWN_ENV = "cse_PICKSELF01"  # what LANE_ENV holds for OWN_REMOTE
TARGET = "session_PICKTGT01"  # the lane the send goes to
OTHER = "session_PICKOTHER01"  # another lane
PARENT = "session_PICKPARENT01"  # this session's parent: the target of a send to "@parent"
FIXTURE_TIME = "2026-11-08T09:00:00.000Z"  # a fixed stamp: no case reads the clock
PICK = ("Goal: keep the stamp check in the lint job.\n"
        "Problem (rule): the stamp runs after lint, so a red stamp hides the lint verdict.\n"
        "Based on (measured): the stamp ran 3 minutes after lint in the last 20 runs.\n" + tcj.DEPARTS_LINE)
AGREED = "Agreed. Keep the stamp check in the lint job."
PLAIN = "Status: PR #12 is merged; the lane is idle."
FENCED = ("Status: the lane quotes the form of a pick and makes none.\n"
          "```\n" + tcj.DEPARTS_LINE + "\n```\n"
          "The lane is idle.")
FAILED = []


def check(name, ok, detail=""):
    if ok:
        print("ok   " + name)
    else:
        FAILED.append(name)
        print("FAIL " + name + (" :: " + str(detail) if detail else ""))


# ------------------------------------------------------------------ transcript fixtures

def owner_said(text):
    return {"type": "user", "cwd": REPO, "message": {"role": "user", "content": text}}


def inbound(from_session, body):
    """A peer message in the origin shape: a meta user record with an origin key. The real transcripts hold
    real_inbound's shape instead; this one stays for the cases that name it."""
    frame = ('<cross-session-message from="uds:fixture-pipe" from-session="%s" from-name="peer-lane" '
             'from-mode="bypass">%s</cross-session-message>' % (from_session, body))
    return {"type": "user", "cwd": REPO, "isSidechain": False, "isMeta": True,
            "origin": {"kind": "peer", "from": "uds:fixture-pipe", "fromSession": from_session,
                       "fromMode": "bypass", "name": "peer-lane", "body": body},
            "message": {"role": "user", "content": "Another Claude session sent a message:\n" + frame}}


def real_inbound(from_session, body):
    """A peer message as a real transcript holds it: a queue-operation enqueue record, then a `user` record with
    isMeta true and no origin key, whose string content is the frame. The frame opens
    `<cross-session-message from-session="<id>">` and closes `</cross-session-message>`. The ids and text are synthetic."""
    frame = '<cross-session-message from-session="%s">%s</cross-session-message>' % (from_session, body)
    enqueue = {"type": "queue-operation", "operation": "enqueue", "timestamp": FIXTURE_TIME,
               "sessionId": OWN_UUID, "content": frame}
    user = {"parentUuid": None, "isSidechain": False, "type": "user", "message": {"role": "user", "content": frame},
            "isMeta": True, "uuid": "fixture-peer-frame", "timestamp": FIXTURE_TIME, "promptSource": "system",
            "turnOrigin": "system", "entrypoint": "remote", "cwd": REPO, "sessionId": OWN_UUID}
    return [enqueue, user]


def real_frame_shape(record, from_session):
    """True when the record is the real shape of a peer message from `from_session`: no origin key, and string content
    that opens with that session's frame tag. A scope check, so a red verdict is not a bad fixture."""
    content = (record.get("message") or {}).get("content")
    return ("origin" not in record and isinstance(content, str)
            and content.startswith('<cross-session-message from-session="%s">' % from_session))


def own_session_record(parent):
    """A get_session call and its result for this session. The result is the record's JSON: a ccr block whose id is
    the remote id and which names its parent_session_id, as get_session returns it."""
    tool_id = "fixture-get-session"
    call = {"type": "tool_use", "id": tool_id, "name": GET_SESSION, "input": {}}
    body = json.dumps({"ccr": {"id": OWN_REMOTE, "title": "a lane session", "tags": [], "parent_session_id": parent}})
    done = {"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": body}]}
    return [{"type": "assistant", "cwd": REPO, "message": {"role": "assistant", "content": [call]}},
            {"type": "user", "cwd": REPO, "message": {"role": "user", "content": [done]}}]


def sent(target, message, tool_id):
    """A send_message call and its result, as a transcript holds them."""
    call = {"type": "tool_use", "id": tool_id, "name": TOOL, "input": {"session_id": target, "message": message}}
    done = {"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": "sent"}]}
    return [{"type": "assistant", "cwd": REPO, "message": {"role": "assistant", "content": [call]}},
            {"type": "user", "cwd": REPO, "message": {"role": "user", "content": [done]}}]


def transcript(name, items):
    """The JSONL transcript of `items` (one record, a list of them, or a list holding lists), in this run's folder.
    Returns its path. A bare record is one item: iterating it would walk its keys, so it is wrapped first. Every
    record names this session's local UUID as its sessionId, as a real transcript does, unless it names one."""
    folder = os.path.join(RUN_FOLDER, "pick")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".jsonl")
    if isinstance(items, dict):
        items = [items]
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            for rec in (item if isinstance(item, list) else [item]):
                f.write(json.dumps(dict(rec, sessionId=rec.get("sessionId", OWN_UUID))) + "\n")
    return path


# ------------------------------------------------------------------ calls into the check

def pick_fn(case):
    """guard_merge.pick_ack_hit, or None after its named failure."""
    import guard_merge  # the one home of the send_message checks (hooks/guard_merge.py)
    fn = getattr(guard_merge, "pick_ack_hit", None)
    check(case + ": guard_merge.pick_ack_hit exists", callable(fn), "missing function")
    return fn if callable(fn) else None


@contextlib.contextmanager
def in_repo():
    """The check reads the repo from the process cwd, so the cases run inside it."""
    back = os.getcwd()
    os.chdir(REPO)
    try:
        yield
    finally:
        os.chdir(back)


def send(fn, message, path, target=TARGET):
    """pick_ack_hit called as hooks/guard.py calls it: the payload's cwd and session_id (the local UUID)."""
    with in_repo():
        return fn(TOOL, {"session_id": target, "message": message}, path, REPO, OWN_UUID)


def send_capturing_stderr(fn, message, path, target=TARGET):
    """send(), with the stderr lines the check printed, blank lines dropped."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        got = send(fn, message, path, target)
    return got, [line for line in err.getvalue().splitlines() if line.strip()]


def asked(got):
    return isinstance(got, tuple) and len(got) == 2 and bool(got[1])


# ------------------------------------------------------------------ the cases

def case_departs_pick_without_checked_asks():
    case = "A: a departs pick with no Checked line asks"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, PICK, transcript("a-pick", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_inbound_pick_without_checked_asks():
    case = "B: a reply agreeing to a departs pick with no Checked line asks"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, AGREED, transcript("b-pick", inbound(TARGET, PICK)))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_real_frame_inbound_pick_without_checked_asks():
    case = "B: a reply to a pick in the real frame shape, with no Checked line, asks"
    fn = pick_fn(case)
    if fn is None:
        return
    frame = real_inbound(TARGET, PICK)
    check(case + ": scope: the fixture frame is the real shape from the target", real_frame_shape(frame[1], TARGET),
          "not the real shape")
    got = send(fn, AGREED, transcript("b-real-pick", [owner_said("Run the lint on the batch."), frame]))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_real_frame_inbound_pick_with_real_checked_passes():
    case = "B: a reply to a pick in the real frame shape, Checked naming a real decision, passes"
    fn = pick_fn(case)
    if fn is None:
        return
    path = transcript("b-real-checked", [owner_said("Run the lint on the batch."), real_inbound(TARGET, PICK)])
    got = send(fn, AGREED + "\nChecked: " + REAL_ID, path)
    check(case, got is None, "asked: got %r" % (got,))


def case_departs_pick_with_real_checked_passes():
    case = "A: a departs pick whose Checked line names a real decision passes"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, PICK + "\nChecked: " + REAL_ID, transcript("a-real", owner_said("Run the lint on the batch.")))
    check(case, got is None, "asked: got %r" % (got,))


def case_inbound_pick_with_real_checked_passes():
    case = "B: a reply agreeing to a departs pick, Checked naming a real decision, passes"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, AGREED + "\nChecked: " + REAL_ID, transcript("b-real", inbound(TARGET, PICK)))
    check(case, got is None, "asked: got %r" % (got,))


def case_parent_send_asks_on_parent_departs_frame():
    case = "@parent: a reply to the parent asks when the parent's newest frame has Departs and no Checked line"
    fn = pick_fn(case)
    if fn is None:
        return
    import own_session  # the one reader of a session's own get_session record (hooks/own_session.py)
    path = transcript("parent-ask", [owner_said("Run the lint on the batch."), own_session_record(PARENT),
                                     real_inbound(PARENT, PICK)])
    named = own_session.own_session_read(path, OWN_REMOTE)[2]
    check(case + ": scope: the own get_session record names the parent", named == PARENT,
          "parent is %r" % (named,))
    with mock.patch.dict(os.environ) as env:
        env.pop(LANE_ENV, None)  # the env unset: the parent comes from the record's ccr.id
        got = send(fn, AGREED, path, target="@parent")
    check(case, asked(got), "no ask: got %r" % (got,))


def case_parent_send_without_parent_id_passes_with_stderr():
    case = "@parent: with no parent id resolvable, a reply to @parent passes, with one stderr line"
    fn = pick_fn(case)
    if fn is None:
        return
    import own_session  # the one reader of a session's own get_session record (hooks/own_session.py)
    path = transcript("parent-none", [owner_said("Run the lint on the batch."), real_inbound(PARENT, PICK)])
    check(case + ": scope: no get_session record names a parent",
          own_session.own_session_read(path, OWN_REMOTE)[2] is None, "a parent resolved")
    got, err = send_capturing_stderr(fn, AGREED, path, target="@parent")
    check(case, got is None, "asked: got %r" % (got,))
    check(case + ": one stderr line, naming the rule", len(err) == 1 and err[0].startswith("pick-names-rulings: "),
          "stderr lines: %r" % (err[:3],))


def parent_send_asks_with_uuid_payload(case, name, remote_env):
    """A real-shape reply to @parent asks when the payload id and the transcript's sessionId are this session's UUID,
    and the own get_session record names the remote id and its parent. `remote_env` is the value of
    CLAUDE_CODE_REMOTE_SESSION_ID, or None for an unset env."""
    fn = pick_fn(case)
    if fn is None:
        return
    import own_session  # the one reader of a session's own get_session record (hooks/own_session.py)
    import override  # the one reader of the remote env (hooks/override.py remote_session_id)
    path = transcript(name, [owner_said("Run the lint on the batch."), own_session_record(PARENT),
                             real_inbound(PARENT, PICK)])
    with mock.patch.dict(os.environ) as env:
        env.pop(LANE_ENV, None)
        if remote_env is not None:
            env[LANE_ENV] = remote_env
        check(case + ": scope: the env names the remote id, or no id when unset",
              override.remote_session_id() == (OWN_REMOTE if remote_env is not None else None),
              "env maps to %r" % (override.remote_session_id(),))
        check(case + ": scope: the own get_session record names the parent by the remote id",
              own_session.own_session_read(path, OWN_REMOTE)[2] == PARENT, "no parent by the remote id")
        got = send(fn, AGREED, path, target="@parent")
    check(case, asked(got), "no ask: got %r" % (got,))


def case_uuid_parent_send_asks_with_remote_env():
    parent_send_asks_with_uuid_payload(
        "@parent, payload id a UUID, CLAUDE_CODE_REMOTE_SESSION_ID set to the remote id: a reply asks",
        "parent-uuid-env", OWN_ENV)


def case_uuid_parent_send_asks_without_remote_env():
    parent_send_asks_with_uuid_payload(
        "@parent, payload id a UUID, env unset: a reply asks, resolved through the own record's ccr.id",
        "parent-uuid-noenv", None)


def case_quoted_departs_line_asks():
    case = "A: a `> Departs from:` quoted line is a pick, and asks with no Checked line"
    fn = pick_fn(case)
    if fn is None:
        return
    quoted = PICK.replace(tcj.DEPARTS_LINE, "> " + tcj.DEPARTS_LINE)
    got = send(fn, quoted, transcript("a-quoted", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_numbered_departs_line_asks():
    case = "A: a `1. Departs from:` numbered line is a pick, and asks with no Checked line"
    fn = pick_fn(case)
    if fn is None:
        return
    numbered = PICK.replace(tcj.DEPARTS_LINE, "1. " + tcj.DEPARTS_LINE)
    got = send(fn, numbered, transcript("a-numbered", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_fenced_departs_line_passes():
    case = "A: a Departs from line inside a code fence does not fire trigger A, and the send passes"
    fn = pick_fn(case)
    if fn is None:
        return
    import question_form  # the one past-rulings search (hooks/question_form.py)
    check(case + ": scope: the Departs line sits between the fence marks",
          FENCED.index("```") < FENCED.index(tcj.DEPARTS_LINE) < FENCED.rindex("```"), "the line is outside the fence")
    path = transcript("a-fenced", owner_said("Run the lint on the batch."))
    with mock.patch.object(question_form, "past_rulings", return_value=([], [])) as past:
        got = send(fn, FENCED, path)
    check(case, got is None, "asked: got %r" % (got,))
    check(case + ": past_rulings is not called", past.call_count == 0, "called %d time(s)" % past.call_count)


def case_departs_line_after_fence_asks():
    case = "control: a Departs from line after a closed code fence still asks"
    fn = pick_fn(case)
    if fn is None:
        return
    message = "```\n" + tcj.DEPARTS_LINE + "\n```\n" + PICK
    got = send(fn, message, transcript("a-after-fence", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_lone_backtick_in_text_does_not_hide_departs_line():
    case = "control: a lone backtick in text does not hide a Departs from line, which asks"
    fn = pick_fn(case)
    if fn is None:
        return
    message = "Type a lone ` in the form; it is text, not a fence.\n" + PICK
    got = send(fn, message, transcript("a-backtick", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_checked_made_up_decision_asks():
    case = "A: a Checked line naming a made-up decision asks"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, PICK + "\nChecked: " + MADE_UP_ID, transcript("a-made-up", owner_said("Run the lint.")))
    check(case, asked(got), "no ask: got %r" % (got,))


def case_checked_bare_slug_passes():
    case = "A: a Checked line naming a real decision by its bare slug passes"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, PICK + "\nChecked: " + tcj.APPS_SLUG, transcript("a-bare", owner_said("Run the lint.")))
    check(case, got is None, "asked: got %r" % (got,))


def case_no_pick_passes_without_past_rulings():
    case = "no pick and no inbound pick passes"
    fn = pick_fn(case)
    if fn is None:
        return
    import question_form  # the one past-rulings search (hooks/question_form.py)
    path = transcript("plain", [owner_said("Run the lint."), inbound(TARGET, "Status: the lane is idle.")])
    with mock.patch.object(question_form, "past_rulings", return_value=([], [])) as past:
        got = send(fn, PLAIN, path)
    check(case, got is None, "asked: got %r" % (got,))
    check("no pick and no inbound pick: past_rulings is not called", past.call_count == 0,
          "called %d time(s)" % past.call_count)


def case_inbound_pick_from_other_session_passes():
    case = "an inbound pick from another session than the target passes"
    fn = pick_fn(case)
    if fn is None:
        return
    got = send(fn, AGREED, transcript("other", inbound(OTHER, PICK)))
    check(case, got is None, "asked: got %r" % (got,))


def case_second_send_after_one_reply_passes():
    case = "a second send to the target after one reply passes"
    fn = pick_fn(case)
    if fn is None:
        return
    path = transcript("second", [inbound(TARGET, PICK), sent(TARGET, "Agreed, first reply.", "t1")])
    got = send(fn, "Second note: the stamp check stays in the lint job.", path)
    check(case, got is None, "asked: got %r" % (got,))


def case_newest_frame_decides_passes():
    # The newest inbound frame from the target is the one read: an older Departs frame does not trigger B once a
    # newer plain frame from the same target follows it.
    case = "B: an older Departs frame then a newer plain frame from the target passes"
    fn = pick_fn(case)
    if fn is None:
        return
    path = transcript("newest", [inbound(TARGET, PICK), inbound(TARGET, "Status: the lane is idle.")])
    got = send(fn, AGREED, path)
    check(case, got is None, "asked: got %r" % (got,))


def case_unreadable_transcript_on_trigger_b_passes():
    # The inbound trigger cannot be read, so it is unknown: the reply passes, with one stderr line.
    case = "B: an unreadable transcript on trigger B passes"
    fn = pick_fn(case)
    if fn is None:
        return
    folder = os.path.join(RUN_FOLDER, "pick", "unreadable")  # a folder: opening it for read fails
    os.makedirs(folder, exist_ok=True)
    check(case + ": the transcript path is not a readable file", not os.path.isfile(folder),
          "the fixture is a readable file")
    got = send(fn, AGREED, folder)
    check(case, got is None, "asked: got %r" % (got,))


def case_no_transcript_path_passes_with_stderr_line():
    case = "a send with no transcript path passes, with one stderr line"
    fn = pick_fn(case)
    if fn is None:
        return
    got, err = send_capturing_stderr(fn, PLAIN, "")
    check(case, got is None, "asked: got %r" % (got,))
    check(case + ": one stderr line, naming the rule", len(err) == 1 and err[0].startswith("pick-names-rulings: "),
          "stderr lines: %r" % (err[:3],))


def case_past_rulings_raising_after_trigger_a_asks():
    # The search that would name the ids fails after trigger A fired: the pick has no verified Checked line, so it asks.
    case = "A: past_rulings raising after trigger A fires asks"
    fn = pick_fn(case)
    if fn is None:
        return
    import question_form  # the one past-rulings search (hooks/question_form.py)
    path = transcript("a-raise", owner_said("Run the lint on the batch."))
    with mock.patch.object(question_form, "past_rulings", side_effect=RuntimeError("records unreadable")) as past:
        got = send(fn, PICK, path)
    check(case + ": past_rulings is called once, after trigger A fired", past.call_count == 1,
          "called %d time(s)" % past.call_count)
    check(case, asked(got), "no ask: got %r" % (got,))


def case_bold_departs_label_is_a_pick_asks():
    case = "A: a bold Departs from label is a pick too, and asks with no Checked line"
    fn = pick_fn(case)
    if fn is None:
        return
    bold = PICK.replace("Departs from:", "**Departs from:**")
    got = send(fn, bold, transcript("a-bold", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


# ------------------------------------------------------------------ real guard.py runs

def guard_run(name, message, path, target=TARGET, remote_env=None):
    """One guard.py run on a send_message to `target`, from this repo, with its own config folder, and the transcript
    at `path`. The payload session_id is this session's local UUID, as a real run gives it. `remote_env` is the value
    of CLAUDE_CODE_REMOTE_SESSION_ID for the run, or None for an unset env. Returns the process."""
    cfg = os.path.join(RUN_FOLDER, "guard-" + name, "config")
    os.makedirs(cfg)
    payload = {"tool_name": TOOL, "tool_input": {"session_id": target, "message": message}, "cwd": REPO,
               "session_id": OWN_UUID, "transcript_path": path}
    env = dict(os.environ)
    for key in ("CLAUDE_CODE_SESSION_ID", LANE_ENV, "CLAUDE_CODE_REMOTE", "CLAUDE_PROJECT_DIR"):
        env.pop(key, None)
    if remote_env is not None:
        env[LANE_ENV] = remote_env
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())  # the suite stands in for `claude`, as hooks/test_guard.py does
    return subprocess.run([sys.executable, os.path.join(HERE, "guard.py")], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                          cwd=REPO, timeout=120)


def decision_of(proc):
    """(decision, reason) that a guard run printed. No output is an allow, as the harness reads it."""
    out = proc.stdout.strip()
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block["permissionDecisionReason"]
    except Exception:
        return "unparsable", out[:200]


def guard_asks(case, proc):
    """The checks a guard run that asks must pass: exit 0, an ask, and a reason that names the rule."""
    check(case + ": exits 0", proc.returncode == 0, proc.stderr[-200:])
    decision, reason = decision_of(proc)
    check(case + ": permissionDecision is ask", decision == "ask", "decision %r" % (decision,))
    if decision == "ask":
        check(case + ": the reason names rule pick-names-rulings", reason.startswith("pick-names-rulings: "),
              reason[:120])


def case_guard_asks_on_inbound_pick():
    case = "guard.py on trigger B prints an ask"
    path = transcript("guard-b-ask", inbound(TARGET, PICK))
    guard_asks(case, guard_run("b-ask", AGREED, path))


def case_guard_asks_on_real_frame_inbound_pick():
    case = "guard.py on trigger B in the real frame shape prints an ask"
    frame = real_inbound(TARGET, PICK)
    check(case + ": scope: the fixture frame is the real shape from the target", real_frame_shape(frame[1], TARGET),
          "not the real shape")
    path = transcript("guard-b-real-ask", frame)
    guard_asks(case, guard_run("b-real-ask", AGREED, path))


def guard_uuid_parent_send_asks(case, name, remote_env):
    """guard.py end to end on a real-shape reply to @parent, with the payload id a UUID: prints an ask."""
    import own_session  # the one reader of a session's own get_session record (hooks/own_session.py)
    path = transcript(name, [owner_said("Run the lint on the batch."), own_session_record(PARENT),
                             real_inbound(PARENT, PICK)])
    check(case + ": scope: the own get_session record names the parent by the remote id",
          own_session.own_session_read(path, OWN_REMOTE)[2] == PARENT, "no parent by the remote id")
    guard_asks(case, guard_run(name, AGREED, path, target="@parent", remote_env=remote_env))


def case_guard_uuid_parent_send_asks_with_remote_env():
    guard_uuid_parent_send_asks(
        "guard.py: @parent, payload id a UUID, CLAUDE_CODE_REMOTE_SESSION_ID set to the remote id: prints an ask",
        "guard-parent-uuid-env", OWN_ENV)


def case_guard_uuid_parent_send_asks_without_remote_env():
    guard_uuid_parent_send_asks(
        "guard.py: @parent, payload id a UUID, env unset: prints an ask, resolved through the own record's ccr.id",
        "guard-parent-uuid-noenv", None)


def case_control_guard_allows_plain_send():
    # Green on main: a send with no pick and no inbound pick is allowed, so the guard run itself is read as working.
    case = "control: guard.py allows a plain send with no pick"
    path = transcript("guard-plain", owner_said("Run the lint."))
    proc = guard_run("plain", PLAIN, path)
    check(case + ": exits 0", proc.returncode == 0, proc.stderr[-200:])
    decision, reason = decision_of(proc)
    check(case + ": permissionDecision is allow", decision == "allow", "decision %r: %s" % (decision, reason[:120]))


CASES = (case_departs_pick_without_checked_asks, case_inbound_pick_without_checked_asks,
         case_real_frame_inbound_pick_without_checked_asks, case_real_frame_inbound_pick_with_real_checked_passes,
         case_departs_pick_with_real_checked_passes, case_inbound_pick_with_real_checked_passes,
         case_parent_send_asks_on_parent_departs_frame, case_parent_send_without_parent_id_passes_with_stderr,
         case_uuid_parent_send_asks_with_remote_env, case_uuid_parent_send_asks_without_remote_env,
         case_quoted_departs_line_asks, case_numbered_departs_line_asks,
         case_fenced_departs_line_passes, case_departs_line_after_fence_asks,
         case_lone_backtick_in_text_does_not_hide_departs_line,
         case_checked_made_up_decision_asks, case_checked_bare_slug_passes,
         case_no_pick_passes_without_past_rulings, case_inbound_pick_from_other_session_passes,
         case_second_send_after_one_reply_passes, case_newest_frame_decides_passes,
         case_unreadable_transcript_on_trigger_b_passes, case_no_transcript_path_passes_with_stderr_line,
         case_past_rulings_raising_after_trigger_a_asks, case_bold_departs_label_is_a_pick_asks,
         case_guard_asks_on_inbound_pick, case_guard_asks_on_real_frame_inbound_pick,
         case_guard_uuid_parent_send_asks_with_remote_env, case_guard_uuid_parent_send_asks_without_remote_env,
         case_control_guard_allows_plain_send)


def main():
    for case in CASES:
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
