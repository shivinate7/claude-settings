# section 17500
FAMILY = "conflict-markers"
FAMILIES["conflict-markers"] = "a git commit or --continue judged on the index and the files its adds or paths name, and a git push judged on the net change it sends: all three markers in one file's added lines are refused; a blind step before a commit, with a push after it, is refused only when the commit covers a triplet already in the tree; a chain that makes a conflict is refused, and a clean, whitespace-only, unstaged or half-marked file is allowed"
# Marker lines are assembled, so this file never holds one at the start of a line.
CM_START = "<" * 7 + " HEAD\n"
CM_MID = "=" * 7 + "\n"
CM_END = ">" * 7 + " topic\n"
CM_TRIPLET = CM_START + "ours line\n" + CM_MID + "theirs line\n" + CM_END
MD_FENCE = "`" * 3
CMK_RULE = "conflict-markers"
CMKROOT = os.path.join(ROOT, "cmk")
CMK_MERGE = os.path.join(CMKROOT, "merge")      # a real conflicting merge, left unresolved
CMK_STAGED = os.path.join(CMKROOT, "staged")    # the triplet staged in a source file
CMK_AM = os.path.join(CMKROOT, "am")            # the triplet in a tracked file, unstaged; a clean change staged
CMK_CLEAN = os.path.join(CMKROOT, "clean")      # a clean change staged
CMK_WS = os.path.join(CMKROOT, "ws")            # a staged change that adds trailing whitespace only
CMK_MDOK = os.path.join(CMKROOT, "mdok")        # one marker line in a fence, and a setext underline
CMK_MDFENCE = os.path.join(CMKROOT, "mdfence")  # a full triplet inside a fence
CMK_NOHEAD = os.path.join(CMKROOT, "nohead")    # no commit yet, the triplet staged
CMK_LONE = os.path.join(CMKROOT, "lone")        # a lone apostrophe in text, then a staged triplet
CMK_TPL = os.path.join(CMKROOT, "tpl")          # a staged triplet inside a multi-line template literal
CMK_OPEN = os.path.join(CMKROOT, "open")        # a string holding comment openers, then a staged triplet


