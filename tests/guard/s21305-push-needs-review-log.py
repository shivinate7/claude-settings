# section 21305
# =========================================================================== push needs a review record
#
# Rule push-needs-review-record. A shell `git push` asks first when the session's own transcript shows, in
# order: a PR known to the session (a create_pull_request or a Bash `gh pr create` that succeeded, or a posted
# review record); then every reviewer or design-reviewer report, of any verdict (its Done line: PASS, FAIL or
# PARTIAL, a round or a fix check), that has no later posted review record clearing it. A record clears a report
# only when it parses, its comment call returned no error (add_issue_comment, or a Bash `gh pr comment` or
# `gh api .../comments` call that succeeded), and it holds a line with that report's role, verdict and round
# (a Round line, or the Fix check line for a fix verifier). When the report names its reviewed head, that head
# must be the record's Head line, or for a fix verifier the sha of its Fix check line. One record that
# holds all the lines clears every report before it. A push asks until each report has its record. A deny is
# left for a push to a PR's head branch once its fix check is recorded.
# A report reads from the Agent result, from a later task-notification, from a queued_command
# attachment, or from a hand-back (a user message that opens with the frame, names the agent in its tag, and
# indents the report). Its verdict is the Done line, never a finding line, and the Done line still matches when
# indented. A line inside a code fence is never a verdict. A PASS needs its own record as much as a FAIL does: a
# push waits for the record of every report. A session with no PR known is allowed: the first push is never
# blocked on a transcript that shows no PR (a known miss, pinned below).
FAMILY = "push-needs-review-record"  # glossary-ok: the family name hooks/test_guard.py keys on, a literal

PFR_RULE = "push-needs-review-record"  # glossary-ok: the rule id the guard prints, a literal
PFR_BRANCH = "notes-delete-pass"   # the lane's branch: a refusal never names it (rule git-remedy-never-names-target)
PFR_PUSH = VCS + " push origin HEAD:" + PFR_BRANCH
PFR_MODEL = "claude-sonnet-5-5"
PFR_FIX_SHA = "fedcba9876543210fedcba9876543210fedcba98"   # the reviewed head of a fix check, never the Head
PFR_HEAD_A = "08462577333eefc425e50c60f85514b699c8bdf0"    # a real lane's head: the Head its first-review FAIL record names
PFR_HEAD_B = "5b77f144394703c567bd335f63d6d887e3e71cf1"    # the same lane's later head, which its second-review report names
PFR_MODEL_2871 = "claude-haiku-5-5"                        # the model that ran that lane's first reviewer
PFR_GH_ROOT = "gh -R shivinate7/claude-settings"           # a repo flag before the verb, as gh reads it
PFR_GH_LONG = "gh --repo shivinate7/claude-settings"       # the long form of the same repo flag
PFR_GH_GROUP = "gh pr -R shivinate7/claude-settings"       # the same flag after the group word `pr`
PFR_AGENT_ID = "a1b2c3d4e5f607182"                          # 17 characters, the agent_id an agent's call carries
PFR_AGENT_TOOL = "Agent"
PFR_CREATE_PR = "mcp__github__create_pull_request"
PFR_ADD_COMMENT = "mcp__github__add_issue_comment"
PFR_FINDING = "Finding: the guard would let the push through before the record is posted."
PFR_DIR = os.path.join(ROOT, "failrec")
PFR_UNREADABLE = os.path.join(PFR_DIR, "unreadable.jsonl")   # a folder, so the guard's open() fails on it


def _load_merge():
    """merge/merge.py, loaded by path. Its review_body writes the record form and its parse_review reads it
    back, so no case names a copy of that form."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("merge_under_test", os.path.join(REPO, "merge", "merge.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MERGE = _load_merge()


def pfr_record(rounds=(), fix=None, n=1467, head=SHA):
    """A posted review record for PR `n`, written by merge's own form. A body the reader refuses is a fixture
    error, so it stops the run here instead of turning a case red for the wrong cause."""
    body = MERGE.review_body(n, head, "normal", "no", list(rounds), "not owed", fix)
    if MERGE.parse_review(body) is None:
        sys.exit("fixture setup failed: merge.parse_review refuses the record body %r" % body[:60])
    return body


def pfr_pr():
    """The lane opens its pull request: a create_pull_request call whose result is no error."""
    return [role_use("toolu_pr1", PFR_CREATE_PR, {"owner": "shivinate7", "repo": "claude-settings",
                                                  "head": PFR_BRANCH, "base": "main", "title": "notes delete pass"}),
            role_result("toolu_pr1", '{"number": 1467}')]


def pfr_report(verdict, *lines):
    """A reviewer's report: the Done heading, its verdict line, then the body."""
    return "\n".join(["Done", verdict, *lines])


def pfr_verdict(verdict, n=1, model=PFR_MODEL):
    """The Done line of a report for round n: its verdict, its round and its model."""
    return "%s, round %d of 3, %s" % (verdict, n, model)


def pfr_fix_verdict(verdict, model=PFR_MODEL):
    """A Done line for a fix check: `FAIL, fix check, <model>`."""
    return "%s, fix check, %s" % (verdict, model)


def pfr_call(tool_id, report, role="reviewer", blocks=False):
    """An Agent call in the foreground: its result carries the report, as one string or as a list of text
    blocks when `blocks` is set."""
    call = role_use(tool_id, PFR_AGENT_TOOL, {"subagent_type": role, "description": "review round",
                                              "prompt": "review the diff"})
    if blocks:
        return [call, role_result(tool_id, report)]
    return [call, role_result_block(tool_id, content=report)]


def pfr_background(tool_id, role="reviewer"):
    """An Agent call in the background: its result is only the launch ack, and the report arrives later in a
    notice that names this call."""
    return [role_use(tool_id, PFR_AGENT_TOOL, {"subagent_type": role, "description": "review round",
                                               "prompt": "review the diff", "run_in_background": True}),
            role_result(tool_id, "Started in the background.")]


def pfr_notice(tool_id, report, attachment=False):
    """The completion notice for call `tool_id`: a user message with string content, or a queued_command
    attachment record with the same text."""
    text = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
            "<status>completed</status>\n<summary>Agent \"review\" completed</summary>\n"
            "<result>%s</result>\n</task-notification>" % (tool_id, tool_id, report))
    if attachment:
        return [json.dumps({"type": "attachment", "attachment": {"type": "queued_command", "prompt": text}})]
    return [role_said(text)]


def pfr_call_handback(tool_id, agent_id, role="reviewer"):
    """A background Agent call whose result names its agentId. Its report comes back as a hand-back, not a notice."""
    return [role_use(tool_id, PFR_AGENT_TOOL, {"subagent_type": role, "description": "review round",
                                               "prompt": "review the diff", "run_in_background": True}),
            role_result(tool_id, "Started in the background.\nagentId: %s" % agent_id)]


def pfr_handback(agent_id, report):
    """A report as the harness hands it back: a user message whose string content opens with the frame, then the
    agent-message tag that names the agent, then the report indented by the harness (hooks/shared_names.py)."""
    indented = "\n".join("    " + line for line in report.split("\n"))
    return [role_said("%s\n<agent-message from=\"%s\">\n[Agent hand-back]\n%s\n</agent-message>"
                      % (PFR_HAND_FRAME, agent_id, indented))]


def pfr_post(tool_id, body, error=False, n=1467):
    """A comment posted on PR `n`. An error result means the post did not happen."""
    call = role_use(tool_id, PFR_ADD_COMMENT, {"owner": "shivinate7", "repo": "claude-settings",
                                               "issue_number": n, "body": body})
    if error:
        return [call, role_result_block(tool_id, content="403 Forbidden", is_error=True)]
    return [call, role_result(tool_id, '{"id": 9001}')]


def pfr_pr_open(tool_id, number, head):
    """A create_pull_request call that succeeds: pull request `number`, opened from branch `head`."""
    return [role_use(tool_id, PFR_CREATE_PR, {"owner": "shivinate7", "repo": "claude-settings", "head": head,
                                              "base": "main", "title": "notes fix"}),
            role_result(tool_id, '{"number": %d}' % number)]


