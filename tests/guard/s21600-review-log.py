# section 21600
FAMILY = "review-log"
#
# Decision pr-review-record. A comment whose body holds the review-record marker is refused unless the body parses as a
# record (merge/merge.py parse_review), its PR number is the target, and its Head is the PR's live head. The live head is
# one gh read per marked post. A post with no marker makes no read. The bodies come from the form's one home
# (merge/merge.py review_body), so a case cannot drift from the form the merge tool parses.
REVIEW_RULE = "pr-review-record"
MCP_COMMENT = "mcp__github__add_issue_comment"
MCP_UPDATE = "mcp__github__update_issue_comment"
REVIEW_PR = 12
REVIEW_COMMENT = 4242                         # a conversation comment on REVIEW_PR, answered by the record fakes; not 12, so a read that takes it for a pull request number finds none
REVIEW_COMMENTS = {REVIEW_COMMENT: REVIEW_PR}
REVIEW_LIVE = "3a7c9e21" * 5                  # the PR's live head, in every fake below
REVIEW_TAIL = REVIEW_LIVE[:32] + "0badbeef"   # the live head with a wrong tail, the way a hand-typed sha goes wrong
REVIEW_OLD = "5e0f1a2b" * 5                   # the head before a push
REVIEW_FIX_FROM = "9c4d7e10" * 5              # the reviewed head a fix check starts from; it differs from the record's Head
REVIEW_RENDER = "merge %d --review-record --head %s" % (REVIEW_PR, REVIEW_LIVE)  # the render command a head refusal prints
REVIEW_CALLS = "review-calls.log"             # the counted tool's log, read through gh_calls_taken
GHRECORD = os.path.join(ROOT, "ghrecord")                # the live head, for pull request 12 of any repo
GHRECORDREPO = os.path.join(ROOT, "ghrecordrepo")        # the same, and a read of any repo but y/x breaks
GHRECORDBROKEN = os.path.join(ROOT, "ghrecordbroken")    # every call fails, so the live head cannot be read
GHRECORDCOUNT = os.path.join(ROOT, "ghrecordcount")      # the same as GHRECORD, and every call is logged
GHRECORDDIR = os.path.join(ROOT, "record-bodies")        # the body files the Bash forms name
GHRECORDBRANCH = os.path.join(ROOT, "ghrecordbranch")    # a checkout on `feat`, the head branch of the fake's pull request 12
PR_CMD = "gh pr comment %d" % REVIEW_PR
API_CMD = "gh api repos/y/x/issues/%d/comments" % REVIEW_PR

_REVIEW_FORM = []


