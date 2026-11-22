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


# ---- A case that a parent renamed or whose verdict a parent flipped is held, not lost (decision merge-union-reads-lost) ----
# One parent renames a case's description or its function, or flips its expected verdict. The other parent keeps the old
# text and adds a case. A result that takes the first parent's text holds every case, so it is allowed, though the other
# parent's old text is no longer in it. The rows are plain calls: the files are parsed, never run.
# The controls stay refused as lost: a deleted call, call and function, row or twin row, a rename that comes with a
# deletion, and a function that both parents changed where the result drops either parent's edit. The result holds
# fewer of that case than a parent does, or drops a parent's edit.
# The edit and the lane's new row are adjacent, so the merge conflicts at the end of the file. The full-size case edits a
# row in the middle (a clean merge) and conflicts on the rows both sides append at the end.
MR_TOP = MT_BASE + "\n"
MR_LANE_ROW = 'sh("a lane commit to its own branch passes", COMMIT_OWN, "allow")\n'
MR_MAIN_ROW = 'sh("a main commit to its own branch passes", COMMIT_MAIN, "allow")\n'


def _mr_case(name, base, lane, main, result):
    """A conflicted merge of the test file: its text at the merge base, in each parent, and as the builder left it."""
    return _mt_case(name, [(TEST_A, lane)], [(TEST_A, main)], [TEST_A], resolve=[(TEST_A, result)], stage=True,
                    files={**BASE_FILES, TEST_A: base})


def _mr_allowed(slug, name, old, new):
    """The `old` statement sits in the base and the lane, `new` in main; the lane adds a row. The result takes `new`."""
    _mt_allow("builder-refuse: " + name, _mr_case("mr-" + slug, MR_TOP + old, MR_TOP + old + MR_LANE_ROW, MR_TOP + new,
                                                   MR_TOP + new + MR_LANE_ROW))


# Incident shape: main renamed a row's description and flipped its verdict.
_MR_OLD = 'sh("a lane\'s push # to main is refused by the gate", PUSH_MAIN, "deny")\n'
_MR_NEW = 'sh("a lane\'s push # to main asks the owner first", PUSH_MAIN, "ask")\n'
_mr_allowed("description-and-verdict", "a merge that takes main's renamed description and flipped verdict, with the "
            "lane's new row, is allowed", _MR_OLD, _MR_NEW)

# A function and the call that registers it are renamed together. The function name holds no verdict word.
_MR_OLD = ('def _gate_push_plain():\n    return PUSH_MAIN\n\n\n'
           'add_case("a plain push to main is refused by the gate", _gate_push_plain)\n')
_MR_NEW = ('def _gate_push_ordinary():\n    return PUSH_MAIN\n\n\n'
           'add_case("a plain push to main is blocked by the gate", _gate_push_ordinary)\n')
_mr_allowed("function-and-call", "a merge that takes main's renamed case function and its renamed registering call is "
            "allowed", _MR_OLD, _MR_NEW)

# An sh or add row whose expected verdict flipped from deny to ask, and nothing else.
_MR_OLD = 'add("a stop with a conflict marker is refused by the gate", "deny", rule=BDIFF, event="SubagentStop")\n'
_MR_NEW = 'add("a stop with a conflict marker is refused by the gate", "ask", rule=BDIFF, event="SubagentStop")\n'
_mr_allowed("add-row-flip", "a merge that takes main's add row, flipped from deny to ask, with the lane's new row, is "
            "allowed", _MR_OLD, _MR_NEW)
_MR_OLD = 'sh("a force push to main is refused by the gate", FORCE_MAIN, "deny")\n'
_MR_NEW = 'sh("a force push to main is refused by the gate", FORCE_MAIN, "ask")\n'
_mr_allowed("sh-row-flip", "a merge that takes main's sh row, flipped from deny to ask, with the lane's new row, is "
            "allowed", _MR_OLD, _MR_NEW)

# A verdict keyword that the flip adds: the default verdict has none.
_MR_OLD = 'row("a plain commit passes the gate here", COMMIT_OWN)\n'
_MR_NEW = 'row("a plain commit passes the gate here", COMMIT_OWN, want="ask")\n'
_mr_allowed("want-keyword", "a merge that takes main's row with an added want=\"ask\" keyword, with the lane's new row, "
            "is allowed", _MR_OLD, _MR_NEW)

# Full-size state: a hundred rows, as in the incident (103 cases). Main renames and flips row 50 and adds a row, the lane
# adds a row, and the result holds every row.
MR_FULL_N, MR_FULL_AT = 100, 50


def _mr_rows(renamed=None):
    rows = []
    for n in range(MR_FULL_N):
        if n == renamed:
            rows.append('sh("row number %03d asks the owner first", CMD_%03d, "ask")\n' % (n, n))
        else:
            rows.append('sh("row number %03d is refused by the gate", CMD_%03d, "deny")\n' % (n, n))
    return "".join(rows)


MR_FULL = _mr_case("mr-full-size-rename", MR_TOP + _mr_rows(), MR_TOP + _mr_rows() + MR_LANE_ROW,
                   MR_TOP + _mr_rows(MR_FULL_AT) + MR_MAIN_ROW,
                   MR_TOP + _mr_rows(MR_FULL_AT) + MR_LANE_ROW + MR_MAIN_ROW)
_mt_allow("builder-refuse: a merge of a hundred rows that takes main's renamed and flipped row 50, and keeps both sides' "
          "new rows, is allowed", MR_FULL)

