# section 43400
FAMILY = "red-run"  # the push check on test commits (rule red-run, decision red-run-trailer-on-test-commits)

# A Bash `git push` is refused when a commit the push sends adds lines to a test path and carries no valid
# Red-run trailer. A valid trailer is `Red-run: <command> -> <N> failed on <sha>` (N 1 or more, sha 7 or more hex
# digits) or `Red-run: none: <reason>`. A refusal names only acts the guard allows with no force push. The check
# runs one `git log` per push and no diff.
RR_RULE = "red-run"
RR_TEST = "hooks/test_x.py"
RR_TEST_TEXT = "def test_x():\n    assert 1 == 1\n"
RR_SUBJECT = "add hooks/test_x.py"
RR_BASE = {"a.txt": "base\n"}
RR_RED_LINE = "Red-run: python3 -m pytest x -> 1 failed on abc1234"
RR_NONE_LINE = "Red-run: none: x"
RR_PAREN_LINE = "Red-run: none (x)"
RR_ZERO_LINE = "Red-run: pytest x -> 0 failed on abc1234"
RR_NOARROW_LINE = "Red-run: pytest x failed"
RR_SHORTSHA_LINE = "Red-run: pytest x -> 1 failed on abc12"
# The acts a refusal must never name: the replacement route of the old CLI remedy, which needs a branch switch,
# a cherry-pick and a replacement pull request, and a force push.
RR_REMEDY_LACKS = ("git switch", "cherry-pick", "replacement PR", "--force")

RRROOT = os.path.join(ROOT, "redrun")                  # one folder per run, under the run folder
RR_PLAIN = os.path.join(RRROOT, "rr-plain")            # topic: an unpushed commit adding hooks/test_x.py, no trailer
RR_RED = os.path.join(RRROOT, "rr-red")                # the same commit, with a valid red-run line
RR_NONE = os.path.join(RRROOT, "rr-none")              # the same commit, with `none: x`
RR_PAREN = os.path.join(RRROOT, "rr-paren")            # the same commit, with `none (x)`
RR_ZERO = os.path.join(RRROOT, "rr-zero")              # the same commit, with a zero count
RR_NOARROW = os.path.join(RRROOT, "rr-noarrow")        # the same commit, with no arrow and no sha
RR_SHORTSHA = os.path.join(RRROOT, "rr-shortsha")      # the same commit, with a five-digit sha
RR_COMMENT = os.path.join(RRROOT, "rr-comment")        # a comment line reworded in hooks/test_x.py, no trailer
RR_COMMENT_NONE = os.path.join(RRROOT, "rr-commentnone")  # the same reword, with `none: x`
RR_DOCS = os.path.join(RRROOT, "rr-docs")              # one commit: a docs file, a product file and a spec doc
RR_DELETE = os.path.join(RRROOT, "rr-delete")          # one commit that deletes hooks/test_x.py
RR_SIX = os.path.join(RRROOT, "rr-six")                # one commit adding six test files, none with a trailer
RR_EMPTY = os.path.join(RRROOT, "rr-empty")            # pushed, with nothing unpushed
RR_MERGE = os.path.join(RRROOT, "rr-merge")            # topic merged main, which holds an untrailered test commit
RR_REBASE = os.path.join(RRROOT, "rr-rebase")          # topic rebased onto main, which holds one
RR_LANEMERGE = os.path.join(RRROOT, "rr-lanemerge")    # topic's own untrailered test commit, then a merge of main
RR_LANEREBASE = os.path.join(RRROOT, "rr-lanerebase")  # the same, then a rebase onto main
RR_CHAIN = os.path.join(RRROOT, "rr-chain")            # a fresh branch, no upstream, untracked test and docs files
RR_NOBASE = os.path.join(RRROOT, "rr-nobase")          # no remote, no tracking ref, no main
RR_GAPDOCS = os.path.join(RRROOT, "rr-gapdocs")        # an untrailered test commit, then a docs commit on top of it
RR_HEREDOC = os.path.join(RRROOT, "rr-heredoc")        # test lines staged and not committed: the commit is in the call
RR_BELOW = os.path.join(RRROOT, "rr-below")            # an untrailered test commit, then a docs commit on top of it
RR_LIMIT = os.path.join(RRROOT, "rr-limit")            # an untrailered test commit, then a docs file staged for the commit forms below
RR_TRAILER_FIXTURES = (
    (RR_PLAIN, None),
    (RR_RED, RR_RED_LINE),
    (RR_NONE, RR_NONE_LINE),
    (RR_PAREN, RR_PAREN_LINE),
    (RR_ZERO, RR_ZERO_LINE),
    (RR_NOARROW, RR_NOARROW_LINE),
    (RR_SHORTSHA, RR_SHORTSHA_LINE),
)
RR_FIXTURES = [where for where, _ in RR_TRAILER_FIXTURES] + [
    RR_COMMENT, RR_COMMENT_NONE, RR_DOCS, RR_DELETE, RR_SIX, RR_EMPTY, RR_MERGE, RR_REBASE,
    RR_LANEMERGE, RR_LANEREBASE, RR_CHAIN, RR_NOBASE, RR_GAPDOCS]


