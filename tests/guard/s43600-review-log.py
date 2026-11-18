# section 43600
FAMILY = "review-log"
#
# The review log a PR comment carries (decision pr-review-record). A comment whose first line is exactly the marker
# is a record, and merge/merge.py parse_review reads it. A body that parse_review refuses is a log the merge tool
# cannot use, so the merge stops on it. Three paths post a comment: the add and the update of the GitHub comment
# tools, and a Bash `gh pr comment` or `gh api ... -f body=`, whose body the guard reads from the command line.
# Two rules judge each path, for a body whose first line is the marker:
#
# review-log-form  parse_review(body) is None: refused. The reason names the one form to use, `merge <pr> --review-record
#                  --head <sha> ...`, whose printed text is posted as is.
# review-log-sha   the body parses, and a 40-hex sha on its Head or Fix check line does not resolve with
#                  `git cat-file -e <sha>^{commit}` in the call's checkout: refused. The reason tells the reader to fetch,
#                  since the commit may be on origin. A check that cannot run allows: no git on PATH, or no checkout in
#                  the call's folder.
#
# A body whose first line is not the marker is no log, so neither rule judges it. The matcher that routes the two
# comment tools to the guard is pinned in lint/test_settings_matcher.py (JudgedToolMatcher).
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
RVW_FORM = "review-log-form"
RVW_SHA = "review-log-sha"
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
        sys.exit("fixture setup failed in the review-log fixtures: " + what)


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


def _rvw_merge_module():
    """merge/merge.py, loaded from its file: the one home of the record's form (parse_review and review_body)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("review_log_under_test", os.path.join(REPO, "merge", "merge.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    parse = _rvw_merge_module().parse_review
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


def rvw_quoted(body):
    """The body as one double-quoted shell word. Inside double quotes these characters expand, so a body that holds one
    would not post as written."""
    _rvw_need(not any(ch in body for ch in '"$`\\'), "a log body holds a character a double-quoted shell word expands")
    return body


def rvw_gh_pr_comment(name, expected, body, rule=None, carries=()):
    """A Bash `gh pr comment 12 --body` call that posts `body`, run in the fixture checkout."""
    sh(name, 'gh pr comment 12 --body "%s"' % rvw_quoted(body), expected, rule=rule, cwd=RVW_REPO, carries=carries)


def rvw_gh_api_comment(name, expected, body, rule=None, carries=()):
    """A Bash `gh api` call that posts `body` as a new comment on issue 12, run in the fixture checkout."""
    sh(name, 'gh api repos/%s/%s/issues/12/comments -f body="%s"' % (RVW_OWNER, RVW_NAME, rvw_quoted(body)),
       expected, rule=rule, cwd=RVW_REPO, carries=carries)


# The merge tool's own printed text: merge --review-record prints review_body without its last newline. The GitHub
# footer follows a rule line, and parse_review stops reading at that rule line.
RVW_TOOL_OUT = _rvw_merge_module().review_body(12, RVW_HEAD, "normal", "no", [(1, "reviewer", "sonnet", "PASS")],
                                               "not owed").rstrip("\n")

# ---- review-log-form: a body whose first line is the marker must parse. Refused forms, then the controls.
rvw_add("review-log-form: a record whose Kind is free text is refused", "deny", RVW_HAND_KIND,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-log-form: a round line with no role is refused", "deny", RVW_HAND_ROUND,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-log-form: a rounds summary line is refused", "deny", RVW_HAND_SUMMARY,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-log-form: a free-text Fix check line is refused", "deny", RVW_HAND_FIX,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-log-form: the marker with no fields after it is refused", "deny", RVW_HAND_MARKER,
        rule=RVW_FORM, carries=RVW_REMEDY)
rvw_update("review-log-form: an update that holds a hand-typed Kind line is refused", "deny", RVW_HAND_KIND,
           rule=RVW_FORM, carries=RVW_REMEDY)
rvw_add("review-log-form: a 10-character Head is refused by form", "deny", rvw_body(head=RVW_HEAD[:10]),
        rule=RVW_FORM, carries=RVW_REMEDY)
# The same hand-typed log, posted with gh from the Bash tool, is judged the same way.
rvw_gh_pr_comment("review-log-form: a Bash gh pr comment that posts a hand-typed review log is refused", "deny",
                  RVW_HAND_KIND, rule=RVW_FORM, carries=RVW_REMEDY)

rvw_add("review-log-form: a tool-form record for a head that resolves is allowed", "allow", rvw_body())
rvw_update("review-log-form: an update with a tool-form record for a head that resolves is allowed", "allow",
           rvw_body())
rvw_add("review-log-form: a full-size record, three rounds and a Fix check, is allowed", "allow",
        rvw_body(rows=RVW_FULL_ROWS, fix=RVW_FIX))
rvw_add("review-log-form: the merge tool's printed record, then the GitHub footer, is allowed", "allow",
        RVW_TOOL_OUT + "\n---\n_Generated by [Claude Code](https://claude.ai/code)_\n")
rvw_add("review-log-form: a body with no marker is allowed", "allow",
        "Lint PASS on the head. Merging after CI.\n")
rvw_add("review-log-form: a body with no marker that holds the hand-typed Kind line is allowed", "allow",
        RVW_HAND_KIND.split("\n", 1)[1])
rvw_gh_pr_comment("review-log-form: a Bash gh pr comment whose body does not open with the marker is allowed", "allow",
                  "Lint PASS on the head. Merging after CI.\n")

# ---- review-log-sha: a body that parses names shas that must resolve in the call's checkout.
rvw_add("review-log-sha: a record whose Head is a made-up sha is refused", "deny", rvw_body(head=RVW_UNKNOWN),
        rule=RVW_SHA)
# No rule is named here: this case reads the remedy, so a rule rename fails only the cases that name it.
rvw_add("review-log-sha: the refusal for a made-up Head tells the reader to fetch", "deny",
        rvw_body(head=RVW_UNKNOWN), carries="fetch")
rvw_gh_api_comment("review-log-sha: a Bash gh api call that posts a log with a made-up Head is refused", "deny",
                   rvw_body(head=RVW_UNKNOWN), rule=RVW_SHA)
rvw_add("review-log-sha: a record whose Fix check sha is made up is refused", "deny", rvw_body(fix=RVW_UNKNOWN),
        rule=RVW_SHA)
rvw_update("review-log-sha: an update whose Head is a made-up sha is refused", "deny",
           rvw_body(head=RVW_UNKNOWN), rule=RVW_SHA)
rvw_add("review-log-sha: a Head sha in a checkout with no commit is refused", "deny", rvw_body(),
        rule=RVW_SHA, cwd=RVW_EMPTY)
rvw_add("review-log-sha: a Head and a Fix check that both resolve are allowed", "allow",
        rvw_body(fix=RVW_FIX))
rvw_add("review-log-sha: a made-up Head is allowed when no git runs on PATH", "allow",
        rvw_body(head=RVW_UNKNOWN), env_path=RVW_NOPATH)
rvw_add("review-log-sha: a made-up Head is allowed in a folder that is no git tree", "allow",
        rvw_body(head=RVW_UNKNOWN), cwd=RVW_NOTREE)
rvw_gh_api_comment("review-log-sha: a Bash gh api call whose body does not open with the marker is allowed", "allow",
                   "Review below.\n" + rvw_body(head=RVW_UNKNOWN))
