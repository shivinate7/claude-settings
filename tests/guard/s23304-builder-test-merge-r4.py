# section 23304
# A builder's merge that resolves a conflict in a test file, for two holes the reader still lets through (decision
# builders-cannot-edit-tests; owner ruling, plan R31: a lost test is a silent accuracy hole).
#   1. A rename that conflicts. One parent renames the test file and the other edits it and adds a case. The conflict
#      sits at the new path, which the other parent does not hold, so the reader never sees that parent's file. A
#      result that keeps the renamed file whole drops the other parent's edit and case, so it is refused.
#   2. A parent's edit to a top-level node that holds no test case (a table, a helper, a class decorator). The reader
#      matches the node by its name, so a result that keeps the other parent's version of that node drops the edit and
#      reads as nothing lost. It must read as lost.
# The controls pin what stays allowed: a delete against a modify that keeps the modified file, an add of one file on
# each side that keeps both cases, a node both parents leave unchanged, and a node the result keeps at the changed
# parent's version. The plain keep-both control is s23300's mt-allow-open, which pins that shape already.
# The fixtures reuse s23300's case helpers (_mt_case, _mt_refuse, _mt_allow, MT_B, MT_LANE, MT_MAIN, MT_CARRY,
# MT_FULL_MAIN), s23301's _mt2_node_case and s23264's _must and IDENT. Only the rename and modify/delete merge steps
# are new here: the shared opener writes files but cannot rename or delete one.
_MT4_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

MT4_ADD = "tests/test_add.py"
MT4_BASE = "def test_one():\n    v = 1\n    assert v == 1\n\ndef test_two():\n    assert 2\n"
# The renaming side keeps test_one's first edit. The editing side changes the same line and adds a case.
MT4_RENAMED = MT4_BASE.replace("assert v == 1", "assert v == 11")
MT4_EDITED = MT4_BASE.replace("assert v == 1", "assert v == 12") + "\ndef test_three():\n    assert 3\n"
MT4_EDITED_FULL = MT4_BASE.replace("assert v == 1", "assert v == 12") + MT_FULL_MAIN
MT4_FILES = {**BASE_FILES, TEST_A: MT4_BASE}


def _mt4_ops(where, ops, message):
    """Each op is ("put", path, text), ("mv", src, dst) or ("rm", path). They are committed in one commit."""
    for op in ops:
        if op[0] == "mv":
            _must(where, "mv", op[1], op[2])
        elif op[0] == "rm":
            _must(where, "rm", "-q", op[1])
        else:
            write(os.path.join(where, op[1]), op[2])
    _must(where, "add", "-A")
    _must(where, *IDENT, "commit", "-q", "-m", message)


def _mt4_unmerged(where, rel, codes):
    """Stop the suite unless `where` holds an open merge with `rel` in one of the git status codes `codes`. The shared
    `_require_conflict` accepts only UU and AA, so a modify/delete conflict (UD, DU) needs this check."""
    verify = run_vcs(where, "rev-parse", "--verify", "-q", "MERGE_HEAD")
    status = run_vcs(where, "status", "--porcelain")
    lines = [line for line in status.stdout.splitlines() if line[3:] == rel]
    if verify.returncode != 0 or not any(line[:2] in codes for line in lines):
        sys.exit("fixture setup failed: %r is not left in one of %s in %r. git status --porcelain shows: %r"
                 % (rel, codes, where, lines))


def _mt4_case(name, lane_ops, main_ops, conflicted, resolve, files=None):
    """A fixture. Cut at main: the test-author's ops commit on `lane`, and the builder resets to it. Main then commits
    its ops, and the builder merges main, leaving each (path, codes) of `conflicted` unmerged. `resolve` writes each
    (path, text) and stages the tree."""
    def build(w):
        main = w + "-main"
        _must(main, "checkout", "-q", "-b", "lane")
        _mt4_ops(main, lane_ops, "test-author lane")
        _must(main, "checkout", "-q", "main")
        _must(w, "reset", "-q", "--hard", "lane")
        _mt4_ops(main, main_ops, "main moves")
        merged = run_vcs(w, *IDENT, "-c", "merge.conflictStyle=merge", "merge", "--no-edit", "main")
        if merged.returncode == 0:
            sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
        for rel, codes in conflicted:
            _mt4_unmerged(w, rel, codes)
        for rel, text in resolve:
            write(os.path.join(w, rel), text)
        _must(w, "add", "-A")
    return diff_repo(name, build, files=files)


