#!/usr/bin/env python3
"""Cases for the wave-2 handoff hooks: decisions/precompact-handoff.md, items 8 and 9.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_handoff_wave2.py

Seams. Every seam is a CLI mode that reads one JSON payload on stdin.

Part 1, hooks/precompact_handoff.py:
  --session-end  (SessionEnd; session_id, reason, cwd). Reason `clear` writes one new file that
                 holds the old session id and the project dir as values. A value is a JSON
                 string or key, or a line or word of plain text. Any other reason writes no
                 pointer. Every reason records the session's project dir, in a place the
                 fallback reads. The cases check that by behavior, not by file.
  --reorient     (SessionStart; session_id, source, cwd). Source `clear`: names the OLD
                 session's handoff path, taken from the newest pointer for cwd. With no
                 pointer, it names the newest handoff for cwd. Source `fork`: reads no pointer.
                 It names the newest handoff for cwd, by handoff file mtime. With none, it
                 prints the words "no handoff". Both sources also name the NEW session's own
                 handoff path.
                 A handoff belongs to a project dir through a record of that dir. A PreCompact,
                 a --nudge, or a SessionEnd run writes the record. Most fixtures seed a session
                 with a real PreCompact run in its dir. The quiet-session case uses --nudge and
                 SessionEnd only.
  (no flag)      PreCompact. Unchanged.
  /safe-stop     The pin. The mod runs HANDOFF_PY (mods/session-board/hooks/register.mjs) with
                 `-I -B -c`, cwd = the config dir. It reads JSON with exactly the keys handoff
                 and prompt. HANDOFF_PY is copied below, verbatim, and is not parsed.

Part 2, hooks/reread_check.py (new file):
  --post-compact (PostCompact; session_id, trigger, cwd). Sets the session's flag.
  --pre-read     (PreToolUse, tool Read; session_id, tool_name, tool_input.file_path, cwd).
                 Clears the flag when the path names this session's handoff, in any spelling:
                 full path, forward slashes (Windows only), 8.3 short name (Windows only),
                 long name, or `~/.claude/...`. It never denies the read: exit 0 and no deny or
                 block in stdout. A payload with `agent_id` (the hook fired inside an agent)
                 clears nothing: only the session's own Read counts.
  --stop         (Stop; session_id, stop_hook_active, cwd). With the flag set, stop_hook_active
                 false, and the handoff file present, prints {"decision": "block", "reason": ...},
                 and the reason names the handoff path. Otherwise exits 0 and blocks nothing.
                 Flags are per session.

Part 4, the compaction audit (hooks/reread_check.py and hooks/guard.py, rule compaction-audit,
decision precompact-handoff, item 16). After a compaction the main session must spawn one Agent whose
prompt's first non-blank line starts with `Audit:` before the guard passes its next call. Until then
the guard refuses each call the main session makes under compaction-audit, and --stop blocks once
after the handoff is read, naming the same remedy. The flag is <config dir>/state/handoff/<sid>.audit.
A spawn that a later guard rule refuses has not run, so it clears nothing. The marker is read as the
one home reads it (hooks/shared_names.py, EXPLORE_AUDIT_MARKER and BRIEF_MARKERS).
The guard is a seam too: one JSON payload on stdin, the decision on stdout. An agent's payload
(`agent_id`) is never refused and clears nothing.

Bad stdin. Every mode of both modules exits 0 on empty stdin, a JSON list, JSON null, or
text that is not JSON. reread_check.py imports precompact_handoff.py; if that import fails,
every reread_check mode still exits 0.

Config. CLAUDE_CONFIG_DIR is <scratch>/home/.claude. HOME and USERPROFILE are <scratch>/home,
so `~/.claude` names the same folder as CLAUDE_CONFIG_DIR.

Stubs. PRECOMPACT_HANDOFF_UNDER_TEST and READ_CHECK_UNDER_TEST replace the two modules. An
always-pass stub (exit 0, no output) must fail every case, the /safe-stop pin included.

The /safe-stop pin guards a signature that already works, so it passes on the unchanged hook.

Each negative case carries a positive twin on a separate session. So a pass cannot come from
a hook that does nothing. The Read spelling cases and the twin use the same live check.
"""
import ast
import collections
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_precompact_handoff import (  # noqa: E402
    HANDOFF_WITH_PREMISES, RUN_FOLDER, ids_in, put, put_bytes, transcript_line, write_transcript)

PRECOMPACT = os.environ.get("PRECOMPACT_HANDOFF_UNDER_TEST") or os.path.join(
    HERE, "precompact_handoff.py")
READ_CHECK = os.environ.get("READ_CHECK_UNDER_TEST") or os.path.join(HERE, "reread_check.py")
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
PROMPT_NAME = os.path.join("hooks", "precompact_handoff_prompt.md")

# Copied verbatim from mods/session-board/hooks/register.mjs (HANDOFF_PY, the .join('\n')).
# Keep the two in step by hand. Do not parse the .mjs.
HANDOFF_PY = "\n".join([
    'import sys, json',
    'sys.path.append(sys.argv[1])',
    'import precompact_handoff as p',
    'if sys.argv[3] != "plan": p.ensure_handoff_dir(sys.argv[2])',
    'print(json.dumps({"handoff": p.handoff_path(sys.argv[2]), "prompt": p.prompt_path()}))',
])

FAILED = []
Result = collections.namedtuple("Result", "returncode stdout stderr")


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


def tail(text, n=200):
    return (text or "")[-n:]


def json_or_none(text):
    try:
        return json.loads(text)
    except ValueError:
        return None


def last_json(text):
    lines = (text or "").strip().split("\n")
    return json_or_none(lines[-1]) if lines[0] else None


def blocks(c, proc, sid):
    """Stop blocked, and the block names this session's handoff path."""
    obj = json_or_none(proc.stdout)
    return (proc.returncode == 0 and isinstance(obj, dict) and obj.get("decision") == "block"
            and c.handoff(sid) in str(obj.get("reason", "")))


def passes(proc):
    """Exit 0 and no block."""
    obj = json_or_none(proc.stdout)
    return proc.returncode == 0 and not (isinstance(obj, dict) and obj.get("decision") == "block")


def audit_blocks(proc):
    """Stop blocked for the compaction audit: the reason names the Audit: remedy, not the re-read."""
    obj = json_or_none(proc.stdout)
    reason = str(obj.get("reason", "")) if isinstance(obj, dict) else ""
    return (proc.returncode == 0 and isinstance(obj, dict) and obj.get("decision") == "block"
            and "Audit:" in reason and "not re-read" not in reason)


def audit_then_pass(c, sid, label):
    """After a read of the handoff, the next Stop names the Audit: remedy and not the re-read. The
    session's Audit: spawn is allowed (AUDIT_SPAWN, part 4 below), and the next Stop passes."""
    stop = c.stop(sid)
    check("%s clears the re-read flag: the next Stop names the Audit: remedy, not the re-read" % label,
          audit_blocks(stop), "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
    why = allowed_why(guard_call(c, sid, "Agent", AUDIT_SPAWN))
    check("%s, then the Audit: spawn is allowed" % label, why == "", why)
    after = c.stop(sid)
    check("%s, then the Audit: spawn: the next Stop passes" % label, passes(after),
          "rc=%r out=%r" % (after.returncode, tail(after.stdout)))


def read_allowed(proc):
    """Exit 0 and no deny or block. A Read hook must never stop the read itself."""
    low = (proc.stdout or "").lower()
    return proc.returncode == 0 and "deny" not in low and "block" not in low


def strings_in(data):
    """The strings a file holds: JSON keys and values when it parses to an object or list;
    otherwise its lines and its words."""
    text = data.decode("utf-8", "replace")
    obj = json_or_none(text)
    if not isinstance(obj, (dict, list)):
        return text.splitlines() + text.split()
    out = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                out.append(k)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(obj)
    return out


def same_dir(a, b):
    """The same folder: equal after normpath, or equal after realpath. A short 8.3 name on
    Windows (SHIVAM~1) and its long name are the same folder."""
    if os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b)):
        return True
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError):
        return False


def holds_pointer(data, sid, project):
    """One value is exactly the session id, and one value is the project dir."""
    strings = [s.strip() for s in strings_in(data)]
    return any(s == sid for s in strings) and any(same_dir(s, project) for s in strings if s)


def spell(c, sid, label):
    """One spelling of the session's handoff path, or None when this platform has none."""
    if label == "full path":
        return c.handoff(sid)
    if label == "forward slashes":
        return c.handoff(sid).replace("\\", "/") if os.sep == "\\" else None
    if label == "tilde":
        return "~/.claude/handoffs/%s.md" % sid
    raise ValueError(label)


def set_age(path, age):
    """Make a file `age` seconds old."""
    t = time.time() - age
    os.utime(path, (t, t))


def spellings(path):
    """(short, long, reason) for an existing path on Windows: its 8.3 short spelling and its
    long spelling. short is None, with the reason, on a platform with no 8.3 names, or when
    the volume gives this path no short name."""
    if sys.platform != "win32":
        return None, None, "no 8.3 short names on %s" % sys.platform
    import ctypes
    kernel = ctypes.windll.kernel32

    def convert(fn, p):
        buf = ctypes.create_unicode_buffer(32768)
        return buf.value if fn(p, buf, 32768) else None

    long_name = convert(kernel.GetLongPathNameW, path)
    short_name = convert(kernel.GetShortPathNameW, long_name) if long_name else None
    if not long_name or not short_name:
        return None, None, "Windows could not convert the path"
    if short_name == long_name:
        return None, None, "the volume gives this path no 8.3 short name"
    return short_name, long_name, ""


BAD_STDIN = (("empty", ""), ("JSON list", "[]"), ("JSON null", "null"), ("not JSON", "{not json"))


