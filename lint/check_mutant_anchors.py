#!/usr/bin/env python3
"""Fails when a mutant of hooks/mutate_guard.py or janitor/mutate_sweep.py names an anchor that no longer sits exactly once where its
table entry says.

    python3 lint/check_mutant_anchors.py

The mutant table is MUTATIONS in hooks/mutate_guard.py; this script imports it and keeps no copy. A "guard" or "audit" mutant is found
by hooks/mutate_shared.py `find_anchor` across the guard modules: no match is stale, two or more is ambiguous. Any other target is
read in its own file (TARGETS), and the anchor must occur once there. The mutation run reads the same table, but its own pre-check
covers ambiguity only for guard and audit targets. A sweep row (MUTATIONS and SOURCES of janitor/mutate_sweep.py, read at call
time) names its target in SOURCES; its anchor is matched in that one file by `find_anchor`. A merge of main into a lane can move an
anchor. This read covers every anchor in one pass, in about a second, and names each bad one.

Prints `PASS mutant anchor census: N mutants` and exits 0, or one `FAIL` line per bad mutant (a row with too few fields counts) and a closing count line, naming its label, its target and the
file or folder searched, and exits 1. It does not check the required-case name or the mutant file names: the mutation run does.
Cost: one read of each target file and of the guard modules; the sweep module is imported once. No suite, no child process, no file written.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HOOKS)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "janitor"))

import mutate_guard  # noqa: E402
import mutate_shared  # noqa: E402
import mutate_sweep  # noqa: E402  imported by this name, so the table and file map are read from the one module object

SWEEP_TABLE = "janitor/mutate_sweep.py"  # the file a sweep finding names: the table the row sits in
GUARD_TABLE = "hooks/mutate_guard.py"  # the file a guard finding names: the table the row sits in
ROW_FIELDS = 3  # both tables need a label, an anchor and a replacement or target before the census can read a row


def malformed_row(entry, index, table_file):
    """-> a `FAIL ...` line when `entry` has too few fields to read, else None. It names the row's label, or `row N` (0-based) when
    the row has none, and the table, so one short row does not stop the read of the others."""
    if len(entry) >= ROW_FIELDS:
        return None
    name = "%s (row %d)" % (entry[0], index) if entry else "row %d" % index
    return "FAIL malformed row, %d fields where %d are needed, in %s: %s" % (len(entry), ROW_FIELDS, table_file, name)

# A mutant of these targets is anchored across the guard modules (mutate_guard.main), so no target file names it.
GUARD_FAMILY = ("guard", "audit")


def findings(mutations=None, targets=None, hooks=HOOKS):
    """-> a list of `FAIL ...` lines, one per mutant whose anchor is stale, ambiguous or aimed at an unknown target. `mutations`,
    `targets` and `hooks` default to the real table, target map and guard folder; a caller may pass others."""
    table = mutate_guard.MUTATIONS if mutations is None else mutations
    targets = mutate_guard.TARGETS if targets is None else targets
    bad = []
    for index, entry in enumerate(table):
        short = malformed_row(entry, index, GUARD_TABLE)
        if short:
            bad.append(short)
            continue
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


def sweep_findings(mutations=None, sources=None):
    """-> a list of `FAIL ...` lines, one per sweep row whose anchor is stale, ambiguous or aimed at an unknown target. `mutations`
    and `sources` default to MUTATIONS and SOURCES of janitor/mutate_sweep.py, read now so a caller's patch of either is seen."""
    table = mutate_sweep.MUTATIONS if mutations is None else mutations
    sources = mutate_sweep.SOURCES if sources is None else sources
    bad = []
    for index, entry in enumerate(table):
        short = malformed_row(entry, index, SWEEP_TABLE)
        if short:
            bad.append(short)
            continue
        label, target, old = entry[0], entry[1], entry[2]
        if target not in sources:
            bad.append("FAIL unknown mutation target %r in %s: %s" % (target, SWEEP_TABLE, label))
            continue
        folder, name = os.path.split(sources[target])
        try:
            mutate_shared.find_anchor(folder, old, [name])
        except mutate_shared.StaleMutant:
            bad.append("FAIL stale anchor, text not found in %s (sweep target %s, table %s): %s" % (sources[target], target, SWEEP_TABLE, label))
        except mutate_shared.AmbiguousMutant as error:
            bad.append("FAIL ambiguous anchor, %s in %s (sweep target %s, table %s): %s" % (error, sources[target], target, SWEEP_TABLE, label))
    return bad


def main() -> int:
    bad = findings() + sweep_findings()
    total = len(mutate_guard.MUTATIONS) + len(mutate_sweep.MUTATIONS)
    for line in bad:
        print(line)
    if bad:
        print("mutant anchor census failed: %d of %d mutants have a bad row or anchor" % (len(bad), total))
        return 1
    print("PASS mutant anchor census: %d mutants" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