def _rr_run(where, *args):
    """One git call that builds a fixture. A failure stops the suite here, not in a case."""
    done = run_vcs(where, *IDENT, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in the red-run push fixtures: git %s in %r: %s"
                 % (" ".join(args), where, done.stderr.strip()))


def _rr_commit(where, files, *paragraphs):
    """Write `files` and commit them. `paragraphs` are the message's -m paragraphs: the subject first."""
    for rel, text in files.items():
        write(os.path.join(where, rel), text)
    _rr_run(where, "add", "-A")
    message = []
    for paragraph in paragraphs:
        message += ["-m", paragraph]
    _rr_run(where, "commit", "-q", *message)


def _rr_main_test_commit(where):
    """Main gets an untrailered test commit and is pushed, so origin/main holds it. Topic is checked out again."""
    _rr_run(where, "checkout", "-q", "main")
    _rr_commit(where, {"hooks/test_main.py": RR_TEST_TEXT}, "add hooks/test_main.py")
    _rr_run(where, "push", "-q", "origin", "main")
    _rr_run(where, "checkout", "-q", "topic")


def _build_red_run_push():
    for where, trailer in RR_TRAILER_FIXTURES:
        _cmk_pushed(where, RR_BASE)
        _rr_commit(where, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT, *([trailer] if trailer else []))

    old = "# old note\n" + RR_TEST_TEXT
    new = "# new note\n" + RR_TEST_TEXT
    _cmk_pushed(RR_COMMENT, {RR_TEST: old})
    _rr_commit(RR_COMMENT, {RR_TEST: new}, "reword a comment in hooks/test_x.py")
    _cmk_pushed(RR_COMMENT_NONE, {RR_TEST: old})
    _rr_commit(RR_COMMENT_NONE, {RR_TEST: new}, "reword a comment in hooks/test_x.py", RR_NONE_LINE)

    _cmk_pushed(RR_DOCS, RR_BASE)
    _rr_commit(RR_DOCS, {"docs/x.md": "# X\n", "lib/product.py": "x = 1\n", "docs/spec/api.md": "# API\n"},
               "docs, a product file and a spec doc")

    _cmk_pushed(RR_DELETE, {RR_TEST: RR_TEST_TEXT})
    os.remove(os.path.join(RR_DELETE, RR_TEST))
    _rr_run(RR_DELETE, "add", "-A")
    _rr_run(RR_DELETE, "commit", "-q", "-m", "delete hooks/test_x.py")

    _cmk_pushed(RR_SIX, RR_BASE)
    _rr_commit(RR_SIX, {"hooks/test_%d.py" % number: RR_TEST_TEXT for number in range(1, 7)},
               "add six test files")

    _cmk_pushed(RR_EMPTY, RR_BASE)

    _cmk_pushed(RR_MERGE, RR_BASE)
    _rr_main_test_commit(RR_MERGE)
    _rr_commit(RR_MERGE, {"b.txt": "lane\n"}, "lane change")
    _rr_run(RR_MERGE, "merge", "-q", "--no-edit", "main")

    _cmk_pushed(RR_REBASE, RR_BASE)
    _rr_main_test_commit(RR_REBASE)
    _rr_commit(RR_REBASE, {"b.txt": "lane\n"}, "lane change")
    _rr_run(RR_REBASE, "rebase", "-q", "main")

    _cmk_pushed(RR_LANEMERGE, RR_BASE)
    _rr_commit(RR_LANEMERGE, {"hooks/test_own.py": RR_TEST_TEXT}, "add hooks/test_own.py")
    _rr_main_test_commit(RR_LANEMERGE)
    _rr_run(RR_LANEMERGE, "merge", "-q", "--no-edit", "main")

    _cmk_pushed(RR_LANEREBASE, RR_BASE)
    _rr_commit(RR_LANEREBASE, {"hooks/test_own.py": RR_TEST_TEXT}, "add hooks/test_own.py")
    _rr_main_test_commit(RR_LANEREBASE)
    _rr_run(RR_LANEREBASE, "rebase", "-q", "main")

    _cmk_pushed(RR_GAPDOCS, RR_BASE)
    _rr_commit(RR_GAPDOCS, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT)
    _rr_commit(RR_GAPDOCS, {"docs/x.md": "# X\n"}, "docs on top of an untrailered test commit")

    _cmk_pushed(RR_CHAIN, RR_BASE)
    _rr_run(RR_CHAIN, "checkout", "-q", "-b", "fresh")
    write(os.path.join(RR_CHAIN, RR_TEST), RR_TEST_TEXT)       # untracked: the chain adds it
    write(os.path.join(RR_CHAIN, "docs", "x.md"), "# X\n")     # untracked

    os.makedirs(RR_NOBASE, exist_ok=True)
    _rr_run(RR_NOBASE, "init", "-q", "-b", "topic", ".")
    _rr_commit(RR_NOBASE, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT)


