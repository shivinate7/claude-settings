# section 43600
FAMILY = "review-log"
#
# The review record a PR comment carries (decision pr-review-record). A comment whose first line is exactly the marker
# is a record, and merge/merge.py parse_review reads it. A body that parse_review refuses is a record the merge tool
# cannot use, so the merge stops on it. Two rules judge the GitHub comment tools, the add and the update:
#
# review-record-form  the first line is the marker and parse_review(body) is None: refused. The reason names the one
#                     form to use, `merge <pr> --review-record --head <sha> ...`, whose printed text is posted as is.
# review-record-sha   the body parses, and a 40-hex sha on its Head or Fix check line does not resolve with
#                     `git cat-file -e <sha>^{commit}` in the call's checkout: refused. A check that cannot run
#                     allows: no git on PATH, or no checkout in the call's folder.
#
# A body with no marker is no record, so neither rule judges it. The matcher that routes both tools to the guard is
# pinned in lint/test_settings_matcher.py (JudgedToolMatcher).
#
# THE FIXTURE. One checkout on main, RVW_REPO, with two commits: RVW_FIX, then RVW_HEAD. The identity and the dates are
# fixed, so the two shas are fixed, and the build refuses any other pair. RVW_UNKNOWN is made up from RVW_HEAD's first
# ten characters, as a sha in the incident was. RVW_NOTREE is a folder that is no git tree, RVW_EMPTY a repository
# with no commit, and RVW_NOPATH an empty folder on PATH, so no git runs. The build also reads merge/merge.py's
# parse_review, so each verdict rests on what the merge tool accepts, not on a copy of its rules.

RVW_OWNER = "shivinate7"
RVW_NAME = "claude-settings"
RVW_ADD = "mcp__github__add_issue_comment"
RVW_UPDATE = "mcp__github__update_issue_comment"
RVW_FORM = "review-record-form"
RVW_SHA = "review-record-sha"
RVW_MARK = "<!-- review-record -->"
RVW_CI = "CI: read live by merge --reviewed"
RVW_REMEDY = ("--review-record --head",)  # the one form the refusal names
RVW_REPO = os.path.join(ROOT, "reviewrec", "repo")            # a checkout on main: RVW_FIX, then RVW_HEAD
RVW_NOTREE = os.path.join(ROOT, "reviewrec", "notree")        # a folder that is no git tree
RVW_EMPTY = os.path.join(ROOT, "reviewrec", "empty-repo")     # a repository with no commit
RVW_NOPATH = os.path.join(ROOT, "reviewrec", "no-git-path")   # an empty folder on PATH: no git runs
RVW_WHEN = ("1762000000 +0000", "1762000100 +0000")          # the author and committer dates of the two commits
RVW_FIX = "7fca3909fd0cd7f987b44b16a183aa84f193d8fd"
RVW_HEAD = "46de774f5e9f3e0f78d2b7bae0dfea421e83bc2c"
RVW_UNKNOWN = RVW_HEAD[:10] + "a" * 30
RVW_ROUND = "Round 1: reviewer, sonnet, PASS"
RVW_FULL_ROWS = ("Round 1: reviewer, sonnet, FAIL", "Round 2: reviewer, sonnet, FAIL", "Round 3: reviewer, sonnet, PASS")


def rvw_body(head=RVW_HEAD, fix=None, rows=(RVW_ROUND,), kind="normal", guard="no", net="positive", n=12):
    """A record in the form merge/merge.py's review_body prints: the marker, the PR, Head, Kind, Guard or check, the
    rows (round lines, or any text a case names), an optional Fix check line, Net value, and the CI line."""
    lines = [RVW_MARK, "PR: #%d" % n, "Head: %s" % head, "Kind: %s" % kind, "Guard or check: %s" % guard, *rows]
    if fix:
        lines.append("Fix check: %s, reviewer, sonnet, PASS" % fix)
    lines += ["Net value: %s" % net, RVW_CI]
    return "\n".join(lines) + "\n"


# The hand-typed forms the merge tool refused, one per shape: a Kind in free text, a round with no role, a summary
# line, a free-text Fix check, and the marker with no fields after it.
RVW_HAND_KIND = rvw_body(kind="guard or check change", guard="yes")
RVW_HAND_ROUND = rvw_body(rows=("Round 1: FAIL, claude-haiku-5-5",))
RVW_HAND_SUMMARY = rvw_body(rows=("Rounds: 1 PASS",))
RVW_HAND_FIX = rvw_body(rows=("Round 1: reviewer, sonnet, FAIL", "Fix check: lint error fixed on the branch, PASS"))
RVW_HAND_MARKER = RVW_MARK + "\n"
RVW_HAND_BODIES = (("a Kind in free text", RVW_HAND_KIND), ("a round with no role", RVW_HAND_ROUND),
                   ("a rounds summary", RVW_HAND_SUMMARY), ("a free-text Fix check", RVW_HAND_FIX),
                   ("the marker alone", RVW_HAND_MARKER))


def _rvw_need(ok, what):
    if not ok:
        sys.exit("fixture setup failed in the review-record fixtures: " + what)


def _rvw_run(where, args, when=None):
    """One git call in a fixture folder, with the test identity, and the caller's git location variables removed.
    A date pins a commit's sha."""
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    return subprocess.run([VCS, *IDENT, *args], cwd=where, capture_output=True, text=True, env=env)


def _rvw_git(where, *args, when=None):
    done = _rvw_run(where, args, when=when)
    _rvw_need(done.returncode == 0, "%s %s in %r failed: %s" % (VCS, " ".join(args), where, done.stderr.strip()))
    return done.stdout.strip()


