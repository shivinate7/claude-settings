# section 39497
FAMILY = "load-brake"
FAMILIES["load-brake"] = "the machine-load brake: busy and full on start calls, full on an agent's or a lane session's shell or file write (a lane session's own record tags cs-build:lane), the reader seam, no child process, no per-call read, no CPU read or wait, the cloud skip (CLAUDE_CODE_REMOTE=true reads nothing), the neutral load every other family's lane call meets"
# The machine-load brake. On a start call only (Agent, Task, Workflow, mcp__ccd_session__start_session)
# the guard reads the machine's load once: memory in use as a share of this machine's memory, and disk free on
# the home drive in GB against the drive's size. CPU is not read (decision machine-load-brake): a 200 ms CPU
# sample is noise, and memory and disk are what stall a machine. It counts no claude process and no running
# lane. A GB here is 2**30 bytes, as df -k and PowerShell 1GB give. The levels:
#   busy  memory over 85%, or disk free under the smaller of 10% of the disk and 15 GB. An Agent or Task call
#         passes busy only when run_in_background is absent or exactly false. Any other value (true, a string,
#         null, a number) is refused. Any Workflow is refused. The refusal says to wait for the load to drop, or
#         to make this an Agent call that leaves run_in_background out or sets it false. A disk reading
#         names free disk space instead.
#   full  memory over 95%, or disk free under the smaller of 5% of the disk and 5 GB. Every lane call is refused,
#         an Agent or Task call too.
# The refusal names the reading that tripped it, and never names the CPU. A read that fails, or a reading left
# unread, counts as normal. An agent's own shell or file write reads once and is refused at full only
# (A RUNNING LANE, below). Every other tool reads no load. The read starts no child process, writes no file,
# and sleeps for no wait.
# Not pinned: start_session at busy.
#
# THE SEAM. The cases drive the guard in a probe process that imports guard.py (GUARD_UNDER_TEST
# honored), patches the function below, and calls main() with the real stdin payload. The
# builder must honor this contract:
#   read_load()    a function in guard.py, or in a guard_*.py module that guard.py imports. It takes
#                  no argument and does every OS read. It returns a dict with the keys memory_pct
#                  (percent of physical memory IN USE), disk_free_gb and disk_total_gb (GB FREE and GB
#                  TOTAL on the home drive, never clamped to 0-100). It returns no cpu_pct key. A
#                  missing key or a None is an unread reading, which counts as normal. read_load may
#                  raise: every reading then counts as normal. It returns no claude_procs, and a
#                  claude_procs key in a reading changes nothing. A cpu_pct key in a stub reading changes
#                  nothing either: a change that still reads the CPU refuses on those stubs and fails here.
#                  The OS sources, all faked by THE FAKE HOST: darwin reads memory through sysctlbyname;
#                  linux reads memory unread; both read the disk through shutil.disk_usage on the home
#                  folder. Neither reads the CPU ticks, the load average, or waits.
# The judge must call it by its bare name, so the probe's patch (set on every guard module that
# holds the name) is the function that runs. A function the probe cannot replace fails every case.
# The reading of a call is one read_load() per start call, and none on any other call.
# THE FAKE HOST. A case with a `fake` spec runs the real read_load under fakes, in the probe, and judges the
# call on what it read. The fake sets sys.platform, ctypes.CDLL and ctypes.cdll, os.getloadavg (the load
# average, which no reading uses), shutil.disk_usage, and the /proc/stat file (builtins.open and io.open).
# Each source is restored before the judge runs. Tick samples: a base sample, then one that adds the case's
# busy share, so a reader that reads the ticks would see that share. `tick_reads` counts each read of them.
# THE WAITS. Every time.sleep the probe makes is counted in `sleeps`, and nothing waits. On Windows the probe
# also counts each GetSystemTimes call (`GetSystemTimes`). A judge with no `reading` and no `fake` runs the
# real reader on this host (the live judge), so its waits and tick calls are the lane call's own.
# A fake case must start no child process; the probe counts them and the case checks the count.
# The probe also counts the child processes a run starts (subprocess.Popen, os.system, os.spawn*,
# os.posix_spawn*, os.startfile), which is the harness's process seam for the "zero children" cases.
LB_PROBE = r"""
import builtins, importlib.machinery, importlib.util, io, json, os, subprocess, sys, time, types
from unittest import mock
guard_path, side, spec = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
children = []
sleeps = []
time.sleep = lambda seconds: sleeps.append(seconds)   # counted, never waited on
real_popen = subprocess.Popen
in_popen = [0]


# Python 3.13+ may start a Popen child through os.posix_spawn, so the os-level counters skip calls made
# inside a counted Popen: one child counts once.
class CountingPopen(real_popen):
    def __init__(self, *args, **kwargs):
        children.append(str(args[0] if args else kwargs.get("args"))[:80])
        in_popen[0] += 1
        try:
            super().__init__(*args, **kwargs)
        finally:
            in_popen[0] -= 1


subprocess.Popen = CountingPopen


def counted(name, real):
    def call(*args, **kwargs):
        if not in_popen[0]:
            children.append(name)
        return real(*args, **kwargs)
    return call


for name in ("system", "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
             "startfile"):
    if hasattr(os, name):
        setattr(os, name, counted(name, getattr(os, name)))
# The network seams are counted only for a case that asks (spec "network"). A call through one is refused here,
# so it never reaches a socket. A case with no network key leaves them as they are.
network = []


def refused_network(name):
    def call(*args, **kwargs):
        network.append(name)
        raise OSError("%s is refused in this probe" % name)
    return call


if spec.get("network"):
    import socket
    import urllib.request
    urllib.request.urlopen = refused_network("urlopen")
    socket.create_connection = refused_network("create_connection")
    socket.socket.connect = refused_network("socket connect")


def listing():
    return sorted(os.path.join(folder, n) for top in spec.get("watch", [])
                  for folder, _, names in os.walk(top) for n in names)


GB = 2 ** 30


# Run `read` with every OS source faked, then restore each one: the platform, the Mach ticks and
# memory level (darwin), the load average, the disk and /proc/stat. The waits stay counted, not waited on.
def under_fake(read, fake):
    real_open = open
    busy = int(fake["busy"])
    samples = [(1000, 0, 9000, 0), (1000 + busy * 10, 0, 9000 + (100 - busy) * 10, 0)]   # (user, system, idle, nice)
    calls = {"ticks": 0, "stat": 0}

    def sample(counter):
        # A read past 100 raises, so a loop with no bound fails its case instead of hanging the run.
        calls[counter] += 1
        if calls[counter] > 100:
            raise RuntimeError("the fake host gave more than 100 tick reads")
        return samples[min(calls[counter] - 1, len(samples) - 1)]

    def host_statistics(host, flavor, info, count):
        user, system, idle, nice = sample("ticks")
        target = getattr(info, "_obj", info)
        for index, value in enumerate((user, system, idle, nice)):
            target[index] = value
        return 0

    def sysctlbyname(name, oldp, oldlenp, newp, newlen):
        getattr(oldp, "_obj", oldp).value = 100 - int(fake["memory"])
        return 0

    def cdll(*args, **kwargs):
        return types.SimpleNamespace(mach_host_self=lambda: 1, host_statistics=host_statistics,
                                     sysctlbyname=sysctlbyname)

    def stat_open(file, *args, **kwargs):
        if str(file) == "/proc/stat":
            user, system, idle, nice = sample("stat")
            return io.StringIO("cpu  %d %d %d %d 0 0 0 0 0 0\n" % (user, nice, system, idle))
        return real_open(file, *args, **kwargs)

    total, free = int(fake["disk_total_gb"] * GB), int(fake["disk_free_gb"] * GB)
    usage = types.SimpleNamespace(total=total, used=total - free, free=free)
    load = fake["load"]
    with mock.patch.object(sys, "platform", fake["platform"]), \
            mock.patch("ctypes.CDLL", cdll), \
            mock.patch("ctypes.cdll", types.SimpleNamespace(LoadLibrary=cdll)), \
            mock.patch("os.getloadavg", lambda: (load, load, load), create=True), \
            mock.patch("shutil.disk_usage", lambda path: usage), \
            mock.patch("builtins.open", stat_open), mock.patch("io.open", stat_open):
        try:
            return read()
        finally:
            out["tick_reads"] = calls["ticks"] + calls["stat"]


out = {"reads": 0}
if sys.platform == "win32":
    # The Windows CPU tick read is GetSystemTimes: count each call the reader makes, then make the real one.
    import ctypes
    kernel = ctypes.windll.kernel32
    real_times = kernel.GetSystemTimes

    def counted_times(*args):
        out["GetSystemTimes"] = out.get("GetSystemTimes", 0) + 1
        return real_times(*args)
    kernel.GetSystemTimes = counted_times
try:
    # The loader is named, so a GUARD_UNDER_TEST copy with a .bak suffix loads like guard.py does.
    loader = importlib.util.spec_from_file_location(
        "guard_under_test", guard_path,
        loader=importlib.machinery.SourceFileLoader("guard_under_test", guard_path))
    g = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(g)
    mods = [g] + [m for n, m in list(sys.modules.items()) if n.startswith("guard_") and m is not None]
    holders = [m for m in mods if hasattr(m, "read_load")]
    out["had_reader"] = bool(holders)

    def put(name, fn):
        for m in mods:
            if m is g or hasattr(m, name):
                setattr(m, name, fn)

    before = listing()
    if spec.get("spy"):
        # The spy counts each open of the transcript path, through builtins.open and io.open, the two names a guard
        # reads a file by. The path is compared by its real path, so a link to the same file counts too.
        real_open, target = open, os.path.realpath(spec["spy"])

        def spy_open(file, *args, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)) and os.path.realpath(os.fsdecode(file)) == target:
                out["opened"] = out.get("opened", 0) + 1
            return real_open(file, *args, **kwargs)
        builtins.open = spy_open
        io.open = spy_open
    if spec["mode"] == "selfcheck_child":
        subprocess.run([sys.executable, "-c", "pass"])
    elif spec["mode"] == "selfcheck_open":
        open(spec["spy"], encoding="utf-8").close()
    elif spec["mode"] == "reader":
        if not holders:
            out["missing"] = True
        else:
            try:
                if "fake" in spec:
                    out["reading"] = under_fake(holders[0].read_load, spec["fake"])
                else:
                    out["reading"] = holders[0].read_load()
            except Exception as exc:
                out["raised"] = type(exc).__name__ + ": " + str(exc)[:80]
    else:
        if "fake" in spec and holders:
            spec["reading"] = under_fake(holders[0].read_load, spec["fake"])
        if "reading" in spec:
            def read_load():
                out["reads"] += 1
                if spec["reading"] == "raise":
                    raise OSError("fake read failure")
                return dict(spec["reading"])
            put("read_load", read_load)
        if spec.get("patch_floor") == "deny":
            g.floor_hit = lambda tool, tool_input: "haiku"
        elif spec.get("patch_floor") == "read":
            g.floor_hit = lambda tool, tool_input: g.read_load() and ""
        try:
            if spec["mode"] == "hit":
                # The brake's two functions, called direct on the call's own payload (the probe's stdin), so a
                # case reads each pair they return, not only the decision.
                body = json.loads(sys.stdin.read())
                out["hit"] = list(g.load_hit(body.get("tool_name"), body.get("tool_input")))
                # A guard with no running_agent_hit records None, which the check reports as a missing name.
                running_hit = getattr(g, "running_agent_hit", None)
                out["running"] = list(running_hit(body, body.get("tool_name"))) if running_hit else None
            elif spec["mode"] == "lane":
                # lane_session_hit, called direct on the call's payload. A guard with no such name leaves the pair None.
                body = json.loads(sys.stdin.read())
                direct = getattr(g, "lane_session_hit", None)
                out["lane"] = None if direct is None else list(direct(body, body.get("tool_name")))
            else:
                g.main()
        except SystemExit:
            pass
    out["files"] = [p for p in listing() if p not in before]
except Exception as exc:
    out["probe_error"] = type(exc).__name__ + ": " + str(exc)[:200]
out["sleeps"] = len(sleeps)
out["children"] = children
out["network"] = network
with open(side, "w", encoding="utf-8") as handle:
    json.dump(out, handle, default=str)
if out.get("probe_error"):
    sys.exit("probe: " + out["probe_error"])   # decide() reads a non-zero exit as an error, never an allow
"""

