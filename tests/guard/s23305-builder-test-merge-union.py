# section 23305
# A builder's merge that resolves a conflict in a test file where both parents add entries to one statement that holds
# no test case: a case tuple inside a function (test_question_form.py's main()), or a module-level table. A result that
# keeps every entry of both parents is a correct union. The reader refuses it as lost, since the base version is in
# neither parent (`_edit_dropped`), and as body, since the result statement is in neither parent.
# RED on the current guard: the union cases (`_mt_allow`). GREEN controls pin today's verdicts: a union that drops one
# parent's entry is refused as lost, a union that adds an entry neither parent had is refused, a deliberate removal is
# refused as lost, and a one-sided edit of the same statement is allowed when the result keeps it and refused as lost
# when the result drops it. The one-sided edits of a case body are s23302's, and of a table, a helper and a decorator
# are s23304's.
# The fixtures reuse s23300's case helpers (_mt_case, _mt_allow, _mt_refuse, MT_CARRY, MT_BASE, MT_LANE, MT_MAIN,
# BASE_FILES, TEST_A), so this section adds no copy of them.
_MU5_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

MU5_BASE_E = "('base', 0)"
MU5_LANE_E = "(\"lane's # case\", 1)"
MU5_MAIN_E = "('main', 2)"
MU5_MAIN_E2 = "('main two', 3)"
MU5_NEW_E = "('builder', 4)"
MU5_SCAN_E = "'''row\n# not a comment\n'''"


def _mu5_main(*entries):
    """A test file's main(), holding one case tuple with one entry per line, each with a trailing comma."""
    return "def main():\n    cases = (\n" + "".join("        %s,\n" % e for e in entries) + "    )\n    return cases\n"


def _mu5_table(*entries):
    """A module-level table, one entry per line, each with a trailing comma."""
    return "TABLE = [\n" + "".join("    %s,\n" % e for e in entries) + "]\n"


# ---- RED: a union that keeps every entry of both parents is allowed ----
# The incident shape: each side adds an entry to main()'s tuple at the same place. The base holds one entry.
MU5_UNION = _mt_case("mt5-union-main-tuple", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E))],
                     [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E))], [TEST_A],
                     resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E, MU5_MAIN_E))], stage=True,
                     files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' entries of a case tuple in main() is allowed",
          MU5_UNION)

# Full-size state: each side adds thirty entries to the tuple, and the union keeps all sixty.
MU5_LANE_FULL = ["('lane_%02d', %d)" % (n, n) for n in range(30)]
MU5_MAIN_FULL = ["('main_%02d', %d)" % (n, n + 100) for n in range(30)]
MU5_UNION_FULL = _mt_case("mt5-union-main-tuple-full",
                          [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, *MU5_LANE_FULL))],
                          [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, *MU5_MAIN_FULL))], [TEST_A],
                          resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, *(MU5_LANE_FULL + MU5_MAIN_FULL)))],
                          stage=True, files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_allow("builder-refuse: a builder's open merge that keeps thirty entries from each side of a case tuple in main() is "
          "allowed", MU5_UNION_FULL)

# Empty state: the base holds no test case, and its tuple holds no entry. Each side adds one entry.
MU5_UNION_EMPTY = _mt_case("mt5-union-main-tuple-empty", [(TEST_A, _mu5_main(MU5_LANE_E))],
                           [(TEST_A, _mu5_main(MU5_MAIN_E))], [TEST_A],
                           resolve=[(TEST_A, _mu5_main(MU5_LANE_E, MU5_MAIN_E))], stage=True,
                           files={**BASE_FILES, TEST_A: _mu5_main()})
_mt_allow("builder-refuse: a builder's open merge into an empty case tuple, each side adds one entry and both are kept, "
          "is allowed", MU5_UNION_EMPTY)

# A module-level table: each side adds one entry, and the union keeps both. One entry is a triple-quoted string whose
# second line opens with a comment mark, which is no comment inside a string.
MU5_UNION_TABLE = _mt_case("mt5-union-table", [(TEST_A, MT_BASE + _mu5_table(MU5_BASE_E, MU5_LANE_E))],
                           [(TEST_A, MT_BASE + _mu5_table(MU5_BASE_E, MU5_SCAN_E))], [TEST_A],
                           resolve=[(TEST_A, MT_BASE + _mu5_table(MU5_BASE_E, MU5_LANE_E, MU5_SCAN_E))], stage=True,
                           files={**BASE_FILES, TEST_A: MT_BASE + _mu5_table(MU5_BASE_E)})
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' entries of a module-level table is allowed",
          MU5_UNION_TABLE)


# ---- GREEN: a union that drops an entry of either parent stays refused, as lost ----
# The result keeps the lane's entries and drops main's entry.
MU5_DROP_MAIN = _mt_case("mt5-drop-main-entry", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E))],
                         [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E))], [TEST_A],
                         resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E))], stage=True,
                         files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: a merge of a case tuple that keeps the lane's entries and drops main's entry is refused as "
           "lost", MU5_DROP_MAIN, "lost", (MT_CARRY["lost"],))