lazy_fixture(RR_FIXTURES, _build_red_run_push)


def _rr_case(command, cwd, env_path=None):
    """A case built by hand for a checker that runs decide on one command. decide reads these keys."""
    return {"raw": None, "tool": "Bash", "cwd": cwd, "session": None, "env_path": env_path, "config": None,
            "agent_id": None, "agent_type": None, "event": None, "stop_active": False, "transcript": None,
            "env": None, "temp": None, "guard": None, "no_root": False, "tool_input": {"command": command}}


def rr_refuse(name, command, cwd):
    sh("red-run: %s is refused" % name, command, "deny", RR_RULE, cwd=cwd, lacks=RR_REMEDY_LACKS)


def rr_allow(name, command, cwd):
    sh("red-run: %s is allowed" % name, command, "allow", cwd=cwd)


# 1. A push that sends a test commit with no Red-run line is refused.
rr_refuse("a push of an unpushed commit that adds hooks/test_x.py with no Red-run line", VCS + " push", RR_PLAIN)

# 2. A malformed Red-run line is no line: a zero count, no arrow and no sha, and a sha of five digits.
rr_refuse("a test commit with Red-run: pytest x -> 0 failed on abc1234, a zero count", VCS + " push", RR_ZERO)
rr_refuse("a test commit with Red-run: pytest x failed, no arrow and no sha", VCS + " push", RR_NOARROW)
rr_refuse("a test commit with Red-run: pytest x -> 1 failed on abc12, a sha of five digits", VCS + " push", RR_SHORTSHA)

# 3. `none` takes a colon and a reason. `none (x)` is refused; `none: x` is allowed.
rr_refuse("a test commit with Red-run: none (x), no colon after none", VCS + " push", RR_PAREN)
rr_allow("a test commit with Red-run: none: x", VCS + " push", RR_NONE)

# 4. A comment-only edit to a test file is a test line too, so it needs a line. Its `none` control is allowed.
rr_refuse("a comment-only reword in hooks/test_x.py with no Red-run line", VCS + " push", RR_COMMENT)
rr_allow("a comment-only reword in hooks/test_x.py with Red-run: none: x", VCS + " push", RR_COMMENT_NONE)

# 5. A merge of main or a rebase onto main brings main's commits in, and they are not judged. The lane's own
# untrailered test commit is judged, merged or rebased alike.
rr_allow("a lane that merged main, which holds an untrailered test commit", VCS + " push", RR_MERGE)
rr_allow("a lane that rebased onto main, which holds an untrailered test commit", VCS + " push", RR_REBASE)
rr_refuse("a lane's own untrailered test commit, then a merge of main that holds another", VCS + " push",
          RR_LANEMERGE)