LB_DIR = os.path.join(ROOT, "loadbrake")
LB_TOOLS = (("Agent", "Agent"), ("Task", "Task"), ("Workflow", "Workflow"),
            ("start_session", "mcp__ccd_session__start_session"))
LB_LANE_INPUT = {
    "Agent": {"description": "d", "prompt": "x", "model": "sonnet"},
    "Task": {"description": "d", "prompt": "x", "model": "sonnet"},
    "Workflow": {"script": _flow("sonnet")},
    "mcp__ccd_session__start_session": {"initiation": "user_asked", "prompt": "x", "model": "sonnet"},
}
LB_NORMAL = {"memory_pct": 40.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0}
LB_ALL_HIGH = {"memory_pct": 99.0, "disk_free_gb": 1.0, "disk_total_gb": 926.0}
# The tools that take run_in_background. At busy, only an absent or exactly false value passes.
LB_SPAWNS = (("Agent", "Agent"), ("Task", "Task"))
LB_BG = ((True, "run_in_background true"), (None, "run_in_background left out"),
         (False, "run_in_background false"))
LB_REMEDY = re.compile(re.escape("Wait until the load drops, or make this an Agent call that leaves "
                                 "run_in_background out or sets it false."), re.I)
LB_FREE_DISK = re.compile(r"free disk space", re.I)   # the disk reading's remedy
LB_FOREGROUND = re.compile(r"foreground", re.I)   # a busy refusal of an Agent or Task call never says this
LB_BUSY_CITE = re.compile(r"starts no new lane or agent")   # the decision cite of a busy or full refusal
LB_NO_NEW = re.compile(r"No new lane or agent starts")   # the first sentence of a full refusal
LB_RUN_CITE = re.compile(r"stops a running agent")   # the decision cite of a running agent's full refusal


def lb_gb(free, total):
    """A disk reading as a refusal words it: free GB to one place, total GB to a whole number."""
    return re.compile(re.escape("disk %.1f GB free of %.0f GB" % (free, total)))


def lb_fake(platform, busy=10.0, load=0.5, memory=40, disk_total=926.0, disk_free=500.0):
    """A fake host for THE FAKE HOST: `busy` the CPU share the tick samples would show, `load` the 1-minute
    load average, `memory` the percent in use, and the disk in GB. The defaults are a quiet host with room on
    the disk."""
    return {"platform": platform, "busy": busy, "load": load, "memory": memory,
            "disk_total_gb": disk_total, "disk_free_gb": disk_free}


def lb_reading(**changes):
    """A normal reading with the named readings changed."""
    return dict(LB_NORMAL, **changes)


def lb_lane_input(tool, background=None):
    """The input of a start call. `background` is run_in_background: True, False, or None to
    leave it out. Only Agent and Task take it."""
    given = dict(LB_LANE_INPUT[tool])
    if background is not None and tool in dict(LB_SPAWNS).values():
        given["run_in_background"] = background
    return given


def lb_spawn_input(tool, value):
    """A spawn call whose run_in_background is `value` exactly as given: a string, null or a number included."""
    return dict(LB_LANE_INPUT[tool], run_in_background=value)


LB_MISSING = "missing"   # a transcript sentinel: the payload names a path that is not there
LB_FOLDER = "folder"     # a transcript sentinel: the payload names a folder, so the guard's open() fails


def lb_run(tool, spec, tool_input=None, event=None, agent=None, remote=None, own_env=None, transcript=None,
           spy=False):
    """One guard run in the probe. Returns (decision, reason, side): the decision the run printed,
    and what the probe saw (reads, children, files, had_reader, reading, opened, lane...). `agent` is the payload's
    agent_id, so the call is an agent's own; None leaves it out (the orchestrator's call). `remote` is the
    value of CLAUDE_CODE_REMOTE; None leaves it unset. The runner's own value never reaches a case, so
    every case judges a local machine unless it names `remote`. `own_env` is a dict of env values that name the
    session's own id (CLAUDE_CODE_REMOTE_SESSION_ID); None leaves it unset, as the runner's value is never kept.
    `transcript` is the payload's transcript_path: a list of JSONL lines written to the run folder, or LB_MISSING or
    LB_FOLDER. `spy` counts the opens of that transcript path, into side["opened"]."""
    os.makedirs(LB_DIR, exist_ok=True)
    run = tempfile.mkdtemp(dir=LB_DIR)
    try:
        dirs = {name: os.path.join(run, name) for name in ("cfg", "tmp", "side", "cwd")}
        for path in dirs.values():
            os.makedirs(path)
        side_file = os.path.join(dirs["side"], "probe.json")
        spec = dict(spec, watch=[dirs["cfg"], dirs["tmp"]])
        if event:
            body = {"hook_event_name": event}
        else:
            given = LB_LANE_INPUT[tool] if tool_input is None else tool_input
            body = {"tool_name": tool, "tool_input": {
                k: v.replace("{cwd}", dirs["cwd"]) if isinstance(v, str) else v
                for k, v in given.items()}}
        body["cwd"] = dirs["cwd"]
        body["session_id"] = "lb-" + os.path.basename(run)
        if agent is not None:
            body["agent_id"], body["agent_type"] = agent, "general-purpose"
        if transcript is not None:
            # The transcript sits in the run folder, outside cfg and tmp, so the file listing never counts it.
            if transcript == LB_FOLDER:
                path = os.path.join(run, "folder.jsonl")
                os.makedirs(path)
            elif transcript == LB_MISSING:
                path = os.path.join(run, "missing.jsonl")
            else:
                path = os.path.join(run, "transcript.jsonl")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("".join(line + "\n" for line in transcript))
            body["transcript_path"] = path
            if spy:
                spec = dict(spec, spy=path)
        env = dict(os.environ)
        for name in ("TMPDIR", "TEMP", "TMP"):
            env[name] = dirs["tmp"]
        env["CLAUDE_CONFIG_DIR"] = dirs["cfg"]
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        env.pop("CLAUDE_CODE_REMOTE", None)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)   # this container sets one: only a case that names it has one
        if own_env:
            env.update(own_env)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())   # the suite stands in for `claude`
        done = subprocess.run([sys.executable, "-c", LB_PROBE, GUARD, side_file, json.dumps(spec)],
                              input=json.dumps(body), capture_output=True, text=True, env=env,
                              timeout=120)
        try:
            with open(side_file, "r", encoding="utf-8") as handle:
                side = json.load(handle)
        except Exception:
            return "error", "the probe wrote nothing: " + done.stderr.strip()[-160:], {}
        if side.get("probe_error"):
            return "error", "the probe failed: " + side["probe_error"], side
        decision, reason = read_decision(done.stdout)
        return decision, reason, side
    finally:
        shutil.rmtree(run, ignore_errors=True)


