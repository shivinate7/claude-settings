#!/usr/bin/env python3
"""Cases for the pick-names-rulings guard (rule `pick-names-rulings`, step pick-ack-past-ruling). A pick that
departs from main, or a reply that agrees to one, names the decisions it checked, or the guard asks. The form of
a Departs from line is decision port-keeps-behaviour; hooks/question_form.py DEPARTS_LINE is its one pattern.
Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_pick_ack.py

Interface the code must match (hooks/guard_merge.py, beside brief_hit):
- pick_ack_hit(tool, tool_input, transcript) -> (matched, reason) when the send asks, else None. `transcript` is
  the path of the JSONL transcript. The repo is the process cwd; each transcript record also names it in `cwd`.
- Trigger A: the message has a line that starts `Departs from:`. Bold and bulleted labels count too, as
  DEPARTS_LINE reads them.
- Trigger B: the newest inbound `<cross-session-message from-session="<id>">` frame from the target session_id
  carries a Departs from line, and this send is the first send to that target since that frame.
- A trigger that fires passes when the message has a `Checked: <id>[, <id>...]` line that names an id
  question_form.candidate_ids(question_form.past_rulings(...)) returns: `decisions/<slug>` or the bare slug.
- past_rulings runs only when a trigger fires.
- hooks/guard.py calls it for mcp__claude-code-remote__send_message. A refusal is decision "ask", and the printed
  reason starts with `pick-names-rulings: `.

A missing function fails each case by name (`missing function`), never by a crash.
"""
import contextlib
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
SENDER = "session_PICKSELF01"  # this session
TARGET = "session_PICKTGT01"  # the lane the send goes to
OTHER = "session_PICKOTHER01"  # another lane
PICK = ("Goal: keep the stamp check in the lint job.\n"
        "Problem (rule): the stamp runs after lint, so a red stamp hides the lint verdict.\n"
        "Based on (measured): the stamp ran 3 minutes after lint in the last 20 runs.\n" + tcj.DEPARTS_LINE)
AGREED = "Agreed. Keep the stamp check in the lint job."
PLAIN = "Status: PR #12 is merged; the lane is idle."
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
    """A peer's message as a transcript holds it: a meta user record with origin.kind peer, and the frame in its content."""
    frame = ('<cross-session-message from="uds:fixture-pipe" from-session="%s" from-name="peer-lane" '
             'from-mode="bypass">%s</cross-session-message>' % (from_session, body))
    return {"type": "user", "cwd": REPO, "isSidechain": False, "isMeta": True,
            "origin": {"kind": "peer", "from": "uds:fixture-pipe", "fromSession": from_session,
                       "fromMode": "bypass", "name": "peer-lane", "body": body},
            "message": {"role": "user", "content": "Another Claude session sent a message:\n" + frame}}


def sent(target, message, tool_id):
    """A send_message call and its result, as a transcript holds them."""
    call = {"type": "tool_use", "id": tool_id, "name": TOOL, "input": {"session_id": target, "message": message}}
    done = {"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": "sent"}]}
    return [{"type": "assistant", "cwd": REPO, "message": {"role": "assistant", "content": [call]}},
            {"type": "user", "cwd": REPO, "message": {"role": "user", "content": [done]}}]


def transcript(name, items):
    """The JSONL transcript of `items` (a record, or a list of them), in this run's folder. Returns its path."""
    folder = os.path.join(RUN_FOLDER, "pick")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            for rec in (item if isinstance(item, list) else [item]):
                f.write(json.dumps(rec) + "\n")
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
    with in_repo():
        return fn(TOOL, {"session_id": target, "message": message}, path)


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


def case_bold_departs_label_is_a_pick_asks():
    case = "A: a bold Departs from label is a pick too, and asks with no Checked line"
    fn = pick_fn(case)
    if fn is None:
        return
    bold = PICK.replace("Departs from:", "**Departs from:**")
    got = send(fn, bold, transcript("a-bold", owner_said("Run the lint on the batch.")))
    check(case, asked(got), "no ask: got %r" % (got,))


# ------------------------------------------------------------------ real guard.py runs

def guard_run(name, message, items):
    """One guard.py run on a send_message to TARGET, from this repo, with its own config folder. Returns the process."""
    cfg = os.path.join(RUN_FOLDER, "guard-" + name, "config")
    os.makedirs(cfg)
    payload = {"tool_name": TOOL, "tool_input": {"session_id": TARGET, "message": message}, "cwd": REPO,
               "session_id": SENDER, "transcript_path": transcript("guard-" + name, items)}
    env = dict(os.environ)
    for key in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_REMOTE", "CLAUDE_PROJECT_DIR"):
        env.pop(key, None)
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


def case_guard_asks_on_inbound_pick():
    case = "guard.py on trigger B prints an ask"
    proc = guard_run("b-ask", AGREED, inbound(TARGET, PICK))
    check(case + ": exits 0", proc.returncode == 0, proc.stderr[-200:])
    decision, reason = decision_of(proc)
    check(case + ": permissionDecision is ask", decision == "ask", "decision %r" % (decision,))
    if decision == "ask":
        check(case + ": the reason names rule pick-names-rulings", reason.startswith("pick-names-rulings: "),
              reason[:120])


def case_control_guard_allows_plain_send():
    # Green on main: a send with no pick and no inbound pick is allowed, so the guard run itself is read as working.
    case = "control: guard.py allows a plain send with no pick"
    proc = guard_run("plain", PLAIN, owner_said("Run the lint."))
    check(case + ": exits 0", proc.returncode == 0, proc.stderr[-200:])
    decision, reason = decision_of(proc)
    check(case + ": permissionDecision is allow", decision == "allow", "decision %r: %s" % (decision, reason[:120]))


CASES = (case_departs_pick_without_checked_asks, case_inbound_pick_without_checked_asks,
         case_departs_pick_with_real_checked_passes, case_inbound_pick_with_real_checked_passes,
         case_checked_made_up_decision_asks, case_checked_bare_slug_passes,
         case_no_pick_passes_without_past_rulings, case_inbound_pick_from_other_session_passes,
         case_second_send_after_one_reply_passes, case_bold_departs_label_is_a_pick_asks,
         case_guard_asks_on_inbound_pick, case_control_guard_allows_plain_send)


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
