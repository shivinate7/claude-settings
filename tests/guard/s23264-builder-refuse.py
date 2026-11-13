# section 23264
FAMILY = "builder-refuse"
TEST_A = "tests/test_a.py"
# The test-author's five cases, added to main's test file on the lane branch.
LANE_FUNCS = ["def test_lane_%d():\n    assert %d\n\n" % (n, n) for n in range(1, 6)]
LANE_TEXT = BASE_FILES[TEST_A] + "".join(LANE_FUNCS)
# What a builder leaves after it removes four of the five: it differs from main AND from the lane tip.
TRIMMED = BASE_FILES[TEST_A] + LANE_FUNCS[0]


def _must(where, *args):
    """One git call a fixture needs. A call that fails stops the run: a broken build proves nothing."""
    done = run_vcs(where, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed: git %s in %r: %s" % (" ".join(args), where, done.stderr.strip()))


def _product_commit(w):
    write(os.path.join(w, "src/app.py"), "x = 3\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "product work")


def _test_author_lane(w, rel=TEST_A, text=LANE_TEXT, more=()):
    """The test-author's commit on branch `lane`, cut from main. Main's checkout ends on main. `more` holds
    (path, text) pairs written into the same commit."""
    main = w + "-main"
    _must(main, "checkout", "-q", "-b", "lane")
    write(os.path.join(main, rel), text)
    for other, other_text in more:
        write(os.path.join(main, other), other_text)
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "test-author cases")
    _must(main, "checkout", "-q", "main")


def _incident(w):
    """Cut at main. `reset --hard` to the lane tip, then the builder removes lines from the test file."""
    _test_author_lane(w)
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(w, TEST_A), TRIMMED)


def _merge_commit(w):
    """Cut at main. The builder commits product work, merges the lane tip (a merge commit), then
    removes lines from the test file."""
    _product_commit(w)
    _test_author_lane(w)
    _must(w, *IDENT, "merge", "-q", "--no-ff", "--no-edit", "lane")
    write(os.path.join(w, TEST_A), TRIMMED)


def _clean_merge(w):
    """Cut at main. The builder merges the lane tip and changes product files only (Oct 2 false alarm)."""
    _test_author_lane(w)
    _must(w, *IDENT, "merge", "-q", "--no-ff", "--no-edit", "lane")
    write(os.path.join(w, "src/app.py"), "x = 4\n")


def _clean_reset(w):
    """Cut at main. The builder resets to the lane tip and changes product files only (Oct 2 false alarm)."""
    _test_author_lane(w)
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(w, "src/app.py"), "x = 4\n")


def _own_then_clean_merge(w):
    """Cut at main. The builder commits product work, merges the lane tip, then changes product files only."""
    _product_commit(w)
    _test_author_lane(w)
    _must(w, *IDENT, "merge", "-q", "--no-ff", "--no-edit", "lane")
    write(os.path.join(w, "src/app.py"), "x = 4\n")


def _launder(w):
    """Cut at main. The builder commits a test edit, makes a product commit on a side branch from it,
    returns to its own branch and resets to the side commit, which contains its own test edit."""
    write(os.path.join(w, TEST_A), "pass\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "own test edit")
    _must(w, "switch", "-q", "-c", "side")
    write(os.path.join(w, "src/app.py"), "x = 5\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "product on side")
    _must(w, "switch", "-q", "work")
    _must(w, "reset", "-q", "--hard", "side")


def _shell_write(w):
    """Cut at main. The test file is written by a Python process, as a Bash `python3 -c` call writes
    it. No write tool runs, so no path check sees the write. Only the diff shows it."""
    code = "open(%r, 'w').write(%r)" % (os.path.join(w, TEST_A), TRIMMED)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    if done.returncode != 0:
        sys.exit("fixture setup failed: python write in %r: %s" % (w, done.stderr.strip()))


NEW_TEST = "tests/test_lane_new.py"


def _stale_revert(w):
    """Cut at main. Reset to a lane tip that adds test lines, then write the test file back to the cut
    point's exact bytes. The cut point is no base once the lane tip is one."""
    _test_author_lane(w)
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(w, TEST_A), BASE_FILES[TEST_A])


def _stale_delete(w):
    """Cut at main. Clean-merge a lane tip that adds a new test file, then delete that file."""
    _test_author_lane(w, NEW_TEST, "def test_lane_new():\n    assert 1\n")
    _must(w, *IDENT, "merge", "-q", "--no-ff", "--no-edit", "lane")
    os.remove(os.path.join(w, NEW_TEST))


def _newer_main_merge(w):
    """Cut at main. The builder commits product work on its lane, main gains a test change, and the
    builder clean-merges main in. It changes no test."""
    _product_commit(w)
    main = w + "-main"
    write(os.path.join(main, TEST_A), BASE_FILES[TEST_A] + "# main's newer case\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main moves")
    _must(w, *IDENT, "merge", "-q", "--no-ff", "--no-edit", "main")
    write(os.path.join(w, "src/app.py"), "x = 4\n")


def _rebase_then_stale_revert(w):
    """Cut at main. The builder commits product work and rebases onto the lane tip, then writes the test
    file back to main's bytes. The rebase received the lane tip, which holds the lane's cases, so main's
    bytes differ from it and the write is refused. Without the rebase, main's bytes match the only base."""
    _product_commit(w)
    _test_author_lane(w)
    _must(w, *IDENT, "rebase", "-q", "lane")
    write(os.path.join(w, TEST_A), BASE_FILES[TEST_A])


def _rebase_clean(w):
    """Cut at main. The builder commits product work, rebases onto the lane tip and changes product files only."""
    _product_commit(w)
    _test_author_lane(w)
    _must(w, *IDENT, "rebase", "-q", "lane")
    write(os.path.join(w, "src/app.py"), "x = 4\n")


def _two_bases_test_edit(w):
    """The long-lived worktree, then a builder's test edit that matches neither of its two bases."""
    _long_lived_main_tests(w)
    write(os.path.join(w, TEST_A), "pass\n")


def _origin(w):
    """A bare remote for the worktree's main checkout, so the builder can push and pull."""
    main = w + "-main"
    bare = w + "-origin"
    _must(main, "init", "-q", "--bare", bare)
    _must(main, "remote", "add", "origin", bare)


def _f1_pull(w):
    """Cut at main. The builder commits product work P and pushes it. The test-author adds test cases T1 on
    top of P and pushes. The builder pulls T1 fast-forward and commits product work again. The pull is a
    base the builder received, and it holds the builder's own P."""
    main = w + "-main"
    _origin(w)
    _product_commit(w)
    _must(w, "push", "-q", "origin", "HEAD:refs/heads/feat")
    _must(main, "fetch", "-q", "origin")
    _must(main, "checkout", "-q", "-b", "lane", "origin/feat")
    write(os.path.join(main, TEST_A), LANE_TEXT)
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "test-author cases")
    _must(main, "push", "-q", "origin", "lane:refs/heads/feat")
    _must(main, "checkout", "-q", "main")
    _must(w, "pull", "-q", "--ff-only", "origin", "feat")
    write(os.path.join(w, "src/app.py"), "x = 4\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "product work again")


def _f1b_push_reset(w):
    """Cut at main. The builder commits a test edit C1 and pushes it. It resets to the cut point, then to its
    pushed C1, which holds its own commit, and commits product work on top."""
    _origin(w)
    write(os.path.join(w, TEST_A), "pass\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "own test edit")
    _must(w, "push", "-q", "origin", "HEAD:refs/heads/feat")
    _must(w, "reset", "-q", "--hard", "HEAD~1")
    _must(w, "reset", "-q", "--hard", "origin/feat")
    write(os.path.join(w, "src/app.py"), "x = 5\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "product work")


def _f2_conflict_open(w):
    """Cut at main. Reset to a lane tip that adds test cases to the test file. Main then adds a different
    line at the same place in that file. The builder merges main, and the test file conflicts. The merge is
    left in progress: MERGE_HEAD is set, the test file is unmerged, and nothing is committed."""
    main = w + "-main"
    _test_author_lane(w)
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(main, TEST_A), BASE_FILES[TEST_A] + "# main's newer case\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main moves")
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)


def _f2_conflict_merge(w):
    """The open merge of _f2_conflict_open. The builder takes its own side of the test file and commits the
    merge by hand (reflog `commit (merge)`)."""
    _f2_conflict_open(w)
    write(os.path.join(w, TEST_A), LANE_TEXT)
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


def _f2b_clean_merge(w):
    """Cut at main. Reset to a lane tip that adds test cases to one test file. Main adds a different test file.
    The builder merges main cleanly (`Merge made by`), and each test file equals one received base."""
    main = w + "-main"
    _test_author_lane(w)
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(main, "tests/test_main_new.py"), "def test_m():\n    assert 1\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main adds a file")
    _must(w, *IDENT, "merge", "-q", "--no-edit", "main")


def _f2_conflict_then_reset(w):
    """The conflicted own merge of _f2_conflict_merge, then a reset to the lane tip, which leaves that merge
    behind. The test file it conflicted in is no longer in the tree."""
    _f2_conflict_merge(w)
    _must(w, "reset", "-q", "--hard", "lane")