def lb_names(word, *numbers, percent=True):
    """Patterns a refusal's reason must match to name a reading: the word, and one of the numbers
    (a reading spelled whole, rounded or to one place) followed by % or the word percent."""
    tail = r"\s*(?:%|percent)" if percent else ""
    return (re.compile(word, re.I), re.compile(
        r"(?<![\d.])(?:%s)(?!\d)(?!\.\d)%s" %("|".join(re.escape(n) for n in numbers), tail)))


def lb_decision_check(tool, reading, want, names=(), background=None, tool_input=None, reads=1, lacks=(),
                      fake=None, agent=None, remote=None, own_env=None, transcript=None, spy=False):
    """A start call under a forced reading, or under THE FAKE HOST when `fake` is given (then `reading`
    is unused and the real read_load runs). `background` is the call's run_in_background: True, False, or
    None to leave it out. `tool_input` replaces the whole input. `remote` is CLAUDE_CODE_REMOTE (see lb_run),
    and `own_env`, `transcript` and `spy` are lb_run's."""
    def check():
        given = lb_lane_input(tool, background) if tool_input is None else tool_input
        spec = {"mode": "judge", "fake": fake} if fake else {"mode": "judge", "reading": reading}
        got, reason, side = lb_run(tool, spec, given, agent=agent, remote=remote, own_env=own_env,
                                   transcript=transcript, spy=spy)
        if got == "error":
            return False, reason
        called = side.get("reads")
        if fake and side["children"]:
            return False, "%d child process(es) started under the fake host: %s" % (
                len(side["children"]), side["children"][:3])
        if got != want:
            return False, "%s, want %s (the reader ran %s times): %s" % (got, want, called, reason[:80])
        if reads is not None and called != reads:
            return False, "%s as wanted, but the reader ran %s times, want %d" % (got, called, reads)
        if got == "allow" and side["files"]:
            return False, "an allowed lane call wrote %d file(s)" % len(side["files"])
        for pattern in names:
            if not pattern.search(reason):
                return False, "the reason does not name the reading (%s): %s" % (
                    pattern.pattern[:30], reason[:100])
        for pattern in lacks:
            if pattern.search(reason):
                return False, "the reason matches %r, which it must not: %s" % (pattern.pattern[:30], reason[:100])
        return True, "%s, the reader ran %d time" % (got, called)
    return check


def lb_no_read_check(tool, tool_input=None, event=None, agent=None, remote=None):
    """A call that reads no load under the worst reading: one that is not a lane start, or a lane start in a
    cloud session (`remote` "true"), where the brake is skipped and the reader is never called."""
    def check():
        got, reason, side = lb_run(tool, {"mode": "judge", "reading": LB_ALL_HIGH}, tool_input, event, agent,
                                   remote=remote)
        if got == "error":
            return False, reason
        if got != "allow":
            return False, "%s, want allow: %s" % (got, reason[:90])
        if side.get("reads"):
            return False, "the call read the load (%s read_load)" % side.get("reads")
        return True, "allow, no read"
    return check


def lb_real_children_check(tool, background=None):
    """A start call with the real reader starts no child process, whatever the machine reads
    and whatever the call is then judged."""
    def check():
        got, reason, side = lb_run(tool, {"mode": "judge"}, lb_lane_input(tool, background))
        if got == "error":
            return False, reason
        if not side.get("had_reader"):
            return False, "the guard has no read_load, so no real reading was taken"
        if side["children"]:
            return False, "%d child process(es) started: %s" % (len(side["children"]), side["children"][:3])
        return True, "%s, no child process" % got
    return check


def lb_reader(spec_check):
    """A check on the real read_load, called alone. `spec_check(side)` returns (ok, note)."""
    def check():
        got, reason, side = lb_run(None, {"mode": "reader"}, tool_input={})
        if got == "error":
            return False, reason
        if side.get("missing"):
            return False, "no read_load function in guard.py or a guard_*.py module"
        return spec_check(side)
    return check


def lb_reader_fake(fake, spec_check, side_check=False):
    """The real read_load under THE FAKE HOST, called alone. `spec_check(reading)` returns (ok, note), or
    `spec_check(side)` when side_check is set, for the probe's own counts. The read must start no child
    process and write no file, and must not raise."""
    def check():
        got, reason, side = lb_run(None, {"mode": "reader", "fake": fake}, tool_input={})
        if got == "error":
            return False, reason
        if side.get("missing"):
            return False, "no read_load function in guard.py or a guard_*.py module"
        if side.get("raised"):
            return False, "read_load raised under the fake host: %s" % side["raised"]
        if side["children"]:
            return False, "read_load started %d child process(es): %s" % (len(side["children"]), side["children"][:3])
        if side["files"]:
            return False, "read_load wrote %d file(s): %s" % (len(side["files"]), side["files"][:2])
        if side_check:
            return spec_check(side)
        return spec_check(side.get("reading") or {})
    return check


def lb_gb_unclamped(reading):
    """A 926 GB disk with 119 GB free reads disk_total_gb 926 and disk_free_gb 119, not a value clamped to 100."""
    total, free = reading.get("disk_total_gb"), reading.get("disk_free_gb")
    if total is None or free is None:
        return False, "read_load left disk_free_gb or disk_total_gb unset: %r" % (reading,)
    ok = abs(total - 926.0) < 0.01 and abs(free - 119.0) < 0.01
    return ok, "disk_free_gb %s, disk_total_gb %s, want 119 and 926" % (free, total)


def lb_reader_children(side):
    if side["children"]:
        return False, "read_load started %d child process(es): %s" % (len(side["children"]), side["children"][:3])
    return True, "no child process"


def lb_reader_files(side):
    if side["files"]:
        return False, "read_load wrote %d file(s): %s" % (len(side["files"]), side["files"][:2])
    return True, "no file written"


def lb_reader_shape(side):
    supported = sys.platform in ("win32", "darwin")
    if side.get("raised"):
        if supported:
            return False, "exception raised in read_load on %s: %s" % (sys.platform, side["raised"])
        return True, "read_load raised on %s, which counts as normal" % sys.platform
    reading = side.get("reading")
    if not isinstance(reading, dict):
        return False, "read_load returned %r, want a dict" % (reading,)
    if "claude_procs" in reading:
        return False, "read_load still returns claude_procs, the process count the owner dropped"
    if "cpu_pct" in reading:
        return False, "read_load still returns cpu_pct %r, the CPU reading the owner dropped" % (reading["cpu_pct"],)
    for key in ("memory_pct",):
        value = reading.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            return False, "%s is %r, want a number in range" % (key, value)
    for key in ("disk_free_gb", "disk_total_gb"):
        value = reading.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return False, "%s is %r, want a number of GB" % (key, value)
    if supported:
        need = ("memory_pct", "disk_free_gb", "disk_total_gb")
        unread = [key for key in need if reading.get(key) is None]
        if unread:
            return False, "read_load left %s unread on %s" % (", ".join(unread), sys.platform)
        if not (reading["memory_pct"] > 0 and reading["disk_free_gb"] > 0):
            return False, "memory_pct and disk_free_gb read 0: %r" % (reading,)
        if reading["disk_free_gb"] > reading["disk_total_gb"]:
            return False, "disk_free_gb %r is over disk_total_gb %r" % (
                reading["disk_free_gb"], reading["disk_total_gb"])
    return True, "%s" % {k: reading[k] for k in sorted(reading)}


def lb_probe_child_check():
    got, reason, side = lb_run(None, {"mode": "selfcheck_child"}, tool_input={})
    if got == "error":
        return False, reason
    return (len(side["children"]) == 1,
            "the probe counted %d child(ren), want 1" % len(side["children"]))


def lb_probe_patch_check():
    got, reason, side = lb_run("Agent", {"mode": "judge", "patch_floor": "deny"})
    if got == "error":
        return False, reason
    return (got == "deny" and "floor" in reason,
            "a patched floor_hit gave %s: %s, want a floor deny" % (got, reason[:60]))


def lb_probe_reads_check():
    # A Bash call, so that the brake's own read of a lane call does not add to the count.
    got, reason, side = lb_run("Bash", {"mode": "judge", "reading": LB_NORMAL, "patch_floor": "read"},
                               {"command": "echo hi"})
    if got == "error":
        return False, reason
    return (got == "allow" and side["reads"] == 1 and not side["files"],
            "a patched read_load called once was counted %s times, the call was %s, %d file(s) written" % (
                side["reads"], got, len(side["files"])))


# A stand-in guard whose own reader reads busy. It denies on a busy reading and allows otherwise.
LB_STAND_IN = '''import json, sys


def read_load():
    return {"memory_pct": 99.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0}


def main():
    sys.stdin.read()
    busy = read_load()["memory_pct"] > 90
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
          "permissionDecision": "deny" if busy else "allow", "permissionDecisionReason": "host busy"}}))


if __name__ == "__main__":
    main()
'''


def lb_neutral_default_check():
    """decide() gives a start call a neutral load unless the case names one (`load`), so a case about
    another rule never meets the host's load. A call that starts no lane runs the guard file itself."""
    global GUARD
    folder = os.path.join(ROOT, "neutral-load")
    os.makedirs(folder, exist_ok=True)
    stand_in = os.path.join(folder, "guard.py")
    with open(stand_in, "w", encoding="utf-8") as handle:
        handle.write(LB_STAND_IN)

    def judged(tool, **more):
        given = {"prompt": "x"} if tool == "Agent" else {"command": "echo hi"}
        return decide(dict({"raw": None, "tool": tool, "cwd": folder, "session": None, "env_path": None,
                            "config": None, "tool_input": given}, **more))[0]

    real, GUARD = GUARD, stand_in
    try:
        got = (judged("Agent"), judged("Agent", load=lb_reading(memory_pct=99.0)), judged("Bash"))
    finally:
        GUARD = real
    want = ("allow", "deny", "deny")
    return got == want, "a lane call, a lane call named busy, a Bash call: %s, want %s" % (got, want)


