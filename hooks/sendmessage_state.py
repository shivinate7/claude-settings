#!/usr/bin/env python3
"""Before a SendMessage, two model judges read the call. Either may deny it, and an owner override
pass lifts the deny (decision owner-override-pass), as it lifts every guard.

Rule: parallelism-no-mid-task-talk (a lane messages a peer only when the branch must hear
something that changes its work). Spec: docs/decisions/agent-model-cap.md, the two SendMessage rows.

- The wording judge reads every send, by wording only (WORDING_PROMPT). It lives here, not in a
  settings.json prompt hook: a prompt hook sees only the call's JSON, so it cannot read the pass
  file, and a command hook cannot stop a sibling hook.
- The busy judge reads the receiver's state from the session board: `claude agents --json`, read by
  mods/session-board/hooks/receiver-state.mjs (lib.mjs is the one home of that read). One word:
  busy, idle, waiting or unseen. Only busy gets a model call (build_prompt). idle and waiting are not
  mid-task; unseen (main, an in-process teammate, no row, a duplicate name, node or claude missing)
  is left to the wording judge.
Both model calls go through decision_watch.invoke_model, the one model caller. The wording call runs
in a thread beside the board read, so the two do not add their times.

A deny goes through guard_core.refuse(), the one home of the pass check and the guard.log line.
Fail open. Any judge error allows, with one stderr line. Deny: one PreToolUse deny JSON, exit 0.
receiver-state.mjs is found in the pointer checkout (a copy install has no mods/ beside hooks/),
else beside this file's real path (a symlink install, a worktree). Neither found reads as unseen.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

READER_PARTS = ("mods", "session-board", "hooks", "receiver-state.mjs")
OK_SHAPE = {"ok": (True, False)}
# THE TIME BUDGET. The board read (READER_TIMEOUT, plus up to 5 s for kill_tree) then the busy call
# (MODEL_TIMEOUT) run beside the wording call (WORDING_TIMEOUT, joined 5 s later at most), so the
# longest path is 12 + 5 + 25 = 42 s plus start-up. The settings.json PreToolUse entry for this hook
# carries "timeout": 50.
READER_TIMEOUT = 12
MODEL_TIMEOUT = 25
WORDING_TIMEOUT = 30  # a prompt hook's default timeout
WORDING_MODEL = "claude-sonnet-5-5"  # at the model's default effort (docs/decisions/agent-model-cap.md)
RULE = "parallelism-no-mid-task-talk"
WORDING_PROMPT = (
    "Judge this SendMessage call: %s\nAnswer {\"ok\": true} at once for a resume, a status message, "
    "or an orchestrator instruction. Rule: parallelism-no-mid-task-talk (a lane messages a peer only "
    "when the branch must hear something that changes its work). Judge by wording only: a separate "
    "state check handles a receiver on the session board. Block only on a clear breach; when unsure "
    "answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": "
    "\"<rule id and the fix, one line>\"}."
)
MESSAGE_MAX = 4000  # the prompt rides stdin (decision_watch.invoke_model), so no argv cap; the clip bounds cost and latency only (unmeasured)


def find_reader():
    """The reader's path, or ''. The pointer checkout first (guard_pointer.pointer_checkout, the one
    Python reader of the `@<clone>/CLAUDE.md` line the installers write), then the clone this file
    really sits in. A copy install has only the first."""
    roots = []
    try:
        from guard_pointer import pointer_checkout
        roots.append(pointer_checkout())
    except Exception:
        pass
    roots.append(os.path.join(HERE, ".."))
    for root in roots:
        path = os.path.join(root, *READER_PARTS) if root else ""
        if os.path.isfile(path):
            return path
    return ""


def receiver_state(name):
    node, reader = shutil.which("node"), find_reader()
    if not node or not reader:
        return "unseen"
    # Stdout goes to a file, not a pipe: on Windows, subprocess.run reads the pipe again after the
    # kill, and a grandchild that holds the pipe then holds the hook with no bound.
    with tempfile.TemporaryFile() as out:
        proc = _nowindow.Popen([node, reader, name], stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")
        try:
            code = proc.wait(timeout=READER_TIMEOUT)
        except subprocess.TimeoutExpired:  # slow board read: unseen, the wording judge covers it
            kill_tree(proc)
            print("sendmessage state judge failed open: the board read timed out", file=sys.stderr)
            return "unseen"
        out.seek(0)
        word = out.read().decode("utf-8", "replace").strip()
    return word if code == 0 and word in ("busy", "idle", "waiting") else "unseen"


def kill_tree(proc):
    """Kill the reader and what it started. Only the process this hook started."""
    try:
        if os.name == "nt":
            _nowindow.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=5)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
        proc.wait(timeout=5)
    except Exception:
        pass


def build_prompt(to, message):
    return (
        "Judge this message from one agent to a peer. The peer is BUSY: mid-task on the session "
        "board right now.\nRule: parallelism-no-mid-task-talk (message a peer only when the branch "
        "must hear something that changes its work). Answer {\"ok\": true} when the message "
        "names a fact, a correction or a stop that changes the peer's work, or is a short status "
        "the peer needs now. Answer {\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"} "
        "for chat, a progress check, or news the peer does not need before it finishes. When unsure "
        "answer {\"ok\": true}. Reply JSON only.\n\nTo: %s\nMessage:\n%s" % (to, message[:MESSAGE_MAX])
    )


def build_wording_prompt(tool_input, message):
    if isinstance(message, str):
        shown = json.dumps({"tool_name": "SendMessage", "tool_input": dict(tool_input, message=message[:MESSAGE_MAX])},
                           ensure_ascii=False)
    else:  # a structured message: clip the whole call instead
        shown = json.dumps({"tool_name": "SendMessage", "tool_input": tool_input}, ensure_ascii=False)[:MESSAGE_MAX + 1000]
    return WORDING_PROMPT % shown


def ask(answers, key, prompt, **kwargs):
    """One judge call into answers[key]: (verdict, error). Never raises."""
    try:
        import decision_watch
        answers[key] = decision_watch.invoke_model(prompt, shape=OK_SHAPE, **kwargs)
    except Exception as exc:
        answers[key] = (None, "%s: %s" % (type(exc).__name__, exc))


def deny(payload, to, reason):
    """Deny through guard_core.refuse(), which lets an owner override pass lift it. refuse() exits."""
    reason = reason.strip()
    if reason.startswith(RULE):
        reason = reason[len(RULE):].lstrip(" :-")
    reason = reason or "the receiver must hear only what changes its work."
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_pass_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_pass_veto(lambda: False)  # a SendMessage holds no act that every pass refuses
        guard_core.refuse("SendMessage", "deny", RULE, reason, to)
    except Exception:  # no guard_core: no pass can be read, so the deny stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": RULE + ": " + reason}}))
    return 0


def main():
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") or {}
        to, message = tool_input.get("to"), tool_input.get("message")
        # A structured message or a non-string receiver still gets the wording judge; only a plain
        # message to a named receiver gets the board read and the busy judge.
        plain = isinstance(to, str) and bool(to.strip()) and isinstance(message, str)
    except Exception as exc:
        print("sendmessage state judge failed open: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()),
              file=sys.stderr)
        return 0
    answers = {}
    wording = threading.Thread(target=ask, daemon=True, args=(answers, "wording", build_wording_prompt(tool_input, message)),
                               kwargs={"model": WORDING_MODEL, "timeout": WORDING_TIMEOUT, "effort": None})
    wording.start()
    try:
        if plain and receiver_state(to) == "busy":
            ask(answers, "busy", build_prompt(to, message), timeout=MODEL_TIMEOUT)
    except Exception as exc:
        answers["busy"] = (None, "%s: %s" % (type(exc).__name__, exc))
    wording.join(WORDING_TIMEOUT + 5)
    answers.setdefault("wording", (None, "the wording call did not return"))
    reasons = []
    for key, label in (("wording", "sendmessage wording judge"), ("busy", "sendmessage state judge")):
        if key not in answers:
            continue
        verdict, error = answers[key]
        if error:
            print("%s failed open: %s" % (label, " ".join(error.split())), file=sys.stderr)
        elif verdict.get("ok") is False:
            reason = verdict.get("reason")
            reasons.append(reason if isinstance(reason, str) else "")
    if reasons:
        return deny(payload, to if isinstance(to, str) else "", next((r for r in reasons if r.strip()), ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