def _product_conflict_merge(w):
    """Cut at main. Reset to a lane tip that changes a product file. Main changes the same product file on the
    same line. The builder merges main, the product file conflicts, and the builder resolves it and commits the
    merge by hand. No test file conflicts."""
    main = w + "-main"
    _must(main, "checkout", "-q", "-b", "lane")
    write(os.path.join(main, "src/app.py"), "x = 6\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "lane product")
    _must(main, "checkout", "-q", "main")
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(main, "src/app.py"), "x = 9\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main product")
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    write(os.path.join(w, "src/app.py"), "x = 7\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


MAIN_FIRST = "def test_main_first():\n    assert 9\n\n"


def _push_main(w):
    """Publish the main checkout's main to the worktree's origin, so the builder can fetch and rebase onto it."""
    _must(w + "-main", "push", "-q", "origin", "main")


def _c1_mid_merge(w, extra_tests=()):
    """Cut at main. The builder commits product work. Main then changes a test file and the product file the
    builder changed, and adds each of `extra_tests`. The builder merges main: the product file conflicts and the
    test files merge clean. The builder resolves the product file and stops before the commit."""
    main = w + "-main"
    _origin(w)
    _push_main(w)
    _product_commit(w)
    write(os.path.join(main, TEST_A), MAIN_FIRST + BASE_FILES[TEST_A])
    for rel in extra_tests:
        write(os.path.join(main, rel), "def test_clean():\n    assert 2\n")
    write(os.path.join(main, "src/app.py"), "x = 10\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main changes a test file and the product file")
    _push_main(w)
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    write(os.path.join(w, "src/app.py"), "x = 12\n")
    _must(w, "add", "-A")


def _c1_committed(w):
    _c1_mid_merge(w)
    _must(w, *IDENT, "commit", "-q", "--no-edit")


# Twenty test files that main adds and the builder never touches: each merges clean into the builder's tree.
MANY_CLEAN_TESTS = ["tests/test_clean_%02d.py" % n for n in range(1, 21)]


def _c1_many_clean(w):
    """The _c1_mid_merge shape, with twenty more test files that main adds and that merge clean beside TEST_A."""
    _c1_mid_merge(w, MANY_CLEAN_TESTS)


def _open_test_conflict_left(w):
    """The open merge of _f2_conflict_open, with the builder's product edit staged. The conflicted test file stays
    as git's merge wrote it, with its conflict markers: a test file that still holds markers is a builder's test
    change, so the builder's commit is refused until the test-author resolves it."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    write(os.path.join(w, "src/app.py"), "x = 7\n")
    _must(w, "add", "src/app.py")


def _open_test_conflict_edited(w):
    """The open merge of _f2_conflict_open, where the builder rewrites the conflicted test file to its own side.
    The bytes are no text git's merge wrote, so this is the builder's own change."""
    _open_test_conflict_left(w)
    write(os.path.join(w, TEST_A), LANE_TEXT)


def _open_test_conflict_mode(w):
    """The open merge of _f2_conflict_open, where the builder sets the exec bit on the conflicted test file and keeps
    git's bytes. The file stays unmerged in the index, so the mode change is the builder's only change to it."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    os.chmod(os.path.join(w, TEST_A), 0o755)
    if not os.stat(os.path.join(w, TEST_A)).st_mode & 0o111:
        sys.exit("fixture setup failed: chmod +x did not land on %r" % TEST_A)


MAIN_CASE = "def test_main_case():\n    assert 3\n"
BUILDER_CASE = "def test_builder_case():\n    assert 4\n"


def _main_test_merge_open(w, builder_text=None):
    """Cut at main. The builder commits product work. Main appends MAIN_CASE to TEST_A, which the builder never
    touches, so git's merge takes it clean. The merge is left open. `builder_text`, when given, then replaces
    TEST_A in the worktree."""
    main = w + "-main"
    _product_commit(w)
    write(os.path.join(main, TEST_A), BASE_FILES[TEST_A] + MAIN_CASE)
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main adds a case")
    _must(w, *IDENT, "merge", "-q", "--no-commit", "--no-ff", "main")
    _require_says(w, ["show", ":" + TEST_A], MAIN_CASE)
    if builder_text is not None:
        write(os.path.join(w, TEST_A), builder_text)


def _main_test_merge_committed(w):
    """The _main_test_merge_open merge, committed as the merge commit. Then the builder appends BUILDER_CASE to
    TEST_A, the test file git's merge took clean."""
    _main_test_merge_open(w)
    _commit_merge(w)
    _require_says(w, ["show", "HEAD:" + TEST_A], MAIN_CASE)
    write(os.path.join(w, TEST_A), BASE_FILES[TEST_A] + MAIN_CASE + BUILDER_CASE)


def _main_test_merge_clean_committed(w):
    """The _main_test_merge_open merge, committed as the builder's merge commit with no builder edit to a test file.
    The commit is git's merge of its two parents, so it holds main's clean test change and nothing the builder wrote."""
    _main_test_merge_open(w)
    _commit_merge(w)
    _require_says(w, ["show", "HEAD:" + TEST_A], MAIN_CASE)
    if len(run_vcs(w, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()) != 3:
        sys.exit("fixture setup failed: HEAD in %r is not a merge commit" % w)


def _f2_conflict_staged(w):
    """The open merge of _f2_conflict_open, with git's markers staged by `git add`: the index holds them as the bytes
    of the test file, and the merge is still open."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    _must(w, "add", "-A")


def _resolve_test_conflict_open(w, text):
    """The open merge of _f2_conflict_open, where the builder rewrites the conflicted test file to `text`, with no
    marker left in it."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    write(os.path.join(w, TEST_A), text)


def _strip_test_conflict_markers(w):
    """The open merge of _f2_conflict_open, where the builder deletes git's three marker lines and keeps both sides."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    path = os.path.join(w, TEST_A)
    with open(path, encoding="utf-8") as handle:
        kept = [line for line in handle if not line.startswith(("<<<<<<< ", "=======", ">>>>>>> "))]
    text = "".join(kept)
    if "<<<<<<<" in text or "def test_lane_1" not in text or "# main's newer case" not in text:
        sys.exit("fixture setup failed: the markers did not strip to both sides in %r" % w)
    write(path, text)


# A top-level test file that an add/add merge conflicts. The base holds no such file, so the lane and main each add it;
# _f2_conflict_open changes tests/test_a.py, which the base holds. The builder's untracked file of the same name sits
# under src/, so the guard must tell the two apart by their folders.
TOP_TEST = "test_x.py"


def _top_test_conflict_open(w):
    """The open merge of an add/add conflict on TOP_TEST: the lane adds the file with one case, main adds it with
    another, and the builder merges main. The conflicted file stays as git's merge wrote it, unmerged, and nothing is
    committed. The builder then adds an untracked test file of the same name under src/."""
    main = w + "-main"
    _test_author_lane(w, TOP_TEST, "def test_x():\n    assert 1\n")
    _must(w, "reset", "-q", "--hard", "lane")
    write(os.path.join(main, TOP_TEST), "def test_x():\n    assert 2\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main adds the same test file")
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    _require_conflict(w, TOP_TEST)
    write(os.path.join(w, "src", TOP_TEST), "def test_x_builder():\n    assert 3\n")


# An empty test file is still a test file: the rows below refuse one added or deleted in a merge. They also refuse a
# test file whose only change is one invalid UTF-8 byte. Both bytes decode to the same character, so only a comparison
# of the bytes tells the two versions apart.
EMPTY_TEST = "tests/test_empty.py"
TEST_BYTES = "tests/test_bytes.py"
COST_PATHS = ["src/app.py", "tests/test_cost_one.py", "tests/test_cost_two.py"]


def _put_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def _rewrite_bytes(path, change):
    with open(path, "rb") as handle:
        raw = handle.read()
    _put_bytes(path, change(raw))


def _clean_merge_open(w, main_adds=None):
    """Cut at main. The builder commits product work. Main adds each file in `main_adds` (path: bytes) and changes a
    product file. The builder merges main with no commit: the merge is clean and stays in progress, so git's own
    merge is the base the builder's change is judged against."""
    main = w + "-main"
    _product_commit(w)
    for rel, data in (main_adds or {}).items():
        _put_bytes(os.path.join(main, rel), data)
    write(os.path.join(main, "src/other.py"), "z = 1\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main adds files")
    _must(w, *IDENT, "merge", "-q", "--no-commit", "--no-ff", "main")


def _empty_add_open(w):
    """A clean merge left open, where the builder adds an empty test file that git's merge does not have."""
    _clean_merge_open(w)
    write(os.path.join(w, EMPTY_TEST), "")


def _empty_delete_open(w):
    """A clean merge left open, where git's merge holds an empty test file and the builder deletes it."""
    _clean_merge_open(w, {EMPTY_TEST: b""})
    os.remove(os.path.join(w, EMPTY_TEST))


def _commit_merge(w):
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


def _empty_add_committed(w):
    """The _empty_add_open change, committed as the builder's merge commit (reflog `commit (merge)`)."""
    _empty_add_open(w)
    _commit_merge(w)


def _empty_delete_committed(w):
    """The _empty_delete_open change, committed as the builder's merge commit."""
    _empty_delete_open(w)
    _commit_merge(w)


def _conflict_crlf(w):
    """The open conflict of _f2_conflict_open, where the builder rewrites the conflicted test file with each LF as
    CRLF. Only the line endings change."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    _rewrite_bytes(os.path.join(w, TEST_A), lambda raw: raw.replace(b"\n", b"\r\n"))


def _conflict_cr(w):
    """As _conflict_crlf, with each LF as a lone CR."""
    _f2_conflict_open(w)
    _require_conflict(w, TEST_A)
    _rewrite_bytes(os.path.join(w, TEST_A), lambda raw: raw.replace(b"\n", b"\r"))


def _invalid_byte_open(w):
    """A clean merge left open, where git's merge holds a test file with one stray byte, 0x80, and the builder
    rewrites that byte to 0x81. Both are invalid UTF-8, so both decode to the same replacement character."""
    _clean_merge_open(w, {TEST_BYTES: b"# \x80\n"})
    _put_bytes(os.path.join(w, TEST_BYTES), b"# \x81\n")


# A gitlink (a submodule entry) and a mode-only change under a test path are refused. A gitlink has no
# bytes in this repository, and a mode-only change keeps the same bytes, so only the mode can refuse either. The rows
# check a gitlink to a commit the clone lacks, a gitlink to a commit the clone holds, and a mode-only change. The
# fixtures read each change back with git first: a change that did not land would give an allow for the wrong reason.
GITLINK = "tests/sub_lib"
GITLINK_MISSING = "0123456789abcdef0123456789abcdef01234567"   # a commit this clone does not hold


def _head_sha(w):
    return run_vcs(w, "rev-parse", "HEAD").stdout.strip()


def _require_says(where, args, want):
    """Stop the suite unless git's answer for `args` in `where` holds `want`."""
    done = run_vcs(where, *args)
    if done.returncode != 0 or want not in done.stdout:
        sys.exit("fixture setup failed: git %s in %r does not show %r: %s"
                 % (" ".join(args), where, want, (done.stdout + done.stderr).strip()))


def _gitlink_stage(w, sha=GITLINK_MISSING):
    """A gitlink under tests/ at `sha`, staged, with the empty folder a checkout would make."""
    os.makedirs(os.path.join(w, GITLINK), exist_ok=True)
    _must(w, "update-index", "--add", "--cacheinfo", "160000," + sha + "," + GITLINK)
    _require_says(w, ["ls-files", "-s", "--", GITLINK], "160000 " + sha)


def _gitlink_open(w):
    """A clean merge left open, where the builder stages a gitlink under tests/ that git's merge does not have."""
    _clean_merge_open(w)
    _gitlink_stage(w)


def _gitlink_committed(w, sha=GITLINK_MISSING):
    """The _gitlink_open change at `sha`, committed as the builder's merge commit."""
    _clean_merge_open(w)
    _gitlink_stage(w, sha)
    _commit_merge(w)
    _require_says(w, ["ls-tree", "HEAD", "--", GITLINK], "160000 commit " + sha)


def _gitlink_committed_held(w):
    """The _gitlink_committed change, to the commit this clone holds (the work branch's HEAD), as a control."""
    _gitlink_committed(w, _head_sha(w))


def _mode_exec(rel):
    """chmod +x on a test file in the worktree: the bytes stay, and only the mode changes."""
    def go(w):
        os.chmod(os.path.join(w, rel), 0o755)
        _require_says(w, ["diff", "--raw", "--", rel], "100644 100755")
    return go


def _mode_exec_committed(w):
    """A clean merge, where the builder sets the exec bit on a test file and commits it as the merge commit."""
    _clean_merge_open(w)
    _must(w, "update-index", "--chmod=+x", TEST_A)
    os.chmod(os.path.join(w, TEST_A), 0o755)
    _commit_merge(w)
    _require_says(w, ["ls-tree", "HEAD", "--", TEST_A], "100755 ")
    _require_says(w, ["ls-tree", "HEAD^1", "--", TEST_A], "100644 ")


def _mode_exec_open(w):
    """A clean merge left open, where the builder sets the exec bit on a test file in the worktree."""
    _clean_merge_open(w)
    _mode_exec(TEST_A)(w)


def _cost_files(w):
    """The builder's change for the cost checks: a product edit and two new test files."""
    write(os.path.join(w, "src/app.py"), "x = 4\n")
    write(os.path.join(w, "tests/test_cost_one.py"), "def test_one():\n    assert 1\n")
    write(os.path.join(w, "tests/test_cost_two.py"), "def test_two():\n    assert 2\n")


def _g_lane_and_product(w):
    """Cut from a lane tip that adds a test case at the end of the test file. The builder commits product work
    on that tip. Main then prepends a test case to the same file, a different hunk, and is published."""
    main = w + "-main"
    _origin(w)
    _test_author_lane(w, TEST_A, LANE_TEXT)
    _must(w, "reset", "-q", "--hard", "lane")
    _product_commit(w)
    write(os.path.join(main, TEST_A), MAIN_FIRST + BASE_FILES[TEST_A])
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main prepends a case")
    _push_main(w)


def _g2_rebase(w):
    _g_lane_and_product(w)
    _must(w, "fetch", "-q", "origin")
    _must(w, *IDENT, "rebase", "origin/main")


def _g3_pull_rebase(w):
    _g_lane_and_product(w)
    _must(w, *IDENT, "pull", "--rebase", "origin", "main")


def _h1r_restore(w):
    """After a clean rebase onto main, the builder writes main's bytes back over the test file, which drops the
    test-author's case. The rebase kept main's side, but that does not license a write made after it: refused."""
    _g2_rebase(w)
    write(os.path.join(w, TEST_A), MAIN_FIRST + BASE_FILES[TEST_A])


def _h1r_committed(w):
    """The write-back of _h1r_restore, committed by the builder. The commit is the builder's own, and it drops
    the test-author's case."""
    _h1r_restore(w)
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "restore main's test file")


def _fixup_rebase(w):
    """Cut at the test-author's lane tip. The builder commits product work, commits a fixup of it, then rebases
    with autosquash. The todo editor is `true`, so the list runs as autosquash built it. Product files only."""
    _test_author_lane(w)
    _must(w, "reset", "-q", "--hard", "lane")
    _product_commit(w)
    write(os.path.join(w, "src/app.py"), "x = 4\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "fixup! product work")
    _must(w, *IDENT, "-c", "sequence.editor=true", "rebase", "-i", "--autosquash", "lane")
    # A rebase that ran no fixup would pass for the wrong reason: check the squash and its reflog step.
    subjects = run_vcs(w, "log", "--format=%s", "lane..HEAD").stdout.splitlines()
    steps = run_vcs(w, "reflog", "--format=%gs", "HEAD").stdout
    if subjects != ["product work"] or "rebase (fixup)" not in steps:
        sys.exit("fixture setup failed: the fixup rebase in %r did not squash: %r" % (w, subjects))


def _b1_cherry(w):
    """Cut at main. The builder cherry-picks a test-author's commit, which adds a test case. The pick commits."""
    main = w + "-main"
    _test_author_lane(w)
    pick = run_vcs(main, "rev-parse", "lane").stdout.strip()
    _must(w, *IDENT, "cherry-pick", pick)


def _b1b_cherry_staged(w):
    """Cut at main. The builder cherry-picks a test-author's commit with --no-commit and stops before the commit."""
    main = w + "-main"
    _test_author_lane(w)
    pick = run_vcs(main, "rev-parse", "lane").stdout.strip()
    _must(w, *IDENT, "cherry-pick", "-n", pick)


def _b1b_cherry_committed(w):
    _b1b_cherry_staged(w)
    _must(w, *IDENT, "commit", "-q", "-m", "cherry-picked test-author cases")


def _j1_squash(w):
    """Cut at main. The builder squash-merges a test-author's lane, which adds a test file, and commits the result."""
    _test_author_lane(w, NEW_TEST, "def test_lane_new():\n    assert 1\n")
    _must(w, *IDENT, "merge", "--squash", "lane")
    _must(w, *IDENT, "commit", "-q", "-m", "squashed test-author case")


def _i1_rebase_ours(w):
    """A test-author's lane changes a line of the test file, and main changes the same line. The builder rebases
    its product commit onto main. The rebase stops in the test file, and the builder keeps the upstream side
    (`--ours` in a rebase). The replayed case is then empty, so the builder skips it."""
    main = w + "-main"
    _origin(w)
    _test_author_lane(w, TEST_A, "def test_a():\n    assert 1 == 1\n")
    _must(w, "reset", "-q", "--hard", "lane")
    _product_commit(w)
    write(os.path.join(main, TEST_A), "def test_a():\n    assert 2 == 2\n")
    _must(main, "add", "-A")
    _must(main, *IDENT, "commit", "-q", "-m", "main changes the case")
    _push_main(w)
    _must(w, "fetch", "-q", "origin")
    stopped = run_vcs(w, *IDENT, "rebase", "origin/main")
    if stopped.returncode == 0:
        sys.exit("fixture setup failed: the rebase in %r did not stop in the test file" % w)
    write(os.path.join(w, TEST_A), "def test_a():\n    assert 2 == 2\n")
    _must(w, "add", "-A")
    cont = run_vcs(w, "-c", "core.editor=true", *IDENT, "rebase", "--continue")
    if cont.returncode != 0:
        _must(w, "rebase", "--skip")


def _u2_new_test(w):
    """The builder adds a test file that no base holds."""
    write(os.path.join(w, "tests/test_new.py"), "def test_new():\n    assert 5\n")


_bd_inc = diff_repo("bd-incident", _incident)
# Case 1: the incident. A reset to the lane tip, then a removed line, is refused at commit and push.
sh("builder-refuse: a reset to the lane tip, then a removed test line, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_inc, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a reset to the lane tip, then a removed test line, is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_inc, agent_id="bld1", agent_type="builder")
# Case 7: the same refused commit names no path, and gives an undo route and the orchestrator.
sh("builder-refuse: the refused commit names no test path and gives an undo route",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_inc, agent_id="bld1", agent_type="builder",
   lacks=("tests/", "test_a"), carries=(("restore", "Restore", "put back"), "orchestrator"))

# Case 2: a merge commit of the lane tip, then a removed line, is refused.
_bd_merge = diff_repo("bd-merge-commit", _merge_commit)
sh("builder-refuse: a merge commit of the lane tip, then a removed test line, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_merge, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a merge commit of the lane tip, then a removed test line, is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_merge, agent_id="bld1", agent_type="builder")

# Case 4: a commit that contains the builder's own test edit is no base, so the edit is still refused.
_bd_launder = diff_repo("bd-launder", _launder)
sh("builder-refuse: a reset to a commit that holds the builder's own test edit is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_launder, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a reset to a commit that holds the builder's own test edit is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_launder, agent_id="bld1", agent_type="builder")

# Case 5: the shell route. A test file written by `python3 -c` (no write tool) is refused by the diff.
_bd_shell = diff_repo("bd-shell", _shell_write)
sh("builder-refuse: a test file written by a Python process is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_shell, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a test file written by a Python process is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_shell, agent_id="bld1", agent_type="builder")

# Stale revert: the cut point's bytes are no base once a reset has moved the worktree to a lane tip
# that holds the test lines. The reverted file differs from that tip, so it is refused.
_bd_stale = diff_repo("bd-stale-revert", _stale_revert)
sh("builder-refuse: a stale revert to the cut point's bytes, after a reset to a lane tip, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_stale, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a stale revert to the cut point's bytes, after a reset to a lane tip, is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_stale, agent_id="bld1", agent_type="builder")

# Stale delete: a file the clean merge brought in is no base once the merge result holds it.
_bd_stale_del = diff_repo("bd-stale-delete", _stale_delete)
sh("builder-refuse: a stale delete of a test file a clean merge brought in is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_stale_del, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a stale delete of a test file a clean merge brought in is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_stale_del, agent_id="bld1", agent_type="builder")

# Newer main: a builder that clean-merges a newer main into its own lane, and changes no test, is
# allowed. The newer main is a base, and the file equals it.
_bd_newer = diff_repo("bd-newer-main", _newer_main_merge)
sh("builder-refuse: a builder that clean-merges a newer main and changes no test is allowed at commit",
   COMMIT, "allow", cwd=_bd_newer, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder that clean-merges a newer main and changes no test is allowed at push",
   PUSH, "allow", cwd=_bd_newer, agent_id="bld1", agent_type="builder")

# Rebase: a builder that rebases onto the lane tip is judged against that tip. A test file written back
# to main's bytes differs from it, so it is refused. The clean rebase is checked with the log checks below.
_bd_rebase = diff_repo("bd-rebase-stale", _rebase_then_stale_revert)
sh("builder-refuse: a builder's rebase onto a lane tip, then a test file written back to main's bytes, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_rebase, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's rebase onto a lane tip, then a test file written back to main's bytes, is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_rebase, agent_id="bld1", agent_type="builder")

# Two received bases: a test edit that matches neither is refused, and the refusal names no test path.
_bd_two = diff_repo("bd-two-bases", _two_bases_test_edit)
sh("builder-refuse: a test edit that matches neither of two received bases is denied at commit, naming no test path",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_two, agent_id="bld1", agent_type="builder",
   lacks=("tests/", "test_a"), carries=(("restore", "Restore", "put back"), "orchestrator"))

# Launder, kept: a test edit the builder pushed, then reset back to, is still its own test edit.
_bd_f1b = diff_repo("bd-f1b-push-reset", _f1b_push_reset)
sh("builder-refuse: a builder's pushed test edit, then a reset back to that push, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_f1b, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's pushed test edit, then a reset back to that push, is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_f1b, agent_id="bld1", agent_type="builder")

# A merge that conflicts in a test file and is resolved to the builder's own side is a test-author's to
# resolve, so it is denied.
_bd_f2 = diff_repo("bd-f2-conflict", _f2_conflict_merge)
sh("builder-refuse: a builder's merge of main that conflicts in a test file, resolved to its own side, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_f2, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's merge of main that conflicts in a test file, resolved to its own side, is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_f2, agent_id="bld1", agent_type="builder")

# Case 8: a test-author's product edit is still allowed at commit. Its log line is pinned by
# diff_refusal_case (the a-product-edit row: author-diff at commit, push and stop).
sh("builder-refuse: a test-author's commit with a product file is allowed",
   COMMIT, "allow", cwd=os.path.join(DIFFROOT, "a-product-edit"), agent_id="auth1",
   agent_type="test-author")

# The xctestplan skip is a test change too (builder-refuse, not logged). Its repo is built once, here.
_bd_plan = _plan_repo("xctestplan-skip", XCTESTPLAN_SKIP)
sh("builder-refuse: a builder's skippedTests line is denied at commit", COMMIT, "deny", rule=BDIFF,
   cwd=_bd_plan, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's skippedTests line is denied at push", PUSH, "deny", rule=BDIFF,
   cwd=_bd_plan, agent_id="bld1", agent_type="builder")
add("builder-refuse: a builder's skippedTests line is blocked at the first stop", "deny", rule=BDIFF,
    event="SubagentStop", cwd=_bd_plan, agent_id="bld1", agent_type="builder")


def clean_builder_case(label):
    """Case 3, the Oct 2 false alarm. A builder that joined the lane tip and changed product files
    only is allowed at commit, push and stop, and writes no builder-diff line."""
    def case():
        out, rows = _diff_log_run(os.path.join(ROOT, "difflog-" + label),
                                  os.path.join(DIFFROOT, label), "builder", "bld1")
        hits = [r for r in rows if len(r) > 3 and r[3] == BDIFF]
        if out or hits:
            return False, "expected silent allows and no builder-diff line, got %r and %d line(s)" % (
                out[:60], len(hits))
        return True, "allowed at commit, push and stop; no builder-diff line"
    return case


diff_repo("bd-clean-merge", _clean_merge)
diff_repo("bd-clean-reset", _clean_reset)
diff_repo("bd-own-clean-merge", _own_then_clean_merge)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder that merges the lane tip and changes product files "
                         "only is allowed and logs no builder-diff line", clean_builder_case("bd-clean-merge")))
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder that resets to the lane tip and changes product files "
                         "only is allowed and logs no builder-diff line", clean_builder_case("bd-clean-reset")))
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder with its own product commit that then merges the lane "
                         "tip is allowed and logs no builder-diff line",
                         clean_builder_case("bd-own-clean-merge")))
diff_repo("bd-clean-rebase", _rebase_clean)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder that rebases onto a lane tip and changes product files "
                         "only is allowed and logs no builder-diff line", clean_builder_case("bd-clean-rebase")))


def two_bases_reason_case():
    """A deny on a test edit that matches neither of two received bases names no path and no commit, and its
    one reason gives both undo routes: restore a changed test file, and delete a new one. The rule reads no
    bases, so the reason cannot name one."""
    out, _rows = _diff_log_run(os.path.join(ROOT, "difflog-bd-two"), _bd_two, "builder", "bld1")
    answers = _guard_answers(out)
    if not answers:
        return False, "no guard answer for the commit"
    decision, reason = answers[0]
    main = _bd_two + "-main"
    commits = [run_vcs(main, "rev-parse", rev).stdout.strip() for rev in ("lane", "main", "main~1")]
    problems = []
    if decision != "deny":
        problems.append("expected deny at commit, got %r" % decision)
    for sha in commits:
        if sha[:12] in reason:
            problems.append("the reason names a commit, %s" % sha[:12])
    for word in ("tests/", "test_a"):
        if word in reason:
            problems.append("the reason names a test path: %r" % word)
    for route in ("restore", "delete"):
        if route not in reason.lower():
            problems.append("the reason gives no %r undo route" % route)
    return (not problems), ("; ".join(problems) or "the deny names no path and no commit, and gives both undo routes")


LOG_CHECKS_EXTRA.append(("builder-refuse: a deny on a test edit that matches neither of two received bases names no "
                         "path or commit, and gives both undo routes", two_bases_reason_case))
# A pull of a test-author's fast-forward onto the builder's own product commit is a received base.
diff_repo("bd-f1-pull", _f1_pull)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder that pulls a test-author's fast-forward over its own product "
                         "commit, then commits product work, is allowed and logs no builder-diff line",
                         clean_builder_case("bd-f1-pull")))
# A clean merge where each side changed a different test file: each file equals one received base.
diff_repo("bd-f2b-clean-merge", _f2b_clean_merge)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's clean merge of main, where each side changed a different "
                         "test file, is allowed and logs no builder-diff line", clean_builder_case("bd-f2b-clean-merge")))
