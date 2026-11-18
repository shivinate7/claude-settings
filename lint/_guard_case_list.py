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
import tempfile

# The fields that make the payload a case sends to the guard, and the environment it runs in.
KEY_FIELDS = ("tool", "raw", "cwd", "env_path", "session", "config", "transcript", "agent_id", "agent_type",
              "event", "stop_active", "no_root", "env", "guard", "temp", "tool_input")
CLOCK_VALUE = re.compile(r"\b1[5-9]\d{8}(?:\d{3})?(?:\.\d+)?\b")  # epoch seconds or milliseconds, with a fraction
MEMORY_ADDRESS = re.compile(r"0x[0-9a-f]{6,}")  # a repr of an object
LOCAL_PORT = re.compile(r"\b(127\.0\.0\.1|localhost):\d+\b")  # a fake server a section starts on a free port
# The pids after `kill` or `pkill -P`, which a section takes from a process it starts, and a process group as -pid.
# Pid 0 and pid 1 (init) stay, with their minus: a case pins them.
KILL_PIDS = re.compile(r"(\bp?kill(?:\s+(?:-[\w-]*|--))*)((?:\s+-?\d+)+)")
PID = re.compile(r"(-?)(\d+)")


def normalise(text, run_folders):
    """text with each run folder, the system temp folder and the clock values replaced by fixed words.
    run_folders is the run's root folder first, then the folder that holds every run's root."""
    words = list(zip(run_folders, ("<ROOT>", "<TEMP_ROOT>")))
    words.append((tempfile.gettempdir(), "<TMP>"))
    words += [(os.path.realpath(folder), word) for folder, word in words]
    # A backslash spelling of the path too, as the JSON of the payload holds it (doubled) and as a name holds it (single).
    words += [(folder.replace("/", back), word) for folder, word in words for back in ("\\", "\\\\")]
    # The longest folder first: the run's root sits inside the folder of all roots, which sits inside the temp folder.
    for folder, word in sorted(set(words), key=lambda pair: -len(pair[0])):
        text = text.replace(folder, word)
    for pattern, word in ((CLOCK_VALUE, "<CLOCK>"), (MEMORY_ADDRESS, "<ADDR>")):
        text = pattern.sub(word, text)
    text = LOCAL_PORT.sub(lambda m: m.group(1) + ":<PORT>", text)
    return KILL_PIDS.sub(lambda m: m.group(1) + PID.sub(
        lambda n: n.group(0) if int(n.group(2)) < 2 else n.group(1) + "<PID>", m.group(2)), text)


def case_key(case, run_folders):
    body = json.dumps({field: case.get(field) for field in KEY_FIELDS}, sort_keys=True, default=repr)
    return hashlib.sha256(normalise(body, run_folders).encode("utf-8")).hexdigest()[:16]


def write_listing(path, cases, run_folders):
    """Write one row {name, tool, expected, key} for each case to path, as JSON. A name that holds a run value reads
    normalised too, so it is the same in every run. -> the row count."""
    rows = [{"name": normalise(c["name"], run_folders), "tool": c["tool"], "expected": c["expected"], "key": case_key(c, run_folders)}
            for c in cases]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=0)
    return len(rows)
