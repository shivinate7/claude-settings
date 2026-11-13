"""The one home of the per-agent process record (step agent-owned-processes, ruling own-agent-owned-processes).

A record lists the processes one agent started: `<dir>/<agent_id>.json` = {"agent": id, "procs": [{"pid", "start",
"owner", "kind"}]}. `dir` is $CLAUDE_AGENT_PROCS_DIR, else `<CLAUDE_CONFIG_DIR or ~/.claude>/agent-procs`. `start` is
the process's start ticks (field 22 of /proc/<pid>/stat), so a reused pid never reads as the recorded one. Where the
ticks cannot be read (macOS, Windows) a start is None and the record proves nothing: every reader treats that as "no
record", so those platforms keep the behaviour they had. `kind` is "background" (a marked process the SubagentStop scan
found), "sim-lease" (bin/sim-lease writes it), "office" (the Windows adapter) or "unclear" (the recorded start no
longer matches, or the start cannot be read: reported, never ended).

Three readers use it: janitor/agent_end_reap.py builds the record at SubagentStop and ends only this agent's
matching-start processes; janitor/sweep.py host_child_stops refuses a pid another record also lists, or whose start
differs; hooks/guard_kill.py agent_pid_kill refuses a kill of a pid recorded to another agent or holding another
agent's live marker (`CLAUDE_AGENT_ID`, read by proc_env).

A pid ends only when the agent owns it (its live marker or its Office diff), its start matches, no other agent's
record lists it, and no window of it is visible. A visible window, an unclear owner, a start that differs and a pid
two agents both hold are reported in the record, never ended (`plan_ends`).

Office. COM-started Office has the DcomLaunch service as parent, so no parent check finds it. The adapter lists the
three Office images at SubagentStart (`mark_office_start`) and again at SubagentStop, and the new pids are the agent's
(`office_started`). It exits at once off Windows, and when no Office process runs, and it records nothing when the
start list could not be read, so an unread list never makes the user's own Excel the agent's. Another agent still
open (its record holds `office_before`) at the stop makes every new Office pid shared, so none ends. The Windows
window read (`visible_office_pids`) is unmeasured: a failed read counts every pid as visible.

Cost (rule outcomes-mechanize-rules): zero process starts and zero files written per tool call. This module is not
imported on the tool-call path (hooks/stall_watch.py only writes the marker line). It runs at SubagentStop, at a `kill`
command's guard check, in a sweep's stop list and in a sim-lease take: file reads and one record write each. On
Windows only, SubagentStart and SubagentStop each start one `tasklist` (none when the platform is not Windows).
hooks/test_agent_procs.py pins the tool-call number.

Stdlib only. Every read answers None or an empty list on failure; nothing here raises to a hook.
"""
import csv
import json
import os
import re
import subprocess
import sys

try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper
    _nowindow = subprocess

AGENT_FILE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # an id safe to use as a file name
OFFICE_IMAGES = ("EXCEL.EXE", "POWERPNT.EXE", "WINWORD.EXE")
NEVER_ENDED_KINDS = ("sim-lease", "unclear")  # the lease has its own release; unclear is reported only


def procs_dir() -> str:
    explicit = os.environ.get("CLAUDE_AGENT_PROCS_DIR")
    if explicit:
        return explicit
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(config, "agent-procs")


def record_path(agent):
    if not isinstance(agent, str) or not AGENT_FILE_ID.match(agent):
        return None
    return os.path.join(procs_dir(), agent + ".json")


def start_ticks(pid):
    """Field 22 of /proc/<pid>/stat, or None (a dead pid, a read that failed, any platform without /proc)."""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return int(handle.read().rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError, TypeError):
        return None


def is_running(pid) -> bool:
    """True when `pid` is a live process. A zombie (a stopped child nobody waited on) is not running."""
    try:
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return handle.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError, TypeError):
        pass
    if os.path.isdir("/proc"):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def read_record(agent):
    """The agent's record as a dict with a "procs" list of entry dicts, or None when none is readable."""
    path = record_path(agent)
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    procs = data.get("procs")
    data["procs"] = [e for e in procs if isinstance(e, dict) and isinstance(e.get("pid"), int)] \
        if isinstance(procs, list) else []
    return data


def write_record(agent, record) -> bool:
    """Write the record through a temp file and os.replace. False when it could not."""
    path = record_path(agent)
    if not path:
        return False
    tmp = "%s.%d.tmp" % (path, os.getpid())
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(dict(record, agent=agent), handle, indent=1)
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def add_entry(agent, entry) -> bool:
    """Add ENTRY ({"pid", "start", "owner", "kind"}) to the agent's record, replacing the entry for the same pid."""
    record = read_record(agent) or {"procs": []}
    record["procs"] = [e for e in record["procs"] if e.get("pid") != entry.get("pid")] + [entry]
    return write_record(agent, record)