# ---- 1. A rename that conflicts ----
# The lane renames the file and edits test_one. Main edits the same line and adds a case at the old path. The conflict
# sits at the new path, and a builder that keeps the renamed file whole loses main's edit and case.
MT4_RENAME_LANE = _mt4_case("mt4-rename-lane-keeps-renamed",
                            [("mv", TEST_A, MT_B), ("put", MT_B, MT4_RENAMED)],
                            [("put", TEST_A, MT4_EDITED)],
                            [(MT_B, ("UU",))], [(MT_B, MT4_RENAMED)], files=MT4_FILES)
_mt_refuse("builder-refuse: a merge that keeps the renamed file whole, dropping the other side's edit and case "
           "at the old path, is refused", MT4_RENAME_LANE, ("lost", "unread"), (MT_CARRY["lost"] + MT_CARRY["unread"],))

# The mirror: main renames the file, and the lane edits it. The builder keeps main's renamed file whole.
MT4_RENAME_MAIN = _mt4_case("mt4-rename-main-keeps-renamed",
                            [("put", TEST_A, MT4_EDITED)],
                            [("mv", TEST_A, MT_B), ("put", MT_B, MT4_RENAMED)],
                            [(MT_B, ("UU",))], [(MT_B, MT4_RENAMED)], files=MT4_FILES)
_mt_refuse("builder-refuse: a merge that keeps the renamed file whole, dropping the lane's edit and case at the "
           "old path, is refused", MT4_RENAME_MAIN, ("lost", "unread"), (MT_CARRY["lost"] + MT_CARRY["unread"],))

# Full-size state: the other side adds thirty cases at the old path, and the builder keeps the renamed file whole.
MT4_RENAME_FULL = _mt4_case("mt4-rename-full-keeps-renamed",
                            [("mv", TEST_A, MT_B), ("put", MT_B, MT4_RENAMED)],
                            [("put", TEST_A, MT4_EDITED_FULL)],
                            [(MT_B, ("UU",))], [(MT_B, MT4_RENAMED)], files=MT4_FILES)
_mt_refuse("builder-refuse: a merge that keeps the renamed file whole, dropping thirty cases from the other side "
           "at the old path, is refused", MT4_RENAME_FULL, ("lost", "unread"),
           (MT_CARRY["lost"] + MT_CARRY["unread"],))

# Controls: a delete on one side against a modify on the other, keeping the modified file whole, is allowed.
MT4_DEL_KEEP = _mt4_case("mt4-delete-keeps-modified",
                         [("rm", TEST_A)], [("put", TEST_A, MT4_EDITED)],
                         [(TEST_A, ("DU", "UD"))], [(TEST_A, MT4_EDITED)], files=MT4_FILES)
_mt_allow("builder-refuse: control, a delete on one side against a modify on the other, keeping the modified "
          "file whole, is allowed", MT4_DEL_KEEP)

# Control: each side adds a file at one path, and the builder keeps both cases.
MT4_ADD_BOTH = _mt4_case("mt4-add-add-keeps-both",
                         [("put", MT4_ADD, MT_LANE)], [("put", MT4_ADD, MT_MAIN)],
                         [(MT4_ADD, ("AA",))], [(MT4_ADD, MT_LANE + MT_MAIN)])
_mt_allow("builder-refuse: control, each side adds a test file at one path, and the builder keeps both cases, "
          "is allowed", MT4_ADD_BOTH)


