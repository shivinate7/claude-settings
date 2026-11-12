"""A copy of this checkout with no skills/waiting-page folder, for the cases that read the waiting page's collection
list after that folder is gone. lint/layout.py reads the list lazily (WAITING_COLLECTIONS), so a copy with lint/ and
no skill folder still imports, and a read of the list raises LayoutError. One home for the copy: the waiting-page
cases of hooks/test_waiting_export.py and of tests/guard use it. Standard library only.
"""
import os
import shutil

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
TREE_SKIP = shutil.ignore_patterns("test_*", "*_test.py", "__pycache__")


def copy_without_skill(dest):
    """Copy hooks/ and lint/ of this checkout into `dest` (test files and caches left out), and make no skills/
    folder there. Returns the copy's hooks folder: a process run from it finds the copy's lint/ beside it, and no
    waiting-page skill. `dest` is the caller's run folder and must not exist yet."""
    os.makedirs(dest)
    for part in ("hooks", "lint"):
        shutil.copytree(os.path.join(REPO, part), os.path.join(dest, part), ignore=TREE_SKIP)
    return os.path.join(dest, "hooks")