def _rvw_merge_parse():
    """merge/merge.py's parse_review, loaded from its file: the one home of the record's form."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("review_log_under_test", os.path.join(REPO, "merge", "merge.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.parse_review


def _rvw_build():
    os.makedirs(RVW_REPO, exist_ok=True)
    _rvw_git(RVW_REPO, "init", "-q", "-b", "main", ".")
    write(os.path.join(RVW_REPO, "README.md"), "review record fixture\n")
    _rvw_git(RVW_REPO, "add", "-A")
    _rvw_git(RVW_REPO, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "first", when=RVW_WHEN[0])
    write(os.path.join(RVW_REPO, "notes.txt"), "second commit\n")
    _rvw_git(RVW_REPO, "add", "-A")
    _rvw_git(RVW_REPO, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "second", when=RVW_WHEN[1])
    shas = (_rvw_git(RVW_REPO, "rev-parse", "HEAD~1"), _rvw_git(RVW_REPO, "rev-parse", "HEAD"))
    _rvw_need(shas == (RVW_FIX, RVW_HEAD), "the commits are %r, not the shas the cases name" % (shas,))
    os.makedirs(RVW_NOTREE, exist_ok=True)
    _rvw_need(_rvw_run(RVW_NOTREE, ("rev-parse", "--is-inside-work-tree")).returncode != 0,
              "%r is inside a git tree, so it is not the no-checkout shape" % RVW_NOTREE)
    os.makedirs(RVW_EMPTY, exist_ok=True)
    _rvw_git(RVW_EMPTY, "init", "-q", "-b", "main", ".")
    os.makedirs(RVW_NOPATH, exist_ok=True)
    # Scope before subject: the shapes the cases name are the shapes the merge tool accepts or refuses.
    parse = _rvw_merge_parse()
    _rvw_need(parse(rvw_body()) is not None, "parse_review refuses the tool-form record the cases allow")
    _rvw_need(parse(rvw_body(rows=RVW_FULL_ROWS, fix=RVW_FIX)) is not None,
              "parse_review refuses the full-size record the cases allow")
    for label, body in RVW_HAND_BODIES:
        _rvw_need(parse(body) is None, "parse_review accepts the hand-typed record with %s" % label)


lazy_fixture([RVW_REPO, RVW_NOTREE, RVW_EMPTY, RVW_NOPATH], _rvw_build)


def rvw_add(name, expected, body, rule=None, cwd=RVW_REPO, env_path=None, carries=()):
    add(name, expected, rule=rule, tool=RVW_ADD, cwd=cwd, env_path=env_path, carries=carries,
        owner=RVW_OWNER, repo=RVW_NAME, issue_number=12, body=body)


def rvw_update(name, expected, body, rule=None, cwd=RVW_REPO, carries=()):
    add(name, expected, rule=rule, tool=RVW_UPDATE, cwd=cwd, carries=carries,
        owner=RVW_OWNER, repo=RVW_NAME, comment_id=101, body=body)


# ---- review-record-form: a body whose first line is the marker must parse. Refused forms, then the controls.
rvw_add("review-record-form: a record whose Kind is free text is refused", "deny", RVW_HAND_KIND,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-record-form: a round line with no role is refused", "deny", RVW_HAND_ROUND,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-record-form: a rounds summary line is refused", "deny", RVW_HAND_SUMMARY,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-record-form: a free-text Fix check line is refused", "deny", RVW_HAND_FIX,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-record-form: the marker with no fields after it is refused", "deny", RVW_HAND_MARKER,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_update("review-record-form: an update that holds a hand-typed Kind line is refused", "deny", RVW_HAND_KIND,
           rule=RVW_FORM, carries=RVW_REMEDY)

rvw_add("review-record-form: a tool-form record for a head that resolves is allowed", "allow", rvw_body())
rvw_update("review-record-form: an update with a tool-form record for a head that resolves is allowed", "allow",
           rvw_body())
rvw_add("review-record-form: a full-size record, three rounds and a Fix check, is allowed", "allow",
        rvw_body(rows=RVW_FULL_ROWS, fix=RVW_FIX))
rvw_add("review-record-form: a body with no marker is allowed", "allow",
        "Lint PASS on the head. Merging after CI.\n")
rvw_add("review-record-form: a body with no marker that holds the hand-typed Kind line is allowed", "allow",
        RVW_HAND_KIND.split("\n", 1)[1])

# ---- review-record-sha: a body that parses names shas that must resolve in the call's checkout.
rvw_add("review-record-sha: a record whose Head is a made-up sha is refused", "deny", rvw_body(head=RVW_UNKNOWN),
        rule=RVW_SHA)
rvw_add("review-record-sha: a record whose Fix check sha is made up is refused", "deny", rvw_body(fix=RVW_UNKNOWN),
        rule=RVW_SHA)
rvw_update("review-record-sha: an update whose Head is a made-up sha is refused", "deny",
           rvw_body(head=RVW_UNKNOWN), rule=RVW_SHA)
rvw_add("review-record-sha: a Head sha in a checkout with no commit is refused", "deny", rvw_body(),
        rule=RVW_SHA, cwd=RVW_EMPTY)
rvw_add("review-record-sha: a Head and a Fix check that both resolve are allowed", "allow",
        rvw_body(fix=RVW_FIX))
rvw_add("review-record-sha: a made-up Head is allowed when no git runs on PATH", "allow",
        rvw_body(head=RVW_UNKNOWN), env_path=RVW_NOPATH)
rvw_add("review-record-sha: a made-up Head is allowed in a folder that is no git tree", "allow",
        rvw_body(head=RVW_UNKNOWN), cwd=RVW_NOTREE)
