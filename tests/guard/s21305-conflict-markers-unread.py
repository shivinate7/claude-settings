# section 21305
# Unread git reads, judged in-process. A git read that cannot run answers None. Here one read at a time answers
# None, and the verdict of `conflict_markers_hit` is read straight off the module. The subprocess rows (every read
# unread at once) are beside the conflict-markers rows in s17500-conflict-markers.py.
#
# These register through LOG_CHECKS_EXTRA, which section 21304 defines; section 17500 runs before that list exists.
FAMILY = "conflict-markers"
# guard_core imports `_git` from git_reads, and guard_merge imports it from guard_core, so each name binds its own
# copy. A patch of one name reaches only the callers bound to it, so each case patches all three.
CMK_READ_MODULES = ("git_reads", "guard_core", "guard_merge")
CMK_UNREAD = "unread"   # the kind `conflict_markers_hit` answers for a read that could not run


def cmk_judge(command, cwd, unread=None):
    """(verdict, calls): `conflict_markers_hit` on COMMAND in CWD, judged by a fresh load of the guard. With UNREAD,
    each git call whose args it matches is answered None on every module that binds `_git`. `calls` holds the args
    of each call so answered."""
    guard = _load_guard_module()
    if unread is None:
        return guard.conflict_markers_hit(command, cwd), []
    real = sys.modules["git_reads"]._git
    calls = []

    def answering(where, *args):
        if unread(args):
            calls.append(args)
            return None
        return real(where, *args)

    with mock.patch.object(sys.modules["git_reads"], "_git", answering), \
            mock.patch.object(sys.modules["guard_core"], "_git", answering), \
            mock.patch.object(sys.modules["guard_merge"], "_git", answering):
        verdict = guard.conflict_markers_hit(command, cwd)
    return verdict, calls


def cmk_unread_kind_case(what, command, cwd, unread, plain=("", "")):
    """COMMAND in CWD is PLAIN with git unpatched. With the git calls UNREAD matches answered None, the verdict is
    the unread kind: a read that cannot run is unknown, so the caller asks. The patch must reach a call first."""
    def check():
        materialize(cwd)
        got_plain, _none = cmk_judge(command, cwd)
        if got_plain != plain:
            return False, "%s: %r with git unpatched, want %r: the fixture changed" % (what, got_plain, plain)
        got, calls = cmk_judge(command, cwd, unread)
        if not calls:
            return False, "%s: no git call matched the patch, so no read was unread" % what
        if got[0] != CMK_UNREAD:
            return False, ("%s: %r with %d git calls answered None, want kind %r: an unread read was read as clear"
                           % (what, got, len(calls), CMK_UNREAD))
        return True, "%s: %r with %d git calls answered None" % (what, got, len(calls))
    return check


def cmk_found_kept_case(what, command, cwd, unread, want):
    """COMMAND in CWD finds a triplet and is WANT with git unpatched. With the git calls UNREAD matches answered None,
    it is still WANT: a read that cannot run does not turn a triplet already found into unread."""
    def check():
        materialize(cwd)
        got_plain, _none = cmk_judge(command, cwd)
        if got_plain != want:
            return False, "%s: %r with git unpatched, want %r: the fixture changed" % (what, got_plain, want)
        got, calls = cmk_judge(command, cwd, unread)
        if not calls:
            return False, "%s: no git call matched the patch, so the other read was never unread" % what
        if got != want:
            return False, ("%s: %r with %d git calls answered None, want %r: an unread read took a found triplet's deny"
                           % (what, got, len(calls), want))
        return True, "%s: %r with %d git calls answered None" % (what, got, len(calls))
    return check


UNREAD_CASES = (
    ("conflict-markers: the toplevel and HEAD read of a commit answers None, the commit is unread, not clear",
     cmk_unread_kind_case("the toplevel and HEAD read of a commit", VCS + " commit -m x", CMK_CLEAN,
                          lambda args: "--show-toplevel" in args)),
    ("conflict-markers: the diff --check read of a commit answers None, the commit is unread, not clear",
     cmk_unread_kind_case("the diff --check read of a commit", VCS + " commit -m x", CMK_CLEAN,
                          lambda args: "--check" in args)),
    ("conflict-markers: the blob read of a staged triplet answers None, the commit is unread, not clear",
     cmk_unread_kind_case("the blob read of a staged triplet", VCS + " commit -m x", CMK_STAGED,
                          lambda args: "cat-file" in args, plain=("commit", "src/app.py"))),
    ("conflict-markers: the diff --check read of a push answers None, the push is unread, not clear",
     cmk_unread_kind_case("the diff --check read of a push", VCS + " push", CMK_CL,
                          lambda args: "--check" in args)),
    ("conflict-markers: a staged triplet found by the diff --check still denies when the untracked read is unread",
     cmk_found_kept_case("a staged triplet, with a whole-tree add whose untracked read is unread",
                         VCS + " add -A && " + VCS + " commit -m x", CMK_STAGED,
                         lambda args: "ls-files" in args, ("commit", "src/app.py"))),
)

for _label, _check in UNREAD_CASES:
    LOG_CHECKS_EXTRA.append((_label, _check))
    FIXTURELESS_CHECKS.add(_check)   # each builds only the fixture it names, through materialize