def pfr_filler(count):
    """Unrelated reads, the transcript's bulk: each a call and its result, neither a report nor a PR."""
    lines = []
    for i in range(count):
        lines.append(role_use("toolu_rd%d" % i, "Read", {"file_path": "notes/%d.md" % i}))
        lines.append(role_result("toolu_rd%d" % i, "read"))
    return lines


def pfr_bash(tool_id, command, output):
    """A Bash call and its result: the gh forms a lane runs in place of the MCP tools."""
    return [role_use(tool_id, "Bash", {"command": command}), role_result(tool_id, output)]


def pfr_gh_pr(tool_id, number=1467, head=PFR_BRANCH, words="gh pr create"):
    """A successful `gh pr create`, spelled as `words` says (a repo flag may sit before or after `pr`): its result is
    the URL of the new pull request."""
    return pfr_bash(tool_id, '%s --base main --head %s --title "notes delete pass"' % (words, head),
                    "https://github.com/shivinate7/claude-settings/pull/%d\n" % number)


def pfr_gh_post(tool_id, body, form="comment", n=1467, words="gh pr comment"):
    """A record posted by `gh pr comment` (spelled as `words` says) or by `gh api .../comments`. The whole body sits
    in the command text."""
    if form == "comment":
        return pfr_bash(tool_id, "%s %d --body-file - <<'EOF'\n%s\nEOF" % (words, n, body),
                        "https://github.com/shivinate7/claude-settings/pull/%d#issuecomment-9001" % n)
    return pfr_bash(tool_id, "gh api repos/shivinate7/claude-settings/issues/%d/comments -F body=@- <<'EOF'\n%s\nEOF"
                    % (n, body), '{"id": 9001}')


# A Done-shaped sample in a code fence above the report's real Done line. Lines inside a fence are never a verdict.
PFR_FENCE_SAMPLE = "A sample of an earlier verdict, quoted in a fence:\n```\nDone\nFAIL, round 1 of 3, x\n```\n"
PFR_PASS_FENCED = PFR_FENCE_SAMPLE + pfr_report(pfr_verdict("PASS", 1), PFR_FINDING)
PFR_FAIL = pfr_report(pfr_verdict("FAIL", 1), PFR_FINDING)           # a reviewer FAIL, read from its Done line
PFR_FAIL_RECORD = pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")])    # a posted record that holds it
PFR_PARTIAL = pfr_report(pfr_verdict("PARTIAL", 1), PFR_FINDING)     # a reviewer PARTIAL, read from its Done line
PFR_PARTIAL_RECORD = pfr_record([(1, "reviewer", PFR_MODEL, "PARTIAL")])
PFR_PASS = pfr_report(pfr_verdict("PASS", 1), PFR_FINDING)          # a reviewer PASS, read from its Done line
PFR_PASS_RECORD = pfr_record([(1, "reviewer", PFR_MODEL, "PASS")])
PFR_DESIGN_PASS_RECORD = pfr_record([(1, "design-reviewer", PFR_MODEL, "PASS")])
PFR_BOTH_RECORD = pfr_record([(1, "reviewer", PFR_MODEL, "FAIL"), (1, "design-reviewer", PFR_MODEL, "PASS")])
PFR_HAND_AGENT = "b3c9d0e1f2a34b5c6"                      # the agentId the Agent call's result names
PFR_HAND_FRAME = "Another Claude session sent a message:"  # the frame before an <agent-message> tag
# A posted Fix check line for PR n denies a push to n's head branch. n's head comes from its create_pull_request.
PFR_FIX_BRANCH = "notes-fix-report"       # the head branch of the PR whose fix check is recorded
PFR_NEXT_BRANCH = "notes-fix-report-2"    # the head branch of a PR opened after that record
PFR_FIX_PR = 1464
PFR_NEXT_PR = 1500
PFR_FIX_PUSH = VCS + " push origin HEAD:" + PFR_FIX_BRANCH
PFR_NEXT_PUSH = VCS + " push origin HEAD:" + PFR_NEXT_BRANCH
PFR_FIX_PASS_RECORD = pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "PASS"), n=PFR_FIX_PR)
PFR_FIX_FAIL_RECORD = pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "FAIL"), n=PFR_FIX_PR)
PFR_ROUND_RECORD = pfr_record([(1, "reviewer", PFR_MODEL, "PASS")], n=PFR_FIX_PR)
# A system line that names an Agent, with a message that holds no content: the key missing, null, or a plain string.
PFR_STRAY_NO_CONTENT = json.dumps({"type": "system", "tool": "Agent", "message": {"role": "system"}})
PFR_STRAY_NULL = json.dumps({"type": "system", "tool": "Agent", "message": None})
PFR_STRAY_STRING = json.dumps({"type": "system", "tool": "Agent", "message": "Agent note"})
# Valid JSON that is not an object. Each holds the mark `"Agent"`, so the reader parses it: a list, and a bare string.
PFR_STRAY_LIST = json.dumps(["Agent", 1, 2])
PFR_STRAY_BARE_STRING = json.dumps("Agent")


def pfr_fix_after_round1(report_head):
    """A first-review FAIL, reviewed and recorded at head A. Then a fix check PASS whose report names `report_head`, and the fix
    record: Head B, with its Fix check line at A, where the fix diff starts. Only the fix report's head varies."""
    return (pfr_pr() + pfr_call("toolu_rev1", pfr_report(pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_A,
                                                       PFR_FINDING))
            + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")], head=PFR_HEAD_A))
            + pfr_call("toolu_rev2", pfr_report(pfr_fix_verdict("PASS"), "Reviewed at head %s" % report_head,
                                                PFR_FINDING), blocks=True)
            + pfr_post("toolu_c2", pfr_record(fix=(PFR_HEAD_A, "reviewer", PFR_MODEL, "PASS"), head=PFR_HEAD_B)))