# The conflicted merge a builder resets away leaves no resolution in the tree, so its test file is not judged.
diff_repo("bd-conflict-reset", _f2_conflict_then_reset)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's conflicted merge of a test file, which it then resets away, "
                         "is allowed and logs no builder-diff line", clean_builder_case("bd-conflict-reset")))
# A conflict both sides made in a product file is no test path, so it does not offend for a builder.
diff_repo("bd-product-conflict", _product_conflict_merge)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's conflicted merge of a product file, both sides changed it, "
                         "is allowed and logs no builder-diff line", clean_builder_case("bd-product-conflict")))


def author_silent_case(repo, label):
    """A test-author's change in `repo` is never refused, and writes no author-diff or builder-diff line."""
    def case():
        out, rows = _diff_log_run(os.path.join(ROOT, "difflog-" + label), repo, "test-author", "auth1")
        hits = [r for r in rows if len(r) > 3 and r[3] in (BDIFF, "author-diff")]
        if out:
            return False, "a test-author's change was refused: %r" % out[:60]
        if hits:
            return False, "a test-author's change was logged: %d line(s)" % len(hits)
        return True, "allowed at commit, push and stop; no builder-diff or author-diff line"
    return case


# A test-author's conflicted merge of a test file is never refused, and logs nothing: a test file is the
# test-author's own work, so the conflict is no offence for it.
author_conflict_case = author_silent_case(_bd_f2, "author-conflict")


