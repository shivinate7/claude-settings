#!/usr/bin/env python3
"""Fails when a mutant of hooks/mutate_guard.py names an anchor that no longer sits exactly once where its table entry says.

    python3 lint/check_mutant_anchors.py

The mutant table is MUTATIONS in hooks/mutate_guard.py; this script imports it and keeps no copy. A "guard" or "audit" mutant is found
by hooks/mutate_shared.py `find_anchor` across the guard modules: no match is stale, two or more is ambiguous. Any other target is
read in its own file (TARGETS), and the anchor must occur once there. The mutation run reads the same table, but its own pre-check
covers ambiguity only for guard and audit targets. A merge of main into a lane can move an anchor. This read covers every anchor in one pass,
in about a second, and names each bad one.

Prints `PASS mutant anchor census: N mutants` and exits 0, or one `FAIL` line per bad mutant, naming its label, its target and the
file or folder searched, and exits 1. It does not check the required-case name or the mutant file names: the mutation run does.
Cost: one read of each target file and of the guard modules. No suite, no child process, no file written.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HOOKS)

import mutate_guard  # noqa: E402
import mutate_shared  # noqa: E402

# A mutant of these targets is anchored across the guard modules (mutate_guard.main), so no target file names it.
GUARD_FAMILY = ("guard", "audit")


def findings(mutations=None, targets=None, hooks=HOOKS):
    """-> a list of `FAIL ...` lines, one per mutant whose anchor is stale, ambiguous or aimed at an unknown target. `mutations`,
    `targets` and `hooks` default to the real table, target map and guard folder; a caller may pass others."""
    table = mutate_guard.MUTATIONS if mutations is None else mutations
    targets = mutate_guard.TARGETS if targets is None else targets
    bad = []
    for entry in table:
        label, old, _new, target, _required, _only_on = mutate_guard.mutation_parts(entry)
        if target not in targets:
            bad.append("FAIL unknown mutation target %r: %s" % (target, label))
        elif target in GUARD_FAMILY:
            try:
                mutate_shared.find_anchor(hooks, old)
            except mutate_shared.StaleMutant:
                bad.append("FAIL stale anchor, text not found in the guard modules of %s: %s" % (hooks, label))
            except mutate_shared.AmbiguousMutant as error:
                bad.append("FAIL ambiguous anchor, %s: %s" % (error, label))
        else:
            path = targets[target][0]
            with open(path, encoding="utf-8") as handle:
                count = handle.read().count(old)
            if count != 1:
                bad.append("FAIL %s anchor, text found %d times in %s (target %s): %s"
                           % ("stale" if count == 0 else "ambiguous", count, path, target, label))
    return bad


def main() -> int:
    bad = findings()
    for line in bad:
        print(line)
    if bad:
        print("FAIL mutant anchor census: %d of %d mutants have a stale or ambiguous anchor" % (len(bad), len(mutate_guard.MUTATIONS)))
        return 1
    print("PASS mutant anchor census: %d mutants" % len(mutate_guard.MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
