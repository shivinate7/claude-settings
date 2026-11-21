# section 43410
FAMILY = "red-run"  # the commit-time check on test commits (rule red-run, decision red-run-trailer-on-test-commits)

# A Bash `git commit` with no `git push` after it in the same call is refused when it adds lines to a test path and
# its own `-m` message holds no valid Red-run trailer. The push cases in s43400-red-run-push.py judge the same trailer at
# push time. A refusal names both trailer forms and a fix that re-runs the commit with the trailer in `-m`. It names no
# `git commit --amend`: the commit has not landed, so an amend would reach the previous HEAD.
RC_RULE = "red-run"
RC_LACKS = RR_REMEDY_LACKS + ("--amend",)
RC_HEREDOC_END = "\nEOF\n)\""                  # closes the heredoc of HEREDOC_HEAD, with no push after it
RC_REVERT_LINE = "This reverts commit abc1234."  # git's revert line: check_red_run does not judge that commit
RC_TEST_MAIN = "hooks/test_main.py"              # the test file _rr_main_test_commit adds on main

RCROOT = os.path.join(ROOT, "redcommit")
RC_UNSTAGED = os.path.join(RCROOT, "rc-unstaged")  # hooks/test_x.py untracked, not added
RC_TRACKED = os.path.join(RCROOT, "rc-tracked")    # hooks/test_x.py tracked on the base, changed, not staged
RC_SIX = os.path.join(RCROOT, "rc-six")            # six test files staged, not committed
RC_DOCS = os.path.join(RCROOT, "rc-docs")          # a docs file, a product file and a spec doc, staged
RC_DELETE = os.path.join(RCROOT, "rc-delete")      # hooks/test_x.py staged for deletion
RC_AMEND = os.path.join(RCROOT, "rc-amend")        # HEAD adds hooks/test_x.py with Red-run: none: x; docs/x.md staged
RC_EMPTY = os.path.join(RCROOT, "rc-empty")        # nothing changed
RC_MERGE = os.path.join(RCROOT, "rc-merge")        # a merge of main in progress: main's test file staged
RC_REVERT = os.path.join(RCROOT, "rc-revert")      # a revert of a test deletion in progress: hooks/test_x.py staged
RC_NOHEAD = os.path.join(RCROOT, "rc-nohead")      # a repo with no commit: hooks/test_x.py staged
RC_LIMIT = os.path.join(RCROOT, "rc-limit")        # hooks/test_x.py staged, msg.txt beside it
RC_CLEAN = os.path.join(RCROOT, "rc-clean")        # hooks/test_x.py and docs/x.md tracked, unchanged: a shell edit is the only change


def _rc_stage(where, files):
    """Write `files` into `where` and stage them. Nothing is committed."""
    for rel, text in files.items():
        write(os.path.join(where, rel), text)
    _rr_run(where, "add", "-A")


