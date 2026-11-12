# section 22670
FAMILY = "push-batch-held"  # the family the cases below run in

# Rule push-batch-held (decision batch-freeze-lane-set). A non-forced push to a lane's branch is refused while that
# branch's remote tip sits inside the head of an open, ready pull request on the default base, from a different head
# branch: a running batch was built from that head, so a moved head breaks its confirm. The reads are one open pull
# request list, and one compare of `<tip>...<head>` per ready pull request, on a push that reaches the rule only. A read
# that fails allows the push and logs push-batch-unread.
#
# Each lane here is cut from origin/main, and its remote tip is its remote-tracking ref. A local commit that is not
# pushed makes the local head differ from the tip. The fake keys every compare by the tip's real sha, so a guard that
# compares any other sha reads "diverged", and allows.
PUSH_BATCH_RULE = "push-batch-held"
PUSH_BATCH_UNREAD = "push-batch-unread"
# The deny names the rule, the hold and the remedy (wait, drop the lane, or a new lane). It names no forced push,
# no hook skip and no delete.
BH_CARRIES = (("held", "holds"), "batch", ("wait", "drop"), "new lane")
BH_LACKS = ("--force", "force-with-lease", "--no-verify", "--delete")

BH_HELD = os.path.join(ROOT, "bhheldrepo")                # lane-held: its tip held by pull request 2, one local commit ahead
BH_HELD_GH = os.path.join(ROOT, "bhheldgh")               # the open list, and the compare of the tip reads ahead
BH_HELD_BROKEN_GH = os.path.join(ROOT, "bhheldbrokengh")  # the open list cannot be read
BH_HELD_SERVER_GH = os.path.join(ROOT, "bhheldservergh")  # the compare of the tip fails with a server error
BH_IDENT = os.path.join(ROOT, "bhidentrepo")              # lane-ident: its batch head is identical to the tip
BH_IDENT_GH = os.path.join(ROOT, "bhidentgh")
BH_SECOND = os.path.join(ROOT, "bhsecondrepo")            # lane-second: the second ready pull request holds the tip
BH_SECOND_GH = os.path.join(ROOT, "bhsecondgh")
BH_DRAFT = os.path.join(ROOT, "bhdraftrepo")              # lane-draft: its only holder is a draft
BH_DRAFT_GH = os.path.join(ROOT, "bhdraftgh")
BH_EMPTY_GH = os.path.join(ROOT, "bhemptygh")             # no open pull request at all, beside lane-draft
BH_BASE = os.path.join(ROOT, "bhbaserepo")                # lane-base: its holder is on another base
BH_BASE_GH = os.path.join(ROOT, "bhbasegh")
BH_SAME = os.path.join(ROOT, "bhsamerepo")                # lane-same: local head equals its tip
BH_SAME_GH = os.path.join(ROOT, "bhsamegh")
BH_INT = os.path.join(ROOT, "bhintrepo")                  # integration/b68: a branch that is its own pull request's head
BH_INT_GH = os.path.join(ROOT, "bhintgh")
BH_NEW = os.path.join(ROOT, "bhnewrepo")                  # lane-new: pushed nowhere, so it has no remote tip
BH_NEW_GH = os.path.join(ROOT, "bhnewgh")
BH_FULL = os.path.join(ROOT, "bhfullrepo")                # lane-full: its holder is past the first page of the open list
BH_FULL_GH = os.path.join(ROOT, "bhfullgh")
BH_COUNT = os.path.join(ROOT, "bhcountrepo")              # lane-count: two ready pull requests, neither holds its tip
BH_COUNT_GH = os.path.join(ROOT, "bhcountgh")
BH_MERGED = os.path.join(ROOT, "bhmergedrepo")            # lane-merged: its tip is an ancestor of origin/main, and a ready pull request holds it
BH_MERGED_GH = os.path.join(ROOT, "bhmergedgh")
BH_AGENT = os.path.join(ROOT, "bhagentrepo")              # the lane named in the agent-worktree form (see the literal below), its tip held
BH_AGENT_GH = os.path.join(ROOT, "bhagentgh")
BH_NONE = os.path.join(ROOT, "bhnonerepo")                # lane-none: push.default=matching, so a bare push reads no destination
BH_NONE_GH = os.path.join(ROOT, "bhnonegh")
BH_NODEF = os.path.join(ROOT, "bhnodefrepo")              # lane-nodef: its default-branch read cannot answer (a git that fails --git-dir)
BH_NODEF_GH = os.path.join(ROOT, "bhnodefgh")
BH_PUSHREMOTE = os.path.join(ROOT, "bhpushremoterepo")    # lane-pushremote: branch.<cur>.pushRemote names `other`, which holds the tip
BH_PUSHREMOTE_GH = os.path.join(ROOT, "bhpushremotegh")
BH_PUSHDEF = os.path.join(ROOT, "bhpushdefrepo")          # lane-pushdef: remote.pushDefault names `other`, which holds the tip
BH_PUSHDEF_GH = os.path.join(ROOT, "bhpushdefgh")
BH_BRANCHREMOTE = os.path.join(ROOT, "bhbranchremoterepo")  # lane-branchremote: branch.<cur>.remote names `other`, which holds the tip
BH_BRANCHREMOTE_GH = os.path.join(ROOT, "bhbranchremotegh")
BH_FALLBACK = os.path.join(ROOT, "bhfallbackrepo")        # lane-fallback: no pushRemote, pushDefault or upstream, so origin holds the tip
BH_FALLBACK_GH = os.path.join(ROOT, "bhfallbackgh")
BH_OTHERFREE = os.path.join(ROOT, "bhotherfreerepo")      # lane-otherfree: pushRemote names `other`, which holds nothing
BH_OTHERFREE_GH = os.path.join(ROOT, "bhotherfreegh")


