#!/usr/bin/env python3
"""Before a SendMessage, a past-ruling check and two model judges read the call. Any may refuse it, and an
owner override lifts the refusal (decision owner-override), as it lifts every guard.

Rule: parallelism-no-mid-task-talk (a lane messages a peer only when the branch must hear
something that changes its work). Spec: docs/decisions/agent-model-cap.md, the two SendMessage rows.

- The past-ruling check runs first and calls no model. A message that settles a question ("settled",
  "no owner item", "already ruled", "already decided"; not after `not` or `n't`) and cites a decision gets a
  read of the `"ref":` lines under roadmap/rulings, in the repo of the payload's cwd: one `ref` listing, then
  one `grep` of the local ref `roadmap` and `origin/roadmap`, both when both exist. `origin/roadmap` is first
  fetched when its last roadmap fetch is older than roadmap_ref.MAX_AGE, bounded at roadmap_ref.FETCH_TIMEOUT
  (lint/roadmap_ref.py); a read that could not be fetched fresh says "read as of <time>" on stderr. It refuses,
  rule `past-ruling`, when a ruling's supersedes ref names a cited decision. A ref that quotes a sentence
  refuses only when the message shares two of its key words; a bare-slug or docs-path ref with no sentence
  refuses always, and prose that names a decision with no sentence after it refuses never. Why: a
  reply that settles a lane's question on a superseded decision sends the lane the wrong way (incident: a
  reply cited a decision a later ruling had replaced). Cost: two git processes, only for a settling message
  that cites a decision, plus one `git fetch` of up to FETCH_TIMEOUT seconds when the ref is stale; any other
  message starts none. A missing store allows silently; an unreadable
  store, or a payload with no cwd, allows with one stderr line.
- The wording judge reads every send, by wording only (WORDING_PROMPT). It lives here, not in a
  settings.json prompt hook: a prompt hook sees only the call's JSON, so it cannot read the override
  file, and a command hook cannot stop a sibling hook.
- The busy judge reads the receiver's state from the session board: `claude agents --json`, read by
  mods/session-board/hooks/receiver-state.mjs (lib.mjs is the one home of that read). One word:
  busy, idle, waiting or unseen. Only busy gets a model call (build_prompt). idle and waiting are not
  mid-task; unseen (main, an in-process teammate, no row, a duplicate name, node or claude missing)
  is left to the wording judge.
Both model calls go through decision_watch.invoke_model, the one model caller. The wording call runs
in a thread beside the board read, so the two do not add their times.

A refusal goes through guard_core.refuse(), the one home of the override check and the guard.log line.
Fail open. Any judge error allows, with one stderr line. A refusal: one PreToolUse deny JSON, exit 0.
receiver-state.mjs is found in the pointer checkout (a copy install has no mods/ beside hooks/),
else beside this file's real path (a symlink install, a worktree). Neither found reads as unseen.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

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
# longest path is 12 + 5 + 25 = 42 s, plus RULINGS_TIMEOUT = 5 s for the past-ruling read before them (one
# shared deadline) and up to roadmap_ref.FETCH_TIMEOUT = 2 s for its fetch of a stale ref = 49 s plus start-up. The settings.json PreToolUse entry for this hook
# carries "timeout": 50.
READER_TIMEOUT = 12
MODEL_TIMEOUT = 25
RULINGS_TIMEOUT = 5  # one deadline for the whole past-ruling read (ref list, then one grep of about 150 small files)
WORDING_TIMEOUT = 30  # a prompt hook's default timeout
WORDING_MODEL = "claude-sonnet-5-5"  # at the model's default effort (docs/decisions/agent-model-cap.md)
RULE = "parallelism-no-mid-task-talk"
# The cite names the record, not the rule: the deny prefix already carries the rule id once.
RULE_CITE = "(decision haiku-prompt-hooks, the SendMessage wording judge holds a peer message to what changes its work)"
WORDING_PROMPT = (
    "Judge this SendMessage call: %s\nAnswer {\"ok\": true} at once for a resume, a status message, "
    "or an orchestrator instruction. Rule: parallelism-no-mid-task-talk (a lane messages a peer only "
    "when the branch must hear something that changes its work). Judge by wording only: a separate "
    "state check handles a receiver on the session board. Block only on a clear breach; when unsure "
    "answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": "
    "\"<rule id and the fix, one line>\"}."
)
PAST_RULE = "past-ruling"
PAST_RULE_CITE = "(decision question-form, a settled answer must not rest on a decision a later ruling replaced)"
RULINGS_PATH = "roadmap/rulings"
STORE_REFS = ("refs/heads/roadmap", "refs/remotes/origin/roadmap")  # local first; a stale local ref must not hide origin
REF_LINE = re.compile(r"^[^:]+:" + RULINGS_PATH + r"/([^:/]+)\.json:(.*)$")  # <ref>:<path>:<line>
REF_VALUE = re.compile(r'"ref":\s*("(?:[^"\\]|\\.)*")')  # a line may hold several refs
SETTLING = re.compile(r"\bsettled\b|\bno owner item\b|\balready (?:ruled|decided)\b|\bowner already decided\b", re.I)
NEGATED = re.compile(r"(?:\bnot|n['\u2019]t)\s+(?:yet\s+)?$", re.I)  # right before a settling phrase: it settles nothing
# A cited decision: `decisions/<slug>` (so also docs/decisions/<slug>.md), or `decision(s)` and a list of slugs
# (backticks ok). Any run of separators (comma, semicolon, slash, &, parentheses, "and", "or") joins two slugs, so
# an Oxford comma (", and") keeps the list going; a sentence end or a word with no hyphen ends it. The prose form
# needs a hyphen in the slug (every record slug has one), so "decision made" is no cite. A slug is read whole.
CITE_PATH = re.compile(r"\bdecisions/([\w-]+)", re.I)
CITE_SEP = r"(?:\s*(?:[,;/&()]|\band\b|\bor\b)\s*)"
CITE_WORD = re.compile(r"\bdecisions?\b:?\s*\(?\s*((?:`?\w+(?:-\w+)+`?" + CITE_SEP + r"*)+)", re.I)
SLUG = re.compile(r"\w+(?:-\w+)+")
# A stored ref, three shapes: `docs/decisions/<slug>.md[: "<sentence>"]`, `<slug>[: <sentence>]`, or prose that cites.
REF_PATH = re.compile(r"\s*(?:docs/)?decisions/([\w-]+)(?:\.md)?\s*(?::\s*(.*))?$", re.S)
REF_SLUG = re.compile(r"\s*([\w-]+)\s*(?::\s*(.*))?$", re.S)
KEY_MIN_LETTERS, KEY_NEEDED = 5, 2  # a sentence is "shared" when the reply holds this many of its key words
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


def cites(text):
    """[(slug, end offset)] for each decision a text cites, in order of appearance."""
    found = [(m.group(1).lower(), m.end()) for m in CITE_PATH.finditer(text)]
    for m in CITE_WORD.finditer(text):
        found += [(slug.lower(), m.end()) for slug in SLUG.findall(m.group(1))]
    return sorted(found, key=lambda pair: pair[1])


def cited_decisions(text):
    """The decision slugs a text cites, in order, no repeats."""
    out = []
    for slug, _ in cites(text):
        if slug not in out:
            out.append(slug)
    return out


def settles(message):
    """True when the message holds a settling phrase that no `not` or `n't` right before it negates."""
    return any(not NEGATED.search(message[:m.start()]) for m in SETTLING.finditer(message))


def ref_decisions(ref):
    """[(slug, quoted sentence or "")] for one stored supersedes ref. Only a bare slug, `<slug>: <sentence>` or
    `docs/decisions/<slug>.md[: <sentence>]` may retire the whole decision (no key words in its sentence). Prose
    (as in `decision <slug> (owner ...): <sentence>`) takes the text after the cite, and a prose cite with no key
    words after it (as in `lint/x.py:36: '... per decision <slug>.'`) retires nothing."""
    for shape in (REF_PATH, REF_SLUG):
        match = shape.match(ref)
        if match:
            return [(match.group(1).lower(), (match.group(2) or "").strip().strip("\"'\u201c\u201d"))]
    prose = [(slug, ref[end:].strip(" :()-")) for slug, end in cites(ref)]
    return [(slug, sentence) for slug, sentence in prose if key_words(sentence, slug)]


def key_words(text, slug=""):
    """The words that make a sentence its own: lowercase, 5+ letters, no stop word (question_form.STOPWORDS), and
    none of the decision's own slug words, which every cite repeats."""
    import question_form
    own = question_form._words(slug.replace("-", " "))
    return {w for w in question_form._words(text) if len(w) >= KEY_MIN_LETTERS} - own


