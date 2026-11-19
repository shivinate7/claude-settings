# section 43500
FAMILY = "handed-in-push"  # a push to a pull request's branch (roadmap step handed-in-push-needs-record; decision pr-review-record)

# A Bash `git push` to the branch of an open pull request is refused when the pull request's newest review record is stale
# against the live head: the record is for an older head, and no clean merge of main and no records-page commit of the merge
# tool carries it to the live head. The live head is the pull request's head on GitHub before the push, the head the lane
# pushes from. A record for the live head (a FAIL round too) passes, so the fix push after a posted FAIL round is allowed.
# A pull request with no record at all passes: its first round is the known gap of option a. A PR-list read that cannot run
# lets the push pass, and a read after a pull request is found that cannot run is refused unknown (decision
# guard-hooks-fail-closed), never allowed as clear and never named as a missing record.
#
# THE FIXTURE. A bare origin with feat (Z, A, B), feat-merge (a clean merge M of main into B), feat-page (a page-only commit
# P on A), feat-three (C, one commit on B) and main, which moves on after feat is cut. A bare backup beside it is a second
# remote for the cases that push to another remote. Each case's clone sits on the live head it names, with one local commit
# on top, which the case pushes as HEAD:<branch>. Each case's fake gh answers for its own pull request, with its own records.
# The records are built by merge/merge.py review_body, the one writer of the form, and the page subject is its PAGE_SUBJECT,
# so no literal copy of either lives here.
HIP_RULE = "handed-in-push-needs-record"
HIP_ROOT = os.path.join(ROOT, "handed-in-push")
HIP_ORIGIN = os.path.join(HIP_ROOT, "origin.git")
HIP_SEED = os.path.join(HIP_ROOT, "seed")
HIP_GEN = os.path.join(REPO, "lint", "hook_catalog.py")
HIP_PR = 12  # the number the fake pull request answers as
HIP_PUSH_FILE = "pushed.txt"
HIP_CLONE_B = os.path.join(HIP_ROOT, "clone-b")      # live head B, the feat tip
HIP_CLONE_A = os.path.join(HIP_ROOT, "clone-a")      # live head A, the reviewed head with a FAIL round
HIP_CLONE_M = os.path.join(HIP_ROOT, "clone-m")      # live head M, a clean merge of main into B
HIP_CLONE_P = os.path.join(HIP_ROOT, "clone-p")      # live head P, a records-page commit on A
HIP_CLONE_C = os.path.join(HIP_ROOT, "clone-c")      # live head C, one commit on B (feat-three)
HIP_CLONE_BK = os.path.join(HIP_ROOT, "clone-bk")    # live head B, with a second remote named backup
HIP_BACKUP = os.path.join(HIP_ROOT, "backup.git")    # the bare repo backup names: not the repo the pull request lives in
HIP_STAMP = json.dumps({"defaultBranch": "main", "kinds": [],
                        "merge": {"method": "merge", "deadlineMinutes": 5, "afterMerge": [], "deleteBranch": True}})
HIP_DEBT = "# Gap one\n\n- **What.** The check misses one case.\n- **Where.** x\n- **Decision.** none\n- **Retire.** y\n"
REVIEW_PASS_ONE = [(1, "reviewer", "sonnet", "PASS")]  # the rounds of one record: one PASS round, or one FAIL round
REVIEW_FAIL_ONE = [(1, "reviewer", "sonnet", "FAIL")]
HIP_FOLDERS = [HIP_ROOT]  # the fixture's folders: a case that names one builds the fixture first
HIP_GH_STALE = os.path.join(HIP_ROOT, "gh-stale")                # live B, the record for A: stale
HIP_GH_FIRST = os.path.join(HIP_ROOT, "gh-first")                # live B, no record on the pull request
HIP_GH_LIVE = os.path.join(HIP_ROOT, "gh-live")                  # live B, the record for B
HIP_GH_FAIL_OLD = os.path.join(HIP_ROOT, "gh-fail-old")          # live A, a FAIL record for Z and none for A
HIP_GH_FAIL_LIVE = os.path.join(HIP_ROOT, "gh-fail-live")        # live A, a FAIL record for A
HIP_GH_CLEAN = os.path.join(HIP_ROOT, "gh-clean")                # live M, a clean merge of main into B, its record for B
HIP_GH_PAGE = os.path.join(HIP_ROOT, "gh-page")                  # live P, a records-page commit on A, its record for A
HIP_GH_UNREAD = os.path.join(HIP_ROOT, "gh-unread")              # live B, the comment reads answer 404
HIP_GH_CLEAN_UNREAD = os.path.join(HIP_ROOT, "gh-clean-unread")  # live M, the record for B, the main compare answers 404
HIP_GH_MALFORMED = os.path.join(HIP_ROOT, "gh-malformed")        # live C, a valid record for A, then a malformed newest record
HIP_GH_FEATURE = os.path.join(HIP_ROOT, "gh-feature")            # live B, on a branch named feature, the record for A: stale
HIP_GH_FORK = os.path.join(HIP_ROOT, "gh-fork")                  # live B on feat, the head repo a fork, the record for A: stale
HIP_GH_BROKEN = os.path.join(HIP_ROOT, "gh-broken")              # every pull request read answers no JSON: no lookup can run
HIP_STALE_CARRIES = ("record",)     # a stale refusal names the review record, the thing to post
HIP_UNKNOWN_CARRIES = ("unknown",)  # an unread refusal says the read is unknown
HIP_UNKNOWN_LACKS = ("no record", "missing")  # ...and never reads as a record that is absent

