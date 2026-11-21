#!/usr/bin/env python3
"""CI check: each flat module a guard file imports is in each guard-set list.

The lists are the install.sh copy loop, the install.ps1 copy and set loops, and the ci-scope.sh case
line. hooks/test_install_src.sh reads them in guardset4, guardset7 and guardset8. Only job
checks-install-checkout runs that file, so lane lint (job checks alone) passed a short list that
the install checkout job then failed. This check runs just those three cases and reads the
suite's own verdict lines.

A case counts as passed only when its own `ok` line is printed. A case with no line (the case
list lost it, a name filter matched nothing, or the suite crashed first), a `FAIL` or `SKIP`
line, a timeout, and a non-zero suite exit all read as failure. The check never reads a read that
could not run as a pass.

Run it from the repository root:

    python3 lint/check_guardset_lists.py

Exits 0 when all three cases pass. Exits 1 and names each failing case otherwise.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

CASES = ("guardset4", "guardset7", "guardset8")
SUITE = os.path.join("hooks", "test_install_src.sh")
TIMEOUT = 280  # the three cases run in about 5 s; this is a hang guard


def verdict_line(lines, case):
    """The suite's verdict line for `case` (`ok   - guardset4: ...`), or None when it printed none."""
    for line in lines:
        head = line.split(":", 1)[0]
        if head.startswith(("ok   - ", "FAIL - ", "SKIP - ")) and head.split(" - ", 1)[1] == case:
            return line
    return None


def main() -> int:
    if not os.path.exists(os.path.join(ROOT, SUITE)):
        print("check_guardset_lists: FAIL, %s does not exist" % SUITE)
        return 1
    try:
        done = _nowindow.run(["sh", SUITE, *CASES], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    except OSError as e:
        print("check_guardset_lists: FAIL, could not run %s: %s" % (SUITE, e))
        return 1
    except Exception as e:  # a timeout reads as a failure, never as a pass
        print("check_guardset_lists: FAIL, %s did not finish: %s" % (SUITE, e))
        return 1
    lines = done.stdout.splitlines()
    failing = []
    for case in CASES:
        line = verdict_line(lines, case)
        if line is None:
            failing.append("%s: no verdict line, the case did not run" % case)
        elif not line.startswith("ok"):
            failing.append(line)
    if failing:
        for item in failing:
            print("FAIL  %s" % item)
        print("check_guardset_lists: FAIL, %d of %d cases failed" % (len(failing), len(CASES)))
        if done.returncode != 0:
            print("\n".join((done.stdout + done.stderr).splitlines()[-30:]))
        return 1
    if done.returncode != 0:
        print("check_guardset_lists: FAIL, every case passed but %s exited %d" % (SUITE, done.returncode))
        print("\n".join(done.stderr.splitlines()[-30:]))
        return 1
    print("check_guardset_lists: OK, %s all pass" % ", ".join(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