def read_rulings(root, notes=None):
    """({ruling id: [(slug, sentence)]}, state) from the `"ref":` lines under roadmap/rulings of the local ref
    `roadmap` and of `origin/roadmap`, both read when both exist, through ONE `git grep`. A first `git for-each-ref`
    says which exist. state is "ok", "absent" (no repo, or neither ref) or "unreadable: <why>". The file stem is
    the ruling id. Before the reads, `origin/roadmap` is fetched when stale (roadmap_ref.fresh_ref, once); the note
    "read as of ..." of a fetch that failed, or "read as of unknown: <why>" when the check cannot run, is appended to
    `notes` when it is given. One deadline (RULINGS_TIMEOUT) covers both git starts, not the fetch."""
    import question_form
    if question_form._git_root_of(root) is None:
        return {}, "absent"
    try:
        lint = os.path.join(HERE, "..", "lint")
        if lint not in sys.path:
            sys.path.append(lint)
        import roadmap_ref
        note = roadmap_ref.fresh_ref(root)
    except Exception as exc:  # a read is never silent about how fresh it is
        note = "read as of unknown: " + (" ".join(str(exc).split()) or type(exc).__name__)[:80]
    if note and notes is not None:
        notes.append(note)
    deadline = time.monotonic() + RULINGS_TIMEOUT
    env = dict(os.environ, LC_ALL="C")

    def git(*args):
        proc = _nowindow.run(["git", "-C", root, *args], stdin=subprocess.DEVNULL, capture_output=True,
                             timeout=max(0.1, deadline - time.monotonic()), env=env)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")

    # The ref list is a separate start, because git grep cannot skip a ref that does not resolve.
    code, out, err = git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin")
    if code:
        return {}, "unreadable: git for-each-ref exit %d: %s" % (code, " ".join(err.split())[:120])
    have = set(out.split())
    refs = [r for r in STORE_REFS if r in have]
    if not refs:
        return {}, "absent"
    code, out, err = git("grep", "-I", "--no-color", "-e", '"ref":', *refs, "--", RULINGS_PATH)
    # Exit 1 with no stderr is "no ref lines". Exit 1 with stderr is a blob git could not read.
    if code not in (0, 1) or err.strip():
        return {}, "unreadable: git grep exit %d: %s" % (code, " ".join(err.split())[:120])
    rulings = {}
    for line in out.splitlines():
        match = REF_LINE.match(line)
        if not match:
            return {}, "unreadable: odd git grep line"
        for value in REF_VALUE.findall(match.group(2)):
            try:
                rulings.setdefault(match.group(1), []).extend(ref_decisions(json.loads(value)))
            except ValueError:
                return {}, "unreadable: bad JSON in a ref of " + match.group(1)
    return rulings, "ok"