def review_form():
    """merge/merge.py, loaded by path: the one home of the record's form (REVIEW_MARKER, review_body, parse_review)."""
    if not _REVIEW_FORM:
        import importlib.util
        spec = importlib.util.spec_from_file_location("merge_under_test", os.path.join(HERE, "..", "merge", "merge.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _REVIEW_FORM.append(module)
    return _REVIEW_FORM[0]


def review_log(n=REVIEW_PR, head=REVIEW_LIVE, rounds=None, fix=None, net="not owed", guard="yes", footer=False):
    """A record body, rendered by review_body. `footer` adds the attribution footer a posted comment carries, after a `---` line."""
    rounds = rounds or [(1, "reviewer", "claude-sonnet-5-5", "PASS")]
    text = review_form().review_body(n, head, "normal", guard, rounds, net, fix=fix)
    return text + "---\nGenerated with Claude Code\n" if footer else text


REVIEW_MARKER_TEXT = review_form().REVIEW_MARKER
# A comment that names the marker in prose, below its first line. The marker is a record only as the exact first line.
REVIEW_PROSE = "Lane note.\nThe record starts with %s on its first line, see the decision." % REVIEW_MARKER_TEXT
# The full size of the form: three rounds and a Fix check, with the footer a posted comment carries.
REVIEW_FULL = review_log(rounds=[(1, "reviewer", "claude-sonnet-5-5", "FAIL"), (1, "design-reviewer", "claude-opus-5-5", "PASS"),
                                    (2, "reviewer", "claude-sonnet-5-5", "PASS"), (3, "reviewer", "claude-sonnet-5-5", "PASS")],
                            fix=(REVIEW_FIX_FROM, "reviewer", "claude-sonnet-5-5", "PASS"), net="positive", footer=True)
REVIEW_NO_HEAD = "\n".join(line for line in review_log().splitlines() if not line.startswith("Head:")) + "\n"
REVIEW_SHORT_HEAD = review_log().replace("Head: " + REVIEW_LIVE, "Head: " + REVIEW_LIVE[:39])
REVIEW_SKIPPED_ROUND = review_log(rounds=[(1, "reviewer", "claude-sonnet-5-5", "PASS"), (3, "reviewer", "claude-sonnet-5-5", "PASS")])
# Bodies for the form cases. A record is its lines up to the CI line; prose after that line, with no `---`, is not a record.
REVIEW_TRAILING = review_log() + "Lane note after the record.\n"
REVIEW_FULL_TRAILING = REVIEW_FULL.split("---\n", 1)[0] + "Lane note after the record.\n"   # the full size, with the prose
REVIEW_FOOTED = review_log(footer=True)                                              # a record, then `---` and the footer
REVIEW_FENCED = "```\n" + review_log() + "```\n"                                     # a code fence, then the marker
# The bodies the Bash forms read from a file, one file each in the record folder (build_record_fixtures writes them).
RECORD_BODY_FILES = {"trailing.md": REVIEW_TRAILING, "full-trailing.md": REVIEW_FULL_TRAILING, "footed.md": REVIEW_FOOTED,
                     "fenced.md": REVIEW_FENCED, "prose.md": REVIEW_PROSE}
# A form refusal's message names the `---` line and the footer. The form text is pinned on every refusal of a malformed body.
FORM_TEXT = ("a line exactly `---`", "footer")
REVIEW_COMMENT_ID = 4417
API_EDIT_CMD = "gh api -X PATCH repos/y/x/issues/comments/%d" % REVIEW_COMMENT_ID


def build_record_fixtures():
    """The pull request tools the record cases name, and the body files the Bash forms read. One folder each."""
    make_fake_gh(GHRECORD, "main", need=["12"], head_sha=REVIEW_LIVE, comments=REVIEW_COMMENTS)
    make_fake_gh(GHRECORDREPO, "main", need=["y/x", "12"], head_sha=REVIEW_LIVE, comments=REVIEW_COMMENTS)
    make_fake_gh(GHRECORDBROKEN, "main", broken=True, head_sha=REVIEW_LIVE)
    write(os.path.join(GHRECORDDIR, "ok.md"), review_log())
    write(os.path.join(GHRECORDDIR, "wrong_tail.md"), review_log(head=REVIEW_TAIL))
    write(os.path.join(GHRECORDDIR, "stale.md"), review_log(head=REVIEW_OLD))
    for name, text in RECORD_BODY_FILES.items():
        write(os.path.join(GHRECORDDIR, name), text)
    write(os.path.join(GHRECORDDIR, "trailing.json"), json.dumps({"body": REVIEW_TRAILING}))
    make_repo(GHRECORDBRANCH, {"lane.txt": "lane\n"})
    switched = run_vcs(GHRECORDBRANCH, "checkout", "-q", "-b", "feat")
    if switched.returncode != 0:
        sys.exit("fixture setup failed in build_record_fixtures: checking out feat in %r failed. stderr: %s"
                 % (GHRECORDBRANCH, switched.stderr.strip()))


lazy_fixture([GHRECORD, GHRECORDREPO, GHRECORDBROKEN, GHRECORDDIR, GHRECORDBRANCH], build_record_fixtures)


def mcp_input(body, number=REVIEW_PR, comment_id=None):
    """The input of one call of the comment tool on pull request `number` of y/x. With `comment_id`, the input of the update
    tool on that comment: it names no pull request."""
    if comment_id is not None:
        return {"owner": "y", "repo": "x", "comment_id": comment_id, "body": body}
    return {"owner": "y", "repo": "x", "issue_number": number, "body": body}


def mcp_post(name, body, expected, rule=None, carries=(), number=REVIEW_PR, comment_id=None):
    """A case for one call of the comment tool, or of the update tool on `comment_id`. It reads the live head from the repo the input names (GHRECORDREPO)."""
    add(name, expected, rule=rule, tool=MCP_COMMENT if comment_id is None else MCP_UPDATE, cwd=NOGIT,
        env_path=GHRECORDREPO + os.pathsep + PY_PATH, carries=carries, **mcp_input(body, number, comment_id))


def bash_post(name, command, expected, rule=None, carries=()):
    """A case for one Bash command that posts a comment on pull request 12. Its live head is read from the cwd's repo."""
    sh(name, command, expected, rule=rule, cwd=NOGIT, env_path=GHRECORD + os.pathsep + PY_PATH, carries=carries)


def inline_forms(body):
    """The Bash forms that post `body` as text, one command each. The body is single-quoted, so its # and <!-- are text."""
    quoted = "'%s'" % body
    return [("gh pr comment --body", "%s --body %s" % (PR_CMD, quoted)),
            ("gh pr comment -b", "%s -b %s" % (PR_CMD, quoted)),
            ("gh api -f body=", "%s -f 'body=%s'" % (API_CMD, body)),
            ("gh api --field body=", "%s --field 'body=%s'" % (API_CMD, body)),
            ("gh api --raw-field body=", "%s --raw-field 'body=%s'" % (API_CMD, body))]


def file_forms(path):
    """The Bash forms that post the body in the file at `path`."""
    return [("gh pr comment --body-file", "%s --body-file %s" % (PR_CMD, path)),
            ("gh pr comment -F", "%s -F %s" % (PR_CMD, path)),
            ("gh api -F body=@", "%s -F body=@%s" % (API_CMD, path))]


def all_forms(body, path):
    """Every Bash form that posts a body: the text forms carry `body`, and the file forms read `path`, which holds the same body."""
    return inline_forms(body) + file_forms(path)


# A record for the live head is allowed, whatever its form, in the MCP form and in every Bash form.
mcp_post("review-log: a record at the live head is allowed, MCP add_issue_comment", review_log(), "allow")
mcp_post("review-log: a full-size record with its footer is allowed, MCP add_issue_comment", REVIEW_FULL, "allow")
for _label, _command in all_forms(review_log(), os.path.join(GHRECORDDIR, "ok.md")):
    bash_post("review-log: a record at the live head is allowed, %s" % _label, _command, "allow")

# A comment with no marker is not judged, so it is allowed, and it makes no gh read (checked below).
mcp_post("review-log: a comment with no marker is allowed, MCP add_issue_comment", "Round 1 ran. No review log yet.", "allow")
mcp_post("review-log: a comment that names the record without its marker is allowed",
         "review-log is the form, see the decision.", "allow")
mcp_post("review-log: an empty comment is allowed, MCP add_issue_comment", "", "allow")
bash_post("review-log: a lone quote in a comment with no marker is allowed", PR_CMD + " --body \"Don't merge yet\"", "allow")

# A record for a head other than the live one is refused. The refusal prints the render command for the live head.
mcp_post("review-log: a wrong head tail is refused, MCP add_issue_comment", review_log(head=REVIEW_TAIL), "deny",
         rule=REVIEW_RULE, carries=(REVIEW_RENDER,))
for _label, _command in all_forms(review_log(head=REVIEW_TAIL), os.path.join(GHRECORDDIR, "wrong_tail.md")):
    bash_post("review-log: a wrong head tail is refused, %s" % _label, _command, "deny",
              rule=REVIEW_RULE, carries=(REVIEW_RENDER,))
mcp_post("review-log: a stale record is refused, MCP add_issue_comment", review_log(head=REVIEW_OLD), "deny",
         rule=REVIEW_RULE, carries=(REVIEW_RENDER,))
bash_post("review-log: a stale record is refused, gh pr comment --body-file",
          "%s --body-file %s" % (PR_CMD, os.path.join(GHRECORDDIR, "stale.md")), "deny", rule=REVIEW_RULE, carries=(REVIEW_RENDER,))
# A body the shell builds from a file is judged by that file: a command substitution reads it, and so does a piped cat.
bash_post("review-log: a stale record read by a command substitution is refused, gh pr comment --body $(cat)",
          "%s --body \"$(cat %s)\"" % (PR_CMD, os.path.join(GHRECORDDIR, "stale.md")), "deny", rule=REVIEW_RULE, carries=(REVIEW_RENDER,))
bash_post("review-log: a stale record piped in is refused, cat | gh pr comment -F -",
          "cat %s | %s -F -" % (os.path.join(GHRECORDDIR, "stale.md"), PR_CMD), "deny", rule=REVIEW_RULE, carries=(REVIEW_RENDER,))
# A piped body the guard cannot read at all is allowed, with a note (checked below). Its command names no file.
bash_post("review-log: a plain stdin body the guard cannot read is allowed, some_cmd | gh pr comment -F -",
          "some_cmd | %s -F -" % PR_CMD, "allow")

# A record for another pull request is refused.
mcp_post("review-log: a record for another pull request is refused, MCP add_issue_comment", review_log(n=REVIEW_PR + 1),
         "deny", rule=REVIEW_RULE, number=REVIEW_PR)
bash_post("review-log: a record for another pull request is refused, gh pr comment --body",
          "%s --body '%s'" % (PR_CMD, review_log(n=REVIEW_PR + 1)), "deny", rule=REVIEW_RULE)
bash_post("review-log: a record for another pull request is refused, gh api -f body=",
          "%s -f 'body=%s'" % (API_CMD, review_log(n=REVIEW_PR + 1)), "deny", rule=REVIEW_RULE)

# A body that holds the marker but does not parse is refused, from its empty state to its near misses.
mcp_post("review-log: a marker with no record is refused, MCP add_issue_comment", REVIEW_MARKER_TEXT, "deny", rule=REVIEW_RULE)
# A body is a record only when its first line is the marker (merge/merge.py parse_review). Prose that names it lower down is a comment.
mcp_post("review-log: a marker in prose below the first line is allowed, MCP add_issue_comment", REVIEW_PROSE, "allow")
bash_post("review-log: a marker in prose below the first line is allowed, gh pr comment --body",
          "%s --body '%s'" % (PR_CMD, REVIEW_PROSE), "allow")
mcp_post("review-log: a record with a round skipped is refused, MCP add_issue_comment", REVIEW_SKIPPED_ROUND,
         "deny", rule=REVIEW_RULE)
bash_post("review-log: a record with no Head line is refused, gh pr comment -b", "%s -b '%s'" % (PR_CMD, REVIEW_NO_HEAD),
          "deny", rule=REVIEW_RULE)
bash_post("review-log: a record with a 39-digit Head is refused, gh api -f body=",
          "%s -f 'body=%s'" % (API_CMD, REVIEW_SHORT_HEAD), "deny", rule=REVIEW_RULE)
# Two bodies in one call. gh rejects a repeated `-f body=`, but the guard judges every marked body it reads. A good record
# and a stale one are refused whichever comes first, so a check that reads only the first or only the last body fails here.
TWO_BODIES = "%s -f 'body=%s' -f 'body=%s'"
bash_post("review-log: a good record then a stale one in one call is refused, gh api -f body= twice",
          TWO_BODIES % (API_CMD, review_log(), review_log(head=REVIEW_OLD)), "deny", rule=REVIEW_RULE,
          carries=(REVIEW_RENDER,))
bash_post("review-log: a stale record then a good one in one call is refused, gh api -f body= twice",
          TWO_BODIES % (API_CMD, review_log(head=REVIEW_OLD), review_log()), "deny", rule=REVIEW_RULE,
          carries=(REVIEW_RENDER,))


# The form cases. A record is its lines up to the CI line: prose after that line, with no `---`, is refused. The judge sees
# every post, and an edit too: the PATCH route and --edit-last are the two places a body is changed in place.
def edit_forms(body, path):
    """The Bash forms that edit a comment, or post it with --edit-last, one command each."""
    return [("gh api -X PATCH -f body=", "%s -f 'body=%s'" % (API_EDIT_CMD, body)),
            ("gh api -X PATCH -F body=@", "%s -F body=@%s" % (API_EDIT_CMD, path)),
            ("gh pr comment --edit-last --body", "%s --edit-last --body '%s'" % (PR_CMD, body))]


def every_form(body, path):
    """Every Bash form that posts or edits a body: the posts of all_forms, then the edits."""
    return all_forms(body, path) + edit_forms(body, path)


TRAILING_PATH = os.path.join(GHRECORDDIR, "trailing.md")
# The forms the pins name. A trailing-prose body is refused on each of them, on the decision alone.
PIN_FORM_LABELS = ("gh pr comment --body", "gh pr comment -b", "gh pr comment --body-file", "gh pr comment -F",
                   "gh api -f body=", "gh api -F body=@", "gh pr comment --edit-last --body")

# Prose after the CI line is refused on each form that posts it.
mcp_post("review-log: prose after the CI line is refused, MCP add_issue_comment", REVIEW_TRAILING, "deny", rule=REVIEW_RULE)
for _label, _command in every_form(REVIEW_TRAILING, TRAILING_PATH):
    if _label in PIN_FORM_LABELS:
        bash_post("review-log: prose after the CI line is refused, %s" % _label, _command, "deny", rule=REVIEW_RULE)

# Prose after the CI line is refused on every Bash form, edits included, and each refusal also names the form text. Its message
# carries the `---` line and the footer.
for _label, _command in every_form(REVIEW_TRAILING, TRAILING_PATH):
    bash_post("review-log: prose after the CI line is refused and names the form, %s" % _label, _command, "deny",
              rule=REVIEW_RULE, carries=FORM_TEXT)
mcp_post("review-log: prose after the CI line is refused and names the form, MCP add_issue_comment", REVIEW_TRAILING,
         "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
# The malformed bodies in the add and post cases also name the form text: the same judge refuses them.
mcp_post("review-log: a marker with no record is refused and names the form, MCP add_issue_comment", REVIEW_MARKER_TEXT,
         "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
mcp_post("review-log: a record with a round skipped is refused and names the form, MCP add_issue_comment",
         REVIEW_SKIPPED_ROUND, "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
bash_post("review-log: a record with no Head line is refused and names the form, gh pr comment -b",
          "%s -b '%s'" % (PR_CMD, REVIEW_NO_HEAD), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
bash_post("review-log: a record with a 39-digit Head is refused and names the form, gh api -f body=",
          "%s -f 'body=%s'" % (API_CMD, REVIEW_SHORT_HEAD), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)

# ALLOW CONTROLS on every form. A body that is not a record by form is allowed: a record with its footer, the marker in
# prose below line 1, and a code fence then the marker. A bare record at the live head is allowed on the edit forms too.
mcp_post("review-log: a record with its footer is allowed, MCP add_issue_comment", REVIEW_FOOTED, "allow")
mcp_post("review-log: a code fence, then the marker, is allowed, MCP add_issue_comment", REVIEW_FENCED, "allow")
for _label, _command in edit_forms(review_log(), os.path.join(GHRECORDDIR, "ok.md")):
    bash_post("review-log: a record at the live head is allowed, %s" % _label, _command, "allow")
for _body, _file, _what in ((REVIEW_FOOTED, "footed.md", "a record with its footer"),
                            (REVIEW_PROSE, "prose.md", "the marker in prose below the first line"),
                            (REVIEW_FENCED, "fenced.md", "a code fence, then the marker")):
    for _label, _command in every_form(_body, os.path.join(GHRECORDDIR, _file)):
        bash_post("review-log: %s is allowed, %s" % (_what, _label), _command, "allow")


# THE ISSUE WORD AND THE ANSI-C QUOTING. `gh issue comment` posts to the same pull request, and merge --reviewed reads issue
# comments, so it is judged as `gh pr comment` is. Bash reads `$'...'` with its escapes decoded, so a body in that form can hold
# the marker. The ANSI-C cases below pin that the guard decodes each `$'...'` word as Bash does, then judges the decoded body.
ISSUE_CMD = "gh issue comment %d" % REVIEW_PR


def issue_forms(body, path):
    """The Bash forms that post `body` through `gh issue comment`, one command each: the text forms carry `body`, the file forms
    read `path`. inline_forms and file_forms cannot take this word: they also hold the gh api forms, which have no issue word."""
    quoted = "'%s'" % body
    return [("gh issue comment --body", "%s --body %s" % (ISSUE_CMD, quoted)),
            ("gh issue comment -b", "%s -b %s" % (ISSUE_CMD, quoted)),
            ("gh issue comment --body-file", "%s --body-file %s" % (ISSUE_CMD, path)),
            ("gh issue comment -F", "%s -F %s" % (ISSUE_CMD, path))]


def ansi_c(text):
    """The `$'...'` form of `text`, as bash reads it: a backslash, a single quote and a newline are written as escapes."""
    return "$'%s'" % text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


# `gh issue comment` is judged as `gh pr comment` is: prose after the CI line is refused on every form. Each refusal names the
# form, as the gh pr comment refusal does.
for _label, _command in issue_forms(REVIEW_TRAILING, TRAILING_PATH):
    bash_post("review-log: prose after the CI line is refused, %s" % _label, _command, "deny", rule=REVIEW_RULE,
              carries=FORM_TEXT)
# A record for an older head is refused on gh issue comment, with the render line.
bash_post("review-log: a stale record is refused, gh issue comment --body-file",
          "%s --body-file %s" % (ISSUE_CMD, os.path.join(GHRECORDDIR, "stale.md")), "deny", rule=REVIEW_RULE,
          carries=(REVIEW_RENDER,))
# ALLOW CONTROLS for gh issue comment: a bare record at the live head is allowed on every form, as on gh pr comment.
for _label, _command in issue_forms(review_log(), os.path.join(GHRECORDDIR, "ok.md")):
    bash_post("review-log: a record at the live head is allowed, %s" % _label, _command, "allow")

# `gh issue comment N --edit-last` edits the comment, and is judged on its form before any read, as a post is.
bash_post("review-log: prose after the CI line is refused, gh issue comment 12 --edit-last --body",
          "%s --edit-last --body '%s'" % (ISSUE_CMD, REVIEW_TRAILING), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)


# THE ANSI-C FORMS, on `gh issue comment`. The guard decodes a `$'...'` word as bash does, then judges the body. Each deny holds
# prose after the CI line, written in its form, so the refusal turns on the decode. Each allow control holds the same form in a
# bare record: in the marker's brackets where the form can write them, else after `---`, since a record has no free text and the
# parse ignores the footer.
def ansi_word(text, sub=None, tail=""):
    """A `$'...'` word for `text`: backslashes, quotes and newlines escaped as ansi_c does, each char in `sub` (a dict) written as
    its escape, then `tail`, written as it is, so a case names each escape it means."""
    body = ansi_c(text)[2:-1]
    for char, escape in (sub or {}).items():
        body = body.replace(char, escape)
    return "$'" + body + tail + "'"


def ansi_issue(name, word, expected):
    """A case for `gh issue comment 12 --body` with the body `word`. A refusal names the record's form, as the other forms do."""
    deny = expected == "deny"
    bash_post(name, "%s --body %s" % (ISSUE_CMD, word), expected, rule=REVIEW_RULE if deny else None,
              carries=FORM_TEXT if deny else ())


RECORD_HEX = {"<": r"\x3c", ">": r"\x3e"}   # the marker's brackets, in each escape form
RECORD_UNI = {"<": r"<", ">": r">"}
RECORD_OCT = {"<": r"\074", ">": r"\076"}
RECORD_FIRST = REVIEW_MARKER_TEXT + "\n"     # the record's first line, and the lines after it
RECORD_REST = review_log()[len(RECORD_FIRST):]

ansi_issue("review-log: prose after the CI line is refused, ANSI-C backslash-quote and an apostrophe in prose, gh issue comment --body",
           ansi_word(review_log(), None, r"\'Lane note: it\'s after the record.\n"), "deny")
ansi_issue("review-log: a record with its footer is allowed, ANSI-C backslash-quote and an apostrophe, gh issue comment --body",
           ansi_word(review_log(), None, r"---\nGenerated with Claude Code, it\'s free\n"), "allow")
ansi_issue("review-log: prose after the CI line is refused, ANSI-C hex escapes, gh issue comment --body",
           ansi_word(review_log(), RECORD_HEX, r"Lane note: \x41fter the record.\n"), "deny")
ansi_issue("review-log: a bare record in ANSI-C hex escapes is allowed, gh issue comment --body",
           ansi_word(review_log(), RECORD_HEX), "allow")
ansi_issue("review-log: prose after the CI line is refused, ANSI-C unicode escapes, gh issue comment --body",
           ansi_word(review_log(), RECORD_UNI, r"Lane note: After the record.\n"), "deny")
ansi_issue("review-log: a bare record in ANSI-C unicode escapes is allowed, gh issue comment --body",
           ansi_word(review_log(), RECORD_UNI), "allow")
ansi_issue("review-log: prose after the CI line is refused, ANSI-C octal escapes, gh issue comment --body",
           ansi_word(review_log(), RECORD_OCT, r"Lane note: \101fter the record.\n"), "deny")
ansi_issue("review-log: a bare record in ANSI-C octal escapes is allowed, gh issue comment --body",
           ansi_word(review_log(), RECORD_OCT), "allow")
ansi_issue("review-log: prose after the CI line is refused, ANSI-C tab escape, gh issue comment --body",
           ansi_word(review_log(), None, r"Lane note:\tafter the record.\n"), "deny")
ansi_issue("review-log: a record with its footer is allowed, ANSI-C tab escape, gh issue comment --body",
           ansi_word(review_log(), None, r"---\nGenerated\twith Claude Code\n"), "allow")
ansi_issue("review-log: prose before a NUL cut is refused, gh issue comment --body",
           ansi_word(review_log(), None, r"Lane note after the record.\n\0---\nGenerated with Claude Code\n"), "deny")
ansi_issue("review-log: a bare record before a NUL cut is allowed, gh issue comment --body",
           ansi_word(review_log(), None, r"\0Lane note after the cut.\n"), "allow")
ansi_issue("review-log: prose after the CI line is refused, ANSI-C word then double quotes, gh issue comment --body",
           ansi_word(RECORD_FIRST) + '"' + RECORD_REST + "Lane note after the record.\n" + '"', "deny")
ansi_issue("review-log: a bare record in an ANSI-C word then double quotes is allowed, gh issue comment --body",
           ansi_word(RECORD_FIRST) + '"' + RECORD_REST + '"', "allow")
ansi_issue("review-log: prose after the CI line is refused, double quotes then ANSI-C word, gh issue comment --body",
           '"' + RECORD_FIRST + '"' + ansi_word(RECORD_REST + "Lane note after the record.\n"), "deny")
ansi_issue("review-log: a bare record in double quotes then an ANSI-C word is allowed, gh issue comment --body",
           '"' + RECORD_FIRST + '"' + ansi_word(RECORD_REST), "allow")
ansi_issue("review-log: prose after the CI line is refused, a // inside the ANSI-C word, gh issue comment --body",
           ansi_word(review_log(), None, "//Lane note after the record.\n"), "deny")
ansi_issue("review-log: a record with its footer is allowed, a // inside the ANSI-C word, gh issue comment --body",
           ansi_word(review_log(), None, "---\n//x and /* y\n"), "allow")
ansi_issue("review-log: prose after the CI line is refused, a /* inside the ANSI-C word, gh issue comment --body",
           ansi_word(review_log(), None, "/*Lane note after the record.\n"), "deny")
ansi_issue("review-log: a record with its footer is allowed, a /* inside the ANSI-C word, gh issue comment --body",
           ansi_word(review_log(), None, "---\nSee /*x and // y\n"), "allow")

# The guard judges a `$'...'` body on its decoded text, so prose after the CI line is refused in that form too, as in plain quotes.
bash_post("review-log: prose after the CI line is refused, gh pr comment --body with ANSI-C quoting",
          "%s --body %s" % (PR_CMD, ansi_c(REVIEW_TRAILING)), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
bash_post("review-log: prose after the CI line is refused, gh api -X PATCH -f with ANSI-C quoting",
          "%s -f %s" % (API_EDIT_CMD, ansi_c("body=" + REVIEW_TRAILING)), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
# ALLOW CONTROLS for the ANSI-C forms: a bare record at the live head is allowed on the post and both gh api routes, the marker in
# prose below line 1 is allowed, and a plain ANSI-C text body is allowed.
bash_post("review-log: a record at the live head is allowed, gh pr comment --body with ANSI-C quoting",
          "%s --body %s" % (PR_CMD, ansi_c(review_log())), "allow")
bash_post("review-log: a record at the live head is allowed, gh api -f with ANSI-C quoting",
          "%s -f %s" % (API_CMD, ansi_c("body=" + review_log())), "allow")
bash_post("review-log: a record at the live head is allowed, gh api -X PATCH -f with ANSI-C quoting",
          "%s -f %s" % (API_EDIT_CMD, ansi_c("body=" + review_log())), "allow")
bash_post("review-log: the marker in prose below the first line is allowed, gh pr comment --body with ANSI-C quoting",
          "%s --body %s" % (PR_CMD, ansi_c(REVIEW_PROSE)), "allow")
bash_post("review-log: a plain ANSI-C text body is allowed, gh pr comment --body $'plain text'",
          "%s --body $'plain text'" % PR_CMD, "allow")

# The guard does not resolve a shell variable, so a body held in one is not judged: a named limit, allowed on purpose.
bash_post("review-log: a body in a shell variable is allowed, a named limit, gh pr comment --body \"$BODY\"",
          "%s --body \"$BODY\"" % PR_CMD, "allow")

# MORE NAMED LIMITS. The guard judges a body written in the command, or in a file a form names. Three forms keep the body out of
# its reach, so a malformed record is allowed on each: a command substitution, a JSON file read by --input, and a full URL.
bash_post("review-log: a body from a command substitution is allowed, a named limit, gh pr comment --body \"$(printf ...)\"",
          PR_CMD + " --body \"$(printf '%s' '" + REVIEW_TRAILING + "')\"", "allow")
bash_post("review-log: a body in a JSON file read by --input is allowed, a named limit, gh api --input",
          "%s --input %s" % (API_CMD, os.path.join(GHRECORDDIR, "trailing.json")), "allow")
bash_post("review-log: a full-URL gh api post with a malformed record is allowed, a named limit, gh api https://...",
          "gh api https://api.github.com/repos/y/x/issues/%d/comments -f 'body=%s'" % (REVIEW_PR, REVIEW_TRAILING), "allow")

# A marked body in a heredoc is judged as a quoted body is: the text between the `<<'EOF'` line and the `EOF` line. A `#` inside a
# quoted body is text, not a shell comment, so the judge reads on past it.
bash_post("review-log: prose after the CI line is refused, a heredoc body, gh pr comment --body-file -",
          "%s --body-file - <<'EOF'\n%sEOF\n" % (PR_CMD, REVIEW_TRAILING), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
# The `#` opens a line of prose after the CI line. A reader that cuts a quoted body at a `#` sees a bare record, and allows it.
HASH_TRAILING = REVIEW_TRAILING.replace("Lane note after the record.\n", "# Lane note after the record.\n")
bash_post("review-log: prose after the CI line is refused, a # at a line start in a quoted body, gh pr comment --body",
          "%s --body '%s'" % (PR_CMD, HASH_TRAILING), "deny", rule=REVIEW_RULE, carries=FORM_TEXT)
# The Grant line holds `#12` at a word start. A reader that cuts at that `#` leaves `Grant: ` with no round line after it, and refuses.
GRANT_TEXT = "#%d, item 219 a, owner, 2026-11-04 17:44 CST" % REVIEW_PR
GRANT_ROUNDS = [(1, "reviewer", "claude-sonnet-5-5", "FAIL"), (2, "reviewer", "claude-sonnet-5-5", "PASS"),
                (3, "reviewer", "claude-sonnet-5-5", "PASS"), (4, "reviewer", "claude-sonnet-5-5", "PASS")]
GRANT_BODY = review_form().review_body(REVIEW_PR, REVIEW_LIVE, "normal", "yes", GRANT_ROUNDS, "not owed", grant=GRANT_TEXT)
bash_post("review-log: a granted record with a # in its Grant line is allowed, gh pr comment --body",
          "%s --body '%s'" % (PR_CMD, GRANT_BODY), "allow")


def review_counted_fake():
    """The counted pull request tool, with its log emptied. Each call it answers is logged."""
    make_fake_gh(GHRECORDCOUNT, "main", need=["12"], head_sha=REVIEW_LIVE, comments=REVIEW_COMMENTS,
                 count_file=os.path.join(GHRECORDCOUNT, REVIEW_CALLS))
    gh_calls_taken(GHRECORDCOUNT, REVIEW_CALLS)


def review_case(tool, tool_input, env_path, cwd=NOGIT):
    """The case dict decide() reads, for one post judged with the PATH `env_path`, from the folder `cwd` (no repo by default)."""
    return {"raw": None, "tool": tool, "cwd": cwd, "session": None, "env_path": env_path, "config": None,
            "agent_id": None, "agent_type": None, "temp": None, "load": None, "env": None, "transcript": None,
            "tool_input": tool_input}


def review_counter_works():
    """-> (ok, note). The counted tool logs one call made to it directly. Without this, an empty log proves no zero reads."""
    review_counted_fake()
    env = dict(os.environ, PATH=fake_gh_path(GHRECORDCOUNT))
    program = shutil.which("gh", path=env["PATH"])
    if not program:
        return False, "the counted pull request tool is not on PATH, so no call can be counted"
    subprocess.run([program, "api", "repos/y/x/pulls/%d" % REVIEW_PR], capture_output=True, text=True, env=env, timeout=60)
    logged = gh_calls_taken(GHRECORDCOUNT, REVIEW_CALLS)
    if len(logged) != 1:
        return False, "the counter logged %d call(s) for one direct call, so an empty log proves no zero reads" % len(logged)
    return True, "the counter logs a direct call"


def review_reads(tool, tool_input, want, reads, cwd=NOGIT, path_dirs=()):
    """A checker for one post: the guard says `want`, and the post makes `reads` gh calls, the one live-head read. `cwd` is the
    folder the post runs in. `path_dirs` are folders the guard's PATH adds after the fake gh's, such as git's for a post with no number."""
    def check():
        if reads == 0:
            ok, note = review_counter_works()
            if not ok:
                return False, note
        review_counted_fake()
        env_path = os.pathsep.join((GHRECORDCOUNT,) + tuple(path_dirs) + (PY_PATH,))
        decision, reason = decide(review_case(tool, tool_input, env_path, cwd))
        calls = gh_calls_taken(GHRECORDCOUNT, REVIEW_CALLS)
        if decision != want:
            return False, "want %s, got %s: %s" % (want, decision, reason[:90])
        if len(calls) != reads:
            return False, "%d gh call(s) wanted for the live head, %d seen: %r" % (reads, len(calls), calls)
        return True, "%s, with %d gh call(s)" % (want, reads)
    FIXTURELESS_CHECKS.add(check)
    return check


def review_note(tool, tool_input, env_path):
    """A checker for one post the guard must allow, with a note on stderr that names the review record."""
    def check():
        decision, reason = decide(review_case(tool, tool_input, env_path))
        note = LAST_RUN.get("stderr", "").strip()
        if decision != "allow":
            return False, "want allow, got %s: %s" % (decision, reason[:90])
        if "review" not in note.lower():
            return False, "allowed, but no note on stderr names the review record: %r" % note[:120]
        return True, "allowed, with a note on stderr"
    FIXTURELESS_CHECKS.add(check)
    return check


def review_fixtures_check():
    """The bodies the cases post parse as their names say, so each refusal above turns on its head, its PR number or its form."""
    form = review_form()
    good = form.parse_review(review_log())
    if not good or good["head"] != REVIEW_LIVE or good["n"] != REVIEW_PR:
        return False, "the ok record does not parse for pull request %d at the live head: %r" % (REVIEW_PR, good)
    if (form.parse_review(review_log(head=REVIEW_TAIL)) or {}).get("head") != REVIEW_TAIL:
        return False, "the wrong-tail record does not parse with its wrong head"
    if (form.parse_review(review_log(n=REVIEW_PR + 1)) or {}).get("n") != REVIEW_PR + 1:
        return False, "the record for another pull request does not parse as pull request %d" % (REVIEW_PR + 1)
    if form.parse_review(REVIEW_MARKER_TEXT) is not None:
        return False, "a marker-only body parses as a record"
    if form.parse_review(REVIEW_SKIPPED_ROUND) is not None:
        return False, "a record with a skipped round parses as a record"
    full = form.parse_review(REVIEW_FULL)
    if not full or full["fix"] is None or len(full["rounds"]) != 4:
        return False, "the full-size record does not parse with its rounds and its Fix check"
    if form.parse_review(REVIEW_TRAILING) is not None or form.parse_review(REVIEW_FULL_TRAILING) is not None:
        return False, "a body with prose after the CI line parses as a record"
    if form.parse_review(REVIEW_FENCED) is not None:
        return False, "a body that opens with a code fence parses as a record"
    if form.parse_review(REVIEW_FOOTED) is None:
        return False, "the record with its footer does not parse"
    return True, "the bodies parse as their names say"


FIXTURELESS_CHECKS.add(review_fixtures_check)
REVIEW_LOG_CHECKS = []  # (label, check) pairs, appended to LOG_CHECKS_EXTRA where that list is defined (below the archive section)
REVIEW_LOG_CHECKS.append(("review-log:the bodies the cases post parse as their names say", review_fixtures_check))
REVIEW_LOG_CHECKS.append(("review-log:a marked post at the live head makes one gh read, MCP add_issue_comment",
                         review_reads(MCP_COMMENT, mcp_input(review_log()), "allow", 1)))
REVIEW_LOG_CHECKS.append(("review-log:a marked post at the live head makes one gh read, gh pr comment --body",
                         review_reads("Bash", {"command": "%s --body '%s'" % (PR_CMD, review_log())}, "allow", 1)))
REVIEW_LOG_CHECKS.append(("review-log:a marker in prose below the first line makes no gh read, MCP add_issue_comment",
                         review_reads(MCP_COMMENT, mcp_input(REVIEW_PROSE), "allow", 0)))
REVIEW_LOG_CHECKS.append(("review-log:a marker in prose below the first line makes no gh read, gh pr comment --body",
                         review_reads("Bash", {"command": "%s --body '%s'" % (PR_CMD, REVIEW_PROSE)}, "allow", 0)))
REVIEW_LOG_CHECKS.append(("review-log:a post with no pull request number makes two gh reads, gh pr comment --body",
                         review_reads("Bash", {"command": "gh pr comment --body '%s'" % review_log()}, "allow", 2,
                                      cwd=GHRECORDBRANCH, path_dirs=(GIT_PATH,))))
REVIEW_LOG_CHECKS.append(("review-log:a post that names a branch makes two gh reads, gh pr comment --body",
                         review_reads("Bash", {"command": "gh pr comment feat --body '%s'" % review_log()}, "allow", 2)))
REVIEW_LOG_CHECKS.append(("review-log:a marked post with a wrong head tail makes one gh read, and is refused",
                         review_reads(MCP_COMMENT, mcp_input(review_log(head=REVIEW_TAIL)), "deny", 1)))
REVIEW_LOG_CHECKS.append(("review-log:a comment with no marker makes no gh read",
                         review_reads(MCP_COMMENT, mcp_input("Round 1 ran. No review log yet."), "allow", 0)))
REVIEW_LOG_CHECKS.append(("review-log:a live-head read that fails allows the post and notes it on stderr",
                         review_note(MCP_COMMENT, mcp_input(review_log()), GHRECORDBROKEN + os.pathsep + PY_PATH)))
REVIEW_LOG_CHECKS.append(("review-log:an unreadable body file allows the post and notes it on stderr",
                         review_note("Bash", {"command": "%s --body-file %s" % (PR_CMD, os.path.join(GHRECORDDIR, "missing.md"))},
                                     GHRECORD + os.pathsep + PY_PATH)))
REVIEW_LOG_CHECKS.append(("review-log:a plain stdin body the guard cannot read is allowed and noted on stderr, gh pr comment -F -",
                         review_note("Bash", {"command": "some_cmd | %s -F -" % PR_CMD}, GHRECORD + os.pathsep + PY_PATH)))
# The issue word costs what the pull request word costs: one read per marked post at a number, and two with no number in a repo.
REVIEW_LOG_CHECKS.append(("review-log:a marked post at the live head makes one gh read, gh issue comment --body",
                         review_reads("Bash", {"command": "%s --body '%s'" % (ISSUE_CMD, review_log())}, "allow", 1)))
REVIEW_LOG_CHECKS.append(("review-log:a marked post at the live head makes one gh read, gh issue comment 12 --edit-last --body",
                         review_reads("Bash", {"command": "%s --edit-last --body '%s'" % (ISSUE_CMD, review_log())}, "allow", 1)))
REVIEW_LOG_CHECKS.append(("review-log:a marked post with a wrong head tail makes one gh read, gh issue comment 12 --edit-last",
                         review_reads("Bash", {"command": "%s --edit-last --body '%s'" % (ISSUE_CMD, review_log(head=REVIEW_TAIL))},
                                      "deny", 1)))
# An edit in place names a comment, not a pull request: the PATCH route reads no head.
REVIEW_LOG_CHECKS.append(("review-log:a well-formed record in a PATCH makes no gh read, gh api -X PATCH",
                         review_reads("Bash", {"command": "%s -f 'body=%s'" % (API_EDIT_CMD, review_log())}, "allow", 0)))
# The update tool names a comment, not a pull request, so the guard finds the pull request from the comment (one read) and
# reads its live head (a second read). A marked update is judged as a post is; its two reads are the cost pr-review-record states.
mcp_post("review-log: a record at the live head is allowed, MCP update_issue_comment", review_log(), "allow",
         comment_id=REVIEW_COMMENT)
mcp_post("review-log: a full-size record with its footer is allowed, MCP update_issue_comment", REVIEW_FULL, "allow",
         comment_id=REVIEW_COMMENT)
mcp_post("review-log: a comment with no marker is allowed, MCP update_issue_comment", "Round 1 ran. No review log yet.",
         "allow", comment_id=REVIEW_COMMENT)
mcp_post("review-log: a marker in prose below the first line is allowed, MCP update_issue_comment", REVIEW_PROSE, "allow",
         comment_id=REVIEW_COMMENT)
mcp_post("review-log: a wrong head tail is refused, MCP update_issue_comment", review_log(head=REVIEW_TAIL), "deny",
         rule=REVIEW_RULE, carries=(REVIEW_RENDER,), comment_id=REVIEW_COMMENT)
mcp_post("review-log: a stale record is refused, MCP update_issue_comment", review_log(head=REVIEW_OLD), "deny",
         rule=REVIEW_RULE, carries=(REVIEW_RENDER,), comment_id=REVIEW_COMMENT)
mcp_post("review-log: a record for another pull request is refused, MCP update_issue_comment", review_log(n=REVIEW_PR + 1),
         "deny", rule=REVIEW_RULE, comment_id=REVIEW_COMMENT)
mcp_post("review-log: a marker with no record is refused, MCP update_issue_comment", REVIEW_MARKER_TEXT, "deny",
         rule=REVIEW_RULE, comment_id=REVIEW_COMMENT)
mcp_post("review-log: a record with a round skipped is refused, MCP update_issue_comment", REVIEW_SKIPPED_ROUND, "deny",
         rule=REVIEW_RULE, comment_id=REVIEW_COMMENT)


def comment_read_check():
    """The record fakes answer the comment read with the pull request the comment sits on (issue_url ends /issues/12). Without
    this, a fake that answers wrong would look like a guard bug."""
    materialize(GHRECORDREPO)
    env = dict(os.environ, PATH=fake_gh_path(GHRECORDREPO))
    program = shutil.which("gh", path=env["PATH"])
    if not program:
        return False, "the record pull request tool is not on PATH, so the comment read cannot be checked"
    done = subprocess.run([program, "api", "repos/y/x/issues/comments/%d" % REVIEW_COMMENT], capture_output=True, text=True,
                          env=env, timeout=60)
    try:
        issue = json.loads(done.stdout).get("issue_url", "")
    except (ValueError, AttributeError):
        return False, "the comment read does not answer a JSON object: %r" % done.stdout[:120]
    if not issue.endswith("/issues/%d" % REVIEW_PR):
        return False, "the comment read names %r, want an issue_url ending /issues/%d" % (issue, REVIEW_PR)
    return True, "the comment read names pull request %d" % REVIEW_PR


REVIEW_LOG_CHECKS.append(("review-log:the record fake answers the comment read with the pull request the comment sits on",
                         comment_read_check))
REVIEW_LOG_CHECKS.append(("review-log:a marked update at the live head makes two gh reads, MCP update_issue_comment",
                         review_reads(MCP_UPDATE, mcp_input(review_log(), comment_id=REVIEW_COMMENT), "allow", 2)))
REVIEW_LOG_CHECKS.append(("review-log:a marked update with a wrong head tail makes two gh reads, and is refused, MCP update_issue_comment",
                         review_reads(MCP_UPDATE, mcp_input(review_log(head=REVIEW_TAIL), comment_id=REVIEW_COMMENT), "deny", 2)))
REVIEW_LOG_CHECKS.append(("review-log:a comment with no marker makes no gh read, MCP update_issue_comment",
                         review_reads(MCP_UPDATE, mcp_input("Round 1 ran. No review log yet.", comment_id=REVIEW_COMMENT), "allow", 0)))
REVIEW_LOG_CHECKS.append(("review-log:a marker in prose below the first line makes no gh read, MCP update_issue_comment",
                         review_reads(MCP_UPDATE, mcp_input(REVIEW_PROSE, comment_id=REVIEW_COMMENT), "allow", 0)))
REVIEW_LOG_CHECKS.append(("review-log:a marked update whose comment cannot be read is allowed and noted on stderr, MCP update_issue_comment",
                         review_note(MCP_UPDATE, mcp_input(review_log(), comment_id=REVIEW_COMMENT),
                                     GHRECORDBROKEN + os.pathsep + PY_PATH)))


for _label, _check in REVIEW_LOG_CHECKS:
    LOG_CHECKS_EXTRA.append((_label, _check))