# ---- 2. A parent's edit to a top-level node that holds no test case, dropped when the result keeps the other parent's
# version. The edit reads as nothing lost, so each refusal must read as lost.
MT4_HEAD = "import pytest\n\nTABLE = [1, 2]\n"
MT4_TAIL = "\n@pytest.mark.parametrize('n', TABLE)\ndef test_rows(n):\n    assert n > 0\n"
MT4_GROWN = MT4_HEAD.replace("[1, 2]", "[1, 2, 3, 4]")
MT4_TABLE_CASE = "def test_extra():\n    assert 9\n"

# A table grown by one parent, and the other parent adds a case right after it. The result keeps the other whole.
MT4_TABLE_DROP = _mt_case("mt4-table-edit-dropped", [(TEST_A, MT4_GROWN + MT4_TAIL)],
                          [(TEST_A, MT4_HEAD + MT4_TABLE_CASE + MT4_TAIL)], [TEST_A],
                          resolve=[(TEST_A, MT4_HEAD + MT4_TABLE_CASE + MT4_TAIL)], stage=True,
                          files={**BASE_FILES, TEST_A: MT4_HEAD + MT4_TAIL})
_mt_refuse("builder-refuse: a merge that drops one parent's edit to a module-level table, keeping the other "
           "parent's whole file, is refused as lost", MT4_TABLE_DROP, "lost", (MT_CARRY["lost"],))

# Empty state: the base holds no test case, only the table, and each side changes it one way.
MT4_TABLE_EMPTY = _mt_case("mt4-table-edit-dropped-empty", [(TEST_A, MT4_GROWN)],
                           [(TEST_A, MT4_HEAD + MT4_TABLE_CASE)], [TEST_A],
                           resolve=[(TEST_A, MT4_HEAD + MT4_TABLE_CASE)], stage=True,
                           files={**BASE_FILES, TEST_A: MT4_HEAD})
_mt_refuse("builder-refuse: a merge into a test file with no case that drops one parent's edit to its table is "
           "refused as lost", MT4_TABLE_EMPTY, "lost", (MT_CARRY["lost"],))

# Control: the result keeps the changed parent's table, and the other parent's added case.
MT4_TABLE_KEPT = _mt_case("mt4-table-edit-kept", [(TEST_A, MT4_GROWN + MT4_TAIL)],
                          [(TEST_A, MT4_HEAD + MT4_TABLE_CASE + MT4_TAIL)], [TEST_A],
                          resolve=[(TEST_A, MT4_GROWN + MT4_TABLE_CASE + MT4_TAIL)], stage=True,
                          files={**BASE_FILES, TEST_A: MT4_HEAD + MT4_TAIL})
_mt_allow("builder-refuse: control, a merge that keeps the changed parent's table and the other parent's added case is "
          "allowed", MT4_TABLE_KEPT)

# Control: neither parent changes the table, and the result keeps it with both sides' cases.
MT4_TABLE_HELD = _mt2_node_case("mt4-table-unchanged-kept", "TABLE = [1, 2]\n", kept="TABLE = [1, 2]\n",
                                head="import pytest\n")
_mt_allow("builder-refuse: control, a merge that keeps a table neither parent changed, with both sides' cases, "
          "is allowed", MT4_TABLE_HELD)

# A helper hardened by one parent, and the other parent adds a case beside it. The result keeps the other whole.
MT4_CHECK_HEAD = "def check(n):\n    assert n > 0\n"
MT4_CHECK_HARD = "def check(n):\n    assert n > 0\n    assert n < 1000\n    assert isinstance(n, int)\n"
MT4_CHECK_TEST = "def test_k():\n    check(1)\n"
MT4_CHECK_CASE = "def test_m():\n    check(2)\n"
MT4_CHECK_DROP = _mt_case("mt4-helper-edit-dropped", [(TEST_A, MT4_CHECK_HARD + MT4_CHECK_TEST)],
                          [(TEST_A, MT4_CHECK_HEAD + MT4_CHECK_CASE + MT4_CHECK_TEST)], [TEST_A],
                          resolve=[(TEST_A, MT4_CHECK_HEAD + MT4_CHECK_CASE + MT4_CHECK_TEST)], stage=True,
                          files={**BASE_FILES, TEST_A: MT4_CHECK_HEAD + MT4_CHECK_TEST})
