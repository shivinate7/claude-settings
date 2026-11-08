"""One shallow-clone fixture for every suite that proves "a cut history reads unknown, never off main".

`git merge-base --is-ancestor A B` exits 1 both when A is not an ancestor of B and when a shallow clone
cut the history between them. A plain `--depth 1` clone lacks A's object, so a read stops for another reason.
The shape that reaches the bug holds A's object and cuts the path to it: a depth-1 clone of the source, then A
fetched at depth 1.

    import shallow_clone
    error = shallow_clone.make(source, dest, pin)        # "" when both git calls worked
    shallow_origin = shallow_clone.origin(source, dest)  # a bare copy of source cut at depth 1: a remote that is itself shallow
    facts = shallow_clone.facts(dest, pin)               # shallow, pin_present, ancestor_rc (1 in the bug shape)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)


def _git(where, *args):
    return _nowindow.run(["git", "-C", where, *args], capture_output=True, text=True)


def make(source, dest, pin):
    """A shallow clone of `source`'s HEAD at `dest` (a path that does not exist yet), with the commit `pin` fetched at
    depth 1. Sets `uploadpack.allowAnySHA1InWant` on `source`, which the fetch of a bare sha needs. Returns the git
    error text, "" when both calls worked."""
    _git(source, "config", "uploadpack.allowAnySHA1InWant", "true")
    made = _nowindow.run(["git", "clone", "-q", "--depth", "1", "--no-local", source, dest], capture_output=True, text=True)
    if made.returncode:
        return made.stderr.strip() or "git clone failed"
    fetched = _git(dest, "fetch", "-q", "--depth", "1", "origin", pin)
    return fetched.stderr.strip() or "git fetch failed" if fetched.returncode else ""


def origin(source, dest):
    """A bare copy of `source` with every branch cut at depth 1 at `dest` (a path that does not exist yet): a remote that is itself
    shallow, so a fetch from it cannot deepen a clone past the cut. Returns `dest`; raises on a failed clone."""
    _nowindow.run(["git", "clone", "-q", "--bare", "--depth", "1", "--no-single-branch", "--no-local", source, dest],
                  capture_output=True, text=True, check=True)
    return dest


def facts(clone, pin, tip="HEAD"):
    """What a case reads before it claims the bug: the clone is shallow, `pin`'s object is present, and
    `merge-base --is-ancestor <pin> <tip>` exits `ancestor_rc` (1 in the bug shape)."""
    return {"shallow": _git(clone, "rev-parse", "--is-shallow-repository").stdout.strip() == "true",
            "pin_present": _git(clone, "cat-file", "-e", pin + "^{commit}").returncode == 0,
            "ancestor_rc": _git(clone, "merge-base", "--is-ancestor", pin, tip).returncode}