def all_records():
    """{agent: record} for every readable record in the folder."""
    found = {}
    try:
        names = sorted(os.listdir(procs_dir()))
    except OSError:
        return found
    for name in names:
        if name.endswith(".json") and AGENT_FILE_ID.match(name[:-5]):
            record = read_record(name[:-5])
            if record is not None:
                found[name[:-5]] = record
    return found


def recorded_owners(pid):
    """The agents whose record lists `pid` with the start it has now. Empty when its start cannot be read."""
    current = start_ticks(pid)
    if current is None:
        return []
    return [agent for agent, record in all_records().items()
            if any(e.get("pid") == pid and e.get("start") == current for e in record["procs"])]


def held_by_others(pid, agent):
    """The agents other than AGENT whose record lists `pid` with the start it has now."""
    return [other for other in recorded_owners(pid) if other != agent]


def proven_own(pid, agent) -> bool:
    """False when the record puts `pid` in doubt for AGENT: its entry's start differs from the pid's now (a reused
    pid), or another agent's record lists it too. True otherwise, and True where the start cannot be read."""
    current = start_ticks(pid)
    if current is None:
        return True
    mine = read_record(agent)
    entry = next((e for e in (mine or {}).get("procs", []) if e.get("pid") == pid), None)
    if entry is not None and entry.get("start") != current:
        return False
    return not held_by_others(pid, agent)


def plan_ends(candidates, agent):
    """The pids to end. A candidate is {"pid", "owner", "visible", "start_ok"} (and "shared", "kind" when known). It
    ends only when AGENT owns it, its start matches, no window of it is visible, no other agent holds it, and its
    kind is not one that is reported only."""
    return [c["pid"] for c in candidates
            if c.get("owner") == agent and c.get("start_ok") and not c.get("visible")
            and not c.get("shared") and c.get("kind") not in NEVER_ENDED_KINDS]


def office_lister():
    """{pid: image name} for every process, from one `tasklist` (Windows only; {} elsewhere or when it fails)."""
    if not sys.platform.startswith("win"):
        return {}
    try:
        text = _nowindow.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        raise OSError("tasklist failed")
    table = {}
    for row in csv.reader(text.splitlines()):
        if len(row) >= 2 and row[1].isdigit():
            table[int(row[1])] = row[0]
    return table


def office_snapshot(platform, lister):
    """{pid: image} of the running Office processes, or None off Windows (the lister is never called) and when none
    runs."""
    if not str(platform).startswith("win"):
        return None
    office = {pid: image for pid, image in lister().items() if str(image).upper() in OFFICE_IMAGES}
    return office or None


def office_started(before, after):
    """The Office pids in AFTER that BEFORE does not hold, sorted. Either may be None (no Office process then)."""
    seen = set(before or {})
    return sorted(pid for pid, image in (after or {}).items()
                  if pid not in seen and str(image).upper() in OFFICE_IMAGES)


def mark_office_start(agent, platform=None, lister=None):
    """SubagentStart: store the Office pids running now in the agent's record (`office_before`). Off Windows it
    returns before any read. A list that cannot be read stores nothing, so the stop ends no Office."""
    platform = sys.platform if platform is None else platform
    if not str(platform).startswith("win"):
        return False
    try:
        listing = (lister or office_lister)()
        before = office_snapshot(platform, lambda: listing) or {}
    except Exception:
        return False
    record = read_record(agent) or {"procs": []}
    record["office_before"] = {str(pid): image for pid, image in before.items()}
    return write_record(agent, record)


def visible_office_pids():
    """The pids that own a visible top-level window, or None when the read failed (Windows only, unmeasured)."""
    if not sys.platform.startswith("win"):
        return set()
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        seen = set()
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def each(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                seen.add(pid.value)
            return True

        user32.EnumWindows(callback_type(each), 0)
        return seen
    except Exception:
        return None


def office_candidates(agent, platform=None, lister=None, visible=None):
    """SubagentStop: the Office pids this agent's diff names, as candidates for `plan_ends`. [] when the adapter does
    not apply. The caller drops `office_before` from the record afterwards, so a later agent's stop no longer waits
    on this one."""
    platform = sys.platform if platform is None else platform
    if not str(platform).startswith("win"):
        return []
    record = read_record(agent)
    before = (record or {}).get("office_before")
    if not isinstance(before, dict):
        return []
    try:
        after = office_snapshot(platform, lister or office_lister)
    except Exception:
        return []
    started = office_started({int(pid): image for pid, image in before.items() if str(pid).isdigit()}, after)
    others_open = any(isinstance(other.get("office_before"), dict)
                      for name, other in all_records().items() if name != agent)
    seen = (visible or visible_office_pids)()
    return [{"pid": pid, "owner": agent, "kind": "office", "start_ok": True, "shared": others_open,
             "visible": seen is None or pid in seen} for pid in started]
