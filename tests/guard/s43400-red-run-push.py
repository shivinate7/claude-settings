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
        filled = span.replace("<sha>", short)
        filled = re.sub(r"Red-run: \.\.\.", "Red-run: none: x", filled)
        filled = re.sub(r"<[^>]*>", "s", filled)
        got, reason = decide(_rr_case(filled, RR_BELOW))
        if got != "allow":
            return False, "the printed command `%s`, run in the fixture, is %s, want allow: %s" % (
                filled, got, reason[:100])
    return True, "the refusal prints a git command that names the commit below the tip, and each one is allowed"


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