class Case(object):
    """A scratch home: config dir, one project dir, and a helper to make more dirs."""

    def __init__(self, name):
        self.root = tempfile.mkdtemp(prefix="wave2_%s_" % name, dir=RUN_FOLDER)
        self.home = os.path.join(self.root, "home")
        self.cfg = os.path.join(self.home, ".claude")
        os.makedirs(self.cfg, exist_ok=True)
        self.proj = self.dir("proj")

    def dir(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def env(self):
        env = dict(os.environ)
        env["CLAUDE_CONFIG_DIR"] = self.cfg
        env["HOME"] = self.home
        env["USERPROFILE"] = self.home
        return env

    def run(self, module, flag, payload, cwd=None):
        """One hook mode, payload on stdin. A missing module is a failed run, not a crash."""
        if not os.path.isfile(module):
            return Result(127, "", "module missing: %s" % module)
        args = [sys.executable, module] + ([flag] if flag else [])
        proc = subprocess.run(args, input=json.dumps(payload), capture_output=True, text=True,
                              env=self.env(), cwd=cwd or self.proj)
        return Result(proc.returncode, proc.stdout or "", proc.stderr or "")

    def handoff(self, sid):
        return os.path.join(self.cfg, "handoffs", "%s.md" % sid)

    def pointer(self, sid):
        """The /clear pointer of a session: state/handoff/pointers/<sid>.json."""
        return os.path.join(self.cfg, "state", "handoff", "pointers", "%s.json" % sid)

    def state(self, name):
        """A file in state/handoff/, such as <sid>.dir or <sid>.reread."""
        return os.path.join(self.cfg, "state", "handoff", name)

    def snapshot(self):
        """Every file under the config dir: {absolute path: bytes}. Folders are not counted."""
        out = {}
        for dp, _, names in os.walk(self.cfg):
            for name in names:
                path = os.path.join(dp, name)
                with open(path, "rb") as f:
                    out[path] = f.read()
        return out

    def changed(self, before):
        """Files new or changed since `before`, as {path: bytes}. A deleted file maps to None."""
        now = self.snapshot()
        out = {p: d for p, d in now.items() if before.get(p) != d}
        for p in before:
            if p not in now:
                out[p] = None
        return out

    def backdate(self, changed, seconds):
        t = time.time() - seconds
        for p, data in changed.items():
            if data is not None and os.path.isfile(p):
                os.utime(p, (t, t))

    def session_end(self, sid, reason, cwd=None):
        return self.run(PRECOMPACT, "--session-end", {
            "session_id": sid, "hook_event_name": "SessionEnd", "reason": reason,
            "cwd": cwd or self.proj})

    def reorient(self, sid, source, cwd=None):
        return self.run(PRECOMPACT, "--reorient", {
            "session_id": sid, "hook_event_name": "SessionStart", "source": source,
            "cwd": cwd or self.proj})

    def pre_compact(self, sid, cwd):
        tp = os.path.join(self.root, "transcript-%s.jsonl" % sid)
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        return self.run(PRECOMPACT, "", {
            "session_id": sid, "hook_event_name": "PreCompact", "transcript_path": tp,
            "cwd": cwd})

    def link(self, sid, cwd, age):
        """A session that compacted in `cwd`, so its PreCompact state names the dir. Its
        handoff file is `age` seconds old, so the newest one is the smallest age."""
        self.pre_compact(sid, cwd)
        path = self.handoff(sid)
        put(path, "HANDOFF %s\n" % sid)
        t = time.time() - age
        os.utime(path, (t, t))

    def post_compact(self, sid):
        return self.run(READ_CHECK, "--post-compact", {
            "session_id": sid, "hook_event_name": "PostCompact", "trigger": "auto",
            "cwd": self.proj})

    def read(self, sid, file_path, extra=None):
        payload = {
            "session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "Read",
            "tool_input": {"file_path": file_path}, "cwd": self.proj}
        payload.update(extra or {})
        return self.run(READ_CHECK, "--pre-read", payload)

    def stop(self, sid, active=False):
        return self.run(READ_CHECK, "--stop", {
            "session_id": sid, "hook_event_name": "Stop", "stop_hook_active": active,
            "cwd": self.proj})

    def seed_handoff(self, sid):
        """This session's handoff file exists, so a Stop block has a path to name."""
        put(self.handoff(sid), "HANDOFF %s\n" % sid)

    def nudge(self, sid, cwd=None, size=1000):
        """A --nudge run for one session. A 1000-token first-turn line comes first, then a
        line of `size` + 1000 input tokens, so the hook reads `size` message tokens."""
        tp = os.path.join(self.root, "nudge-%s.jsonl" % sid)

        def line(n):
            usage = {"input_tokens": n, "cache_creation_input_tokens": 0,
                     "cache_read_input_tokens": 0}
            return json.dumps({"type": "assistant", "message": {
                "model": "claude-test", "content": [], "usage": usage}})
        write_transcript(tp, [line(1000), line(size + 1000)])
        return self.run(PRECOMPACT, "--nudge", {
            "session_id": sid, "hook_event_name": "Stop", "stop_hook_active": False,
            "transcript_path": tp, "cwd": cwd or self.proj})

    def run_text(self, module, flag, text):
        """One hook mode with raw text on stdin. Case.run sends JSON only, so bad stdin goes here."""
        args = [sys.executable, module] + ([flag] if flag else [])
        proc = subprocess.run(args, input=text, capture_output=True, text=True,
                              env=self.env(), cwd=self.proj)
        return Result(proc.returncode, proc.stdout or "", proc.stderr or "")

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


# --------------------------------------------------------------------------- part 1


def case_session_end_clear_writes_pointer():
    """SessionEnd with reason clear writes a pointer that holds the old session id and the
    project dir."""
    c = Case("end_clear")
    try:
        before = c.snapshot()
        proc = c.session_end("old-1", "clear")
        new = [d for d in c.changed(before).values() if d is not None]
        check("session-end clear: exits 0", proc.returncode == 0,
              "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        check("session-end clear: a file holds the old session id and the project dir",
              any(holds_pointer(d, "old-1", c.proj) for d in new),
              "changed files: %d" % len(new))
    finally:
        c.cleanup()


def case_session_end_other_reason_writes_no_pointer():
    """SessionEnd with any other reason writes no pointer, but it still records the dir. Check
    by behavior: a clear run's pointer still names its handoff, though a newer session ended
    for another reason in the same dir. Each reason first gets a positive twin, a clear run
    that writes a pointer holding the old session id and the dir."""
    for reason in ("logout", "prompt_input_exit", "other"):
        c = Case("end_" + reason)
        try:
            c.link("old-1", c.proj, age=100)
            before = c.snapshot()
            c.session_end("old-1", "clear")
            twin = [d for d in c.changed(before).values() if d is not None]
            check("session-end %s: positive twin, a clear run writes the pointer" % reason,
                  any(holds_pointer(d, "old-1", c.proj) for d in twin),
                  "changed files: %d" % len(twin))
            put(c.handoff("other-1"), "HANDOFF other-1\n")
            c.session_end("other-1", reason)
            out = c.reorient("new-1", "clear").stdout
            check("session-end %s: clear start names the pointer's handoff (old-1)" % reason,
                  c.handoff("old-1") in out, "stdout: %r" % tail(out, 300))
            check("session-end %s: a newer session that ended for this reason is not named "
                  "(other-1)" % reason, c.handoff("other-1") not in out,
                  "stdout: %r" % tail(out, 300))
        finally:
            c.cleanup()


def case_reorient_names_newest_pointer_same_dir():
    """SessionStart clear names the handoff of the NEWEST pointer for the same dir. The older
    handoff is newer by mtime, so the pointer, not the mtime, must decide. Fork reads no
    pointer: see case_fork_ignores_stale_pointer."""
    c = Case("ptr_clear")
    try:
        c.link("old-1", c.proj, age=0)
        c.link("old-2", c.proj, age=100)
        before = c.snapshot()
        c.session_end("old-1", "clear")
        c.backdate(c.changed(before), 100)
        c.session_end("old-2", "clear")
        out = c.reorient("new-1", "clear").stdout
        check("reorient clear: names the newest pointer's handoff (old-2)",
              c.handoff("old-2") in out, "stdout: %r" % tail(out, 300))
        check("reorient clear: does not name the older pointer's handoff (old-1)",
              c.handoff("old-1") not in out, "stdout: %r" % tail(out, 300))
        check("reorient clear: names the new session's own handoff path",
              c.handoff("new-1") in out, "stdout: %r" % tail(out, 300))
    finally:
        c.cleanup()


def case_reorient_ignores_pointer_for_other_dir():
    """A pointer for another project dir is ignored. This dir's own handoff is named."""
    for source in ("clear", "fork"):
        c = Case("otherdir_" + source)
        try:
            other = c.dir("other")
            c.link("a-old", c.proj, age=0)
            c.session_end("a-old", "clear", cwd=c.proj)
            c.link("b-old", other, age=50)
            out = c.reorient("new-b", source, cwd=other).stdout
            check("reorient %s, pointer for another dir: names this dir's handoff (b-old)"
                  % source, c.handoff("b-old") in out, "stdout: %r" % tail(out, 300))
            check("reorient %s, pointer for another dir: does not name a-old" % source,
                  c.handoff("a-old") not in out, "stdout: %r" % tail(out, 300))
        finally:
            c.cleanup()


def case_reorient_no_pointer_names_newest_handoff_same_dir():
    """With no pointer, SessionStart clear or fork names the newest handoff for the same dir.
    A newer handoff from another dir must not win."""
    for source in ("clear", "fork"):
        c = Case("newest_" + source)
        try:
            other = c.dir("other")
            c.link("old-1", c.proj, age=200)
            c.link("old-2", c.proj, age=100)
            c.link("b-1", other, age=0)
            out = c.reorient("new-1", source).stdout
            check("reorient %s, no pointer: names the newest handoff for this dir (old-2)"
                  % source, c.handoff("old-2") in out, "stdout: %r" % tail(out, 300))
            check("reorient %s, no pointer: does not name the older same-dir handoff (old-1)"
                  % source, c.handoff("old-1") not in out, "stdout: %r" % tail(out, 300))
            check("reorient %s, no pointer: does not name another dir's handoff (b-1)" % source,
                  c.handoff("b-1") not in out, "stdout: %r" % tail(out, 300))
        finally:
            c.cleanup()


def case_reorient_none_says_so():
    """With no handoff and no pointer anywhere, SessionStart clear or fork says so: the
    words "no handoff"."""
    for source in ("clear", "fork"):
        c = Case("none_" + source)
        try:
            proc = c.reorient("new-1", source)
            check("reorient %s, no handoff at all: exits 0 and says no handoff" % source,
                  proc.returncode == 0 and "no handoff" in proc.stdout.lower(),
                  "rc=%r stdout: %r" % (proc.returncode, tail(proc.stdout, 300)))
        finally:
            c.cleanup()


def case_cleared_reorient_lists_every_old_premise():
    """After /clear or a fork, the old handoff's premises came from another session, so the
    message lists every one of them, a ruling too. Clear goes by pointer, fork by newest."""
    for source, by_pointer in (("clear", True), ("fork", False)):
        c = Case("clr_prem_" + source)
        try:
            c.link("old-1", c.proj, age=10)
            put(c.handoff("old-1"), HANDOFF_WITH_PREMISES)
            if by_pointer:
                c.session_end("old-1", "clear")
            out = c.reorient("new-1", source).stdout
            check("reorient %s: live control, names the old handoff" % source,
                  c.handoff("old-1") in out, "stdout: %r" % tail(out, 300))
            ids = ids_in(out)
            check("reorient %s: lists every premise id of the old handoff (P1 to P5)" % source,
                  {"P1", "P2", "P3", "P4", "P5"} <= ids, "listed: %r" % sorted(ids))
        finally:
            c.cleanup()


def case_fork_ignores_stale_pointer():
    """Fork names the newest handoff for the dir and reads no pointer. Setup: a session cleared
    first, so its pointer is the only pointer. Then a parent links in the same dir, so the
    parent's handoff is the newest. The clear twin in the same setup names the pointer's
    handoff, so a stub that always names the newest file fails this case."""
    c = Case("fork_stale")
    try:
        c.link("stale-1", c.proj, age=100)
        c.session_end("stale-1", "clear")
        c.link("parent-1", c.proj, age=0)
        fork = c.reorient("fork-1", "fork").stdout
        check("fork with a stale /clear pointer: names the parent's handoff (parent-1)",
              c.handoff("parent-1") in fork, "stdout: %r" % tail(fork, 300))
        check("fork with a stale /clear pointer: does not name the pointer's handoff (stale-1)",
              c.handoff("stale-1") not in fork, "stdout: %r" % tail(fork, 300))
        clear = c.reorient("clear-1", "clear").stdout
        check("twin, clear in the same setup: names the pointer's handoff (stale-1)",
              c.handoff("stale-1") in clear, "stdout: %r" % tail(clear, 300))
    finally:
        c.cleanup()


def case_quiet_session_found_by_fallback():
    """A session that never compacted is still found by fork. Its dir is recorded when a
    --nudge run or a SessionEnd run (any reason) happens for it. Negative twin: a newer handoff
    in another dir, from a session that ran only --nudge there, is not named."""
    for label in ("nudge", "session end"):
        c = Case("quiet_" + label.replace(" ", "_"))
        try:
            put(c.handoff("quiet-1"), "HANDOFF quiet-1\n")
            set_age(c.handoff("quiet-1"), 100)
            if label == "nudge":
                ran = c.nudge("quiet-1", cwd=c.proj)
            else:
                ran = c.session_end("quiet-1", "logout", cwd=c.proj)
            check("%s run for a quiet session: exits 0" % label, ran.returncode == 0,
                  "rc=%r err=%r" % (ran.returncode, tail(ran.stderr)))
            other = c.dir("other")
            put(c.handoff("other-1"), "HANDOFF other-1\n")
            c.nudge("other-1", cwd=other)
            out = c.reorient("new-1", "fork").stdout
            check("fork after a %s run: names the quiet session's handoff (quiet-1)" % label,
                  c.handoff("quiet-1") in out, "stdout: %r" % tail(out, 300))
            check("fork after a %s run: does not name the newer handoff in another dir "
                  "(other-1)" % label, c.handoff("other-1") not in out,
                  "stdout: %r" % tail(out, 300))
        finally:
            c.cleanup()


def case_reorient_matches_either_spelling_of_proj():
    """The project dir given as its 8.3 short name or its long name names the same handoff,
    for clear (through the pointer) and for fork (through the newest handoff). Skips, with the
    reason, where this platform or volume has no 8.3 name for the dir."""
    c = Case("dot3_dir")
    try:
        short, long_name, why = spellings(c.proj)
        if short is None:
            print("SKIP: reorient by 8.3 dir spelling: %s" % why)
            return
        c.link("p-old", c.proj, age=0)
        c.session_end("p-old", "clear", cwd=c.proj)
        for source in ("clear", "fork"):
            for label, cwd in (("short", short), ("long", long_name)):
                out = c.reorient("new-%s-%s" % (source, label), source, cwd=cwd).stdout
                check("reorient %s, dir given as its %s name: names the project's handoff "
                      "(p-old)" % (source, label), c.handoff("p-old") in out,
                      "stdout: %r" % tail(out, 300))
    finally:
        c.cleanup()


def case_safe_stop_entry_pinned():
    """The /safe-stop seam: a pin on a signature that already works."""
    c = Case("safe_stop")
    try:
        hooks_dir = os.path.dirname(PRECOMPACT)
        handoffs = os.path.join(c.cfg, "handoffs")
        want_prompt = os.path.join(c.cfg, PROMPT_NAME)

        def call(mode, sid):
            return subprocess.run(
                [sys.executable, "-I", "-B", "-c", HANDOFF_PY, hooks_dir, sid, mode],
                capture_output=True, text=True, env=c.env(), cwd=c.cfg)

        proc = call("plan", "safe-1")
        obj = last_json(proc.stdout)
        check("safe-stop pin, plan: exits 0 and prints exactly the keys handoff and prompt",
              proc.returncode == 0 and isinstance(obj, dict) and set(obj) == {"handoff", "prompt"},
              "rc=%r out=%r err=%r" % (proc.returncode, tail(proc.stdout), tail(proc.stderr)))
        check("safe-stop pin, plan: the paths are the per-session handoff and the prompt file",
              isinstance(obj, dict) and obj.get("handoff") == c.handoff("safe-1")
              and obj.get("prompt") == want_prompt, "obj=%r" % (obj,))
        check("safe-stop pin, plan: makes no handoffs folder", not os.path.isdir(handoffs))

        proc = call("run", "safe-1")
        obj = last_json(proc.stdout)
        check("safe-stop pin, run: same output shape and paths",
              proc.returncode == 0 and isinstance(obj, dict)
              and set(obj) == {"handoff", "prompt"} and obj.get("handoff") == c.handoff("safe-1")
              and obj.get("prompt") == want_prompt,
              "rc=%r out=%r err=%r" % (proc.returncode, tail(proc.stdout), tail(proc.stderr)))
        check("safe-stop pin, run: makes the handoffs folder", os.path.isdir(handoffs))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 2


def live_ok():
    """A flagged session, in a case of its own, must block. A pass in a case below means
    nothing unless this holds."""
    c = Case("live")
    try:
        c.seed_handoff("live-1")
        c.post_compact("live-1")
        return blocks(c, c.stop("live-1"), "live-1")
    finally:
        c.cleanup()


def case_post_compact_sets_flag():
    """PostCompact sets the flag. The next Stop blocks once and names the handoff path."""
    c = Case("flag")
    try:
        c.seed_handoff("s-1")
        proc = c.post_compact("s-1")
        check("post-compact: exits 0", proc.returncode == 0,
              "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        stop = c.stop("s-1")
        check("post-compact sets the flag: the next Stop blocks and names the handoff",
              blocks(c, stop, "s-1"), "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
        reason = str((json_or_none(stop.stdout) or {}).get("reason", ""))
        check("post-compact: the Stop refusal cites decision precompact-handoff",
              "decision precompact-handoff" in reason, "reason=%r" % reason)
    finally:
        c.cleanup()


def case_stop_needs_handoff_file():
    """A flagged session with no handoff file: Stop does not block, since there is no path to
    name. The same session, once its handoff file exists, blocks (positive twin)."""
    c = Case("nofile")
    try:
        c.post_compact("nf-1")
        absent = c.stop("nf-1")
        check("flag set, handoff file absent: Stop does not block",
              passes(absent), "rc=%r out=%r" % (absent.returncode, tail(absent.stdout)))
        c.seed_handoff("nf-1")
        present = c.stop("nf-1")
        check("the same flagged session, handoff file present: Stop blocks (positive twin)",
              blocks(c, present, "nf-1"), "rc=%r out=%r" % (present.returncode, tail(present.stdout)))
    finally:
        c.cleanup()


def case_read_of_handoff_clears_flag():
    """A Read of this session's handoff clears the flag, in every spelling this platform has."""
    check("read clears flag: live control, a flagged session blocks", live_ok())
    for i, label in enumerate(("full path", "forward slashes", "tilde")):
        c = Case("read%d" % i)
        try:
            spelled = spell(c, "r-1", label)
            if spelled is None:
                print("SKIP: read by %s: no such spelling on this platform" % label)
                continue
            c.seed_handoff("r-1")
            c.post_compact("r-1")
            check("read by %s, live control: the flagged session blocks before the read" % label,
                  blocks(c, c.stop("r-1"), "r-1"), "")
            rd = c.read("r-1", spelled)
            check("read by %s: the read is not denied" % label, read_allowed(rd),
                  "rc=%r out=%r" % (rd.returncode, tail(rd.stdout)))
            audit_then_pass(c, "r-1", "read by %s" % label)
        finally:
            c.cleanup()


def case_read_of_other_file_keeps_flag():
    """A Read of any other file keeps the flag. Includes a prefix of the handoff path and
    another session's handoff."""
    check("read keeps flag: live control, a flagged session blocks", live_ok())
    c = Case("other")
    try:
        c.seed_handoff("o-1")
        c.post_compact("o-1")
        others = [
            os.path.join(c.proj, "README.md"),
            c.handoff("o-1") + ".bak",
            os.path.join(c.cfg, "handoffs", "other-session.md"),
        ]
        for other in others:
            rd = c.read("o-1", other)
            check("read of %s: the read is not denied" % os.path.basename(other),
                  read_allowed(rd), "rc=%r out=%r" % (rd.returncode, tail(rd.stdout)))
        stop = c.stop("o-1")
        check("reads of other files keep the flag: the next Stop blocks and names the handoff",
              blocks(c, stop, "o-1"), "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
    finally:
        c.cleanup()


def case_agent_read_keeps_flag():
    """A Read inside an agent carries agent_id. It must not clear the main session's flag:
    the agent is not the session that has to re-read its handoff. The session's own Read,
    after the agent's, still clears it (positive twin, same session)."""
    check("agent read keeps flag: live control, a flagged session blocks", live_ok())
    c = Case("subread")
    try:
        c.seed_handoff("sub-1")
        c.post_compact("sub-1")
        inside = {"agent_id": "agent-abc123", "agent_type": "question-reviewer"}
        for label in ("full path", "tilde"):
            rd = c.read("sub-1", spell(c, "sub-1", label), extra=inside)
            check("agent read by %s: the read is not denied" % label, read_allowed(rd),
                  "rc=%r out=%r" % (rd.returncode, tail(rd.stdout)))
        stop = c.stop("sub-1")
        check("agent reads of the handoff keep the flag: the next Stop blocks",
              blocks(c, stop, "sub-1"), "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
        c.read("sub-1", c.handoff("sub-1"))
        audit_then_pass(c, "sub-1", "the session's own Read after them")
    finally:
        c.cleanup()


def case_stop_hook_active_passes():
    """stop_hook_active true passes, so a block cannot loop. Its twin, the same flagged
    state without the flag, must block."""
    c = Case("active")
    try:
        c.seed_handoff("a-1")
        c.seed_handoff("a-2")
        c.post_compact("a-1")
        c.post_compact("a-2")
        twin = c.stop("a-2", active=False)
        check("stop_hook_active twin: a flagged session without it blocks",
              blocks(c, twin, "a-2"), "rc=%r out=%r" % (twin.returncode, tail(twin.stdout)))
        looped = c.stop("a-1", active=True)
        check("stop_hook_active true: passes, so the block cannot loop",
              passes(looped), "rc=%r out=%r" % (looped.returncode, tail(looped.stdout)))
    finally:
        c.cleanup()


def case_stop_no_flag_passes():
    """A session with no flag passes. Flags are per session: a flagged sibling still blocks."""
    c = Case("noflag")
    try:
        c.seed_handoff("n-2")
        c.post_compact("n-2")
        plain = c.stop("n-1")
        check("no flag: a session that never compacted passes", passes(plain),
              "rc=%r out=%r" % (plain.returncode, tail(plain.stdout)))
        sibling = c.stop("n-2")
        check("flags are per session: the flagged sibling still blocks",
              blocks(c, sibling, "n-2"), "rc=%r out=%r" % (sibling.returncode, tail(sibling.stdout)))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- the run


def case_read_by_8dot3_spelling_clears_flag():
    """A Read of this session's handoff clears the flag by its 8.3 short name and by its long
    name. Each spelling gets its own flagged session, checked live before the read. Skips,
    with the reason, where this platform or volume has no 8.3 name for the file."""
    for tag, want_short in (("short", True), ("long", False)):
        c = Case("dot3_read_" + tag)
        try:
            c.seed_handoff("d-1")
            short, long_name, why = spellings(c.handoff("d-1"))
            if short is None:
                print("SKIP: read by %s name: %s" % (tag, why))
                continue
            spelled = short if want_short else long_name
            c.post_compact("d-1")
            check("read by %s name, live control: the flagged session blocks before the read"
                  % tag, blocks(c, c.stop("d-1"), "d-1"), "")
            rd = c.read("d-1", spelled)
            check("read by %s name: the read is not denied" % tag, read_allowed(rd),
                  "rc=%r out=%r" % (rd.returncode, tail(rd.stdout)))
            audit_then_pass(c, "d-1", "read by %s name" % tag)
        finally:
            c.cleanup()


def sibling_dir(c, tag, sibling):
    """A scratch dir with a copy of reread_check.py, and a precompact_handoff.py beside it holding
    `sibling` (text). `sibling` None leaves the sibling out. The one home of these copies."""
    d = c.dir("sib_" + tag)
    shutil.copy(READ_CHECK, os.path.join(d, "reread_check.py"))
    if sibling is not None:
        put(os.path.join(d, "precompact_handoff.py"), sibling)
    return d


def real_sibling():
    """The text of the real hooks/precompact_handoff.py."""
    with open(PRECOMPACT, encoding="utf-8") as f:
        return f.read()


def case_sibling_import_failure_exits_zero():
    """reread_check.py imports its sibling precompact_handoff.py. With the sibling missing, or
    present but raising on import, each reread_check mode exits 0. Live control: a copy that
    has the real sibling still blocks. The copies sit in this case's scratch dir."""
    c = Case("import")
    try:
        probe = {"session_id": "imp-1", "hook_event_name": "Stop", "stop_hook_active": False,
                 "tool_name": "Read", "tool_input": {"file_path": c.handoff("imp-1")},
                 "cwd": c.proj}
        for tag, variant, sibling in (
                ("missing", "no sibling", None),
                ("raises", "sibling raises on import",
                 "raise ImportError('test stub: sibling import fails')\n")):
            d = sibling_dir(c, tag, sibling)
            for flag in ("--post-compact", "--pre-read", "--stop"):
                proc = c.run(os.path.join(d, "reread_check.py"), flag, probe)
                check("%s, %s: exits 0" % (variant, flag), proc.returncode == 0,
                      "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        mod = os.path.join(sibling_dir(c, "real", real_sibling()), "reread_check.py")
        c.seed_handoff("imp-1")
        c.run(mod, "--post-compact", probe)
        stop = c.run(mod, "--stop", probe)
        check("live control, copied real sibling: Stop still blocks", blocks(c, stop, "imp-1"),
              "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
    finally:
        c.cleanup()


def _live_session_end(c):
    before = c.snapshot()
    proc = c.session_end("live-1", "clear")
    new = [d for d in c.changed(before).values() if d is not None]
    return proc.returncode == 0 and any(holds_pointer(d, "live-1", c.proj) for d in new)


def _live_reorient(c):
    return "no handoff" in c.reorient("live-1", "clear").stdout.lower()


def _live_precompact(c):
    proc = c.pre_compact("live-1", c.proj)
    c.seed_handoff("live-1")
    return proc.returncode == 0 and c.handoff("live-1") in c.reorient("new-1", "fork").stdout


def _live_nudge(c):
    return blocks(c, c.nudge("live-1", size=250000), "live-1")


def _live_post_compact(c):
    c.seed_handoff("live-1")
    c.post_compact("live-1")
    return blocks(c, c.stop("live-1"), "live-1")


def _live_pre_read(c):
    c.seed_handoff("live-1")
    c.post_compact("live-1")
    if not blocks(c, c.stop("live-1"), "live-1"):
        return False
    c.read("live-1", c.handoff("live-1"))
    return audit_blocks(c.stop("live-1"))


def case_bad_stdin_and_live_control_per_mode():
    """Every mode of both modules exits 0 on bad stdin: empty, a JSON list, JSON null, or text
    that is not JSON. Each mode also has a live control in the same case: the mode must still
    do its job on a valid payload. An always-pass stub fails the controls."""
    modes = (
        (PRECOMPACT, "--session-end", _live_session_end),
        (PRECOMPACT, "--reorient", _live_reorient),
        (PRECOMPACT, "--nudge", _live_nudge),
        (PRECOMPACT, "", _live_precompact),
        (READ_CHECK, "--post-compact", _live_post_compact),
        (READ_CHECK, "--pre-read", _live_pre_read),
        (READ_CHECK, "--stop", _live_post_compact),
    )
    for module, flag, live in modes:
        mode = flag or "(no flag, PreCompact)"
        c = Case("bad_" + (flag.strip("-") or "precompact"))
        try:
            check("live control %s: the mode works on a valid payload" % mode, live(c), "")
            for label, text in BAD_STDIN:
                proc = c.run_text(module, flag, text)
                check("bad stdin (%s) to %s: exits 0" % (label, mode), proc.returncode == 0,
                      "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        finally:
            c.cleanup()



STALE_AGE = 400 * 86400  # seconds: no live session is this old

UNREADABLE_SRC = "\n".join([
    "import runpy, sys",
    "class Unreadable(object):",
    "    def read(self, *args):",
    "        raise OSError('stdin unreadable (test)')",
    "sys.stdin = Unreadable()",
    "sys.argv = sys.argv[1:]",
    "runpy.run_path(sys.argv[0], run_name='__main__')",
    "",
])


# The guard's load brake reads the free space of the home drive (hooks/guard.py _read_disk). On a nearly full drive
# it refuses every Agent call, which stops these cases before the compaction-audit step they pin. The brake has its
# own cases (tests/guard/s39497-load-brake.py), so the guard runs here with the drive read as roomy. The launcher runs
# the guard as __main__ with its own folder first on sys.path, as `python guard.py` does.
# With HOME_MARKER_ENV set, the launcher also sets the home's EXPLORE_AUDIT_MARKER (hooks/shared_names.py) to
# that value before any module imports it, so the guard and reread_check read the same mocked marker.
HOME_MARKER_ENV = "WAVE2_HOME_MARKER"   # the launcher below reads this name, spelled out
ROOMY_DISK_SRC = "\n".join([
    "import collections, os, re, runpy, shutil, sys, types",
    "Usage = collections.namedtuple('Usage', 'total used free')",
    "shutil.disk_usage = lambda path: Usage(total=100 * 2**30, used=20 * 2**30, free=80 * 2**30)",
    "sys.argv = sys.argv[1:]",
    "sys.path[0] = os.path.dirname(os.path.abspath(sys.argv[0]))",
    "marker = os.environ.get('WAVE2_HOME_MARKER')",
    "if marker is not None:",
    "    home = os.path.join(sys.path[0], 'shared_names.py')",
    "    with open(home, encoding='utf-8') as f:",
    "        text = f.read()",
    "    text = re.sub(r'^EXPLORE_AUDIT_MARKER = .*$', 'EXPLORE_AUDIT_MARKER = ' + repr(marker), text, flags=re.M)",
    "    mod = types.ModuleType('shared_names')",
    "    mod.__file__ = home",
    "    exec(compile(text, home, 'exec'), mod.__dict__)",
    "    sys.modules['shared_names'] = mod",
    "runpy.run_path(sys.argv[0], run_name='__main__')",
    "",
])


def run_unreadable(c, launcher, module, flag):
    """One hook mode whose stdin read raises OSError. Not a JSON error: a failed read."""
    proc = subprocess.run([sys.executable, launcher, module, flag], input="", capture_output=True,
                          text=True, env=c.env(), cwd=c.proj)
    return Result(proc.returncode, proc.stdout or "", proc.stderr or "")


def lock_against_delete(c, sid):
    """Make the pointer of `sid` impossible to delete in this run -> an undo function, and
    whether the lock holds. Windows: the file is read-only. POSIX: its folder is read-only. Root
    ignores mode bits, so a root run marks the file immutable (chattr +i); where that fails, the
    lock check fails the case rather than passing it."""
    ptr, pdir = c.pointer(sid), os.path.dirname(c.pointer(sid))
    if os.name == "nt":
        os.chmod(ptr, stat.S_IREAD)
        target, undo = ptr, (lambda: os.chmod(ptr, stat.S_IREAD | stat.S_IWRITE))
    elif os.geteuid() == 0:
        def chattr(flag):
            try:
                subprocess.run(["chattr", flag, ptr], capture_output=True)
            except OSError:
                pass   # no chattr: the lock check below fails the case
        chattr("+i")
        target, undo = ptr, (lambda: chattr("-i"))
    else:
        os.chmod(pdir, 0o555)
        target, undo = pdir, (lambda: os.chmod(pdir, 0o755))
    return undo, not os.access(target, os.W_OK)


def case_clear_pointer_without_handoff_names_none():
    """The newest /clear pointer names a session with no handoff. The reorient names no other
    session's handoff (old-a has one, under an older pointer), says none, and consumes the newest
    pointer. Twin: the same setup, but the newest session has a handoff, and it is named."""
    c = Case("ptr_no_handoff")
    try:
        c.link("old-a", c.proj, age=100)
        c.session_end("old-a", "clear")
        set_age(c.pointer("old-a"), 200)
        c.session_end("old-b", "clear")   # the newest pointer; old-b never had a handoff
        out = c.reorient("new-1", "clear").stdout
        check("clear, newest pointer has no handoff: says no handoff", "no handoff" in out.lower(),
              "stdout: %r" % tail(out, 300))
        check("clear, newest pointer has no handoff: names no other session's handoff (old-a)",
              c.handoff("old-a") not in out, "stdout: %r" % tail(out, 300))
        check("clear, newest pointer has no handoff: the newest pointer (old-b) is consumed",
              not os.path.exists(c.pointer("old-b")), "")
    finally:
        c.cleanup()

    t = Case("ptr_no_handoff_twin")
    try:
        t.link("old-a", t.proj, age=100)
        t.session_end("old-a", "clear")
        set_age(t.pointer("old-a"), 200)
        t.link("old-b", t.proj, age=50)
        t.session_end("old-b", "clear")
        out = t.reorient("new-1", "clear").stdout
        check("twin, newest pointer has a handoff: names it (old-b)", t.handoff("old-b") in out,
              "stdout: %r" % tail(out, 300))
    finally:
        t.cleanup()


def case_unusable_pointers_are_removed():
    """Pointers that can never be used do not pile up: a malformed pointer, and an older pointer
    whose session has no handoff. A reorient run for the dir removes them, and the newest pointer
    is consumed."""
    c = Case("junk_ptrs")
    try:
        put(c.pointer("junk-1"), "{not json")
        c.session_end("gone-1", "clear")
        set_age(c.pointer("gone-1"), 300)
        c.session_end("gone-2", "clear")
        c.reorient("new-1", "clear")
        for sid in ("junk-1", "gone-1", "gone-2"):
            check("unusable pointer %s is removed after the reorient run" % sid,
                  not os.path.exists(c.pointer(sid)), "still on disk")
    finally:
        c.cleanup()


def case_stale_records_are_swept():
    """A .dir record and a .reread flag with no live session behind them are stale: a reorient
    run removes both. A live session's fresh .dir record and fresh flag stay. The sweep point is
    SessionStart reorient, the mode that already reads these records."""
    c = Case("stale_records")
    try:
        c.link("live-1", c.proj, age=0)
        c.session_end("live-1", "logout")   # records live-1.dir, any reason
        put(c.state("live-1.reread"), "1")
        put(c.state("dead-1.dir"), c.proj)
        put(c.state("dead-1.reread"), "1")
        set_age(c.state("dead-1.dir"), STALE_AGE)
        set_age(c.state("dead-1.reread"), STALE_AGE)
        c.reorient("new-1", "clear")
        check("stale .dir record (dead-1, 400 days old, no session) is removed",
              not os.path.exists(c.state("dead-1.dir")), "still on disk")
        check("stale .reread flag (dead-1, 400 days old) is removed",
              not os.path.exists(c.state("dead-1.reread")), "still on disk")
        check("live session's .dir record stays", os.path.exists(c.state("live-1.dir")),
              "removed")
        check("live session's fresh .reread flag stays", os.path.exists(c.state("live-1.reread")),
              "removed")
    finally:
        c.cleanup()


def case_failed_pointer_delete_is_logged():
    """A pointer that cannot be deleted is logged to stderr, naming the pointer. The reorient
    still exits 0. Silence hides the stale pointer."""
    c = Case("delete_logged")
    undo = None
    try:
        c.link("old-1", c.proj, age=100)
        c.session_end("old-1", "clear")
        undo, locked = lock_against_delete(c, "old-1")
        check("failed pointer delete, precondition: the pointer cannot be deleted in this run",
              locked, "")
        proc = c.reorient("new-1", "clear")
        check("failed pointer delete: the reorient still exits 0", proc.returncode == 0,
              "rc=%r" % proc.returncode)
        check("failed pointer delete: logged to stderr, naming the pointer (old-1)",
              "old-1" in proc.stderr, "stderr: %r" % tail(proc.stderr, 300))
    finally:
        if undo is not None:
            undo()
        c.cleanup()


def case_unreadable_stdin_reread_exits_zero():
    """reread_check reads stdin in a try that catches only ValueError. A stdin whose read raises
    OSError must still exit 0 in every mode. The control proves the launcher is not what exits 0."""
    c = Case("unreadable")
    try:
        launcher = os.path.join(c.root, "unreadable_stdin.py")
        put(launcher, UNREADABLE_SRC)
        for flag in ("--post-compact", "--pre-read", "--stop"):
            proc = run_unreadable(c, launcher, READ_CHECK, flag)
            check("unreadable stdin (read raises OSError), reread_check %s: exits 0" % flag,
                  proc.returncode == 0, "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        control = run_unreadable(c, launcher, os.path.join(c.root, "no_such_module.py"), "--stop")
        check("control: a missing module under the same launcher does not exit 0",
              control.returncode != 0, "rc=%r" % control.returncode)
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 4
# The compaction audit (hooks/reread_check.py, hooks/guard.py). Each case reads the seams' output and
# files only, so a missing name in the code under test is a failed check, never a crash.

AUDIT_RULE = "compaction-audit"
HANDOFF_RULE = "handoff-unread"
SID = "5b1d7e90-0000-4000-8000-0000000c0a11"   # the main session in every part 4 case
AGENT_ID = "a7f3c9e10b2d4e58"   # an agent's id on the payload
ENV_DROP = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID",
            "CLAUDE_PROJECT_DIR", "PYTHONPATH")
BASH = {"command": "echo hi"}
AUDIT_SPAWN = {"description": "audit", "subagent_type": "Explore", "model": "sonnet",
               "prompt": "Audit: check the handoff against the repo."}
PLAIN_SPAWN = {"description": "look", "prompt": "Read the repo and list its tests."}
QUOTED_SPAWN = {"description": "look", "subagent_type": "Explore", "model": "sonnet",
                "prompt": "Read the repo.\n\nAudit: this line is quoted, not the first one."}
BLANK_SPAWN = {"description": "audit", "subagent_type": "Explore", "model": "sonnet",
               "prompt": "\n\n   Audit: check after blank lines\nmore text"}
# An Explore may run Haiku (HAIKU_ROLES in hooks/guard.py), so an Explore spawn on Haiku passes every rule.
# A general-purpose spawn on Haiku is refused by agent-model-floor, a rule that runs after compaction-audit.
HAIKU_AUDIT_SPAWN = {"description": "audit", "subagent_type": "general-purpose", "model": "haiku",
                     "prompt": "Audit: check the handoff against the repo."}


def step(name, why):
    """One step of a case: check() with the one cause on its failing line. True when the step holds,
    so a case stops at a scope that was not reached."""
    check(name, not why, why)
    return not why


def exit_why(proc):
    return "" if proc.returncode == 0 else "rc=%r err=%r" % (proc.returncode, tail(proc.stderr))


def audit_flag(c, sid):
    """The flag PostCompact writes beside the reread flag."""
    return c.state("%s.audit" % sid)


def write_call(c):
    return {"file_path": os.path.join(c.proj, "notes.md"), "content": "x"}


def guard_call(c, sid, tool, tool_input, agent_id=None, home=None, extra_env=None, src=None):
    """One PreToolUse payload through hooks/guard.py, as Claude Code sends it: (decision, reason).
    An empty stdout is an allow. `agent_id` is set on a call made from inside an agent. `home` is the
    audit marker the home holds for this call (see ROOMY_DISK_SRC); None leaves the home as it is.
    `extra_env` adds variables to the guard's environment; `src` replaces the launcher (ROOMY_DISK_SRC)."""
    body = {"hook_event_name": "PreToolUse", "session_id": sid, "tool_name": tool,
            "tool_input": tool_input, "cwd": c.proj}
    if agent_id:
        body["agent_id"] = agent_id
    env = c.env()
    for name in ENV_DROP:
        env.pop(name, None)
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    if home is not None:
        env[HOME_MARKER_ENV] = home
    env.update(extra_env or {})
    proc = subprocess.run([sys.executable, "-c", src or ROOMY_DISK_SRC, GUARD], input=json.dumps(body),
                          capture_output=True, text=True, env=env, cwd=c.proj, timeout=120)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return "exit %d" % proc.returncode, tail(proc.stderr)
    if not out:
        return "allow", ""
    try:
        block = json.loads(out)["hookSpecificOutput"]
        return block["permissionDecision"], block["permissionDecisionReason"]
    except (ValueError, KeyError, TypeError):
        return "unparsable", out[:120]


def allowed_why(got):
    """'' when the guard let the call through, with no reason printed."""
    decision, reason = got
    return "" if decision == "allow" else "%s: %s, want allowed" % (decision, reason[:80])


def refused_by(got, rule):
    """'' when the guard refused the call under `rule`: a deny whose reason opens with `<rule>:`."""
    decision, reason = got
    if decision != "deny":
        return "%s: %s, want a refusal by %s" % (decision, reason[:80], rule)
    if not reason.startswith(rule + ":"):
        return "refused by %s, want %s" % (reason.split(":", 1)[0][:40], rule)
    return ""


def names_remedy(got):
    """'' when the refusal names the Audit: marker, the remedy that clears it."""
    return "" if "Audit:" in got[1] else "the refusal does not name the Audit: remedy: %s" % got[1][:80]


def compact(c, sid, read=True):
    """A handoff on disk, then PostCompact, then (when `read`) a Read of that handoff. Returns the
    PostCompact run and the Read run, or None for a Read that was not made."""
    c.seed_handoff(sid)
    post = c.post_compact(sid)
    rd = c.read(sid, c.handoff(sid)) if read else None
    return post, rd


def case_compaction_audit_refuses_bash_and_write():
    """After compaction and a Read of the handoff, a Bash or Write call with no Audit: spawn is refused by
    compaction-audit, and the refusal names the Audit: remedy. The Read clears the reread flag only."""
    c = Case("refuse")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact exits 0", exit_why(post)):
            return
        if not step("the Read of the handoff exits 0", exit_why(rd)):
            return
        step("the Read of the handoff clears the reread flag",
             "" if not os.path.isfile(c.state("%s.reread" % SID)) else "the reread flag is still set after the Read")
        bash = guard_call(c, SID, "Bash", BASH)
        step("after the read, a Bash call is refused by compaction-audit",
             refused_by(bash, AUDIT_RULE) or names_remedy(bash))
        write = guard_call(c, SID, "Write", write_call(c))
        step("after the read, a Write call is refused by compaction-audit",
             refused_by(write, AUDIT_RULE) or names_remedy(write))
    finally:
        c.cleanup()


def case_audit_spawn_clears_flag_and_writes_pass():
    """An Audit: spawn from the main session is allowed and clears the audit flag. After it, Bash, Write
    and Stop all pass."""
    c = Case("clears")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact wrote the audit flag, so the Audit: spawn has a flag to clear",
                    "" if os.path.isfile(audit_flag(c, SID)) else "no %s.audit flag after --post-compact" % SID):
            return
        spawn = guard_call(c, SID, "Agent", AUDIT_SPAWN)
        if not step("the Audit: spawn from the main session is allowed", allowed_why(spawn)):
            return
        step("the Audit: spawn clears the audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the audit flag is still set after the Audit: spawn")
        step("after the spawn, a Bash call is allowed", allowed_why(guard_call(c, SID, "Bash", BASH)))
        step("after the spawn, a Write call is allowed", allowed_why(guard_call(c, SID, "Write", write_call(c))))
        stop = c.stop(SID)
        step("after the spawn, Stop is quiet",
             "" if passes(stop) else "Stop blocked: %r" % tail(stop.stdout))
    finally:
        c.cleanup()


def case_no_compaction_never_refused():
    """With no compaction no flag is set, and no call is refused: Bash, Write, a plain Agent spawn and an
    Audit: spawn all pass. The Audit: spawn writes no audit flag."""
    c = Case("clean")
    try:
        c.seed_handoff(SID)
        step("with no compaction, neither flag is set",
             "" if not (os.path.isfile(c.state("%s.reread" % SID)) or os.path.isfile(audit_flag(c, SID)))
             else "a flag is set with no compaction")
        step("with no compaction, a Bash call is allowed", allowed_why(guard_call(c, SID, "Bash", BASH)))
        step("with no compaction, a Write call is allowed",
             allowed_why(guard_call(c, SID, "Write", write_call(c))))
        step("with no compaction, a plain Agent spawn is allowed",
             allowed_why(guard_call(c, SID, "Agent", PLAIN_SPAWN)))
        step("with no compaction, an Audit: spawn is allowed",
             allowed_why(guard_call(c, SID, "Agent", AUDIT_SPAWN)))
        step("with no compaction, an Audit: spawn writes no audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "an audit flag appeared with no compaction")
    finally:
        c.cleanup()


def case_post_compact_writes_audit_flag():
    """PostCompact still sets the reread flag, and also writes the audit flag beside it."""
    c = Case("flag-file")
    try:
        post, _ = compact(c, SID, read=False)
        if not step("--post-compact exits 0", exit_why(post)):
            return
        step("--post-compact still sets the reread flag",
             "" if os.path.isfile(c.state("%s.reread" % SID)) else "no reread flag after --post-compact")
        step("--post-compact writes the audit flag, state/handoff/<sid>.audit",
             "" if os.path.isfile(audit_flag(c, SID)) else "no %s.audit flag after --post-compact" % SID)
    finally:
        c.cleanup()


def case_quoted_or_plain_spawn_is_refused_and_clears_nothing():
    """An Agent whose Audit: line is not its first non-blank line, or that has no Audit: line, is refused by
    compaction-audit. The refused spawns clear nothing: a Bash call is still refused after them."""
    c = Case("quoted")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact and the Read exit 0", exit_why(post) or exit_why(rd)):
            return
        quoted = guard_call(c, SID, "Agent", QUOTED_SPAWN)
        step("an Agent whose Audit: line is quoted on a later line is refused by compaction-audit",
             refused_by(quoted, AUDIT_RULE) or names_remedy(quoted))
        plain = guard_call(c, SID, "Agent", PLAIN_SPAWN)
        step("a plain Agent spawn with no Audit: line is refused by compaction-audit",
             refused_by(plain, AUDIT_RULE) or names_remedy(plain))
        step("after the refused spawns, a Bash call is still refused by compaction-audit",
             refused_by(guard_call(c, SID, "Bash", BASH), AUDIT_RULE))
    finally:
        c.cleanup()


def case_agent_payload_never_refused_or_clears():
    """A call whose payload carries agent_id is never refused by compaction-audit and clears nothing: the
    main session's Bash call is still refused after an agent's Bash call and an agent's Audit: spawn."""
    c = Case("agent")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact and the Read exit 0", exit_why(post) or exit_why(rd)):
            return
        step("the main session's Bash call is refused by compaction-audit",
             refused_by(guard_call(c, SID, "Bash", BASH), AUDIT_RULE))
        step("a Bash call whose payload carries agent_id is allowed",
             allowed_why(guard_call(c, SID, "Bash", BASH, agent_id=AGENT_ID)))
        step("an Audit: spawn whose payload carries agent_id is allowed",
             allowed_why(guard_call(c, SID, "Agent", AUDIT_SPAWN, agent_id=AGENT_ID)))
        step("the agent's Audit: spawn clears nothing: the main session's Bash call is still refused",
             refused_by(guard_call(c, SID, "Bash", BASH), AUDIT_RULE))
    finally:
        c.cleanup()


def case_unread_handoff_is_refused_first():
    """While the handoff is unread, handoff-unread refuses first, for a Bash call and for an Audit: spawn, and
    the refused spawn leaves the audit flag set. Once the handoff is read, compaction-audit refuses."""
    c = Case("unread-first")
    try:
        post, _ = compact(c, SID, read=False)
        if not step("--post-compact exits 0", exit_why(post)):
            return
        step("with the handoff unread, a Bash call is refused by handoff-unread",
             refused_by(guard_call(c, SID, "Bash", BASH), HANDOFF_RULE))
        step("with the handoff unread, an Audit: spawn is refused by handoff-unread",
             refused_by(guard_call(c, SID, "Agent", AUDIT_SPAWN), HANDOFF_RULE))
        step("the refused Audit: spawn leaves the audit flag set",
             "" if os.path.isfile(audit_flag(c, SID)) else "no %s.audit flag after --post-compact" % SID)
        rd = c.read(SID, c.handoff(SID))
        if not step("the Read of the handoff exits 0", exit_why(rd)):
            return
        step("once the handoff is read, a Bash call is refused by compaction-audit",
             refused_by(guard_call(c, SID, "Bash", BASH), AUDIT_RULE))
    finally:
        c.cleanup()


def case_stop_blocks_for_audit_after_read():
    """Stop blocks while the handoff is unread, and names the handoff. Once the handoff is read, Stop blocks
    and names the Audit: remedy. With stop_hook_active set, Stop is quiet."""
    c = Case("stop-audit")
    try:
        compact(c, SID, read=False)
        unread = c.stop(SID)
        step("with the handoff unread, Stop blocks and names the handoff path",
             "" if blocks(c, unread, SID) else "rc=%r out=%r" % (unread.returncode, tail(unread.stdout)))
        c.read(SID, c.handoff(SID))
        first = c.stop(SID)
        obj = json_or_none(first.stdout)
        reason = str(obj.get("reason", "")) if isinstance(obj, dict) else ""
        step("after the read, Stop blocks and names the Audit: remedy",
             "" if (first.returncode == 0 and isinstance(obj, dict) and obj.get("decision") == "block"
                    and "Audit:" in reason)
             else "rc=%r out=%r, want a block that names Audit:" % (first.returncode, tail(first.stdout)))
        again = c.stop(SID, active=True)
        step("Stop with stop_hook_active set is quiet",
             "" if passes(again) else "Stop blocked again: %r" % tail(again.stdout))
    finally:
        c.cleanup()


def case_stop_quiet_without_compaction():
    """With no compaction, Stop is quiet: the audit does not reach a session that never compacted."""
    c = Case("stop-clean")
    try:
        c.seed_handoff(SID)
        stop = c.stop(SID)
        step("with no compaction, Stop is quiet",
             "" if passes(stop) else "Stop blocked: %r" % tail(stop.stdout))
    finally:
        c.cleanup()


def case_audit_marker_after_blank_lines_clears():
    """The Audit: marker counts on the first non-blank line, after blank lines and spaces. That spawn clears
    the audit flag."""
    c = Case("blank-lines")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact wrote the audit flag, so the spawn has a flag to clear",
                    "" if os.path.isfile(audit_flag(c, SID)) else "no %s.audit flag after --post-compact" % SID):
            return
        spawn = guard_call(c, SID, "Agent", BLANK_SPAWN)
        step("an Audit: spawn whose marker follows blank lines is allowed", allowed_why(spawn))
        step("that spawn clears the audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the audit flag is still set after the spawn")
    finally:
        c.cleanup()


def cut_function(text, name):
    """The source `text` with its top-level `def name` removed, or None when it has none. ast finds
    the lines, so the cut follows the parser, not a text pattern."""
    lines = text.splitlines(True)
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            first = min([node.lineno] + [d.lineno for d in node.decorator_list])
            return "".join(lines[:first - 1] + lines[node.end_lineno:])
    return None


def case_refused_audit_spawn_keeps_flag():
    """An Audit: spawn that a later guard rule refuses (agent-model-floor) has not run, so it clears
    nothing: the audit flag stays, the next Bash call is still refused by compaction-audit, and Stop
    still blocks with the Audit: remedy."""
    c = Case("refused-keeps")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact and the Read exit 0", exit_why(post) or exit_why(rd)):
            return
        refused = guard_call(c, SID, "Agent", HAIKU_AUDIT_SPAWN)
        if not step("the Audit: spawn on Haiku is refused by agent-model-floor, a later rule",
                    refused_by(refused, "agent-model-floor")):
            return
        step("the refused Audit: spawn leaves the audit flag set",
             "" if os.path.isfile(audit_flag(c, SID)) else "the audit flag is gone after the refused Audit: spawn")
        step("after the refused spawn, a Bash call is still refused by compaction-audit",
             refused_by(guard_call(c, SID, "Bash", BASH), AUDIT_RULE))
        stop = c.stop(SID)
        step("after the refused spawn, Stop still blocks and names the Audit: remedy",
             "" if audit_blocks(stop) else "Stop did not block for the audit: rc=%r out=%r"
             % (stop.returncode, tail(stop.stdout)))
    finally:
        c.cleanup()


def case_refused_then_accepted_audit_spawn_clears():
    """After a refused Audit: spawn, the same spawn on Sonnet is allowed, clears the audit flag, and
    the next Bash call passes. Only the flag check is red on the current head: the refused spawn
    clears the flag, so the accepted spawn has nothing left to clear. The other checks are green."""
    c = Case("refused-then-ok")
    try:
        post, rd = compact(c, SID)
        if not step("--post-compact and the Read exit 0", exit_why(post) or exit_why(rd)):
            return
        refused = guard_call(c, SID, "Agent", HAIKU_AUDIT_SPAWN)
        if not step("the Audit: spawn on Haiku is refused by agent-model-floor, a later rule",
                    refused_by(refused, "agent-model-floor")):
            return
        step("the refused Audit: spawn leaves the audit flag set, for the accepted spawn to clear",
             "" if os.path.isfile(audit_flag(c, SID)) else "the audit flag is gone after the refused Audit: spawn")
        accepted = dict(HAIKU_AUDIT_SPAWN, model="sonnet")
        step("the same Audit: spawn on Sonnet is allowed", allowed_why(guard_call(c, SID, "Agent", accepted)))
        step("the accepted Audit: spawn clears the audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the audit flag is still set after the accepted spawn")
        step("after the accepted spawn, a Bash call passes", allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


def case_audit_marker_judged_like_the_home():
    """A brief whose first non-blank line opens `**Audit:**` carries the Audit: marker, as the one home
    reads it (hooks/shared_names.py: the first-line audit row of BRIEF_MARKERS, case-sensitive). Its
    spawn clears the audit flag. A lowercase `audit:` first line does not carry it: its spawn is refused
    by compaction-audit and clears nothing. The lowercase case is a green control."""
    bold = {"description": "audit", "subagent_type": "Explore", "model": "sonnet",
            "prompt": "**Audit:** check the handoff against the repo."}
    c = Case("bold-audit")
    try:
        compact(c, SID)
        step("a `**Audit:**` first line is the Audit: marker: its spawn is allowed",
             allowed_why(guard_call(c, SID, "Agent", bold)))
        step("a `**Audit:**` first line: its spawn clears the audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the audit flag is still set after the bold Audit: spawn")
    finally:
        c.cleanup()
    lower = dict(bold, prompt="audit: check the handoff against the repo.")
    d = Case("lower-audit")
    try:
        compact(d, SID)
        got = guard_call(d, SID, "Agent", lower)
        step("a lowercase `audit:` first line is not the marker: its spawn is refused by compaction-audit",
             refused_by(got, AUDIT_RULE) or names_remedy(got))
        step("a lowercase `audit:` spawn leaves the audit flag set",
             "" if os.path.isfile(audit_flag(d, SID)) else "the audit flag is gone after the lowercase spawn")
    finally:
        d.cleanup()


def case_reader_follows_the_home_constant():
    """audit_spawn reads the marker from hooks/shared_names.py, the one home, and keeps no copy of it.
    Scratch copies of shared_names.py and reread_check.py, with the home's constant set to `Probe:`:
    `Probe:` opens an audit brief and `Audit:` does not."""
    c = Case("home-pin")
    try:
        names = os.path.join(HERE, "shared_names.py")
        with open(names, encoding="utf-8") as f:
            home = f.read()
        line = 'EXPLORE_AUDIT_MARKER = "Audit:"'
        if not step("the home sets EXPLORE_AUDIT_MARKER to `Audit:`, so there is one line to change",
                    "" if home.count(line) == 1 else "shared_names.py has %d such lines" % home.count(line)):
            return
        d = c.dir("home_probe")
        put(os.path.join(d, "shared_names.py"), home.replace(line, 'EXPLORE_AUDIT_MARKER = "Probe:"'))
        shutil.copy(READ_CHECK, os.path.join(d, "reread_check.py"))
        shutil.copy(PRECOMPACT, os.path.join(d, "precompact_handoff.py"))
        code = ("import json, sys; import reread_check as r; "
                "print(json.dumps(r.audit_spawn(json.loads(sys.argv[1]), ('Agent', 'Task'))))")

        def judged(prompt):
            body = {"session_id": SID, "tool_name": "Agent", "tool_input": {"prompt": prompt}}
            proc = subprocess.run([sys.executable, "-c", code, json.dumps(body)], cwd=d,
                                  capture_output=True, text=True, env=c.env(), timeout=120)
            return proc.returncode, proc.stdout.strip(), proc.stderr

        rc, out, err = judged("Probe: check the handoff.")
        step("the reader follows the home: `Probe:` opens an audit brief once the home says `Probe:`",
             "" if (rc == 0 and out == "true") else "rc=%r out=%r err=%r" % (rc, out, tail(err)))
        rc, out, err = judged("Audit: check the handoff.")
        step("the reader follows the home: `Audit:` opens no audit brief once the home says `Probe:`",
             "" if (rc == 0 and out == "false") else "rc=%r out=%r err=%r" % (rc, out, tail(err)))
    finally:
        c.cleanup()


def case_stale_sibling_without_audit_flag_path_exits_zero():
    """reread_check.py reads audit_flag_path from its sibling. A stale sibling that lacks that name
    (an older copy) must not make a mode exit non-zero: each mode exits 0. Live control: the real
    sibling, copied the same way, still blocks."""
    c = Case("stale-sibling")
    try:
        stale = cut_function(real_sibling(), "audit_flag_path")
        if not step("the real sibling defines audit_flag_path, so there is a name to remove",
                    "" if stale is not None else "hooks/precompact_handoff.py defines no audit_flag_path"):
            return
        d = sibling_dir(c, "stale", stale)
        probe_import = subprocess.run(
            [sys.executable, "-c", "import precompact_handoff as p; "
             "print(hasattr(p, 'reread_flag_path'), hasattr(p, 'audit_flag_path'))"],
            cwd=d, capture_output=True, text=True, env=c.env(), timeout=120)
        if not step("the stale sibling imports, keeps reread_flag_path and lacks audit_flag_path",
                    "" if probe_import.returncode == 0 and probe_import.stdout.strip() == "True False"
                    else "rc=%r out=%r err=%r" % (probe_import.returncode, probe_import.stdout.strip(),
                                                   tail(probe_import.stderr))):
            return
        probe = {"session_id": "stale-1", "hook_event_name": "Stop", "stop_hook_active": False,
                 "tool_name": "Read", "tool_input": {"file_path": c.handoff("stale-1")}, "cwd": c.proj}
        for flag in ("--post-compact", "--pre-read", "--stop"):
            proc = c.run(os.path.join(d, "reread_check.py"), flag, probe)
            step("stale sibling, %s: exits 0" % flag, exit_why(proc))
        real = os.path.join(sibling_dir(c, "stale_real", real_sibling()), "reread_check.py")
        c.seed_handoff("stale-1")
        c.run(real, "--post-compact", probe)
        stop = c.run(real, "--stop", probe)
        step("live control, the real sibling copied the same way: Stop still blocks",
             "" if blocks(c, stop, "stale-1") else "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 4, the remedy texts
# The compaction-audit refusal (hooks/guard.py COMPACTION_AUDIT_REASON) and reread_check's Stop remedy
# (audit_reason) each name the audit marker in backticks after `first line is`. Both must name the home's
# marker (hooks/shared_names.py), so an agent that follows either text is accepted by the guard. Under the
# mocked home `Probe:` the refusal keeps the literal `Audit:`: that is the defect. `Audit:` is the unchanged
# home, the green control of each case.

PROBE = "Probe:"
UNPATCHED = "Audit:"
SPAWN_TAIL = " check the handoff against the repo."


def home_line_why():
    """'' when hooks/shared_names.py has one EXPLORE_AUDIT_MARKER line, the line the launcher rewrites."""
    with open(os.path.join(HERE, "shared_names.py"), encoding="utf-8") as f:
        lines = sum(1 for line in f if line.startswith("EXPLORE_AUDIT_MARKER = "))
    return "" if lines == 1 else "shared_names.py has %d EXPLORE_AUDIT_MARKER lines, want 1" % lines


def remedy_marker(text):
    """The marker a remedy names: the backticked text after `first line is `. "" when it names none."""
    found = re.search(r"first line is `([^`]*)`", text or "")
    return found.group(1) if found else ""


def stop_reason(c, sid, home):
    """The reason of reread_check's Stop block under the home marker `home`, or "" when Stop does not block.
    The flags are files in the config dir, so the module that set them does not matter here."""
    body = {"session_id": sid, "hook_event_name": "Stop", "stop_hook_active": False, "cwd": c.proj}
    env = c.env()
    env[HOME_MARKER_ENV] = home
    proc = subprocess.run([sys.executable, "-c", ROOMY_DISK_SRC, READ_CHECK, "--stop"],
                          input=json.dumps(body), capture_output=True, text=True, env=env,
                          cwd=c.proj, timeout=120)
    obj = json_or_none(proc.stdout)
    if proc.returncode == 0 and isinstance(obj, dict) and obj.get("decision") == "block":
        return str(obj.get("reason", ""))
    return ""


def names_home_marker(home):
    """The Stop remedy and the compaction-audit refusal each name the home's marker `home`. Scope first: the
    refusal is compaction-audit's. Then the subject, the marker each remedy names. Under the mocked `Probe:`
    home the refusal names `Audit:`: that step is the red."""
    c = Case("names-home")
    try:
        if not step("the home holds one EXPLORE_AUDIT_MARKER line, so the mock reaches it", home_line_why()):
            return
        post, rd = compact(c, SID)
        if not step("--post-compact and the Read exit 0", exit_why(post) or exit_why(rd)):
            return
        stop = remedy_marker(stop_reason(c, SID, home))
        refusal = guard_call(c, SID, "Bash", BASH, home=home)
        if not step("after the read, a Bash call is refused by compaction-audit", refused_by(refusal, AUDIT_RULE)):
            return
        step("reread_check's Stop remedy names the home marker `%s`" % home,
             "" if stop == home else "the Stop remedy names `%s`" % (stop or "no marker"))
        named = remedy_marker(refusal[1])
        step("the compaction-audit refusal names the home marker `%s`" % home,
             "" if named == home else "the refusal names `%s`" % (named or "no marker"))
    finally:
        c.cleanup()


def spawn_from_remedy(home, source):
    """A spawn whose brief opens with the marker one remedy names, and whose other fields are AUDIT_SPAWN's.
    `source` is "stop" (reread_check's Stop remedy) or "refusal" (the compaction-audit refusal). The spawn
    must pass the guard and clear the owed audit flag, as the remedy promises."""
    c = Case("spawn-%s" % source)
    try:
        if not step("the home holds one EXPLORE_AUDIT_MARKER line, so the mock reaches it", home_line_why()):
            return
        post, rd = compact(c, SID)
        if not step("--post-compact and the Read exit 0", exit_why(post) or exit_why(rd)):
            return
        if source == "stop":
            text = stop_reason(c, SID, home)
        else:
            refusal = guard_call(c, SID, "Bash", BASH, home=home)
            if not step("after the read, a Bash call is refused by compaction-audit",
                        refused_by(refusal, AUDIT_RULE)):
                return
            text = refusal[1]
        marker = remedy_marker(text)
        if not step("the %s remedy names a marker" % source, "" if marker else "the remedy names no marker"):
            return
        got = guard_call(c, SID, "Agent", dict(AUDIT_SPAWN, prompt=marker + SPAWN_TAIL), home=home)
        if not step("a spawn built word for word from the %s remedy is allowed" % source, allowed_why(got)):
            return
        step("that spawn clears the audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the audit flag is still set after the spawn")
    finally:
        c.cleanup()


def case_remedies_name_probe_home():
    """Red on the old code: with the home marker `Probe:`, the compaction-audit refusal still names `Audit:`
    while the Stop remedy names `Probe:`."""
    names_home_marker(PROBE)


def case_remedies_name_unpatched_home():
    """Green control: the unchanged home (`Audit:`) through the same launcher. Both remedies name it."""
    names_home_marker(UNPATCHED)


def case_stop_remedy_spawn_clears_probe_home():
    """Green: a spawn built from reread_check's Stop remedy passes the guard under the `Probe:` home. This
    shows the guard's audit_spawn reads the mocked marker, the scope for the refusal case below."""
    spawn_from_remedy(PROBE, "stop")


def case_refusal_remedy_spawn_clears_probe_home():
    """Red on the old code: a spawn built from the compaction-audit refusal's remedy, under the `Probe:` home,
    is refused by compaction-audit instead of passing the guard."""
    spawn_from_remedy(PROBE, "refusal")


def case_refusal_remedy_spawn_clears_unpatched_home():
    """Green control: the same spawn, built from the refusal's remedy, under the unchanged `Audit:` home."""
    spawn_from_remedy(UNPATCHED, "refusal")


def case_stop_remedy_spawn_clears_unpatched_home():
    """Green control: the same spawn, built from the Stop remedy, under the unchanged `Audit:` home."""
    spawn_from_remedy(UNPATCHED, "stop")


# --------------------------------------------------------------------------- part 5
# Owed state is per session: PostCompact writes <session_id>.reread and <session_id>.audit under state/handoff/.
# An agent shares its parent's session_id and carries agent_id, so an agent's compaction must not owe its
# parent anything. Each case builds its own config dir (Case) and reads the guard's answer on the calls it names.

OTHER_SID = "5b1d7e90-0000-4000-8000-0000000c0b11"   # session B, a second session in the same folder; SID is session A
OWED_RULES = (HANDOFF_RULE, AUDIT_RULE)


def owed_flags(c, sid):
    """The owed-state flag files that exist for one session, by name."""
    return [name for name in ("%s.reread" % sid, "%s.audit" % sid) if os.path.isfile(c.state(name))]


def owed_refusal(got):
    """The owed-state rule that refused a call, or '' when neither of them refused it."""
    decision, reason = got
    if decision != "deny":
        return ""
    return next((rule for rule in OWED_RULES if reason.startswith(rule + ":")), "")


def no_owed_flag(c, sid):
    """'' when the session has no owed flag, else the flag names that are set."""
    flags = owed_flags(c, sid)
    return "" if not flags else "session %s has owed flags: %s" % (sid, ", ".join(flags))


def owes_read_and_audit(c, sid, other, who, other_who):
    """Session `sid` (named `who` in messages) compacts. Its next Bash call is refused by handoff-unread, and after
    its Read of the handoff by compaction-audit. Session `other` (`other_who`) did not compact, so its Bash call is
    allowed."""
    c.seed_handoff(sid)
    post = c.post_compact(sid)
    if not step("PostCompact for %s exits 0" % who, exit_why(post)):
        return
    step("%s's compaction sets its own owed flags" % who,
         "" if len(owed_flags(c, sid)) == 2 else "owed flags for %s: %s" % (who, owed_flags(c, sid)))
    step("%s's Bash call is allowed: %s's compaction does not reach it" % (other_who, who),
         allowed_why(guard_call(c, other, "Bash", BASH)))
    step("%s's Bash call is refused by handoff-unread before it reads its handoff" % who,
         refused_by(guard_call(c, sid, "Bash", BASH), HANDOFF_RULE))
    rd = c.read(sid, c.handoff(sid))
    if not step("the Read of %s's handoff exits 0" % who, exit_why(rd)):
        return
    step("%s's Bash call is refused by compaction-audit after its Read" % who,
         refused_by(guard_call(c, sid, "Bash", BASH), AUDIT_RULE))


def case_other_session_compaction_owes_nothing():
    """Session B compacts in the same project folder and session A does not. B's PostCompact sets B's own flags
    (the scope, so the case cannot pass by doing nothing). A has no owed flag, and A's Bash call is allowed."""
    c = Case("other-sid")
    try:
        c.seed_handoff(SID)
        c.seed_handoff(OTHER_SID)
        post = c.post_compact(OTHER_SID)
        if not step("session B's PostCompact exits 0", exit_why(post)):
            return
        step("session B's own Bash call is refused by handoff-unread, so its compaction took hold",
             refused_by(guard_call(c, OTHER_SID, "Bash", BASH), HANDOFF_RULE))
        step("session A has no owed flag after session B compacted", no_owed_flag(c, SID))
        step("session A's Bash call is allowed after session B compacted",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


def case_compacting_session_still_owes_read_and_audit():
    """Session B's own compaction still makes B owe its read and its audit, and session A stays free. Keying the
    flags by session must not weaken the session that compacted."""
    c = Case("own-b")
    try:
        owes_read_and_audit(c, OTHER_SID, SID, "session B", "session A")
    finally:
        c.cleanup()


def case_own_compaction_owes_read_and_audit():
    """Session A's own compaction makes A owe its read and its audit, and session B stays free."""
    c = Case("own-a")
    try:
        owes_read_and_audit(c, SID, OTHER_SID, "session A", "session B")
    finally:
        c.cleanup()


def case_stop_checkpoint_owes_nothing():
    """The Stop-hook checkpoint at a large context (about 358k tokens, decision precompact-handoff) writes its
    checkpoint state and no owed flag, so session A's Bash call is allowed."""
    c = Case("checkpoint")
    try:
        c.seed_handoff(SID)
        nudge = c.nudge(SID, size=358000)
        if not step("the Stop-hook checkpoint exits 0", exit_why(nudge)):
            return
        step("the Stop-hook checkpoint sets no owed flag for session A", no_owed_flag(c, SID))
        step("session A's Bash call is allowed after the Stop-hook checkpoint",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


def case_main_transcript_compaction_owes_flags():
    """Control for the agent cases: a PostCompact whose transcript_path is the main session's own transcript
    sets both owed flags, and session A's Bash call is refused by handoff-unread."""
    c = Case("main-transcript")
    try:
        c.seed_handoff(SID)
        tp = os.path.join(c.cfg, "projects", "proj", "%s.jsonl" % SID)
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        post = c.run(READ_CHECK, "--post-compact", {
            "session_id": SID, "hook_event_name": "PostCompact", "trigger": "auto",
            "cwd": c.proj, "transcript_path": tp})
        if not step("PostCompact with the main transcript exits 0", exit_why(post)):
            return
        step("a PostCompact with the main transcript sets both owed flags",
             "" if len(owed_flags(c, SID)) == 2 else "owed flags for A: %s" % owed_flags(c, SID))
        step("session A's Bash call is refused by handoff-unread after its own compaction",
             refused_by(guard_call(c, SID, "Bash", BASH), HANDOFF_RULE))
    finally:
        c.cleanup()


def case_agent_handoff_write_keeps_owed_read():
    """Session A owes its read after its own compaction. An agent of A (agent_id set) writes A's handoff file.
    The write is not refused by an owed-state rule and leaves A's owed flags as they were, so A's Bash call is
    still refused by handoff-unread."""
    c = Case("agent-write")
    try:
        c.seed_handoff(SID)
        post = c.post_compact(SID)
        if not step("PostCompact for session A exits 0", exit_why(post)):
            return
        before = owed_flags(c, SID)
        if not step("session A owes its read before the agent writes",
                    "" if "%s.reread" % SID in before else "no reread flag before the write"):
            return
        write = guard_call(c, SID, "Write",
                           {"file_path": c.handoff(SID), "content": "HANDOFF rewritten by an agent\n"},
                           agent_id=AGENT_ID)
        step("the agent's Write is not refused by an owed-state rule",
             "" if not owed_refusal(write) else "the agent's Write was refused by %s" % owed_refusal(write))
        put(c.handoff(SID), "HANDOFF rewritten by an agent\n")
        step("the agent's write leaves session A's owed flags as they were",
             "" if owed_flags(c, SID) == before else "owed flags changed: %s -> %s" % (before, owed_flags(c, SID)))
        step("session A's Bash call is still refused by handoff-unread after the agent's write",
             refused_by(guard_call(c, SID, "Bash", BASH), HANDOFF_RULE))
    finally:
        c.cleanup()


def case_agent_compaction_owes_nothing():
    """An agent of session A compacts. Its PostCompact carries A's session id and agent_id, and A's main context
    did not compact. The PostCompact must set no owed flag for A, so A's Bash call is allowed."""
    c = Case("agent-compact")
    try:
        c.seed_handoff(SID)
        post = c.run(READ_CHECK, "--post-compact", {
            "session_id": SID, "hook_event_name": "PostCompact", "trigger": "auto",
            "cwd": c.proj, "agent_id": AGENT_ID})
        if not step("the agent's PostCompact exits 0", exit_why(post)):
            return
        step("an agent's compaction (agent_id set) sets no owed flag for its main session",
             no_owed_flag(c, SID))
        step("session A's Bash call is allowed after an agent's compaction",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


def case_agent_transcript_compaction_owes_nothing():
    """The same agent compaction with no agent_id on the payload. Its transcript_path is the agent's own file
    under the session's `subagents` folder, so the PostCompact sets no owed flag for the main session."""
    c = Case("agent-transcript")
    try:
        c.seed_handoff(SID)
        tp = os.path.join(c.cfg, "projects", "proj", SID, "subagents", "agent-%s.jsonl" % AGENT_ID)
        write_transcript(tp, [transcript_line("user", [{"type": "text", "text": "hello"}])])
        post = c.run(READ_CHECK, "--post-compact", {
            "session_id": SID, "hook_event_name": "PostCompact", "trigger": "auto",
            "cwd": c.proj, "transcript_path": tp})
        if not step("the agent transcript's PostCompact exits 0", exit_why(post)):
            return
        step("an agent's compaction (its transcript under subagents/) sets no owed flag for the main session",
             no_owed_flag(c, SID))
        step("session A's Bash call is allowed after an agent's compaction seen by transcript",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


def case_unkeyed_legacy_flag_owes_nothing():
    """A flag left on disk in the old shared form, with no session id in its name, is never read as an owed state.
    Neither session's Bash call is refused. No file of that form exists on this machine, so none needs migrating."""
    c = Case("legacy")
    try:
        c.seed_handoff(SID)
        c.seed_handoff(OTHER_SID)
        for name in ("reread", "audit"):
            put(c.state(name), "1")
        step("session A's Bash call is allowed with an unkeyed legacy flag on disk",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
        step("session B's Bash call is allowed with an unkeyed legacy flag on disk",
             allowed_why(guard_call(c, OTHER_SID, "Bash", BASH)))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 6
# A Read clears the reread flag only when the Reads so far cover the whole handoff (decision
# precompact-handoff, item 9). Each case puts the handoff on disk, sets the flag with PostCompact, then Reads.

LINES50 = "".join("line %02d\n" % i for i in range(1, 51))   # 50 lines of 8 bytes each


def flag_set(c, sid):
    return os.path.isfile(c.state("%s.reread" % sid))


def read_range(c, sid, path, offset=None, limit=None):
    """One PreToolUse Read of `path`. offset and limit are sent only when given, as Claude Code sends them."""
    tool_input = {"file_path": path}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    return c.run(READ_CHECK, "--pre-read", {
        "session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "Read",
        "tool_input": tool_input, "cwd": c.proj})


def compact_with(c, sid, text):
    """The handoff on disk holds `text` byte for byte, and PostCompact sets the flag. Returns the PostCompact run."""
    put_bytes(c.handoff(sid), text.encode("utf-8"))
    return c.post_compact(sid)


def case_partial_read_keeps_flag():
    """A Read of lines 1-10 of a 50-line handoff keeps the flag set. The next Bash call is refused by
    handoff-unread, and the refusal names the unread lines 11-50."""
    c = Case("partial-read")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        rd = read_range(c, SID, c.handoff(SID), offset=1, limit=10)
        if not step("the Read of lines 1-10 exits 0", exit_why(rd)):
            return
        step("a Read of lines 1-10 keeps the reread flag set",
             "" if flag_set(c, SID) else "the Read of lines 1-10 cleared the reread flag")
        got = guard_call(c, SID, "Bash", BASH)
        if step("the Bash call is refused by handoff-unread after the partial Read",
                refused_by(got, HANDOFF_RULE)):
            step("the refusal names the unread lines 11-50",
                 "" if "11-50" in got[1] else "the refusal does not name 11-50: %r" % got[1][:120])
    finally:
        c.cleanup()


def case_pages_clear_flag_when_covered():
    """Lines 1-25, then lines 26-50, of a 50-line handoff. The flag stays set after the first page and is
    cleared by the second."""
    c = Case("pages")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        first = read_range(c, SID, c.handoff(SID), offset=1, limit=25)
        if not step("the Read of lines 1-25 exits 0", exit_why(first)):
            return
        step("after lines 1-25 the reread flag is still set",
             "" if flag_set(c, SID) else "the Read of lines 1-25 cleared the reread flag")
        second = read_range(c, SID, c.handoff(SID), offset=26, limit=25)
        if not step("the Read of lines 26-50 exits 0", exit_why(second)):
            return
        step("after lines 26-50 the reread flag is cleared",
             "" if not flag_set(c, SID) else "the reread flag is still set after lines 26-50")
    finally:
        c.cleanup()


def case_out_of_order_pages_clear_flag():
    """Lines 26-50, then lines 1-25. The flag stays set after the first page and is cleared by the second."""
    c = Case("out-of-order")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        first = read_range(c, SID, c.handoff(SID), offset=26, limit=25)
        if not step("the Read of lines 26-50 exits 0", exit_why(first)):
            return
        step("after lines 26-50 the reread flag is still set",
             "" if flag_set(c, SID) else "the Read of lines 26-50 cleared the reread flag")
        second = read_range(c, SID, c.handoff(SID), offset=1, limit=25)
        if not step("the Read of lines 1-25 exits 0", exit_why(second)):
            return
        step("after lines 1-25 the reread flag is cleared",
             "" if not flag_set(c, SID) else "the reread flag is still set after both pages")
    finally:
        c.cleanup()


def case_overlapping_pages_clear_flag():
    """Lines 1-30, then lines 20-50. The two overlap and together cover the handoff, so the flag is cleared by
    the second Read. The first Read alone leaves it set."""
    c = Case("overlap")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        first = read_range(c, SID, c.handoff(SID), offset=1, limit=30)
        if not step("the Read of lines 1-30 exits 0", exit_why(first)):
            return
        step("after lines 1-30 the reread flag is still set",
             "" if flag_set(c, SID) else "the Read of lines 1-30 cleared the reread flag")
        second = read_range(c, SID, c.handoff(SID), offset=20, limit=31)
        if not step("the Read of lines 20-50 exits 0", exit_why(second)):
            return
        step("after lines 20-50 the reread flag is cleared",
             "" if not flag_set(c, SID) else "the reread flag is still set after the overlapping Read")
    finally:
        c.cleanup()


def case_plain_read_of_small_handoff_clears_flag():
    """A plain Read (no offset, no limit) of a handoff under the size limit clears the flag. Green on the
    old code: a regression pin for the one Read that clears it whole."""
    c = Case("plain-read")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        rd = read_range(c, SID, c.handoff(SID))
        if not step("the plain Read exits 0", exit_why(rd)):
            return
        step("a plain Read of the handoff clears the reread flag",
             "" if not flag_set(c, SID) else "the plain Read did not clear the reread flag")
    finally:
        c.cleanup()


def case_limit5_read_keeps_flag():
    """A Read with limit 5 of a 50-line handoff keeps the flag set. A real session made this Read and the
    flag cleared, so the rule was too loose."""
    c = Case("limit5")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        rd = read_range(c, SID, c.handoff(SID), limit=5)
        if not step("the Read with limit 5 exits 0", exit_why(rd)):
            return
        step("a Read with limit 5 keeps the reread flag set",
             "" if flag_set(c, SID) else "the Read with limit 5 cleared the reread flag")
    finally:
        c.cleanup()


def case_offset_zero_read_counts_as_line_one():
    """A Read with offset 0 and limit 25 counts lines 1-25, the same as offset 1 and limit 25: the next Bash call is
    refused naming lines 26-50, and a Read of lines 26-50 clears the flag. case_pages_clear_flag_when_covered is the
    green control, the same pages asked for with offset 1 and 26."""
    c = Case("offset-zero")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, LINES50))):
            return
        first = read_range(c, SID, c.handoff(SID), offset=0, limit=25)
        if not step("the Read with offset 0 and limit 25 exits 0", exit_why(first)):
            return
        step("after offset 0 and limit 25 the reread flag is still set",
             "" if flag_set(c, SID) else "the Read with offset 0 and limit 25 cleared the reread flag")
        got = guard_call(c, SID, "Bash", BASH)
        if step("the Bash call is refused by handoff-unread after the offset 0 Read",
                refused_by(got, HANDOFF_RULE)):
            step("the refusal names the unread lines 26-50, so offset 0 counted lines 1-25",
                 "" if "26-50" in got[1] else "the refusal does not name 26-50: %r" % got[1][:120])
        second = read_range(c, SID, c.handoff(SID), offset=26, limit=25)
        if not step("the Read of lines 26-50 exits 0", exit_why(second)):
            return
        step("after lines 26-50 the reread flag is cleared",
             "" if not flag_set(c, SID) else "the reread flag is still set after lines 26-50")
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 7
# The size limit on a session handoff (decision precompact-handoff). A token is ceil(UTF-8 bytes / 3.5), and
# HANDOFF_MAX_TOKENS is 10000 in hooks/reread_check.py: 35000 bytes is the most that passes (10000 tokens),
# and 35001 bytes is 10001 tokens. Every handoff a case writes has the six required sections, so the
# handoff-sections rule never refuses it first.

SIZE_RULE = "handoff-too-big"
SIZE_LIMIT = 10000
BASE_SECTIONS = ("# Handoff\n\n## Goal\nFix the handoff.\n\n## Working premises\nNone yet.\n\n"
                 "## Where things stand\nThe reread check is in review.\n\n## Work in flight\nNothing.\n\n"
                 "## Next steps\n- Go on.\n\n## Files and commands\nhooks/reread_check.py\n")
FILLER_LINE = "Filler: \n"   # 9 bytes: the filler's label and its newline
CUT_LINE = "Cut: " + "k" * 500 + "\n"   # 506 bytes, one line of the handoff that a case shrinks or grows


def token_estimate(n):
    """ceil(n / 3.5) for a byte count n, in whole numbers."""
    return (2 * n + 6) // 7


def handoff_text(total, middle=""):
    """A handoff of exactly `total` UTF-8 bytes: the six sections, then `middle`, then a filler line of w's."""
    head = BASE_SECTIONS + middle
    pad = total - len(head.encode("utf-8")) - len(FILLER_LINE)
    if pad < 0:
        raise ValueError("handoff_text: %d bytes is too small for the sections" % total)
    return head + "Filler: " + "w" * pad + "\n"


def handoff_multibyte(min_bytes):
    """A handoff of at least `min_bytes` UTF-8 bytes and fewer characters: its filler is e-acute, two bytes each."""
    head = BASE_SECTIONS
    pairs = (min_bytes - len(head.encode("utf-8")) - len(FILLER_LINE) + 1) // 2
    return head + "Filler: " + "é" * pairs + "\n"


def write_handoff(c, text, sid=SID, agent_id=None):
    return guard_call(c, sid, "Write", {"file_path": c.handoff(sid), "content": text}, agent_id=agent_id)


def edit_handoff(c, old, new, replace_all=False, sid=SID, agent_id=None):
    return guard_call(c, sid, "Edit", {"file_path": c.handoff(sid), "old_string": old, "new_string": new,
                                       "replace_all": replace_all}, agent_id=agent_id)


def multi_edit_handoff(c, edits, sid=SID, agent_id=None):
    return guard_call(c, sid, "MultiEdit", {"file_path": c.handoff(sid), "edits": edits}, agent_id=agent_id)


def size_refusal(got, tokens):
    """'' when the guard refused the call under handoff-too-big and its reason gives the estimate, the limit
    and the remedy words (history, review rounds, CI). Else the first thing that is missing."""
    why = refused_by(got, SIZE_RULE)
    if why:
        return why
    reason = got[1]
    missing = [w for w in (str(tokens), str(SIZE_LIMIT), "history", "review rounds") if w not in reason.lower()]
    if not re.search(r"\bCI\b", reason):
        missing.append("CI")
    return "" if not missing else "the refusal lacks %s: %r" % (", ".join(missing), reason[:160])


def read_check_module():
    """hooks/reread_check.py imported in this process, or None when the import fails."""
    try:
        spec = importlib.util.spec_from_file_location("reread_check_under_test", READ_CHECK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def case_size_limit_constant_is_10000_tokens():
    """hooks/reread_check.py holds HANDOFF_MAX_TOKENS = 10000."""
    mod = read_check_module()
    value = getattr(mod, "HANDOFF_MAX_TOKENS", None) if mod is not None else None
    check("reread_check: HANDOFF_MAX_TOKENS is 10000", value == SIZE_LIMIT,
          "HANDOFF_MAX_TOKENS is %r" % (value,))


def case_write_over_limit_is_refused():
    """A main-session Write of 35001 bytes (10001 tokens) to the handoff is refused by handoff-too-big. The reason
    gives the estimate, the limit and the remedy words."""
    c = Case("too-big-write")
    try:
        step("a Write of 35001 bytes (10001 tokens) to the handoff is refused by handoff-too-big",
             size_refusal(write_handoff(c, handoff_text(35001)), token_estimate(35001)))
    finally:
        c.cleanup()


def case_write_at_limit_passes():
    """A main-session Write of exactly 35000 bytes (10000 tokens) passes. Green on the old code: the boundary pin
    that the refusal above must not move."""
    c = Case("at-limit")
    try:
        step("a Write of exactly 35000 bytes (10000 tokens) to the handoff passes",
             allowed_why(write_handoff(c, handoff_text(35000))))
    finally:
        c.cleanup()


def case_write_counts_utf8_bytes_not_characters():
    """A Write with fewer characters than the limit and more UTF-8 bytes is refused: the estimate counts bytes."""
    c = Case("utf8-bytes")
    try:
        text = handoff_multibyte(35001)
        size = len(text.encode("utf-8"))
        chars = len(text)
        if not step("the fixture is over the limit in bytes and under it in characters",
                    "" if size > 35000 and chars < 35000 else "bytes %d, characters %d" % (size, chars)):
            return
        step("a Write over the limit in UTF-8 bytes is refused, though its characters are under it",
             size_refusal(write_handoff(c, text), token_estimate(size)))
    finally:
        c.cleanup()


def case_write_over_limit_to_other_path_passes():
    """A Write of 40000 bytes to a file that is not the session handoff passes."""
    c = Case("other-path")
    try:
        other = os.path.join(c.proj, "notes.md")
        step("a Write of 40000 bytes to another file passes",
             allowed_why(guard_call(c, SID, "Write", {"file_path": other, "content": "w" * 40000})))
    finally:
        c.cleanup()


def case_agent_write_over_limit_is_refused():
    """An agent's Write of 35001 bytes to the session's handoff is refused by handoff-too-big, as a main-session
    Write is."""
    c = Case("agent-too-big")
    try:
        step("an agent's Write of 35001 bytes to the handoff is refused by handoff-too-big",
             size_refusal(write_handoff(c, handoff_text(35001), agent_id=AGENT_ID), token_estimate(35001)))
    finally:
        c.cleanup()


def case_edit_over_limit_is_refused():
    """An Edit whose result is 36001 bytes (10286 tokens) is refused. The file on disk is 30000 bytes, under the
    limit, so the Edit is what takes it over. An Edit to 31000 bytes passes."""
    c = Case("edit-grow")
    try:
        before = handoff_text(30000)
        put_bytes(c.handoff(SID), before.encode("utf-8"))
        big = "- Go on. " + "z" * 6000
        after = before.replace("- Go on.", big, 1)
        step("an Edit to 36001 bytes (over the limit) is refused by handoff-too-big",
             size_refusal(edit_handoff(c, "- Go on.", big), token_estimate(len(after.encode("utf-8")))))
        small = "- Go on. " + "z" * 1000
        step("an Edit to 31000 bytes (under the limit) passes",
             allowed_why(edit_handoff(c, "- Go on.", small)))
    finally:
        c.cleanup()


def case_edit_replace_all_counts_every_occurrence():
    """Three occurrences of `Mark ZZ` in a 30000-byte handoff. With replace_all false the Edit replaces the first
    one, which is under the limit, and passes. With replace_all true it replaces all three, which is over the
    limit, and is refused."""
    c = Case("replace-all")
    try:
        before = handoff_text(30000, "Mark ZZ one\nMark ZZ two\nMark ZZ three\n")
        put_bytes(c.handoff(SID), before.encode("utf-8"))
        new = "Mark " + "y" * 2000
        first_only = before.replace("Mark ZZ", new, 1)
        every = before.replace("Mark ZZ", new)
        step("the fixture: one replacement is under the limit and all three are over it",
             "" if (token_estimate(len(first_only.encode("utf-8"))) <= SIZE_LIMIT
                   and token_estimate(len(every.encode("utf-8"))) > SIZE_LIMIT)
             else "one replacement %d bytes, all %d bytes" % (len(first_only.encode("utf-8")),
                                                            len(every.encode("utf-8"))))
        step("an Edit with replace_all false (one replacement, under the limit) passes",
             allowed_why(edit_handoff(c, "Mark ZZ", new, replace_all=False)))
        step("an Edit with replace_all true (three replacements, over the limit) is refused by handoff-too-big",
             size_refusal(edit_handoff(c, "Mark ZZ", new, replace_all=True),
                          token_estimate(len(every.encode("utf-8")))))
    finally:
        c.cleanup()


def case_over_limit_file_write_shrink_passes_grow_refused():
    """The handoff on disk is 36000 bytes (10286 tokens), over the limit. A Write that makes it smaller passes
    even though the result is still over the limit. A Write of the same size, or larger, is refused."""
    c = Case("shrink-write")
    try:
        before = handoff_text(36000, CUT_LINE)
        put_bytes(c.handoff(SID), before.encode("utf-8"))
        step("the handoff on disk is over the limit before the Write",
             "" if token_estimate(len(before.encode("utf-8"))) > SIZE_LIMIT else "the fixture is under the limit")
        smaller = handoff_text(35500)
        step("a Write of 35500 bytes (still over the limit, smaller than the file) passes",
             allowed_why(write_handoff(c, smaller)))
        step("a Write of 36000 bytes (the same size as the file) is refused by handoff-too-big",
             size_refusal(write_handoff(c, handoff_text(36000)), token_estimate(36000)))
        step("a Write of 36500 bytes (larger than the file) is refused by handoff-too-big",
             size_refusal(write_handoff(c, handoff_text(36500)), token_estimate(36500)))
    finally:
        c.cleanup()


def case_over_limit_file_edit_shrink_passes_grow_refused():
    """The handoff on disk is 36000 bytes, over the limit. An Edit that cuts 506 bytes passes: the result is still
    over the limit but smaller. An Edit that keeps the size, or grows it, is refused."""
    c = Case("shrink-edit")
    try:
        before = handoff_text(36000, CUT_LINE)
        put_bytes(c.handoff(SID), before.encode("utf-8"))
        step("an Edit that removes the cut line (35494 bytes, smaller, still over the limit) passes",
             allowed_why(edit_handoff(c, CUT_LINE, "")))
        same = "Cut: " + "j" * 500 + "\n"
        same_after = before.replace(CUT_LINE, same, 1)
        step("an Edit that keeps the file the same size is refused by handoff-too-big",
             size_refusal(edit_handoff(c, CUT_LINE, same), token_estimate(len(same_after.encode("utf-8")))))
        grow = "Cut: " + "k" * 600 + "\n"
        grow_after = before.replace(CUT_LINE, grow, 1)
        step("an Edit that grows the file is refused by handoff-too-big",
             size_refusal(edit_handoff(c, CUT_LINE, grow), token_estimate(len(grow_after.encode("utf-8")))))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 8
# A Read clears the reread flag only when its range counts: at most READ_CAP_TOKENS = 25000 tokens and at most
# 2000 lines (the Read default when no limit is given). The hook cannot see what a Read returned, so a range over
# the cap counts nothing. An agent's rewrite of the handoff sets the same flag (decision precompact-handoff, item 9).

READ_CAP_TOKENS = 25000


def long_lines(count, width):
    """`count` lines of exactly `width` bytes each, newline included."""
    out = []
    for i in range(1, count + 1):
        head = "line %03d " % i
        out.append(head + "x" * (width - len(head) - 1) + "\n")
    return "".join(out)


ONE_HUNDRED_LONG = long_lines(100, 900)   # 90000 bytes, 25715 tokens: over READ_CAP_TOKENS in one range
SHORT_2500 = "".join("l%04d\n" % i for i in range(1, 2501))   # 2500 lines of 6 bytes: 15000 bytes, 4286 tokens


def case_plain_read_over_cap_keeps_flag():
    """A plain Read (no offset, no limit) of a 100-line handoff of 90000 bytes (25715 tokens) keeps the flag set:
    its one range is over READ_CAP_TOKENS, so it counts nothing."""
    c = Case("read-over-cap")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, ONE_HUNDRED_LONG))):
            return
        rd = read_range(c, SID, c.handoff(SID))
        if not step("the plain Read exits 0", exit_why(rd)):
            return
        step("a plain Read of a 25715-token handoff keeps the reread flag set",
             "" if flag_set(c, SID) else "the plain Read cleared the reread flag")
    finally:
        c.cleanup()


def case_range_over_cap_counts_nothing():
    """Lines 1-100 of the same 90000-byte handoff, asked for with limit 100: the range is over the cap, so the flag
    stays set."""
    c = Case("range-over-cap")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, ONE_HUNDRED_LONG))):
            return
        rd = read_range(c, SID, c.handoff(SID), offset=1, limit=100)
        if not step("the Read of lines 1-100 exits 0", exit_why(rd)):
            return
        step("a Read of lines 1-100 (25715 tokens) keeps the reread flag set",
             "" if flag_set(c, SID) else "the Read of lines 1-100 cleared the reread flag")
    finally:
        c.cleanup()


def case_pages_under_cap_clear_flag():
    """Lines 1-50, then lines 51-100, of the 90000-byte handoff. Each page is 12858 tokens, under the cap, and
    together they cover the handoff: the flag is cleared by the second page."""
    c = Case("pages-under-cap")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, ONE_HUNDRED_LONG))):
            return
        first = read_range(c, SID, c.handoff(SID), offset=1, limit=50)
        if not step("the Read of lines 1-50 exits 0", exit_why(first)):
            return
        step("after lines 1-50 the reread flag is still set",
             "" if flag_set(c, SID) else "the Read of lines 1-50 cleared the reread flag")
        second = read_range(c, SID, c.handoff(SID), offset=51, limit=50)
        if not step("the Read of lines 51-100 exits 0", exit_why(second)):
            return
        step("after lines 51-100 the reread flag is cleared",
             "" if not flag_set(c, SID) else "the reread flag is still set after lines 51-100")
    finally:
        c.cleanup()


def case_plain_read_past_2000_lines_keeps_flag():
    """A plain Read of a 2500-line handoff covers only lines 1-2000, the Read default. The flag stays set."""
    c = Case("plain-2000")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, SHORT_2500))):
            return
        rd = read_range(c, SID, c.handoff(SID))
        if not step("the plain Read exits 0", exit_why(rd)):
            return
        step("a plain Read of a 2500-line handoff keeps the reread flag set",
             "" if flag_set(c, SID) else "the plain Read cleared the reread flag")
    finally:
        c.cleanup()


