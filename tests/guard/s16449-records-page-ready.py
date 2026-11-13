# section 16449
FAMILY = "records-page-ready"
#
# `records-page-ready`. Marking a pull request ready is refused while its head holds a stale records page: the merge
# tool rebuilds the page only on a draft, before the branch goes ready (decision records-index-at-merge). The rule
# asks ready_page_state (merge/merge.py) about the head. A read that cannot run is refused unknown.
#
# THE FIXTURE. One bare origin with real branches, a checkout on main (the folder a case runs in), a checkout on
# feat-stale (the no-selector form reads the folder's branch), and a repo with no stamp file (not a merge-tool repo).
# Each case's fake gh answers for its own pull request with the head's real sha. The fixture assumes the base's
# .github/stamp.json names the default branch, read from origin/<base>, and that the page is what lint/hook_catalog.py writes.
RPR = os.path.join(ROOT, "readypage")
RPR_ORIGIN = os.path.join(RPR, "origin.git")
RPR_SEED = os.path.join(RPR, "seed")
RPR_REPO = os.path.join(RPR, "clone")          # the folder most cases run in: on main
RPR_NOSEL = os.path.join(RPR, "clone-feat")    # the same origin, on feat-stale: the no-selector form
RPR_PLAIN = os.path.join(RPR, "plain")         # a repo with no .github/stamp.json: it does not use the merge tool
RPR_GEN = os.path.join(REPO, "lint", "hook_catalog.py")
RPR_COUNT = os.path.join(RPR, "gh-calls.log")  # the count fake's log: one line per gh call
RPR_RULE = "records-page-ready"
RPR_CARRY = ("Return #12 to draft",)           # the stale remedy's first step (merge.stale_page_remedy)
RPR_DEBT = "# Gap one\n\n- **What.** The check misses one case.\n- **Where.** x\n- **Decision.** none\n- **Retire.** y\n"
RPR_STAMP = json.dumps({"defaultBranch": "main", "kinds": [],
                        "merge": {"method": "merge", "deadlineMinutes": 5, "afterMerge": [], "deleteBranch": True}})
GHREADY_STALE = os.path.join(RPR, "gh-stale")      # feat-stale, base main: a debt with no page
GHREADY_NAMED = os.path.join(RPR, "gh-named")      # the same, and every call must name repos/y/x
GHREADY_CURRENT = os.path.join(RPR, "gh-current")  # feat-current: a debt and the page the generator writes
GHREADY_CLAIM = os.path.join(RPR, "gh-claim")      # feat-claim: its head commit holds a Record-claim
GHREADY_BEHIND = os.path.join(RPR, "gh-behind")    # feat-behind: cut before main moved on
GHREADY_DEV = os.path.join(RPR, "gh-dev")          # feat-dev: base dev, not the default branch
GHREADY_EMPTY = os.path.join(RPR, "gh-empty")      # feat-empty: no record in the tree
GHREADY_BAD = os.path.join(RPR, "gh-bad")          # feat-bad: a record the generator refuses
GHREADY_HANG = os.path.join(RPR, "gh-hang")        # feat-stale, every answer delayed past any read deadline
GHREADY_COUNT = os.path.join(RPR, "gh-count")      # feat-stale, one log line per gh call
GHREADY_PLAIN = os.path.join(RPR, "gh-plain")      # feat-stale, for the repo that does not use the merge tool
RPR_SHALLOW = os.path.join(RPR, "shallow")         # a shallow clone of origin: it holds main's tip and cuts feat-behind's path to it
RPR_SHALLOW_WT = os.path.join(RPR, "shallow-wt")   # a worktree of that clone at feat-behind, for the scope read in the fixture
GHREADY_SHALLOW = os.path.join(RPR, "gh-shallow")  # feat-behind in RPR_SHALLOW: the ancestry is unknown, so the ready mark is refused
GHREADY_SHALLOW_NAMED = os.path.join(RPR, "gh-shallow-named")  # the same, and every call must name repos/y/x
RPR_UNKNOWN_LACKS = ("--confirm", "merge <pr>", "merge 12")  # the unknown reason names no merge command: it says to retry, or to draft first