def _bh_commit(where, name, text):
    write(os.path.join(where, name), text)
    run_vcs(where, "add", "-A")
    commit = run_vcs(where, *IDENT, "commit", "-q", "-m", "push-batch fixture: " + name)
    if commit.returncode != 0:
        sys.exit("fixture setup failed in build_fixtures: a commit in %r failed. stderr: %s"
                 % (where, commit.stderr.strip()))


def _bh_head(where):
    return run_vcs(where, "rev-parse", "HEAD").stdout.strip()


def _bh_lane(where, lane, pushed=True, local_ahead=True, merged=False):
    """A checkout on `lane`, cut from origin/main, with one commit. When `pushed`, origin/<lane> holds that commit and
    the lane's upstream is set. When `local_ahead`, one more commit is not pushed. When `merged`, origin/main moves one
    commit past that first commit, so the tip is an ancestor of origin/main and not equal to it. Returns (the first
    commit, the local head), each read back with git, so no case judges a fixture that lacks its state."""
    make_repo(where, {"base.txt": "base\n"})
    run_vcs(where, "remote", "add", "origin", PUSHREMOTE)
    run_vcs(where, "update-ref", "refs/remotes/origin/main", "HEAD")
    run_vcs(where, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    run_vcs(where, "config", "push.default", "simple")
    run_vcs(where, "checkout", "-q", "-b", lane)
    _bh_commit(where, "lane.txt", "pushed\n")
    first = _bh_head(where)
    if pushed:
        run_vcs(where, "update-ref", "refs/remotes/origin/" + lane, "HEAD")
        run_vcs(where, "branch", "--set-upstream-to=origin/" + lane, lane)
    if merged:
        past = run_vcs(where, *IDENT, "commit-tree", first + "^{tree}", "-p", first, "-m", "main past the merged tip")
        if past.returncode != 0:
            sys.exit("fixture setup failed in build_fixtures: %r could not commit past %s" % (where, first))
        run_vcs(where, "update-ref", "refs/remotes/origin/main", past.stdout.strip())
    if local_ahead:
        _bh_commit(where, "lane.txt", "not pushed\n")
    remote = run_vcs(where, "rev-parse", "-q", "--verify", "refs/remotes/origin/" + lane)
    if (remote.returncode == 0) != pushed or (pushed and remote.stdout.strip() != first):
        sys.exit("fixture setup failed in build_fixtures: %r needs origin/%s at its first commit, pushed=%s"
                 % (where, lane, pushed))
    if (_bh_head(where) != first) != local_ahead:
        sys.exit("fixture setup failed in build_fixtures: %r needs local_ahead=%s" % (where, local_ahead))
    if merged and (run_vcs(where, "merge-base", "--is-ancestor", first, "refs/remotes/origin/main").returncode != 0
                   or run_vcs(where, "rev-parse", "refs/remotes/origin/main").stdout.strip() == first):
        sys.exit("fixture setup failed in build_fixtures: %r needs its tip an ancestor of origin/main, not equal" % where)
    if pushed and run_vcs(where, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip() \
            != "origin/" + lane:
        sys.exit("fixture setup failed in build_fixtures: %r needs upstream origin/%s" % (where, lane))
    return first, _bh_head(where)


def _bh_pr(number, head, ref, base="main", draft=False):
    """One open pull request for the fake tool: its head sha and branch, its base, and its draft flag."""
    return {"number": number, "head": head, "ref": ref, "base": base, "draft": draft, "checks": [], "runs": []}


def _bh_fake(folder, key, rows, statuses=None, broken=False, own_open=True):
    """A counted fake pull request tool at `folder`, whose other open pull requests are `rows`. Its own pull request
    is a draft, so it is no candidate; `own_open=False` closes it instead, so the open list holds only `rows`. `statuses`
    maps a row's head sha to the status of the compare `<key>...<head>`; a head with no entry compares diverged, as the
    fake answers every pair it does not list."""
    own = {"base": {"ref": "main", "repo": {"default_branch": "main"}}}
    own.update({"draft": True} if own_open else {"state": "closed"})
    make_fake_gh(folder, "main", others=rows, broken=broken, pr=own,
                 compares={key + "..." + head: status for head, status in (statuses or {}).items()},
                 count_file=os.path.join(folder, ARCHIVE_CALLS))


def _build_bh_held():
    tip, _ = _bh_lane(BH_HELD, "lane-held")
    rows = [_bh_pr(2, "pr-two-head", "integration/b68")]
    _bh_fake(BH_HELD_GH, tip, rows, {"pr-two-head": "ahead"})
    _bh_fake(BH_HELD_BROKEN_GH, tip, rows, {"pr-two-head": "ahead"}, broken=True)
    _bh_fake(BH_HELD_SERVER_GH, tip, rows, {"pr-two-head": "server"})


def _build_bh_ident():
    tip, _ = _bh_lane(BH_IDENT, "lane-ident")
    _bh_fake(BH_IDENT_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "identical"})


def _build_bh_second():
    tip, _ = _bh_lane(BH_SECOND, "lane-second")
    rows = [_bh_pr(2, "pr-two-head", "integration/b68"), _bh_pr(3, "pr-three-head", "integration/b69")]
    _bh_fake(BH_SECOND_GH, tip, rows, {"pr-three-head": "ahead"})


def _build_bh_draft():
    tip, _ = _bh_lane(BH_DRAFT, "lane-draft")
    _bh_fake(BH_DRAFT_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68", draft=True)], {"pr-two-head": "ahead"})
    _bh_fake(BH_EMPTY_GH, tip, [], {}, own_open=False)


def _build_bh_base():
    tip, _ = _bh_lane(BH_BASE, "lane-base")
    _bh_fake(BH_BASE_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68", base="release-1")], {"pr-two-head": "ahead"})


def _build_bh_same():
    tip, _ = _bh_lane(BH_SAME, "lane-same", local_ahead=False)
    _bh_fake(BH_SAME_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_int():
    tip, _ = _bh_lane(BH_INT, "integration/b68")
    _bh_fake(BH_INT_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_new():
    _, head = _bh_lane(BH_NEW, "lane-new", pushed=False, local_ahead=False)
    # The compare is keyed by the local head, not by a remote tip (there is none). A guard that judged the local head would deny.
    _bh_fake(BH_NEW_GH, head, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_full():
    tip, _ = _bh_lane(BH_FULL, "lane-full")
    # The fake pages its open list at 100 rows, and its own draft is one of them: 100 filler rows put the holder on page two.
    rows = [_bh_pr(n, "pr-fill-%d" % n, "integration/fill-%d" % n, draft=True) for n in range(100, 200)]
    rows.append(_bh_pr(300, "pr-two-head", "integration/b68"))
    _bh_fake(BH_FULL_GH, tip, rows, {"pr-two-head": "ahead"})


def _build_bh_count():
    tip, _ = _bh_lane(BH_COUNT, "lane-count")
    rows = [_bh_pr(2, "pr-two-head", "integration/b68"), _bh_pr(3, "pr-three-head", "integration/b69")]
    _bh_fake(BH_COUNT_GH, tip, rows)


def _build_bh_merged():
    tip, _ = _bh_lane(BH_MERGED, "lane-merged", merged=True)
    _bh_fake(BH_MERGED_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_agent():
    tip, _ = _bh_lane(BH_AGENT, "worktree-agent-5e6f7a8b")
    _bh_fake(BH_AGENT_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_none():
    tip, _ = _bh_lane(BH_NONE, "lane-none")
    run_vcs(BH_NONE, "config", "push.default", "matching")
    if run_vcs(BH_NONE, "config", "--get", "push.default").stdout.strip() != "matching":
        sys.exit("fixture setup failed in build_fixtures: %r needs push.default=matching" % BH_NONE)
    _bh_fake(BH_NONE_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _bh_blind_defaults_git(folder):
    """A `git` on PATH for this folder. Its `rev-parse --git-dir` fails, the one read the default-branch lookup makes,
    and every other call runs the real git by its own path. POSIX only: a CreateProcess call never reads a .cmd stand-in."""
    real = shutil.which("git", path=os.environ.get("PATH"))
    if not real:
        sys.exit("fixture setup failed in build_fixtures: no git on this process's PATH for the default-branch stand-in")
    script = os.path.join(folder, "git")
    write(script, "#!/bin/sh\n"
                  "if [ \"$#\" -eq 4 ] && [ \"$3\" = \"rev-parse\" ] && [ \"$4\" = \"--git-dir\" ]; then\n"
                  "  echo 'blind git: no git dir' >&2\n"
                  "  exit 128\n"
                  "fi\n"
                  "exec \"%s\" \"$@\"\n" % real)
    os.chmod(script, 0o755)


def _build_bh_nodef():
    tip, _ = _bh_lane(BH_NODEF, "lane-nodef")
    _bh_fake(BH_NODEF_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})
    _bh_blind_defaults_git(BH_NODEF_GH)


def _bh_other_remote(where, lane, configs):
    """A lane cut from origin/main with one unpushed commit. origin/<lane> is absent, and remote `other` holds the tip.
    `configs` are the (key, value) pairs that point a bare push at a remote. Each is read back, so no case judges a
    fixture that lacks its state. Returns the tip."""
    tip, _ = _bh_lane(where, lane, pushed=False)
    run_vcs(where, "remote", "add", "other", PUSHREMOTE)
    run_vcs(where, "update-ref", "refs/remotes/other/" + lane, tip)
    for key, value in configs:
        run_vcs(where, "config", key, value)
    if run_vcs(where, "rev-parse", "-q", "--verify", "refs/remotes/origin/" + lane).returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: %r must have no origin/%s" % (where, lane))
    if run_vcs(where, "rev-parse", "refs/remotes/other/" + lane).stdout.strip() != tip:
        sys.exit("fixture setup failed in build_fixtures: %r needs other/%s at its tip" % (where, lane))
    for key, value in configs:
        if run_vcs(where, "config", "--get", key).stdout.strip() != value:
            sys.exit("fixture setup failed in build_fixtures: %r needs %s=%s" % (where, key, value))
    return tip


def _build_bh_pushremote():
    tip = _bh_other_remote(BH_PUSHREMOTE, "lane-pushremote", [
        ("branch.lane-pushremote.pushRemote", "other"),    # link 1: the one git reads first, so it holds
        ("remote.pushDefault", "origin"),                  # below it, a remote that holds nothing
        ("branch.lane-pushremote.remote", "origin"),
        ("branch.lane-pushremote.merge", "refs/heads/lane-pushremote")])
    _bh_fake(BH_PUSHREMOTE_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_pushdef():
    tip = _bh_other_remote(BH_PUSHDEF, "lane-pushdef", [
        ("remote.pushDefault", "other"),                   # link 2: no pushRemote, so pushDefault holds
        ("branch.lane-pushdef.remote", "origin"),          # below it, a remote that holds nothing
        ("branch.lane-pushdef.merge", "refs/heads/lane-pushdef")])
    _bh_fake(BH_PUSHDEF_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_branchremote():
    tip = _bh_other_remote(BH_BRANCHREMOTE, "lane-branchremote", [
        ("branch.lane-branchremote.remote", "other"),      # link 3: the upstream's remote, with no pushRemote or pushDefault
        ("branch.lane-branchremote.merge", "refs/heads/lane-branchremote")])
    _bh_fake(BH_BRANCHREMOTE_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_fallback():
    tip, _ = _bh_lane(BH_FALLBACK, "lane-fallback")
    run_vcs(BH_FALLBACK, "config", "--unset", "branch.lane-fallback.remote")
    run_vcs(BH_FALLBACK, "config", "--unset", "branch.lane-fallback.merge")
    if run_vcs(BH_FALLBACK, "config", "--get", "branch.lane-fallback.remote").returncode == 0:
        sys.exit("fixture setup failed in build_fixtures: %r must have no upstream remote" % BH_FALLBACK)
    _bh_fake(BH_FALLBACK_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")], {"pr-two-head": "ahead"})


def _build_bh_otherfree():
    tip = _bh_other_remote(BH_OTHERFREE, "lane-otherfree", [("branch.lane-otherfree.pushRemote", "other")])
    # No status is listed for the holder, so its compare against `other`'s tip reads diverged: nothing is held.
    _bh_fake(BH_OTHERFREE_GH, tip, [_bh_pr(2, "pr-two-head", "integration/b68")])


lazy_fixture([BH_HELD, BH_HELD_GH, BH_HELD_BROKEN_GH, BH_HELD_SERVER_GH], _build_bh_held)
lazy_fixture([BH_IDENT, BH_IDENT_GH], _build_bh_ident)
lazy_fixture([BH_SECOND, BH_SECOND_GH], _build_bh_second)
lazy_fixture([BH_DRAFT, BH_DRAFT_GH, BH_EMPTY_GH], _build_bh_draft)
lazy_fixture([BH_BASE, BH_BASE_GH], _build_bh_base)
lazy_fixture([BH_SAME, BH_SAME_GH], _build_bh_same)
lazy_fixture([BH_INT, BH_INT_GH], _build_bh_int)
lazy_fixture([BH_NEW, BH_NEW_GH], _build_bh_new)
lazy_fixture([BH_FULL, BH_FULL_GH], _build_bh_full)
lazy_fixture([BH_COUNT, BH_COUNT_GH], _build_bh_count)
lazy_fixture([BH_MERGED, BH_MERGED_GH], _build_bh_merged)
lazy_fixture([BH_AGENT, BH_AGENT_GH], _build_bh_agent)
lazy_fixture([BH_NONE, BH_NONE_GH], _build_bh_none)
lazy_fixture([BH_NODEF, BH_NODEF_GH], _build_bh_nodef)
lazy_fixture([BH_PUSHREMOTE, BH_PUSHREMOTE_GH], _build_bh_pushremote)
lazy_fixture([BH_PUSHDEF, BH_PUSHDEF_GH], _build_bh_pushdef)
lazy_fixture([BH_BRANCHREMOTE, BH_BRANCHREMOTE_GH], _build_bh_branchremote)
lazy_fixture([BH_FALLBACK, BH_FALLBACK_GH], _build_bh_fallback)
lazy_fixture([BH_OTHERFREE, BH_OTHERFREE_GH], _build_bh_otherfree)


def _bh_env(fake):
    """The PATH a case's guard runs on: the counted fake first, then the interpreter's and git's folders."""
    return fake + os.pathsep + PY_PATH + os.pathsep + GIT_PATH


def _bh_push(name, tail, expected, fake, cwd, **kw):
    """One `git push` case, judged with its lane's fake pull request tool first on PATH."""
    sh("push-batch: " + name, VCS + " push " + tail, expected, cwd=cwd, env_path=_bh_env(fake), **kw)


BH_REFUSE = {"rule": PUSH_BATCH_RULE, "carries": BH_CARRIES, "lacks": BH_LACKS}
# DENY, rule push-batch-held. Each lane's tip is held by a ready pull request on main, so each push is refused.
_bh_push("refused, an explicit HEAD refspec to a held lane", "origin HEAD:lane-held", "deny", BH_HELD_GH, BH_HELD,
         **BH_REFUSE)
_bh_push("refused, a colon-less refspec that names the held lane", "origin lane-held", "deny", BH_HELD_GH, BH_HELD,
         **BH_REFUSE)
_bh_push("refused, the refs/heads spelling of the held lane", "origin HEAD:refs/heads/lane-held", "deny", BH_HELD_GH,
         BH_HELD, **BH_REFUSE)
_bh_push("refused, a bare push of the held lane under its upstream", "", "deny", BH_HELD_GH, BH_HELD, **BH_REFUSE)
_bh_push("refused, -u HEAD to the held lane", "-u origin HEAD", "deny", BH_HELD_GH, BH_HELD, **BH_REFUSE)
sh("push-batch: refused, a held push chained after an echo", "echo ok && " + VCS + " push origin HEAD:lane-held",
   "deny", cwd=BH_HELD, env_path=_bh_env(BH_HELD_GH), **BH_REFUSE)
_bh_push("refused, a lane whose tip a second ready pull request holds", "origin HEAD:lane-second", "deny",
         BH_SECOND_GH, BH_SECOND, **BH_REFUSE)
_bh_push("refused, a lane whose holder is past the first page of the open list", "origin HEAD:lane-full", "deny",
         BH_FULL_GH, BH_FULL, **BH_REFUSE)
_bh_push("refused, a lane whose batch head is identical to its tip", "origin HEAD:lane-ident", "deny",
         BH_IDENT_GH, BH_IDENT, **BH_REFUSE)
# The agent-branch ask (rule push-agent-branch) names this lane too. The batch deny comes first, so it wins.
_bh_push("refused, an agent-named lane held by a ready pull request: the deny wins over the agent-branch ask",
         "origin HEAD:worktree-agent-5e6f7a8b", "deny", BH_AGENT_GH, BH_AGENT, **BH_REFUSE)

# CONTROL: each is an allow or an ask the rule must leave unchanged, and each names its rule.
_bh_push("control, a push that moves nothing to a held lane is silent", "origin HEAD:lane-same", "allow",
         BH_SAME_GH, BH_SAME, silent=True)
_bh_push("control, a bare push that moves nothing to a held lane is silent", "", "allow", BH_SAME_GH, BH_SAME,
         silent=True)
_bh_push("control, a lane with no remote tip is silent", "origin HEAD:lane-new", "allow", BH_NEW_GH, BH_NEW,
         silent=True)
_bh_push("control, a holder on another base is silent", "origin HEAD:lane-base", "allow", BH_BASE_GH, BH_BASE,
         silent=True)
_bh_push("control, a holder that is a draft is silent", "origin HEAD:lane-draft", "allow", BH_DRAFT_GH, BH_DRAFT,
         silent=True)
_bh_push("control, an empty open list is silent", "origin HEAD:lane-draft", "allow", BH_EMPTY_GH, BH_DRAFT,
         silent=True)
_bh_push("control, a push to the integration branch itself is silent", "origin HEAD:integration/b68", "allow",
         BH_INT_GH, BH_INT, silent=True)
_bh_push("control, two ready pull requests that hold no tip are silent", "origin HEAD:lane-count", "allow",
         BH_COUNT_GH, BH_COUNT, silent=True)
_bh_push("control, a dry run into a held lane is silent", "--dry-run origin HEAD:lane-held", "allow", BH_HELD_GH,
         BH_HELD, silent=True)
_bh_push("control, a push of main asks push-main", "origin main", "ask", BH_HELD_GH, BH_HELD,
         rule=PUSH_MAIN_RULE)
_bh_push("control, a forced push to a held lane keeps its force-push deny", "--force origin HEAD:lane-held", "deny",
         BH_HELD_GH, BH_HELD, rule="force-push", lacks=PUSH_BATCH_RULE)
sh("push-batch: control, a quoted push into a held lane is silent", 'echo "' + VCS + ' push origin HEAD:lane-held"',
   "allow", cwd=BH_HELD, env_path=_bh_env(BH_HELD_GH), silent=True)


# A held lane moved in the same push as a delete, and --all naming a held lane branch, are refused. A literal name and
# -u alone stay refused. A delete-only push and --all with no held tip keep their verdicts.
_bh_push("refused, a held lane moved in the same push as a delete", "origin HEAD:lane-held :old-zz", "deny",
         BH_HELD_GH, BH_HELD, **BH_REFUSE)
_bh_push("control, a delete-only push is silent", "origin :old-zz", "allow", BH_HELD_GH, BH_HELD, silent=True)
_bh_push("refused, --all with a held lane branch", "--all origin", "deny", BH_HELD_GH, BH_HELD, **BH_REFUSE)
_bh_push("control, --all with no held tip is silent", "--all origin", "allow", BH_COUNT_GH, BH_COUNT, silent=True)
_bh_push("refused, a literal destination name", "origin HEAD:lane-held", "deny", BH_HELD_GH, BH_HELD,
         **BH_REFUSE)
_bh_push("refused, -u with a literal destination into a held lane", "-u origin HEAD:lane-held", "deny", BH_HELD_GH,
         BH_HELD, **BH_REFUSE)


# The cost, pinned on the counted fake: one open-list call, then one compare per ready pull request, and nothing for a
# push of main or a dry run. ARCHIVE_CALLS is the counted fake's log (gh_calls_taken reads and clears it).
def _bh_gh_calls(folder, command, cwd):
    """The guard's verdict on one Bash command, and the gh calls its fake logged for that command."""
    gh_calls_taken(folder)
    decision, reason = decide({"raw": None, "tool": "Bash", "cwd": cwd, "session": None,
                               "env_path": _bh_env(folder), "tool_input": {"command": command}})
    return decision, reason, gh_calls_taken(folder)


def _bh_kinds(calls):
    """Each gh call's kind: the open list ("pulls"), a compare, or other. Sorted, so the order of reads does not count."""
    return sorted("pulls" if "pulls" in call else "compare" if "compare" in call else "other" for call in calls)


def _bh_cost_case(fake, lane_cwd, command, want_decision, want_calls, label):
    """The verdict is want_decision, and the gh calls are want_calls, as kinds (see _bh_kinds)."""
    decision, reason, calls = _bh_gh_calls(fake, VCS + " " + command, lane_cwd)
    if decision != want_decision:
        return False, "%s: %s, not %s (%s)" % (label, decision, want_decision, reason[:90])
    if _bh_kinds(calls) != sorted(want_calls):
        return False, "%s: gh calls %r wanted, %r made" % (label, sorted(want_calls), _bh_kinds(calls))
    return True, label


def bh_draft_only_cost_case():
    return _bh_cost_case(BH_DRAFT_GH, BH_DRAFT, "push origin HEAD:lane-draft", "allow", ["pulls"],
                         "a holder that is a draft costs the open list alone, one gh call")


def bh_empty_list_cost_case():
    return _bh_cost_case(BH_EMPTY_GH, BH_DRAFT, "push origin HEAD:lane-draft", "allow", ["pulls"],
                         "an empty open list costs one gh call, the list")


def bh_two_ready_cost_case():
    return _bh_cost_case(BH_COUNT_GH, BH_COUNT, "push origin HEAD:lane-count", "allow",
                         ["pulls", "compare", "compare"],
                         "two ready pull requests that hold no tip cost the list and one compare each, 3 gh calls")


def bh_main_push_cost_case():
    return _bh_cost_case(BH_HELD_GH, BH_HELD, "push origin main", "ask", [],
                         "control, a push of main makes no gh call")


def bh_dry_run_cost_case():
    return _bh_cost_case(BH_HELD_GH, BH_HELD, "push --dry-run origin HEAD:lane-held", "allow", [],
                         "control, a dry run makes no gh call")


def bh_unread_case(config_name, fake, label, tail="origin HEAD:lane-held", cwd=BH_HELD):
    """A push the batch read cannot judge is allowed, and its log holds exactly one push-batch-unread line. The log is
    the signal: an unread read that allowed silently would be a pass nobody can see. `tail` is the push's arguments,
    `cwd` the checkout it runs in."""
    def check():
        config = os.path.join(ROOT, config_name)
        os.makedirs(config, exist_ok=True)
        log = os.path.join(config, "guard.log")
        if os.path.exists(log):
            os.remove(log)
        decision, reason = decide({"raw": None, "tool": "Bash", "cwd": cwd, "session": None,
                                   "env_path": _bh_env(fake), "config": config,
                                   "tool_input": {"command": VCS + " push " + tail}})
        if decision != "allow":
            return False, "%s: the push was %s, not allowed (%s)" % (label, decision, reason[:90])
        text = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
        lines = [line for line in text.splitlines() if PUSH_BATCH_UNREAD in line]
        if not lines:
            return False, "%s: the allow left no %s line in guard.log" % (label, PUSH_BATCH_UNREAD)
        if len(lines) > 1:
            return False, "%s: the allow left %d %s lines in guard.log, one wanted" % (label, len(lines), PUSH_BATCH_UNREAD)
        return True, "%s: allowed, and logged as %s" % (label, PUSH_BATCH_UNREAD)
    return check


def bh_merged_tip_cost_case():
    return _bh_cost_case(BH_MERGED_GH, BH_MERGED, "push origin HEAD:lane-merged", "allow", [],
                         "a tip already merged into origin/main is allowed, with no gh call")


def bh_unmerged_cost_case():
    return _bh_cost_case(BH_HELD_GH, BH_HELD, "push origin HEAD:lane-held", "deny", ["pulls", "compare"],
                         "an unmerged held tip is refused, with one list and one compare")


def bh_short_dry_run_cost_case():
    return _bh_cost_case(BH_HELD_GH, BH_HELD, "push -nu origin HEAD:lane-held", "allow", [],
                         "a dry run in a short-flag cluster (-nu) is allowed, with no gh call")


LOG_CHECKS_EXTRA.append(("push-batch-held: a holder that is a draft costs the open list alone, one gh call",
                         bh_draft_only_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: an empty open list costs one gh call, the list",
                         bh_empty_list_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: two ready pull requests that hold no tip cost the list and one compare each",
                         bh_two_ready_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: control, a push of main makes no gh call", bh_main_push_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: control, a dry run makes no gh call", bh_dry_run_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: an open list that cannot be read allows the push, and logs push-batch-unread",
                         bh_unread_case("bhunreadlist", BH_HELD_BROKEN_GH, "the open list cannot be read")))
LOG_CHECKS_EXTRA.append(("push-batch-held: a compare that cannot be read allows the push, and logs push-batch-unread",
                         bh_unread_case("bhunreadcmp", BH_HELD_SERVER_GH, "the compare cannot be read")))
LOG_CHECKS_EXTRA.append(("push-batch-held: a tip already merged into origin/main is allowed, with no gh call",
                         bh_merged_tip_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: an unmerged held tip is refused, with one list and one compare",
                         bh_unmerged_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: a dry run in a short-flag cluster (-nu) is allowed, with no gh call",
                         bh_short_dry_run_cost_case))
LOG_CHECKS_EXTRA.append(("push-batch-held: a destination name the guard cannot read is allowed, and logs push-batch-unread",
                         bh_unread_case("bhunreaddollar", BH_HELD_GH, "the destination name cannot be read",
                                        tail="origin HEAD:$LANEB")))

# A push the batch read cannot judge is allowed, and logs one push-batch-unread line. Each form is one way the read
# gives up: a glob destination no read names, a destination that reads as None (push.default=matching), an unreadable
# `$X:` source, and a default-branch read that cannot answer.
LOG_CHECKS_EXTRA.append(("push-batch-held: a glob destination is allowed, and logs push-batch-unread",
                         bh_unread_case("bhunreadglob", BH_HELD_GH, "a glob destination",
                                        tail="origin refs/heads/*:refs/heads/*")))
LOG_CHECKS_EXTRA.append(("push-batch-held: a bare push whose destination reads as none is allowed, and logs push-batch-unread",
                         bh_unread_case("bhunreadnone", BH_NONE_GH, "a bare push under push.default=matching",
                                        tail="", cwd=BH_NONE)))
LOG_CHECKS_EXTRA.append(("push-batch-held: an unreadable $X source is allowed, and logs push-batch-unread",
                         bh_unread_case("bhunreadsrc", BH_HELD_GH, "an unreadable source", tail="origin $X:lane-held")))
NODEF_LABEL = "push-batch-held: a default-branch read that cannot answer is allowed, and logs push-batch-unread"
if os.name == "nt":
    skip_case(NODEF_LABEL, NO_STAND_IN)
else:
    LOG_CHECKS_EXTRA.append((NODEF_LABEL, bh_unread_case("bhunreaddefaults", BH_NODEF_GH,
                                                         "a default-branch read that cannot answer",
                                                         tail="origin HEAD:lane-nodef", cwd=BH_NODEF)))

# A bare push names no remote, so git picks one in this order: branch.<cur>.pushRemote, remote.pushDefault,
# branch.<cur>.remote, else origin. Each case holds the tip on one link and on no link above it; the lower links hold
# nothing, so a fix that reads them out of order still fails here.
_bh_push("refused, a bare push whose branch pushRemote names a remote that holds the tip", "", "deny",
         BH_PUSHREMOTE_GH, BH_PUSHREMOTE, **BH_REFUSE)
_bh_push("refused, a bare push whose remote.pushDefault names a remote that holds the tip", "", "deny",
         BH_PUSHDEF_GH, BH_PUSHDEF, **BH_REFUSE)
_bh_push("refused, a bare push whose upstream remote holds the tip", "", "deny", BH_BRANCHREMOTE_GH, BH_BRANCHREMOTE,
         **BH_REFUSE)
_bh_push("refused, a bare push with no remote config reads origin, which holds the tip", "", "deny",
         BH_FALLBACK_GH, BH_FALLBACK, **BH_REFUSE)
_bh_push("control, a bare push whose pushRemote holds no tip is silent", "", "allow", BH_OTHERFREE_GH, BH_OTHERFREE,
         silent=True)

# A delete part of a push is no move (decision text), so deleting a held lane is silent.
_bh_push("control, a delete of a held lane is silent, since a delete part of a push is no move", "origin :lane-held",
         "allow", BH_HELD_GH, BH_HELD, silent=True)
