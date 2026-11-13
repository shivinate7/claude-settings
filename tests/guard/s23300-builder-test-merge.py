# section 23300
# A builder's merge that resolves a conflict in a test file (owner ruling 2026-11-11 11:02 CST; decision
# builders-cannot-edit-tests). The resolution is allowed when every test case of both parents survives. Each
# refusal names its class of loss in the reason: each refused case carries one class's words, and lacks the
# other classes' words and any path, so one generic reason listing every class fails.
# The conflict steps are the builder-refuse section's (s23264): _test_author_lane, _put_commit, _must,
# _require_conflict, clean_builder_case and author_silent_case. Log checks join at section 40805, so this
# section stays below it.
_MT_PRIOR_FAMILY = FAMILY
FAMILY = "builder-refuse"

MT_BASE = BASE_FILES[TEST_A]
MT_LANE = "def test_lane_new():\n    assert 1\n"
MT_MAIN = "def test_main_new():\n    assert 2\n"
MT_BOTH = MT_BASE + MT_LANE + MT_MAIN
MT_LANE_SIDE = [(TEST_A, MT_BASE + MT_LANE)]
MT_MAIN_SIDE = [(TEST_A, MT_BASE + MT_MAIN)]
MT_OTHER_PATH = "tests/test_other.py"
MT_OTHER = "def test_other():\n    assert 0\n"
MT_GHOST = '"""\ndef test_ghost():\n    assert 0\n"""\n'
MT_COMMENT = "# don't count: def test_old():\n#     assert 0\n"
MT_NESTED = "class TestInner:\n    def test_nested(self):\n        assert 1\n"
MT_ASYNC = "async def test_async():\n    assert 1\n"
MT_DECORATED = "@pytest.mark.parametrize('x', [1])\ndef test_param(x):\n    assert x\n"
MT_UNITTEST = "class TestLane(unittest.TestCase):\n    def test_lane(self):\n        assert 1\n"
MT_FULL_LANE = "".join("def test_lane_%02d():\n    assert %d\n" % (n, n) for n in range(30))
MT_FULL_MAIN = "".join("def test_main_%02d():\n    assert %d\n" % (n, n + 100) for n in range(30))
MT_INI = "pytest.ini"
MT_INI_FILES = {**BASE_FILES, MT_INI: "[pytest]\naddopts = -q\n"}
MT_INI_LANE = [(MT_INI, "[pytest]\naddopts = -q -x\n")]
MT_INI_MAIN = [(MT_INI, "[pytest]\naddopts = -q --tb=short\n")]
MT_MUT_FILES = ("hooks/mutate_guard.py", "hooks/mutate_shared.py", "janitor/mutate_sweep.py")
MT_MJS = "tests/widget.test.mjs"
MT_MJS_BASE = "test('base', () => {});\n"
MT_B = "tests/test_b.py"

# The words each class's reason must carry (any one of a tuple's options), and the words of the other classes,
# which a refusal of this class must not carry.
MT_CARRY = {
    "lost": ("lost", "missing", "removed", "dropped"),
    "renamed": ("renamed", "rename"),
    "moved": ("moved to", "another file"),
    "body": ("body", "differs"),
    "skip": ("skip", "xfail", "expected-fail", "expected failure"),
    "new": ("new test", "new case", "added case", "new function"),
    "config": ("beyond", "neither parent"),
    "mutation": ("mutation",),
    "unread": ("unread", "cannot read", "could not read", "could not be read"),
}
# No reason names a path or a test name: the rule's remedy stays with the undo route.
MT_PATH_WORDS = ("tests/", "test_a", "test_lane", "test_main", "test_moved", "test_other", "mutate_",
                 "pytest.ini", "widget")


def _mt_lacks(classes):
    own = (classes,) if isinstance(classes, str) else tuple(classes)
    words = []
    for name, options in MT_CARRY.items():
        if name not in own:
            words.extend(options)
    return tuple(words) + MT_PATH_WORDS