rr_refuse("a lane's own untrailered test commit, then a rebase onto main that holds another", VCS + " push",
          RR_LANEREBASE)

# 6. A valid trailer lets the push through. A range git cannot read is no hit.
rr_allow("a test commit with Red-run: python3 -m pytest x -> 1 failed on abc1234", VCS + " push", RR_RED)
rr_allow("a push where git reads no base: no remote, no tracking ref, no main", VCS + " push origin topic", RR_NOBASE)

# 7. Full size and empty. Six test files in one commit name more paths than the judge lists. A push with
# nothing unpushed sends nothing, and a commit that only deletes a test file adds no test line.
rr_refuse("a commit that adds six test files, none with a trailer", VCS + " push", RR_SIX)
rr_allow("a push with nothing unpushed", VCS + " push", RR_EMPTY)
rr_allow("a commit that only deletes hooks/test_x.py", VCS + " push", RR_DELETE)
rr_allow("a push of a docs file, a product file and a spec doc, none a test path", VCS + " push", RR_DOCS)

# 8. The refusal's remedy is an amend with a Red-run line, then a push, and no branch switch or force push. The
# chain forms read the commit's own message: a valid line lets the amend or the commit pass, and no line refuses it.
rr_allow("a commit --amend that gives the test commit a Red-run line, then a push",
         VCS + ' commit --amend -m s -m "Red-run: none: x" && ' + VCS + " push", RR_PLAIN)
rr_refuse("a commit --amend that gives the test commit no Red-run line, then a push",
          VCS + " commit --amend -m s && " + VCS + " push", RR_PLAIN)
rr_allow("a commit --amend of a docs-only commit, then a push",
         VCS + " commit --amend -m s && " + VCS + " push", RR_DOCS)
rr_allow("add a test file, commit with a Red-run line, then a push of a fresh branch",
         VCS + " add " + RR_TEST + " && " + VCS + ' commit -m m -m "Red-run: none: x" && ' + VCS
         + " push origin fresh", RR_CHAIN)
rr_refuse("add a test file, commit with no Red-run line, then a push of a fresh branch",
          VCS + " add " + RR_TEST + " && " + VCS + " commit -m m && " + VCS + " push origin fresh", RR_CHAIN)
rr_allow("add a docs file, commit, then a push of a fresh branch",
         VCS + " add docs/x.md && " + VCS + " commit -m m && " + VCS + " push origin fresh", RR_CHAIN)
# A valid line on the last commit does not clear an untrailered test commit below it: the push sends both, so it is
# refused. A check that reads only HEAD's own message would allow it.
rr_refuse("a commit --amend that gives the docs commit on top a Red-run line, with an untrailered test commit below",
          VCS + ' commit --amend -m s -m "Red-run: none: x" && ' + VCS + " push", RR_GAPDOCS)


def _build_red_run_heredoc_below_limit():
    _cmk_pushed(RR_HEREDOC, RR_BASE)
    write(os.path.join(RR_HEREDOC, RR_TEST), RR_TEST_TEXT)
    _rr_run(RR_HEREDOC, "add", "-A")

    _cmk_pushed(RR_BELOW, RR_BASE)
    _rr_commit(RR_BELOW, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT)
    _rr_commit(RR_BELOW, {"docs/x.md": "# X\n"}, "docs on top of an untrailered test commit")

    _cmk_pushed(RR_LIMIT, RR_BASE)
    _rr_commit(RR_LIMIT, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT)
    write(os.path.join(RR_LIMIT, "docs", "y.md"), "# Y\n")
    _rr_run(RR_LIMIT, "add", "-A")
    write(os.path.join(RR_LIMIT, "msg.txt"), "docs y\n")


lazy_fixture([RR_HEREDOC, RR_BELOW, RR_LIMIT], _build_red_run_heredoc_below_limit)

# 9. A heredoc message is judged on its body, so a Red-run trailer in the body is a valid line. The bare heredoc is
# the green control: a body with no trailer is refused.
HEREDOC_HEAD = VCS + ' commit -m "$(cat <<\'EOF\'\n'
HEREDOC_TAIL = '\nEOF\n)" && ' + VCS + " push"
rr_allow("a heredoc commit message with a Red-run trailer in its body, then a push",
         HEREDOC_HEAD + RR_SUBJECT + "\n\n" + RR_NONE_LINE + HEREDOC_TAIL, RR_HEREDOC)