def pfr_base_head_report(record_head):
    """A first-review FAIL whose text reads `Base: main head B, reviewed A`, then a record posted at `record_head`. Only the
    record's head varies: the report's reviewed head is A either way."""
    return (pfr_pr() + pfr_call("toolu_rev1", pfr_report(pfr_verdict("FAIL", 1),
                                                         "Base: main head %s, reviewed %s" % (PFR_HEAD_B, PFR_HEAD_A),
                                                         PFR_FINDING))
            + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")], head=record_head)))


# The session's own files, one per case, each a list of JSON lines. An empty list is a zero-byte file.
PFR_LINES = {
    # The incident: the PR is open, the FAIL comes back in the foreground, then the push.
    "incident": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL),
    "incident-notice": pfr_pr() + pfr_background("toolu_rev1") + pfr_notice("toolu_rev1", PFR_FAIL),
    "incident-attachment": pfr_pr() + pfr_background("toolu_rev1")
                           + pfr_notice("toolu_rev1", PFR_FAIL, attachment=True),
    "fix-verifier": pfr_pr() + pfr_call("toolu_rev1", pfr_report(pfr_fix_verdict("FAIL"), PFR_FINDING), blocks=True),
    "partial": pfr_pr() + pfr_call("toolu_rev1", PFR_PARTIAL),
    "design-fail": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL, role="design-reviewer"),
    "design-partial": pfr_pr() + pfr_call("toolu_rev1", PFR_PARTIAL, role="design-reviewer"),
    # The builder's push reads the parent file. Its own file holds a PASS with its record, which a guard that
    # read the wrong file would take as clean.
    "builder": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL),
    "builder-clean": pfr_pr(),
    # The #1490 shape: a reviewer PASS with the PR known and no record after it.
    "pass-no-record": pfr_pr() + pfr_call("toolu_rev1", PFR_PASS),
    "design-fail-reviewer-record": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL, role="design-reviewer")
                                   + pfr_post("toolu_c1", PFR_FAIL_RECORD),
    "pass-fail-record": pfr_pr() + pfr_call("toolu_rev1", PFR_PASS) + pfr_post("toolu_c1", PFR_FAIL_RECORD),
    # An unrecorded reviewer FAIL, then a design-reviewer PASS. The record holds one line, or both.
    "mixed-unrecorded-reviewer": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                                 + pfr_call("toolu_dsn1", PFR_PASS, role="design-reviewer")
                                 + pfr_post("toolu_c1", PFR_DESIGN_PASS_RECORD),
    "mixed-both-recorded": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                           + pfr_call("toolu_dsn1", PFR_PASS, role="design-reviewer")
                           + pfr_post("toolu_c1", PFR_BOTH_RECORD),
    # Hand-back: the report comes back as a user message, not a notice. The agentId names the Agent call.
    "handback-fail": pfr_pr() + pfr_call_handback("toolu_rev1", PFR_HAND_AGENT)
                     + pfr_handback(PFR_HAND_AGENT, PFR_FAIL),
    "handback-pass": pfr_pr() + pfr_call_handback("toolu_rev1", PFR_HAND_AGENT)
                     + pfr_handback(PFR_HAND_AGENT, PFR_PASS),
    "handback-fail-record": pfr_pr() + pfr_call_handback("toolu_rev1", PFR_HAND_AGENT)
                            + pfr_handback(PFR_HAND_AGENT, PFR_FAIL) + pfr_post("toolu_c1", PFR_FAIL_RECORD),
    "fail-then-older-pass-record": pfr_pr() + pfr_call("toolu_rev1", pfr_report(pfr_verdict("FAIL", 2), PFR_FINDING))
                                   + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "PASS")])),
    "fail-then-errored-record": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                                + pfr_post("toolu_c1", PFR_FAIL_RECORD, error=True),
    "fail-then-fail-record": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + pfr_post("toolu_c1", PFR_FAIL_RECORD),
    "partial-then-partial-record": pfr_pr() + pfr_call("toolu_rev1", PFR_PARTIAL)
                                   + pfr_post("toolu_c1", PFR_PARTIAL_RECORD),
    "fix-verifier-record": pfr_pr() + pfr_call("toolu_rev1", pfr_report(pfr_fix_verdict("FAIL"), PFR_FINDING), blocks=True)
                        + pfr_post("toolu_c1", pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "FAIL"))),
    # A fix check FAIL, then a fix check PASS whose record is posted. The PASS record clears only its own line.
    "fix-fail-then-fix-pass": pfr_pr()
        + pfr_call("toolu_rev1", pfr_report(pfr_fix_verdict("FAIL"), PFR_FINDING), blocks=True)
        + pfr_call("toolu_rev2", pfr_report(pfr_fix_verdict("PASS"), PFR_FINDING), blocks=True)
        + pfr_post("toolu_c1", pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "PASS"))),
    # The control: the same, with the FAIL fix record posted between the two reports.
    "fix-fail-record-then-fix-pass": pfr_pr()
        + pfr_call("toolu_rev1", pfr_report(pfr_fix_verdict("FAIL"), PFR_FINDING), blocks=True)
        + pfr_post("toolu_c2", pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "FAIL")))
        + pfr_call("toolu_rev2", pfr_report(pfr_fix_verdict("PASS"), PFR_FINDING), blocks=True)
        + pfr_post("toolu_c1", pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "PASS"))),
    # A round report names reviewed head B. A record posted for head A holds the same round, so only the Head line differs.
    "round-head-b-record-head-a": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_B, PFR_FINDING))
        + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")], head=PFR_HEAD_A)),
    # The same report, and a record posted at its reviewed head, head A.
    "round-head-a-record-head-a": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_A, PFR_FINDING))
        + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")], head=PFR_HEAD_A)),
    # A review report and no record at all: the lane posted no comments.
    "round-no-record-2921": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_A, PFR_FINDING)),
    # A real lane's shape: its first-review record is posted at head A, and a second-review report names the later
    # head B with no record, so the push asks.
    "2871-round2-unrecorded": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1, PFR_MODEL_2871), "Reviewed at head %s" % PFR_HEAD_A, PFR_FINDING))
        + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL_2871, "FAIL")], head=PFR_HEAD_A))
        + pfr_call("toolu_rev2", pfr_report(pfr_verdict("FAIL", 2, PFR_MODEL_2871),
                                            "Reviewed at head %s" % PFR_HEAD_B, PFR_FINDING)),
    # A fix verifier is cleared by its reviewed head A, the sha of the record's Fix check line. The record's Head line
    # (B) is another head, and the first-review record at head B holds both lines.
    "round-head-b-fix-head-a": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_B, PFR_FINDING))
        + pfr_call("toolu_rev2", pfr_report(pfr_fix_verdict("PASS"), "Reviewed at head %s" % PFR_HEAD_A, PFR_FINDING),
                   blocks=True)
        + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")],
                                          fix=(PFR_HEAD_A, "reviewer", PFR_MODEL, "PASS"), head=PFR_HEAD_B)),
    # A fix check that reviewed head B, recorded at head B with its Fix check line at A, where the fix diff starts.
    # The control names head A, the Fix check line's own sha.
    "fix-head-b-record-fix-a": pfr_fix_after_round1(PFR_HEAD_B),
    "fix-head-a-record-fix-a": pfr_fix_after_round1(PFR_HEAD_A),
    # A round report whose text reads `Base: main head B, reviewed A`: its reviewed head is A, and a record at A holds
    # it. A record at B alone does not: B is the base, not the reviewed head.
    "round-base-head-b-reviewed-a-record-a": pfr_base_head_report(PFR_HEAD_A),
    "round-base-head-b-reviewed-a-record-b-only": pfr_base_head_report(PFR_HEAD_B),
    # A Fix check line clears no round report, and it denies a push to its PR's head branch before the round ask.
    "round-fail-fix-record": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                             + pfr_post("toolu_c1", pfr_record(fix=(PFR_FIX_SHA, "reviewer", PFR_MODEL, "FAIL"))),
    "fail-then-comment": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                         + pfr_post("toolu_c1", "Round 1: reviewer, %s, FAIL\nNet value: not owed" % PFR_MODEL),
    # The PR is known only from a posted record: the R1 FAIL record, then an R2 FAIL report, then the push.
    "record-known-pr": pfr_call("toolu_rev0", PFR_FAIL) + pfr_post("toolu_c0", PFR_FAIL_RECORD)
                       + pfr_call("toolu_rev1", pfr_report(pfr_verdict("FAIL", 2), PFR_FINDING)),
    "bold-lead": pfr_pr() + pfr_call("toolu_rev1", pfr_report("**%s**" % pfr_verdict("FAIL", 1), PFR_FINDING)),
    "long": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + pfr_filler(1500),
    "fail-then-fail-pass": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                           + pfr_call("toolu_rev2", pfr_report(pfr_verdict("PASS", 2), PFR_FINDING)),
    "fail-then-pass-record": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                             + pfr_call("toolu_rev2", pfr_report(pfr_verdict("PASS", 2), PFR_FINDING))
                             + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL"),
                                                                (2, "reviewer", PFR_MODEL, "PASS")])),
    "fail-after-recorded-rounds": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + pfr_post("toolu_c1", PFR_FAIL_RECORD)
                                  + pfr_call("toolu_rev2", pfr_report(pfr_verdict("PASS", 2), PFR_FINDING))
                                  + pfr_post("toolu_c2", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL"),
                                                                      (2, "reviewer", PFR_MODEL, "PASS")]))
                                  + pfr_call("toolu_rev3", pfr_report(pfr_verdict("FAIL", 3), PFR_FINDING)),
    "pass-finding-says-fail": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("PASS", 1), "Finding: the old guard would FAIL open on a missing file.",
        "- " + pfr_verdict("FAIL", 1) + " (an earlier reading, now fixed)"))
                              + pfr_post("toolu_c1", PFR_PASS_RECORD),
    "no-review": pfr_pr(),
    "no-pr-fail": pfr_call("toolu_rev1", PFR_FAIL),
    # A fix check recorded for a PR, with its head branch as the push's destination.
    "fix-pass-same": pfr_pr_open("toolu_pr1", PFR_FIX_PR, PFR_FIX_BRANCH)
                     + pfr_post("toolu_c1", PFR_FIX_PASS_RECORD, n=PFR_FIX_PR),
    "fix-fail-same": pfr_pr_open("toolu_pr1", PFR_FIX_PR, PFR_FIX_BRANCH)
                     + pfr_post("toolu_c1", PFR_FIX_FAIL_RECORD, n=PFR_FIX_PR),
    "fix-pass-other-branch": pfr_pr_open("toolu_pr1", PFR_FIX_PR, PFR_FIX_BRANCH)
                             + pfr_post("toolu_c1", PFR_FIX_PASS_RECORD, n=PFR_FIX_PR)
                             + pfr_pr_open("toolu_pr2", PFR_NEXT_PR, PFR_NEXT_BRANCH),
    "round-record-same": pfr_pr_open("toolu_pr1", PFR_FIX_PR, PFR_FIX_BRANCH)
                         + pfr_post("toolu_c1", PFR_ROUND_RECORD, n=PFR_FIX_PR),
    # A fix check recorded for a PR whose create_pull_request is not in the transcript.
    "fix-pass-unknown-head": pfr_post("toolu_c1", PFR_FIX_PASS_RECORD, n=PFR_FIX_PR),
    "gh-pr-create-fail": pfr_gh_pr("toolu_pr1") + pfr_call("toolu_rev1", PFR_FAIL),
    # A round report is cleared only by a record line of the same round: a line of any other round never clears it.
    "round-scoped-refuse": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                         + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "PASS"),
                                                            (2, "reviewer", PFR_MODEL, "FAIL")])),
    "round-scoped-allow": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                          + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL"),
                                                             (2, "reviewer", PFR_MODEL, "FAIL")])),
    "pass-fence-sample": pfr_pr() + pfr_call("toolu_rev1", PFR_PASS_FENCED) + pfr_post("toolu_c1", PFR_PASS_RECORD),
    "fail-gh-pr-comment": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + pfr_gh_post("toolu_c1", PFR_FAIL_RECORD),
    "fail-gh-api-comment": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                           + pfr_gh_post("toolu_c1", PFR_FAIL_RECORD, form="api"),
    # A command that only names `gh pr create` opens no PR. The real create is the control.
    "gh-mention-grep": pfr_bash("toolu_g1", 'grep -rn "gh pr create" docs', "docs/review.md:12:gh pr create --draft")
                       + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-mention-echo": pfr_bash("toolu_g1", "echo 'run gh pr create later'", "run gh pr create later")
                       + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-mention-comment": pfr_bash("toolu_g1", "# gh pr create --draft --title t", "")
                          + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-mention-heredoc": pfr_bash("toolu_g1", "cat <<'EOF'\ngh pr create --draft\nEOF", "gh pr create --draft")
                          + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-real-create": pfr_bash("toolu_pr1", "cd x && gh pr create --draft --title t",
                               "https://github.com/shivinate7/claude-settings/pull/1467\n")
                      + pfr_call("toolu_rev1", PFR_FAIL),
    # An interpreter that runs a heredoc body opens the PR the body names.
    "gh-heredoc-bash": pfr_bash("toolu_pr1", "bash <<'EOF'\ngh pr create --draft --title t\nEOF",
                                "https://github.com/shivinate7/claude-settings/pull/1467\n")
                       + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-heredoc-sh": pfr_bash("toolu_pr1", "sh <<EOF\ngh pr create --draft --title t\nEOF",
                              "https://github.com/shivinate7/claude-settings/pull/1467\n")
                     + pfr_call("toolu_rev1", PFR_FAIL),
    # A command substitution runs its gh pr create, so the PR it opens is known to the session.
    "gh-subst-assign": pfr_bash("toolu_pr1", "URL=$(gh pr create --draft --title t)",
                                "https://github.com/shivinate7/claude-settings/pull/1467\n")
                       + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-subst-dquote": pfr_bash("toolu_pr1", 'echo "PR: $(gh pr create --draft --title t)"',
                                "PR: https://github.com/shivinate7/claude-settings/pull/1467\n")
                       + pfr_call("toolu_rev1", PFR_FAIL),
    # Single quotes make the substitution text, so no PR opens.
    "gh-subst-squote": pfr_bash("toolu_g1", "echo '$(gh pr create)'", "$(gh pr create)")
                       + pfr_call("toolu_rev1", PFR_FAIL),
    # A verdict in backticks or with a verdict word is still the Done verdict.
    "fail-backtick": pfr_pr() + pfr_call("toolu_rev1", pfr_report("`%s`" % pfr_verdict("FAIL", 1, "claude-haiku-5-5"),
                                                                  PFR_FINDING)),
    "fail-bold-verdict": pfr_pr() + pfr_call("toolu_rev1", pfr_report("**FAIL**, round 1 of 3, m", PFR_FINDING)),
    "pass-backtick-record": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        "`%s`" % pfr_verdict("PASS", 1, "claude-haiku-5-5"), PFR_FINDING)) + pfr_post("toolu_c1", PFR_PASS_RECORD),
    # A Done label line that holds the verdict itself, in a word order the ruled form does not use.
    "label-haiku": pfr_pr() + pfr_call("toolu_rev1", "Done: round 1 reviewer haiku FAIL\n" + PFR_FINDING),
    "label-claude-haiku": pfr_pr() + pfr_call("toolu_rev1",
                                              "Done: round 1 reviewer claude-haiku-5-5 PARTIAL\n" + PFR_FINDING),
    "label-design": pfr_pr() + pfr_call("toolu_rev1", "Done: round 2 design-reviewer sonnet PASS\n" + PFR_FINDING,
                                        role="design-reviewer"),
    "label-haiku-record": pfr_pr() + pfr_call("toolu_rev1", "Done: round 1 reviewer haiku FAIL\n" + PFR_FINDING)
                          + pfr_post("toolu_c1", PFR_FAIL_RECORD),
    # A Done label line with no verdict word, then the ruled form on the next line.
    "see-below-ruled": pfr_pr() + pfr_call("toolu_rev1", "Done: see below\n" + pfr_verdict("FAIL", 1) + "\n" + PFR_FINDING),
    # A PR opened with a repo flag in one of gh's three spellings. gh reads the same verb for each, so the PR is known.
    "gh-root-flag-pr-create-fail": pfr_gh_pr("toolu_pr1", words=PFR_GH_ROOT + " pr create")
                                   + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-long-flag-pr-create-fail": pfr_gh_pr("toolu_pr1", words=PFR_GH_LONG + " pr create")
                                   + pfr_call("toolu_rev1", PFR_FAIL),
    "gh-group-flag-pr-create-fail": pfr_gh_pr("toolu_pr1", words=PFR_GH_GROUP + " create")
                                    + pfr_call("toolu_rev1", PFR_FAIL),
    # A FAIL recorded by a comment that carries the same repo flag. gh reads the flag in front of the verb as valid.
    "fail-gh-root-flag-pr-comment": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                                    + pfr_gh_post("toolu_c1", PFR_FAIL_RECORD, words=PFR_GH_ROOT + " pr comment"),
    "fail-gh-long-flag-pr-comment": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL)
                                    + pfr_gh_post("toolu_c1", PFR_FAIL_RECORD, words=PFR_GH_LONG + " pr comment"),
    # A fix check PASS for a fix PR is posted, then a second-review FAIL with no record. The fix-branch refusal still denies.
    "fix-pass-then-round2-fail": pfr_pr_open("toolu_pr1", PFR_FIX_PR, PFR_FIX_BRANCH)
                                 + pfr_post("toolu_c1", PFR_FIX_PASS_RECORD, n=PFR_FIX_PR)
                                 + pfr_call("toolu_rev2", pfr_report(pfr_verdict("FAIL", 2), PFR_FINDING)),
    # A FAIL report, then a stray line with no message content. The reader must step over the stray line and
    # keep the FAIL unrecorded, so a stray line never hides a FAIL.
    "stray-no-content": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + [PFR_STRAY_NO_CONTENT],
    "stray-null": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + [PFR_STRAY_NULL],
    "stray-string": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + [PFR_STRAY_STRING],
    # The control: the same stray line, then the record posted at the reviewed head, head A.
    "stray-no-content-record-head-a": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_A, PFR_FINDING)) + [PFR_STRAY_NO_CONTENT]
        + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")], head=PFR_HEAD_A)),
    # A FAIL report, then a line that is valid JSON but not an object: a list, then a bare string. The reader
    # must step over each and keep the FAIL unrecorded, so such a line never hides a FAIL.
    "stray-list": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + [PFR_STRAY_LIST],
    "stray-bare-string": pfr_pr() + pfr_call("toolu_rev1", PFR_FAIL) + [PFR_STRAY_BARE_STRING],
    # The control: the same list line, then the record posted at the reviewed head, head A.
    "stray-list-record-head-a": pfr_pr() + pfr_call("toolu_rev1", pfr_report(
        pfr_verdict("FAIL", 1), "Reviewed at head %s" % PFR_HEAD_A, PFR_FINDING)) + [PFR_STRAY_LIST]
        + pfr_post("toolu_c1", pfr_record([(1, "reviewer", PFR_MODEL, "FAIL")], head=PFR_HEAD_A)),
    "empty": [],
}
# An agent's own file, `<session>/subagents/agent-<id>.jsonl`, keyed by the session name it sits under.
PFR_AGENT_LINES = {
    "builder": pfr_call("toolu_rev9", PFR_PASS) + pfr_post("toolu_c9", PFR_PASS_RECORD),
    "builder-clean": pfr_call("toolu_rev1", PFR_FAIL),
}


