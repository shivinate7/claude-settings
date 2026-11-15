# section 43500
FAMILY = "handed-in-push"  # a push to a pull request's branch (roadmap step handed-in-push-needs-record; decision pr-review-record)

# A Bash `git push` to the branch of an open pull request is refused when the pull request's newest review record is stale
# against the live head: the record is for an older head, and no clean merge of main and no records-page commit of the merge
# tool carries it to the live head. The live head is the pull request's head on GitHub before the push, the head the lane
# pushes from. A record for the live head (a FAIL round too) passes, so the fix push after a posted FAIL round is allowed.
# A pull request with no record at all passes: its first round is the known gap of option a. A read that cannot run is
# refused unknown (decision guard-hooks-fail-closed), never allowed as clear and never named as a missing record.
#
# THE FIXTURE. A bare origin with feat (Z, A, B), feat-merge (a clean merge M of main into B), feat-page (a page-only commit
# P on A) and main, which moves on after feat is cut. Each case's clone sits on the live head it names, with one local commit
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


def _hip_record(i, head, rounds):
    """An issue comment that carries a review record for `head`, written by the merge tool's own writer."""
    body = merge_tool.review_body(HIP_PR, head, "normal", "no", rounds, "not owed")
    stamp = "2026-11-14T10:%02d:00Z" % i
    return {"id": 7000 + i, "body": body, "created_at": stamp, "updated_at": stamp,
            "issue_url": "https://api.github.com/repos/y/x/issues/%d" % HIP_PR, "user": {"login": "o"},
            "author_association": "OWNER"}


def _hip_build():
    os.makedirs(HIP_ROOT, exist_ok=True)
    _hip_git(HIP_ROOT, "init", "-q", "--bare", "-b", "main", HIP_ORIGIN)
    os.makedirs(HIP_SEED, exist_ok=True)
    _hip_git(HIP_SEED, "init", "-q", "-b", "main", ".")
    _hip_git(HIP_SEED, "remote", "add", "origin", HIP_ORIGIN)
    base = _hip_commit("base", {".github/stamp.json": HIP_STAMP, "debts/gap-one.md": HIP_DEBT,
                                "README.md": "base\n", "feature.txt": "base\n"})
    _hip_git(HIP_SEED, "checkout", "-q", "-B", "feat", "main")
    z = _hip_commit("round one, reviewed", {"feature.txt": "z\n"})
    a = _hip_commit("fix after round one", {"feature.txt": "a\n"})
    b = _hip_commit("fix two", {"feature.txt": "b\n"})
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
    _hip_git(HIP_SEED, "push", "-q", "origin", "main", "feat", "feat-merge", "feat-page")

    commits = {}
    for sha in (base, z, a, b, mt, m, p):
        parents = _hip_git(HIP_SEED, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        commits[sha] = {"parents": parents, "tree": _hip_git(HIP_SEED, "rev-parse", sha + "^{tree}")}

    _hip_clone_at(HIP_CLONE_B, b)
    _hip_clone_at(HIP_CLONE_A, a)
    _hip_clone_at(HIP_CLONE_M, m)
    _hip_clone_at(HIP_CLONE_P, p)

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


lazy_fixture(HIP_FOLDERS, _hip_build)


def hip_push(name, expected, cwd, fake, dest="feat", **kw):
    """One case: a Bash `git push origin HEAD:<dest>` run in `cwd`, judged against the pull request answers of `fake`."""
    sh(name, "git push origin HEAD:" + dest, expected, rule=HIP_RULE if expected == "deny" else None,
       cwd=cwd, env_path=_hip_env(fake), config=MERGECFG, **kw)


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
