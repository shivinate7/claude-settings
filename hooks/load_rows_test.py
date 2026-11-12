"""The machine-load readings that both callers judge alike: the guard (hooks/test_guard.py, family load-brake)
and bin/sim-lease (lint/test_sim_lease.py). Plain data, no test cases.

Each row names the readings and the level the ruling gives them (decision one-load-definition, "Levels"), written
here by hand. Neither suite derives the level from guard_load.load_verdict, so a wrong verdict fails the rows and
is not hidden by the same code on both sides. Disk values are GB: free and total of the drive that holds the home
folder. A reading set to None, or to a value that is not a number (a bool included), is unread, as guard_load
counts it.

Each caller's act on a row, from the ruling:
  guard, an Agent or Task call with run_in_background true, and any Workflow: refused unless the level is normal.
  guard, an Agent or Task call that leaves run_in_background out: refused only at full.
  sim-lease: a grant needs a level that is not full and no unread reading; slot 2 also needs a normal level.
  Unread counts as normal for the guard only.
"""

ROWS = (
    {"name": "idle", "reading": {"memory_pct": 40.0, "disk_free_gb": 500.0, "disk_total_gb": 926.0},
     "level": "normal"},
    {"name": "memory 85.0, at the busy line", "reading": {"memory_pct": 85.0, "disk_free_gb": 500.0,
                                                          "disk_total_gb": 926.0}, "level": "normal"},
    {"name": "memory 85.1, just over the busy line", "reading": {"memory_pct": 85.1, "disk_free_gb": 500.0,
                                                                 "disk_total_gb": 926.0}, "level": "busy"},
    {"name": "memory 90.0, busy", "reading": {"memory_pct": 90.0, "disk_free_gb": 500.0,
                                                "disk_total_gb": 926.0}, "level": "busy"},
    {"name": "memory 95.0, at the full line", "reading": {"memory_pct": 95.0, "disk_free_gb": 500.0,
                                                           "disk_total_gb": 926.0}, "level": "busy"},
    {"name": "memory 95.1, just over the full line", "reading": {"memory_pct": 95.1, "disk_free_gb": 500.0,
                                                                 "disk_total_gb": 926.0}, "level": "full"},
    {"name": "926 GB disk, 15.0 GB free, at the GB cap", "reading": {"memory_pct": 40.0, "disk_free_gb": 15.0,
                                                                     "disk_total_gb": 926.0}, "level": "normal"},
    {"name": "926 GB disk, 14.9 GB free, under the GB cap", "reading": {"memory_pct": 40.0, "disk_free_gb": 14.9,
                                                                        "disk_total_gb": 926.0}, "level": "busy"},
    {"name": "926 GB disk, 4.9 GB free, under the full GB cap", "reading": {"memory_pct": 40.0,
                                                                            "disk_free_gb": 4.9,
                                                                            "disk_total_gb": 926.0},
     "level": "full"},
    {"name": "926 GB disk, 5.0 GB free, at the full GB cap", "reading": {"memory_pct": 40.0, "disk_free_gb": 5.0,
                                                                        "disk_total_gb": 926.0}, "level": "busy"},
    {"name": "50 GB disk, 5.1 GB free, above the busy share", "reading": {"memory_pct": 40.0, "disk_free_gb": 5.1,
                                                                          "disk_total_gb": 50.0}, "level": "normal"},
    {"name": "50 GB disk, 4.9 GB free, under the busy share", "reading": {"memory_pct": 40.0, "disk_free_gb": 4.9,
                                                                          "disk_total_gb": 50.0}, "level": "busy"},
    {"name": "50 GB disk, 2.6 GB free, above the full share", "reading": {"memory_pct": 40.0, "disk_free_gb": 2.6,
                                                                          "disk_total_gb": 50.0}, "level": "busy"},
    {"name": "50 GB disk, 2.4 GB free, under the full share", "reading": {"memory_pct": 40.0, "disk_free_gb": 2.4,
                                                                          "disk_total_gb": 50.0}, "level": "full"},
    {"name": "100 GB disk, 12.0 GB free: the 10 GB share applies", "reading": {"memory_pct": 40.0,
                                                                              "disk_free_gb": 12.0,
                                                                              "disk_total_gb": 100.0},
     "level": "normal"},
    {"name": "500 GB disk, 20.0 GB free: the 15 GB cap applies", "reading": {"memory_pct": 40.0,
                                                                             "disk_free_gb": 20.0,
                                                                             "disk_total_gb": 500.0},
     "level": "normal"},
    {"name": "memory unread, disk normal", "reading": {"memory_pct": None, "disk_free_gb": 500.0,
                                                        "disk_total_gb": 926.0}, "level": "normal"},
    {"name": "memory unread, disk full", "reading": {"memory_pct": None, "disk_free_gb": 4.9,
                                                      "disk_total_gb": 926.0}, "level": "full"},
    {"name": "disk unread, memory 96.0", "reading": {"memory_pct": 96.0, "disk_free_gb": None,
                                                      "disk_total_gb": None}, "level": "full"},
    {"name": "disk unread, memory 90.0", "reading": {"memory_pct": 90.0, "disk_free_gb": None,
                                                      "disk_total_gb": None}, "level": "busy"},
    {"name": "disk free unread, disk total known", "reading": {"memory_pct": 40.0, "disk_free_gb": None,
                                                                "disk_total_gb": 926.0}, "level": "normal"},
    {"name": "both unread", "reading": {"memory_pct": None, "disk_free_gb": None, "disk_total_gb": None},
     "level": "normal"},
    # A bool is not a number: guard_load reads it as unread, not as 1.0 (memory) or 1.0 GB (disk).
    {"name": "memory a bool, disk normal", "reading": {"memory_pct": True, "disk_free_gb": 500.0,
                                                       "disk_total_gb": 926.0}, "level": "normal"},
    {"name": "disk free a bool, disk total known", "reading": {"memory_pct": 40.0, "disk_free_gb": True,
                                                              "disk_total_gb": 926.0}, "level": "normal"},
)


def unread(row):
    """True when a row holds an unread reading: a None value, or a value that is not a number (a bool included)."""
    return any(value is None or isinstance(value, bool) or not isinstance(value, (int, float))
               for value in row["reading"].values())