def case_range_over_2000_lines_counts_nothing():
    """Lines 1-2500 of a 2500-line handoff, asked for with limit 2500: over 2000 lines, so the range counts nothing
    and the flag stays set."""
    c = Case("range-over-2000")
    try:
        if not step("PostCompact exits 0", exit_why(compact_with(c, SID, SHORT_2500))):
            return
        rd = read_range(c, SID, c.handoff(SID), offset=1, limit=2500)
        if not step("the Read of lines 1-2500 exits 0", exit_why(rd)):
            return
        step("a Read of lines 1-2500 keeps the reread flag set",
             "" if flag_set(c, SID) else "the Read of lines 1-2500 cleared the reread flag")
    finally:
        c.cleanup()


def case_agent_write_sets_read_flag():
    """An agent's Write of the session's handoff sets the reread flag. The main session's next Bash call is refused
    by handoff-unread, and the refusal says an agent rewrote the handoff. The agent's write sets no audit flag."""
    c = Case("agent-write-flag")
    try:
        put_bytes(c.handoff(SID), handoff_text(600).encode("utf-8"))
        step("no reread flag before the agent writes",
             "" if not flag_set(c, SID) else "the reread flag is set before any agent write")
        rewritten = handoff_text(700)
        if not step("the agent's Write is allowed", allowed_why(write_handoff(c, rewritten, agent_id=AGENT_ID))):
            return
        put_bytes(c.handoff(SID), rewritten.encode("utf-8"))
        got = guard_call(c, SID, "Bash", BASH)
        if not step("the main session's Bash call is refused by handoff-unread after the agent's write",
                    refused_by(got, HANDOFF_RULE)):
            return
        step("the refusal says an agent rewrote the handoff",
             "" if "agent" in got[1].lower() and "rewrote" in got[1].lower()
             else "the refusal does not say an agent rewrote it: %r" % got[1][:120])
        step("the agent's write sets no audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the audit flag is set after the agent's write")
    finally:
        c.cleanup()