LOG_CHECKS_EXTRA.append(("builder-refuse: a test-author's conflicted merge of a test file is never refused and logs nothing",
                         author_conflict_case))


def logged_case(label, agent_type, agent_id, rule):
    """Log-only: nothing is refused at commit, push or stop, and at least one `rule` line is written. The repo
    is the diff repo named `label`."""
    def case():
        out, rows = _diff_log_run(os.path.join(ROOT, "difflog-" + label), os.path.join(DIFFROOT, label),
                                  agent_type, agent_id)
        hits = [r for r in rows if len(r) > 3 and r[2] == "noted" and r[3] == rule]
        if out:
            return False, "expected no refusal, got %r" % out[:60]
        if not hits:
            return False, "expected a %s line, found none" % rule
        return True, "not refused at commit, push or stop; %d %s line(s)" % (len(hits), rule)
    return case


def logged_builder_case(label):
    """Log-only for a builder: nothing is refused, and at least one builder-diff line is written."""
    return logged_case(label, "builder", "bld1", BDIFF)


# ---- the mixed merge: one merge that conflicts in a test file AND a product file (decision
# builders-cannot-edit-tests, "What the builder wrote"). The test-author owns a product path its merge left
# conflicted, since git's own merge left it conflicted. A builder keeps every test path it resolved, here too.
# `src/clean.py` merges clean, so it is no test-author's to change. `src/other.py` is in no merge at all.
MIXED_FILES = {**BASE_FILES, "src/clean.py": "z = 0\n"}


def _put_commit(where, files, message):
    """Write each (path, text) of `files` under `where`, and commit them in one commit."""
    for rel, text in files:
        write(os.path.join(where, rel), text)
    _must(where, "add", "-A")
    _must(where, *IDENT, "commit", "-q", "-m", message)


def _mixed_mid_merge(w, rel=TEST_A):
    """Cut at main. The lane changes `rel` (the test file by default) and src/app.py. Main changes the same lines in
    both (a conflict in each) and src/clean.py, which the lane never touches (a clean merge). Main is merged in and
    the merge is left in progress: MERGE_HEAD is set, and the two conflicts are unmerged. `rel` may name a mutation
    test or a near-miss name instead: only the path differs."""
    main = w + "-main"
    _test_author_lane(w, rel, LANE_TEXT, more=(("src/app.py", "x = 6\n"),))
    _must(w, "reset", "-q", "--hard", "lane")
    _put_commit(main, [(rel, BASE_FILES[TEST_A] + "# main's newer case\n"), ("src/app.py", "x = 9\n"),
                       ("src/clean.py", "z = 1\n")], "main moves")
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    _require_conflict(w, rel)
    _require_conflict(w, "src/app.py")
    with open(os.path.join(w, "src/clean.py"), encoding="utf-8") as handle:
        clean = handle.read()
    if clean != "z = 1\n":
        sys.exit("fixture setup failed: src/clean.py did not merge clean in %r: %r" % (w, clean))


def _mixed_merge_commit(w, clean=None):
    """`_mixed_mid_merge`, resolved by hand and committed. The test file takes the lane's text, and src/app.py takes
    a text neither side holds. `clean`, when given, is the text the merge commit also gives src/clean.py."""
    _mixed_mid_merge(w)
    write(os.path.join(w, TEST_A), LANE_TEXT)
    write(os.path.join(w, "src/app.py"), "x = 7\n")
    if clean is not None:
        write(os.path.join(w, "src/clean.py"), clean)
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