# Both parents change one function: the lane only flips a verdict in it, main edits what it checks. Both change one line,
# so the merge conflicts on the function. The result keeps main's edit, so it drops the lane's flip. Decision
# `merge-union-reads-lost`, line 17: "Still refused as `lost`: a result that drops any entry of either parent."
MR_FUNC = ('def _gate_rows():\n    rows = []\n    rows.append(("push to main", "deny"))\n'
           '    rows.append(("push to a branch", "allow"))\n    return rows\n')
MR_FUNC_FLIP = MR_FUNC.replace('"push to main", "deny"', '"push to main", "ask"')
MR_FUNC_EDIT = MR_FUNC.replace('"push to main", "deny"', '"push --force to main", "deny"')
MR_FUNC_FLIP_DROPPED = _mr_case("mr-both-changed-drops-flip", MR_TOP + MR_FUNC, MR_TOP + MR_FUNC_FLIP,
                                MR_TOP + MR_FUNC_EDIT, MR_TOP + MR_FUNC_EDIT)
_mt_refuse("builder-refuse: a merge of a function that the lane only flipped and main edited, which keeps main's edit "
           "and drops the flip, is refused as lost", MR_FUNC_FLIP_DROPPED, "lost", (MT_CARRY["lost"],))
MR_FUNC_DROPPED = _mr_case("mr-both-changed-drops-edit", MR_TOP + MR_FUNC, MR_TOP + MR_FUNC_FLIP, MR_TOP + MR_FUNC_EDIT,
                           MR_TOP + MR_FUNC_FLIP)
_mt_refuse("builder-refuse: control, a merge of a function that the lane only flipped and main edited, which keeps the "
           "flip and drops main's edit, is refused as lost", MR_FUNC_DROPPED, "lost", (MT_CARRY["lost"],))
# Green control: main did not edit the function, and the result keeps the lane's flip. Both sides append a row at the
# end, so the merge conflicts there, and the function merges clean.
MR_FUNC_FLIP_KEPT = _mr_case("mr-lane-only-flip-kept", MR_TOP + MR_FUNC, MR_TOP + MR_FUNC_FLIP + MR_LANE_ROW,
                             MR_TOP + MR_FUNC + MR_MAIN_ROW, MR_TOP + MR_FUNC_FLIP + MR_LANE_ROW + MR_MAIN_ROW)
_mt_allow("builder-refuse: control, a merge of a function that the lane only flipped and main did not edit, which keeps "
          "the flip, is allowed", MR_FUNC_FLIP_KEPT)


# ---- CONTROLS: a deleted case stays lost, since the result holds fewer of its case than a parent ----
# Each side adds a row at the end, and the builder leaves out part of the base.
def _mr_deleted(slug, name, base, kept):
    _mt_refuse("builder-refuse: control, " + name + " is refused as lost", _mr_case(
        "mr-" + slug, MR_TOP + base, MR_TOP + base + MR_LANE_ROW, MR_TOP + base + MR_MAIN_ROW,
        MR_TOP + kept + MR_LANE_ROW + MR_MAIN_ROW), "lost", (MT_CARRY["lost"],))


MR_DEF = "def _gate_push_plain():\n    return PUSH_MAIN\n\n\n"
MR_CALL = 'add_case("a plain push to main is refused by the gate", _gate_push_plain)\n'
_mr_deleted("call-only", "a merge that deletes a registering call and keeps its function", MR_DEF + MR_CALL, MR_DEF)
_mr_deleted("call-and-def", "a merge that deletes a registering call and its function", MR_DEF + MR_CALL, "")
MR_ROW_A = 'sh("a push to main is checked by the gate", PUSH_MAIN, "deny")\n'
MR_ROW_B = 'sh("a push to a branch is checked by the gate", PUSH_BRANCH, "allow")\n'
_mr_deleted("row", "a merge that deletes one of two rows", MR_ROW_A + MR_ROW_B, MR_ROW_B)
# Twins: two rows with one command and one description, whose verdicts differ. Each holds the other's case key.
MR_TWIN_DENY = 'sh("a push to main is checked by the gate", PUSH_MAIN, "deny")\n'
MR_TWIN_ASK = 'sh("a push to main is checked by the gate", PUSH_MAIN, "ask")\n'
_mr_deleted("twin-row", "a merge that deletes one of two twin rows that differ only in verdict",
            MR_TWIN_DENY + MR_TWIN_ASK, MR_TWIN_DENY)

# A rename that main made is honoured, and another row is deleted in the same result.
MR_RENAME_OLD = 'sh("a push to a branch is checked by the gate", PUSH_BRANCH, "allow")\n'
MR_RENAME_NEW = 'sh("a push to a branch passes the gate here", PUSH_BRANCH, "ask")\n'
MR_RENAME_LOST = _mr_case("mr-rename-kept-row-deleted", MR_TOP + MR_ROW_A + MR_RENAME_OLD,
                          MR_TOP + MR_ROW_A + MR_RENAME_OLD + MR_LANE_ROW, MR_TOP + MR_ROW_A + MR_RENAME_NEW,
                          MR_TOP + MR_RENAME_NEW + MR_LANE_ROW)
_mt_refuse("builder-refuse: control, a merge that takes main's renamed row and deletes another row is refused as lost",
           MR_RENAME_LOST, "lost", (MT_CARRY["lost"],))

FAMILY = _MU5_PRIOR_FAMILY
