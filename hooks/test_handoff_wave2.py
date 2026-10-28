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
import collections
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_precompact_handoff import (  # noqa: E402
    HANDOFF_WITH_PREMISES, ids_in, put, transcript_line, write_transcript)

PRECOMPACT = os.environ.get("PRECOMPACT_HANDOFF_UNDER_TEST") or os.path.join(
    HERE, "precompact_handoff.py")
READ_CHECK = os.environ.get("READ_CHECK_UNDER_TEST") or os.path.join(HERE, "reread_check.py")
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
        self.root = tempfile.mkdtemp(prefix="wave2_%s_" % name)
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
            check("read by %s clears the flag: the next Stop passes" % label,
                  passes(c.stop("r-1")), "")
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
        check("the session's own Read after them clears the flag: the next Stop passes",
              passes(c.stop("sub-1")), "")
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
            check("read by %s name clears the flag: the next Stop passes" % tag,
                  passes(c.stop("d-1")), "rc=%r out=%r" % (rd.returncode, tail(rd.stdout)))
        finally:
            c.cleanup()


def case_sibling_import_failure_exits_zero():
    """reread_check.py imports its sibling precompact_handoff.py. With the sibling missing, or
    present but raising on import, each reread_check mode exits 0. Live control: a copy that
    has the real sibling still blocks. The copies sit in this case's scratch dir."""
    c = Case("import")
    try:
        probe = {"session_id": "imp-1", "hook_event_name": "Stop", "stop_hook_active": False,
                 "tool_name": "Read", "tool_input": {"file_path": c.handoff("imp-1")},
                 "cwd": c.proj}
        for tag, variant in (("missing", "no sibling"), ("raises", "sibling raises on import")):
            d = c.dir("sib_" + tag)
            shutil.copy(READ_CHECK, os.path.join(d, "reread_check.py"))
            if tag == "raises":
                put(os.path.join(d, "precompact_handoff.py"),
                    "raise ImportError('test stub: sibling import fails')\n")
            for flag in ("--post-compact", "--pre-read", "--stop"):
                proc = c.run(os.path.join(d, "reread_check.py"), flag, probe)
                check("%s, %s: exits 0" % (variant, flag), proc.returncode == 0,
                      "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        d = c.dir("sib_real")
        shutil.copy(READ_CHECK, os.path.join(d, "reread_check.py"))
        shutil.copy(PRECOMPACT, os.path.join(d, "precompact_handoff.py"))
        mod = os.path.join(d, "reread_check.py")
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
    return passes(c.stop("live-1"))


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

    if FAILED:
        print()
        print("test_handoff_wave2 FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print()
    print("test_handoff_wave2 PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