def case_agent_edit_sets_read_flag():
    """An agent's Edit of the session's handoff sets the reread flag, as its Write does: the main session's next
    Bash call is refused by handoff-unread, and the refusal says an agent rewrote the handoff."""
    c = Case("agent-edit-flag")
    try:
        put_bytes(c.handoff(SID), handoff_text(600).encode("utf-8"))
        step("no reread flag before the agent edits",
             "" if not flag_set(c, SID) else "the reread flag is set before any agent edit")
        old, new = "- Go on.", "- Go on, then check the premises."
        if not step("the agent's Edit is allowed", allowed_why(edit_handoff(c, old, new, agent_id=AGENT_ID))):
            return
        put_bytes(c.handoff(SID), handoff_text(600).replace(old, new, 1).encode("utf-8"))
        got = guard_call(c, SID, "Bash", BASH)
        if not step("the main session's Bash call is refused by handoff-unread after the agent's edit",
                    refused_by(got, HANDOFF_RULE)):
            return
        step("the refusal says an agent rewrote the handoff",
             "" if "agent" in got[1].lower() and "rewrote" in got[1].lower()
             else "the refusal does not say an agent rewrote it: %r" % got[1][:120])
    finally:
        c.cleanup()


def case_agent_multiedit_sets_read_flag():
    """An agent's MultiEdit of the session's handoff sets the reread flag, as its Edit does: the main session's next
    Bash call is refused by handoff-unread, and the refusal says an agent rewrote the handoff."""
    c = Case("agent-multiedit-flag")
    try:
        put_bytes(c.handoff(SID), handoff_text(600).encode("utf-8"))
        step("no reread flag before the agent's MultiEdit",
             "" if not flag_set(c, SID) else "the reread flag is set before any agent MultiEdit")
        old, new = "- Go on.", "- Go on, then check the premises."
        edits = [{"old_string": old, "new_string": new, "replace_all": False}]
        if not step("the agent's MultiEdit is allowed",
                    allowed_why(multi_edit_handoff(c, edits, agent_id=AGENT_ID))):
            return
        put_bytes(c.handoff(SID), handoff_text(600).replace(old, new, 1).encode("utf-8"))
        got = guard_call(c, SID, "Bash", BASH)
        if not step("the main session's Bash call is refused by handoff-unread after the agent's MultiEdit",
                    refused_by(got, HANDOFF_RULE)):
            return
        step("the refusal says an agent rewrote the handoff",
             "" if "agent" in got[1].lower() and "rewrote" in got[1].lower()
             else "the refusal does not say an agent rewrote it: %r" % got[1][:120])
    finally:
        c.cleanup()