def past_ruling_hit(payload, message):
    """(decision slug, ruling id) of the first cited decision that a ruling supersedes, else None. A quoted
    sentence counts only when the message shares KEY_NEEDED of its key words; a whole-decision ref counts always.
    Runs a git read only for a settling message that cites a decision. Never raises: a store that cannot be read
    allows, with one stderr line."""
    if not isinstance(message, str) or not settles(message):
        return None
    cited = cited_decisions(message)
    if not cited:
        return None
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        print("sendmessage past-ruling check: the rulings store was not read (the payload has no cwd)", file=sys.stderr)
        return None
    notes = []
    try:
        rulings, state = read_rulings(cwd, notes)
        if notes:
            print("sendmessage past-ruling check: the rulings store was %s" % notes[0], file=sys.stderr)
        if state == "ok":
            for slug in cited:
                for rid, entries in sorted(rulings.items()):
                    for ref_slug, sentence in entries:
                        if ref_slug != slug:
                            continue
                        keys = key_words(sentence, slug)
                        if not keys or len(keys & key_words(message, slug)) >= min(KEY_NEEDED, len(keys)):
                            return slug, rid
    except Exception as exc:
        state = "unreadable: %s" % type(exc).__name__
    if state.startswith("unreadable"):
        print("sendmessage past-ruling check failed open: the rulings store was %s" % state, file=sys.stderr)
    return None


def refuse(payload, to, reason, rule=RULE):
    """Refuse through guard_core.refuse(), which lets an owner override lift it. refuse() exits."""
    reason = reason.strip()
    if reason.startswith(rule):
        reason = reason[len(rule):].lstrip(" :-")
    reason = reason or "the receiver must hear only what changes its work."
    cite = PAST_RULE_CITE if rule == PAST_RULE else RULE_CITE
    text = reason + " " + cite  # the one text both the refuse() path and the fallback print carry
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_override_veto(lambda: False)  # a SendMessage holds no act that no override lifts
        guard_core.refuse("SendMessage", "deny", rule, text, to)
    except Exception:  # no guard_core: no override can be read, so the refusal stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": rule + ": " + text}}))
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
    hit = past_ruling_hit(payload, message)
    if hit:
        slug, rid = hit
        return refuse(payload, to if isinstance(to, str) else "",
                      "decision %s is superseded by ruling %s. Re-check the later ruling before you settle this; "
                      "an owner override lifts this refusal." % (slug, rid), PAST_RULE)
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
        return refuse(payload, to if isinstance(to, str) else "", next((r for r in reasons if r.strip()), ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