def _mt_open(w, lane, main, conflicted, no_ff=False):
    """Cut at main. The test-author's commit on `lane` writes each (path, text) of `lane`, and the builder resets
    to it. Main then commits each (path, text) of `main`. The builder merges main: each path in `conflicted` is
    left unmerged and the merge stays open. With no conflict, the merge is clean and commits."""
    main_checkout = w + "-main"
    _test_author_lane(w, lane[0][0], lane[0][1], more=lane[1:])
    _must(w, "reset", "-q", "--hard", "lane")
    _put_commit(main_checkout, main, "main moves")
    flags = ["--no-ff"] if no_ff else []
    merged = run_vcs(w, *IDENT, "-c", "merge.conflictStyle=merge", "merge", "--no-edit", *flags, "main")
    if not conflicted:
        if merged.returncode != 0:
            sys.exit("fixture setup failed: the merge in %r did not merge clean: %s" % (w, merged.stderr.strip()))
        return
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    for rel in conflicted:
        _require_conflict(w, rel)


def _require_merge_names_from(where, folder, rel):
    """Stop the suite unless git's merge-tree, run from `folder` of `where`, names the conflicted `rel` relative to that
    folder (with `../`). A case run from the folder then takes the path merge_tree must put back to the top."""
    want = os.path.relpath(os.path.join(where, rel), os.path.join(where, folder)).replace(os.sep, "/")
    done = run_vcs(os.path.join(where, folder), "merge-tree", "--write-tree", "-z", "--no-messages", "HEAD", "MERGE_HEAD")
    if done.returncode not in (0, 1) or not any(entry.endswith("\t" + want) for entry in done.stdout.split("\0")):
        sys.exit("fixture setup failed: merge-tree in %r does not name %r from %r: %s"
                 % (where, want, folder, (done.stdout + done.stderr).strip()))


def _mt_case(name, lane, main, conflicted, resolve=(), stage=False, commit=False, files=None, no_ff=False,
             folder=""):
    """A fixture: the merge `_mt_open` leaves, then each (path, text) of `resolve` written. `stage` adds the
    tree to the index; `commit` makes the merge commit. `folder`, when given, is the subfolder the case runs from:
    the fixture first checks that merge-tree names the conflicted path from there, so the case takes that path."""
    def build(w):
        _mt_open(w, lane, main, conflicted, no_ff=no_ff)
        if folder:
            _require_merge_names_from(w, folder, conflicted[0])
        for rel, text in resolve:
            write(os.path.join(w, rel), text)
        if stage or commit:
            _must(w, "add", "-A")
        if commit:
            _must(w, *IDENT, "commit", "-q", "--no-edit")
    return diff_repo(name, build, files=files)


def _mt_refuse(name, repo, classes, carries):
    """Three rows: deny at commit, at push and at the first stop, each by builder-diff. The reason carries one
    of `carries` and none of the other classes' words, nor a path."""
    lacks = _mt_lacks(classes)
    sh(name + ", at commit", COMMIT, "deny", rule=BDIFF, cwd=repo, agent_id="bld1", agent_type="builder",
       carries=carries, lacks=lacks)
    sh(name + ", at push", PUSH, "deny", rule=BDIFF, cwd=repo, agent_id="bld1", agent_type="builder",
       carries=carries, lacks=lacks)
    add(name + ", at stop", "deny", rule=BDIFF, event="SubagentStop", cwd=repo, agent_id="bld1",
        agent_type="builder", carries=carries, lacks=lacks)


def _mt_allow(name, repo):
    """Allowed at commit, push and the first stop, in the state the fixture leaves (staged open merge)."""
    sh(name + ", at commit", COMMIT, "allow", cwd=repo, agent_id="bld1", agent_type="builder")
    sh(name + ", at push", PUSH, "allow", cwd=repo, agent_id="bld1", agent_type="builder")
    add(name + ", at stop", "allow", event="SubagentStop", cwd=repo, agent_id="bld1", agent_type="builder")


# ---- ALLOWED (red on main: today a builder's test-file merge resolution is refused) ----
MT_OPEN = _mt_case("mt-allow-open", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A], resolve=[(TEST_A, MT_BOTH)], stage=True)
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' test cases, staged", MT_OPEN)

MT_COMMITTED = _mt_case("mt-allow-committed", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A], resolve=[(TEST_A, MT_BOTH)],
                        commit=True)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's merge commit that keeps both sides' test cases is allowed "
                         "at commit, push and stop, and logs no builder-diff line", clean_builder_case("mt-allow-committed")))

