#!/usr/bin/env python3
"""Checks that landed-dirs.txt, install.sh, install.ps1, and hooks/guard.py's
CONFIG_FROZEN_DIRS agree on the set of directories that land under ~/.claude.

Four places used to hardcode this set independently (drift already cost commit 9c1efab, which
pruned install.sh land_dir() calls the source no longer defined). Now there is one manifest,
landed-dirs.txt at the repo root. install.sh and both lists in install.ps1 read it at their own
runtime, so they cannot drift from it by construction; this check instead confirms each site is
still wired to the manifest and has not quietly reverted to a hardcoded list. hooks/guard.py
keeps CONFIG_FROZEN_DIRS as a literal on purpose (see the comment beside it there), so this
check parses that literal and compares it against the manifest directly, `state` excepted as a
documented guard-only extra.

Run it from the repository root:

    python3 lint/check_landed_dirs.py

Exits 0 and prints nothing on agreement. Exits 1 and names the disagreeing site otherwise.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

MANIFEST_PATH = os.path.join(REPO_ROOT, "landed-dirs.txt")
INSTALL_SH_PATH = os.path.join(REPO_ROOT, "install.sh")
INSTALL_PS1_PATH = os.path.join(REPO_ROOT, "install.ps1")
GUARD_PY_PATH = os.path.join(REPO_ROOT, "hooks", "guard.py")

# guard.py directories that are never landed by either installer, and why. The "why" string
# must appear verbatim (as a substring) beside the entry in hooks/guard.py, so a comment that
# drifts from the reason it excuses is itself a failure, not a silent pass.
KNOWN_GUARD_ONLY_EXTRAS = {
    "state": "holds the baseline `hooks/config_watch.py` restores a reverted file from",
}


def fail(msg):
    print("check_landed_dirs: FAIL: %s" % msg, file=sys.stderr)
    sys.exit(1)


def read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        fail("cannot read %s: %s" % (path, e))


def parse_manifest(text):
    dirs = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            dirs.append(line)
    if not dirs:
        fail("landed-dirs.txt has no directory lines")
    return dirs


def parse_guard_frozen_dirs(text):
    m = re.search(r"CONFIG_FROZEN_DIRS\s*=\s*\((.*?)\n\)", text, re.DOTALL)
    if not m:
        fail("hooks/guard.py: could not find a CONFIG_FROZEN_DIRS = (...) literal to parse")
    body = m.group(1)
    entries = re.findall(r'os\.path\.normcase\("([^"]+)"\)', body)
    if not entries:
        fail("hooks/guard.py: CONFIG_FROZEN_DIRS parsed but held no os.path.normcase(...) entries")
    for extra, reason_fragment in KNOWN_GUARD_ONLY_EXTRAS.items():
        if extra in entries and reason_fragment not in body:
            fail(
                "hooks/guard.py: CONFIG_FROZEN_DIRS has %r but its comment no longer says %r; "
                "the exception and its reason must not drift apart" % (extra, reason_fragment)
            )
    return entries


def check_install_sh(text, manifest_dirs):
    if "landed-dirs.txt" not in text:
        fail("install.sh: no reference to landed-dirs.txt found; it must read the manifest")
    if 'done < "$SRC/landed-dirs.txt"' not in text:
        fail(
            "install.sh: expected a `done < \"$SRC/landed-dirs.txt\"` loop reading the manifest; "
            "the read site looks different or missing"
        )
    # A literal, bareword land_dir call (land_dir hooks) is the old hardcoded shape. The only
    # call allowed after the fix is the variable-driven one inside the manifest-reading loop.
    stale = re.findall(r"^land_dir\s+([A-Za-z0-9_.\-]+)\s*$", text, re.MULTILINE)
    if stale:
        fail(
            "install.sh: found hardcoded land_dir call(s) for %s outside the manifest loop; "
            "install.sh must land directories only by reading landed-dirs.txt" % stale
        )


def check_install_ps1(text):
    occurrences = text.count("landed-dirs.txt")
    if occurrences < 2:
        fail(
            "install.ps1: expected landed-dirs.txt to be read twice (the main script's own "
            "foreach, and the embedded post-merge hook it writes), found %d reference(s)"
            % occurrences
        )
    if "Join-Path $FromRepoDir 'landed-dirs.txt'" not in text and "Join-Path $RepoDir 'landed-dirs.txt'" not in text:
        fail(
            "install.ps1: the main script's directory list no longer reads landed-dirs.txt via "
            "Get-Content; it looks hardcoded again"
        )
    if "done < \"`$repo/landed-dirs.txt\"" not in text:
        fail(
            "install.ps1: the embedded post-merge hook's directory list no longer reads "
            "landed-dirs.txt; it looks hardcoded again"
        )
    # The old hardcoded shapes this fix removed. If either comes back, something reverted.
    if re.search(r"foreach\s*\(\s*\$sub\s+in\s+@\(\s*'[a-zA-Z]+'", text):
        fail("install.ps1: found a hardcoded @('...') directory list on the main foreach again")
    if re.search(r"for sub in [a-zA-Z]+( [a-zA-Z]+)*;\s*do", text):
        fail("install.ps1: found a hardcoded 'for sub in ...; do' directory list in the embedded hook again")


def main():
    manifest_dirs = parse_manifest(read(MANIFEST_PATH))
    manifest_set = set(manifest_dirs)

    guard_text = read(GUARD_PY_PATH)
    guard_dirs = parse_guard_frozen_dirs(guard_text)
    guard_set = set(guard_dirs) - set(KNOWN_GUARD_ONLY_EXTRAS)

    if guard_set != manifest_set:
        missing_from_guard = manifest_set - guard_set
        extra_in_guard = guard_set - manifest_set
        detail = []
        if missing_from_guard:
            detail.append(
                "landed-dirs.txt has %s that hooks/guard.py's CONFIG_FROZEN_DIRS does not"
                % sorted(missing_from_guard)
            )
        if extra_in_guard:
            detail.append(
                "hooks/guard.py's CONFIG_FROZEN_DIRS has %s that landed-dirs.txt does not "
                "(add it there, or list it in KNOWN_GUARD_ONLY_EXTRAS with its reason)"
                % sorted(extra_in_guard)
            )
        fail("; ".join(detail))

    check_install_sh(read(INSTALL_SH_PATH), manifest_dirs)
    check_install_ps1(read(INSTALL_PS1_PATH))

    print(
        "check_landed_dirs: ok, %d directories agree (%s)"
        % (len(manifest_dirs), ", ".join(manifest_dirs))
    )


if __name__ == "__main__":
    main()
