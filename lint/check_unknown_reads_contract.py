#!/usr/bin/env python3
"""CI check: a read that could not run is reported as unknown, never as clear or broken.

THE CONTRACT, stated once so a later addition has a rule to meet rather than a pattern to
copy. CLAUDE.md: "Verify a claim before you rely on it, and report a read that could not
run as unknown, never as clear or broken." A caller that cannot read a subject has exactly
three honest answers: the subject is clear, the subject is not clear, or the read itself
failed and the caller does not know which. Folding that third answer into either of the
first two is the defect this check exists to catch: a silent allow reads as "nothing is
wrong", and a silent deny reads as "this is unsafe", when the true state is "unread".

WHY THIS IS BEHAVIOURAL, NOT A GREP. An earlier draft of this check planned to scan the
source tree for phrases such as "cannot read" and call that coverage. decisions/
predicate-is-the-act.md already paid for that lesson: a phrase list grows one shape at a
time and never finishes, and it passes on a branch that spells the same failure a different
way. This check instead REPRODUCES the failure -- makes the read genuinely fail -- and
reads the code's own answer back, the way hooks/mutate_guard.py proves a rule catches its
own defect rather than assuming a green run means the rule exists.

THE CONTRACT'S MEMBERS, today. Each one drives a real failure and asserts the unknown
token, never a bare allow or a bare deny:

  - guard: hooks/test_guard.py's `subject_unread_log_case` points the guard at a real git
    repository with a blind `git` on PATH, so `git status --porcelain` genuinely cannot
    answer. The guard must still allow the call (a refusal on this ground would be a guess),
    but it must log `noted`/`subject-unread`, a line distinct from every refusal and from a
    silent allow.
  - session_start: hooks/test_install_src.sh's `caseF4` points the pointer checkout at a
    remote that does not exist, and `caseF6` kills the `git fetch` mid-flight with
    `CLAUDE_SETTINGS_FETCH_TIMEOUT=0`. Both must print the line ending "freshness unknown"
    rather than staying silent or reporting a stale/fresh verdict they never confirmed.
  - liveness: hooks/test_guard.py's `process_start_ms_case` puts a `ps` on PATH that exits 2
    with no output, so `guard._process_start_ms` genuinely cannot tell whether the pid is
    alive or dead. This member's "unknown" token is not a string: it is the distinct sentinel
    `guard.PROCESS_START_UNREADABLE`, never `None` (the CONFIRMED-dead answer) and never an
    int (the alive answer). A read that folds this sentinel into either neighbor is the
    defect this contract exists to catch. The token stays a return value here, not a log
    line.

TO ADD A THIRD MEMBER: write a fixture that makes some other read genuinely fail (not a
string that names failure), have the code under test answer with a token that contains
"unknown" and is distinct from its allow/clear and deny/broken outputs, then add one entry
to MEMBERS below that drives that fixture and checks for the token. The check grows by
fixture. A member that does not reproduce a real failure does not belong here.

Run it from the repository root:

    python3 lint/check_unknown_reads_contract.py

Exits 0 and prints one line per member on success. Exits 1 and names the member (and, for
the shell member, which case) that went silent otherwise.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TEST_INSTALL_SRC = os.path.join(ROOT, "hooks", "test_install_src.sh")

sys.path.insert(0, os.path.join(HERE, "..", "hooks"))


def guard_subject_unread_member() -> Tuple[bool, str]:
    """Reuse hooks/test_guard.py's own fixture. Import, not re-implement: the blind-`git`
    setup that makes the read genuinely fail already lives there, and a second copy of it
    here would be exactly the drift this file's rules elsewhere warn against."""
    try:
        import test_guard
    except ImportError as e:
        return False, "could not import hooks/test_guard.py: %s" % e
    ok, detail = test_guard.subject_unread_log_case()
    return ok, detail


def session_start_freshness_unknown_member() -> Tuple[bool, str]:
    """Reuse hooks/test_install_src.sh's own caseF4 and caseF6 wholesale, by running the
    real suite and reading its real verdict lines, rather than re-driving a fetch failure
    and a fetch timeout a second time in Python."""
    if not os.path.exists(TEST_INSTALL_SRC):
        return False, "hooks/test_install_src.sh does not exist"
    result = subprocess.run(
        ["sh", TEST_INSTALL_SRC], capture_output=True, text=True, timeout=180,
    )
    lines = result.stdout.splitlines()
    missing = []
    for case in ("caseF4", "caseF6"):
        matches = [ln for ln in lines if case in ln]
        if not matches:
            missing.append("%s did not run" % case)
        elif not any(ln.startswith("ok") for ln in matches):
            missing.append("%s did not pass: %s" % (case, matches[0]))
    if missing:
        return False, "; ".join(missing)
    return True, "caseF4 and caseF6 both report freshness unknown"


def liveness_unreadable_member() -> Tuple[bool, str]:
    """Reuse hooks/test_guard.py's own fixture. Do not re-implement it. The fake-`ps` setup
    lives there. It makes the read genuinely fail."""
    try:
        import test_guard
    except ImportError as e:
        return False, "could not import hooks/test_guard.py: %s" % e
    ok, detail = test_guard.process_start_ms_case()
    return ok, detail


MEMBERS = (
    ("guard: an unreadable git-status subject logs noted/subject-unread, not a bare allow",
     guard_subject_unread_member),
    ("session_start: an unreachable or timed-out origin fetch prints freshness unknown",
     session_start_freshness_unknown_member),
    ("liveness: an unreadable ps read answers PROCESS_START_UNREADABLE, "
     "distinct from alive and confirmed-dead",
     liveness_unreadable_member),
)


def main() -> None:
    failed = 0
    for label, member in MEMBERS:
        ok, detail = member()
        print("%s  %s  (%s)" % ("PASS" if ok else "FAIL", label, detail))
        if not ok:
            failed += 1
    if failed:
        print("check_unknown_reads_contract: FAIL, %d of %d members silent" % (
            failed, len(MEMBERS)))
        sys.exit(1)
    print("check_unknown_reads_contract: OK, %d of %d members report unknown on a real failure" % (
        len(MEMBERS), len(MEMBERS)))


if __name__ == "__main__":
    main()