LB_CHECKS = []   # the checks that reach the real reader: the Windows slice runs these too


def lb_add(label, check, real=False):
    LOG_CHECKS_EXTRA.append(("load-brake: " + label, check))
    FIXTURELESS_CHECKS.add(check)
    if real:
        LB_CHECKS.append(check)


lb_add("probe control: a child process the probe starts is counted", lb_probe_child_check)
lb_add("probe control: a patch on a guard function reaches the judge", lb_probe_patch_check)
lb_add("probe control: a call to the patched read_load is counted", lb_probe_reads_check)
lb_add("neutral default: a lane call in another family's case meets a neutral load, not the host's",
       lb_neutral_default_check)

LB_MEM_BUSY = lb_names("memory", "91.7", "91", "92")
LB_MEM_FULL = lb_names("memory", "97.2", "97")
LB_MEM90 = lb_names("memory", "90.0", "90")
LB_CPU_WORD = re.compile(r"cpu", re.I)   # a refusal that names the CPU at all

# Agent and Task: every way a call says run_in_background, at normal, busy and full. At busy only a value
# other than absent or false is refused.
for _short, _tool in LB_SPAWNS:
    for _bg, _say in LB_BG:
        lb_add("%s, normal reading, %s: allowed" % (_short, _say),
               lb_decision_check(_tool, LB_NORMAL, "allow", background=_bg))
        if _bg is True:
            lb_add("%s, memory 91.7%%, %s: busy, refused, names the reading, gives the wait or Agent-call remedy"
                   % (_short, _say),
                   lb_decision_check(_tool, lb_reading(memory_pct=91.7), "deny",
                                     LB_MEM_BUSY + (LB_REMEDY, LB_BUSY_CITE), background=_bg,
                                     lacks=(LB_FOREGROUND,)))
        else:
            lb_add("%s, memory 91.7%%, %s: busy, allowed" % (_short, _say),
                   lb_decision_check(_tool, lb_reading(memory_pct=91.7), "allow", background=_bg))
        lb_add("%s, memory 97.2%%, %s: full, refused, names the reading, says no new lane or agent starts"
               % (_short, _say),
               lb_decision_check(_tool, lb_reading(memory_pct=97.2), "deny", LB_MEM_FULL + (LB_NO_NEW,),
                                 background=_bg))
        lb_add("%s, a read that raises, %s: allowed" % (_short, _say),
               lb_decision_check(_tool, "raise", "allow", background=_bg))

# Workflow is refused at busy. start_session at busy is not pinned.
lb_add("Workflow, memory 91.7%: busy, refused, names the reading",
       lb_decision_check("Workflow", lb_reading(memory_pct=91.7), "deny", LB_MEM_BUSY))
lb_add("Workflow named, not scripted, memory 91.7%: busy, refused",
       lb_decision_check("Workflow", lb_reading(memory_pct=91.7), "deny", tool_input={"name": "audit"}))
for _short, _tool in (("Workflow", "Workflow"), ("start_session", "mcp__ccd_session__start_session")):
    lb_add("%s, normal reading: allowed" % _short, lb_decision_check(_tool, LB_NORMAL, "allow"))
    lb_add("%s, memory 97.2%%: full, refused, names the reading" % _short,
           lb_decision_check(_tool, lb_reading(memory_pct=97.2), "deny", LB_MEM_FULL))
    lb_add("%s, a read that raises: allowed" % _short, lb_decision_check(_tool, "raise", "allow"))

# The other readings, on Agent. Each trips on its own, and an absent or false run_in_background passes busy
# but not full.
lb_add("Agent, 9.4 GB free of 926 GB, run_in_background left out: busy, allowed",
       lb_decision_check("Agent", lb_reading(disk_free_gb=9.4, disk_total_gb=926.0), "allow"))
lb_add("Agent, 9.4 GB free of 926 GB, run_in_background true: busy, refused, names the reading and free disk space",
       lb_decision_check("Agent", lb_reading(disk_free_gb=9.4, disk_total_gb=926.0), "deny",
                         (lb_gb(9.4, 926), LB_FREE_DISK), background=True, lacks=(LB_FOREGROUND,)))
lb_add("Agent, 9.4 GB free of 926 GB, run_in_background false: busy, allowed",
       lb_decision_check("Agent", lb_reading(disk_free_gb=9.4, disk_total_gb=926.0), "allow", background=False))
lb_add("Agent, 3.1 GB free of 926 GB, run_in_background false: full, refused, names the reading",
       lb_decision_check("Agent", lb_reading(disk_free_gb=3.1, disk_total_gb=926.0), "deny", (lb_gb(3.1, 926),),
                         background=False))

# THE DISK LINE, on the real reader under THE FAKE HOST. Busy is free under the smaller of 10% of the disk and
# 15 GB; full is free under the smaller of 5% and 5 GB. A share rule would brake the 926 GB disk with 119 GB
# free (12.85%) and the 100 GB disk with 12 GB free (12%), which this line lets run.
lb_add("disk 926 GB, 119 GB free, run_in_background true: not busy, allowed",
       lb_decision_check("Agent", None, "allow", background=True,
                         fake=lb_fake("darwin", disk_total=926.0, disk_free=119.0)))
# The 15 GB cap pins here: 50 GB is under 10% of 926 GB (92.6 GB) but not under 15 GB, so a share-only busy
# line would refuse it.
lb_add("disk 926 GB, 50 GB free, run_in_background true: not busy, allowed",
       lb_decision_check("Agent", None, "allow", background=True,
                         fake=lb_fake("darwin", disk_total=926.0, disk_free=50.0)))
lb_add("disk 926 GB, 10 GB free, run_in_background true: busy, refused, names disk 10.0 GB free of 926 GB",
       lb_decision_check("Agent", None, "deny", (lb_gb(10.0, 926), LB_FREE_DISK), background=True,
                         lacks=(LB_FOREGROUND,), fake=lb_fake("darwin", disk_total=926.0, disk_free=10.0)))
lb_add("disk 926 GB, 10 GB free, run_in_background false: busy, allowed",
       lb_decision_check("Agent", None, "allow", background=False,
                         fake=lb_fake("darwin", disk_total=926.0, disk_free=10.0)))
lb_add("disk 926 GB, 3 GB free, run_in_background true: full, refused, names disk 3.0 GB free of 926 GB",
       lb_decision_check("Agent", None, "deny", (lb_gb(3.0, 926),), background=True,
                         fake=lb_fake("darwin", disk_total=926.0, disk_free=3.0)))
lb_add("disk 100 GB, 9 GB free, run_in_background true: busy, refused, names disk 9.0 GB free of 100 GB",
       lb_decision_check("Agent", None, "deny", (lb_gb(9.0, 100), LB_FREE_DISK), background=True,
                         lacks=(LB_FOREGROUND,), fake=lb_fake("darwin", disk_total=100.0, disk_free=9.0)))
lb_add("disk 100 GB, 12 GB free, run_in_background true: not busy, allowed",
       lb_decision_check("Agent", None, "allow", background=True,
                         fake=lb_fake("darwin", disk_total=100.0, disk_free=12.0)))
lb_add("disk GB not clamped: a 926 GB disk with 119 GB free reads disk_total_gb 926 and disk_free_gb 119",
       lb_reader_fake(lb_fake("darwin", disk_total=926.0, disk_free=119.0), lb_gb_unclamped))
# Memory 80% is under the 85% that memory alone needs, so it is not busy. The brake reads no CPU: the load average
# and the CPU ticks change nothing here. The darwin fake host shows the real reader's memory is what counts.
lb_add("Agent, darwin host at memory 80%, load 107 and CPU ticks 50% busy, run_in_background true: not busy, allowed",
       lb_decision_check("Agent", None, "allow", background=True,
                         fake=lb_fake("darwin", busy=50.0, load=107.0, memory=80)))
lb_add("Agent, darwin host at memory 80%, load 1.0 and CPU ticks 90% busy, run_in_background true: not busy, allowed",
       lb_decision_check("Agent", None, "allow", background=True,
                         fake=lb_fake("darwin", busy=90.0, load=1.0, memory=80)))


def lb_no_tick_check(side):
    """The reader read no CPU tick: on a host whose ticks would read 90% busy, the host_statistics and
    /proc/stat counts stay at zero."""
    reads = side.get("tick_reads")
    if reads:
        return False, "read_load made %s CPU tick read(s), want none" % reads
    return True, "no CPU tick read"


def lb_no_cpu_key(reading):
    if "cpu_pct" in reading:
        return False, "read_load returns cpu_pct %r, want no cpu_pct key" % (reading["cpu_pct"],)
    return True, "no cpu_pct key: %s" % ", ".join(sorted(reading))


lb_add("CPU on darwin: read_load makes no host_statistics tick read on a host whose ticks would read 90% busy",
       lb_reader_fake(lb_fake("darwin", busy=90.0), lb_no_tick_check, side_check=True))
lb_add("CPU on linux: read_load makes no /proc/stat read on a host whose ticks would read 90% busy",
       lb_reader_fake(lb_fake("linux", busy=90.0), lb_no_tick_check, side_check=True))
lb_add("the reader returns no cpu_pct key on darwin", lb_reader_fake(lb_fake("darwin"), lb_no_cpu_key))
lb_add("the reader returns no cpu_pct key on linux", lb_reader_fake(lb_fake("linux"), lb_no_cpu_key))