def _mixed_ours_commit(w):
    """`_mixed_mid_merge`, then a builder keeps its own side of the test file whole (`git checkout --ours`),
    resolves src/app.py by hand, and commits the merge."""
    _mixed_mid_merge(w)
    _must(w, "checkout", "--ours", "--", TEST_A)
    write(os.path.join(w, "src/app.py"), "x = 7\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


def _merge_adds_test(w):
    """Cut at main. Main changes src/clean.py, a clean merge. The builder merges with --no-commit, adds a test
    function that neither side holds, and commits: the merge commit itself holds the builder's test text."""
    _put_commit(w + "-main", [("src/clean.py", "z = 1\n")], "main moves")
    _must(w, *IDENT, "merge", "-q", "--no-commit", "--no-ff", "main")
    write(os.path.join(w, TEST_A), BASE_FILES[TEST_A] + "def test_builder_added():\n    assert 4\n\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


MIXED_MID = diff_repo("ta-mixed-mid", _mixed_mid_merge, files=MIXED_FILES)
MIXED_DONE = diff_repo("ta-mixed-done", _mixed_merge_commit, files=MIXED_FILES)
MIXED_CLEAN = diff_repo("ta-mixed-clean", lambda w: _mixed_merge_commit(w, clean="z = 2\n"), files=MIXED_FILES)
MIXED_OURS = diff_repo("bd-mixed-ours", _mixed_ours_commit, files=MIXED_FILES)
MERGE_ADDS = diff_repo("bd-merge-adds-test", _merge_adds_test, files=MIXED_FILES)

AUTH_MIXED = dict(agent_id="auth1", agent_type="test-author", cwd=MIXED_MID)
# Case 1 (red today): a test-author may write a product path its merge conflicts, because git's own merge left
# it conflicted. The write tool refuses it today (test-author-scope).
add("test-author: Edit of a product file its merge conflicts is allowed", "allow", tool="Edit",
    file_path=os.path.join(MIXED_MID, "src/app.py"), new_string="x = 7\n", **AUTH_MIXED)
add("test-author: Write of a product file its merge conflicts is allowed", "allow", tool="Write",
    file_path=os.path.join(MIXED_MID, "src/app.py"), content="x = 7\n", **AUTH_MIXED)
# Case 2 (green pin): a product path the merge merged clean, or that no merge holds, stays refused.
add("test-author: Edit of a product file the merge merged clean is refused", "deny", rule=TA, tool="Edit",
    file_path=os.path.join(MIXED_MID, "src/clean.py"), new_string="z = 2\n", carries=("builder", "Report"),
    **AUTH_MIXED)
add("test-author: Edit of a product file outside the merge is refused", "deny", rule=TA, tool="Edit",
    file_path=os.path.join(MIXED_MID, "src/other.py"), new_string="w = 1\n", carries=("builder", "Report"),
    **AUTH_MIXED)
# Case 3 (red today): a test-author's merge commit resolves a conflicted test file and a conflicted product
# file. The product path is the test-author's, so no author-diff line is written.
LOG_CHECKS_EXTRA.append(("builder-refuse: a test-author's merge commit that resolves a conflicted test file and a "
                         "conflicted product file is never refused and logs no author-diff line",
                         author_silent_case(MIXED_DONE, "ta-mixed-done")))
# Case 4 (green pin): the same merge commit also changes a product file that merged clean. That path is no
# test-author's, so its author-diff line stays.
LOG_CHECKS_EXTRA.append(("builder-refuse: a test-author's merge commit that also changes a product file that merged "
                         "clean is still logged as author-diff",
                         logged_case("ta-mixed-clean", "test-author", "auth1", "author-diff")))
# Case 5 (green pin): a builder keeps its own side of a test conflict with `git checkout --ours`, in a merge that
# also conflicts a product file. A builder keeps the rule, so the test path is refused at commit, push and stop.
# The same outcome without the product conflict is pinned by `bd-f2-conflict`, which resolves by a write.
sh("builder-refuse: a builder's merge that keeps its own side of a test conflict with checkout --ours is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=MIXED_OURS, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's merge that keeps its own side of a test conflict with checkout --ours is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=MIXED_OURS, agent_id="bld1", agent_type="builder")
add("builder-refuse: a builder's merge that keeps its own side of a test conflict with checkout --ours is blocked at the first stop",
    "deny", rule=BDIFF, event="SubagentStop", cwd=MIXED_OURS, agent_id="bld1", agent_type="builder")
# Case 6 (green pin): a merge commit that adds a test function neither parent holds. No other case pins this:
# `_c1_committed` commits main's test text, and `_merge_main_in` leaves the builder's text uncommitted.
sh("builder-refuse: a builder's merge commit that adds a new test function is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=MERGE_ADDS, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's merge commit that adds a new test function is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=MERGE_ADDS, agent_id="bld1", agent_type="builder")
add("builder-refuse: a builder's merge commit that adds a new test function is blocked at the first stop",
    "deny", rule=BDIFF, event="SubagentStop", cwd=MERGE_ADDS, agent_id="bld1", agent_type="builder")


def _author_test_commit(w):
    """Cut at main. The test-author edits its test file and commits: an ordinary commit, no merge."""
    write(os.path.join(w, TEST_A), BASE_FILES[TEST_A] + "def test_author_ordinary():\n    assert 6\n\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "test-author case")


def _author_merge_test_edit(w):
    """Cut at main. Main adds a test file the lane never touches, so the merge brings it in clean. The test-author
    merges with --no-commit, edits that clean-merged test file, and commits: the merge commit changes a test file."""
    _put_commit(w + "-main", [("tests/test_main_new.py", "def test_m():\n    assert 1\n")], "main adds a test")
    _must(w, *IDENT, "merge", "-q", "--no-commit", "--no-ff", "main")
    write(os.path.join(w, "tests/test_main_new.py"), "def test_m():\n    assert 2\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


TA_TEST_COMMIT = diff_repo("ta-test-commit", _author_test_commit)
TA_MERGE_TEST = diff_repo("ta-merge-test-edit", _author_merge_test_edit)
# Case 7 (green pin; red on the role-diff mutant that judges a test-author as a builder): a test-author's ordinary
# commit of a test file, with no merge, logs no author-diff line.
LOG_CHECKS_EXTRA.append(("builder-refuse: a test-author's ordinary commit of a test file is never refused and logs "
                         "no author-diff line",
                         author_silent_case(TA_TEST_COMMIT, "ta-test-commit")))
# Case 8 (green pin; red on the same mutant): a test file that merged clean, which the test-author edits in its merge
# commit, logs no author-diff line. A merge the test file only came in by changes nothing here, so the edit is the case.
LOG_CHECKS_EXTRA.append(("builder-refuse: a test-author's merge commit that edits a test file that merged clean logs "
                         "no author-diff line",
                         author_silent_case(TA_MERGE_TEST, "ta-merge-test-edit")))


# ---- the test-author's merge route covers the product paths a merge left conflicted, in a merge that has a test
# conflict (decision builders-cannot-edit-tests). A merge with no test path conflicted gives no path that route, and
# a conflicted workflow keeps its content check. `src/app.py` is the only conflict in the product-only merge.
def _product_mid_merge(w):
    """Cut at main. The lane changes src/app.py, and main changes the same line. No test path is in the merge.
    Main is merged in and the merge is left in progress with src/app.py conflicted."""
    main = w + "-main"
    _test_author_lane(w, "src/app.py", "x = 6\n")
    _must(w, "reset", "-q", "--hard", "lane")
    _put_commit(main, [("src/app.py", "x = 9\n")], "main moves")
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    _require_conflict(w, "src/app.py")


def _product_merge_commit(w):
    """`_product_mid_merge`, resolved by hand and committed: src/app.py takes a text neither side holds."""
    _product_mid_merge(w)
    write(os.path.join(w, "src/app.py"), "x = 7\n")
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "--no-edit")


CI = ".github/workflows/ci.yml"
CI_LINT = "      - name: Lint\n        run: python3 lint/ste_lint.py\n"
CI_BASE = "on: push\njobs:\n  check:\n    steps:\n" + CI_LINT
CI_FILES = {**MIXED_FILES, CI: CI_BASE}


def _mixed_workflow_mid_merge(w):
    """Cut at main. The lane changes the test file and the lint step's run line in ci.yml. Main changes the same two
    (a conflict in each). The merge is left in progress with both conflicted."""
    main = w + "-main"
    _test_author_lane(w, TEST_A, LANE_TEXT, more=((CI, CI_BASE.replace("ste_lint.py", "lane_lint.py")),))
    _must(w, "reset", "-q", "--hard", "lane")
    _put_commit(main, [(TEST_A, BASE_FILES[TEST_A] + "# main's newer case\n"),
                       (CI, CI_BASE.replace("ste_lint.py", "main_lint.py"))], "main moves")
    merged = run_vcs(w, *IDENT, "merge", "--no-edit", "main")
    if merged.returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    _require_conflict(w, TEST_A)
    _require_conflict(w, CI)


PROD_MID = diff_repo("ta-prod-mid", _product_mid_merge, files=MIXED_FILES)
PROD_DONE = diff_repo("ta-prod-done", _product_merge_commit, files=MIXED_FILES)
CI_MID = diff_repo("ta-ci-mixed-mid", _mixed_workflow_mid_merge, files=CI_FILES)
AUTH_PROD = dict(agent_id="auth1", agent_type="test-author", cwd=PROD_MID)
AUTH_CI = dict(agent_id="auth1", agent_type="test-author", cwd=CI_MID)
# Case 9: a product-only conflict merge. The test-author's Edit of the conflicted product file is refused,
# because no test path is conflicted and the merge route has no product path to give.
add("test-author: Edit of a product file its merge conflicts, with no test path conflicted, is refused", "deny",
    rule=TA, tool="Edit", file_path=os.path.join(PROD_MID, "src/app.py"), new_string="x = 7\n",
    carries=("builder", "Report"), **AUTH_PROD)
# Case 10: that product-only conflict merge's commit logs author-diff for the product path.
LOG_CHECKS_EXTRA.append(("builder-refuse: a test-author's merge commit that resolves a product-only conflict logs "
                         "author-diff",
                         logged_case("ta-prod-done", "test-author", "auth1", "author-diff")))
# Case 11: a mixed merge that conflicts a test file and ci.yml. An Edit of ci.yml that changes a non-test step is
# refused. The merge route covers product paths only: a workflow keeps its content check.
add("test-author: Edit of a workflow that changes a non-test step in a mixed merge is refused", "deny", rule=TA,
    tool="Edit", file_path=os.path.join(CI_MID, CI), old_string=CI_LINT,
    new_string=CI_LINT.replace("ste_lint.py", "other_lint.py"), carries=("builder", "Report"), **AUTH_CI)

# ---- the merge route for a mutation test (decision builders-cannot-edit-tests, "Merge route"). A mutation test is test
# code only a test-author edits, so a merge that conflicts one of the three (AUTHOR_MUTATION_TESTS) gives its
# test-author the conflicted product paths, as a conflicted test file does. Each fixture is `_mixed_mid_merge` with the
# mutation test as its conflicted path: src/app.py conflicts beside it, and src/clean.py merges clean.
MUT_GUARD, MUT_SHARED, MUT_SWEEP = "hooks/mutate_guard.py", "hooks/mutate_shared.py", "janitor/mutate_sweep.py"
MUT_FILES = {**MIXED_FILES, MUT_GUARD: BASE_FILES[TEST_A], MUT_SHARED: BASE_FILES[TEST_A], MUT_SWEEP: BASE_FILES[TEST_A]}
MUT_GUARD_MID = diff_repo("ta-mut-guard-mid", lambda w: _mixed_mid_merge(w, MUT_GUARD), files=MUT_FILES)
MUT_SHARED_MID = diff_repo("ta-mut-shared-mid", lambda w: _mixed_mid_merge(w, MUT_SHARED), files=MUT_FILES)
MUT_SWEEP_MID = diff_repo("ta-mut-sweep-mid", lambda w: _mixed_mid_merge(w, MUT_SWEEP), files=MUT_FILES)
# Near misses: a name that looks like a mutation test but is product code, so the route stays shut for it. A fix that
# matches the prefix (`mutate_*.py`) or the basename alone (MUTATION_TEST_NAMES) would open it.
NEAR_A, NEAR_B = "hooks/mutate_x.py", "src/mutate_guard.py"
NEAR_FILES = {**MIXED_FILES, NEAR_A: BASE_FILES[TEST_A], NEAR_B: BASE_FILES[TEST_A]}
NEAR_A_MID = diff_repo("ta-near-a-mid", lambda w: _mixed_mid_merge(w, NEAR_A), files=NEAR_FILES)
NEAR_B_MID = diff_repo("ta-near-b-mid", lambda w: _mixed_mid_merge(w, NEAR_B), files=NEAR_FILES)

AUTH_MUT_GUARD = dict(agent_id="auth1", agent_type="test-author", cwd=MUT_GUARD_MID)
AUTH_MUT_SHARED = dict(agent_id="auth1", agent_type="test-author", cwd=MUT_SHARED_MID)
AUTH_MUT_SWEEP = dict(agent_id="auth1", agent_type="test-author", cwd=MUT_SWEEP_MID)
AUTH_NEAR_A = dict(agent_id="auth1", agent_type="test-author", cwd=NEAR_A_MID)
AUTH_NEAR_B = dict(agent_id="auth1", agent_type="test-author", cwd=NEAR_B_MID)
BLD_MUT_GUARD = dict(agent_id="bld1", agent_type="builder", cwd=MUT_GUARD_MID)
# (i) Case 1's form, in a merge that also conflicts a mutation test. No test path is conflicted here, so the route is
# shut and the Edit is refused on main (red). Each of the three mutation tests is its own merge.
add("test-author: Edit of a product file its merge conflicts, beside a conflicted hooks/mutate_guard.py, is allowed",
    "allow", tool="Edit", file_path=os.path.join(MUT_GUARD_MID, "src/app.py"), new_string="x = 7\n", **AUTH_MUT_GUARD)
add("test-author: Edit of a product file its merge conflicts, beside a conflicted hooks/mutate_shared.py, is allowed",
    "allow", tool="Edit", file_path=os.path.join(MUT_SHARED_MID, "src/app.py"), new_string="x = 7\n", **AUTH_MUT_SHARED)
add("test-author: Edit of a product file its merge conflicts, beside a conflicted janitor/mutate_sweep.py, is allowed",
    "allow", tool="Edit", file_path=os.path.join(MUT_SWEEP_MID, "src/app.py"), new_string="x = 7\n", **AUTH_MUT_SWEEP)
# (ii) A merge that conflicts only product files: the near-miss name is product code, so no test path and no mutation
# test is conflicted. Refused on main, and must stay refused. Case 9 pins the plain product-only merge.
add("test-author: Edit of a product file its merge conflicts, beside a conflicted hooks/mutate_x.py, is refused", "deny",
    rule=TA, tool="Edit", file_path=os.path.join(NEAR_A_MID, "src/app.py"), new_string="x = 7\n",
    carries=("builder", "Report"), **AUTH_NEAR_A)
add("test-author: Edit of a product file its merge conflicts, beside a conflicted src/mutate_guard.py, is refused", "deny",
    rule=TA, tool="Edit", file_path=os.path.join(NEAR_B_MID, "src/app.py"), new_string="x = 7\n",
    carries=("builder", "Report"), **AUTH_NEAR_B)
# (iii) In the mutate_guard merge: a builder's Edit of the conflicted mutation test is refused (builder-test-edit), and
# its Edit of the conflicted product file is allowed, as main allows it today.
add("builder-test: Edit of hooks/mutate_guard.py in a merge that conflicts it is refused", "deny", rule=BT, tool="Edit",
    file_path=os.path.join(MUT_GUARD_MID, MUT_GUARD), new_string="x = 2\n", carries=("test-author", "Report"),
    **BLD_MUT_GUARD)
add("builder-test: Edit of the conflicted src/app.py in a merge that conflicts hooks/mutate_guard.py is allowed", "allow",
    tool="Edit", file_path=os.path.join(MUT_GUARD_MID, "src/app.py"), new_string="x = 2\n", **BLD_MUT_GUARD)
# (iv) In the same merge, a product path that merged clean stays refused for the test-author.
add("test-author: Edit of a product file the merge merged clean, beside a conflicted hooks/mutate_guard.py, is refused",
    "deny", rule=TA, tool="Edit", file_path=os.path.join(MUT_GUARD_MID, "src/clean.py"), new_string="z = 2\n",
    carries=("builder", "Report"), **AUTH_MUT_GUARD)


def refused_push_and_stop_case(label):
    """A builder's own commit holds a test change. Push and the first stop are each denied, and each denial
    writes a builder-diff line. The commit check is left out: the row names push and stop only."""
    def case():
        out, rows = _diff_log_run(os.path.join(ROOT, "difflog-" + label), os.path.join(DIFFROOT, label),
                                  "builder", "bld1", commit=False)
        decisions = [decision for decision, _reason in _guard_answers(out)]
        denied = [r for r in rows if len(r) > 3 and r[2] == "deny" and r[3] == BDIFF]
        if decisions != ["deny", "deny"]:
            return False, "expected a deny at push and at the first stop, got %r" % decisions
        if len(denied) != 2:
            return False, "expected two builder-diff deny lines, got %d" % len(denied)
        return True, "denied at push and at the first stop; two builder-diff deny lines"
    return case


# Allow: a merge result and a plain cherry-pick of a test-author commit are git's, not the builder's. A commit
# the builder makes from a staged pick or a squash is its own (the rows below).
# The commit check runs in the state the builder stops in; push and stop run after the commit.
_bd_c1_pre = diff_repo("bd-c1-pre", _c1_mid_merge)
sh("builder-refuse: a merge of main with a product-file conflict, while main changed a test file, is allowed at commit",
   COMMIT, "allow", cwd=_bd_c1_pre, agent_id="bld1", agent_type="builder")
diff_repo("bd-c1-post", _c1_committed)
LOG_CHECKS_EXTRA.append(("builder-refuse: a merge of main with a product-file conflict, while main changed a test "
                         "file, is allowed at push and stop, and logs no builder-diff line",
                         clean_builder_case("bd-c1-post")))
diff_repo("bd-g2-rebase", _g2_rebase)
LOG_CHECKS_EXTRA.append(("builder-refuse: a rebase onto main where a test-author's commit and main change the same "
                         "test file in different hunks is allowed and logs no builder-diff line",
                         clean_builder_case("bd-g2-rebase")))
diff_repo("bd-g3-pull", _g3_pull_rebase)
LOG_CHECKS_EXTRA.append(("builder-refuse: a pull --rebase onto main where a test-author's commit and main change the "
                         "same test file in different hunks is allowed and logs no builder-diff line",
                         clean_builder_case("bd-g3-pull")))
diff_repo("bd-b1-cherry", _b1_cherry)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's cherry-pick of a test-author's commit is allowed and logs no "
                         "builder-diff line", clean_builder_case("bd-b1-cherry")))
_bd_b1b = diff_repo("bd-b1b-staged", _b1b_cherry_staged)
sh("builder-refuse: a builder's cherry-pick of a test-author's commit with --no-commit is allowed at commit",
   COMMIT, "allow", cwd=_bd_b1b, agent_id="bld1", agent_type="builder")
# A staged cherry-pick that the builder commits, and a squash the builder commits, are plain commits of its own.
# Their test file is refused at push and stop. A squash commit cannot be told apart from the builder's own commit,
# so this is a known gap, named in docs/debts/notes.md (builders-squash-cherry-pick-n).
diff_repo("bd-b1b-committed", _b1b_cherry_committed)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's cherry-pick of a test-author's commit with --no-commit, then a "
                         "commit, is denied at push and at the first stop",
                         refused_push_and_stop_case("bd-b1b-committed")))
diff_repo("bd-j1-squash", _j1_squash)
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's squash merge of a test-author's lane is denied at push and at "
                         "the first stop", refused_push_and_stop_case("bd-j1-squash")))

