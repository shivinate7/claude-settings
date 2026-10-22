#!/usr/bin/env python3
"""Accuracy of the machine-load readings against the OS's own tools. Standard library only, and no
test runner.

Run it from the repository root, on a real Windows or Mac host:

    python hooks/test_guard_load_os.py

On any other platform each case prints SKIP and the run passes. GUARD_UNDER_TEST points the run at
another copy of the guard, as in hooks/test_guard.py.

THE CLAIM. The load brake in hooks/guard.py judges a lane-start call from four readings. A reading
that is off by a wide margin brakes a healthy machine or lets a full one run, and the unit cases in
hooks/test_guard.py cannot see it, because they replace the reader. Here the real reader runs and
each reading is compared with the OS's own tool, taken a moment later, within a tolerance. The
tolerances are wide on purpose: the machine moves between two reads, and the brake needs the right
level, not the exact digit.

THE READER. read_load() is the function named in the load-brake section of hooks/test_guard.py. It
returns a dict, and each reading is defined here:

  memory_pct      percent of physical memory IN USE.
                  Windows reference: Win32_OperatingSystem, 100 * (total - free) / total.
                  Mac reference: memory_pressure, 100 - "System-wide memory free percentage".
  disk_free_pct   percent FREE on the drive that holds the home folder.
                  Windows reference: Get-PSDrive, Free / (Free + Used).
                  Mac reference: df -k on the home folder, Available / 1K-blocks.
  cpu_pct         percent of CPU busy. Secondary: it only ever makes the machine busy.
                  Windows reference: Win32_PerfFormattedData_PerfOS_Processor, the _Total row.
                  Mac reference: the 1-minute load average from uptime, divided by hw.ncpu from
                  sysctl, times 100, capped at 100.
  claude_procs    Windows only: the count of processes whose image name is claude.exe (any case).
                  Reference: Get-Process -Name claude.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")

# Points of percent, or processes, by which the reader and the OS tool may differ.
TOLERANCE = {
    "win32": {"memory_pct": 5.0, "disk_free_pct": 1.5, "cpu_pct": 35.0, "claude_procs": 2},
    "darwin": {"memory_pct": 8.0, "disk_free_pct": 1.5, "cpu_pct": 25.0},
}
# The CPU of a machine moves most between two reads, so a CPU case takes the closest of this many tries.
CPU_TRIES = 3

WINDOWS_SCRIPT = r"""
$os = Get-CimInstance Win32_OperatingSystem
$drive = Get-PSDrive -Name $env:LB_DRIVE
$cpu = (Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'").PercentProcessorTime
[pscustomobject]@{
  memory_pct = 100 * ($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / $os.TotalVisibleMemorySize
  disk_free_pct = 100 * $drive.Free / ($drive.Free + $drive.Used)
  cpu_pct = [double]$cpu
  claude_procs = @(Get-Process -Name claude -ErrorAction SilentlyContinue).Count
} | ConvertTo-Json -Compress
"""


def run(*command, env=None):
    done = subprocess.run(list(command), capture_output=True, text=True, timeout=60, env=env)
    if done.returncode != 0:
        raise RuntimeError("%s exited %d: %s" % (command[0], done.returncode, done.stderr.strip()[:120]))
    return done.stdout


def windows_reference():
    drive = os.path.splitdrive(os.path.expanduser("~"))[0].rstrip(":")
    shell = shutil.which("powershell") or shutil.which("pwsh")
    out = run(shell, "-NoProfile", "-NonInteractive", "-Command", WINDOWS_SCRIPT,
              env=dict(os.environ, LB_DRIVE=drive))
    return json.loads(out)


def mac_reference():
    pressure = run("memory_pressure")
    free = re.search(r"System-wide memory free percentage:\s*(\d+)%", pressure)
    df = run("df", "-k", os.path.expanduser("~")).strip().splitlines()[-1].split()
    load = re.search(r"load averages?:\s*([\d.]+)", run("uptime"))
    cores = int(run("sysctl", "-n", "hw.ncpu").strip())
    return {
        "memory_pct": 100 - int(free.group(1)),
        "disk_free_pct": 100 * int(df[3]) / int(df[1]),
        "cpu_pct": min(100.0, 100 * float(load.group(1)) / cores),
    }


REFERENCE = {"win32": windows_reference, "darwin": mac_reference}


def load_reader():
    """The read_load function of the guard under test, or None."""
    for name in [n for n in sys.modules if n == "guard_core" or n.startswith("guard_")]:
        sys.modules.pop(name, None)   # each load gets modules of its own
    spec = importlib.util.spec_from_file_location("guard_under_test", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    holders = [module] + [m for n, m in list(sys.modules.items())
                          if n.startswith("guard_") and m is not None]
    return next((m.read_load for m in holders if hasattr(m, "read_load")), None)


def check_reading(key, tries=1):
    """The reader's `key` against the OS tool, within the platform's tolerance. Returns (ok, note)."""
    read_load = load_reader()
    if read_load is None:
        return False, "no read_load function in guard.py or a guard_*.py module"
    tolerance = TOLERANCE[sys.platform][key]
    best = None
    for _ in range(tries):
        try:
            reading = read_load()[key]
        except Exception as exc:
            return False, "read_load failed on %s: %s: %s" % (sys.platform, type(exc).__name__, str(exc)[:80])
        if reading is None:
            return False, "read_load left %s unread on %s" % (key, sys.platform)
        reference = REFERENCE[sys.platform]()[key]
        gap = abs(reading - reference)
        if best is None or gap < best[0]:
            best = (gap, reading, reference)
        if gap <= tolerance:
            break
    gap, reading, reference = best
    return (gap <= tolerance,
            "%s read %.1f, the OS tool %.1f, gap %.1f, tolerance %.1f" % (key, reading, reference, gap, tolerance))


CASES = [
    ("memory in use matches the OS tool", lambda: check_reading("memory_pct"), ("win32", "darwin")),
    ("disk free on the home drive matches the OS tool", lambda: check_reading("disk_free_pct"),
     ("win32", "darwin")),
    ("CPU busy matches the OS tool", lambda: check_reading("cpu_pct", CPU_TRIES), ("win32", "darwin")),
    ("the claude process count matches the OS tool", lambda: check_reading("claude_procs"), ("win32",)),
]


def main():
    failed = skipped = ran = 0
    for label, check, platforms in CASES:
        if sys.platform not in platforms:
            skipped += 1
            print("SKIP  %s  (needs %s, this is %s)" % (label, " or ".join(platforms), sys.platform))
            continue
        ran += 1
        ok, note = check()
        failed += 0 if ok else 1
        print("%s  %s  (%s)" % ("PASS" if ok else "FAIL", label, note))
    if failed:
        print("test_guard_load_os FAIL: %d of %d cases wrong, %d skipped" % (failed, ran, skipped))
        return 1
    print("test_guard_load_os PASS: %d of %d cases right, %d skipped" % (ran, ran, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