# The mirror: the result keeps main's entries and drops the lane's entry.
MU5_DROP_LANE = _mt_case("mt5-drop-lane-entry", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E))],
                         [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E))], [TEST_A],
                         resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E))], stage=True,
                         files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: a merge of a case tuple that keeps main's entries and drops the lane's entry is refused as "
           "lost", MU5_DROP_LANE, "lost", (MT_CARRY["lost"],))

# Each side is represented, but main's second entry is dropped. A check that only asks whether each side appears in the
# result would allow this, so it stays refused.
MU5_DROP_ONE = _mt_case("mt5-union-drops-one-entry", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E))],
                        [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E, MU5_MAIN_E2))], [TEST_A],
                        resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E, MU5_MAIN_E))], stage=True,
                        files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: a merge that keeps both sides of a case tuple but drops main's second entry is refused as "
           "lost", MU5_DROP_ONE, "lost", (MT_CARRY["lost"],))

# A union that adds an entry neither parent had is refused. The reason may be lost, body or new, since the class
# depends on the fix.
MU5_ADD_NEW = _mt_case("mt5-union-adds-entry", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E))],
                       [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E))], [TEST_A],
                       resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E, MU5_MAIN_E, MU5_NEW_E))], stage=True,
                       files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: a merge that keeps both sides of a case tuple and adds an entry neither parent had is refused",
           MU5_ADD_NEW, ("lost", "body", "new"), (MT_CARRY["lost"] + MT_CARRY["body"] + MT_CARRY["new"],))

# A deliberate removal: the lane deletes the base entry, and main keeps it and adds one. The result honours the removal,
# and keeps main's entry. Today the reader refuses it as lost.
MU5_REMOVE_ENTRY = _mt_case("mt5-deliberate-entry-removal", [(TEST_A, MT_BASE + _mu5_main())],
                            [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E))], [TEST_A],
                            resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_MAIN_E))], stage=True,
                            files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: a merge that honours the lane's deliberate removal of a case-tuple entry is refused as lost",
           MU5_REMOVE_ENTRY, "lost", (MT_CARRY["lost"],))

# A deliberate removal of a test case, which the reader names as a gap (debt merge-deliberate-case-removal-unhonoured).
# The lane deletes test_a and adds its own case, and main keeps test_a and adds one. Today the result is refused as lost.
MU5_REMOVE_CASE = _mt_case("mt5-deliberate-case-removal", [(TEST_A, MT_LANE)],
                           [(TEST_A, MT_BASE + MT_MAIN)], [TEST_A], resolve=[(TEST_A, MT_LANE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that honours the lane's deliberate deletion of a test case is refused as lost",
           MU5_REMOVE_CASE, "lost", (MT_CARRY["lost"],))


# ---- CONTROLS: a one-sided edit of the same statement keeps its verdict. The conflict sits at the end of the file, so
# the edit to the statement merges clean and only the appended cases conflict.
# The lane edits the tuple, and the result keeps the lane's edit: allowed.
MU5_ONE_LANE_KEPT = _mt_case("mt5-one-side-lane-kept", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E) + MT_LANE)],
                             [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E) + MT_MAIN)], [TEST_A],
                             resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E) + MT_LANE + MT_MAIN)],
                             stage=True, files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_allow("builder-refuse: control, a merge that keeps the lane's one-sided edit of a case tuple, with both sides' appended "
          "cases, is allowed", MU5_ONE_LANE_KEPT)

# Main edits the tuple, and the result keeps main's edit: allowed.
MU5_ONE_MAIN_KEPT = _mt_case("mt5-one-side-main-kept", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E) + MT_LANE)],
                             [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E) + MT_MAIN)], [TEST_A],
                             resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E) + MT_LANE + MT_MAIN)],
                             stage=True, files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_allow("builder-refuse: control, a merge that keeps main's one-sided edit of a case tuple, with both sides' appended "
          "cases, is allowed", MU5_ONE_MAIN_KEPT)

# The lane edits the tuple, and the result drops that edit: refused as lost.
MU5_ONE_LANE_DROPPED = _mt_case("mt5-one-side-lane-dropped", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_LANE_E) + MT_LANE)],
                                [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E) + MT_MAIN)], [TEST_A],
                                resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E) + MT_LANE + MT_MAIN)], stage=True,
                                files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: control, a merge that drops the lane's one-sided edit of a case tuple is refused as lost",
           MU5_ONE_LANE_DROPPED, "lost", (MT_CARRY["lost"],))

# Main edits the tuple, and the result drops that edit: refused as lost.
MU5_ONE_MAIN_DROPPED = _mt_case("mt5-one-side-main-dropped", [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E) + MT_LANE)],
                                [(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E, MU5_MAIN_E) + MT_MAIN)], [TEST_A],
                                resolve=[(TEST_A, MT_BASE + _mu5_main(MU5_BASE_E) + MT_LANE + MT_MAIN)], stage=True,
                                files={**BASE_FILES, TEST_A: MT_BASE + _mu5_main(MU5_BASE_E)})
_mt_refuse("builder-refuse: control, a merge that drops main's one-sided edit of a case tuple is refused as lost",
           MU5_ONE_MAIN_DROPPED, "lost", (MT_CARRY["lost"],))

FAMILY = _MU5_PRIOR_FAMILY