def _rpr_git(where, *args):
    done = run_vcs(where, *IDENT, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in the records-page-ready fixtures: %s %s in %r: %s"
                 % (VCS, " ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def _rpr_need(ok, what):
    if not ok:
        sys.exit("fixture setup failed in the records-page-ready fixtures: " + what)


def _build_ready_page():
    os.makedirs(RPR, exist_ok=True)
    _rpr_git(RPR, "init", "-q", "--bare", "-b", "main", RPR_ORIGIN)
    os.makedirs(RPR_SEED, exist_ok=True)
    _rpr_git(RPR_SEED, "init", "-q", "-b", "main", ".")
    _rpr_git(RPR_SEED, "remote", "add", "origin", RPR_ORIGIN)

    def commit(message, files=None, page=False):
        for rel, text in (files or {}).items():
            write(os.path.join(RPR_SEED, *rel.split("/")), text)
        if page:  # the generator writes the page for this tree, as the merge tool does before the branch goes ready
            done = subprocess.run([sys.executable, RPR_GEN, "--root", RPR_SEED, "--records-only"], capture_output=True, text=True)
            _rpr_need(done.returncode == 0, "the generator refused the seed tree: " + done.stderr.strip())
        _rpr_git(RPR_SEED, "add", "-A")
        _rpr_git(RPR_SEED, "commit", "-q", "-m", message)

    def branch(name, base):
        _rpr_git(RPR_SEED, "checkout", "-q", "-B", name, base)

    commit("base", {".github/stamp.json": RPR_STAMP, "README.md": "base\n"})
    branch("feat-behind", "main")                         # cut here, before main moves on
    commit("a debt, cut before main moved", {"debts/gap-one.md": RPR_DEBT})
    _rpr_git(RPR_SEED, "checkout", "-q", "main")
    commit("main moves on", {"README.md": "main moved\n"})
    branch("feat-stale", "main")
    commit("a debt and no page", {"debts/gap-one.md": RPR_DEBT})
    branch("feat-current", "main")
    commit("a debt and the page the generator writes", {"debts/gap-one.md": RPR_DEBT}, page=True)
    branch("feat-claim", "main")
    commit("Claim record numbers\n\nRecord-claim: D-002", {"debts/gap-one.md": RPR_DEBT})
    branch("feat-empty", "main")
    commit("a note and no record", {"notes.txt": "a note\n"})
    branch("feat-bad", "main")
    commit("a record the generator refuses", {"debts/bad.md": "# Bad\n\n- **Where.** x\n"})
    branch("dev", "main")
    commit("dev moves on", {"dev.txt": "dev side\n"})
    branch("feat-dev", "dev")
    commit("a debt aimed at dev", {"debts/gap-one.md": RPR_DEBT})
    _rpr_git(RPR_SEED, "push", "-q", "origin", "main", "dev", "feat-behind", "feat-stale", "feat-current",
             "feat-claim", "feat-empty", "feat-bad", "feat-dev")

    # Scope before subject: each head is the state its case names.
    _rpr_need(run_vcs(RPR_SEED, "merge-base", "--is-ancestor", "main", "feat-behind").returncode == 1,
              "feat-behind holds the base tip, so it has no lack to skip for")
    _rpr_need("gap-one" in _rpr_git(RPR_SEED, "show", "feat-current:docs/records.md"), "feat-current carries no page")
    _rpr_need(_rpr_git(RPR_SEED, "ls-tree", "--name-only", "feat-stale", "--", "docs/records.md") == "", "feat-stale carries a page")
    _rpr_need("**What.**" not in _rpr_git(RPR_SEED, "show", "feat-bad:debts/bad.md"), "feat-bad holds a What line")

    _rpr_git(RPR, "clone", "-q", RPR_ORIGIN, RPR_REPO)
    _rpr_git(RPR, "clone", "-q", RPR_ORIGIN, RPR_NOSEL)
    _rpr_git(RPR_NOSEL, "checkout", "-q", "feat-stale")
    make_repo(RPR_PLAIN, {"README.md": "plain\n", "debts/gap-one.md": RPR_DEBT})

    def head(name):
        return _rpr_git(RPR_SEED, "rev-parse", "--verify", name)
    stale = dict(head_sha=head("feat-stale"), head_ref="feat-stale", draft=True)
    make_fake_gh(GHREADY_STALE, "main", **stale)
    make_fake_gh(GHREADY_NAMED, "main", need=["y/x"], **stale)
    make_fake_gh(GHREADY_HANG, "main", delay_s=75, **stale)  # past any read deadline under the 60 s hook timeout, under decide's 120 s
    make_fake_gh(GHREADY_COUNT, "main", count_file=RPR_COUNT, **stale)
    make_fake_gh(GHREADY_PLAIN, "main", **stale)
    make_fake_gh(GHREADY_CURRENT, "main", head_sha=head("feat-current"), head_ref="feat-current", draft=True)
    make_fake_gh(GHREADY_CLAIM, "main", head_sha=head("feat-claim"), head_ref="feat-claim", draft=True)
    make_fake_gh(GHREADY_BEHIND, "main", head_sha=head("feat-behind"), head_ref="feat-behind", draft=True)
    make_fake_gh(GHREADY_DEV, "dev", head_sha=head("feat-dev"), head_ref="feat-dev", draft=True)
    make_fake_gh(GHREADY_EMPTY, "main", head_sha=head("feat-empty"), head_ref="feat-empty", draft=True)
    make_fake_gh(GHREADY_BAD, "main", head_sha=head("feat-bad"), head_ref="feat-bad", draft=True)

    # The unknown ancestry: a shallow clone holds main's tip and cuts the path from feat-behind to it, so the read
    # answers None, never False (testing/shallow_clone.py, the one shallow fixture). Scope first, in the clone and in a worktree.
    error = shallow_clone.make(RPR_ORIGIN, RPR_SHALLOW, head("main"))
    _rpr_need(not error, "the shallow fixture could not be built: " + error)
    _rpr_git(RPR_SHALLOW, "fetch", "origin", "+refs/heads/feat-behind:refs/remotes/origin/feat-behind")
    behind = head("feat-behind")
    facts = shallow_clone.facts(RPR_SHALLOW, head("main"), behind)
    _rpr_need(facts["shallow"] and facts["pin_present"] and facts["ancestor_rc"] == 1,
              "the shallow clone does not reach the unknown shape: %r" % (facts,))
    _rpr_git(RPR_SHALLOW, "worktree", "add", "--detach", RPR_SHALLOW_WT, behind)
    _rpr_need(_load_git_reads().branch_is_ancestor(RPR_SHALLOW_WT, behind, "refs/remotes/origin/main") is None,
              "the worktree's ancestry read is not unknown")
    _rpr_git(RPR_SHALLOW, "worktree", "remove", "--force", RPR_SHALLOW_WT)
    behind_pr = dict(head_sha=behind, head_ref="feat-behind", draft=True)
    make_fake_gh(GHREADY_SHALLOW, "main", **behind_pr)
    make_fake_gh(GHREADY_SHALLOW_NAMED, "main", need=["y/x"], **behind_pr)


lazy_fixture([RPR], _build_ready_page)


def _rpr_env(fake):
    """The guard's PATH: the fake gh's folder, git, and the interpreter's folder. Nothing else, so no real gh is reached."""
    return fake + os.pathsep + GIT_PATH + os.pathsep + PY_PATH


def rpr_bash(name, command, expected, fake, cwd=RPR_REPO, tool="Bash", carries=(), lacks=()):
    sh(name, command, expected, rule=RPR_RULE if expected == "deny" else None, tool=tool, cwd=cwd,
       env_path=_rpr_env(fake), config=MERGECFG, carries=carries, lacks=lacks)


def rpr_mcp(name, expected, fake, carries=(), lacks=(), cwd=RPR_REPO, **tool_input):
    add(name, expected, rule=RPR_RULE if expected == "deny" else None, tool="mcp__github__update_pull_request",
        cwd=cwd, env_path=_rpr_env(fake), config=MERGECFG, carries=carries, lacks=lacks, **tool_input)


RPR_STALE_LACKS = ("unknown",)  # a stale refusal names the page, never an unread
# Refused: the page is stale on the head, and the refusal names the remedy. Each form of the call is its own case.
rpr_mcp("records-page-ready: MCP draft false on a stale page is refused", "deny", GHREADY_NAMED,
        carries=RPR_CARRY, lacks=RPR_STALE_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpr_bash("records-page-ready: gh pr ready 12 on a stale page is refused", "gh pr ready 12", "deny", GHREADY_STALE,
         carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: gh pr ready with no selector on a stale branch is refused", "gh pr ready", "deny",
         GHREADY_STALE, cwd=RPR_NOSEL, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: gh pr ready by URL on a stale page is refused",
         "gh pr ready https://github.com/y/x/pull/12", "deny", GHREADY_NAMED, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: gh pr ready \"#12\" on a stale page is refused", 'gh pr ready "#12"', "deny",
         GHREADY_STALE, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: GH_REPO=y/x gh pr ready 12 on a stale page is refused", "GH_REPO=y/x gh pr ready 12", "deny",
         GHREADY_NAMED, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: gh pr ready 12 -R y/x on a stale page is refused", "gh pr ready 12 -R y/x", "deny",
         GHREADY_NAMED, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: a PowerShell gh pr ready 12 on a stale page is refused", "gh pr ready 12", "deny",
         GHREADY_STALE, tool="PowerShell", carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
# Refused unknown: the read cannot run, so the rule cannot clear the head. The unknown reason names no merge command
# (RPR_UNKNOWN_LACKS): a ready mark that is already set would be merged by the --confirm it names.
rpr_bash("records-page-ready: a page the generator refuses is refused unknown", "gh pr ready 12", "deny", GHREADY_BAD,
         carries=("unknown",), lacks=RPR_UNKNOWN_LACKS)
rpr_bash("records-page-ready: a read that never answers is refused unknown", "gh pr ready 12", "deny", GHREADY_HANG,
         carries=("unknown",), lacks=RPR_UNKNOWN_LACKS)
# An unknown ancestry (merge-base reads None in a shallow clone) is unknown, not off main: the ready mark is refused, on both forms.
rpr_bash("records-page-ready: gh pr ready 12 with an unknown ancestry in a shallow clone is refused unknown", "gh pr ready 12",
         "deny", GHREADY_SHALLOW, cwd=RPR_SHALLOW, carries=("unknown",), lacks=RPR_UNKNOWN_LACKS)
rpr_mcp("records-page-ready: MCP draft false with an unknown ancestry in a shallow clone is refused unknown", "deny",
        GHREADY_SHALLOW_NAMED, cwd=RPR_SHALLOW, carries=("unknown",), lacks=RPR_UNKNOWN_LACKS,
        owner="y", repo="x", pullNumber=12, draft=False)
# A scanner must read the call as the parser does: text in quotes, heredocs and comments is no call.
rpr_bash("records-page-ready: a quoted # before the call does not hide it", 'echo "#" && gh pr ready 12', "deny",
         GHREADY_STALE, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: an apostrophe in a word does not hide the call", "echo Don't && gh pr ready 12", "deny",
         GHREADY_STALE, carries=RPR_CARRY, lacks=RPR_STALE_LACKS)
rpr_bash("records-page-ready: the call on a line of a multi-line quoted string is no call",
         'echo "start\ngh pr ready 12\nend"', "allow", GHREADY_STALE)
rpr_bash("records-page-ready: the call in a heredoc body is no call", "cat <<'EOF'\ngh pr ready 12\nEOF", "allow", GHREADY_STALE)
rpr_bash("records-page-ready: the call in a comment is no call", "echo ok # gh pr ready 12", "allow", GHREADY_STALE)
# Allowed: each control changes one thing from the refused case.
rpr_mcp("records-page-ready: MCP draft false on a current page is allowed", "allow", GHREADY_CURRENT,
        owner="y", repo="x", pullNumber=12, draft=False)
rpr_bash("records-page-ready: gh pr ready 12 on a current page is allowed", "gh pr ready 12", "allow", GHREADY_CURRENT)
rpr_bash("records-page-ready: a stale page into a base that is not the default is allowed", "gh pr ready 12", "allow",
         GHREADY_DEV)
rpr_bash("records-page-ready: a head holding a Record-claim is allowed", "gh pr ready 12", "allow", GHREADY_CLAIM)
rpr_bash("records-page-ready: a head that lacks the base tip is allowed", "gh pr ready 12", "allow", GHREADY_BEHIND)
rpr_bash("records-page-ready: a head with no record folders is allowed", "gh pr ready 12", "allow", GHREADY_EMPTY)
rpr_bash("records-page-ready: gh pr ready --undo on a stale page is allowed", "gh pr ready 12 --undo", "allow", GHREADY_STALE)
rpr_mcp("records-page-ready: MCP draft true on a stale page is allowed", "allow", GHREADY_NAMED,
        owner="y", repo="x", pullNumber=12, draft=True)
rpr_bash("records-page-ready: gh pr ready 12 in a repo that does not use the merge tool is allowed", "gh pr ready 12",
         "allow", GHREADY_PLAIN, cwd=RPR_PLAIN)
rpr_bash("records-page-ready: gh pr view 12 on a stale page is allowed", "gh pr view 12", "allow", GHREADY_STALE)


def _rpr_no_read(tool_input):
    """An MCP update that marks nothing ready (a title edit, or a close) is allowed, and starts no gh call."""
    if os.path.exists(RPR_COUNT):
        os.remove(RPR_COUNT)
    case = {"raw": None, "tool": "mcp__github__update_pull_request", "cwd": RPR_REPO, "session": None,
            "env_path": _rpr_env(GHREADY_COUNT), "config": MERGECFG, "tool_input": tool_input,
            "transcript": None, "agent_id": None, "agent_type": None, "event": None, "stop_active": False,
            "no_root": False, "max_seconds": None, "env": None, "temp": None, "guard": None, "silent": False}
    got, reason = decide(case)
    calls = open(RPR_COUNT, encoding="utf-8").read().splitlines() if os.path.exists(RPR_COUNT) else []
    if got != "allow":
        return False, "want allow, got %s: %s" % (got, reason[:110])
    if calls:
        return False, "%d gh call(s) for a call that marks nothing ready" % len(calls)
    return True, "allowed, no gh call"


def rpr_title_only_case():
    return _rpr_no_read({"owner": "y", "repo": "x", "pullNumber": 12, "title": "A new title"})


def rpr_closed_case():
    return _rpr_no_read({"owner": "y", "repo": "x", "pullNumber": 12, "state": "closed"})


# =========================================================================== 5c. the records page
