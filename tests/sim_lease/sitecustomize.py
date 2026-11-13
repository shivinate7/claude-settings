"""The test seam for the machine-load brake that bin/sim-lease grants on. A test puts this folder on PYTHONPATH.

Python imports this file at the start of each sim-lease run that a test starts, before the tool runs. No product code
imports it, and a run without this folder on PYTHONPATH reads the real machine.
  - sys.platform reads "linux", so no Mac-only branch runs. The brake's memory reading is the one SIM_LEASE_TEST_MEMORY
    holds: a percent in use (a float), or "unreadable". With no file it is unread. The brake's own module, guard.py,
    gets that reading in place of the real counter, so a real Mac's memory cannot change a case.
  - shutil.disk_usage reads SIM_LEASE_TEST_DISK, a file that holds "TOTAL_GB FREE_GB", or "unreadable". The brake
    reads the disk through shutil.disk_usage (hooks/guard.py _read_disk), so it judges this disk as it judges a real
    one. Each call appends one line to SIM_LEASE_TEST_DISKLOG, so a case counts the brake's reads.
  - Each child process the run starts appends its program name to SIM_LEASE_TEST_SPAWNLOG, when that is set.
"""
import collections
import importlib.machinery
import os
import shutil
import sys

GIB = 2 ** 30
sys.platform = "linux"
Usage = collections.namedtuple("usage", "total used free")


def append(path, line):
    with open(path, "a") as f:
        f.write(line + "\n")


def disk_usage(path):
    log = os.environ.get("SIM_LEASE_TEST_DISKLOG")
    if log:
        append(log, "read")
    with open(os.environ["SIM_LEASE_TEST_DISK"]) as f:
        words = f.read().split()
    if len(words) < 2:
        raise OSError("the disk reading is unreadable (test seam)")
    total, free = float(words[0]), float(words[1])
    return Usage(total=int(total * GIB), used=int((total - free) * GIB), free=int(free * GIB))


def memory_reading():
    """The brake's memory reading: the percent in SIM_LEASE_TEST_MEMORY, or None when no file is set (unread). A file
    that says "unreadable" raises, as a failed counter does."""
    path = os.environ.get("SIM_LEASE_TEST_MEMORY")
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        words = f.read().split()
    if not words or words[0] == "unreadable":
        raise OSError("the memory reading is unreadable (test seam)")
    return float(words[0])


_exec_module = importlib.machinery.SourceFileLoader.exec_module


def exec_module(self, module):
    """Python runs every module's code through this. The brake's module is the one the tool loads by path, guard.py.
    guard.read_load looks `_read_memory` up at call time, so replacing it here swaps the brake's counter for the knob."""
    _exec_module(self, module)
    if os.path.basename(self.path) == "guard.py":
        module._read_memory = memory_reading


importlib.machinery.SourceFileLoader.exec_module = exec_module


def spawned(event, args):
    log = os.environ.get("SIM_LEASE_TEST_SPAWNLOG")
    if event == "subprocess.Popen" and log:
        argv = args[1]
        first = argv[0] if isinstance(argv, (list, tuple)) and argv else argv
        append(log, os.path.basename(str(first)))


shutil.disk_usage = disk_usage
sys.addaudithook(spawned)