# Memory 90% and 80% are the memory levels. The CPU never adds to a refusal, and a CPU reading never makes a busy
# call of its own.
for _short, _tool in LB_SPAWNS:
    lb_add("%s, memory 90%%, run_in_background left out: busy, allowed" % _short,
           lb_decision_check(_tool, lb_reading(memory_pct=90.0), "allow"))
    lb_add("%s, memory 90%%, run_in_background true: busy, refused, names the memory" % _short,
           lb_decision_check(_tool, lb_reading(memory_pct=90.0), "deny", LB_MEM90 + (LB_REMEDY,),
                             background=True, lacks=(LB_FOREGROUND,)))
    lb_add("%s, memory 90%%, run_in_background false: busy, allowed" % _short,
           lb_decision_check(_tool, lb_reading(memory_pct=90.0), "allow", background=False))
    for _label, _value in (('the string "true"', "true"), ("null", None), ("the number 1", 1)):
        lb_add("%s, memory 90%%, run_in_background %s: busy, refused, names the memory" % (_short, _label),
               lb_decision_check(_tool, lb_reading(memory_pct=90.0), "deny", LB_MEM90 + (LB_REMEDY,),
                                 tool_input=lb_spawn_input(_tool, _value), lacks=(LB_FOREGROUND,)))
    lb_add("%s, memory 70%%, disk 463 of 926 GB free, CPU 94%% ignored, run_in_background true: allowed" % _short,
           lb_decision_check(_tool, lb_reading(cpu_pct=94.0, memory_pct=70.0, disk_free_gb=463.0, disk_total_gb=926.0),
                             "allow", background=True))
    # Any CPU state at memory 80% is not busy. A stub's CPU is ignored, and a reading with no CPU key is the shape
    # the reader returns.
    lb_add("%s, memory 80%%, CPU 94%%, run_in_background true: not busy, allowed" % _short,
           lb_decision_check(_tool, lb_reading(cpu_pct=94.0, memory_pct=80.0), "allow", background=True))
    lb_add("%s, memory 80%%, CPU 99%%, run_in_background true: not busy, allowed" % _short,
           lb_decision_check(_tool, lb_reading(cpu_pct=99.0, memory_pct=80.0), "allow", background=True))
    lb_add("%s, memory 80%%, no CPU reading, run_in_background true: not busy, allowed" % _short,
           lb_decision_check(_tool, lb_reading(memory_pct=80.0), "allow", background=True))

# A refusal never names the CPU. Memory 90 with CPU 94 is refused on memory alone; a brake that still reads the CPU
# names both, and these cases catch that.
for _short, _tool in LB_SPAWNS:
    lb_add("%s, memory 90%%, CPU 94%%, run_in_background true: busy, refused, names memory and never CPU" % _short,
           lb_decision_check(_tool, lb_reading(cpu_pct=94.0, memory_pct=90.0), "deny", LB_MEM90 + (LB_REMEDY,),
                             background=True, lacks=(LB_CPU_WORD, LB_FOREGROUND)))
lb_add("Workflow, memory 80%, CPU 94%: not busy, allowed",
       lb_decision_check("Workflow", lb_reading(cpu_pct=94.0, memory_pct=80.0), "allow"))
lb_add("Workflow, memory 80%, no CPU reading: not busy, allowed",
       lb_decision_check("Workflow", lb_reading(memory_pct=80.0), "allow"))
lb_add("Workflow, memory 70%, disk 463 of 926 GB free, CPU 94% ignored: allowed",
       lb_decision_check("Workflow", lb_reading(cpu_pct=94.0, memory_pct=70.0, disk_free_gb=463.0,
                                                disk_total_gb=926.0), "allow"))
lb_add("Workflow, memory 90%, CPU 94%: busy, refused, names memory and never CPU",
       lb_decision_check("Workflow", lb_reading(cpu_pct=94.0, memory_pct=90.0), "deny", LB_MEM90,
                         lacks=(LB_CPU_WORD,)))
lb_add("Agent, darwin host at memory 90%, CPU ticks 94% busy, run_in_background true: busy, refused, names memory and never CPU",
       lb_decision_check("Agent", None, "deny", LB_MEM90 + (LB_REMEDY,), background=True,
                         lacks=(LB_CPU_WORD, LB_FOREGROUND), fake=lb_fake("darwin", busy=94.0, memory=90)))
lb_add("Agent, memory 97.2%, CPU 99%, run_in_background false: full, refused, names memory and never CPU",
       lb_decision_check("Agent", lb_reading(cpu_pct=99.0, memory_pct=97.2), "deny", LB_MEM_FULL,
                         background=False, lacks=(LB_CPU_WORD,)))
lb_add("Agent, 20 claude processes read, the rest normal: no process count, allowed",
       lb_decision_check("Agent", lb_reading(claude_procs=20), "allow"))
lb_add("Agent, memory unread and the rest normal, run_in_background left out: allowed",
       lb_decision_check("Agent", lb_reading(memory_pct=None), "allow"))
lb_add("Agent, an empty reading, run_in_background left out: allowed",
       lb_decision_check("Agent", {}, "allow"))
lb_add("Agent, memory unread but disk 3.1 GB free of 926 GB: one unread reading hides no other, refused",
       lb_decision_check("Agent", lb_reading(memory_pct=None, disk_free_gb=3.1, disk_total_gb=926.0), "deny",
                         (lb_gb(3.1, 926),), background=False))

lb_add("Bash reads no load under the worst reading", lb_no_read_check("Bash", {"command": "echo hi"}))
lb_add("PowerShell reads no load under the worst reading",
       lb_no_read_check("PowerShell", {"command": "Write-Output hi"}))
lb_add("Edit reads no load under the worst reading",
       lb_no_read_check("Edit", {"file_path": "{cwd}/notes.txt", "old_string": "a", "new_string": "b"}))
lb_add("Write reads no load under the worst reading",
       lb_no_read_check("Write", {"file_path": "{cwd}/notes.txt", "content": "a"}))
lb_add("a session tool that starts no lane reads no load under the worst reading",
       lb_no_read_check("mcp__ccd_session__list_start_targets", {}))
lb_add("a SubagentStop reads no load under the worst reading",
       lb_no_read_check(None, {}, event="SubagentStop"))

# A RUNNING LANE. An agent's own shell or file write reads the load once, so a lane stops at full even while
# its orchestrator waits on the owner. Busy lets it run. The orchestrator's own calls above read nothing.
LB_AGENT = "a64a7f84210a8721d"
LB_STOP_AGENT = re.compile(r"Stop this agent now")
LB_WRITES = (("Bash", {"command": "echo hi"}), ("PowerShell", {"command": "Write-Output hi"}),
             ("Edit", {"file_path": "{cwd}/notes.txt", "old_string": "a", "new_string": "b"}),
             ("Write", {"file_path": "{cwd}/notes.txt", "content": "a"}),
             ("MultiEdit", {"file_path": "{cwd}/notes.txt", "edits": [{"old_string": "a", "new_string": "b"}]}),
             ("NotebookEdit", {"notebook_path": "{cwd}/n.ipynb", "new_source": "a"}))
for _tool, _given in LB_WRITES:
    lb_add("an agent's %s, 3.1 GB free of 926 GB: full, refused, names the reading, tells the agent to stop" % _tool,
           lb_decision_check(_tool, lb_reading(disk_free_gb=3.1, disk_total_gb=926.0), "deny",
                             (lb_gb(3.1, 926), LB_STOP_AGENT, LB_RUN_CITE), tool_input=_given, agent=LB_AGENT))
lb_add("an agent's Bash, memory 97.2%: full, refused, names the reading",
       lb_decision_check("Bash", lb_reading(memory_pct=97.2), "deny", LB_MEM_FULL + (LB_STOP_AGENT,),
                         tool_input={"command": "echo hi"}, agent=LB_AGENT))
lb_add("an agent's Bash, memory 91.7% and 9.4 GB free of 926 GB: busy, allowed, one read",
       lb_decision_check("Bash", lb_reading(memory_pct=91.7, disk_free_gb=9.4, disk_total_gb=926.0), "allow",
                         tool_input={"command": "echo hi"}, agent=LB_AGENT))
lb_add("an agent's Bash, memory 90% and 8 GB free of 100 GB (8%): busy, not full, allowed, one read",
       lb_decision_check("Bash", lb_reading(memory_pct=90.0, disk_free_gb=8.0, disk_total_gb=100.0), "allow",
                         tool_input={"command": "echo hi"}, agent=LB_AGENT))
lb_add("an agent's Write, memory 95.0% and 5.0 GB free of 100 GB: on the line, not over it, allowed",
       lb_decision_check("Write", lb_reading(memory_pct=95.0, disk_free_gb=5.0, disk_total_gb=100.0), "allow",
                         tool_input={"file_path": "{cwd}/notes.txt", "content": "a"}, agent=LB_AGENT))
lb_add("the orchestrator's own Bash, full machine: never braked, no read",
       lb_no_read_check("Bash", {"command": "df -h"}))
lb_add("an agent's Bash, normal reading: allowed, one read, no file",
       lb_decision_check("Bash", LB_NORMAL, "allow", tool_input={"command": "echo hi"}, agent=LB_AGENT))
lb_add("an agent's Bash, a read that raises: allowed",
       lb_decision_check("Bash", "raise", "allow", tool_input={"command": "echo hi"}, agent=LB_AGENT))
lb_add("an agent's Agent call, memory 97.2%: full, refused, one read, not two",
       lb_decision_check("Agent", lb_reading(memory_pct=97.2), "deny", LB_MEM_FULL, agent=LB_AGENT))
lb_add("an agent's session tool that writes nothing reads no load under the worst reading",
       lb_no_read_check("mcp__ccd_session__list_start_targets", {}, agent=LB_AGENT))
lb_add("a Bash call whose agent_id is malformed reads no load under the worst reading",
       lb_no_read_check("Bash", {"command": "echo hi"}, agent="not an id!"))

