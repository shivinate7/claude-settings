# section 21306
# =========================================================================== a fix branch takes clean merges of main
#
# The fix-branch refusal (guard_push_delete.py review_log_hit, step 2) refuses a push to the head branch of a PR whose
# posted review log holds a `Fix check:` line. A clean merge of main keeps the record (decision pr-review-record, owner
# ruling 2026-11-10 14:07 CST). So a push whose new commits, walked on first parents from the pushed source down to the
# record's Head, are only clean merges of main is allowed: each commit has two parents, its second parent is on
# origin/main, and its tree is git's clean merge of its parents. Any other push keeps the refusal, with the same reason.
# A push of another branch is unaffected. Each case runs in a real checkout, and the builder checks each commit's shape.
FAMILY = "push-needs-review-record"  # glossary-ok: the family name hooks/test_guard.py keys on, a literal

PFR_MERGE_DIR = os.path.join(ROOT, "pfrmerge")       # the source and its checkouts, one folder
PFR_MERGE_SRC = os.path.join(PFR_MERGE_DIR, "src")   # the source: each checkout clones it, so its main is origin/main
PFR_MERGE_PR = 1480                                  # the PR whose head branch is PFR_MERGE_BRANCH
PFR_MERGE_BRANCH = "notes-merge-fix"                 # that PR's head branch, the push's destination
PFR_MERGE_PUSH = VCS + " push origin HEAD:" + PFR_MERGE_BRANCH
PFR_MERGE_ABSENT = "0123456789abcdef0123456789abcdef01234567"   # a commit no fixture holds; the builder checks it
PFR_MERGE_NAMES = ("head", "c1", "c2", "plain", "pc", "mixed", "evil", "conflict", "side", "detour")
PFR_MERGE_CLONE = {name: os.path.join(PFR_MERGE_DIR, "cl-" + name) for name in PFR_MERGE_NAMES}
PFR_MERGE_SHALLOW = os.path.join(PFR_MERGE_DIR, "cl-shallow")   # a depth-1 clone: the parents of its tip are absent
PFR_MERGE_GOOD = pfr_path("merge-good")                          # a record whose Head is the real recorded head H
PFR_MERGE_MISSING = pfr_path("merge-absent-head")                # a record whose Head names PFR_MERGE_ABSENT


def _pfm_commit(where, path, text, message):
    """A commit on the checkout's branch that writes `text` to `path`; -> its sha."""
    write(os.path.join(where, path), text)
    _pfr_step("add", "-A", where=where)
    _pfr_step(*IDENT, "commit", "-q", "-m", message, where=where)
    return _pfr_step("rev-parse", "HEAD", where=where)


def _pfm_merge(where, ref, message):
    """A merge of `ref` into the checkout's branch, with a merge commit even when git could fast-forward; -> the new HEAD."""
    _pfr_step(*IDENT, "merge", "-q", "--no-ff", "-m", message, ref, where=where)
    return _pfr_step("rev-parse", "HEAD", where=where)


def _pfm_parents(where, sha):
    return _pfr_step("rev-list", "--parents", "-n", "1", sha, where=where).split()[1:]


def _pfm_first_parents(where, sha):
    return _pfr_step("rev-list", "--first-parent", sha, where=where).split()


def _pfm_clean(where, sha):
    """True when `sha` merges exactly two parents and its tree is git's clean merge of them (exit 0, the same tree id)."""
    parents = _pfm_parents(where, sha)
    if len(parents) != 2:
        return False
    done = run_vcs(where, "merge-tree", "--write-tree", "--no-messages", "-z", parents[0], parents[1])
    tree = _pfr_step("rev-parse", sha + "^{tree}", where=where)
    return done.returncode == 0 and done.stdout.split("\0")[0] == tree


def _pfm_is_ancestor(where, sha, tip):
    return run_vcs(where, "merge-base", "--is-ancestor", sha, tip).returncode == 0


def _pfm_clone(where, source, sha, main_at):
    """A checkout of `source` on a plain branch at `sha`. Local main is set back to `main_at`, so the default base a
    checkout reads is origin/main (the source's main), never this stale local branch."""
    done = run_vcs(os.path.dirname(where), "clone", "-q", source, where)
    if done.returncode != 0:
        sys.exit("fixture setup failed: git clone of %r into %r: %s" % (source, where, done.stderr.strip()))
    _pfr_step("checkout", "-q", "-b", "merge-check", sha, where=where)
    _pfr_step("branch", "-f", "main", main_at, where=where)