def pfr_path(name):
    return os.path.join(PFR_DIR, name + ".jsonl")


def pfr_agent_path(name):
    return os.path.join(PFR_DIR, name, "subagents", "agent-" + PFR_AGENT_ID + ".jsonl")


def write_pfr_transcripts():
    """Each fixture as JSONL under this run's folder. `unreadable` is a folder, so the guard's open() fails on it."""
    for name, lines in PFR_LINES.items():
        write(pfr_path(name), "".join(line + "\n" for line in lines))
    for name, lines in PFR_AGENT_LINES.items():
        write(pfr_agent_path(name), "".join(line + "\n" for line in lines))
    os.makedirs(PFR_UNREADABLE, exist_ok=True)


lazy_fixture([pfr_path(name) for name in PFR_LINES] + [PFR_UNREADABLE], write_pfr_transcripts)


# The PR head's history for the held reports. A is on main. B is on PFR_BRANCH, with A as its parent. C is on
# main, off A, so B's history does not hold it. PFR_OTHER_BRANCH is a branch at C: a PR for it holds no sha B
# names. A held report names a sha, and a sha exists only once its commit is made, so the builder writes these
# transcripts after the commits.
PFR_HIST = os.path.join(ROOT, "pfrhist")
PFR_OTHER_BRANCH = "notes-other"
PFR_HELD = ("held-ancestor", "held-record-other-head", "held-off-history", "held-no-sha", "held-agent-trailer",
            "held-path-then-off-history", "held-base-then-head", "held-head-then-two-prs",
            "held-label-round", "held-label-head")