_mt_refuse("builder-refuse: a merge that drops one parent's hardened helper, keeping the other parent's whole file, is "
           "refused as lost", MT4_CHECK_DROP, "lost", (MT_CARRY["lost"],))

# Full-size state: the other side adds thirty cases beside the helper, and the hardened helper is dropped.
MT4_CHECK_FULL = _mt_case("mt4-helper-edit-dropped-full", [(TEST_A, MT4_CHECK_HARD + MT4_CHECK_TEST)],
                          [(TEST_A, MT4_CHECK_HEAD + MT_FULL_MAIN + MT4_CHECK_TEST)], [TEST_A],
                          resolve=[(TEST_A, MT4_CHECK_HEAD + MT_FULL_MAIN + MT4_CHECK_TEST)], stage=True,
                          files={**BASE_FILES, TEST_A: MT4_CHECK_HEAD + MT4_CHECK_TEST})
_mt_refuse("builder-refuse: a merge that drops one parent's hardened helper, keeping thirty cases from the other "
           "parent, is refused as lost", MT4_CHECK_FULL, "lost", (MT_CARRY["lost"],))

# Control: the result keeps the hardened helper and the other parent's added case.
MT4_CHECK_KEPT = _mt_case("mt4-helper-edit-kept", [(TEST_A, MT4_CHECK_HARD + MT4_CHECK_TEST)],
                          [(TEST_A, MT4_CHECK_HEAD + MT4_CHECK_CASE + MT4_CHECK_TEST)], [TEST_A],
                          resolve=[(TEST_A, MT4_CHECK_HARD + MT4_CHECK_CASE + MT4_CHECK_TEST)], stage=True,
                          files={**BASE_FILES, TEST_A: MT4_CHECK_HEAD + MT4_CHECK_TEST})
_mt_allow("builder-refuse: control, a merge that keeps the hardened helper and the other parent's added case "
          "is allowed", MT4_CHECK_KEPT)

# A class decorator edited by one parent. The other parent adds a module-level case right above the decorator, so
# the two edits touch. The result keeps the other parent's decorator, which drops the edit.
MT4_DECO_HEAD = "import pytest\n"
MT4_DECO_DB = "@pytest.mark.usefixtures('db')\nclass TestW:\n    def test_x(self):\n        assert 1\n"
MT4_DECO_CACHE = MT4_DECO_DB.replace("('db')", "('db', 'cache')")
MT4_DECO_TOP = "def test_top():\n    assert 0\n"
MT4_DECO_DROP = _mt_case("mt4-decorator-edit-dropped", [(TEST_A, MT4_DECO_HEAD + MT4_DECO_CACHE)],
                         [(TEST_A, MT4_DECO_HEAD + MT4_DECO_TOP + MT4_DECO_DB)], [TEST_A],
                         resolve=[(TEST_A, MT4_DECO_HEAD + MT4_DECO_TOP + MT4_DECO_DB)], stage=True,
                         files={**BASE_FILES, TEST_A: MT4_DECO_HEAD + MT4_DECO_DB})
_mt_refuse("builder-refuse: a merge that drops one parent's edit to a class decorator, keeping the other "
           "parent's whole file, is refused as lost", MT4_DECO_DROP, "lost", (MT_CARRY["lost"],))

# Control: the result keeps the changed decorator and the other parent's added case.
MT4_DECO_KEPT = _mt_case("mt4-decorator-edit-kept", [(TEST_A, MT4_DECO_HEAD + MT4_DECO_CACHE)],
                         [(TEST_A, MT4_DECO_HEAD + MT4_DECO_TOP + MT4_DECO_DB)], [TEST_A],
                         resolve=[(TEST_A, MT4_DECO_HEAD + MT4_DECO_TOP + MT4_DECO_CACHE)], stage=True,
                         files={**BASE_FILES, TEST_A: MT4_DECO_HEAD + MT4_DECO_DB})
_mt_allow("builder-refuse: control, a merge that keeps the changed class decorator and the other parent's "
          "added case is allowed", MT4_DECO_KEPT)

FAMILY = _MT4_PRIOR_FAMILY
