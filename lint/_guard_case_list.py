"""The one home of how a guard test case is listed and keyed.

hooks/test_guard.py writes the listing under GUARD_LIST, and lint/check_guard_cases_from_base.py compares the
listing of a base tree with the listing of the head tree. A case's key is a hash of its payload, with the values
that change from run to run replaced by a fixed word. So one tree lists the same keys in every run, and a case that
keeps its payload keeps its key when its name, verdict or rule changes. The verdict and the rule are not in the key.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time

# The fields that make the payload a case sends to the guard, and the environment it runs in.
KEY_FIELDS = ("tool", "raw", "cwd", "env_path", "session", "config", "transcript", "agent_id", "agent_type",
              "event", "stop_active", "no_root", "env", "guard", "temp", "tool_input")
CLOCK_VALUE = re.compile(r"\b1[5-9]\d{8}(?:\d{3})?(?:\.\d+)?\b")  # epoch seconds or milliseconds, with a fraction
CLOCK_WINDOW = 86400  # seconds: only a value this near the run's clock varies from run to run, a fixed epoch in a case does not
MEMORY_ADDRESS = re.compile(r"0x[0-9a-f]{6,}")  # a repr of an object
LOCAL_PORT = re.compile(r"\b(127\.0\.0\.1|localhost):\d+\b")  # a fake server a section starts on a free port
# The pids after `kill` or `pkill -P`, which a section takes from a process it starts, and a process group as -pid.
# Pid 0 and pid 1 (init) stay, with their minus: a case pins them. Another pid reads as its class (own, live or gone),
# since a guard allows a pid the session started and refuses one it did not, so two such cases are not one payload.
KILL_PIDS = re.compile(r"(\bp?kill(?:\s+(?:-[sn]\s+\w+|-[\w-]*|--))*)((?:\s+-?\d+)+)")
PID = re.compile(r"(-?)(\d+)")


def _parents():
    """{pid: parent pid} of the running processes, or None when `ps` cannot be read (Windows has none)."""
    if os.name == "nt":
        return None
    try:
        done = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True, timeout=30)
        if done.returncode == 0:
            return {int(a): int(b) for a, b in (ln.split() for ln in done.stdout.splitlines() if ln.strip())}
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


_TABLE = [None]  # the last read of the process table
_FROZEN = [False]  # True while one listing runs: the table is read once for it, and not again for a pid it lacks


def pid_class(pid):
    """own: a descendant of this process (a process the section started). live: another running process. gone: no such
    process. any: the class cannot be read here (no `ps`, or Windows), so the pid reads as one class. The table is read
    again when it lacks the pid, since a section starts its processes while it loads. One listing reads it once
    (write_listing), so a pid that is gone costs no `ps`."""
    table = _TABLE[0]
    if not _FROZEN[0] and (table is None or pid not in table):
        table = _TABLE[0] = _parents()
    if table is None:
        return "any"
    if pid not in table:
        return "gone"
    me, seen = os.getpid(), set()
    while pid in table and pid not in seen:
        if pid == me:
            return "own"
        seen.add(pid)
        pid = table[pid]
    return "live"


def _clock_word(match):
    value = float(match.group(0))
    seconds = value / 1000 if value >= 1e11 else value
    return "<CLOCK>" if abs(seconds - time.time()) < CLOCK_WINDOW else match.group(0)


_WORDS = {}  # (run_folders, temp folder) -> the replacement pairs, longest folder first


def _folder_words(run_folders):
    """The (folder, word) pairs normalise replaces. Each realpath is read once for a run, not once per call."""
    key = (tuple(run_folders), tempfile.gettempdir())
    if key not in _WORDS:
        words = list(zip(run_folders, ("<ROOT>", "<TEMP_ROOT>")))
        words.append((key[1], "<TMP>"))
        words += [(os.path.realpath(folder), word) for folder, word in words]
        # A backslash spelling of the path too, as the JSON of the payload holds it (doubled) and as a name holds it (single).
        words += [(folder.replace("/", back), word) for folder, word in words for back in ("\\", "\\\\")]
        # The longest folder first: the run's root sits inside the folder of all roots, which sits inside the temp folder.
        _WORDS[key] = sorted(set(words), key=lambda pair: -len(pair[0]))
    return _WORDS[key]


def normalise(text, run_folders):
    """text with each run folder, the system temp folder and the clock values replaced by fixed words.
    run_folders is the run's root folder first, then the folder that holds every run's root."""
    for folder, word in _folder_words(run_folders):
        text = text.replace(folder, word)
    text = CLOCK_VALUE.sub(_clock_word, text)
    text = MEMORY_ADDRESS.sub("<ADDR>", text)
    text = LOCAL_PORT.sub(lambda m: m.group(1) + ":<PORT>", text)
    return KILL_PIDS.sub(lambda m: m.group(1) + PID.sub(
        lambda n: n.group(0) if int(n.group(2)) < 2 else "%s<PID:%s>" % (n.group(1), pid_class(int(n.group(2)))),
        m.group(2)), text)


def case_key(case, run_folders):
    body = json.dumps({field: case.get(field) for field in KEY_FIELDS}, sort_keys=True, default=repr)
    return hashlib.sha256(normalise(body, run_folders).encode("utf-8")).hexdigest()[:16]


def write_listing(path, cases, run_folders):
    """Write one row {name, tool, expected, key} for each case to path, as JSON. A name that holds a run value reads
    normalised too, so it is the same in every run. A key is never shared by two verdicts. -> the row count."""
    _TABLE[0], _FROZEN[0] = _parents(), True
    try:
        keys = [case_key(c, run_folders) for c in cases]
    finally:
        _FROZEN[0] = False
    # One key must not stand for two verdicts: a payload that two cases hold with another verdict each (a case whose
    # state is no part of its payload, such as a process a section starts) gets its verdict in the key. Cases that
    # share a payload and a verdict share a key, which the comparison reads as one.
    verdicts = {}
    for c, key in zip(cases, keys):
        verdicts.setdefault(key, set()).add(c["expected"])
    keys = [key + "-" + c["expected"] if len(verdicts[key]) > 1 else key for c, key in zip(cases, keys)]
    rows = [{"name": normalise(c["name"], run_folders), "tool": c["tool"], "expected": c["expected"], "key": key}
            for c, key in zip(cases, keys)]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=0)
    return len(rows)
