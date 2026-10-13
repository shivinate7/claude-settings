#!/usr/bin/env python3
"""Cases for the wave-2 handoff hooks: decisions/handoff-hooks-wave-2.md, ruling items 1 and 2.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_handoff_wave2.py

Seams. The builder matches each one. Every seam is a CLI mode that reads one JSON payload on stdin.

Part 1, hooks/precompact_handoff.py:
  --session-end  (SessionEnd; session_id, reason, cwd). Reason `clear` writes one new file that
                 holds the old session id and the project dir as values. A value is a JSON
                 string or key, or a line or word of plain text. Any other reason writes no
                 file under CLAUDE_CONFIG_DIR, and changes none.
  --reorient     (SessionStart; session_id, source, cwd). Source `clear` or `fork`: names the
                 OLD session's handoff path, taken from the newest pointer for cwd. With no
                 pointer, it names the newest handoff for cwd. With none, it prints the words
                 "no handoff". It also names the NEW session's own handoff path.
                 A handoff belongs to a project dir through the PreCompact state record
                 (state/handoff/<sid>.json, field "repo"). The fixtures seed each session with
                 a real PreCompact run in its dir.
  (no flag)      PreCompact. Unchanged.
  /safe-stop     The pin. The mod runs HANDOFF_PY (mods/session-board/hooks/register.mjs) with
                 `-I -B -c`, cwd = the config dir. It reads JSON with exactly the keys handoff
                 and prompt. HANDOFF_PY is copied below, verbatim, and is not parsed.

Part 2, hooks/reread_check.py (new file):
  --post-compact (PostCompact; session_id, trigger, cwd). Sets the session's flag.
  --pre-read     (PreToolUse, tool Read; session_id, tool_name, tool_input.file_path, cwd).
                 Clears the flag when the path names this session's handoff, in any spelling:
                 full path, forward slashes (Windows only), or `~/.claude/...`. It never denies
                 the read: exit 0 and no deny or block in stdout.
  --stop         (Stop; session_id, stop_hook_active, cwd). With the flag set and
                 stop_hook_active false, prints {"decision": "block", "reason": ...}, and the
                 reason names the handoff path. Otherwise exits 0 and blocks nothing. Flags are
                 per session.

Config. CLAUDE_CONFIG_DIR is <scratch>/home/.claude. HOME and USERPROFILE are <scratch>/home,
so `~/.claude` names the same folder as CLAUDE_CONFIG_DIR.

Stubs. PRECOMPACT_HANDOFF_UNDER_TEST and READ_CHECK_UNDER_TEST replace the two modules. An
always-pass stub (exit 0, no output) must fail every case, the /safe-stop pin included.

Red on the current tree: every case except the /safe-stop pin. The pin passes on purpose,
because it guards a signature that works today.

Each negative case carries a positive twin on a separate session. So a pass cannot come from
a hook that does nothing. The Read spelling cases and the twin use the same live check.
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from test_precompact_handoff import put, transcript_line, write_transcript  # noqa: E402

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

    def read(self, sid, file_path):
        return self.run(READ_CHECK, "--pre-read", {
            "session_id": sid, "hook_event_name": "PreToolUse", "tool_name": "Read",
            "tool_input": {"file_path": file_path}, "cwd": self.proj})

    def stop(self, sid, active=False):
        return self.run(READ_CHECK, "--stop", {
            "session_id": sid, "hook_event_name": "Stop", "stop_hook_active": active,
            "cwd": self.proj})

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


def case_session_end_other_reason_writes_nothing():
    """SessionEnd with any other reason writes no file. Each case first proves that a clear
    run does write, so a silent hook cannot pass."""
    for reason in ("logout", "prompt_input_exit", "other"):
        c = Case("end_" + reason)
        try:
            before = c.snapshot()
            c.session_end("twin-1", "clear")
            twin = [d for d in c.changed(before).values() if d is not None]
            check("session-end %s: positive twin, a clear run writes the pointer" % reason,
                  any(holds_pointer(d, "twin-1", c.proj) for d in twin),
                  "changed files: %d" % len(twin))
            before = c.snapshot()
            proc = c.session_end("other-1", reason)
            changed = c.changed(before)
            check("session-end %s: writes no file and exits 0" % reason,
                  not changed and proc.returncode == 0,
                  "changed: %r rc=%r" % (sorted(changed), proc.returncode))
        finally:
            c.cleanup()


def case_reorient_names_newest_pointer_same_dir():
    """SessionStart clear or fork names the handoff of the NEWEST pointer for the same dir.
    The older handoff is newer by mtime, so the pointer, not the mtime, must decide."""
    for source in ("clear", "fork"):
        c = Case("ptr_" + source)
        try:
            c.link("old-1", c.proj, age=0)
            c.link("old-2", c.proj, age=100)
            before = c.snapshot()
            c.session_end("old-1", "clear")
            c.backdate(c.changed(before), 100)
            c.session_end("old-2", "clear")
            out = c.reorient("new-1", source).stdout
            check("reorient %s: names the newest pointer's handoff (old-2)" % source,
                  c.handoff("old-2") in out, "stdout: %r" % tail(out, 300))
            check("reorient %s: does not name the older pointer's handoff (old-1)" % source,
                  c.handoff("old-1") not in out, "stdout: %r" % tail(out, 300))
            check("reorient %s: names the new session's own handoff path" % source,
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


def case_safe_stop_entry_pinned():
    """The /safe-stop seam, pinned as it is today. Passes on the current tree on purpose."""
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
        c.post_compact("live-1")
        return blocks(c, c.stop("live-1"), "live-1")
    finally:
        c.cleanup()


def case_post_compact_sets_flag():
    """PostCompact sets the flag. The next Stop blocks once and names the handoff path."""
    c = Case("flag")
    try:
        proc = c.post_compact("s-1")
        check("post-compact: exits 0", proc.returncode == 0,
              "rc=%r err=%r" % (proc.returncode, tail(proc.stderr)))
        stop = c.stop("s-1")
        check("post-compact sets the flag: the next Stop blocks and names the handoff",
              blocks(c, stop, "s-1"), "rc=%r out=%r" % (stop.returncode, tail(stop.stdout)))
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
            c.post_compact("r-1")
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


def case_stop_hook_active_passes():
    """stop_hook_active true passes, so a block cannot loop. Its twin, the same flagged
    state without the flag, must block."""
    c = Case("active")
    try:
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


def main() -> int:
    print("Part 1: SessionEnd pointer and SessionStart reorient (hooks/precompact_handoff.py)")
    case_session_end_clear_writes_pointer()
    case_session_end_other_reason_writes_nothing()
    case_reorient_names_newest_pointer_same_dir()
    case_reorient_ignores_pointer_for_other_dir()
    case_reorient_no_pointer_names_newest_handoff_same_dir()
    case_reorient_none_says_so()
    case_safe_stop_entry_pinned()

    print("Part 2: PostCompact flag, Read clears it, Stop blocks (hooks/reread_check.py)")
    check("reread_check: the module exists", os.path.isfile(READ_CHECK),
          "missing: %s" % READ_CHECK)
    case_post_compact_sets_flag()
    case_read_of_handoff_clears_flag()
    case_read_of_other_file_keeps_flag()
    case_stop_hook_active_passes()
    case_stop_no_flag_passes()

    if FAILED:
        print()
        print("test_handoff_wave2 FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print()
    print("test_handoff_wave2 PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