rr_refuse("a heredoc commit message with no Red-run trailer in its body, then a push",
          HEREDOC_HEAD + RR_SUBJECT + HEREDOC_TAIL, RR_HEREDOC)

# 10. A flagged commit below the tip. The refusal must print a git command that names that commit, and the guard must
# allow each such command, run in the fixture. The push is left out: its range is the rewritten history, which the
# fixture does not hold. Why: a remedy that amends only the tip does not reach the commit that was flagged.
RR_BELOW_LACKS = ("git switch", "git checkout", "cherry-pick", "new branch", "replacement PR", "--force")
RR_BELOW_LABEL = ("red-run: a flagged commit below the tip: the refusal prints a git command that names that commit, "
                  "and each such command, run in the fixture, is allowed")
LOG_FAMILY[RR_BELOW_LABEL] = FAMILY


def rr_below_remedy_case():
    """The refusal of a push that sends a flagged test commit below the tip prints a remedy that reaches that commit."""
    materialize(RR_BELOW)
    got, reason = decide(_rr_case(VCS + " push", RR_BELOW))
    if got != "deny" or RR_RULE not in reason:
        return False, "a push of an untrailered test commit below the tip is %s, want deny under %s: %s" % (
            got, RR_RULE, reason[:100])
    remedy = reason.split("Remedy:", 1)[-1]
    lacked = [fragment for fragment in RR_BELOW_LACKS if fragment in remedy]
    if lacked:
        return False, "the refusal's remedy names %r, which is no act the guard allows with no force push" % lacked[0]
    below = run_vcs(RR_BELOW, "rev-parse", "HEAD~1").stdout.strip()
    short = below[:7]
    commands = [span for span in re.findall(r"`([^`]*)`", remedy) if "git " in span]
    names = [span for span in commands if "<sha>" in span or short in span]
    if not names:
        return False, "the refusal prints no git command that names the commit below the tip: %s" % remedy[:120]
    for span in names:
        if re.search(r"\bgit push\b", span):
            continue
        filled = _rr_fill(span, short)
        got, reason = decide(_rr_case(filled, RR_BELOW))
        if got != "allow":
            return False, "the printed command `%s`, run in the fixture, is %s, want allow: %s" % (
                filled, got, reason[:100])
    return True, "the refusal prints a git command that names the commit below the tip, and each one is allowed"


# 11. known-limit: a commit whose message comes from a place the guard cannot read (-F, -C, -c, -t, --fixup or
# --squash) makes the whole push no-hit, so an untrailered test commit below it is allowed. This pins the current
# behaviour, not a desired one. A fix that reads these forms turns these cases red, and then they are re-pointed.
LIMIT_COMMIT_THEN_PUSH = VCS + " commit %s && " + VCS + " push"
for limit_form in ("-F msg.txt", "-C HEAD", "-c HEAD", "-t msg.txt", "--fixup=HEAD", "--squash=HEAD"):
    rr_allow("known-limit: a commit with %s, then a push, sends an untrailered test commit below it and is allowed"
             % limit_form, LIMIT_COMMIT_THEN_PUSH % limit_form, RR_LIMIT)


def rr_remedy_case():
    """The refusal of a test commit with no Red-run line prints only commit and push, and the amend it prints, run
    with a Red-run line and then a push, is allowed. Scope first: the push is refused under the rule. Why: a remedy
    that needs a branch switch or a force push sent the lanes to replacement pull requests (decision
    red-run-trailer-on-test-commits, incidents of Nov 7 to 10)."""
    materialize(RR_PLAIN)
    got, reason = decide(_rr_case(VCS + " push", RR_PLAIN))
    if got != "deny" or RR_RULE not in reason:
        return False, "a push of a test commit with no Red-run line is %s, want deny under %s: %s" % (
            got, RR_RULE, reason[:100])
    verbs = sorted(set(re.findall(r"\bgit ([a-z][a-z-]*)", reason)))
    if not verbs:
        return False, "the refusal names no git act, so it prints no remedy: %s" % reason[:100]
    extra = [verb for verb in verbs if verb not in ("commit", "push")]
    if extra:
        return False, "the refusal names git %s, which is no act the guard allows with no force push" % extra[0]
    printed = re.search(r'git commit --amend\b[^`\n]*?-m\s+"Red-run:[^"]*"', reason)
    if not printed:
        return False, "the refusal prints no amend that carries a Red-run line: %s" % reason[:100]
    amend = re.sub(r'-m\s+"Red-run:[^"]*"', '-m "Red-run: none: x"', printed.group(0))
    amend = re.sub(r"<[^>]*>", "s", amend)
    remedy = amend + " && " + VCS + " push"
    got, reason = decide(_rr_case(remedy, RR_PLAIN))
    if got != "allow":
        return False, "the printed remedy, run as `%s`, is %s, want allow: %s" % (remedy, got, reason[:100])
    return True, "the refusal names only commit and push, and its printed amend, run with a Red-run line, is allowed"


