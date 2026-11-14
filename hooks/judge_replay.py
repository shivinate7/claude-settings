#!/usr/bin/env python3
"""Replays the known allow and deny cases of each model judge, so a change to a judge's prompt, model or code is
measured against what the judge must keep doing (decision judge-replay-corpus).

    python3 hooks/judge_replay.py --changed origin/main   # the judges whose scope the diff touches
    python3 hooks/judge_replay.py --judge prose_judge     # one judge
    python3 hooks/judge_replay.py --all                   # every judge
    git diff --name-only A...B | python3 hooks/judge_replay.py --paths   # the touched names, one per line

A corpus is a JSON list in .github/judge-replay/corpus/<name>.json. Each case: {"id", "expect": "allow" | "deny", "source",
"input", "agreement"?}. `input` is the judge's own input, and one adapter per name turns it into the arguments of the
judge's real entry function. The runner holds no prompt: each case drives the entry, which builds its own prompt and
calls decision_watch.invoke_model, the one model seam, looked up at call time. The adapter reads what the entry did:
a refusal, a finding or a flag is deny, an answer with none of those is allow, and no model call or a model error is
unknown. An entry that fails open prints no verdict, so the adapter reads the model's own answer to tell unknown from
allow. The opus_scope adapter reads {"ok": false} as deny and {"ok": true} with no roles as unknown. The feedback adapter
reads any hit as deny, whichever older message the model names.

A corpus that is missing, empty, not JSON or not a list of cases exits 1, and a detail line names the judge and its file.
Only a judge that PENDING_STEPS names may have a missing or empty file.

A case runs `runs` times (--runs N, default 1). It is PASS or MISS only when one answer holds a strict majority of the
runs. Anything else is UNKNOWN, a failed call and a flip alike.

Exit: 1 on any MISS. An UNKNOWN exits 1 when env CI is set, else 0. Cost: no call in normal use; one call per case per
run for each judge asked for, and a temp folder for each decision_watch case. It starts no process but git (decision_watch
cases, and --changed), and writes nothing else.
"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for _path in (HERE, os.path.join(REPO, "lint")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import _nowindow  # noqa: E402  the one home of a no-window child start
import decision_watch  # noqa: E402  the one model seam; invoke_model is looked up here at call time
import layout  # noqa: E402  the one home of the record folders

# The waiting-page item that carries the owner's step of adding the CI secret.
PAGE_ITEM = "283"
UNKNOWN_AUTH_LINE = ("UNKNOWN: model calls cannot authenticate. Add repo secret CLAUDE_CODE_OAUTH_TOKEN "
                     "(owner, page item %s)." % PAGE_ITEM)

CORPUS_DIR = ".github/judge-replay/corpus"  # out of hooks/: the installer lands hooks/ but not its subfolders
SEAM = "hooks/decision_watch.py"
GUARD = "hooks/guard.py"  # decision_watch imports it
SHARED_NAMES = "hooks/shared_names.py"  # holds prompt text: the spawn marker and the gh logins
NOWINDOW = "hooks/_nowindow.py"  # every judge's model call starts in it (decision_watch.run calls _nowindow.run)
# guard.py loads its guard_<family>.py modules and git_reads.py, as the CI scope reads them (guard_test_* is no family
# module). A change to one is a change to guard.py, which every judge's scope holds.
GUARD_FAMILY = re.compile(r"hooks/(guard_(?!test_)[^/]*\.py|git_reads\.py)$")
RUNNER_FILES = ("hooks/judge_replay.py", "hooks/test_judge_replay.py")
CLI_DIR = ".github/judge-replay"  # the folder that pins the claude CLI the job installs
CLI_FILES = (CLI_DIR + "/package.json", CLI_DIR + "/package-lock.json")
WORKFLOW = ".github/workflows/checks.yml"
PIN_TEXT = "@anthropic-ai/claude-code@"
NO_CASES = "no cases yet"
# A judge whose corpus is a later step's to add. Its row names the step while its corpus file is absent.
PENDING_STEPS = {"call_judge.page": "pending step judge-replay-page-cases"}


def corpus_path(name):
    return "%s/%s.json" % (CORPUS_DIR, name)


# ------------------------------------------------------------------ the entries' side effects, held in one place

GUARD_NAMES = ("refuse", "record", "set_log_session", "set_override_context", "set_override_veto")


class Run:
    """What one hook entry did: its exit code, stdout, stderr and the refusals it asked guard_core for."""

    def __init__(self):
        self.code, self.out, self.err, self.refusals = 0, "", "", []


def drive(entry, payload):
    """Run a hook's main() on `payload` as stdin. guard_core.refuse and record are replaced for the run, so a refusal
    is read and never written to guard.log or lifted by an override file. A refusal exits, as the real one does."""
    import guard_core
    result = Run()
    saved = {name: getattr(guard_core, name) for name in GUARD_NAMES if hasattr(guard_core, name)}

    def refuse(tool, decision, rule, text, target="", *args, **kwargs):
        result.refusals.append((rule, text))
        raise SystemExit(0)

    for name in saved:
        setattr(guard_core, name, lambda *args, **kwargs: None)
    guard_core.refuse = refuse
    stdin, out, err = sys.stdin, io.StringIO(), io.StringIO()
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8")
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                result.code = entry() or 0
            except SystemExit as done:
                result.code = done.code or 0
    finally:
        sys.stdin = stdin
        for name, value in saved.items():
            setattr(guard_core, name, value)
    result.out, result.err = out.getvalue(), err.getvalue()
    return result


@contextlib.contextmanager
def probed():
    """decision_watch.invoke_model wrapped for one case run: each (verdict, error) it returns is recorded. The wrapper
    wraps whatever is in place when the run starts, so a test's fake sits under it. Restored after."""
    real = decision_watch.invoke_model
    calls = []

    def wrapper(*args, **kwargs):
        answer = real(*args, **kwargs)
        calls.append(answer)
        return answer

    decision_watch.invoke_model = wrapper
    try:
        yield calls
    finally:
        decision_watch.invoke_model = real