MT_ORDER = _mt_case("mt-allow-order", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                    resolve=[(TEST_A, MT_BASE + MT_MAIN + MT_LANE)], stage=True)
sh("builder-refuse: a builder's open merge that keeps both sides' test cases in the other order is allowed at "
   "commit", COMMIT, "allow", cwd=MT_ORDER, agent_id="bld1", agent_type="builder")

# Empty state: the base holds no test case, and each side adds one.
MT_EMPTY = _mt_case("mt-allow-empty-base", [(TEST_A, MT_LANE)], [(TEST_A, MT_MAIN)], [TEST_A],
                    resolve=[(TEST_A, MT_LANE + MT_MAIN)], stage=True, files={**BASE_FILES, TEST_A: ""})
sh("builder-refuse: a builder's open merge into an empty test file, each side adds one case and both are kept, is "
   "allowed at commit", COMMIT, "allow", cwd=MT_EMPTY, agent_id="bld1", agent_type="builder")

# Full-size state: each side adds thirty cases.
MT_FULL = _mt_case("mt-allow-full", [(TEST_A, MT_BASE + MT_FULL_LANE)], [(TEST_A, MT_BASE + MT_FULL_MAIN)],
                   [TEST_A], resolve=[(TEST_A, MT_BASE + MT_FULL_LANE + MT_FULL_MAIN)], stage=True)
sh("builder-refuse: a builder's open merge that keeps thirty cases from each side is allowed at commit",
   COMMIT, "allow", cwd=MT_FULL, agent_id="bld1", agent_type="builder")

# Scanner: a def test_x that only a string or a comment holds is no case, so dropping it loses nothing.
MT_GHOST_REPO = _mt_case("mt-allow-ghost", [(TEST_A, MT_BASE + MT_GHOST)], MT_MAIN_SIDE, [TEST_A],
                         resolve=[(TEST_A, MT_BASE + MT_MAIN)], stage=True)
sh("builder-refuse: a builder's open merge that drops a string holding a def test_x, keeping the parent's cases, "
   "is allowed at commit", COMMIT, "allow", cwd=MT_GHOST_REPO, agent_id="bld1", agent_type="builder")
MT_COMMENT_REPO = _mt_case("mt-allow-comment", [(TEST_A, MT_BASE + MT_COMMENT)], MT_MAIN_SIDE, [TEST_A],
                           resolve=[(TEST_A, MT_BASE + MT_MAIN)], stage=True)
sh("builder-refuse: a builder's open merge that drops a comment holding a def test_x, with a lone quote in it, is "
   "allowed at commit", COMMIT, "allow", cwd=MT_COMMENT_REPO, agent_id="bld1", agent_type="builder")

# Test config: keeping one parent's pytest.ini whole is no change beyond a parent (the control below is green on
# main, since a non-disabling pytest.ini is not refused today).
MT_INI_ONE = _mt_case("mt-cfg-one-side", MT_INI_LANE, MT_INI_MAIN, [MT_INI],
                      resolve=[(MT_INI, "[pytest]\naddopts = -q -x\n")], stage=True, files=MT_INI_FILES)
sh("builder-refuse: a builder's open merge that keeps one parent's pytest.ini whole is allowed at commit",
   COMMIT, "allow", cwd=MT_INI_ONE, agent_id="bld1", agent_type="builder")

# A clean merge (no conflict) that a builder takes is no test-file resolution, and stays allowed (control).
MT_CLEAN = _mt_case("mt-clean-merge", [(MT_OTHER_PATH, MT_OTHER + MT_LANE)], [(TEST_A, MT_BASE + MT_MAIN)], [],
                    no_ff=True, files={**BASE_FILES, MT_OTHER_PATH: MT_OTHER})
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's clean merge of main's test case and a lane's other-file case, "
                         "with no conflict, is allowed and logs no builder-diff line", clean_builder_case("mt-clean-merge")))