RR_REMEDY_LABEL = ("red-run: the refusal of a test commit names only commit and push, and its printed amend, "
                   "run with a Red-run line, is allowed")
LOG_FAMILY[RR_REMEDY_LABEL] = FAMILY
# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so this check joins LOG_CHECKS here, as section 42840 does.
LOG_CHECKS = LOG_CHECKS + ((RR_REMEDY_LABEL, rr_remedy_case), (RR_BELOW_LABEL, rr_below_remedy_case))

# 12-15. The printed remedy runs for real. Each case copies its fixture under this run's folder and runs the printed git
# commands there, in order, so the fixture stays as built. The lane's commits are judged by check_red_run over
# main..HEAD, which holds no main commit: the same range the push judges, less the commits the default base holds.
RR_MERGEBELOW = os.path.join(RRROOT, "rr-undermerge")  # an untrailered test commit, a merge of main, then a docs commit on top
RR_REWRITTEN = os.path.join(RRROOT, "rr-rewritten")    # an untrailered test commit pushed, then amended: the branch rewritten since its push


def _build_red_run_merge_below_rewritten():
    _cmk_pushed(RR_MERGEBELOW, RR_BASE)
    _rr_commit(RR_MERGEBELOW, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT)
    _rr_main_test_commit(RR_MERGEBELOW)
    _rr_run(RR_MERGEBELOW, "merge", "--no-edit", "main")
    _rr_commit(RR_MERGEBELOW, {"docs/x.md": "# X\n"}, "docs on top of a merge of main")

    _cmk_pushed(RR_REWRITTEN, RR_BASE)
    _rr_commit(RR_REWRITTEN, {RR_TEST: RR_TEST_TEXT}, RR_SUBJECT)
    _rr_run(RR_REWRITTEN, "push", "origin", "topic")
    _rr_run(RR_REWRITTEN, "commit", "-q", "--amend", "-m", "add hooks/test_x.py, reworded")


lazy_fixture([RR_MERGEBELOW, RR_REWRITTEN], _build_red_run_merge_below_rewritten)


def _rr_copy(where, name):
    """A copy of a fixture under this run's folder, so a printed remedy runs in the copy and the fixture stays as built."""
    dest = os.path.join(ROOT, "redrun", "copies", name)
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(where, dest, symlinks=True)
    return dest


def _rr_fill(span, short):
    """One printed span as a shell command: the flagged sha filled in, the Red-run trailer given a value, and each other
    placeholder a word a shell passes through unchanged."""
    filled = span.replace("<sha>", short)
    filled = re.sub(r"Red-run: \.\.\.", "Red-run: none: x", filled)
    return re.sub(r"<[^>]*>", "s", filled)


def _rr_remedy_commands(remedy, short):
    """The git commands a refusal prints, in order, minus the push, each one filled by _rr_fill."""
    return [_rr_fill(span, short) for span in re.findall(r"`([^`]*)`", remedy)
            if "git " in span and not re.search(r"\bgit push\b", span)]


def _rr_run_printed(copy, commands):
    """Run each printed command in order in `copy`. Returns (the command that fails, its output tail), or (None, '')."""
    env = dict(os.environ, GIT_AUTHOR_NAME="cases", GIT_AUTHOR_EMAIL="cases@example.invalid",
               GIT_COMMITTER_NAME="cases", GIT_COMMITTER_EMAIL="cases@example.invalid")
    for command in commands:
        done = subprocess.run(command, shell=True, cwd=copy, env=env, capture_output=True, text=True)
        if done.returncode != 0:
            return command, (done.stdout + done.stderr).strip()[-200:]
    return None, ""