def _rc_scope(where, rels, status):
    """Stop the suite unless each of `rels` shows `status` in `git status --porcelain` of `where`. A status of
    "clean" wants each of `rels` tracked and absent from the status. Scope comes before the subject: a fixture that
    lost its change would pass its cases for the wrong reason."""
    lines = run_vcs(where, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()
    if status == "clean":
        tracked = run_vcs(where, "ls-files").stdout.splitlines()
        for rel in rels:
            if rel not in tracked or any(line[3:] == rel for line in lines):
                sys.exit("fixture setup failed in the red-run commit fixtures: %r is not tracked and clean in %r: %r"
                         % (rel, where, lines))
        return
    for rel in rels:
        if not any(line[:2] == status and line[3:] == rel for line in lines):
            sys.exit("fixture setup failed in the red-run commit fixtures: %r has no %r status in %r: %r"
                     % (rel, status, where, lines))


def _build_red_run_commit():
    _cmk_pushed(RC_UNSTAGED, RR_BASE)
    write(os.path.join(RC_UNSTAGED, RR_TEST), RR_TEST_TEXT)
    _rc_scope(RC_UNSTAGED, [RR_TEST], "??")

    _cmk_pushed(RC_TRACKED, {RR_TEST: RR_TEST_TEXT})
    write(os.path.join(RC_TRACKED, RR_TEST), RR_TEST_TEXT + "def test_more():\n    assert 2 == 2\n")
    _rc_scope(RC_TRACKED, [RR_TEST], " M")

    _cmk_pushed(RC_SIX, RR_BASE)
    six = ["hooks/test_%d.py" % number for number in range(1, 7)]
    _rc_stage(RC_SIX, {rel: RR_TEST_TEXT for rel in six})
    _rc_scope(RC_SIX, six, "A ")

    _cmk_pushed(RC_DOCS, RR_BASE)
    docs = {"docs/x.md": "# X\n", "lib/product.py": "x = 1\n", "docs/spec/api.md": "# API\n"}
    _rc_stage(RC_DOCS, docs)
    _rc_scope(RC_DOCS, list(docs), "A ")

    _cmk_pushed(RC_DELETE, {RR_TEST: RR_TEST_TEXT})
    _rr_run(RC_DELETE, "rm", "-q", RR_TEST)
    _rc_scope(RC_DELETE, [RR_TEST], "D ")

    _cmk_pushed(RC_AMEND, RR_BASE)
    _rr_commit(RC_AMEND, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT, RR_NONE_LINE)
    _rc_stage(RC_AMEND, {"docs/x.md": "# X\n"})
    _rc_scope(RC_AMEND, ["docs/x.md"], "A ")

    _cmk_pushed(RC_EMPTY, RR_BASE)

    _cmk_pushed(RC_MERGE, RR_BASE)
    _rr_main_test_commit(RC_MERGE)
    _rr_commit(RC_MERGE, {"b.txt": "lane\n"}, "lane change")
    _rr_run(RC_MERGE, "merge", "-q", "--no-commit", "--no-ff", "main")
    _rc_scope(RC_MERGE, [RC_TEST_MAIN], "A ")

    _cmk_pushed(RC_REVERT, RR_BASE)
    _rr_commit(RC_REVERT, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT, RR_NONE_LINE)
    _rr_run(RC_REVERT, "rm", "-q", RR_TEST)
    _rr_run(RC_REVERT, "commit", "-q", "-m", "delete hooks/test_x.py")
    _rr_run(RC_REVERT, "revert", "--no-commit", "HEAD")
    _rc_scope(RC_REVERT, [RR_TEST], "A ")

    os.makedirs(RC_NOHEAD, exist_ok=True)
    _rr_run(RC_NOHEAD, "init", "-q", "-b", "topic", ".")
    _rc_stage(RC_NOHEAD, {RR_TEST: RR_TEST_TEXT})
    _rc_scope(RC_NOHEAD, [RR_TEST], "A ")

    _cmk_pushed(RC_LIMIT, RR_BASE)
    _rc_stage(RC_LIMIT, {RR_TEST: RR_TEST_TEXT})
    write(os.path.join(RC_LIMIT, "msg.txt"), "add test\n")
    _rc_scope(RC_LIMIT, [RR_TEST], "A ")

    _cmk_pushed(RC_CLEAN, {RR_TEST: RR_TEST_TEXT, "docs/x.md": "# X\n"})
    _rc_scope(RC_CLEAN, [RR_TEST, "docs/x.md"], "clean")


lazy_fixture([RC_UNSTAGED, RC_TRACKED, RC_SIX, RC_DOCS, RC_DELETE, RC_AMEND, RC_EMPTY, RC_MERGE, RC_REVERT,
              RC_NOHEAD, RC_LIMIT, RC_CLEAN], _build_red_run_commit)


def rc_refuse(name, command, cwd):
    sh("red-run: %s, with no push after it, is refused" % name, command, "deny", RC_RULE, cwd=cwd, lacks=RC_LACKS)


def rc_allow(name, command, cwd):
    sh("red-run: %s, with no push after it, is allowed" % name, command, "allow", cwd=cwd)


# 1. A commit that adds a test line with no valid trailer is refused. The malformed forms the push check refuses are
# refused here too. RR_HEREDOC holds hooks/test_x.py staged and nothing committed, so it is reused, not copied.
rc_refuse("a commit -m that adds hooks/test_x.py with no Red-run line", VCS + ' commit -m "add test"', RR_HEREDOC)
rc_refuse("a commit -m with Red-run: none (x), no colon after none",
          VCS + ' commit -m "add test" -m "%s"' % RR_PAREN_LINE, RR_HEREDOC)
rc_refuse("a commit -m with Red-run: pytest x -> 0 failed on abc1234, a zero count",
          VCS + ' commit -m "add test" -m "%s"' % RR_ZERO_LINE, RR_HEREDOC)
rc_refuse("a commit -m with Red-run: pytest x failed, no arrow and no sha",
          VCS + ' commit -m "add test" -m "%s"' % RR_NOARROW_LINE, RR_HEREDOC)
rc_refuse("a commit -m with Red-run: pytest x -> 1 failed on abc12, a sha of five digits",
          VCS + ' commit -m "add test" -m "%s"' % RR_SHORTSHA_LINE, RR_HEREDOC)
rc_refuse("a heredoc commit message with no Red-run trailer in its body", HEREDOC_HEAD + RR_SUBJECT + RC_HEREDOC_END,
          RR_HEREDOC)

# 2. The flags that stage a changed tracked file, and the add that stages a new one, in the same call as the commit.
rc_refuse("a commit -a -m that changes a tracked test file with no Red-run line", VCS + ' commit -a -m "add test"',
          RC_TRACKED)
rc_refuse("a commit -am that changes a tracked test file with no Red-run line", VCS + ' commit -am "add test"',
          RC_TRACKED)
rc_refuse("an add of hooks/test_x.py, then a commit -m in the same call",
          VCS + " add " + RR_TEST + ' && ' + VCS + ' commit -m "add test"', RC_UNSTAGED)

# 3. Full size: six test files in one commit name more paths than the judge lists.
rc_refuse("a commit -m of six test files with no Red-run line", VCS + ' commit -m "add six test files"', RC_SIX)

# 4. The green controls: each refused case has its trailer form allowed on the same fixture.
rc_allow("a commit -m with Red-run: python3 -m pytest x -> 1 failed on abc1234",
         VCS + ' commit -m "add test" -m "%s"' % RR_RED_LINE, RR_HEREDOC)
rc_allow("a commit -m with Red-run: none: x", VCS + ' commit -m "add test" -m "%s"' % RR_NONE_LINE, RR_HEREDOC)
rc_allow("a commit -a -m with Red-run: none: x", VCS + ' commit -a -m "add test" -m "%s"' % RR_NONE_LINE, RC_TRACKED)
rc_allow("a heredoc commit message with Red-run: none: x in its body",
         HEREDOC_HEAD + RR_SUBJECT + "\n\n" + RR_NONE_LINE + RC_HEREDOC_END, RR_HEREDOC)
rc_allow("an add of hooks/test_x.py, then a commit -m with Red-run: none: x",
         VCS + " add " + RR_TEST + ' && ' + VCS + ' commit -m "add test" -m "%s"' % RR_NONE_LINE, RC_UNSTAGED)
rc_allow("a commit -m of six test files with Red-run: none: x",
         VCS + ' commit -m "add six test files" -m "%s"' % RR_NONE_LINE, RC_SIX)

# 5. Commits the rule does not judge: no test line added, nothing staged, no HEAD, a merge, a revert, and an amend that
# keeps a commit's own trailered message.
rc_allow("a commit -m of a docs file, a product file and a spec doc, none a test path", VCS + ' commit -m "docs"',
         RC_DOCS)
rc_allow("a commit -m that only deletes hooks/test_x.py", VCS + ' commit -m "delete test"', RC_DELETE)
rc_allow("a commit --amend --no-edit of a test commit with Red-run: none: x, staging docs only",
         VCS + " commit --amend --no-edit", RC_AMEND)
rc_allow("a commit --allow-empty -m with nothing changed", VCS + ' commit --allow-empty -m "empty"', RC_EMPTY)
rc_allow("a commit -m in a repo with no HEAD, adding hooks/test_x.py", VCS + ' commit -m "add test"', RC_NOHEAD)
rc_allow("a merge commit of main, which added hooks/test_main.py, with no Red-run line", VCS + ' commit -m "merge main"',
         RC_MERGE)
rc_allow("a revert commit that restores hooks/test_x.py, with git's This reverts commit line",
         VCS + ' commit -m "Revert delete test" -m "%s"' % RC_REVERT_LINE, RC_REVERT)

# 6. known-limit: a message from a place the guard cannot read gives no hit, so the commit is allowed. This pins the
# current behaviour, not a desired one. A fix that reads these forms turns these cases red, and then they are re-pointed.
for limit_form in ("-F msg.txt", "-t msg.txt", "-C HEAD", "-c HEAD", "--fixup=HEAD", "--squash=HEAD"):
    rc_allow("known-limit: a commit %s with hooks/test_x.py staged and no Red-run line" % limit_form,
             VCS + " commit " + limit_form, RC_LIMIT)
rc_allow("known-limit: a plain commit with no -m opens an editor, whose message the guard cannot read",
         VCS + " commit", RC_LIMIT)

# 7. A message from `-F -` (also `-F-` and `--file=-`) is read from the heredoc on the commit's own segment, as a
# `-m "$(cat <<'EOF' ...)"` message already is. The body is read as text: its lone quote and its `#` line do not stop
# the read. Each refused form has a green control with `Red-run: none: x` in the same body.
SED_TEST = "sed -i '1s/a/b/' " + RR_TEST
ECHO_TEST = "echo x >> " + RR_TEST


def _rc_file_commit(flag, body, push=False):
    """A `git commit <flag> <<'EOF'` call with `body` as its message, and `git push` after it on the first line when
    `push` is set. The body ends in a plain `EOF` line, not the `)"` that closes a `$(cat ...)`."""
    tail = " && " + VCS + " push" if push else ""
    return VCS + " commit %s <<'EOF'%s\n%s\nEOF\n" % (flag, tail, body)


RC_F_NONE = RR_SUBJECT + "\n\n" + RR_NONE_LINE
RC_QUOTE_BODY = "add hooks/test_x.py: don't drop it\n# a note"
rc_refuse("a commit -F - <<EOF that adds hooks/test_x.py, with no Red-run line in its body",
          _rc_file_commit("-F -", RR_SUBJECT), RR_HEREDOC)
rc_refuse("a commit -F- <<EOF that adds hooks/test_x.py, with no Red-run line in its body",
          _rc_file_commit("-F-", RR_SUBJECT), RR_HEREDOC)
rc_refuse("a commit --file=- <<EOF that adds hooks/test_x.py, with no Red-run line in its body",
          _rc_file_commit("--file=-", RR_SUBJECT), RR_HEREDOC)
rc_refuse("a commit -F - <<EOF with a lone quote and a # line in its body, and no Red-run line",
          _rc_file_commit("-F -", RC_QUOTE_BODY), RR_HEREDOC)
rr_refuse("a commit -F - <<EOF && git push, with no Red-run line in its body",
          _rc_file_commit("-F -", RR_SUBJECT, push=True), RR_HEREDOC)
rc_refuse("a commit -qam after sed -i on hooks/test_x.py, with no Red-run line",
          SED_TEST + " && " + VCS + ' commit -qam "add test"', RC_CLEAN)
rc_refuse("a commit -am after echo x >> hooks/test_x.py, with no Red-run line",
          ECHO_TEST + " && " + VCS + ' commit -am "add test"', RC_CLEAN)
rc_refuse("a commit -m after sed -i on hooks/test_x.py and git add of it, with no Red-run line",
          SED_TEST + " && " + VCS + " add " + RR_TEST + " && " + VCS + ' commit -m "add test"', RC_CLEAN)

rc_allow("a commit -F - <<EOF with Red-run: none: x in its body", _rc_file_commit("-F -", RC_F_NONE), RR_HEREDOC)
rc_allow("a commit -F- <<EOF with Red-run: none: x in its body", _rc_file_commit("-F-", RC_F_NONE), RR_HEREDOC)
rc_allow("a commit --file=- <<EOF with Red-run: none: x in its body",
         _rc_file_commit("--file=-", RC_F_NONE), RR_HEREDOC)
rc_allow("a commit -F - <<EOF with a lone quote and a # line, and Red-run: none: x in its body",
         _rc_file_commit("-F -", RC_QUOTE_BODY + "\n\n" + RR_NONE_LINE), RR_HEREDOC)
rr_allow("a commit -F - <<EOF && git push, with Red-run: none: x in its body",
         _rc_file_commit("-F -", RC_F_NONE, push=True), RR_HEREDOC)
rc_allow("a commit -qam after sed -i on hooks/test_x.py, with Red-run: none: x",
         SED_TEST + " && " + VCS + ' commit -qam "add test" -m "%s"' % RR_NONE_LINE, RC_CLEAN)
rc_allow("a commit -am after echo x >> hooks/test_x.py, with Red-run: none: x",
         ECHO_TEST + " && " + VCS + ' commit -am "add test" -m "%s"' % RR_NONE_LINE, RC_CLEAN)
rc_allow("a commit -m after sed -i on hooks/test_x.py and git add of it, with Red-run: none: x",
         SED_TEST + " && " + VCS + " add " + RR_TEST + " && " + VCS + ' commit -m "add test" -m "%s"' % RR_NONE_LINE,
         RC_CLEAN)

# The green controls that the rule must not reach: a shell edit to a path that is no test, and a shell edit to a
# test that the commit does not take (no -a, no add in the call).
rc_allow("a commit -qam after sed -i on docs/x.md, a path that is no test, with no Red-run line",
         "sed -i '1s/a/b/' docs/x.md && " + VCS + ' commit -qam "docs"', RC_CLEAN)
rc_allow("a commit -m after sed -i on hooks/test_x.py, with no -a and no add, and no Red-run line",
         SED_TEST + " && " + VCS + ' commit -m "add test"', RC_CLEAN)

# 8. A step before the commit that only names a test path does not write it. A test run, a read or a delete leaves the
# file as it was, so the commit adds no test line and needs no trailer. Each case has a green control: the same call
# with `Red-run: none: x` in its -m. A refused control means another rule refuses the call, not this one.
rc_allow("a test run of hooks/test_x.py, then git add of docs/x.md and a commit -m, with no Red-run line",
         "bin/verdict python3 " + RR_TEST + " && " + VCS + " add docs/x.md && " + VCS + ' commit -m "fix"', RC_CLEAN)
rc_allow("a test run of hooks/test_x.py, then git add of docs/x.md and a commit -m, with Red-run: none: x",
         "bin/verdict python3 " + RR_TEST + " && " + VCS + " add docs/x.md && " + VCS + ' commit -m "fix" -m "%s"'
         % RR_NONE_LINE, RC_CLEAN)
rc_allow("a cat of hooks/test_x.py, then a commit -am, with no Red-run line",
         "cat " + RR_TEST + " && " + VCS + ' commit -am "x"', RC_CLEAN)
rc_allow("a cat of hooks/test_x.py, then a commit -am, with Red-run: none: x",
         "cat " + RR_TEST + " && " + VCS + ' commit -am "x" -m "%s"' % RR_NONE_LINE, RC_CLEAN)
rc_allow("a grep of hooks/test_x.py, then a commit -am, with no Red-run line",
         "grep -n x " + RR_TEST + " && " + VCS + ' commit -am "x"', RC_CLEAN)
rc_allow("a grep of hooks/test_x.py, then a commit -am, with Red-run: none: x",
         "grep -n x " + RR_TEST + " && " + VCS + ' commit -am "x" -m "%s"' % RR_NONE_LINE, RC_CLEAN)
rc_allow("an rm of hooks/test_x.py, then a commit -qam, with no Red-run line",
         "rm " + RR_TEST + " && " + VCS + ' commit -qam "drop"', RC_CLEAN)
rc_allow("an rm of hooks/test_x.py, then a commit -qam, with Red-run: none: x",
         "rm " + RR_TEST + " && " + VCS + ' commit -qam "drop" -m "%s"' % RR_NONE_LINE, RC_CLEAN)


RC_REMEDY_LABEL = ("red-run: a commit with no push after it and no Red-run line is refused, and the refusal names both "
                   "trailer forms, a re-run with the trailer in -m, and no --amend")
LOG_FAMILY[RC_REMEDY_LABEL] = FAMILY


def rc_remedy_case():
    """The refusal of a commit that adds a test line with no trailer. It names both trailer forms and a re-run of the
    commit with the trailer in -m. It names no --amend: the commit has not landed, so an amend would reach the previous
    HEAD (the debt red-run-new-amend-hint)."""
    materialize(RR_HEREDOC)
    got, reason = decide(_rr_case(VCS + ' commit -m "add test"', RR_HEREDOC))
    if got != "deny" or RC_RULE not in reason:
        return False, "a commit -m that adds a test line with no trailer is %s, want deny under %s: %s" % (
            got, RC_RULE, reason[:100])
    if "--amend" in reason:
        return False, "the refusal names --amend, which would reach the previous HEAD: %s" % reason[:100]
    remedy = reason.split("Remedy:", 1)[-1]
    missing = [form for form in ("Red-run: none:", "failed on") if form not in remedy]
    if missing:
        return False, "the refusal's remedy does not name the trailer form %r: %s" % (missing[0], remedy[:100])
    if "commit" not in remedy or "-m" not in remedy:
        return False, "the refusal's remedy does not say to re-run the commit with the trailer in -m: %s" % remedy[:100]
    return True, "the refusal names both trailer forms and a re-run with the trailer in -m, and no --amend"


RC_SCOPE_LABEL = ("red-run: the fixture under the plain refused cases holds hooks/test_x.py staged, so each refusal's "
                  "subject is present")
LOG_FAMILY[RC_SCOPE_LABEL] = FAMILY


def rc_scope_case():
    """Scope before subject. The plain refused cases and their controls read the staged test line of RR_HEREDOC. A
    fixture that lost that line would let a refused case read as allow for the wrong reason, so this green check
    names the line first."""
    materialize(RR_HEREDOC)
    lines = run_vcs(RR_HEREDOC, "status", "--porcelain").stdout.splitlines()
    if not any(line[:2] == "A " and line[3:] == RR_TEST for line in lines):
        return False, "%s is not staged in the RR_HEREDOC fixture: %s" % (RR_TEST, lines)
    return True, "%s is staged in the RR_HEREDOC fixture" % RR_TEST


LOG_CHECKS = LOG_CHECKS + ((RC_SCOPE_LABEL, rc_scope_case), (RC_REMEDY_LABEL, rc_remedy_case))