# CLOUD. decision session-tiers: the load brake is local-only. With CLAUDE_CODE_REMOTE=true a start call is
# allowed at busy and full. These run end to end, so an allowed call's file writes are checked too (nothing reaches
# guard.log). The section below already holds an Agent with run_in_background true, a Workflow and the writes at full,
# so those are not repeated here.
LB_CLOUD = "true"
CLOUD_VALUES = ((None, False), ("true", True), ("TRUE", False), ("True", False), ("1", False), ("", False),
                ("false", False), (" true", False))
for _tool, _bg, _say in (("Agent", False, "run_in_background false"),
                         ("Agent", None, "run_in_background left out"),
                         ("Task", True, "run_in_background true"),
                         ("Task", False, "run_in_background false"),
                         ("Task", None, "run_in_background left out")):
    lb_add("cloud: %s, memory 99%%, disk 1.0 GB free of 926 GB, %s: allowed, nothing written" % (_tool, _say),
           lb_decision_check(_tool, LB_ALL_HIGH, "allow", background=_bg, reads=None, remote=LB_CLOUD))
lb_add("cloud: start_session, memory 99%, disk 1.0 GB free of 926 GB: allowed, nothing written",
       lb_decision_check("mcp__ccd_session__start_session", LB_ALL_HIGH, "allow", reads=None, remote=LB_CLOUD))
for _tool in ("Agent", "Task"):
    lb_add("cloud: %s, memory 91.7%%, run_in_background true: busy, allowed" % _tool,
           lb_decision_check(_tool, lb_reading(memory_pct=91.7), "allow", background=True, reads=None,
                             remote=LB_CLOUD))
lb_add("cloud: an agent's Bash, memory 99%, disk 1.0 GB free of 926 GB: allowed, nothing written",
       lb_decision_check("Bash", LB_ALL_HIGH, "allow", tool_input={"command": "echo hi"}, agent=LB_AGENT,
                         reads=None, remote=LB_CLOUD))
lb_add("cloud: an agent's Agent call, memory 97.2%: allowed",
       lb_decision_check("Agent", lb_reading(memory_pct=97.2), "allow", agent=LB_AGENT, reads=None,
                         remote=LB_CLOUD))
lb_add("cloud: Agent, darwin host at memory 97.2%, run_in_background false, the real reader: allowed",
       lb_decision_check("Agent", None, "allow", background=False, fake=lb_fake("darwin", memory=97.2), reads=None,
                         remote=LB_CLOUD))
lb_add("cloud: Agent, linux disk 3.1 GB free of 926 GB, run_in_background true, the real reader: allowed",
       lb_decision_check("Agent", None, "allow", background=True, fake=lb_fake("linux", disk_free=3.1), reads=None,
                         remote=LB_CLOUD))
# Only the exact value "true" is cloud: the other values keep the local brake, so the refusal still stands.
for _remote in ("1", "TRUE", ""):
    lb_add("CLAUDE_CODE_REMOTE=%r is local: Agent, memory 97.2%%, run_in_background false: full, refused" % _remote,
           lb_decision_check("Agent", lb_reading(memory_pct=97.2), "deny", LB_MEM_FULL, background=False,
                             remote=_remote))


def cloud_name_check():
    """guard_core.is_cloud exists and returns True only for exactly "true", read from the environment at each call."""
    import importlib
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    core = importlib.import_module("guard_core")
    helper = getattr(core, "is_cloud", None)
    if not callable(helper):
        return False, "guard_core has no is_cloud: the cloud check has no one home yet"
    for value, want in CLOUD_VALUES:
        with mock.patch.dict(os.environ):
            if value is None:
                os.environ.pop("CLAUDE_CODE_REMOTE", None)
            else:
                os.environ["CLAUDE_CODE_REMOTE"] = value
            got = helper()
        if got is not want:
            return False, "is_cloud() with CLAUDE_CODE_REMOTE=%r gave %r, want %r" % (value, got, want)
    return True, 'True for exactly "true", False for the other values and when unset'


def cloud_one_home_check():
    """guard.py's brake guard holds guard_core's is_cloud: the cloud check has one home."""
    import importlib
    guard = _load_guard_module()
    core = importlib.import_module("guard_core")
    helper = getattr(core, "is_cloud", None)
    if not callable(helper):
        return False, "guard_core has no is_cloud: the cloud check has no one home yet"
    got = getattr(guard, "is_cloud", None)
    if got is not helper:
        return False, "guard.py's brake guard does not hold guard_core.is_cloud (it holds %r)" % (got,)
    return True, "guard.py holds guard_core.is_cloud"


lb_add('cloud check: guard_core.is_cloud exists and is True only for exactly "true"', cloud_name_check)
lb_add("cloud check: guard.py's brake guard holds guard_core.is_cloud, one home", cloud_one_home_check)


# A CLOUD SESSION. The brake is specific to local sessions: with CLAUDE_CODE_REMOTE "true" it skips every lane
# start and every running-lane call, and reads no load, so the reader is never called. Only the exact value
# "true" is a cloud session. Unset and "false" are local and keep the brake. Every label names CLAUDE_CODE_REMOTE,
# so MUTATE_ONLY=CLAUDE_CODE_REMOTE runs this section alone.
LB_FULL_READING = lb_reading(memory_pct=97.2)   # a full machine: memory over 95%


def lb_hit_check(which, tool, reading, tool_input, remote=None, deny=None, reads=1, agent=None):
    """A direct call of load_hit (which "load_hit") or running_agent_hit (which "running_agent_hit") on the call's
    own payload, under a forced reading and `remote`. `deny` is None for the empty pair ("", ""), or the patterns
    the refusal's reason must name. `reads` is how many times the reader ran across the probe's two calls."""
    key = "hit" if which == "load_hit" else "running"

    def check():
        got, reason, side = lb_run(tool, {"mode": "hit", "reading": reading}, tool_input, agent=agent,
                                   remote=remote)
        if got == "error":
            return False, reason
        called, pair = side.get("reads"), side.get(key)
        if pair is None:
            return False, "guard.py defines no %s" % which
        if not isinstance(pair, list) or len(pair) != 2:
            return False, "%s returned %r, want a pair" % (which, pair)
        if deny is None:
            if pair != ["", ""]:
                return False, "%s returned %r, want the empty pair: %s" % (which, pair, pair[0][:90])
        else:
            if not pair[0]:
                return False, "%s returned the empty pair, want a refusal" % which
            for pattern in deny:
                if not pattern.search(pair[0]):
                    return False, "the reason does not name the reading (%s): %s" % (
                        pattern.pattern[:30], pair[0][:100])
        if called != reads:
            return False, "%s as wanted, but the reader ran %s time(s), want %d" % (which, called, reads)
        return True, "%s as wanted, the reader ran %d time(s)" % (which, called)
    return check


# Cloud: the direct pairs are empty and the reader never runs.
lb_add("CLAUDE_CODE_REMOTE=true, Agent run_in_background true, memory 97.2%: load_hit returns the empty pair, "
       "the reader never runs",
       lb_hit_check("load_hit", "Agent", LB_FULL_READING, lb_lane_input("Agent", True), remote="true", reads=0))
lb_add("CLAUDE_CODE_REMOTE=true, Workflow, memory 97.2%: load_hit returns the empty pair, the reader never runs",
       lb_hit_check("load_hit", "Workflow", LB_FULL_READING, lb_lane_input("Workflow"), remote="true", reads=0))
lb_add("CLAUDE_CODE_REMOTE=true, an agent's Bash, memory 97.2%: running_agent_hit returns the empty pair, "
       "the reader never runs",
       lb_hit_check("running_agent_hit", "Bash", LB_FULL_READING, {"command": "echo hi"}, remote="true", reads=0,
                    agent=LB_AGENT))
lb_add("CLAUDE_CODE_REMOTE=true, Agent run_in_background true, full reading: allowed, the reader never runs",
       lb_no_read_check("Agent", lb_lane_input("Agent", True), remote="true"))
lb_add("CLAUDE_CODE_REMOTE=true, Workflow, full reading: allowed, the reader never runs",
       lb_no_read_check("Workflow", lb_lane_input("Workflow"), remote="true"))
for _tool, _given in LB_WRITES:   # the agent's Bash is the first of these
    lb_add("CLAUDE_CODE_REMOTE=true, an agent's %s, full reading: allowed, the reader never runs" % _tool,
           lb_no_read_check(_tool, _given, agent=LB_AGENT, remote="true"))

# Local: unset and "false" keep the brake, so each full reading is still refused, and the reader runs once.
for _remote, _say in ((None, "unset"), ("false", "false")):
    lb_add("CLAUDE_CODE_REMOTE %s, Agent run_in_background true, memory 97.2%%: load_hit refuses, names the memory"
           % _say,
           lb_hit_check("load_hit", "Agent", LB_FULL_READING, lb_lane_input("Agent", True), remote=_remote,
                        deny=LB_MEM_FULL))
    lb_add("CLAUDE_CODE_REMOTE %s, Workflow, memory 97.2%%: load_hit refuses, names the memory" % _say,
           lb_hit_check("load_hit", "Workflow", LB_FULL_READING, lb_lane_input("Workflow"), remote=_remote,
                        deny=LB_MEM_FULL))
    lb_add("CLAUDE_CODE_REMOTE %s, an agent's Bash, memory 97.2%%: running_agent_hit refuses, names the memory, "
           "tells the agent to stop" % _say,
           lb_hit_check("running_agent_hit", "Bash", LB_FULL_READING, {"command": "echo hi"}, remote=_remote,
                        deny=LB_MEM_FULL + (LB_STOP_AGENT,), agent=LB_AGENT))
    lb_add("CLAUDE_CODE_REMOTE %s, Agent run_in_background true, memory 97.2%%: refused, names the memory, "
           "one read" % _say,
           lb_decision_check("Agent", LB_FULL_READING, "deny", LB_MEM_FULL, background=True, remote=_remote))
    lb_add("CLAUDE_CODE_REMOTE %s, Workflow, memory 97.2%%: refused, names the memory" % _say,
           lb_decision_check("Workflow", LB_FULL_READING, "deny", LB_MEM_FULL, remote=_remote))
    lb_add("CLAUDE_CODE_REMOTE %s, an agent's Bash, memory 97.2%%: refused, names the memory, tells the agent to stop"
           % _say,
           lb_decision_check("Bash", LB_FULL_READING, "deny", LB_MEM_FULL + (LB_STOP_AGENT,),
                             tool_input={"command": "echo hi"}, agent=LB_AGENT, remote=_remote))