def _rr_lane_judge(copy, main):
    """(exit code, FAIL lines) from check_red_run over main..HEAD, the lane's commits. Exit 0 is clean; 2 is unknown."""
    done = subprocess.run([sys.executable, os.path.join(REPO, "lint", "check_red_run.py"), "--base", main, "--root", copy],
                          capture_output=True, text=True)
    return done.returncode, [line for line in done.stdout.splitlines() if line.startswith("check_red_run: FAIL")]


def _rr_merges(copy, main):
    """How many merge commits the lane holds above main, or -1 when git cannot read them."""
    done = run_vcs(copy, "rev-list", "--merges", "--count", main + "..HEAD")
    return int(done.stdout.strip()) if done.returncode == 0 else -1


def _rr_remedy_holds(where, name, remedy, flagged, main):
    """'' when the commands the remedy prints, run in a copy of `where`, leave the lane's commits judged clean and keep
    every merge above `main`. Otherwise one line that names the cause."""
    commands = _rr_remedy_commands(remedy, flagged)
    if not commands:
        return "the refusal prints no git command for flagged commit %s: %s" % (flagged, remedy[:120])
    merges = _rr_merges(where, main)
    copy = _rr_copy(where, name)
    failed, output = _rr_run_printed(copy, commands)
    if failed:
        return "the printed command `%s` fails in the fixture: %s" % (failed, output)
    kept = _rr_merges(copy, main)
    if kept != merges:
        return "the printed commands drop the merge: %d merge commit(s) above main before, %d after" % (merges, kept)
    code, fails = _rr_lane_judge(copy, main)
    if code != 0 or fails:
        return "after the printed commands, check_red_run still flags: %s" % (fails[0] if fails else "exit %d" % code)
    return ""


RR_MERGE_TIP_LABEL = ("red-run: a flagged commit under a merge at the tip: the refusal prints no git commit --amend, and each "
                      "printed command, run in the fixture, leaves the lane's commits judged clean")
LOG_FAMILY[RR_MERGE_TIP_LABEL] = FAMILY


def rr_merge_tip_remedy_case():
    """A flagged commit with a merge of main above it. The refusal must not print an amend: it reaches the merge, not the
    flagged commit. Each printed command, run in the fixture, must leave the lane's commits judged clean. Why: a Red-run
    trailer on the merge leaves the flagged commit with none, so the push is refused again."""
    materialize(RR_LANEMERGE)
    flagged = run_vcs(RR_LANEMERGE, "rev-parse", "HEAD^1").stdout.strip()[:7]
    main = run_vcs(RR_LANEMERGE, "rev-parse", "origin/main").stdout.strip()
    got, reason = decide(_rr_case(VCS + " push", RR_LANEMERGE))
    if got != "deny" or RR_RULE not in reason:
        return False, "a push of a flagged commit under a merge at the tip is %s, want deny under %s: %s" % (
            got, RR_RULE, reason[:100])
    if flagged not in reason:
        return False, "the refusal does not name flagged commit %s: %s" % (flagged, reason[:100])
    remedy = reason.split("Remedy:", 1)[-1]
    if "git commit --amend" in remedy:
        return False, "the refusal prints `git commit --amend`, which reaches the merge at the tip, not flagged commit %s" % flagged
    problem = _rr_remedy_holds(RR_LANEMERGE, "merge-tip", remedy, flagged, main)
    if problem:
        return False, problem
    return True, "the refusal for a flagged commit under a merge at the tip prints no amend, and its printed commands leave the lane clean"


RR_MERGE_BELOW_LABEL = ("red-run: a flagged commit below a merge of main and a docs commit: each printed command, run in the "
                        "fixture, leaves the lane's commits judged clean and keeps the merge")
LOG_FAMILY[RR_MERGE_BELOW_LABEL] = FAMILY