sys.path.append(os.path.join(REPO, "merge"))  # append: no module shadows one the guard suite imports
import merge as merge_tool  # noqa: E402  the review record's one writer (review_body) and the records-page subject (PAGE_SUBJECT)


def _hip_env(fake):
    """The guard's PATH: the fake gh's folder, git, and the interpreter's folder. Nothing else, so no real gh is reached."""
    return fake + os.pathsep + GIT_PATH + os.pathsep + PY_PATH


def _hip_git(where, *args):
    done = run_vcs(where, *IDENT, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in the handed-in-push fixtures: %s %s in %r: %s"
                 % (VCS, " ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def _hip_need(ok, what):
    if not ok:
        sys.exit("fixture setup failed in the handed-in-push fixtures: " + what)


def _hip_commit(message, files=None, page=False):
    for rel, text in (files or {}).items():
        write(os.path.join(HIP_SEED, *rel.split("/")), text)
    if page:  # the generator writes the page for this tree, as the merge tool does before a claim
        done = subprocess.run([sys.executable, HIP_GEN, "--root", HIP_SEED, "--records-only"], capture_output=True, text=True)
        _hip_need(done.returncode == 0, "the records generator refused the seed tree: " + done.stderr.strip())
    _hip_git(HIP_SEED, "add", "-A")
    _hip_git(HIP_SEED, "commit", "-q", "-m", message)
    return _hip_git(HIP_SEED, "rev-parse", "HEAD")


def _hip_clone_at(where, sha):
    """A clone of the origin, on a local branch at `sha`, with one commit on top: the change the case pushes."""
    _hip_git(HIP_ROOT, "clone", "-q", HIP_ORIGIN, where)
    _hip_git(where, "checkout", "-q", "-b", "pushing", sha)
    write(os.path.join(where, HIP_PUSH_FILE), "pushed\n")
    _hip_git(where, "add", "-A")
    _hip_git(where, "commit", "-q", "-m", "the change to push")
    _hip_need(_hip_git(where, "rev-parse", "HEAD^") == sha, "the change to push in %r does not sit on %s" % (where, sha[:9]))


def _hip_comment(i, body):
    """An issue comment on the pull request, in the shape the comment reads answer, numbered and stamped by `i`."""
    stamp = "2026-11-14T10:%02d:00Z" % i
    return {"id": 7000 + i, "body": body, "created_at": stamp, "updated_at": stamp,
            "issue_url": "https://api.github.com/repos/y/x/issues/%d" % HIP_PR, "user": {"login": "o"},
            "author_association": "OWNER"}


def _hip_record(i, head, rounds):
    """An issue comment that carries a review record for `head`, written by the merge tool's own writer."""
    return _hip_comment(i, merge_tool.review_body(HIP_PR, head, "normal", "no", rounds, "not owed"))


def _hip_malformed(i, head, rounds):
    """An issue comment that opens as a review record and does not parse: its Head line holds 12 characters, not 40.
    The writer's own text, changed in one field, so the only fault is the one the case names."""
    body = merge_tool.review_body(HIP_PR, head, "normal", "no", rounds, "not owed")
    return _hip_comment(i, body.replace("Head: " + head, "Head: " + head[:12], 1))


def _hip_build():
    os.makedirs(HIP_ROOT, exist_ok=True)
    _hip_git(HIP_ROOT, "init", "-q", "--bare", "-b", "main", HIP_ORIGIN)
    os.makedirs(HIP_SEED, exist_ok=True)
    _hip_git(HIP_SEED, "init", "-q", "-b", "main", ".")
    _hip_git(HIP_SEED, "remote", "add", "origin", HIP_ORIGIN)
    _hip_git(HIP_ROOT, "init", "-q", "--bare", "-b", "main", HIP_BACKUP)
    base = _hip_commit("base",{".github/stamp.json": HIP_STAMP, "debts/gap-one.md": HIP_DEBT,
                                "README.md": "base\n", "feature.txt": "base\n"})
    _hip_git(HIP_SEED, "checkout", "-q", "-B", "feat", "main")
    z = _hip_commit("round one, reviewed", {"feature.txt": "z\n"})
    a = _hip_commit("fix after round one", {"feature.txt": "a\n"})
    b = _hip_commit("fix two", {"feature.txt": "b\n"})
    _hip_git(HIP_SEED, "checkout", "-q", "-B", "feat-three", b)
    c = _hip_commit("fix three", {"feature.txt": "c\n"})  # one commit on B: the live head of the malformed-record case
    _hip_git(HIP_SEED, "checkout", "-q", "main")
    mt = _hip_commit("main moves on", {"other.txt": "main\n"})  # after feat is cut, so the merge below brings it in
    _hip_git(HIP_SEED, "checkout", "-q", "-B", "feat-merge", b)
    _hip_git(HIP_SEED, "merge", "-q", "--no-edit", "main")
    m = _hip_git(HIP_SEED, "rev-parse", "HEAD")
    _hip_need(_hip_git(HIP_SEED, "rev-list", "--parents", "-n", "1", m).split()[1:] == [b, mt],
              "feat-merge's head is not a merge of B and main's tip")
    _hip_git(HIP_SEED, "checkout", "-q", "-B", "feat-page", a)
    p = _hip_commit(merge_tool.PAGE_SUBJECT, page=True)
    _hip_need(_hip_git(HIP_SEED, "rev-list", "--parents", "-n", "1", p).split()[1:] == [a], "feat-page's head does not sit on A")
    _hip_need("Records index" in _hip_git(HIP_SEED, "show", p + ":docs/records.md"), "the page commit holds no records page")
    _hip_git(HIP_SEED, "push", "-q", "origin", "main", "feat", "feat-merge", "feat-page", "feat-three")

    commits = {}
    for sha in (base, z, a, b, c, mt, m, p):
        parents = _hip_git(HIP_SEED, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        commits[sha] = {"parents": parents, "tree": _hip_git(HIP_SEED, "rev-parse", sha + "^{tree}")}

    _hip_clone_at(HIP_CLONE_B, b)
    _hip_clone_at(HIP_CLONE_A, a)
    _hip_clone_at(HIP_CLONE_M, m)
    _hip_clone_at(HIP_CLONE_P, p)
    _hip_clone_at(HIP_CLONE_C, c)
    _hip_clone_at(HIP_CLONE_BK, b)
    _hip_git(HIP_CLONE_BK, "remote", "add", "backup", HIP_BACKUP)

    main_compare = "%s...main" % mt  # the containment read of main's tip, as holds_head asks it
    make_fake_gh(HIP_GH_STALE, "main", head_sha=b, head_ref="feat", comments=[_hip_record(1, a, REVIEW_PASS_ONE)], commits=commits)
    make_fake_gh(HIP_GH_FIRST, "main", head_sha=b, head_ref="feat", comments=[], commits=commits)
    make_fake_gh(HIP_GH_LIVE, "main", head_sha=b, head_ref="feat", comments=[_hip_record(1, b, REVIEW_PASS_ONE)], commits=commits)
    make_fake_gh(HIP_GH_FAIL_OLD, "main", head_sha=a, head_ref="feat", comments=[_hip_record(1, z, REVIEW_FAIL_ONE)], commits=commits)
    make_fake_gh(HIP_GH_FAIL_LIVE, "main", head_sha=a, head_ref="feat", comments=[_hip_record(1, a, REVIEW_FAIL_ONE)], commits=commits)
    make_fake_gh(HIP_GH_CLEAN, "main", head_sha=m, head_ref="feat", comments=[_hip_record(1, b, REVIEW_PASS_ONE)], commits=commits,
                 compares={main_compare: "identical"})
    make_fake_gh(HIP_GH_PAGE, "main", head_sha=p, head_ref="feat", comments=[_hip_record(1, a, REVIEW_PASS_ONE)], commits=commits)
    make_fake_gh(HIP_GH_UNREAD, "main", head_sha=b, head_ref="feat", comments="missing", commits=commits)
    make_fake_gh(HIP_GH_CLEAN_UNREAD, "main", head_sha=m, head_ref="feat", comments=[_hip_record(1, b, REVIEW_PASS_ONE)],
                 commits=commits, compares={main_compare: "missing"})
    make_fake_gh(HIP_GH_MALFORMED, "main", head_sha=c, head_ref="feat",
                 comments=[_hip_record(1, a, REVIEW_PASS_ONE), _hip_malformed(2, c, REVIEW_PASS_ONE)], commits=commits)
    make_fake_gh(HIP_GH_FEATURE, "main", head_sha=b, head_ref="feature", comments=[_hip_record(1, a, REVIEW_PASS_ONE)], commits=commits)
    make_fake_gh(HIP_GH_FORK, "main", head_sha=b, head_ref="feat", head_repo="fork/x", comments=[_hip_record(1, a, REVIEW_PASS_ONE)],
                 commits=commits)
    make_fake_gh(HIP_GH_BROKEN, "main", head_sha=b, head_ref="feat", broken=True, commits=commits)


lazy_fixture(HIP_FOLDERS, _hip_build)


def hip_run(name, command, expected, cwd, fake, **kw):
    """One case: the Bash `command` run in `cwd`, judged against the pull request answers of `fake`."""
    sh(name, command, expected, rule=HIP_RULE if expected == "deny" else None,
       cwd=cwd, env_path=_hip_env(fake), config=MERGECFG, **kw)


def hip_push(name, expected, cwd, fake, dest="feat", **kw):
    """One case: a Bash `git push origin HEAD:<dest>`, as hip_run judges it."""
    hip_run(name, "git push origin HEAD:" + dest, expected, cwd, fake, **kw)


# Refused: the newest record is for an older head, so the record of the live head is unposted.
hip_push("handed-in-push: a push over a review record for an older head is refused", "deny", HIP_CLONE_B, HIP_GH_STALE,
         carries=HIP_STALE_CARRIES, lacks=HIP_UNKNOWN_CARRIES)
# Refused: the fix push after a FAIL round whose record is for an older head. The reviewed head A holds no record.
hip_push("handed-in-push: a fix push over an unposted FAIL round is refused", "deny", HIP_CLONE_A, HIP_GH_FAIL_OLD,
         carries=HIP_STALE_CARRIES, lacks=HIP_UNKNOWN_CARRIES)
# Allowed: each control changes one thing from a refused case.
hip_push("handed-in-push: a push with no review record on the pull request is allowed (a first round, option a's known gap)",
         "allow", HIP_CLONE_B, HIP_GH_FIRST)
hip_push("handed-in-push: a push over the review record of the live head is allowed", "allow", HIP_CLONE_B, HIP_GH_LIVE)
hip_push("handed-in-push: a fix push over a posted FAIL round is allowed, the record being for the live head", "allow",
         HIP_CLONE_A, HIP_GH_FAIL_LIVE)
hip_push("handed-in-push: a clean merge of main into the reviewed head keeps the record, so the push is allowed", "allow",
         HIP_CLONE_M, HIP_GH_CLEAN)
hip_push("handed-in-push: a push after the merge tool's own records-page commit keeps the record, so the push is allowed", "allow",
         HIP_CLONE_P, HIP_GH_PAGE)
hip_push("handed-in-push: a push to a branch no pull request holds is allowed, whatever another pull request holds", "allow",
         HIP_CLONE_B, HIP_GH_STALE, dest="topic-x")
# Refused unknown: a read that cannot run is never allowed as clear, and never named as a missing record.
hip_push("handed-in-push: a push whose review comments cannot be read is refused unknown", "deny", HIP_CLONE_B, HIP_GH_UNREAD,
         carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)
hip_push("handed-in-push: a push whose clean-merge read cannot run is refused unknown", "deny", HIP_CLONE_M, HIP_GH_CLEAN_UNREAD,
         carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)

# A push the guard cannot name the branch of is refused unknown, never allowed. A push nested in another command is judged as
# its plain form is. A push to another remote, or a fork's pull request under the same head name, is not a push to the pull
# request's branch on origin.

# A newest record that does not parse is not no record: the push is refused unknown. A valid record for an older head before
# it does not carry the push.
hip_push("handed-in-push: a push over a valid record for an older head, then a malformed newest record, is refused unknown",
         "deny", HIP_CLONE_C, HIP_GH_MALFORMED, carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)

# A destination held in a shell variable or a substitution is no branch name: the push is refused unknown, never read as a
# branch that no pull request holds.
hip_run("handed-in-push: a push to a destination held in a shell variable is refused unknown",
        'git push origin "$BR"', "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)
hip_run("handed-in-push: a push to HEAD:$BR, a variable destination, is refused unknown",
        "git push origin HEAD:$BR", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)
hip_run("handed-in-push: a push to a destination from a command substitution is refused unknown",
        'git push origin "$(git rev-parse --abbrev-ref HEAD)"', "deny", HIP_CLONE_B, HIP_GH_STALE,
        carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)

# A destination the config leaves open (push.default=matching sends every matching branch) is refused unknown.
hip_run("handed-in-push: a bare push whose destination the config leaves open (push.default=matching) is refused unknown",
        "git -c push.default=matching push", "deny", HIP_CLONE_B, HIP_GH_STALE,
        carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)

# A push that names every branch (--all, --mirror, --branches) reaches the pull request's branch with no destination this
# reader can name, so it is refused unknown.
hip_run("handed-in-push: git push --all origin is refused unknown, since it names every branch",
        "git push --all origin", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)
hip_run("handed-in-push: git push --mirror origin is refused unknown, since it names every branch",
        "git push --mirror origin", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)
hip_run("handed-in-push: git push --branches origin is refused unknown, since it names every branch",
        "git push --branches origin", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)

# A push nested in another command is judged as the plain form is: the stale record refuses it.
hip_run("handed-in-push: a push inside bash -c is judged like the plain form, so a stale record refuses it",
        "bash -c 'git push origin HEAD:feat'", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_STALE_CARRIES)
hip_run("handed-in-push: a push inside a command substitution is judged like the plain form, so a stale record refuses it",
        "echo $(git push origin HEAD:feat)", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_STALE_CARRIES)

# A push to another remote is not a push to the pull request's branch on origin, so origin's stale record does not refuse it.
# The control after it holds the remote apart from the name: the same branch pushed to origin is refused.
hip_run("handed-in-push: a push to backup's feature, a remote other than the pull request's repo, is allowed over origin's stale record",
        "git push backup feature", "allow", HIP_CLONE_BK, HIP_GH_FEATURE)
hip_push("handed-in-push: the same branch pushed to origin is still refused over that stale record (control)",
         "deny", HIP_CLONE_BK, HIP_GH_FEATURE, dest="feature", carries=HIP_STALE_CARRIES)
# A fork's pull request names its head branch in the fork's repo, so it holds no branch of origin and a push to origin's feat
# is allowed.
hip_push("handed-in-push: a push to feat is allowed when only a fork's pull request holds a stale record under that head name",
         "allow", HIP_CLONE_B, HIP_GH_FORK)

# A folder the guard cannot resolve is refused unknown, never judged as a push outside any pull request. The directory is named
# by a shell variable in each form (`git -C`, and a leading `cd`), so no folder is read.
hip_run("handed-in-push: a git -C into a directory held in a shell variable is refused unknown, over a stale record",
        'git -C "$WT" push origin HEAD:feat', "deny", HIP_CLONE_B, HIP_GH_STALE,
        carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)
hip_run("handed-in-push: a cd into a directory held in a shell variable, then a push, is refused unknown, over a stale record",
        'cd "$WT" && git push origin HEAD:feat', "deny", HIP_CLONE_B, HIP_GH_STALE,
        carries=HIP_UNKNOWN_CARRIES, lacks=HIP_UNKNOWN_LACKS)

# A redirection or a pipe after a push names no destination: its words are a file, not a branch. Only the remote and the refspec
# words are the destination, so a push over the live record passes whatever file takes its output.
hip_run("handed-in-push: a push over the live record with its output redirected to a file is allowed",
        'git push origin feat > "$LOG" 2>&1', "allow", HIP_CLONE_B, HIP_GH_LIVE)
hip_run("handed-in-push: a push over the live record piped through tee to a file is allowed",
        'git push origin feat 2>&1 | tee "$LOG"', "allow", HIP_CLONE_B, HIP_GH_LIVE)

# A pull request lookup that cannot run names no pull request, so no record is stale and the push is allowed. A pull request that is
# found, with its comments unread, is still refused unknown (the comment-read case above).
hip_push("handed-in-push: a push to a new branch while the pull request lookup cannot run is allowed, no record being stale",
         "allow", HIP_CLONE_B, HIP_GH_BROKEN, dest="topic-new")

# A deletion and a push to feat in one call: the deletion moves no head, the push to feat does, so the stale record refuses the call.
hip_run("handed-in-push: a push that deletes old and sends HEAD to feat is refused over a stale record",
        "git push origin :old HEAD:feat", "deny", HIP_CLONE_B, HIP_GH_STALE, carries=HIP_STALE_CARRIES)
