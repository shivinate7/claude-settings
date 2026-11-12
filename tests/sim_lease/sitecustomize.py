"""The test seam for the machine-load brake that bin/sim-lease grants on. A test puts this folder on PYTHONPATH.

Python imports this file at the start of each sim-lease run that a test starts, before the tool runs. No product code
imports it, and a run without this folder on PYTHONPATH reads the real machine.
  - sys.platform reads "linux", so the brake's memory reading is unread on every host. A real Mac's memory cannot
    change a case, and only the disk can trip the brake.
  - shutil.disk_usage reads SIM_LEASE_TEST_DISK, a file that holds "TOTAL_GB FREE_GB", or "unreadable". The brake
    reads the disk through shutil.disk_usage (hooks/guard.py _read_disk), so it judges this disk as it judges a real
    one. Each call appends one line to SIM_LEASE_TEST_DISKLOG, so a case counts the brake's reads.
  - Each child process the run starts appends its program name to SIM_LEASE_TEST_SPAWNLOG, when that is set.
"""
import collections
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


def spawned(event, args):
    log = os.environ.get("SIM_LEASE_TEST_SPAWNLOG")
    if event == "subprocess.Popen" and log:
        argv = args[1]
        first = argv[0] if isinstance(argv, (list, tuple)) and argv else argv
        append(log, os.path.basename(str(first)))


shutil.disk_usage = disk_usage
sys.addaudithook(spawned)