@contextlib.contextmanager
def rulings_listed(rulings):
    """question_form.past_rulings answers with `rulings` (id -> ruling text) instead of reading this repo's records, so a
    case holds its own candidates and the prompt does not move with the records."""
    import question_form
    saved = question_form.past_rulings
    lines = ["%s: %s" % (ruling_id, text) for ruling_id, text in (rulings or {}).items()]
    question_form.past_rulings = lambda text, root: (list(lines), [])
    try:
        yield
    finally:
        question_form.past_rulings = saved


def model_state(calls):
    """(state, error): "unknown" with the reason when the entry made no model call or any call failed, else "ok"."""
    if not calls:
        return "unknown", "the entry made no model call"
    for verdict, error in calls:
        if error or not isinstance(verdict, dict):
            return "unknown", " ".join(str(error or "no verdict").split())
    return "ok", ""


PLATFORM_DECISION = "deny"  # the value Claude Code's own hook output carries for a refusal


def denied(run):
    """True when the entry asked guard_core for a refusal, or printed Claude Code's refusal JSON itself."""
    if run.refusals:
        return True
    for line in run.out.splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        output = doc.get("hookSpecificOutput") if isinstance(doc, dict) else None
        if isinstance(output, dict) and output.get("permissionDecision") == PLATFORM_DECISION:
            return True
    return False


# ------------------------------------------------------------------ one adapter per judge

def spawn(case_input, calls):
    payload = {"session_id": None, "tool_name": "Agent", "tool_input": case_input}
    import call_judge
    run = drive(call_judge.main, payload)
    return "deny" if denied(run) else "allow"


def waiting_url():
    return layout.waiting_page(REPO)  # glossary-ok: lint/layout.py keeps this reader's name, and its callers use it


def question(case_input, calls):
    import call_judge
    payload = {"session_id": None, "tool_name": "AskUserQuestion", "tool_input": case_input["tool_input"], "cwd": REPO}
    with rulings_listed(case_input.get("rulings")):
        run = drive(call_judge.main, payload)
    return "deny" if denied(run) else "allow"


def page(case_input, calls):
    import call_judge
    tool_input = dict(case_input["tool_input"], url=waiting_url())
    payload = {"session_id": None, "tool_name": "ArtifactData", "tool_input": tool_input, "cwd": REPO}
    with rulings_listed(case_input.get("rulings")):
        run = drive(call_judge.main, payload)
    return "deny" if denied(run) else "allow"


def opus_ask(case_input, calls):
    import call_judge
    return "allow" if call_judge.opus_ask(case_input["text"]) else "deny"