def case_main_write_sets_no_flag():
    """The main session's own Write of the handoff sets no reread flag and no audit flag, and its next Bash call is
    allowed. Green on the old code: the control for the agent cases above."""
    c = Case("main-write-flag")
    try:
        rewritten = handoff_text(700)
        if not step("the main session's Write is allowed", allowed_why(write_handoff(c, rewritten))):
            return
        put_bytes(c.handoff(SID), rewritten.encode("utf-8"))
        step("the main session's Write sets no reread flag",
             "" if not flag_set(c, SID) else "the main session's Write set the reread flag")
        step("the main session's Write sets no audit flag",
             "" if not os.path.isfile(audit_flag(c, SID)) else "the main session's Write set the audit flag")
        step("the main session's Bash call is allowed after its own Write",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


def case_agent_rewrite_partial_read_keeps_flag_whole_read_clears():
    """After an agent's rewrite sets the flag, a partial Read (lines 1-10 of 20) keeps it set, and a whole Read
    (no offset, no limit) clears it. The same range rule as a compaction's flag."""
    c = Case("agent-partial-whole")
    try:
        put_bytes(c.handoff(SID), handoff_text(600).encode("utf-8"))
        rewritten = handoff_text(700)
        if not step("the agent's Write is allowed", allowed_why(write_handoff(c, rewritten, agent_id=AGENT_ID))):
            return
        put_bytes(c.handoff(SID), rewritten.encode("utf-8"))
        if not step("the agent's rewrite sets the reread flag",
                    "" if flag_set(c, SID) else "the agent's rewrite did not set the reread flag"):
            return
        partial = read_range(c, SID, c.handoff(SID), offset=1, limit=10)
        if not step("the partial Read exits 0", exit_why(partial)):
            return
        step("after the partial Read (lines 1-10 of 20) the reread flag is still set",
             "" if flag_set(c, SID) else "the partial Read cleared the reread flag")
        whole = read_range(c, SID, c.handoff(SID))
        if not step("the whole Read exits 0", exit_why(whole)):
            return
        step("after the whole Read the reread flag is cleared",
             "" if not flag_set(c, SID) else "the whole Read did not clear the reread flag")
        step("the main session's Bash call is allowed after the whole Read",
             allowed_why(guard_call(c, SID, "Bash", BASH)))
    finally:
        c.cleanup()


# --------------------------------------------------------------------------- part 9
# The cost of the handoff check on an allowed call (decision precompact-handoff, item 9). The reread flag is checked
# first, so a session with no flag never opens its handoff file. The probe is a launcher that logs each open and
# stat of a handoff file in the guard's own process. Its positive twin, a flagged session, must show the probe at
# work, or the no-flag case proves nothing.

COST_LOG_ENV = "WAVE2_COST_LOG"
COST_PREAMBLE = "\n".join([
    "import builtins, os",
    "_log = os.environ.get(%r)" % COST_LOG_ENV,
    "_real_open = builtins.open",
    "_real_stat = os.stat",
    "def _note(p):",
    "    if _log and isinstance(p, (str, bytes)):",
    "        s = os.fsdecode(p)",
    "        if 'handoffs' in s and os.path.basename(s).endswith('.md'):",
    "            with _real_open(_log, 'a', encoding='utf-8') as f:",
    "                f.write(s + chr(10))",
    "def _open(p, *a, **k):",
    "    _note(p)",
    "    return _real_open(p, *a, **k)",
    "def _stat(p, *a, **k):",
    "    _note(p)",
    "    return _real_stat(p, *a, **k)",
    "builtins.open = _open",
    "os.stat = _stat",
    "",
])
COST_SRC = COST_PREAMBLE + "\n" + ROOMY_DISK_SRC


def probed_bash(c, sid, log):
    """One Bash call through the guard with the probe on: (decision, reason)."""
    return guard_call(c, sid, "Bash", BASH, extra_env={COST_LOG_ENV: log}, src=COST_SRC)


def handoff_probe_hits(log, sid):
    """The probe log's lines that name this session's handoff file. [] when nothing was logged."""
    if not os.path.isfile(log):
        return []
    with open(log, encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [s for s in lines if os.path.basename(s) == "%s.md" % sid]


def case_no_flag_call_opens_no_handoff():
    """A Bash call from a session with no flag is allowed, and the guard opens or stats its handoff file 0 times."""
    c = Case("cost-no-flag")
    try:
        c.seed_handoff(SID)
        log = os.path.join(c.root, "probe.log")
        if not step("the Bash call is allowed", allowed_why(probed_bash(c, SID, log))):
            return
        hits = handoff_probe_hits(log, SID)
        step("a Bash call from a session with no flag opens or stats its handoff file 0 times",
             "" if not hits else "the guard touched the handoff %d time(s): %r" % (len(hits), hits[:2]))
    finally:
        c.cleanup()


def case_flagged_call_opens_the_handoff():
    """The positive twin: with the flag set, the same Bash call reads the handoff (the probe logs it) and is refused
    by handoff-unread."""
    c = Case("cost-flagged")
    try:
        c.seed_handoff(SID)
        if not step("PostCompact exits 0", exit_why(c.post_compact(SID))):
            return
        log = os.path.join(c.root, "probe.log")
        got = probed_bash(c, SID, log)
        if not step("the probe logs the flagged call's open or stat of the handoff",
                    "" if handoff_probe_hits(log, SID) else "no handoff open or stat was logged"):
            return
        step("the flagged Bash call is refused by handoff-unread", refused_by(got, HANDOFF_RULE))
    finally:
        c.cleanup()


def main() -> int:
    print("Part 1: SessionEnd pointer, SessionStart reorient (hooks/precompact_handoff.py)")
    case_session_end_clear_writes_pointer()
    case_session_end_other_reason_writes_no_pointer()
    case_reorient_names_newest_pointer_same_dir()
    case_fork_ignores_stale_pointer()
    case_quiet_session_found_by_fallback()
    case_reorient_ignores_pointer_for_other_dir()
    case_reorient_no_pointer_names_newest_handoff_same_dir()
    case_reorient_none_says_so()
    case_cleared_reorient_lists_every_old_premise()
    case_reorient_matches_either_spelling_of_proj()
    case_safe_stop_entry_pinned()
    case_clear_pointer_without_handoff_names_none()
    case_unusable_pointers_are_removed()
    case_stale_records_are_swept()
    case_failed_pointer_delete_is_logged()

    print("Part 2: PostCompact flag, Read clears it, Stop blocks (hooks/reread_check.py)")
    check("reread_check: the module exists", os.path.isfile(READ_CHECK),
          "missing: %s" % READ_CHECK)
    case_post_compact_sets_flag()
    case_stop_needs_handoff_file()
    case_read_by_8dot3_spelling_clears_flag()
    case_read_of_handoff_clears_flag()
    case_read_of_other_file_keeps_flag()
    case_agent_read_keeps_flag()
    case_stop_hook_active_passes()
    case_stop_no_flag_passes()
    case_sibling_import_failure_exits_zero()
    case_unreadable_stdin_reread_exits_zero()

    print("Part 3: bad stdin and live controls, both modules")
    case_bad_stdin_and_live_control_per_mode()

    print("Part 4: the compaction audit (hooks/guard.py rule compaction-audit, hooks/reread_check.py)")
    case_compaction_audit_refuses_bash_and_write()
    case_audit_spawn_clears_flag_and_writes_pass()
    case_no_compaction_never_refused()
    case_post_compact_writes_audit_flag()
    case_quoted_or_plain_spawn_is_refused_and_clears_nothing()
    case_agent_payload_never_refused_or_clears()
    case_unread_handoff_is_refused_first()
    case_stop_blocks_for_audit_after_read()
    case_stop_quiet_without_compaction()
    case_audit_marker_after_blank_lines_clears()
    case_refused_audit_spawn_keeps_flag()
    case_refused_then_accepted_audit_spawn_clears()
    case_audit_marker_judged_like_the_home()
    case_reader_follows_the_home_constant()
    case_stale_sibling_without_audit_flag_path_exits_zero()
    case_remedies_name_probe_home()
    case_remedies_name_unpatched_home()
    case_stop_remedy_spawn_clears_probe_home()
    case_refusal_remedy_spawn_clears_probe_home()
    case_refusal_remedy_spawn_clears_unpatched_home()
    case_stop_remedy_spawn_clears_unpatched_home()

    print("Part 5: owed state is per session, and an agent's compaction owes its parent nothing (hooks/reread_check.py)")
    case_other_session_compaction_owes_nothing()
    case_compacting_session_still_owes_read_and_audit()
    case_own_compaction_owes_read_and_audit()
    case_stop_checkpoint_owes_nothing()
    case_main_transcript_compaction_owes_flags()
    case_agent_handoff_write_keeps_owed_read()
    case_agent_compaction_owes_nothing()
    case_agent_transcript_compaction_owes_nothing()
    case_unkeyed_legacy_flag_owes_nothing()

    print("Part 6: a Read clears the reread flag only when its ranges cover the handoff (hooks/reread_check.py)")
    case_partial_read_keeps_flag()
    case_pages_clear_flag_when_covered()
    case_out_of_order_pages_clear_flag()
    case_overlapping_pages_clear_flag()
    case_plain_read_of_small_handoff_clears_flag()
    case_limit5_read_keeps_flag()
    case_offset_zero_read_counts_as_line_one()

    print("Part 7: the handoff size limit, HANDOFF_MAX_TOKENS = 10000 (hooks/reread_check.py, hooks/guard.py rule handoff-too-big)")
    case_size_limit_constant_is_10000_tokens()
    case_write_over_limit_is_refused()
    case_write_at_limit_passes()
    case_write_counts_utf8_bytes_not_characters()
    case_write_over_limit_to_other_path_passes()
    case_agent_write_over_limit_is_refused()
    case_edit_over_limit_is_refused()
    case_edit_replace_all_counts_every_occurrence()
    case_over_limit_file_write_shrink_passes_grow_refused()
    case_over_limit_file_edit_shrink_passes_grow_refused()

    print("Part 8: an agent's rewrite sets the reread flag, and a Read counts only within the cap (hooks/reread_check.py)")
    case_plain_read_over_cap_keeps_flag()
    case_range_over_cap_counts_nothing()
    case_pages_under_cap_clear_flag()
    case_plain_read_past_2000_lines_keeps_flag()
    case_range_over_2000_lines_counts_nothing()
    case_agent_write_sets_read_flag()
    case_agent_edit_sets_read_flag()
    case_agent_multiedit_sets_read_flag()
    case_main_write_sets_no_flag()
    case_agent_rewrite_partial_read_keeps_flag_whole_read_clears()

    print("Part 9: the handoff check costs no open of the handoff on a call with no flag (hooks/guard.py, hooks/reread_check.py)")
    case_no_flag_call_opens_no_handoff()
    case_flagged_call_opens_the_handoff()

    if FAILED:
        print()
        print("test_handoff_wave2 FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print()
    print("test_handoff_wave2 PASS: all checks right")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
