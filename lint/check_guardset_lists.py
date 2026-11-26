#!/usr/bin/env python3
"""CI check: the guard set is one list, the manifest hooks/guard-set.txt, and each flat module a guard file imports is in it.

The manifest is one file name per line, sorted, none twice, each a file in hooks/, in the form of landed-dirs.txt.
install.sh, install.ps1 (its PowerShell set loop and the post-merge hook it writes) and .github/scripts/ci-scope.sh read it at
run time and hold no list of their own. This check holds four things:

  form     the manifest exists, has an entry, is sorted, repeats none, and names a file in hooks/ for each entry.
  copies   no line of install.sh, install.ps1 or ci-scope.sh names eight or more of its entries: that is a copy, and a copy
           drifts (the old copies had: ci-scope.sh lacked lease.py, the comments lacked answered_claims.py). The scan reads
           text, never the language, so a name in a comment, in a string after a `#`, after a lone quote or in the here-string
           that holds the hook is counted. A line that sets the `shoot` flag is no copy: ci-scope.sh's shoot arm names the
           page export suite's own import list, which lint/test_ci_scope.py walks.
  readers  install.sh, install.ps1 outside the here-string, and the here-string (the post-merge hook) each name the manifest
           in a line that is no comment. Without that a file holds no list and reads none.
  cases    hooks/test_install_src.sh guardset4, guardset7 and guardset8 name each flat module a guard file imports in the
           manifest. Only job checks-install-checkout runs that file, so lane lint (job checks alone) passed a short manifest
           that the install checkout job then failed. This check runs just those cases and reads the suite's own verdict lines.

A case counts as passed only when its own `ok` line is printed. A case with no line (the case list lost it, a name filter matched
nothing, or the suite crashed first), a `FAIL` or `SKIP` line, a timeout, and a non-zero suite exit all read as failure. The check
never reads a read that could not run as a pass.

Run it from the repository root:

    python3 lint/check_guardset_lists.py

Exits 0 when the form, copies, readers and the three cases all pass. Exits 1 and names each failure otherwise.
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "hooks"))
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)

CASES = ("guardset4", "guardset7", "guardset8")
SUITE = os.path.join("hooks", "test_install_src.sh")
TIMEOUT = 280  # the three cases run in about 5 s; this is a hang guard
MANIFEST = "hooks/guard-set.txt"  # the one list of the guard set's files, beside the guard files it adds to
COPY_AT = 8  # a line naming this many manifest entries is a copy of the list
INSTALL_SH, INSTALL_PS1, CI_SCOPE = "install.sh", "install.ps1", ".github/scripts/ci-scope.sh"
COPY_SCAN = (INSTALL_SH, INSTALL_PS1, CI_SCOPE)
HOOK_OPEN = re.compile(r'^\s*\$hook\s*=\s*@"\s*$')  # install.ps1 opens the post-merge hook's here-string with this line
HOOK_CLOSE = re.compile(r'^"@\s*$')
NAME_CHARS = re.compile(r"[^A-Za-z0-9_.\-]+")  # a file name holds none of these, so splitting at them leaves whole names


def verdict_line(lines, case):
    """The suite's verdict line for `case` (`ok   - guardset4: ...`), or None when it printed none."""
    for line in lines:
        head = line.split(":", 1)[0]
        if head.startswith(("ok   - ", "FAIL - ", "SKIP - ")) and head.split(" - ", 1)[1] == case:
            return line
    return None


def read_text(rel):
    """The text of repo file `rel`, or None when it cannot be read."""
    try:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8", newline="") as f:
            return f.read()
    except OSError:
        return None


def manifest_entries(text):
    """The entries of a manifest text, in order: `#` to the line end, outer blanks and empty lines dropped, any line end."""
    out = []
    for line in text.splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            out.append(entry)
    return out


def check_form(entries):
    """Failures of the manifest's form. `entries` is None when the file cannot be read."""
    if entries is None:
        return ["%s: cannot be read, so no module can be in the guard-set list" % MANIFEST]
    if not entries:
        return ["%s: names no file; the guard set needs at least one entry" % MANIFEST]
    failing = []
    seen = set()
    for i, entry in enumerate(entries):
        if entry in seen:
            failing.append("%s: %s is listed twice" % (MANIFEST, entry))
        seen.add(entry)
        if i and entry < entries[i - 1]:
            failing.append("%s: %s is out of order, after %s (sorted by code point, one name per line)" % (MANIFEST, entry, entries[i - 1]))
        if os.path.basename(entry) != entry or not os.path.isfile(os.path.join(ROOT, "hooks", entry)):
            failing.append("%s: %s is not a file in hooks/" % (MANIFEST, entry))
    return failing