# ---- REFUSED: each class's reason names the class (red on main: the reason names no class) ----
# Case 1: a test case of either parent is lost, renamed or moved to another file.
MT_LOST_MAIN = _mt_case("mt-lost-main", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                        resolve=[(TEST_A, MT_BASE + MT_LANE)], stage=True)
_mt_refuse("builder-refuse: a merge that drops main's test case is refused", MT_LOST_MAIN, "lost", (MT_CARRY["lost"],))
MT_LOST_LANE = _mt_case("mt-lost-lane", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                        resolve=[(TEST_A, MT_BASE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that drops the lane's test case is refused", MT_LOST_LANE, "lost", (MT_CARRY["lost"],))
MT_RENAMED = _mt_case("mt-renamed", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                      resolve=[(TEST_A, MT_BASE + "def test_lane_renamed():\n    assert 1\n" + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that renames a test case is refused", MT_RENAMED, "renamed", (MT_CARRY["renamed"],))
MT_MOVED = _mt_case("mt-moved", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                    resolve=[(TEST_A, MT_BASE + MT_MAIN), ("tests/test_moved.py", MT_LANE)], stage=True)
_mt_refuse("builder-refuse: a merge that moves a test case to another file is refused", MT_MOVED, "moved",
           (MT_CARRY["moved"],))
# The same name sits in two files. Keyed by file and name, the drop from TEST_A is a loss; keyed by name alone it is not.
MT_SAME = _mt_case("mt-same-name", [(TEST_A, MT_BASE + MT_LANE), (MT_OTHER_PATH, MT_OTHER + MT_LANE)],
                   [(TEST_A, MT_BASE + MT_MAIN), (MT_OTHER_PATH, MT_OTHER + "# main's note\n")],
                   [TEST_A, MT_OTHER_PATH],
                   resolve=[(TEST_A, MT_BASE + MT_MAIN), (MT_OTHER_PATH, MT_OTHER + MT_LANE + "# main's note\n")],
                   stage=True, files={**BASE_FILES, MT_OTHER_PATH: MT_OTHER})
# The drop reads as lost or moved: one any-of group (a tuple inside `carries` is any-of), so a reason with a word of either
# class passes. Written as a group, not as the six words, so the form matches what the check reads.
MT_SAME_ANY = MT_CARRY["lost"] + MT_CARRY["moved"]
_mt_refuse("builder-refuse: a merge that drops a same-named test case from one file, which another file still holds, "
           "is refused", MT_SAME, ("lost", "moved"), (MT_SAME_ANY,))

# Case 2: a test case body that differs from both parents.
MT_BODY = _mt_case("mt-body", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                   resolve=[(TEST_A, MT_BASE + "def test_lane_new():\n    assert 99\n" + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that rewrites a test case body is refused", MT_BODY, "body", (MT_CARRY["body"],))

# Case 3: a skip or expected-fail mark that neither parent had.
MT_SKIP = _mt_case("mt-skip", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                   resolve=[(TEST_A, MT_BASE + "@pytest.mark.skip(reason=\"later\")\n" + MT_LANE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that adds a pytest skip mark is refused", MT_SKIP, "skip", (MT_CARRY["skip"],))
MT_XFAIL = _mt_case("mt-xfail", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                    resolve=[(TEST_A, MT_BASE + MT_LANE + "@pytest.mark.xfail\n" + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that adds a pytest xfail mark is refused", MT_XFAIL, "skip", (MT_CARRY["skip"],))
MT_SKIPIF = _mt_case("mt-skipif", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                     resolve=[(TEST_A, MT_BASE + "@unittest.skipIf(True, \"later\")\n" + MT_LANE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that adds a unittest skipIf mark is refused", MT_SKIPIF, "skip", (MT_CARRY["skip"],))
MT_PYTESTMARK = _mt_case("mt-pytestmark", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                         resolve=[(TEST_A, "pytestmark = pytest.mark.skip\n" + MT_BASE + MT_LANE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that adds a module-wide pytestmark skip is refused", MT_PYTESTMARK, "skip",
           (MT_CARRY["skip"],))
MT_CLASS_SKIP = _mt_case("mt-class-skip", [(TEST_A, MT_BASE + MT_UNITTEST)], MT_MAIN_SIDE, [TEST_A],
                         resolve=[(TEST_A, MT_BASE + "@unittest.skip(\"later\")\n" + MT_UNITTEST + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that skips a unittest class, its method bodies unchanged, is refused",
           MT_CLASS_SKIP, "skip", (MT_CARRY["skip"],))

# Case 4: a new test function that neither parent had.
MT_NEW = _mt_case("mt-new", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                  resolve=[(TEST_A, MT_BOTH + "def test_builder_new():\n    assert 3\n")], stage=True)
_mt_refuse("builder-refuse: a merge that adds a test function neither parent had is refused", MT_NEW, "new",
           (MT_CARRY["new"],))

# Case 5: test config beyond one parent's version. A blend that disables no test is refused here only by the
# merge rule, so this row is red on main, which allows it.
MT_BLEND = _mt_case("mt-cfg-blend", MT_INI_LANE, MT_INI_MAIN, [MT_INI],
                    resolve=[(MT_INI, "[pytest]\naddopts = -q -x --tb=short\n")], stage=True, files=MT_INI_FILES)
_mt_refuse("builder-refuse: a merge of pytest.ini that keeps neither parent's version is refused", MT_BLEND,
           "config", (MT_CARRY["config"],))

# Case 5, mutation tests: any change to one is refused, however the conflict is resolved.
for _mt_rel in MT_MUT_FILES:
    _mt_slug = _mt_rel.rsplit("/", 1)[-1].replace(".py", "")
    _mt_repo = _mt_case("mt-mut-both-" + _mt_slug, [(_mt_rel, "x = 2\n")], [(_mt_rel, "x = 3\n")], [_mt_rel],
                        resolve=[(_mt_rel, "x = 2\nx = 3\n")], stage=True,
                        files={**BASE_FILES, _mt_rel: "x = 1\n"})
    _mt_refuse("builder-refuse: a merge that keeps both sides of mutation test " + _mt_slug + " is refused",
               _mt_repo, "mutation", (MT_CARRY["mutation"],))
MT_MUT_GUARD = MT_MUT_FILES[0]
MT_MUT_ONE = _mt_case("mt-mut-one-side", [(MT_MUT_GUARD, "x = 2\n")], [(MT_MUT_GUARD, "x = 3\n")], [MT_MUT_GUARD],
                      resolve=[(MT_MUT_GUARD, "x = 2\n")], stage=True, files={**BASE_FILES, MT_MUT_GUARD: "x = 1\n"})
_mt_refuse("builder-refuse: a merge that keeps one side of a mutation test is refused", MT_MUT_ONE, "mutation",
           (MT_CARRY["mutation"],))

# Non-Python test file: the check reads no .mjs, so it cannot prove a case survives. The safe default refuses it.
MT_MJS_RESOLVED = MT_MJS_BASE + "test('lane', () => {});\ntest('main', () => {});\n"
MT_MJS_REPO = _mt_case("mt-unread-mjs", [(MT_MJS, MT_MJS_BASE + "test('lane', () => {});\n")],
                       [(MT_MJS, MT_MJS_BASE + "test('main', () => {});\n")], [MT_MJS],
                       resolve=[(MT_MJS, MT_MJS_RESOLVED)], stage=True, files={**BASE_FILES, MT_MJS: MT_MJS_BASE})
_mt_refuse("builder-refuse: a merge that conflicts in a non-Python test file is refused, since no check reads it",
           MT_MJS_REPO, "unread", (MT_CARRY["unread"],))

# Scanner, loss cases: a case the ast scan counts is lost when the resolution drops it. A nested class's test,
# an async test, a decorated test, and a test moved into a string are each one case.
MT_NESTED_REPO = _mt_case("mt-drop-nested", [(TEST_A, MT_BASE + MT_NESTED)], MT_MAIN_SIDE, [TEST_A],
                          resolve=[(TEST_A, MT_BASE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that drops a nested class's test case is refused", MT_NESTED_REPO, "lost",
           (MT_CARRY["lost"],))
MT_ASYNC_REPO = _mt_case("mt-drop-async", [(TEST_A, MT_BASE + MT_ASYNC)], MT_MAIN_SIDE, [TEST_A],
                         resolve=[(TEST_A, MT_BASE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that drops an async test case is refused", MT_ASYNC_REPO, "lost",
           (MT_CARRY["lost"],))
MT_DECORATED_REPO = _mt_case("mt-drop-decorated", [(TEST_A, MT_BASE + MT_DECORATED)], MT_MAIN_SIDE, [TEST_A],
                             resolve=[(TEST_A, MT_BASE + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that drops a decorated test case is refused", MT_DECORATED_REPO, "lost",
           (MT_CARRY["lost"],))
MT_DOCSTRING_REPO = _mt_case("mt-into-string", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                             resolve=[(TEST_A, MT_BASE + '"""\n' + MT_LANE + '"""\n' + MT_MAIN)], stage=True)
_mt_refuse("builder-refuse: a merge that turns a test case into a string is refused", MT_DOCSTRING_REPO, "lost",
           (MT_CARRY["lost"],))
# A comment opener inside a multi-line string does not end the string: the case after it is still a case.
MT_HASH_REPO = _mt_case("mt-hash-in-string", [(TEST_A, MT_BASE + 'X = """\n# not a comment\n"""\n' + MT_LANE)],
                        MT_MAIN_SIDE, [TEST_A], resolve=[(TEST_A, MT_BASE + 'X = """\n# not a comment\n"""\n' + MT_MAIN)],
                        stage=True)
_mt_refuse("builder-refuse: a merge that drops a case after a string holding a comment opener is refused",
           MT_HASH_REPO, "lost", (MT_CARRY["lost"],))

# ---- CONTROLS (green on main and after the build; labelled) ----
# A builder's own test edit to a file that merged no conflict stays refused beside a clean resolution.
MT_SCOPE = _mt_case("mt-scope-b", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A],
                    resolve=[(TEST_A, MT_BOTH), (MT_B, "def test_b():\n    assert 2\n")], stage=True,
                    files={**BASE_FILES, MT_B: "def test_b():\n    assert 1\n"})
sh("builder-refuse: control, a builder's own edit to a test file that merged no conflict is denied beside a "
   "both-sides resolution", COMMIT, "deny", rule=BDIFF, cwd=MT_SCOPE, agent_id="bld1", agent_type="builder")

# A Write to a test path that merged clean, mid-merge, is refused by path (control).
MT_WRITE_CLEAN = _mt_case("mt-write-clean-path", [("src/app.py", "x = 2\n")],
                          [("src/app.py", "x = 3\n"), (TEST_A, MT_BASE + MT_MAIN)], ["src/app.py"])
add("builder-refuse: control, a builder's Write to a test path that merged clean mid-merge is denied", "deny",
    rule="builder-test-edit", tool="Write", cwd=MT_WRITE_CLEAN, file_path=os.path.join(MT_WRITE_CLEAN, TEST_A),
    content=MT_BASE + MT_MAIN + MT_LANE, agent_id="bld1", agent_type="builder")

# A Write to a conflicted mutation test is refused whatever it holds (control).
MT_MUT_WRITE = _mt_case("mt-mut-write", [(MT_MUT_GUARD, "x = 2\n")], [(MT_MUT_GUARD, "x = 3\n")], [MT_MUT_GUARD],
                        files={**BASE_FILES, MT_MUT_GUARD: "x = 1\n"})
add("builder-refuse: control, a builder's Write to a conflicted mutation test is denied", "deny",
    rule="builder-test-edit", tool="Write", cwd=MT_MUT_WRITE, file_path=os.path.join(MT_MUT_WRITE, MT_MUT_GUARD),
    content="x = 2\nx = 3\n", agent_id="bld1", agent_type="builder")

# A test-author may edit a conflicted test file mid-merge (control, the merge route on main).
MT_AUTHOR_OPEN = _mt_case("mt-author-open", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A])
MT_BLOCK = "<<<<<<< HEAD\n" + MT_LANE + "=======\n" + MT_MAIN + ">>>>>>> main\n"
add("test-author: control, an Edit of a conflicted test file mid-merge is allowed", "allow", tool="Edit",
    cwd=MT_AUTHOR_OPEN, file_path=os.path.join(MT_AUTHOR_OPEN, TEST_A), old_string=MT_BLOCK,
    new_string=MT_LANE + MT_MAIN, agent_id="auth1", agent_type="test-author")

# A test-author's committed merge that keeps both sides is never refused and logs nothing (control).
LOG_CHECKS_EXTRA.append(("builder-refuse: control, a test-author's merge commit that keeps both sides' test cases is "
                         "never refused and logs nothing", author_silent_case(MT_COMMITTED, "mt-allow-committed")))


# ---- a builder's write tool on a test path its merge conflicts (builder_merge_write_ok). The path is allowed mid-merge,
# since the content is judged at commit, push and stop. Red on main, where every builder write to a test path is denied.
MT_WRITE_OPEN = _mt_case("mt-write-conflicted", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A])
add("builder-refuse: a builder's Write of a test path its merge conflicts is allowed mid-merge", "allow", tool="Write",
    cwd=MT_WRITE_OPEN, file_path=os.path.join(MT_WRITE_OPEN, TEST_A), content=MT_BOTH, agent_id="bld1",
    agent_type="builder")
add("builder-refuse: a builder's Edit of a test path its merge conflicts is allowed mid-merge", "allow", tool="Edit",
    cwd=MT_WRITE_OPEN, file_path=os.path.join(MT_WRITE_OPEN, TEST_A), old_string=MT_BLOCK, new_string=MT_BOTH,
    agent_id="bld1", agent_type="builder")
add("builder-refuse: a builder's Write of a test path its merge conflicts, run from a subfolder, is allowed mid-merge",
    "allow", tool="Write", cwd=os.path.join(MT_WRITE_OPEN, "src"), file_path=os.path.join(MT_WRITE_OPEN, TEST_A),
    content=MT_BOTH, agent_id="bld1", agent_type="builder")
# Controls, red only under the mutants: the Edit form of the two refusals, a clean-merged test path and a mutation test.
add("builder-refuse: control, a builder's Edit of a test path that merged clean mid-merge is denied", "deny",
    rule="builder-test-edit", tool="Edit", cwd=MT_WRITE_CLEAN, file_path=os.path.join(MT_WRITE_CLEAN, TEST_A),
    old_string=MT_MAIN, new_string="def test_main_new():\n    assert 5\n", agent_id="bld1", agent_type="builder")
add("builder-refuse: control, a builder's Edit of a conflicted mutation test is denied", "deny",
    rule="builder-test-edit", tool="Edit", cwd=MT_MUT_WRITE, file_path=os.path.join(MT_MUT_WRITE, MT_MUT_GUARD),
    old_string="x = 2\n", new_string="x = 4\n", agent_id="bld1", agent_type="builder")


# ---- the merge route run from a subfolder. merge_tree names a conflicted path relative to the folder git runs in
# (`../tests/test_a.py`), and the guard puts it back to the checkout's top. Each fixture first checks that git names it
# so. Red on main, where the merge route is absent; red on the mutant that drops the prefix, where the deny names no class.
MT_SUB_KEEP = _mt_case("mt-sub-keep-both", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A], resolve=[(TEST_A, MT_BOTH)],
                       stage=True, folder="src")
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' test cases, run from a subfolder, is allowed",
          os.path.join(MT_SUB_KEEP, "src"))
MT_SUB_LOST = _mt_case("mt-sub-lost", MT_LANE_SIDE, MT_MAIN_SIDE, [TEST_A], resolve=[(TEST_A, MT_BASE + MT_LANE)],
                       stage=True, folder="src")
_mt_refuse("builder-refuse: a merge that drops main's test case, run from a subfolder, is refused as lost",
           os.path.join(MT_SUB_LOST, "src"), "lost", (MT_CARRY["lost"],))


# ---- top-level call statements of a test file (merge_test_issue, `calls`). A call a parent holds stays as many times as
# that parent holds it; a call neither parent holds is new, and a skip call is a skip. The base holds one call twice, so
# counting a call's copies as a sum instead of a maximum refuses the keep-both row. Red on main, where the merge route is
# absent.
MT_DUP = "register_case('dup')\n"
MT_CALL_BASE = MT_BASE + MT_DUP * 2
MT_CALL_FILES = {**BASE_FILES, TEST_A: MT_CALL_BASE}
MT_CALL_LANE = "register_case('lane')\n"
MT_CALL_MAIN = "register_case('main')\n"
MT_CALL_LANE_SIDE = [(TEST_A, MT_CALL_BASE + MT_LANE + MT_CALL_LANE)]
MT_CALL_MAIN_SIDE = [(TEST_A, MT_CALL_BASE + MT_MAIN + MT_CALL_MAIN)]
MT_CALL_BOTH = MT_CALL_BASE + MT_LANE + MT_CALL_LANE + MT_MAIN + MT_CALL_MAIN
MT_CALL_FULL_LANE = "".join("register_case('lane_%02d')\n" % n for n in range(30))
MT_CALL_FULL_MAIN = "".join("register_case('main_%02d')\n" % n for n in range(30))

MT_CALL_KEEP = _mt_case("mt-call-keep-both", MT_CALL_LANE_SIDE, MT_CALL_MAIN_SIDE, [TEST_A],
                        resolve=[(TEST_A, MT_CALL_BOTH)], stage=True, files=MT_CALL_FILES)
_mt_allow("builder-refuse: a builder's open merge that keeps both sides' calls, a call held twice in the base, is allowed",
          MT_CALL_KEEP)
# Empty state: the base holds no call, and each side adds one.
MT_CALL_EMPTY = _mt_case("mt-call-empty-base", [(TEST_A, MT_CALL_LANE)], [(TEST_A, MT_CALL_MAIN)], [TEST_A],
                         resolve=[(TEST_A, MT_CALL_LANE + MT_CALL_MAIN)], stage=True, files={**BASE_FILES, TEST_A: ""})
sh("builder-refuse: a builder's open merge into an empty test file, each side adds one call and both are kept, is "
   "allowed at commit", COMMIT, "allow", cwd=MT_CALL_EMPTY, agent_id="bld1", agent_type="builder")
# Full-size state: each side adds thirty calls.
MT_CALL_FULL = _mt_case("mt-call-full", [(TEST_A, MT_CALL_BASE + MT_CALL_FULL_LANE)],
                        [(TEST_A, MT_CALL_BASE + MT_CALL_FULL_MAIN)], [TEST_A],
                        resolve=[(TEST_A, MT_CALL_BASE + MT_CALL_FULL_LANE + MT_CALL_FULL_MAIN)], stage=True,
                        files=MT_CALL_FILES)
sh("builder-refuse: a builder's open merge that keeps thirty calls from each side is allowed at commit",
   COMMIT, "allow", cwd=MT_CALL_FULL, agent_id="bld1", agent_type="builder")
# Lost: the merge drops main's call.
MT_CALL_DROP = _mt_case("mt-call-drop-main", MT_CALL_LANE_SIDE, MT_CALL_MAIN_SIDE, [TEST_A],
                        resolve=[(TEST_A, MT_CALL_BASE + MT_LANE + MT_CALL_LANE + MT_MAIN)], stage=True,
                        files=MT_CALL_FILES)
_mt_refuse("builder-refuse: a merge that drops main's top-level call is refused as lost", MT_CALL_DROP, "lost",
           (MT_CARRY["lost"],))
# Lost: the base holds a call twice, and the merge keeps it once.
MT_CALL_ONCE = _mt_case("mt-call-held-twice", MT_CALL_LANE_SIDE, MT_CALL_MAIN_SIDE, [TEST_A],
                        resolve=[(TEST_A, MT_BASE + MT_DUP + MT_LANE + MT_CALL_LANE + MT_MAIN + MT_CALL_MAIN)],
                        stage=True, files=MT_CALL_FILES)
_mt_refuse("builder-refuse: a merge that keeps a call its parents hold twice only once is refused as lost",
           MT_CALL_ONCE, "lost", (MT_CARRY["lost"],))
# New: the merge adds a call neither parent holds.
MT_CALL_NEW = _mt_case("mt-call-new", MT_CALL_LANE_SIDE, MT_CALL_MAIN_SIDE, [TEST_A],
                       resolve=[(TEST_A, MT_CALL_BOTH + "register_case('builder')\n")], stage=True, files=MT_CALL_FILES)
_mt_refuse("builder-refuse: a merge that adds a top-level call neither parent had is refused as new", MT_CALL_NEW,
           "new", (MT_CARRY["new"],))
# Skip: the call it adds is a skip mark.
MT_CALL_SKIP = _mt_case("mt-call-skip", MT_CALL_LANE_SIDE, MT_CALL_MAIN_SIDE, [TEST_A],
                        resolve=[(TEST_A, MT_CALL_BOTH + "pytest.skip('later')\n")], stage=True, files=MT_CALL_FILES)
_mt_refuse("builder-refuse: a merge that adds a top-level pytest.skip call is refused as a skip", MT_CALL_SKIP,
           "skip", (MT_CARRY["skip"],))

FAMILY = _MT_PRIOR_FAMILY