def opus_scope(case_input, calls):
    import call_judge
    roles = call_judge.opus_scope(case_input["text"], case_input["context"])
    if roles:
        return "allow"
    # opus_scope returns None for a refusal and for a fail-open answer alike, so the model's own answer tells them apart
    answer = calls[-1][0] if calls else None
    if isinstance(roles, list) or (isinstance(answer, dict) and answer.get("ok") is False):
        return "deny"
    raise RuntimeError("call_judge.opus_scope: the answer failed open (ok with no usable roles)")


def prose(case_input, calls):
    import prose_judge
    tool_input = {"file_path": case_input["file_path"]}
    if case_input["tool"] == "Edit":
        tool_input.update(old_string=case_input["old_string"], new_string=case_input["new_string"])
    else:
        tool_input["content"] = case_input["content"]
    run = drive(prose_judge.main, {"session_id": None, "tool_name": case_input["tool"], "tool_input": tool_input})
    return "deny" if denied(run) else "allow"


def reply(case_input, calls):
    import reply_judge
    # No session id: count_this_stop writes no counter file and reads the Stop as number 1, which is judged.
    run = drive(reply_judge.main, {"session_id": None, "last_assistant_message": case_input["reply"]})
    return "deny" if "additionalContext" in run.out else "allow"


FEEDBACK_ID = "fb-9-1"
FEEDBACK_INBOX = "replay000.inbox.md"  # its session part, cut to 8 characters, is `replay00`


def feedback_stamp(index):
    return "2026-11-01 10:%02d" % index  # feedback_guard keeps the first 16 characters in a ref


def feedback_ref(index):
    return "inbox:replay00@" + feedback_stamp(index)


def feedback(case_input, calls):
    import feedback_guard
    older = case_input["older"]
    blocks = [{"stamp": feedback_stamp(i), "text": text, "items": [], "item_at": []} for i, text in enumerate(older)]
    blocks.append({"stamp": feedback_stamp(len(older)), "text": case_input["new"], "items": [], "item_at": []})
    homes = SimpleNamespace(cwd=None)  # no repo: the older messages of this inbox are the only candidates
    hits, why = feedback_guard.judge(homes, FEEDBACK_INBOX, blocks, [(FEEDBACK_ID, len(older))])
    if why is not None:  # the check was not whole: an error, an off-shape answer or a bad entry
        raise RuntimeError("feedback_guard.judge: %s" % why)
    # Any hit is a repeat: the check flags the new item whichever older message the model names.
    return "deny" if hits else "allow"


def past_ruling(case_input, calls):
    import report_guard
    with rulings_listed(case_input.get("rulings")):
        problem = report_guard.past_ruling_problem(case_input["asked"], REPO)
    return "deny" if problem else "allow"


def sendmessage(case_input, calls):
    import sendmessage_state
    judge = case_input["judge"]
    saved_state, saved_model = sendmessage_state.receiver_state, decision_watch.invoke_model
    # The entry always starts the wording judge and starts the state judge for a busy receiver. One case drives one
    # of them: the other call is answered here, and is no model call of the case.
    sendmessage_state.receiver_state = lambda name: "busy" if judge == "state" else "unseen"
    probe = saved_model

    def split(prompt, *args, **kwargs):
        if kwargs.get("model") == sendmessage_state.WORDING_MODEL and judge == "state":
            return {"ok": True}, None
        return probe(prompt, *args, **kwargs)

    decision_watch.invoke_model = split
    try:
        payload = {"session_id": None, "tool_name": "SendMessage",
                   "tool_input": {"to": case_input["to"], "message": case_input["message"]}}
        run = drive(sendmessage_state.main, payload)
    finally:
        sendmessage_state.receiver_state, decision_watch.invoke_model = saved_state, saved_model
    return "deny" if denied(run) else "allow"