def _build_pfm():
    """The clean-merge fixtures, built with git itself. The source holds the record's Head H on `feat`, where its fix
    diff starts at F. Main moves on from the root M0 to M1, M2, then M3, which conflicts with H. Each case's checkout
    sits on the pushed source the case names. The builder checks each commit's shape, so a case cannot pass for another."""
    make_repo(PFR_MERGE_SRC, {"notes.txt": "a\n", "other.txt": "o\n"})
    src = PFR_MERGE_SRC
    m0 = _pfr_step("rev-parse", "HEAD", where=src)
    _pfr_step("checkout", "-q", "-b", "feat", where=src)
    f = _pfm_commit(src, "feat.txt", "f1\n", "feat 1")
    h = _pfm_commit(src, "feat.txt", "f2\n", "feat 2")
    _pfr_step("checkout", "-q", "main", where=src)
    m1 = _pfm_commit(src, "other.txt", "o1\n", "main 1")
    m2 = _pfm_commit(src, "more.txt", "m2\n", "main 2")
    m3 = _pfm_commit(src, "feat.txt", "m3\n", "main 3")
    _pfr_step("checkout", "-q", "-b", "side", m0, where=src)
    s = _pfm_commit(src, "side.txt", "s\n", "side")
    _pfr_step("checkout", "-q", "-b", "detour", m0, where=src)
    d = _pfm_merge(src, m1, "detour: main 1 onto the root")
    _pfr_step("checkout", "-q", "-b", "cm1", h, where=src)
    c1 = _pfm_merge(src, m1, "clean merge of main 1")
    _pfr_step("checkout", "-q", "-b", "cm2", where=src)
    c2 = _pfm_merge(src, m2, "clean merge of main 2")
    _pfr_step("checkout", "-q", "-b", "plain", h, where=src)
    p = _pfm_commit(src, "extra.txt", "x\n", "plain commit")
    _pfr_step("checkout", "-q", "-b", "pc", p, where=src)
    pc = _pfm_merge(src, m1, "clean merge after a plain commit")
    _pfr_step("checkout", "-q", "-b", "mixed", c1, where=src)
    p2 = _pfm_commit(src, "extra2.txt", "y\n", "plain commit after a clean merge")
    _pfr_step("checkout", "-q", "-b", "evil", h, where=src)
    _pfr_step(*IDENT, "merge", "-q", "--no-commit", "--no-ff", m1, where=src)
    e = _pfm_commit(src, "evil.txt", "an edit git's merge does not make\n", "evil merge")
    _pfr_step("checkout", "-q", "-b", "conflict", h, where=src)
    if run_vcs(src, *IDENT, "merge", "-q", "--no-ff", "-m", "conflicted merge", m3).returncode != 1:
        sys.exit("fixture setup failed: merging main 3 into the record's Head did not conflict")
    _require_conflict(src, "feat.txt")
    x = _pfm_commit(src, "feat.txt", "resolved by hand\n", "conflicted merge, resolved by hand")
    _pfr_step("checkout", "-q", "-b", "sidemerge", h, where=src)
    xs = _pfm_merge(src, s, "merge of a side branch off the root")
    _pfr_step("checkout", "-q", "main", where=src)

    # Scope before subject: each shape the cases rely on, read back from git.
    shapes = [
        (_pfm_clean(src, c1) and _pfm_parents(src, c1) == [h, m1], "c1 is not a clean merge of H and main 1"),
        (_pfm_clean(src, c2) and _pfm_parents(src, c2) == [c1, m2], "c2 is not a clean merge of c1 and main 2"),
        (_pfm_clean(src, pc) and _pfm_parents(src, pc) == [p, m1], "pc is not a clean merge of the plain commit and main 1"),
        (_pfm_clean(src, xs) and _pfm_parents(src, xs) == [h, s], "xs is not a clean merge of H and the side branch"),
        (len(_pfm_parents(src, p)) == 1 and len(_pfm_parents(src, p2)) == 1, "a plain commit has other than one parent"),
        (len(_pfm_parents(src, e)) == 2 and not _pfm_clean(src, e), "the evil merge is git's clean merge, so it has no edit"),
        (run_vcs(src, "merge-tree", "--write-tree", "--no-messages", "-z", h, m3).returncode == 1,
         "H and main 3 merge with no conflict, so the conflicted merge is not one"),
        (len(_pfm_parents(src, x)) == 2 and not _pfm_clean(src, x), "the conflicted merge reads as a clean merge"),
        (not _pfm_is_ancestor(src, s, m3), "the side branch is on main, so it is no side branch"),
        (_pfm_is_ancestor(src, m1, m3) and _pfm_is_ancestor(src, m2, m3), "main 1 or main 2 is not on main 3"),
        (h in _pfm_first_parents(src, c1) and h in _pfm_first_parents(src, c2), "the first-parent walk from c1 or c2 misses H"),
        (h not in _pfm_first_parents(src, d), "the detour's first-parent walk reaches H"),
    ]
    for ok, why in shapes:
        if not ok:
            sys.exit("fixture setup failed: " + why)
    if run_vcs(src, "cat-file", "-e", PFR_MERGE_ABSENT).returncode == 0:
        sys.exit("fixture setup failed: the source holds the absent commit %s" % PFR_MERGE_ABSENT)

    tips = {"head": h, "c1": c1, "c2": c2, "plain": p, "pc": pc, "mixed": p2, "evil": e, "conflict": x,
            "side": xs, "detour": d}
    for name in PFR_MERGE_NAMES:
        _pfm_clone(PFR_MERGE_CLONE[name], src, tips[name], m0)

    # A depth-1 clone fetches each branch tip, so cm1 goes first: its tip c1 would be present. c1 stays in the source,
    # as c2's first parent, and m2 is no branch tip. So the tip c2 is present and its parents c1 and m2 are not.
    _pfr_step("branch", "-D", "cm1", where=src)
    url = "file://" + slash(src) if slash(src).startswith("/") else "file:///" + slash(src)
    done = run_vcs(PFR_MERGE_DIR, "clone", "-q", "--depth", "1", "--no-single-branch", url, PFR_MERGE_SHALLOW)
    if done.returncode != 0:
        sys.exit("fixture setup failed: the shallow clone: %s" % done.stderr.strip())
    _pfr_step("checkout", "-q", "-b", "merge-check", c2, where=PFR_MERGE_SHALLOW)
    for parent in (c1, m2):
        if run_vcs(PFR_MERGE_SHALLOW, "cat-file", "-e", parent).returncode == 0:
            sys.exit("fixture setup failed: the shallow checkout holds the parent %s it must lack" % parent)

    # The record: a fix verifier PASS whose Fix check line is F, the fix diff's start, and whose Head is H (or the absent
    # commit). Its PR's head branch is PFR_MERGE_BRANCH, opened by a create_pull_request call.
    fix = (f, "reviewer", PFR_MODEL, "PASS")
    for path, head in ((PFR_MERGE_GOOD, h), (PFR_MERGE_MISSING, PFR_MERGE_ABSENT)):
        lines = (pfr_pr_open("toolu_pr1", PFR_MERGE_PR, PFR_MERGE_BRANCH)
                 + pfr_post("toolu_c1", pfr_record(fix=fix, n=PFR_MERGE_PR, head=head), n=PFR_MERGE_PR))
        write(path, "".join(line + "\n" for line in lines))