for _short, _tool in LB_TOOLS:
    lb_add("%s with the real reader starts no child process" % _short,
           lb_real_children_check(_tool), real=True)
lb_add("Agent with run_in_background false, the real reader, starts no child process",
       lb_real_children_check("Agent", background=False), real=True)
lb_add("the real reader starts no child process", lb_reader(lb_reader_children), real=True)
lb_add("the real reader writes no file", lb_reader(lb_reader_files), real=True)
lb_add("the real reader returns readings in range, and on Windows and Mac reads memory and disk, with no cpu_pct key",
       lb_reader(lb_reader_shape), real=True)


def lb_live_waits_check(tool):
    """A start call on the live judge, with no stub reading, makes no sleep: the CPU read's 200 ms wait."""
    def check():
        got, reason, side = lb_run(tool, {"mode": "judge"}, lb_lane_input(tool))
        if got == "error":
            return False, reason
        if not side.get("had_reader"):
            return False, "the guard has no read_load, so no real reading was taken"
        if side.get("sleeps"):
            return False, "%s slept %d time(s), want none" % (got, side["sleeps"])
        return True, "%s, no sleep" % got
    return check


def lb_live_times_check():
    """On Windows, no start call on the live judge makes a GetSystemTimes call, the CPU tick read."""
    if sys.platform != "win32":
        return SKIP, "GetSystemTimes is the Windows CPU tick read, so this runs on Windows only"
    for _short, tool in LB_TOOLS:
        got, reason, side = lb_run(tool, {"mode": "judge"}, lb_lane_input(tool))
        if got == "error":
            return False, reason
        if not side.get("had_reader"):
            return False, "the guard has no read_load, so no real reading was taken"
        if side.get("GetSystemTimes"):
            return False, "%s made %d GetSystemTimes call(s), want none" % (_short, side["GetSystemTimes"])
    return True, "no GetSystemTimes call on any start call"


for _short, _tool in LB_TOOLS:
    lb_add("%s on the live judge makes no sleep, so no 200 ms CPU wait" % _short,
           lb_live_waits_check(_tool), real=True)
lb_add("Windows: no start call on the live judge makes a GetSystemTimes call", lb_live_times_check, real=True)


# A LANE SESSION (decision machine-load-brake). A lane session's own shell or file write is refused at a full machine,
# as an agent's is, so a lane its orchestrator leaves waiting stops writing. The session's own id is
# CLAUDE_CODE_REMOTE_SESSION_ID (cse_<x>, read as session_<x>). Its own get_session record in the transcript must tag
# cs-build:lane, with no other cs-build: tier tag, and no set_session_tags naming it may follow that record. Any other
# session, a cloud session, a session with no own id, and any read error passes. A session with an own id reads the
# load once, and opens its transcript only when the reading is full.
LB_LANE_TAGS = ["cs-build:lane", "cs-repo:o/r"]
LB_LANE = role_call("g1", LB_LANE_TAGS)   # the lane's own record, as its transcript holds it
LB_OWN = ROLE_ENV                          # the env that names it: CLAUDE_CODE_REMOTE_SESSION_ID=cse_ROLEOWN01
# The refusal tells the lane to end its turn and send the reading to its parent.
LB_LANE_REMEDY = (re.compile(r"end your turn", re.I), re.compile(r"send_message", re.I),
                  re.compile(re.escape("@parent")))
LB_LANE_BASH = {"command": "echo hi"}
LB_LANE_EDIT = {"file_path": "{cwd}/notes.txt", "old_string": "a", "new_string": "b"}
LB_BUSY = lb_reading(memory_pct=91.7)                             # busy on memory: over 85%, not over 95%
LB_BUSY_EDIT = lb_reading(disk_free_gb=9.4, disk_total_gb=926.0)  # busy on disk: under 15 GB of 926
LB_LONG = [line for n in range(200)                               # a 400-line transcript of other calls
           for line in (role_use("f%d" % n, "Bash", {"command": "ls"}), role_result("f%d" % n, "a.txt"))]


def lb_lane_direct_check(tool, tool_input, reading, names):
    """lane_session_hit, called direct on the lane's own call under `reading`: its pair is a refusal that names each
    of `names`, and the reader ran once."""
    def check():
        got, reason, side = lb_run(tool, {"mode": "lane", "reading": reading}, tool_input, own_env=LB_OWN,
                                   transcript=LB_LANE)
        if got == "error":
            return False, reason
        pair = side.get("lane")
        if pair is None:
            return False, "the guard has no lane_session_hit"
        if not isinstance(pair, list) or len(pair) != 2 or not pair[0]:
            return False, "lane_session_hit returned %r, want a refusal" % (pair,)
        for pattern in names:
            if not pattern.search(pair[0]):
                return False, "lane_session_hit's refusal does not name %r: %s" % (pattern.pattern[:30], pair[0][:100])
        if side.get("reads") != 1:
            return False, "lane_session_hit ran the reader %s time(s), want 1" % side.get("reads")
        return True, "lane_session_hit refuses, names the reading and the remedy, and the reader ran once"
    return check


def lb_lane_refusal_check(tool, tool_input, reading, names):
    """A lane session's call under `reading` is refused, names each of `names`, and tells the lane to end its turn and
    report to @parent. The reader runs once. The full run is checked first, so the direct call is judged only once the
    run refuses. The direct call must refuse the same way."""
    full = tuple(names) + LB_LANE_REMEDY
    judge = lb_decision_check(tool, reading, "deny", full, tool_input=tool_input, own_env=LB_OWN, transcript=LB_LANE)
    direct = lb_lane_direct_check(tool, tool_input, reading, full)

    def check():
        ok, note = judge()
        return direct() if ok else (ok, note)
    return check


def lb_lane_refusal_quiet_check():
    """A lane session's shell on a full machine starts no child process, and writes no file but the refusal's guard.log
    line."""
    def check():
        got, reason, side = lb_run("Bash", {"mode": "judge", "reading": LB_FULL_READING}, LB_LANE_BASH,
                                   own_env=LB_OWN, transcript=LB_LANE)
        if got == "error":
            return False, reason
        if got != "deny":
            return False, "%s, want deny: %s" % (got, reason[:90])
        if side["children"]:
            return False, "%d child process(es) started: %s" % (len(side["children"]), side["children"][:3])
        written = sorted(os.path.basename(path) for path in side["files"])
        if written != ["guard.log"]:
            return False, "the refusal wrote %s, want only guard.log" % (written,)
        return True, "deny, no child process, and guard.log is the only file written"
    return check


def lb_lane_quiet_check(own_env=None, remote=None):
    """A call that no lane check reaches, at a full reading: it is allowed, the reader runs no time, the transcript is
    not opened, and no file is written."""
    def check():
        got, reason, side = lb_run("Bash", {"mode": "judge", "reading": LB_ALL_HIGH}, LB_LANE_BASH, own_env=own_env,
                                   transcript=LB_LANE, spy=True, remote=remote)
        if got == "error":
            return False, reason
        if got != "allow":
            return False, "%s, want allow: %s" % (got, reason[:90])
        if side.get("reads"):
            return False, "the reader ran %s time(s), want none" % side["reads"]
        if side.get("opened"):
            return False, "the transcript was opened %d time(s), want none" % side["opened"]
        if side["files"]:
            return False, "an allowed call wrote %d file(s)" % len(side["files"])
        return True, "allow, no read, the transcript is not opened"
    return check


def lb_transcript_read_check(reading, opened_wanted):
    """A lane session's own call: at a full reading its transcript is opened, since the lane check reads it; at a normal
    reading it is not. The reader runs once either way."""
    def check():
        got, reason, side = lb_run("Bash", {"mode": "judge", "reading": reading}, LB_LANE_BASH, own_env=LB_OWN,
                                   transcript=LB_LANE, spy=True)
        if got == "error":
            return False, reason
        opened = side.get("opened", 0)
        if opened_wanted and not opened:
            return False, "the transcript was not opened at a full reading, so no lane check reads it"
        if not opened_wanted and opened:
            return False, "the transcript was opened %d time(s) at a normal reading, want none" % opened
        if side.get("reads") != 1:
            return False, "the reader ran %s time(s), want 1" % side.get("reads")
        return True, "the transcript opened %d time(s), and the reader ran once" % opened
    return check


def lb_spy_control_check():
    """The spy counts one open of the transcript path, so the transcript checks above see a read when one happens."""
    def check():
        got, reason, side = lb_run(None, {"mode": "selfcheck_open"}, tool_input={}, transcript=LB_LANE, spy=True)
        if got == "error":
            return False, reason
        if side.get("opened") != 1:
            return False, "the spy counted %s open(s) of the transcript, want 1" % side.get("opened")
        return True, "the spy counts one open"
    return check