def _cmk_run(where, *args):
    done = run_vcs(where, *IDENT, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in the conflict-markers fixtures: %s %s in %r: %s"
                 % (VCS, " ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def _cmk_topic(where, files):
    """A checkout whose base commit holds `files`, moved onto branch `topic`, so the commit under test is
    no commit on main."""
    make_repo(where, files)
    _cmk_run(where, "checkout", "-q", "-b", "topic")


def _cmk_stage(where, rel, text):
    write(os.path.join(where, rel), text)
    _cmk_run(where, "add", rel)


def _build_conflict_markers():
    run, stage = _cmk_run, _cmk_stage
    # `theirs` and `topic` both change src/app.py, so merging `theirs` into `topic` leaves a real conflict.
    _cmk_topic(CMK_MERGE, {"src/app.py": "x = 1\n"})
    run(CMK_MERGE, "checkout", "-q", "-b", "theirs", "main")
    write(os.path.join(CMK_MERGE, "src", "app.py"), "x = 2\n")
    run(CMK_MERGE, "commit", "-q", "-am", "theirs change")
    run(CMK_MERGE, "checkout", "-q", "topic")
    write(os.path.join(CMK_MERGE, "src", "app.py"), "x = 3\n")
    run(CMK_MERGE, "commit", "-q", "-am", "topic change")
    run_vcs(CMK_MERGE, *IDENT, "merge", "-q", "--no-edit", "theirs")   # conflicts: MERGE_HEAD set, file unmerged
    _require_conflict(CMK_MERGE, "src/app.py")

    _cmk_topic(CMK_STAGED, {"src/app.py": "x = 1\n"})
    stage(CMK_STAGED, "src/app.py", "x = 1\n" + CM_TRIPLET)

    _cmk_topic(CMK_AM, {"src/app.py": "x = 1\n", "src/other.py": "y = 1\n"})
    write(os.path.join(CMK_AM, "src", "app.py"), "x = 1\n" + CM_TRIPLET)   # tracked, modified, unstaged
    stage(CMK_AM, "src/other.py", "y = 2\n")                                # a clean change, staged

    _cmk_topic(CMK_CLEAN, {"src/app.py": "x = 1\n"})
    stage(CMK_CLEAN, "src/app.py", "x = 2\n")

    _cmk_topic(CMK_WS, {"src/app.py": "x = 1\n"})
    stage(CMK_WS, "src/app.py", "x = 2   \n")                               # trailing whitespace only

    _cmk_topic(CMK_MDOK, {"docs/notes.md": "# Notes\n"})
    stage(CMK_MDOK, "docs/notes.md", "# Notes\n\nSetext heading\n" + CM_MID + "\n" + MD_FENCE + "text\n"
          + CM_START + MD_FENCE + "\n")

    _cmk_topic(CMK_MDFENCE, {"docs/notes.md": "# Notes\n"})
    stage(CMK_MDFENCE, "docs/notes.md", "# Notes\n\n" + MD_FENCE + "text\n" + CM_TRIPLET + MD_FENCE + "\n")

    os.makedirs(CMK_NOHEAD, exist_ok=True)
    run(CMK_NOHEAD, "init", "-q", "-b", "topic", ".")
    stage(CMK_NOHEAD, "src/app.py", "x = 1\n" + CM_TRIPLET)

    _cmk_topic(CMK_LONE, {"src/view.jsx": "export const a = 1;\n"})
    stage(CMK_LONE, "src/view.jsx", "export const a = 1;\n<p>Don't</p>\n" + CM_TRIPLET)
    _cmk_topic(CMK_TPL, {"src/tpl.js": "const a = 1;\n"})
    stage(CMK_TPL, "src/tpl.js", "const a = 1;\nconst doc = `\n" + CM_TRIPLET + "`;\n")
    _cmk_topic(CMK_OPEN, {"src/opener.py": "x = 1\n"})
    stage(CMK_OPEN, "src/opener.py", 'x = 1\nNOTE = "/* // #"\n' + CM_TRIPLET)


lazy_fixture([CMK_MERGE, CMK_STAGED, CMK_AM, CMK_CLEAN, CMK_WS, CMK_MDOK, CMK_MDFENCE, CMK_NOHEAD,
              CMK_LONE, CMK_TPL, CMK_OPEN], _build_conflict_markers)


def cmk_refuse(name, command, cwd):
    sh("conflict-markers: %s is refused" % name, command, "deny", CMK_RULE, cwd=cwd)


def cmk_allow(name, command, cwd):
    sh("conflict-markers: %s is allowed" % name, command, "allow", cwd=cwd)


# 1. The index: a real conflict left in the index, or markers staged. A plain commit holds the index.
cmk_refuse("a real merge conflict left in a file, then add -A and commit",
         VCS + " add -A && " + VCS + " commit -m x", CMK_MERGE)
cmk_refuse("a triplet staged in a source file, then commit", VCS + " commit -m x", CMK_STAGED)
cmk_refuse("a triplet staged, behind a false command in the chain", "false && " + VCS + " commit -m x", CMK_STAGED)
# A plain VAR=value runs nothing, so `_chain_safe` keeps the chain readable and the commit is judged. Before
# that change, the assignment made the chain unreadable and the commit was allowed.
cmk_refuse("[cdvar-unread] a triplet staged, behind a plain assignment in the chain", "CDVAR=1 && " + VCS + " commit -m x",
           CMK_STAGED)
# A variable folder is read where the shell runs the commit, as its literal twin is (failed_cd_stays).
cmk_refuse("a variable folder holding a triplet staged in a source file, cd \"$R\" then commit",
           "R=" + slash(CMK_STAGED) + "; cd \"$R\" && " + VCS + " commit -m x", NOGIT)
cmk_refuse("the literal twin, cd to a folder holding a staged triplet then commit, from no repository",
           "cd " + slash(CMK_STAGED) + " && " + VCS + " commit -m x", NOGIT)

# 2. The working tree: an add in the chain, or a commit that names its file, holds that file's content.
cmk_refuse("commit -am with the triplet in a tracked, modified file", VCS + " commit -am x", CMK_AM)
cmk_refuse("add . and commit with the triplet in a tracked, modified file",
         VCS + " add . && " + VCS + " commit -m x", CMK_AM)
cmk_refuse("add of the file and commit, the triplet in that file",
         VCS + " add src/app.py && " + VCS + " commit -m x", CMK_AM)
cmk_refuse("a commit by path that names the file with the triplet", VCS + " commit -m x src/app.py", CMK_AM)

# 3. Scope: the commit holds what it names, and the markers in an unstaged file it does not name are no hit.
cmk_allow("a commit with the triplet unstaged in another file, and a clean change staged",
          VCS + " commit -m x", CMK_AM)
cmk_allow("a commit by path that names only the clean file, the triplet unstaged in another",
          VCS + " commit -m x src/other.py", CMK_AM)
cmk_allow("an add of the clean file and commit, the triplet unstaged in another",
          VCS + " add src/other.py && " + VCS + " commit -m x", CMK_AM)

# 4. Content that is no conflict marker, and a commit with no HEAD to read.
cmk_allow("a clean staged change", VCS + " commit -m x", CMK_CLEAN)
cmk_allow("a staged change that adds trailing whitespace only", VCS + " commit -m x", CMK_WS)
cmk_allow("a markdown file with one marker line in a fence, and a setext underline of =======",
          VCS + " commit -m x", CMK_MDOK)
cmk_allow("a staged triplet in a repository with no commits yet", VCS + " commit -m x", CMK_NOHEAD)

# 5. A fence, a string, a comment or a template literal does not hide a full triplet.
cmk_refuse("a markdown file with a full triplet inside a fence", VCS + " commit -m x", CMK_MDFENCE)
cmk_refuse("a staged triplet after a lone apostrophe in text", VCS + " commit -m x", CMK_LONE)
cmk_refuse("a staged triplet inside a multi-line template literal", VCS + " commit -m x", CMK_TPL)
cmk_refuse("a staged triplet after a string holding comment openers", VCS + " commit -m x", CMK_OPEN)


# The commit check reads the tree only when no earlier segment can change it. The push check judges the
# commits a push would send, so each push case runs in a checkout whose remote is a bare repository
# beside it: nothing leaves the machine.
CMKPUSH = os.path.join(CMKROOT, "push")        # one checkout per push case, on branch `topic`
CMKREMOTE = os.path.join(CMKROOT, "remote")    # the bare remote of each of those checkouts
CMK_PU = os.path.join(CMKPUSH, "unpushed")     # an unpushed commit holding a full triplet
CMK_RB = os.path.join(CMKPUSH, "rebased")      # a commit made by `git rebase --continue`, holding a triplet
CMK_MP = os.path.join(CMKPUSH, "mergepush")    # a commit made by `git merge --continue`, holding a triplet
CMK_NF = os.path.join(CMKPUSH, "newfile")      # an unpushed commit that adds a new file holding a triplet
CMK_CL = os.path.join(CMKPUSH, "clean")        # an unpushed clean commit, and a.txt edited, not staged
CMK_RT = os.path.join(CMKPUSH, "remotetrip")   # a triplet already on the remote branch, then a clean commit
CMK_CLT = os.path.join(CMKPUSH, "cltriplet")   # a.txt holding a triplet, tracked and not staged
CMK_SEQ = os.path.join(CMKPUSH, "seqclean")    # a.txt and b.txt edited, not staged, both clean
CMK_SEQB = os.path.join(CMKPUSH, "seqtriplet")  # as seqclean, with b.txt holding a triplet
CMK_REL = os.path.join(CMKPUSH, "relative")    # diff.relative set; a triplet unpushed in sub/f.txt
CMK_PAREN = os.path.join(CMKPUSH, "fixparen")  # an unpushed triplet on branch fix(x); HEAD on clean topic
CMK_GONE = os.path.join(CMKROOT, "gone")       # a folder no fixture makes: the cd target of the missing-folder cases


def _cmk_commit(where, rel, text, msg):
    _cmk_stage(where, rel, text)
    _cmk_run(where, "commit", "-q", "-m", msg)


def _cmk_unmerged(where, rel):
    """Stop the suite unless `rel` is left unmerged in `where`, as a rebase or merge stop leaves it."""
    lines = [line for line in run_vcs(where, "status", "--porcelain").stdout.splitlines() if rel in line]
    if not any(line[:2] in ("UU", "AA") for line in lines):
        sys.exit("fixture setup failed in the conflict-markers fixtures: %r is not unmerged in %r: %r"
                 % (rel, where, lines))


def _cmk_pushed(where, files):
    """A checkout of `files` on main, pushed to a bare remote beside it, then on branch `topic`, pushed
    too. What is committed on `topic` after this is unpushed."""
    remote = os.path.join(CMKREMOTE, os.path.basename(where) + ".git")
    make_repo(where, files)
    os.makedirs(remote, exist_ok=True)
    _cmk_run(remote, "init", "-q", "--bare")
    _cmk_run(where, "remote", "add", "origin", remote)
    _cmk_run(where, "push", "-q", "-u", "origin", "main")
    _cmk_run(where, "checkout", "-q", "-b", "topic")
    _cmk_run(where, "push", "-q", "-u", "origin", "topic")


def _cmk_must_hold(where, rel, marker, what):
    if marker.strip() not in _cmk_run(where, "show", "HEAD:" + rel):
        sys.exit("fixture setup failed in the conflict-markers fixtures: %s holds no marker" % what)


def _build_conflict_markers_push():
    run, commit = _cmk_run, _cmk_commit

    _cmk_pushed(CMK_PU, {"src/app.py": "x = 1\n"})
    commit(CMK_PU, "src/app.py", "x = 1\n" + CM_TRIPLET, "triplet, unpushed")

    _cmk_pushed(CMK_RB, {"a.txt": "base\n"})
    commit(CMK_RB, "a.txt", "topic\n", "topic change")
    run(CMK_RB, "push", "-q", "origin", "topic")           # the old topic commit is on the remote
    run(CMK_RB, "checkout", "-q", "main")
    commit(CMK_RB, "a.txt", "main\n", "main change")
    run(CMK_RB, "checkout", "-q", "topic")
    run_vcs(CMK_RB, *IDENT, "rebase", "main")              # conflicts on a.txt, and the rebase stops
    _cmk_unmerged(CMK_RB, "a.txt")
    _cmk_stage(CMK_RB, "a.txt", CM_TRIPLET)                # resolved by keeping the markers
    run(CMK_RB, "-c", "core.editor=true", "rebase", "--continue")
    _cmk_must_hold(CMK_RB, "a.txt", CM_START, "the rebased commit")

    _cmk_pushed(CMK_MP, {"a.txt": "base\n"})
    commit(CMK_MP, "a.txt", "topic\n", "topic change")
    run(CMK_MP, "push", "-q", "origin", "topic")
    run(CMK_MP, "checkout", "-q", "main")
    commit(CMK_MP, "a.txt", "main\n", "main change")
    run(CMK_MP, "checkout", "-q", "topic")
    run_vcs(CMK_MP, *IDENT, "merge", "--no-edit", "main")  # conflicts on a.txt
    _require_conflict(CMK_MP, "a.txt")
    _cmk_stage(CMK_MP, "a.txt", CM_TRIPLET)
    run(CMK_MP, "-c", "core.editor=true", "merge", "--continue")
    _cmk_must_hold(CMK_MP, "a.txt", CM_START, "the merge commit")

    _cmk_pushed(CMK_NF, {"a.txt": "base\n"})
    write(os.path.join(CMK_NF, "src", "new.txt"), CM_TRIPLET)
    run(CMK_NF, "add", "-A")
    run(CMK_NF, "commit", "-q", "-m", "new file holding a triplet")

    _cmk_pushed(CMK_CL, {"a.txt": "base\n"})
    commit(CMK_CL, "b.txt", "clean\n", "clean change, unpushed")
    write(os.path.join(CMK_CL, "a.txt"), "edited\n")       # modified, not staged, clean

    _cmk_pushed(CMK_RT, {"a.txt": "base\n"})
    commit(CMK_RT, "a.txt", CM_TRIPLET, "triplet, already sent")
    run(CMK_RT, "push", "-q", "origin", "topic")
    commit(CMK_RT, "b.txt", "clean\n", "clean change, unpushed")

    _cmk_pushed(CMK_CLT, {"a.txt": "base\n"})
    write(os.path.join(CMK_CLT, "a.txt"), CM_TRIPLET)      # tracked, modified, not staged
    commit(CMK_CLT, "b.txt", "clean\n", "clean change, unpushed")

    for path, b_text in ((CMK_SEQ, "b2\n"), (CMK_SEQB, CM_TRIPLET)):
        _cmk_pushed(path, {"a.txt": "base\n", "b.txt": "base\n"})
        write(os.path.join(path, "a.txt"), "a2\n")         # modified, not staged
        write(os.path.join(path, "b.txt"), b_text)

    _cmk_pushed(CMK_REL, {"f.txt": "base\n", "sub/f.txt": "base\n"})
    run(CMK_REL, "config", "diff.relative", "true")
    commit(CMK_REL, "sub/f.txt", CM_TRIPLET, "triplet in sub, unpushed")

    _cmk_pushed(CMK_PAREN, {"a.txt": "base\n"})
    run(CMK_PAREN, "checkout", "-q", "-b", "fix(x)")
    commit(CMK_PAREN, "a.txt", CM_TRIPLET, "triplet on fix(x), unpushed")
    run(CMK_PAREN, "checkout", "-q", "topic")
    run(CMK_PAREN, "branch", "fixy", "fix(x)")             # the same commit, under a plain name
    for gone in (CMK_GONE, os.path.join(CMK_CLT, "nope")):
        if os.path.exists(gone):
            sys.exit("fixture setup failed in the conflict-markers fixtures: %r exists, so a cd to it does not fail"
                     % gone)


lazy_fixture([CMK_PU, CMK_RB, CMK_MP, CMK_NF, CMK_CL, CMK_RT, CMK_CLT, CMK_SEQ, CMK_SEQB, CMK_REL, CMK_PAREN],
             _build_conflict_markers_push)

# A commit that cannot be judged, with no push after it in the call, is no hit. The sed and the fix script
# below cover a file that holds the triplet before the call, so each one with a push after it is refused.
CMK_SED_COMMIT = ("sed -i '/^" + "<" * 7 + " /d;/^" + "=" * 7 + "$/d;/^" + ">" * 7 + " /d' src/app.py && "
                  + VCS + " add src/app.py && " + VCS + " commit -m x")
CMK_FIX_COMMIT = "./fix.sh; " + VCS + " add -A && " + VCS + " commit -m x"
cmk_allow("a sed that deletes the marker lines, then add and commit, no push", CMK_SED_COMMIT, CMK_MERGE)
cmk_allow("a fix script, then add -A and commit, no push", CMK_FIX_COMMIT, CMK_AM)
cmk_refuse("a sed that deletes the marker lines, then add, commit and push", CMK_SED_COMMIT + " && "
           + VCS + " push", CMK_MERGE)
cmk_refuse("a fix script, then add -A, commit and push", CMK_FIX_COMMIT + " && " + VCS + " push", CMK_AM)

# The push check: a push is refused when a commit it would send adds a full triplet, whichever step made it.
cmk_refuse("a push of an unpushed commit that holds a triplet", VCS + " push", CMK_PU)
cmk_refuse("a push of a commit made by rebase --continue that holds a triplet", VCS + " push", CMK_RB)
cmk_refuse("a push of a commit made by merge --continue that holds a triplet", VCS + " push", CMK_MP)
cmk_refuse("a push of a new file that holds a triplet", VCS + " push", CMK_NF)

# A push sends only what is unpushed: clean commits pass, and so does a triplet already on the remote.
cmk_allow("a push of unpushed commits that are clean", VCS + " push", CMK_CL)
cmk_allow("a push of a clean commit, with a triplet already on the remote branch", VCS + " push", CMK_RT)

# A commit then a push in one call: a judged clean commit lets the push through; one that cannot be judged
# is refused.
cmk_allow("add a.txt, commit and push, with a clean a.txt",
          VCS + " add a.txt && " + VCS + " commit -m x && " + VCS + " push", CMK_CL)
# CMK_CL holds no triplet before the call, so the blind chain is allowed.
cmk_allow("a fix script, add -A, commit and push, with no triplet in the tree before the call",
          "./fix.sh && " + VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push", CMK_CL)

# A cd is a safe earlier segment: the commit is judged in the repository it names. These run from a
# directory that is no repository, so only the cd leads to the repository.
cmk_allow("a cd into a repo with a clean change, then add -A, commit and push",
          "cd " + slash(CMK_CL) + " && " + VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push", NOGIT)
cmk_refuse("a cd into a repo with a triplet in a tracked file, then add -A, commit and push",
           "cd " + slash(CMK_CLT) + " && " + VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push", NOGIT)

# A failed cd leaves the shell in its cwd. After `;` the commit runs there, so a missing folder does not stop a
# commit of the triplet in the cwd repository. After `&&` the failed cd ends the chain, so nothing runs.
cmk_refuse("a cd into a missing folder, then ; add -A and commit, with a triplet tracked in the cwd repo",
           "cd " + slash(CMK_GONE) + " ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("a cd into a missing relative folder, then ; add -A and commit, with a triplet tracked in the cwd repo",
           "cd nope ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_allow("a cd into a missing folder, then && add -A and commit, with a triplet tracked in the cwd repo",
          "cd " + slash(CMK_GONE) + " && " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_allow("a cd into a missing folder, then ; add -A and commit, in a cwd repo whose edit is clean",
          "cd " + slash(CMK_GONE) + " ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CL)

# A failed cd leaves the shell where it was, so the next command after `;`, a newline or `||` runs there. After
# `&&` the chain stops. `--work-tree` names the folder an add reads: a missing one fails the add (exit 128), so
# the `&&` stops the commit, and the same call with a real work tree holding the triplet is refused.
cmk_allow("a missing --work-tree, then && commit, with a triplet tracked in the cwd repo",
          VCS + " --work-tree=" + slash(CMK_GONE) + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("an existing --work-tree holding the triplet, then add -A and commit",
           VCS + " --work-tree=" + slash(CMK_CLT) + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("a cd into a missing folder, then && git status, then ; add -A and commit, the triplet in the cwd repo",
           "cd " + slash(CMK_GONE) + " && " + VCS + " status ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("a cd into a missing folder, then && true, then ; add -A and commit, the triplet in the cwd repo",
           "cd " + slash(CMK_GONE) + " && true ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("a cd into a missing folder, then ; add -A and commit, then a cd to a clean repo after the commit",
           "cd " + slash(CMK_GONE) + " ; " + VCS + " add -A && " + VCS + " commit -m x ; cd " + slash(CMK_CL), CMK_CLT)
cmk_refuse("a cd into a missing folder, then || true, then ; add -A and commit, the triplet in the cwd repo",
           "cd " + slash(CMK_GONE) + " || true ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("a cd into a missing folder, then a newline, then add -A and commit, the triplet in the cwd repo",
           "cd " + slash(CMK_GONE) + "\n" + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)

# `cd -` goes back to the folder before the last cd that worked. A failed cd leaves that folder alone, so the
# commit lands in the triplet repo. The NOGIT form has no triplet to refuse, so this case starts in CMK_CLT.
cmk_refuse("a cd into a clean repo, then a cd into a missing folder, then cd -, then add -A and commit",
           "cd " + slash(CMK_CL) + " ; cd " + slash(CMK_GONE) + " ; cd - ; "
           + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)
cmk_refuse("a cd into a clean repo, then cd -, then add -A and commit, the triplet in the cwd repo",
           "cd " + slash(CMK_CL) + " ; cd - ; " + VCS + " add -A && " + VCS + " commit -m x", CMK_CLT)

# An earlier commit is a safe segment too, so each commit is judged and the push sees both.
cmk_allow("two clean commits, each after an add, then a push",
          VCS + " add a.txt && " + VCS + " commit -m a && " + VCS + " add b.txt && " + VCS + " commit -m b && "
          + VCS + " push", CMK_SEQ)
cmk_refuse("two commits, each after an add, the second holding a triplet, then a push",
           VCS + " add a.txt && " + VCS + " commit -m a && " + VCS + " add b.txt && " + VCS + " commit -m b && "
           + VCS + " push", CMK_SEQB)

# A push from a subdirectory with `diff.relative` set: `git diff --check` prints each path relative to that
# directory, so the file it names is read at the top of the tree, under the wrong path. The root push is a
# green control: the same triplet, pushed from the root, is refused today and stays refused.
cmk_refuse("a push from sub/ of a triplet in sub/f.txt, with diff.relative set and a clean f.txt at the top",
           VCS + " push origin topic", os.path.join(CMK_REL, "sub"))
cmk_refuse("a push from the root of the same repo, the triplet in sub/f.txt, with diff.relative set",
           VCS + " push origin topic", CMK_REL)

# A refspec that is no plain name, `fix(x)`, is read as HEAD, so the commit it names is never judged. The
# same commit under the plain name fixy is the green control: it has no tracking ref, so it is judged
# against the default base, and that base holds the triplet.
cmk_refuse("a push of a branch named fix(x) holding a triplet, with HEAD on a clean branch",
           VCS + ' push origin "fix(x)"', CMK_PAREN)
cmk_refuse("a push of the same commit under the plain name fixy, with HEAD on a clean branch",
           VCS + " push origin fixy", CMK_PAREN)


# A commit or a --continue is judged on what it covers. A blind step before a commit (one that can
# change the tree) is refused only when a push follows the commit in the call and the commit covers a
# triplet already in the tree before the call, or when the chain runs a git step that makes a conflict. A
# push judges the net change it sends.
R2_DIR = os.path.join(CMKROOT, "r2")
R2_NEW = os.path.join(R2_DIR, "new")      # new.txt untracked, holding a triplet
R2_RB = os.path.join(R2_DIR, "rebase")    # a rebase stopped on a.txt, the triplet staged after the stop
R2_MC = os.path.join(R2_DIR, "merge")     # a merge stopped on a.txt, the triplet staged after the stop
R2_CP = os.path.join(R2_DIR, "pick")      # a cherry-pick stopped on a.txt, the triplet staged after the stop
R2_MG = os.path.join(R2_DIR, "mg")        # a clean tree, and a merge of feat that conflicts with it
R2_NET = os.path.join(R2_DIR, "net")      # a commit adds a triplet, the next removes it, neither pushed


def _build_conflict_markers_r2():
    run, commit = _cmk_run, _cmk_commit

    _cmk_pushed(R2_NEW, {"a.txt": "base\n"})
    write(os.path.join(R2_NEW, "new.txt"), CM_TRIPLET)      # untracked, not added

    _cmk_pushed(R2_RB, {"a.txt": "base\n"})
    commit(R2_RB, "a.txt", "topic\n", "topic change")
    run(R2_RB, "checkout", "main")
    commit(R2_RB, "a.txt", "main\n", "main change")
    run(R2_RB, "checkout", "topic")
    run_vcs(R2_RB, *IDENT, "rebase", "main")                # conflicts on a.txt, and the rebase stops
    _cmk_unmerged(R2_RB, "a.txt")
    _cmk_stage(R2_RB, "a.txt", CM_TRIPLET)

    _cmk_pushed(R2_MC, {"a.txt": "base\n"})
    commit(R2_MC, "a.txt", "topic\n", "topic change")
    run(R2_MC, "checkout", "main")
    commit(R2_MC, "a.txt", "main\n", "main change")
    run(R2_MC, "checkout", "topic")
    run_vcs(R2_MC, *IDENT, "merge", "--no-edit", "main")    # conflicts on a.txt
    _require_conflict(R2_MC, "a.txt")
    _cmk_stage(R2_MC, "a.txt", CM_TRIPLET)

    _cmk_pushed(R2_CP, {"a.txt": "base\n"})
    run(R2_CP, "checkout", "-b", "pickme")
    commit(R2_CP, "a.txt", "pick\n", "pick change")
    run(R2_CP, "checkout", "topic")
    commit(R2_CP, "a.txt", "topic\n", "topic change")
    run_vcs(R2_CP, *IDENT, "cherry-pick", "pickme")        # conflicts on a.txt
    _cmk_unmerged(R2_CP, "a.txt")
    _cmk_stage(R2_CP, "a.txt", CM_TRIPLET)

    _cmk_pushed(R2_MG, {"a.txt": "base\n"})
    run(R2_MG, "checkout", "-b", "feat")
    commit(R2_MG, "a.txt", "feat\n", "feat change")
    run(R2_MG, "checkout", "topic")
    commit(R2_MG, "a.txt", "topic\n", "topic change")

    _cmk_pushed(R2_NET, {"a.txt": "base\n"})
    commit(R2_NET, "a.txt", CM_TRIPLET, "add a triplet")
    commit(R2_NET, "a.txt", "clean\n", "remove the triplet")


lazy_fixture([R2_NEW, R2_RB, R2_MC, R2_CP, R2_MG, R2_NET], _build_conflict_markers_r2)

# 1. An untracked file holding a triplet is in the commit once it is added, by -A or by name.
cmk_refuse("an untracked new.txt holding a triplet, then add -A, commit and push",
           VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push", R2_NEW)
cmk_refuse("an untracked new.txt holding a triplet, then add it by name and commit",
           VCS + " add new.txt && " + VCS + " commit -m x", R2_NEW)

# 2. A --continue is judged like a commit: the index it would commit holds the triplet.
cmk_refuse("a triplet staged in a.txt in a rebase conflict, then add, rebase --continue and push",
           VCS + " add a.txt && " + VCS + " rebase --continue && " + VCS + " push", R2_RB)
cmk_refuse("a triplet staged in a.txt in a merge conflict, then add, merge --continue and push",
           VCS + " add a.txt && " + VCS + " merge --continue && " + VCS + " push", R2_MC)
cmk_refuse("a triplet staged in a.txt in a cherry-pick conflict, then add, cherry-pick --continue and push",
           VCS + " add a.txt && " + VCS + " cherry-pick --continue && " + VCS + " push", R2_CP)

# 3. A push refspec that does not resolve falls back to HEAD's range, which holds the unpushed triplet.
cmk_refuse("a push of the current branch by a command substitution, with an unpushed triplet commit",
           VCS + ' push -u origin "$(' + VCS + ' branch --show-current)"', CMK_PU)

# 4. An add pathspec that does not resolve is a whole-tree add, which covers the tracked triplet.
cmk_refuse("a tracked triplet, then add of a substituted path list, commit and push",
           VCS + " add $(" + VCS + " diff --name-only) && " + VCS + " commit -m x && "
           + VCS + " push -u origin HEAD", CMK_CLT)

# 5. A blind step before a commit is allowed when no triplet sits in the tree.
cmk_allow("a blind step, then commit -am and push, with no triplet in the tree",
          "./check.sh && " + VCS + " commit -am x && " + VCS + " push", CMK_CL)

# 6. A blind chain with a triplet already in the tree stays refused.
cmk_refuse("a fix script, add -A, commit and push, with a triplet in the tree before the call",
           "./fix.sh && " + VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push", CMK_CLT)

# 7. A chain that runs a git step making a conflict is refused, though the tree starts clean.
cmk_refuse("a merge that conflicts on a clean tree, then add -A, commit and push",
           VCS + " merge feat && " + VCS + " add -A && " + VCS + " commit -m x && " + VCS + " push", R2_MG)

# 8. A push judges the net change it sends: a triplet added and removed again is no hit.
cmk_allow("two commits, the first adding a triplet and the second removing it, then a push",
          VCS + " push", R2_NET)


# =========================================================================== 5e. octopus-push
#
# `octopus-push`. A `git push` is refused when a commit it would send is a merge with more than two parents
# (an octopus merge). The range is the one the conflict-markers push check reads: the destination's
# remote-tracking tip to the pushed ref, else HEAD. An octopus merge already in that tip's history is outside
# the range and passes. A push that writes main or master is out of scope: it keeps its push-main ask. The
# remedy names the two-parent form, so the push can be redone as chained two-parent merges.
#
# Each push case runs in a checkout whose remote is a bare repository beside it: nothing leaves the machine.
# The fixtures reuse the conflict-markers push helpers (`_cmk_pushed`, `_cmk_run`, `_cmk_commit`), and their
# folders carry an `oct-` prefix, so no bare remote name collides with another fixture's.