lazy_fixture([PFR_MERGE_SRC, PFR_MERGE_SHALLOW, PFR_MERGE_GOOD, PFR_MERGE_MISSING] + list(PFR_MERGE_CLONE.values()),
             _build_pfm)


# The allow cases that must go red now: the fix-branch refusal denies a push of clean merges of main. The case with no
# new commit is the empty walk, which is vacuously clean (merge.py clean_merges_after returns True at once).
pfr_allow("clean-merge: the record's Head itself is pushed, no new commit, then the push to its PR head",
          PFR_MERGE_PUSH, PFR_MERGE_GOOD, cwd=PFR_MERGE_CLONE["head"])
pfr_allow("clean-merge: one clean merge of main onto the record's Head, then the push to its PR head",
          PFR_MERGE_PUSH, PFR_MERGE_GOOD, cwd=PFR_MERGE_CLONE["c1"])
pfr_allow("clean-merge: two clean merges of main in a row onto the record's Head, then the push to its PR head",
          PFR_MERGE_PUSH, PFR_MERGE_GOOD, cwd=PFR_MERGE_CLONE["c2"])

# The controls that must stay green: a push of another branch is unaffected, from the same kind of checkout.
pfr_allow("clean-merge: a plain commit pushed to another branch, the control for the checkout",
          PFR_NEXT_PUSH, PFR_MERGE_GOOD, cwd=PFR_MERGE_CLONE["plain"])
pfr_allow("clean-merge: a clean merge of main pushed to another branch, then the push",
          PFR_NEXT_PUSH, PFR_MERGE_GOOD, cwd=PFR_MERGE_CLONE["c1"])

# The refusals that must stay refused, with the same reason. Each names the walk step that refuses it.
pfr_fix_refuse("clean-merge: a plain commit on the record's Head, then the push to its PR head",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["plain"])
pfr_fix_refuse("clean-merge: a clean merge of main, then a plain commit, then the push to its PR head",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["mixed"])
pfr_fix_refuse("clean-merge: a plain commit, then a clean merge of main on top of it, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["pc"])
pfr_fix_refuse("clean-merge: an evil merge of main with an edit beyond git's merge, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["evil"])
pfr_fix_refuse("clean-merge: a conflicted merge of main resolved by hand, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["conflict"])
pfr_fix_refuse("clean-merge: a clean merge whose second parent is a side branch off the root, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["side"])
pfr_fix_refuse("clean-merge: a clean merge of main onto a branch off the root, which never reaches the record's Head",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["detour"])
pfr_fix_refuse("clean-merge: the record's Head is absent from the checkout, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_MISSING, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["c1"])
pfr_fix_refuse("clean-merge: git cannot answer (a blind git on PATH), a read that cannot run, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_CLONE["c1"], env_path=GITBLIND)
pfr_fix_refuse("clean-merge: a parent the checkout lacks (a depth-1 clone), a read that cannot run, then the push",
               PFR_MERGE_PUSH, PFR_MERGE_GOOD, lacks=PFR_MERGE_BRANCH, cwd=PFR_MERGE_SHALLOW)