# The refusal at a full machine: each write tool, a disk reading, and the shell's quiet refusal.
for _tool, _given in LB_WRITES:
    lb_add("a lane session's %s, memory 97.2%%: full, refused, names the memory, tells the lane to end its turn "
           "and report to @parent" % _tool,
           lb_lane_refusal_check(_tool, _given, LB_FULL_READING, LB_MEM_FULL))
lb_add("a lane session's Bash, 3.1 GB free of 926 GB: full, refused, names the disk, tells the lane to end its turn",
       lb_lane_refusal_check("Bash", LB_LANE_BASH, lb_reading(disk_free_gb=3.1, disk_total_gb=926.0), (lb_gb(3.1, 926),)))
lb_add("a lane session's Bash, memory 97.2%: full, starts no child process and writes only the guard.log line",
       lb_lane_refusal_quiet_check())

# The busy reading lets a lane run, and the lane's one read is the reader's.
lb_add("a lane session's Bash, memory 91.7%: busy, allowed, the reader runs once",
       lb_decision_check("Bash", LB_BUSY, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN, transcript=LB_LANE))
lb_add("a lane session's Edit, 9.4 GB free of 926 GB: busy, allowed, the reader runs once",
       lb_decision_check("Edit", LB_BUSY_EDIT, "allow", tool_input=LB_LANE_EDIT, own_env=LB_OWN, transcript=LB_LANE))
# An agent of a lane makes an agent's call, so it reads the load once, as an agent's write does, and the lane check never
# reads it again. Both pin the cost of the new check on an agent's call, which must not add a second read.
lb_add("a lane session's agent Bash (agent_id set), memory 91.7%: busy, allowed, the reader runs once",
       lb_decision_check("Bash", LB_BUSY, "allow", tool_input=LB_LANE_BASH, agent=LB_AGENT, own_env=LB_OWN,
                         transcript=LB_LANE))
lb_add("a lane session's agent Bash (agent_id set), memory 97.2%: full, refused by the agent's stop, "
       "the reader runs once",
       lb_decision_check("Bash", LB_FULL_READING, "deny", LB_MEM_FULL + (LB_STOP_AGENT,), tool_input=LB_LANE_BASH,
                         agent=LB_AGENT, own_env=LB_OWN, transcript=LB_LANE))

# A record that is no lane's: another tier tag, or a parent with no tier tag. At a full machine it is allowed.
for _say, _lines in (
        ("a coordinator record", role_call("g1", ["cs-build:coordinator", "cs-repo:o/r"])),
        ("a triage record, with its parent", role_call("g1", ["cs-build:triage", "cs-repo:o/r"])),
        ("a batch-runner record, with its parent", role_call("g1", ["cs-build:batch-runner", "cs-repo:o/r"])),
        ("a record with cs-build:lane and cs-build:coordinator", role_call(
            "g1", ["cs-build:lane", "cs-build:coordinator", "cs-repo:o/r"])),
        ("a record with a parent and no cs-build tag", role_call("g1", ["cs-repo:o/r"]))):
    lb_add("own record is %s, memory 97.2%%: full, allowed, the reader runs once" % _say,
           lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN,
                             transcript=_lines))

# set_session_tags: a lane that tags its own record after it is no longer a lane. Tagging another session leaves it one.
lb_add("a lane session that tags its own record after it, memory 97.2%: full, allowed, the reader runs once",
       lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN,
                         transcript=LB_LANE + role_tag_call("t1")))
lb_add("a lane session whose record is tagged on another session after it, memory 97.2%: full, refused",
       lb_decision_check("Bash", LB_FULL_READING, "deny", LB_MEM_FULL + LB_LANE_REMEDY, tool_input=LB_LANE_BASH,
                         own_env=LB_OWN, transcript=LB_LANE + role_tag_call("t1", session=ROLE_OTHER)))

# No own record, or a transcript that cannot be read, is no lane: allowed at full, and the reader still runs once.
lb_add("a lane record for another session only, memory 97.2%: full, allowed, the reader runs once",
       lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN,
                         transcript=role_call("g1", LB_LANE_TAGS, session=ROLE_OTHER)))
lb_add("the transcript file is missing, memory 97.2%: full, allowed, the reader runs once",
       lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN,
                         transcript=LB_MISSING))
lb_add("the transcript is a folder, memory 97.2%: full, allowed, the reader runs once",
       lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN,
                         transcript=LB_FOLDER))
lb_add("an empty transcript, memory 97.2%: full, allowed, the reader runs once",
       lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN, transcript=[]))

# The newest own record decides: a lane that later becomes a coordinator is allowed, and the reverse is refused.
lb_add("a lane record, then a coordinator record, memory 97.2%: full, allowed, the newest record decides",
       lb_decision_check("Bash", LB_FULL_READING, "allow", tool_input=LB_LANE_BASH, own_env=LB_OWN,
                         transcript=LB_LANE + role_call("g2", ["cs-build:coordinator", "cs-repo:o/r"])))
lb_add("a coordinator record, then a lane record, memory 97.2%: full, refused, the newest record decides",
       lb_decision_check("Bash", LB_FULL_READING, "deny", LB_MEM_FULL + LB_LANE_REMEDY, tool_input=LB_LANE_BASH,
                         own_env=LB_OWN, transcript=role_call("g1", ["cs-build:coordinator", "cs-repo:o/r"])
                         + role_call("g2", LB_LANE_TAGS)))
lb_add("a lane record at the end of a 400-line transcript, memory 97.2%: full, refused, names the memory",
       lb_decision_check("Bash", LB_FULL_READING, "deny", LB_MEM_FULL + LB_LANE_REMEDY, tool_input=LB_LANE_BASH,
                         own_env=LB_OWN, transcript=LB_LONG + LB_LANE))

# No lane check reaches these calls: a cloud session, a session with no own id, and an own id in another shape.
lb_add("CLAUDE_CODE_REMOTE=true with a lane record, memory 99%: allowed, the reader runs 0 times, transcript not opened",
       lb_lane_quiet_check(own_env=LB_OWN, remote="true"))
lb_add("a lane record and no own id, memory 99%: allowed, the reader runs 0 times, transcript not opened",
       lb_lane_quiet_check(own_env=None))
lb_add("a lane record and an own id in another shape (xyz), memory 99%: allowed, the reader runs 0 times, "
       "transcript not opened", lb_lane_quiet_check(own_env={"CLAUDE_CODE_REMOTE_SESSION_ID": "xyz"}))

# The transcript is opened only at a full reading. The spy control shows that one open is counted.
lb_add("probe control: the transcript spy counts one open of the transcript", lb_spy_control_check())
lb_add("a lane session's transcript is opened at a full reading, so the lane check reads it",
       lb_transcript_read_check(LB_FULL_READING, True))
lb_add("a lane session's transcript is not opened at a normal reading, and the reader runs once",
       lb_transcript_read_check(LB_NORMAL, False))


def shard_split_check():
    """GUARD_SHARD: the n shards of a list are disjoint, hold every item, and differ in size by one at most;
    "<i>-<n>" reads as "<i>/<n>", and a malformed value stops the run."""
    for size in (0, 1, 7, 3900):
        items = list(range(size))
        for n in range(1, 6):
            shards = [shard_of(items, (i, n)) for i in range(1, n + 1)]
            if sorted(sum(shards, [])) != items or max(map(len, shards)) - min(map(len, shards)) > 1:
                return False, "%d items in %d shards split as %s" % (size, n, [len(x) for x in shards])
    for good, want in (("1/3", (1, 3)), ("1-3", (1, 3)), ("2-3", (2, 3))):
        try:
            got = parse_shard(good)
        except SystemExit:
            return False, "GUARD_SHARD=%r was refused, want %r" % (good, want)
        if got != want:
            return False, "GUARD_SHARD=%r read as %r, want %r" % (good, got, want)
    for bad in ("0/2", "3/2", "1", "1/0", "a/b", "1/2/3", " 1/2", "01/2",
                "0-2", "3-2", "1-0", "a-b", "1-2-3", " 1-2", "1-2 ", "1-", "-2", "1/2-3", "1-2/3", "01-2"):
        try:
            parse_shard(bad)
        except SystemExit:
            continue
        return False, "GUARD_SHARD=%r was accepted" % bad
    if parse_shard("") != (1, 1) or parse_shard("2/3") != (2, 3):
        return False, "parse_shard misread an empty or a well-formed value"
    return True, "shards of 0 to 3900 items in 1 to 5 shards are disjoint and whole; i-n reads as i/n; bad values stop"


LOG_CHECKS_EXTRA.append(("GUARD_SHARD: the shards are disjoint and hold every case", shard_split_check))
LOG_FAMILY["GUARD_SHARD: the shards are disjoint and hold every case"] = "misc"
FIXTURELESS_CHECKS.add(shard_split_check)


# =========================================================================== agent role model
#
# Rule agent-role-model (decision agent-model-cap). Three parts, one reader of the table:
#   1. A spawn whose model ranks above its role's row is denied. The row is read at each spawn from
#      the pointer checkout's docs/decisions/agent-model-cap.md, so the guard holds no copy of it.
#   2. A spawn with no model, whose role has no `model:` pin in the pointer's agents/<file>.md, is
#      denied when CLAUDE_CODE_SUBAGENT_MODEL is unset or empty in the guard's environment.
#   3. A decision file that cannot be read fails open: the spawn passes, and guard.log gets one
#      unread line.
# The pointer is the checkout the owner's global rules name. The cases that judge the owner's rows
# name the real checkout (REPO), so they judge the rows the owner set. Opus is never this rule's
# deny: an Opus spawn above its row is refused under agent-model-cap (rule 9d, item 127 pick a).