# A write after a rebase is the builder's own. Main's bytes written back over a test file the rebase replayed
# drop the test-author's case, so the write is refused at commit, push and stop.
_bd_h1r = diff_repo("bd-h1r-restore", _h1r_restore)
sh("builder-refuse: after a rebase, main's bytes written back over a test file are denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_h1r, agent_id="bld1", agent_type="builder")
sh("builder-refuse: after a rebase, main's bytes written back over a test file are denied at push",
   PUSH, "deny", rule=BDIFF, cwd=_bd_h1r, agent_id="bld1", agent_type="builder")
add("builder-refuse: after a rebase, main's bytes written back over a test file are blocked at the first stop",
    "deny", rule=BDIFF, event="SubagentStop", cwd=_bd_h1r, agent_id="bld1", agent_type="builder")
# The same write, committed by the builder: the commit holds the drop, so push and the first stop are refused.
diff_repo("bd-h1r-committed", _h1r_committed)
LOG_CHECKS_EXTRA.append(("builder-refuse: after a rebase, main's bytes written back over a test file and committed are "
                         "denied at push and at the first stop",
                         refused_push_and_stop_case("bd-h1r-committed")))
# Allowed, no test edit: a rebase -i that squashes the builder's fixup into its product commit. It logs nothing.
diff_repo("bd-fixup-rebase", _fixup_rebase)
LOG_CHECKS_EXTRA.append(("builder-refuse: a rebase -i that squashes a fixup of the builder's product commits is allowed "
                         "at commit, push and stop, and logs no builder-diff line",
                         clean_builder_case("bd-fixup-rebase")))
# Log-only: a conflict in a test file that the builder resolved during a rebase is a replay it chose, so the
# guard logs it for the reviewer. Out of scope for the rebase write-back ruling: the builder resolved it with
# `--ours` during the replay, which is not a write after the rebase. It stays logged only.
diff_repo("bd-i1-rebase-ours", _i1_rebase_ours)
LOG_CHECKS_EXTRA.append(("builder-refuse: a rebase conflict in a test file resolved to the upstream side is logged only",
                         logged_builder_case("bd-i1-rebase-ours")))

# A builder never writes test content. A test file that still holds git's conflict markers is a builder's test change,
# so the builder's commit is refused while the file is unresolved. The rows check that refusal. The test-author resolves
# that file. The same merge is denied once the builder rewrites the conflicted file to its own side. Both share one setup.
_bd_m_left = diff_repo("bd-m-test-left", _open_test_conflict_left)
sh("builder-refuse: a builder's merge in progress, with a product edit staged and a conflicted test file left as git "
   "wrote it, is denied at commit by builder-diff", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_left, agent_id="bld1",
   agent_type="builder")
_bd_m_edited = diff_repo("bd-m-test-edited", _open_test_conflict_edited)
sh("builder-refuse: a builder's merge in progress that rewrites a conflicted test file to its own side is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_edited, agent_id="bld1", agent_type="builder")

# The same two merges, run from a subfolder. The guard reads each file from the top of the checkout, whatever folder
# the command runs in: a conflicted test file left as git wrote it is denied, as is one rewritten to the builder's side.
sh("builder-refuse: a builder's merge in progress, with a conflicted test file left as git wrote it, is denied at "
   "commit by builder-diff from a subfolder", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_m_left, "src"),
   agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's merge in progress that rewrites a conflicted test file is denied at commit from a "
   "subfolder", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_m_edited, "src"), agent_id="bld1",
   agent_type="builder")

# A builder's own edit to a test file that a clean merge of main took in is refused, in an open merge and in a merge
# commit. Main's own change, merged clean and left alone, is allowed: the control row below pins that.
_bd_m_main_open = diff_repo("bd-m-main-test-open", lambda w: _main_test_merge_open(w, BASE_FILES[TEST_A] + MAIN_CASE
                                                                                  + BUILDER_CASE))
sh("builder-refuse: a builder's own case in a test file that main changed and git's open merge took clean is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_main_open, agent_id="bld1", agent_type="builder")
_bd_m_main_commit = diff_repo("bd-m-main-test-commit", _main_test_merge_committed)
sh("builder-refuse: a builder's own case in a test file that main changed and a merge commit took clean is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_main_commit, agent_id="bld1", agent_type="builder")
_bd_m_main_clean = diff_repo("bd-m-main-test-clean", lambda w: _main_test_merge_open(w))
sh("builder-refuse: a merge in progress where main changed a test file that merged clean, with no builder edit, is "
   "allowed at commit", COMMIT, "allow", cwd=_bd_m_main_clean, agent_id="bld1", agent_type="builder")
# The same clean change, committed as the builder's merge commit with no builder edit: git's merge of the two parents
# is the commit's tree, so main's test change is allowed at commit and push, and at the stop.
_bd_m_main_merge_clean = diff_repo("bd-m-main-test-merge-clean", _main_test_merge_clean_committed)
sh("builder-refuse: a builder's merge commit that carries main's clean test change, with no builder edit, is allowed "
   "at commit", COMMIT, "allow", cwd=_bd_m_main_merge_clean, agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's merge commit that carries main's clean test change, with no builder edit, is allowed "
   "at push", PUSH, "allow", cwd=_bd_m_main_merge_clean, agent_id="bld1", agent_type="builder")
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's merge commit that carries main's clean test change, with no "
                         "builder edit, is allowed at commit, push and stop, and logs no builder-diff line",
                         clean_builder_case("bd-m-main-test-merge-clean")))

# git's three conflict markers left in a conflicted test file of an open merge are denied by builder-diff, since a test
# file that still holds markers is the builder's change. An unmerged file that is not staged is refused by builder-diff
# too, pinned by the bd-m-test-left row above, so these rows stage the markers first.
_bd_m_markers_chain = diff_repo("bd-m-markers-chain", _f2_conflict_open)
sh("builder-refuse: a builder's open merge that leaves git's markers in a conflicted test file, staged and committed in "
   "one call, is denied by builder-diff", VCS + " add -A && " + COMMIT, "deny", rule=BDIFF,
   cwd=_bd_m_markers_chain, agent_id="bld1", agent_type="builder")
_bd_m_markers_staged = diff_repo("bd-m-markers-staged", _f2_conflict_staged)
sh("builder-refuse: a builder's open merge that stages git's markers in a conflicted test file, then commits, is denied "
   "by builder-diff", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_markers_staged, agent_id="bld1",
   agent_type="builder")
# The same staged markers behind a leading `echo ok;`: builder-diff refuses the test file at commit by itself.
sh("builder-refuse: a builder's open merge, with a test file still holding git's markers, staged and committed after "
   "`echo ok;`, is denied at commit by builder-diff", "echo ok; " + VCS + " add -A && " + COMMIT, "deny", rule=BDIFF,
   cwd=_bd_m_markers_chain, agent_id="bld1", agent_type="builder")

# A builder's resolution of a conflicted test file to main's side, or to a blend of both sides, is refused by
# builder-diff, as its resolution to its own side is (_open_test_conflict_edited).
_bd_m_keep_main = diff_repo("bd-m-keep-main", lambda w: _resolve_test_conflict_open(
    w, BASE_FILES[TEST_A] + "# main's newer case\n"))