def _pfr_step(*args):
    """One git step of the history fixture. A failed step stops the run here, not as a red case."""
    done = run_vcs(PFR_HIST, *args)
    if done.returncode != 0:
        sys.exit("fixture setup failed in _build_pfr_history: git %s: %s" % (" ".join(args), done.stderr.strip()))
    return done.stdout.strip()


def _build_pfr_history():
    """A on main, B on PFR_BRANCH, C on main off A, each in its own commit. The push destinations' remote is set
    up as _build_push sets it, so the checkout reads like a lane's."""
    materialize(BRANCHREMOTE)
    make_repo(PFR_HIST, {"notes.txt": "a\n"})
    _pfr_step("remote", "add", "origin", slash(BRANCHREMOTE))
    _pfr_step("update-ref", "refs/remotes/origin/main", "HEAD")
    _pfr_step("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    sha_a = _pfr_step("rev-parse", "HEAD")
    _pfr_step("checkout", "-q", "-b", PFR_BRANCH)
    write(os.path.join(PFR_HIST, "notes.txt"), "b\n")
    _pfr_step("add", "-A")
    _pfr_step(*IDENT, "commit", "-q", "-m", "b")
    _pfr_step("checkout", "-q", "main")
    write(os.path.join(PFR_HIST, "notes.txt"), "c\n")
    _pfr_step("add", "-A")
    _pfr_step(*IDENT, "commit", "-q", "-m", "c")
    sha_c = _pfr_step("rev-parse", "HEAD")
    _pfr_step("branch", PFR_OTHER_BRANCH)
    _pfr_step("checkout", "-q", PFR_BRANCH)
    sha_b = _pfr_step("rev-parse", "HEAD")
    if run_vcs(PFR_HIST, "merge-base", "--is-ancestor", sha_a, "HEAD").returncode != 0:
        sys.exit("fixture setup failed in _build_pfr_history: A is not in the PR head's history")
    if run_vcs(PFR_HIST, "merge-base", "--is-ancestor", sha_c, "HEAD").returncode == 0:
        sys.exit("fixture setup failed in _build_pfr_history: C is in the PR head's history")

    report_a = pfr_report(pfr_verdict("FAIL", 1), "Reviewed at head %s" % sha_a, PFR_FINDING)
    report_b = pfr_report(pfr_verdict("FAIL", 1), "Reviewed at head %s" % sha_b, PFR_FINDING)
    report_c = pfr_report(pfr_verdict("FAIL", 1), "Reviewed at head %s" % sha_c, PFR_FINDING)
    held = {
        # A is on main, so it never counts for PR head B: a report that names only it is dropped.
        "held-ancestor": pfr_call("toolu_rev1", report_a) + pfr_pr(),
        # A held report carries no head, so a record at another head still clears it: a known miss, pinned.
        "held-record-other-head": pfr_call("toolu_rev1", report_b) + pfr_pr()
                                  + pfr_post("toolu_c1", PFR_FAIL_RECORD),
        "held-off-history": pfr_call("toolu_rev1", report_c) + pfr_pr(),
        "held-no-sha": pfr_call("toolu_rev1", pfr_report(pfr_verdict("FAIL", 1), "Reviewed the lane's latest push.",
                                                         PFR_FINDING)) + pfr_pr(),
        # The agentId trailer's hex word resolves to no commit, so it is skipped and no sha counts.
        "held-agent-trailer": pfr_call("toolu_rev1", pfr_report(pfr_verdict("FAIL", 1), PFR_FINDING)
                                       + "\nagentId: a8970de98355e6dce") + pfr_pr(),
        # A path word that names no commit is skipped; C's sha decides the hold, and C is off PR head B's history.
        "held-path-then-off-history": pfr_call("toolu_rev1", pfr_report(
            pfr_verdict("FAIL", 1), "Read notes/c91cf3c2.md first.", "Reviewed at head %s" % sha_c, PFR_FINDING))
                                      + pfr_pr(),
        # The diff base A is skipped as a commit on main; the head B counts, so the report is held for B's PR.
        "held-base-then-head": pfr_call("toolu_rev1", pfr_report(
            pfr_verdict("FAIL", 1), "Diff base %s, head %s." % (sha_a, sha_b), PFR_FINDING)) + pfr_pr(),
        # Read before two PRs. PR X is for a branch that holds no B, so the report stays held for PR Y, which holds B.
        "held-head-then-two-prs": pfr_call("toolu_rev1", report_b) + pfr_pr_open("toolu_pr0", 1466, PFR_OTHER_BRANCH)
                                  + pfr_pr_open("toolu_pr1", 1467, PFR_BRANCH),
        # Done label lines that name head B. Their verdict word is the only thing the cases below test.
        "held-label-round": pfr_call("toolu_rev1", "Done: Round 1 reviewer haiku FAIL\nReviewed at head %s\n%s"
                                     % (sha_b, PFR_FINDING)) + pfr_pr(),
        "held-label-head": pfr_call("toolu_rev1", "Done: HEAD round 1 FAIL\nReviewed at head %s\n%s"
                                    % (sha_b, PFR_FINDING)) + pfr_pr(),
    }
    for name in PFR_HELD:
        write(pfr_path(name), "".join(line + "\n" for line in held[name]))


lazy_fixture([PFR_HIST] + [pfr_path(name) for name in PFR_HELD], _build_pfr_history)


def pfr_ask(name, command, transcript, tool="Bash", agent_id=None, cwd=PUSHFEAT):
    """A push the guard asks about under push-needs-review-record, until each report's record is posted. The ask
    names the rule, never the branch."""
    sh("push-needs-review-record: " + name, command, "ask", rule=PFR_RULE, lacks=PFR_BRANCH, tool=tool,
       cwd=cwd, agent_id=agent_id, transcript=transcript)


def pfr_allow(name, command, transcript, agent_id=None, cwd=PUSHFEAT):
    """A command the guard lets through silently under push-needs-review-record."""
    sh("push-needs-review-record: " + name, command, "allow", silent=True, cwd=cwd, agent_id=agent_id,
       transcript=transcript)


pfr_ask("the incident: a reviewer FAIL in the foreground result, then the push", PFR_PUSH, pfr_path("incident"))
pfr_ask("the incident: the FAIL read from a task-notification user record, then the push", PFR_PUSH,
           pfr_path("incident-notice"))
pfr_ask("the incident: the FAIL read from a queued_command attachment, then the push", PFR_PUSH,
           pfr_path("incident-attachment"))
pfr_ask("the incident from the PowerShell tool, then the push", PFR_PUSH, pfr_path("incident"), tool="PowerShell")
pfr_ask("a FAIL fix check report, then the push", PFR_PUSH, pfr_path("fix-verifier"))
pfr_ask("a reviewer PARTIAL round 1, then the push", PFR_PUSH, pfr_path("partial"))
pfr_ask("a design-reviewer FAIL round 1, then the push", PFR_PUSH, pfr_path("design-fail"))
pfr_ask("a design-reviewer PARTIAL round 1, then the push", PFR_PUSH, pfr_path("design-partial"))
pfr_ask("a builder push: the parent file holds the FAIL, the agent's own file a PASS, then the push", PFR_PUSH,
           pfr_path("builder"), agent_id=PFR_AGENT_ID)
pfr_ask("a FAIL round 2, then a record for the older PASS round 1 only, then the push", PFR_PUSH,
           pfr_path("fail-then-older-pass-record"))
pfr_ask("a FAIL round 1, then a record post that errored, then the push", PFR_PUSH,
           pfr_path("fail-then-errored-record"))
pfr_ask("a FAIL round 1, then a comment that is no record, then the push", PFR_PUSH,
           pfr_path("fail-then-comment"))
pfr_ask("the PR known only from a posted record: a FAIL record, a FAIL round 2, then the push", PFR_PUSH,
           pfr_path("record-known-pr"))
pfr_ask("a FAIL round 1 with a bold lead on its Done line, then the push", PFR_PUSH, pfr_path("bold-lead"))
pfr_ask("a FAIL round 1, then 1500 later reads, then the push", PFR_PUSH, pfr_path("long"))
# A PASS with no record is refused like a FAIL with none: the verdict does not change the rule.
pfr_ask("the #1490 shape: a reviewer PASS round 1, the PR known, no record, then the push", PFR_PUSH,
           pfr_path("pass-no-record"))
pfr_ask("a FAIL round 1, then a PASS round 2 with no PASS record after it, then the push", PFR_PUSH,
           pfr_path("fail-then-fail-pass"))
# A record clears a report only when it holds a line with that report's role and verdict.
pfr_ask("a design-reviewer FAIL cleared only by a reviewer record line, then the push", PFR_PUSH,
           pfr_path("design-fail-reviewer-record"))
pfr_ask("a reviewer PASS cleared only by a FAIL record line, then the push", PFR_PUSH,
           pfr_path("pass-fail-record"))
# Every report needs its own clearing record: an older unrecorded FAIL is not cleared by a newer recorded PASS.
pfr_ask("an unrecorded reviewer FAIL, then a design-reviewer PASS whose record holds only its own line, then the push",
           PFR_PUSH, pfr_path("mixed-unrecorded-reviewer"))
# A hand-back is a report too: the Done line is read through the indent, and its record clears it.
pfr_ask("a reviewer FAIL handed back with no record, then the push", PFR_PUSH, pfr_path("handback-fail"))
pfr_ask("a reviewer PASS handed back with no record, then the push", PFR_PUSH, pfr_path("handback-pass"))
pfr_ask("a PR opened by a Bash gh pr create, a reviewer FAIL with no record, then the push", PFR_PUSH,
           pfr_path("gh-pr-create-fail"))
# The same open, spelled with the repo flag before the verb, after --repo, or after the group word. Each opens a PR.
pfr_ask("a PR opened by gh -R o/r pr create, a reviewer FAIL with no record, then the push", PFR_PUSH,
           pfr_path("gh-root-flag-pr-create-fail"))
pfr_ask("a PR opened by gh --repo o/r pr create, a reviewer FAIL with no record, then the push", PFR_PUSH,
           pfr_path("gh-long-flag-pr-create-fail"))
pfr_ask("a PR opened by gh pr -R o/r create, a reviewer FAIL with no record, then the push", PFR_PUSH,
           pfr_path("gh-group-flag-pr-create-fail"))
pfr_ask("a FAIL round 1, then a record whose only FAIL line is round 2, then the push", PFR_PUSH,
           pfr_path("round-scoped-refuse"))
# Each record clears only the reports it holds, so a later FAIL with no record of its own stays refused.
pfr_ask("a round 3 FAIL after rounds 1 and 2 were recorded, with no record of its own, then the push", PFR_PUSH,
           pfr_path("fail-after-recorded-rounds"))

pfr_allow("a FAIL round 1, then a FAIL record posted, then the push", PFR_PUSH, pfr_path("fail-then-fail-record"))
pfr_allow("a PARTIAL round 1, then a PARTIAL record posted, then the push", PFR_PUSH,
          pfr_path("partial-then-partial-record"))
pfr_allow("a fix check FAIL with its Fix check record posted, then a push to another branch", PFR_NEXT_PUSH,
          pfr_path("fix-verifier-record"))
pfr_allow("a FAIL round 1, then a PASS round 2 with its record posted, then the push", PFR_PUSH,
          pfr_path("fail-then-pass-record"))
pfr_allow("a PASS whose findings mention FAIL, with its PASS record posted, then the push", PFR_PUSH,
          pfr_path("pass-finding-says-fail"))
pfr_allow("an unrecorded reviewer FAIL, then a design-reviewer PASS whose one record holds both lines, then the push",
          PFR_PUSH, pfr_path("mixed-both-recorded"))
pfr_allow("a reviewer FAIL handed back, with its record posted, then the push", PFR_PUSH,
          pfr_path("handback-fail-record"))
pfr_allow("a FAIL round 1, then a record holding its round 1 and round 2 FAIL lines, then the push", PFR_PUSH,
          pfr_path("round-scoped-allow"))
pfr_allow("a PASS whose fenced sample reads FAIL above its Done line, with its PASS record posted, then the push",
          PFR_PUSH, pfr_path("pass-fence-sample"))
pfr_allow("a FAIL round 1, then its record posted by a Bash gh pr comment, then the push", PFR_PUSH,
          pfr_path("fail-gh-pr-comment"))
pfr_allow("a FAIL round 1, then its record posted by a Bash gh api comments call, then the push", PFR_PUSH,
          pfr_path("fail-gh-api-comment"))
pfr_allow("a FAIL round 1, then its record posted by gh -R o/r pr comment, then the push", PFR_PUSH,
          pfr_path("fail-gh-root-flag-pr-comment"))
pfr_allow("a FAIL round 1, then its record posted by gh --repo o/r pr comment, then the push", PFR_PUSH,
          pfr_path("fail-gh-long-flag-pr-comment"))
pfr_allow("a PR open with no review yet, then the push", PFR_PUSH, pfr_path("no-review"))
# A known miss, pinned: a FAIL with no PR known to the session is allowed, so the first push is never blocked.
pfr_allow("a FAIL with no PR known to the session, then the push", PFR_PUSH, pfr_path("no-pr-fail"))
pfr_allow("no transcript_path on the payload, then the push", PFR_PUSH, None)
pfr_allow("an unreadable transcript, then the push", PFR_PUSH, PFR_UNREADABLE)
pfr_allow("an empty transcript, then the push", PFR_PUSH, pfr_path("empty"))
pfr_allow("a dry run beside a FAIL", VCS + " push --dry-run origin HEAD:" + PFR_BRANCH, pfr_path("incident"))
pfr_allow("a git commit whose message says push, beside a FAIL", VCS + ' commit -m "push after the record"',
          pfr_path("incident"))
pfr_allow("a builder push: the parent holds no report, the agent's own file holds a FAIL", PFR_PUSH,
          pfr_path("builder-clean"), agent_id=PFR_AGENT_ID)
# A command that only names `gh pr create` (a search, an echo, a comment, a quoted heredoc body) opens no PR.
pfr_allow("a grep that names gh pr create, then an unrecorded FAIL, then the push", PFR_PUSH,
          pfr_path("gh-mention-grep"))
pfr_allow("an echo that names gh pr create, then an unrecorded FAIL, then the push", PFR_PUSH,
          pfr_path("gh-mention-echo"))
pfr_allow("a comment that names gh pr create, then an unrecorded FAIL, then the push", PFR_PUSH,
          pfr_path("gh-mention-comment"))
pfr_allow("gh pr create inside a quoted heredoc body, then an unrecorded FAIL, then the push", PFR_PUSH,
          pfr_path("gh-mention-heredoc"))
# The control: a real create in a compound command opens the PR, so the same FAIL denies.
pfr_ask("a cd and a real gh pr create --draft, then an unrecorded FAIL, then the push", PFR_PUSH,
           pfr_path("gh-real-create"))
pfr_ask("a bash heredoc whose body is a gh pr create --draft, then an unrecorded FAIL, then the push", PFR_PUSH,
           pfr_path("gh-heredoc-bash"))
pfr_ask("an sh heredoc whose body is a gh pr create --draft, then an unrecorded FAIL, then the push", PFR_PUSH,
           pfr_path("gh-heredoc-sh"))
pfr_ask("a gh pr create --draft in an assigned command substitution, then an unrecorded FAIL, then the push",
           PFR_PUSH, pfr_path("gh-subst-assign"))
pfr_ask("a gh pr create --draft in a double-quoted command substitution, then an unrecorded FAIL, then the push",
           PFR_PUSH, pfr_path("gh-subst-dquote"))
pfr_allow("a single-quoted $(gh pr create) in an echo, then an unrecorded FAIL, then the push", PFR_PUSH,
          pfr_path("gh-subst-squote"))
# A Done line in backticks, or with a verdict word, reads as its verdict: a FAIL with no record denies.
pfr_ask("a FAIL Done line in backticks with no record, then the push", PFR_PUSH, pfr_path("fail-backtick"))
pfr_ask("a FAIL Done line with a verdict word and no record, then the push", PFR_PUSH, pfr_path("fail-bold-verdict"))
pfr_allow("a PASS Done line in backticks, with its PASS record posted, then the push", PFR_PUSH,
          pfr_path("pass-backtick-record"))


# A verdict on the Done label line is read. Each shape below is refused with no record, and the record of the
# FAIL shape clears it. A label line with no verdict word reads its verdict from the ruled line below it.
pfr_ask("a reviewer FAIL round 1 on the Done label line, no record, then the push", PFR_PUSH,
           pfr_path("label-haiku"))
pfr_ask("a reviewer PARTIAL round 1 on the Done label line, no record, then the push", PFR_PUSH,
           pfr_path("label-claude-haiku"))
pfr_ask("a design-reviewer PASS round 2 on the Done label line, no record, then the push", PFR_PUSH,
           pfr_path("label-design"))
pfr_allow("a reviewer FAIL round 1 on the Done label line, its FAIL record posted, then the push", PFR_PUSH,
          pfr_path("label-haiku-record"))
pfr_ask("a Done label line reading see below, then a ruled FAIL round 1 line, no record, then the push", PFR_PUSH,
           pfr_path("see-below-ruled"))
# Each held label report names head B, so the held sha is counted and the verdict word alone decides the refusal.
pfr_ask("a Done label line reading Round 1 with a capital R, naming head B, then the PR, no record, then the push",
           PFR_PUSH, pfr_path("held-label-round"), cwd=PFR_HIST)
pfr_ask("a Done label line whose first all-capitals word is HEAD, naming head B, then the PR, no record, then the push",
           PFR_PUSH, pfr_path("held-label-head"), cwd=PFR_HIST)


# A report read before any PR is known is held by the sha it names. A sha candidate is a hex word above the report's
# agentId trailer. It counts only when it resolves to a commit that is the PR head or an ancestor of it, and is not
# an ancestor of origin/main, so a diff base on main never counts. A report with no counting candidate is dropped.
# A report that one PR does not count stays held for the next PR. The push runs in the PR head's checkout (PFR_HIST).
# Lane ruling, refining coordinator ruling 16:25 CST: held-ancestor was a deny under the old rule.
pfr_allow("a FAIL naming only diff base A, on main and the parent of PR head B, then the PR, no record, then the push",
          PFR_PUSH, pfr_path("held-ancestor"), cwd=PFR_HIST)
pfr_ask("a FAIL naming diff base A then head B, then the PR, no record, then the push", PFR_PUSH,
           pfr_path("held-base-then-head"), cwd=PFR_HIST)
pfr_allow("a FAIL naming head B, then the PR, then a FAIL record at another head posted (a known miss), then the push",
          PFR_PUSH, pfr_path("held-record-other-head"), cwd=PFR_HIST)
pfr_allow("a FAIL naming a path word, then a commit off main, then the PR, no record, then the push", PFR_PUSH,
          pfr_path("held-path-then-off-history"), cwd=PFR_HIST)
pfr_allow("a FAIL naming no sha but an agentId trailer, then the PR, no record, then the push", PFR_PUSH,
          pfr_path("held-agent-trailer"), cwd=PFR_HIST)
pfr_allow("a FAIL naming a commit off main that PR head B does not hold, then the PR, then the push", PFR_PUSH,
          pfr_path("held-off-history"), cwd=PFR_HIST)
pfr_allow("a FAIL naming no sha, then the PR, then the push", PFR_PUSH, pfr_path("held-no-sha"), cwd=PFR_HIST)
pfr_ask("a FAIL naming head B, then a PR for another branch, then the PR for B, no record, then the push", PFR_PUSH,
           pfr_path("held-head-then-two-prs"), cwd=PFR_HIST)


PFR_COST_LABEL = ("push-needs-review-record: a push reads git for a held report only when one is held, and the count "
                  "sees those reads")


def _load_push_guard():
    """guard_push_delete.py, loaded fresh from the folder GUARD sits in, so a mutant copy is the module measured."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "guard_push_delete_cost_case", os.path.join(os.path.dirname(GUARD), "guard_push_delete.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pfr_held_cost_case():
    """The git reads of a push's held-report check, counted in-process with guard_core._git patched. A transcript
    with a PR and a report after it reaches the held check. With no report held, the check must read no git. A
    transcript that holds a report must read git, which shows the count sees the reads it counts."""
    push = _load_push_guard()
    materialize(PFR_HIST)
    materialize(pfr_path("incident"))

    def measure(transcript):
        reads, entries = [], []
        real_git, real_held = push.guard_core._git, push._held_counts

        def counting_git(where, *args):
            reads.append(args)
            return real_git(where, *args)

        def watching_held(held, head, where):
            before = len(reads)
            counted = real_held(held, head, where)
            entries.append(len(reads) - before)
            return counted

        with mock.patch.object(push.guard_core, "_git", counting_git), \
                mock.patch.object(push, "_held_counts", watching_held):
            verdict = push.review_log_hit(transcript, lambda: [], PFR_HIST)
        return verdict, reads, entries

    problems = []
    verdict, reads, entries = measure(pfr_path("incident"))
    if not verdict[0] or not entries:
        problems.append("the no-held transcript did not reach the held check (refused %s, held checks %d)"
                        % (bool(verdict[0]), len(entries)))
    elif reads:
        problems.append("%d git read(s) with no report held, want 0: %r" % (len(reads), reads[:3]))
    _, held_reads, _ = measure(pfr_path("held-head-then-two-prs"))
    if not held_reads:
        problems.append("the held transcript's count saw no git read, so the zero above proves nothing")
    if problems:
        return False, "; ".join(problems)
    return True, "no git read with no report held, and the held transcript's count saw %d" % len(held_reads)


def pfr_fix_refuse(name, command, transcript, lacks=PFR_FIX_BRANCH):
    """A push onto a PR's head branch after its fix check is recorded. The refusal tells the lane to open a new
    branch and a new PR for the next fix, and names neither branch. `lacks` is the branch the push writes, which
    the refusal must not name."""
    sh("push-needs-review-record: " + name, command, "deny", rule=PFR_RULE, lacks=lacks,
       carries=("new branch", "PR"), cwd=PUSHFEAT, transcript=transcript)


pfr_fix_refuse("a fix check PASS for PR 1464 posted, then a push to its head branch", PFR_FIX_PUSH,
               pfr_path("fix-pass-same"))
pfr_fix_refuse("a fix check FAIL for PR 1464 posted, then a push to its head branch", PFR_FIX_PUSH,
               pfr_path("fix-fail-same"))
# A second-review report with no record, after the fix check, does not turn the fix-branch refusal into an ask.
pfr_fix_refuse("a fix check PASS for PR 1464 posted, a round 2 FAIL unrecorded, then a push to its head branch",
               PFR_FIX_PUSH, pfr_path("fix-pass-then-round2-fail"))
# A Fix check line on a PR denies a push to its head branch, and the first-review FAIL beside it stays uncleared. The
# deny comes before that FAIL's ask, so the push is denied, not asked (decision push-needs-review-log).
pfr_fix_refuse("a FAIL round 1 with a Fix check record line for PR 1467, then a push to its head branch: deny, "
               "the fix-branch rule comes before the pending ask", PFR_PUSH, pfr_path("round-fail-fix-record"),
               lacks=PFR_BRANCH)
# A first-review FAIL unrecorded beside a record that holds only a Fix check line: a push to another branch still asks.
pfr_ask("a FAIL round 1 unrecorded beside a Fix check record line for PR 1467, then a push to another branch",
        PFR_NEXT_PUSH, pfr_path("round-fail-fix-record"))
# A documented miss, pinned: a fix check whose PR head is unknown is allowed, so the next PR is never deadlocked.
pfr_allow("a fix check PASS for a PR the transcript never opens, then a push to its branch", PFR_FIX_PUSH,
          pfr_path("fix-pass-unknown-head"))
pfr_allow("a fix check PASS for PR 1464 posted, then a push to a branch whose PR opened after it", PFR_NEXT_PUSH,
          pfr_path("fix-pass-other-branch"))
pfr_allow("a round PASS record with no Fix check line, posted before a push to its head branch", PFR_FIX_PUSH,
          pfr_path("round-record-same"))

# A report names the head it reviewed. A record whose Head line names another head does not clear it: the push asks.
pfr_ask("a round 1 FAIL reviewed at head B, then a FAIL record for head A posted, then the push", PFR_PUSH,
        pfr_path("round-head-b-record-head-a"))
pfr_allow("a round 1 FAIL reviewed at head A, then a FAIL record for head A posted, then the push", PFR_PUSH,
          pfr_path("round-head-a-record-head-a"))
pfr_ask("the #2921 shape: a round 1 FAIL report and no record at all, then the push", PFR_PUSH,
        pfr_path("round-no-record-2921"))
# A real lane's shape: the first-review record is at head A, and a second-review report names the later head B with no record.
pfr_ask("the #2871 shape: a round 1 record at head A, then a round 2 FAIL at head B with no record, then the push",
        PFR_PUSH, pfr_path("2871-round2-unrecorded"))
# A fix verifier is cleared by its reviewed head: here A, the sha of the Fix check line. The record's Head (B) does not match it.
pfr_allow("a round 1 FAIL at head B and a fix check PASS at head A, the record at head B holds both, "
          "then a push to another branch", PFR_NEXT_PUSH, pfr_path("round-head-b-fix-head-a"))
# A fix check reviewed at head B, recorded at head B with its Fix check line at A: the fix record's Head is the one
# the report names. The control reviews head A, the Fix check line's sha, and already allows.
pfr_allow("a fix check reviewed at head B, recorded at head B with its Fix check line at A, then a push to another "
          "branch", PFR_NEXT_PUSH, pfr_path("fix-head-b-record-fix-a"))
pfr_allow("the same fix check reviewed at head A, then a push to another branch", PFR_NEXT_PUSH,
          pfr_path("fix-head-a-record-fix-a"))
# A round report whose text reads `Base: main head B, reviewed A` is reviewed at A, and the record at A clears it.
pfr_allow("a round 1 FAIL whose text reads Base main head B, reviewed A, with its record at A, then the push", PFR_PUSH,
          pfr_path("round-base-head-b-reviewed-a-record-a"))
# The same report, with its only record at head B. B is the base, not the reviewed head, so the push asks.
pfr_ask("a round 1 FAIL whose text reads Base main head B, reviewed A, with its record at B only, then the push",
        PFR_PUSH, pfr_path("round-base-head-b-reviewed-a-record-b-only"))

pfr_ask("a fix check FAIL unrecorded, then a fix check PASS with its record posted, then the push", PFR_NEXT_PUSH,
           pfr_path("fix-fail-then-fix-pass"))
pfr_allow("a fix check FAIL recorded, then a fix check PASS recorded, then a push to another branch", PFR_NEXT_PUSH,
          pfr_path("fix-fail-record-then-fix-pass"))

# A stray line with no message content, after the FAIL report: the reader steps over it, so the FAIL stays unrecorded.
pfr_ask("a round 1 FAIL, then a system line whose message has no content key, then the push", PFR_PUSH,
        pfr_path("stray-no-content"))
pfr_ask("a round 1 FAIL, then a system line whose message is null, then the push", PFR_PUSH, pfr_path("stray-null"))
pfr_ask("a round 1 FAIL, then a system line whose message is a plain string, then the push", PFR_PUSH,
        pfr_path("stray-string"))
pfr_allow("a round 1 FAIL at head A, then a system line with no message content, then the FAIL record at head A, "
          "then the push", PFR_PUSH, pfr_path("stray-no-content-record-head-a"))

# A line that is valid JSON but not an object, after the FAIL report: the reader steps over it, so the FAIL stays
# unrecorded. Each line holds a mark, so the reader parses it; a line with no mark is skipped before the parse.
pfr_ask("a round 1 FAIL, then a transcript line that is a JSON list, then the push", PFR_PUSH,
        pfr_path("stray-list"))
pfr_ask("a round 1 FAIL, then a transcript line that is a bare JSON string, then the push", PFR_PUSH,
        pfr_path("stray-bare-string"))
pfr_allow("a round 1 FAIL at head A, then a transcript line that is a JSON list, then the FAIL record at head A, "
          "then the push", PFR_PUSH, pfr_path("stray-list-record-head-a"))

LOG_CHECKS_EXTRA.append((PFR_COST_LABEL, pfr_held_cost_case))