def git(cwd, *args, **env):
    full = dict(os.environ, **env)
    _nowindow.run(["git", "-C", cwd, "-c", "user.name=replay", "-c", "user.email=replay@example.invalid",
                  "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, env=full)


def watch(case_input, calls):
    """decision_watch.run on a temp repo that holds `before` committed an hour ago and `after` in the working tree, with
    a transcript whose last human message is half an hour old and `assistant` texts after it."""
    now = datetime.now(timezone.utc)
    stamp = lambda moment: moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    with tempfile.TemporaryDirectory(prefix="judge_replay_") as root:
        repo = os.path.join(root, "repo")
        os.makedirs(repo)
        target = os.path.join(repo, *case_input["path"].split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(case_input["before"])
        old = stamp(now - timedelta(hours=1))
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "before", GIT_AUTHOR_DATE=old, GIT_COMMITTER_DATE=old)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(case_input["after"])
        records = [{"type": "user", "timestamp": stamp(now - timedelta(minutes=30)),
                    "message": {"role": "user", "content": case_input["human"]}}]
        for text in case_input.get("assistant", []):
            records.append({"type": "assistant", "message": {"role": "assistant",
                                                            "content": [{"type": "text", "text": text}]}})
        transcript = os.path.join(root, "transcript.jsonl")
        with open(transcript, "w", encoding="utf-8") as f:
            f.write("\n".join(json.dumps(r) for r in records) + "\n")
        os.utime(target, (time.time(), time.time()))
        hook = {"transcript_path": transcript, "cwd": repo, "session_id": ""}
        text = decision_watch.run(hook, model_call=lambda prompt: decision_watch.invoke_model(prompt))
    return "deny" if text.startswith(decision_watch.FLAG_PREFIX) else "allow"


# ------------------------------------------------------------------ the judges

CALL = "hooks/call_judge.py"
QUESTION_FORM = "hooks/question_form.py"
ROUTE_MATCH = "hooks/route_match.py"  # reply_judge's prompt carries the route rows it reads
REPORT_GUARD = "lint/report_guard.py"  # reply_judge reads its hand-off lines and cite pattern for the route block
TRANSCRIPT = "lint/_transcript.py"  # decision_watch's chat text starts after the record is_last_human picks
OK = {"ok": True}
NOT_OK = {"ok": False, "reason": "the case's judge item misses; fix the line it names."}
# A refusal of a past-ruling check must cite a listed record, and a case's list is its own, so this answer cites none the
# check can vouch for. The check reads that as a refusal it cannot verify, which is still a deny.
RULING_NOT_OK = {"ok": False, "reason": "%s/replay-case: a listed ruling already decides this." % layout.legacy("decisions")}


def entry(name, adapter, own, answers, extra=()):
    """One JUDGES row. The scope is the seam, the modules every judge reads (decision_watch imports guard; shared_names
    holds prompt text; decision_watch.run starts the call in _nowindow), the judge's own files, any module its prompt or model comes from, and its corpus. `answers` are the model answers, in the judge's own shape, that its adapter reads as allow and as deny."""
    scope = [SEAM, GUARD, SHARED_NAMES, NOWINDOW, *own, *extra, corpus_path(name)]
    return {"corpus": corpus_path(name), "scope": list(dict.fromkeys(scope)), "adapter": adapter, "answers": answers}


def verdict_pair(deny):
    return {"allow": dict(OK), "deny": deny}


JUDGES = {
    "call_judge.spawn": entry("call_judge.spawn", spawn, [CALL], verdict_pair(NOT_OK)),
    "call_judge.question": entry("call_judge.question", question, [CALL], verdict_pair(NOT_OK),
                                 [QUESTION_FORM]),
    "call_judge.page": entry("call_judge.page", page, [CALL], verdict_pair(NOT_OK), [QUESTION_FORM]),
    "call_judge.opus_ask": entry("call_judge.opus_ask", opus_ask, [CALL], verdict_pair({"ok": False})),
    "call_judge.opus_scope": entry("call_judge.opus_scope", opus_scope, [CALL],
                                   {"allow": {"ok": True, "roles": ["reviewer"]}, "deny": {"ok": False}},
                                   ["hooks/override.py"]),
    "prose_judge": entry("prose_judge", prose, ["hooks/prose_judge.py"], verdict_pair(NOT_OK)),
    "reply_judge": entry("reply_judge", reply, ["hooks/reply_judge.py"], verdict_pair(NOT_OK),
                         [QUESTION_FORM, ROUTE_MATCH, REPORT_GUARD]),
    "feedback_guard": entry("feedback_guard", feedback, ["hooks/feedback_guard.py"],
                            {"allow": {"repeats": []},
                             "deny": {"repeats": [{"id": FEEDBACK_ID, "ref": feedback_ref(0)}]}}),
    "report_guard.past_ruling": entry("report_guard.past_ruling", past_ruling, [REPORT_GUARD, CALL],
                                      verdict_pair(RULING_NOT_OK), [QUESTION_FORM]),
    "sendmessage_state": entry("sendmessage_state", sendmessage, ["hooks/sendmessage_state.py"], verdict_pair(NOT_OK)),
    "decision_watch": entry("decision_watch", watch, ["hooks/decision_watch.py", TRANSCRIPT],
                            {"allow": {"verdict": "ALLOW"},
                             "deny": {"verdict": "FLAG", "why": "a guard was removed and the chat holds no grant"}}),
}


# ------------------------------------------------------------------ touched, replay, main

def touched(paths):
    """The sorted names whose scope holds one of `paths` or whose corpus is one. The runner, its test, the CLI pin files,
    a module of the guard family and a file of the corpus folder that is no judge's corpus touch every name."""
    paths = [p.replace("\\", "/") for p in paths]
    hit = set()
    for name, row in JUDGES.items():
        if any(p in row["scope"] for p in paths):
            hit.add(name)
    known = {row["corpus"] for row in JUDGES.values()}
    if any(p in RUNNER_FILES or p in CLI_FILES or GUARD_FAMILY.match(p)
           or (p.startswith(CORPUS_DIR + "/") and p not in known) for p in paths):
        hit.update(JUDGES)
    return sorted(hit)


def well_formed(cases):
    """True for a list of cases that each hold a str id, an expect of allow or deny, and an input."""
    return isinstance(cases, list) and all(
        isinstance(c, dict) and isinstance(c.get("id"), str) and c.get("expect") in ("allow", "deny") and "input" in c
        for c in cases)


def read_corpus(name):
    """(cases, gap) of a judge's corpus file. `gap` is None when the cases are readable, else why there are none: no file,
    a file that is not a list of cases, or an empty list. The runner exits 1 on a gap unless PENDING_STEPS names the judge
    and the file is absent or empty."""
    path = JUDGES[name]["corpus"]
    try:
        with open(os.path.join(REPO, *path.split("/")), encoding="utf-8") as f:
            cases = json.load(f)
    except FileNotFoundError:
        return [], "no corpus file"
    except (ValueError, OSError):
        return [], "unreadable corpus (not JSON) in"
    if not well_formed(cases):
        return [], "malformed corpus (not a list of cases) in"
    return cases, (None if cases else "no cases in")


ABSENT = ("no corpus file", "no cases in")  # the gaps a pending judge may have; a corpus that does not parse is never one


def load_corpus(name):
    return read_corpus(name)[0]


def one_run(row, case):
    """(got, error) for one run of one case. A raised error is unknown."""
    with probed() as calls, contextlib.redirect_stderr(io.StringIO()):  # the entries' fail-open lines are not output here
        try:
            got = row["adapter"](case["input"], calls)
        except Exception as exc:  # an adapter or entry fault is a failed read, never a verdict
            return "unknown", "%s: %s" % (type(exc).__name__, " ".join(str(exc).split()))
    state, error = model_state(calls)
    return ("unknown", error) if state == "unknown" else (got, "")


def settle(answers, runs):
    """(got, verdict, agreement) from the runs' answers. A strict majority of one answer decides: PASS or MISS is
    left to the caller. Without one the case is unknown."""
    for got in ("allow", "deny"):
        count = answers.count(got)
        if count * 2 > runs:
            return got, "%d/%d" % (count, runs)
    # a model error is no answer: it never counts toward an agreement, so the numerator holds answered runs only
    return "unknown", "%d/%d" % (max(answers.count("allow"), answers.count("deny")), runs)


def replay(name, runs=1):
    """One row per case: {"id", "expect", "got", "verdict"}, with "agreement" and, for an unknown, "error". Each run
    of a case calls the judge's real entry, which calls decision_watch.invoke_model."""
    row, rows = JUDGES[name], []
    for case in load_corpus(name):
        answers, errors = [], []
        for _ in range(runs):
            got, error = one_run(row, case)
            answers.append(got)
            if error:
                errors.append(error)
        got, agreement = settle(answers, runs)
        verdict = "UNKNOWN" if got == "unknown" else ("PASS" if got == case["expect"] else "MISS")
        result = {"id": case["id"], "expect": case["expect"], "got": got, "verdict": verdict, "agreement": agreement}
        if errors:
            result["error"] = errors[0]
        rows.append(result)
    return rows


def changed_paths(base):
    """The paths the committed diff BASE...HEAD touches, or None when git cannot say."""
    spec = base if "..." in base else base + "...HEAD"
    run = _nowindow.run(["git", "-C", REPO, "diff", "--name-only", "--no-renames", spec],
                        capture_output=True, text=True)
    if run.returncode != 0:
        print("UNKNOWN: git diff %s failed: %s" % (spec, " ".join(run.stderr.split())[:200]))
        return None
    return [line for line in run.stdout.splitlines() if line.strip()]


PROBE_PROMPT = 'Reply with exactly {"ok": true}'
PROBE_TIMEOUT = 30


def probe():
    """One small call through decision_watch.invoke_model. Exit 0 when the model answers, else 1 with the UNKNOWN line
    that names the secret, whatever env CI holds: a sign-in that fails makes every case unknown."""
    verdict, error = decision_watch.invoke_model(PROBE_PROMPT, timeout=PROBE_TIMEOUT, shape={"ok": (True, False)},
                                                 effort=None)
    if error or not isinstance(verdict, dict):
        print(UNKNOWN_AUTH_LINE)
        print("model call error: %s" % " ".join(str(error or "no verdict").split()))
        return 1
    print("model sign-in ok")
    return 0


def pin_changed(base):
    """True when the committed diff BASE...HEAD moves the claude CLI pin: a change to a file of CLI_DIR (the one home of the
    pin), or an added or removed line of the workflow that holds PIN_TEXT, a pin typed into a step. None when git cannot say."""
    spec = base if "..." in base else base + "...HEAD"
    names = _nowindow.run(["git", "-C", REPO, "diff", "--name-only", "--no-renames", spec, "--", *CLI_FILES],
                          capture_output=True, text=True)
    lines = _nowindow.run(["git", "-C", REPO, "diff", "-U0", "--no-renames", spec, "--", WORKFLOW],
                          capture_output=True, text=True)
    if names.returncode != 0 or lines.returncode != 0:
        return None
    moved = [ln for ln in lines.stdout.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    return bool(names.stdout.strip()) or any(PIN_TEXT in ln for ln in moved)


def usage():
    print("usage: judge_replay.py (--changed BASE | --judge NAME | --all | --paths | --probe) [--runs N]")
    return 2


def main(argv):
    args, runs, names, mode, base = list(argv), 1, [], None, None
    while args:
        flag = args.pop(0)
        if flag == "--runs" and args and args[0].isdigit() and int(args[0]) > 0:
            runs = int(args.pop(0))
        elif flag == "--judge" and args and args[0] in JUDGES:
            mode, names = "judge", names + [args.pop(0)]
        elif flag == "--changed" and args:
            mode, base = "changed", args.pop(0)
        elif flag == "--all":
            mode = "all"
        elif flag == "--paths":
            mode = "paths"
        elif flag == "--probe":
            mode = "probe"
        else:
            return usage()
    if mode == "probe":
        return probe()
    if mode == "paths":
        for name in touched([line.strip() for line in sys.stdin if line.strip()]):
            print(name)
        return 0
    if mode == "all":
        names = sorted(JUDGES)
    elif mode == "changed":
        paths = changed_paths(base)
        pinned = pin_changed(base)
        names = sorted(JUDGES) if paths is None or pinned is not False else touched(paths)
        if not names:
            print("no judge touched")
            return 0
    elif mode is None:
        return usage()
    misses = unknowns = unreadable = 0
    asked = answered = 0
    for name in names:
        rows = replay(name, runs)
        print("%s (%d cases, %d run%s each)" % (name, len(rows), runs, "" if runs == 1 else "s"))
        gap = None if rows else read_corpus(name)[1]
        if gap in ABSENT and name in PENDING_STEPS:
            print("  %s" % NO_CASES)
            print("  %s" % PENDING_STEPS[name])
        elif not rows:
            unreadable += 1
            print("  %s: %s %s" % (name, gap, JUDGES[name]["corpus"]))
        for r in rows:
            note = "  %s" % r["error"] if r.get("error") else ""
            print("  %-7s %s expect=%s got=%s agreement=%s%s" % (r["verdict"], r["id"], r["expect"], r["got"],
                                                                 r["agreement"], note))
        misses += sum(r["verdict"] == "MISS" for r in rows)
        unknowns += sum(r["verdict"] == "UNKNOWN" for r in rows)
        asked += len(rows)
        answered += sum(r["got"] != "unknown" for r in rows)
    print("%d cases: %d PASS, %d MISS, %d UNKNOWN" % (asked, asked - misses - unknowns, misses, unknowns))
    if unknowns and not answered:
        print(UNKNOWN_AUTH_LINE)
    elif unknowns:
        print("UNKNOWN: %d cases got no answer from the model." % unknowns)
    if misses or unreadable:
        return 1
    return 1 if unknowns and os.environ.get("CI") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