sh("builder-refuse: a builder's merge in progress that resolves a conflicted test file to main's side is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_keep_main, agent_id="bld1", agent_type="builder")
_bd_m_blend = diff_repo("bd-m-blend", _strip_test_conflict_markers)
sh("builder-refuse: a builder's merge in progress that strips git's markers from a conflicted test file and keeps both "
   "sides is denied at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_blend, agent_id="bld1", agent_type="builder")

# A builder's edit to sub/tests/test_b.py is refused when it runs from sub/ with `diff.relative` set, as it is under the
# default config. With diff.relative, git prints the path relative to sub/ (tests/test_b.py), so the rows check that the
# refusal holds when git names the file that way. The default-config row is the control. The sibling pin for
# `git diff --check` under diff.relative is CMK_REL (conflict-markers).
SUB_TEST = "sub/tests/test_b.py"
SUB_FILES = {**BASE_FILES, "tests/test_b.py": "def test_top():\n    assert 1\n",
             SUB_TEST: "def test_sub():\n    assert 1\n"}
SUB_EDIT = "def test_sub():\n    assert 2\n"


def _folder_names(where, folder, *revs, flags=()):
    """The names `git diff --name-only` prints from `folder`, with `flags` added. A fixture checks them before a case
    relies on them."""
    done = run_vcs(os.path.join(where, folder), "diff", *flags, "--name-only", *revs)
    if done.returncode != 0:
        sys.exit("fixture setup failed: git diff in %s/ of %r: %s" % (folder, where, done.stderr.strip()))
    return done.stdout.split()


def _sub_open_edit(w, relative):
    """The open merge of a clean merge, with the builder's edit to SUB_TEST. `relative` sets diff.relative."""
    _clean_merge_open(w)
    write(os.path.join(w, SUB_TEST), SUB_EDIT)
    if relative:
        _must(w, "config", "diff.relative", "true")
        if _folder_names(w, "sub", "HEAD") != ["tests/test_b.py"]:
            sys.exit("fixture setup failed: diff.relative did not name %r relative to sub/ in %r" % (SUB_TEST, w))
    elif SUB_TEST not in _folder_names(w, "sub", "HEAD"):
        sys.exit("fixture setup failed: the default config did not name %r from sub/ in %r" % (SUB_TEST, w))


def _sub_commit_edit(w):
    """The open merge of _sub_open_edit, committed as the builder's merge commit, with diff.relative set."""
    _clean_merge_open(w)
    write(os.path.join(w, SUB_TEST), SUB_EDIT)
    _commit_merge(w)
    _must(w, "config", "diff.relative", "true")
    if _folder_names(w, "sub", "HEAD^1", "HEAD") != ["tests/test_b.py"]:
        sys.exit("fixture setup failed: diff.relative did not name the merge commit's %r relative to sub/ in %r"
                 % (SUB_TEST, w))


_bd_sub_open_rel = diff_repo("bd-sub-open-rel", lambda w: _sub_open_edit(w, True), files=SUB_FILES)
sh("builder-refuse: a builder's edit to sub/tests/test_b.py in an open merge, from sub/ with diff.relative set, is "
   "denied at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_sub_open_rel, "sub"), agent_id="bld1",
   agent_type="builder")
_bd_sub_commit_rel = diff_repo("bd-sub-commit-rel", _sub_commit_edit, files=SUB_FILES)
sh("builder-refuse: a builder's merge commit that edits sub/tests/test_b.py, from sub/ with diff.relative set, is "
   "denied at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_sub_commit_rel, "sub"), agent_id="bld1",
   agent_type="builder")
_bd_sub_open_default = diff_repo("bd-sub-open-default", lambda w: _sub_open_edit(w, False), files=SUB_FILES)
sh("builder-refuse: the same open-merge edit to sub/tests/test_b.py under the default config, from sub/, is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_sub_open_default, "sub"), agent_id="bld1",
   agent_type="builder")

# With `diff.relative` set, `git diff` names only the paths under the folder it runs in, so from docs/ a builder's edit
# to the top-level tests/test_a.py is named by no plain diff. Only `--no-relative` on each name-producing diff keeps the
# refusal. Each red row runs from docs/ and reads the edit down one call path: the working tree against HEAD, against
# git's open merge, a committed change at push, and a merge commit at commit. Each fixture checks that premise first.
# Each control builds the same change under the default config, where the refusal holds with or without the flag.
DOCS_FILES = {**BASE_FILES, "docs/notes.md": "notes\n"}


def _docs_edit(w):
    write(os.path.join(w, TEST_A), "def test_a():\n    assert 2\n")


def _docs_relative(w, relative, *revs):
    """With `relative`, set diff.relative and check that the plain diff from docs/ names no path while --no-relative
    names the test file. Without it, check that the default diff from docs/ names the test file."""
    if not relative:
        if TEST_A not in _folder_names(w, "docs", *revs):
            sys.exit("fixture setup failed: the default config did not name %r from docs/ in %r" % (TEST_A, w))
        return
    _must(w, "config", "diff.relative", "true")
    if _folder_names(w, "docs", *revs):
        sys.exit("fixture setup failed: diff.relative still named a path from docs/ in %r" % w)
    if TEST_A not in _folder_names(w, "docs", *revs, flags=("--no-relative",)):
        sys.exit("fixture setup failed: --no-relative did not name %r from docs/ in %r" % (TEST_A, w))


def _docs_plain(w, relative):
    """A builder's uncommitted edit to the top-level test file."""
    _docs_edit(w)
    _docs_relative(w, relative, "HEAD")


def _docs_open(w, relative):
    """A builder's edit to the top-level test file, made while git's clean merge of main is still open."""
    _clean_merge_open(w)
    _docs_edit(w)
    _docs_relative(w, relative, "HEAD")


def _docs_committed(w, relative):
    """A builder's plain commit of the top-level test file, read again at push."""
    _docs_edit(w)
    _must(w, "add", "-A")
    _must(w, *IDENT, "commit", "-q", "-m", "builder edit")
    _docs_relative(w, relative, "HEAD^", "HEAD")


def _docs_merge_committed(w, relative):
    """A builder's merge commit that edits the top-level test file, read again at commit."""
    _clean_merge_open(w)
    _docs_edit(w)
    _commit_merge(w)
    _docs_relative(w, relative, "HEAD^1", "HEAD")


_bd_docs_plain = diff_repo("bd-docs-plain-rel", lambda w: _docs_plain(w, True), files=DOCS_FILES)
sh("builder-refuse: a builder's edit to tests/test_a.py, from docs/ with diff.relative set, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_plain, "docs"), agent_id="bld1", agent_type="builder")
_bd_docs_plain_ctl = diff_repo("bd-docs-plain-ctl", lambda w: _docs_plain(w, False), files=DOCS_FILES)
sh("builder-refuse: the same edit to tests/test_a.py, from docs/ under the default config, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_plain_ctl, "docs"), agent_id="bld1", agent_type="builder")

_bd_docs_open = diff_repo("bd-docs-open-rel", lambda w: _docs_open(w, True), files=DOCS_FILES)
sh("builder-refuse: a builder's edit to tests/test_a.py in an open merge, from docs/ with diff.relative set, is "
   "denied at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_open, "docs"), agent_id="bld1",
   agent_type="builder")
_bd_docs_open_ctl = diff_repo("bd-docs-open-ctl", lambda w: _docs_open(w, False), files=DOCS_FILES)
sh("builder-refuse: the same open-merge edit to tests/test_a.py, from docs/ under the default config, is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_open_ctl, "docs"), agent_id="bld1",
   agent_type="builder")

_bd_docs_committed = diff_repo("bd-docs-committed-rel", lambda w: _docs_committed(w, True), files=DOCS_FILES)
sh("builder-refuse: a builder's committed edit to tests/test_a.py, from docs/ with diff.relative set, is denied at "
   "push", PUSH, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_committed, "docs"), agent_id="bld1",
   agent_type="builder")
_bd_docs_committed_ctl = diff_repo("bd-docs-committed-ctl", lambda w: _docs_committed(w, False), files=DOCS_FILES)
sh("builder-refuse: the same committed edit to tests/test_a.py, from docs/ under the default config, is denied at "
   "push", PUSH, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_committed_ctl, "docs"), agent_id="bld1",
   agent_type="builder")

_bd_docs_merge = diff_repo("bd-docs-merge-rel", lambda w: _docs_merge_committed(w, True), files=DOCS_FILES)
sh("builder-refuse: a builder's merge commit that edits tests/test_a.py, from docs/ with diff.relative set, is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_merge, "docs"), agent_id="bld1",
   agent_type="builder")
_bd_docs_merge_ctl = diff_repo("bd-docs-merge-ctl", lambda w: _docs_merge_committed(w, False), files=DOCS_FILES)
sh("builder-refuse: the same merge commit that edits tests/test_a.py, from docs/ under the default config, is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_docs_merge_ctl, "docs"), agent_id="bld1",
   agent_type="builder")

# An untracked file is listed from the checkout's top, whatever folder the command runs in. The builder's test file
# under src/ is judged as src/test_x.py. The conflicted top-level file of that name holds git's markers, so builder-diff
# refuses it either way: this row does not tell the two readings apart.
_bd_m_top = diff_repo("bd-m-top-test", _top_test_conflict_open)
sh("builder-refuse: a builder's merge in progress, with a conflicted top-level test file left as git wrote it and an "
   "untracked test file of the same name under src/, is denied at commit from a subfolder", COMMIT, "deny", rule=BDIFF,
   cwd=os.path.join(_bd_m_top, "src"), agent_id="bld1", agent_type="builder")

# A merge in progress where the merged branch added twenty test files that merged clean is git's, and allowed.
_bd_m_many = diff_repo("bd-m-many-clean", _c1_many_clean)
sh("builder-refuse: a builder's merge in progress, with twenty test files that merged clean and a product file "
   "resolved, is allowed at commit", COMMIT, "allow", cwd=_bd_m_many, agent_id="bld1", agent_type="builder")

# An empty test file that a builder adds or deletes is a builder's change in a merge as in a plain change. The two
# plain cases are the controls: the same change, outside a merge, is refused.
_bd_empty_plain_add = diff_repo("bd-empty-plain-add", _put(EMPTY_TEST, ""))
sh("builder-refuse: a new empty test file in a builder's plain change is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_empty_plain_add, agent_id="bld1", agent_type="builder")
_bd_empty_plain_del = diff_repo("bd-empty-plain-del", _rm(EMPTY_TEST), files={**BASE_FILES, EMPTY_TEST: ""})
sh("builder-refuse: a deleted empty test file in a builder's plain change is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_empty_plain_del, agent_id="bld1", agent_type="builder")

_bd_m_empty_add = diff_repo("bd-m-empty-add", _empty_add_open)
sh("builder-refuse: a builder's merge in progress that adds an empty test file git's merge lacks is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_empty_add, agent_id="bld1", agent_type="builder")
_bd_m_empty_del = diff_repo("bd-m-empty-del", _empty_delete_open)
sh("builder-refuse: a builder's merge in progress that deletes an empty test file git's merge has is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_empty_del, agent_id="bld1", agent_type="builder")
_bd_m_empty_add_c = diff_repo("bd-m-empty-add-commit", _empty_add_committed)
sh("builder-refuse: a builder's merge commit that adds an empty test file git's merge lacks is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_empty_add_c, agent_id="bld1", agent_type="builder")
_bd_m_empty_del_c = diff_repo("bd-m-empty-del-commit", _empty_delete_committed)
sh("builder-refuse: a builder's merge commit that deletes an empty test file git's merge has is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_empty_del_c, agent_id="bld1", agent_type="builder")

# A conflicted test file whose bytes change only in line endings, LF to CRLF or a lone CR, is the builder's change. A
# line-ending change alters the bytes of the file, so the two rows check that each is refused.
_bd_m_crlf = diff_repo("bd-m-crlf", _conflict_crlf)
sh("builder-refuse: a builder's merge in progress that changes only the line endings of a conflicted test file "
   "(LF to CRLF) is denied at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_crlf, agent_id="bld1",
   agent_type="builder")
_bd_m_cr = diff_repo("bd-m-cr", _conflict_cr)
sh("builder-refuse: a builder's merge in progress that changes only the line endings of a conflicted test file "
   "(a lone CR) is denied at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_cr, agent_id="bld1",
   agent_type="builder")

# A test file that differs only in one invalid UTF-8 byte is the builder's change: both bytes decode alike.
_bd_m_byte = diff_repo("bd-m-invalid-byte", _invalid_byte_open)
sh("builder-refuse: a builder's merge in progress that changes only an invalid UTF-8 byte of a test file is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_byte, agent_id="bld1", agent_type="builder")

# A gitlink under tests/, and a mode-only change to a test file, are the builder's changes in a merge, refused as on
# main. The plain changes are the controls: the same change outside a merge is refused.
_bd_m_gitlink = diff_repo("bd-m-gitlink", _gitlink_open)
sh("builder-refuse: a builder's merge in progress that adds a gitlink under tests/ is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_gitlink, agent_id="bld1", agent_type="builder")
_bd_m_gitlink_c = diff_repo("bd-m-gitlink-commit", _gitlink_committed)
sh("builder-refuse: a builder's merge commit that adds a gitlink under tests/ to a commit the clone lacks is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_gitlink_c, agent_id="bld1", agent_type="builder")
_bd_m_gitlink_h = diff_repo("bd-m-gitlink-held", _gitlink_committed_held)
sh("builder-refuse: a builder's merge commit that adds a gitlink under tests/ to a commit the clone holds is denied "
   "at commit", COMMIT, "deny", rule=BDIFF, cwd=_bd_m_gitlink_h, agent_id="bld1", agent_type="builder")
_bd_gitlink_plain = diff_repo("bd-gitlink-plain", _gitlink_stage)
sh("builder-refuse: a builder's plain change that adds a gitlink under tests/ is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_gitlink_plain, agent_id="bld1", agent_type="builder")

# A mode-only change is no byte change, so the exec bit needs a POSIX checkout. The committed one sets the bit in the
# index too, so it reads the same on every platform.
_MODE_OPEN_CASE = ("builder-refuse: a builder's merge in progress that changes only the mode of a test file (chmod +x) "
                   "is denied at commit")
_MODE_PLAIN_CASE = ("builder-refuse: a builder's plain change that changes only the mode of a test file (chmod +x) "
                    "is denied at commit")
# The conflicted test file of an open merge, unmerged in the index, whose only change is the exec bit: the mode change
# is the builder's change, whatever git's raw entry for an unmerged path holds.
_MODE_CONFLICT_CASE = ("builder-refuse: a builder's merge in progress that only sets the exec bit on a conflicted test "
                       "file, keeping git's bytes, is denied at commit")
if os.name != "nt":
    _bd_m_mode = diff_repo("bd-m-mode", _mode_exec_open)
    sh(_MODE_OPEN_CASE, COMMIT, "deny", rule=BDIFF, cwd=_bd_m_mode, agent_id="bld1", agent_type="builder")
    _bd_mode_plain = diff_repo("bd-mode-plain", _mode_exec(TEST_A))
    sh(_MODE_PLAIN_CASE, COMMIT, "deny", rule=BDIFF, cwd=_bd_mode_plain, agent_id="bld1", agent_type="builder")
    _bd_m_conf_mode = diff_repo("bd-m-conflict-mode", _open_test_conflict_mode)
    sh(_MODE_CONFLICT_CASE, COMMIT, "deny", rule=BDIFF, cwd=_bd_m_conf_mode, agent_id="bld1", agent_type="builder")
else:
    skip_case(_MODE_OPEN_CASE, NO_EXEC_BIT)
    skip_case(_MODE_PLAIN_CASE, NO_EXEC_BIT)
    skip_case(_MODE_CONFLICT_CASE, NO_EXEC_BIT)
_bd_m_mode_c = diff_repo("bd-m-mode-commit", _mode_exec_committed)
sh("builder-refuse: a builder's merge commit that changes only the mode of a test file is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_m_mode_c, agent_id="bld1", agent_type="builder")


def _reaches_merge_check_case(where, rel, committed):
    """A builder's change to `rel` in a merge reaches the merge check: own_changes answers, and git's diff of the
    merge's old side lists `rel` before the merge check judges it. So a deny above comes from the merge check, and an
    allow from an unread change fails here instead."""
    materialize(where)
    guard = _load_guard_module()
    if guard.own_changes(where) is None:
        return False, "own_changes returned None, so git could not answer for %s" % rel
    if committed:
        merged = guard.merge_tree(where, run_vcs(where, "rev-parse", "HEAD^1").stdout.strip(),
                                  run_vcs(where, "rev-parse", "HEAD^2").stdout.strip())
        old = None if merged is None else merged[0]
        paths = guard.changed_paths(where, old, "HEAD") if old else None
    else:
        merged = guard.merge_tree(where, "HEAD", run_vcs(where, "rev-parse", "MERGE_HEAD").stdout.strip())
        old = None if merged is None else merged[0]
        paths = guard.changed_paths(where, old) if old else None
    if paths is None:
        return False, "git could not list the change against the merge's old side"
    if rel not in paths:
        return False, "git's diff against the merge's old side does not list %s" % rel
    return True, "git lists %s against the merge's old side, and own_changes answers" % rel


# Each red above must reach the merge check and fail there, not on an unread change.
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's gitlink in a merge in progress reaches the merge check",
                         lambda: _reaches_merge_check_case(_bd_m_gitlink, GITLINK, False)))
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's gitlink in a merge commit reaches the merge check",
                         lambda: _reaches_merge_check_case(_bd_m_gitlink_c, GITLINK, True)))
LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's mode-only change in a merge commit reaches the merge check",
                         lambda: _reaches_merge_check_case(_bd_m_mode_c, TEST_A, True)))
if os.name != "nt":
    LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's mode-only change in a merge in progress "
                             "reaches the merge check", lambda: _reaches_merge_check_case(_bd_m_mode, TEST_A, False)))
    LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's exec-bit change on a conflicted test file in a merge in "
                             "progress reaches the merge check",
                             lambda: _reaches_merge_check_case(_bd_m_conf_mode, TEST_A, False)))


# The git reader a guard call goes through: `_git`, which guard_core imports from git_reads. The guard calls it as
# guard_core._git, so a patch on the core module counts each call the guard makes.
COUNTED_READERS = ("_git",)


def _counted_own_changes(where):
    """own_changes(where) with every git call the guard makes counted: the changes, and the argument tuples of the
    calls in order. The count is taken at the readers the guard calls, so it is the guard's own. A reader that another
    counted reader calls is not counted again: a chain of readers is one call."""
    guard = _load_guard_module()
    core = sys.modules["guard_core"]
    calls = []
    depth = [0]
    real = {name: getattr(core, name) for name in COUNTED_READERS if hasattr(core, name)}

    def counted(real_call):
        def call(root, *args):
            if not depth[0]:
                calls.append(args)
            depth[0] += 1
            try:
                return real_call(root, *args)
            finally:
                depth[0] -= 1
        return call

    for name, real_call in real.items():
        setattr(core, name, counted(real_call))
    try:
        changes = guard.own_changes(where)
    finally:
        for name, real_call in real.items():
            setattr(core, name, real_call)
    return changes, calls


def _calls_naming(calls, rels):
    """{rel: how many git calls name rel} for each path in `rels`."""
    return {rel: sum(1 for args in calls if any(rel in part for part in args)) for rel in rels}


def plain_commit_reads_case():
    """A builder's plain commit: own_changes makes no git call that names one of its changed paths."""
    where = diff_repo("bd-cost-plain", _cost_files, commit=True)
    materialize(where)
    changes, calls = _counted_own_changes(where)
    if changes is None:
        return False, "own_changes returned None for the plain commit"
    found = {path for _old, _new, paths, _kind, _conflicts in changes for path in paths}
    if found != set(COST_PATHS):
        return False, "own_changes found paths %r, want %r" % (sorted(found), COST_PATHS)
    named = {rel: n for rel, n in _calls_naming(calls, COST_PATHS).items() if n}
    if named:
        return False, "the plain commit's git calls name paths %r, want none" % (named,)
    return True, "the plain commit's three paths are read through no git call"


LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's plain commit makes no git call that names a changed path",
                         plain_commit_reads_case))

# Undo route: a new test file is refused, and the reason says to delete it and names no test path.
_bd_u2 = diff_repo("bd-u2-new-file", _u2_new_test)
sh("builder-refuse: a new test file is denied at commit, and the reason says to delete it and names no path",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_u2, agent_id="bld1", agent_type="builder",
   lacks=("tests/", "test_new"), carries=("delete",))
sh("builder-refuse: a new test file is denied at push, and the reason says to delete it and names no path",
   PUSH, "deny", rule=BDIFF, cwd=_bd_u2, agent_id="bld1", agent_type="builder",
   lacks=("tests/", "test_new"), carries=("delete",))
# Untracked files are listed from the checkout's top, so the same new test file, under tests/, is refused from a
# subfolder too.
sh("builder-refuse: a builder's plain change with an untracked test file in another folder is denied at commit from "
   "a subfolder", COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_u2, "src"), agent_id="bld1", agent_type="builder")