def check_copies(entries):
    """Failures for a line that names COPY_AT or more manifest entries, in install.sh, install.ps1 or ci-scope.sh."""
    failing = []
    names = set(entries)
    for rel in COPY_SCAN:
        text = read_text(rel)
        if text is None:
            failing.append("%s: cannot be read, so it is not known to hold no copy of the guard-set list" % rel)
            continue
        for number, line in enumerate(text.splitlines(), 1):
            tokens = set(NAME_CHARS.split(line))
            if rel == CI_SCOPE and "shoot" in tokens:
                continue
            hit = tokens & names
            if len(hit) >= COPY_AT:
                failing.append("%s:%d: names %d of the guard-set files, a copy of the list; the list is %s" % (rel, number, len(hit), MANIFEST))
    return failing


def reads_manifest(lines):
    """True when a line of `lines` names the manifest and is no comment."""
    return any("guard-set.txt" in line and not line.lstrip().startswith("#") for line in lines)


def check_readers():
    """Failures: install.sh, install.ps1 outside its here-string, and the here-string each read the manifest."""
    failing = []
    sh = read_text(INSTALL_SH)
    if sh is None:
        failing.append("%s: cannot be read, so it is not known to read %s" % (INSTALL_SH, MANIFEST))
    elif not reads_manifest(sh.splitlines()):
        failing.append("%s: never names %s outside a comment, so it reads no guard set" % (INSTALL_SH, MANIFEST))
    ps = read_text(INSTALL_PS1)
    if ps is None:
        failing.append("%s: cannot be read, so it is not known to read %s" % (INSTALL_PS1, MANIFEST))
        return failing
    inside, outside, in_hook = [], [], False
    for line in ps.splitlines():
        if in_hook and HOOK_CLOSE.match(line):
            in_hook = False
        elif in_hook:
            inside.append(line)
        else:
            outside.append(line)
            if HOOK_OPEN.match(line):
                in_hook = True
    if not reads_manifest(outside):
        failing.append("%s: never names %s in PowerShell (outside the post-merge hook's here-string)" % (INSTALL_PS1, MANIFEST))
    if not reads_manifest(inside):
        failing.append("%s: the post-merge hook it writes never names %s outside a comment" % (INSTALL_PS1, MANIFEST))
    return failing


def run_cases():
    """(failing lines, tail to print or '') for the three suite cases."""
    if not os.path.exists(os.path.join(ROOT, SUITE)):
        return ["%s does not exist" % SUITE], ""
    try:
        done = _nowindow.run(["sh", SUITE, *CASES], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    except OSError as e:
        return ["could not run %s: %s" % (SUITE, e)], ""
    except Exception as e:  # a timeout reads as a failure, never as a pass
        return ["%s did not finish: %s" % (SUITE, e)], ""
    lines = done.stdout.splitlines()
    failing = []
    for case in CASES:
        line = verdict_line(lines, case)
        if line is None:
            failing.append("%s: no verdict line, the case did not run" % case)
        elif not line.startswith("ok"):
            failing.append(line)
    if failing:
        return failing, ("\n".join((done.stdout + done.stderr).splitlines()[-30:]) if done.returncode != 0 else "")
    if done.returncode != 0:
        return ["every case passed but %s exited %d" % (SUITE, done.returncode)], "\n".join(done.stderr.splitlines()[-30:])
    return [], ""


def main() -> int:
    text = read_text(MANIFEST)
    entries = manifest_entries(text) if text is not None else None
    failing = check_form(entries)
    if entries:
        failing += check_copies(entries)
    failing += check_readers()
    case_failing, tail = run_cases()
    failing += case_failing
    if failing:
        for item in failing:
            print("FAIL  %s" % item)
        print("check_guardset_lists: FAIL, %d failure(s) in the manifest %s, its copies and readers, and %s" % (len(failing), MANIFEST, ", ".join(CASES)))
        if tail:
            print(tail)
        return 1
    print("check_guardset_lists: OK, %s holds %d entries and no copy, the readers name it, %s all pass" % (MANIFEST, len(entries), ", ".join(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