def rr_merge_below_remedy_case():
    """A flagged commit below a merge, with a docs commit on top. Each printed command, run in the fixture, must leave the
    lane's commits judged clean, with no main commit flagged, and the merge still in the history. Why: a rebase that does
    not keep merges drops the merge and replays main's commit under a new sha, so the judge reads that commit as an
    untrailered test commit."""
    materialize(RR_MERGEBELOW)
    flagged = run_vcs(RR_MERGEBELOW, "rev-parse", "HEAD~1^1").stdout.strip()[:7]
    main = run_vcs(RR_MERGEBELOW, "rev-parse", "origin/main").stdout.strip()
    got, reason = decide(_rr_case(VCS + " push", RR_MERGEBELOW))
    if got != "deny" or RR_RULE not in reason:
        return False, "a push of a flagged commit below a merge is %s, want deny under %s: %s" % (got, RR_RULE, reason[:100])
    if flagged not in reason:
        return False, "the refusal does not name flagged commit %s: %s" % (flagged, reason[:100])
    remedy = reason.split("Remedy:", 1)[-1]
    problem = _rr_remedy_holds(RR_MERGEBELOW, "merge-below", remedy, flagged, main)
    if problem:
        return False, problem
    return True, "the printed commands below a merge keep the merge and leave the lane clean, with no main commit flagged"


RR_BELOW_CONTROL_LABEL = ("red-run: a flagged commit below the tip with no merge: each printed command, run in the fixture, "
                          "leaves the lane's commits judged clean (the green control for the run)")
LOG_FAMILY[RR_BELOW_CONTROL_LABEL] = FAMILY


def rr_below_control_case():
    """The green control for the shared run: a linear flagged commit below the tip. Its printed amend and rebase, run in a
    copy, leave the lane clean and keep no merge. A failure here is in the run itself, not in the remedy."""
    materialize(RR_BELOW)
    flagged = run_vcs(RR_BELOW, "rev-parse", "HEAD~1").stdout.strip()[:7]
    main = run_vcs(RR_BELOW, "rev-parse", "origin/main").stdout.strip()
    got, reason = decide(_rr_case(VCS + " push", RR_BELOW))
    if got != "deny" or RR_RULE not in reason:
        return False, "a push of a flagged commit below the tip is %s, want deny under %s: %s" % (got, RR_RULE, reason[:100])
    if flagged not in reason:
        return False, "the refusal does not name flagged commit %s: %s" % (flagged, reason[:100])
    remedy = reason.split("Remedy:", 1)[-1]
    problem = _rr_remedy_holds(RR_BELOW, "below-control", remedy, flagged, main)
    if problem:
        return False, problem
    return True, "the printed commands below the tip, run in a copy, leave the lane clean"


RR_REWRITTEN_LABEL = ("red-run: a branch rewritten since its push: the refusal says the owner must reword the commits, "
                      "and prints no git command")
LOG_FAMILY[RR_REWRITTEN_LABEL] = FAMILY


def rr_rewritten_remedy_case():
    """A flagged commit on a branch rewritten since its push. The refusal says the owner must reword it and prints no git
    command. Why: a reword would rewrite pushed history, which no session does (RED_RUN_PUSHED_FIX)."""
    materialize(RR_REWRITTEN)
    rewritten = run_vcs(RR_REWRITTEN, "merge-base", "--is-ancestor", "origin/topic", "HEAD")
    if rewritten.returncode != 1:
        return False, "the fixture is not rewritten: origin/topic is an ancestor of HEAD, so no refusal reads a rewritten branch"
    got, reason = decide(_rr_case(VCS + " push", RR_REWRITTEN))
    if got != "deny" or RR_RULE not in reason:
        return False, "a push of a rewritten branch is %s, want deny under %s: %s" % (got, RR_RULE, reason[:100])
    remedy = reason.split("Remedy:", 1)[-1]
    if "owner" not in remedy:
        return False, "the refusal for a rewritten branch does not say the owner must act: %s" % remedy[:120]
    if re.search(r"\bgit\b", remedy):
        return False, "the refusal for a rewritten branch names git, which prints a command: %s" % remedy[:120]
    return True, "the refusal for a rewritten branch says the owner must reword, and prints no git command"


LOG_CHECKS = LOG_CHECKS + ((RR_BELOW_CONTROL_LABEL, rr_below_control_case), (RR_MERGE_TIP_LABEL, rr_merge_tip_remedy_case),
                           (RR_MERGE_BELOW_LABEL, rr_merge_below_remedy_case), (RR_REWRITTEN_LABEL, rr_rewritten_remedy_case))