def stop_pair_case():
    """Case 6. A builder's first stop with a test change is blocked. Its second stop, with
    stop_hook_active, is allowed silently and logs role-diff-unresolved."""
    repo = os.path.join(DIFFROOT, "b-rewritten")
    materialize(repo)
    folder = os.path.join(ROOT, "stoppair")
    os.makedirs(folder, exist_ok=True)
    log = os.path.join(folder, "guard.log")
    if os.path.exists(log):
        os.remove(log)
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = folder
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())
    body = {"hook_event_name": "SubagentStop", "cwd": repo, "agent_id": "bld1", "agent_type": "builder"}
    problems = []
    first = subprocess.run([sys.executable, GUARD], input=json.dumps(body), capture_output=True,
                           text=True, env=env, timeout=120)
    if read_decision(first.stdout)[0] != "deny":
        problems.append("first stop: expected a block, got %r" % first.stdout.strip()[:80])
    second = subprocess.run([sys.executable, GUARD], input=json.dumps(dict(body, stop_hook_active=True)),
                            capture_output=True, text=True, env=env, timeout=120)
    if second.stdout.strip():
        problems.append("second stop: expected a silent allow, got %r" % second.stdout.strip()[:80])
    text = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
    if "role-diff-unresolved" not in text:
        problems.append("no role-diff-unresolved line after the second stop")
    return (not problems), ("; ".join(problems) or
                            "first stop blocked; second stop allowed, logs role-diff-unresolved")


LOG_CHECKS_EXTRA.append(("builder-refuse: a builder's first stop with a test change is blocked, and its "
                         "second stop is allowed and logs role-diff-unresolved", stop_pair_case))


# A test-config file is read from the run folder, so a commit run from src/ reads src/src/pytest.ini,
# finds no text, and allows a testpaths line that disables tests. The rows from the top are the control:
# the same file read from the top is refused.
_bd_src_ini = diff_repo("bd-src-ini-untracked", _put("src/pytest.ini", "[pytest]\ntestpaths = nowhere\n"))
sh("builder-refuse: a builder's commit from src/ with an untracked src/pytest.ini that sets testpaths is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_src_ini, "src"), agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's push from src/ with an untracked src/pytest.ini that sets testpaths is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=os.path.join(_bd_src_ini, "src"), agent_id="bld1", agent_type="builder")
sh("builder-refuse: the same untracked src/pytest.ini, committed from the top, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_src_ini, agent_id="bld1", agent_type="builder")

# The same join for a tracked src/pytest.ini: the base holds it, and the builder adds a testpaths line from src/.
_bd_src_ini_t = diff_repo("bd-src-ini-tracked", _put("src/pytest.ini", "[pytest]\naddopts = -q\ntestpaths = nowhere\n"),
                          files={**BASE_FILES, "src/pytest.ini": "[pytest]\naddopts = -q\n"})
sh("builder-refuse: a builder's commit from src/ that adds testpaths to a tracked src/pytest.ini is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=os.path.join(_bd_src_ini_t, "src"), agent_id="bld1", agent_type="builder")
sh("builder-refuse: a builder's push from src/ that adds testpaths to a tracked src/pytest.ini is denied at push",
   PUSH, "deny", rule=BDIFF, cwd=os.path.join(_bd_src_ini_t, "src"), agent_id="bld1", agent_type="builder")
sh("builder-refuse: the same tracked src/pytest.ini edit, committed from the top, is denied at commit",
   COMMIT, "deny", rule=BDIFF, cwd=_bd_src_ini_t, agent_id="bld1", agent_type="builder")


# =========================================================================== failing open
