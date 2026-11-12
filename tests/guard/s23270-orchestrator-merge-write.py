# section 23270
# =========================================================================== 5j. the orchestrator's merge write
#
# Rule orchestrator-merge-write, decision builders-cannot-edit-tests (the merge route). A session with no agent_id,
# whose own newest get_session record carries cs-build:lane or cs-build:coordinator, and with no set_session_tags call
# after that record, is refused in two places while a merge is in progress:
#   Hit A: an Edit or Write of a product or test path (any path not ending .md) in a checkout where MERGE_HEAD is set.
#   Hit B: a `git commit` or `git merge --continue` while git's own merge of HEAD and MERGE_HEAD conflicts a non-.md
#          path. The conflicts come from merge-tree, not from the index, so a resolved and staged merge is judged too.
# An agent's call is judged by its role, not here: the merge route belongs to a test-author. A record or git read
# that fails allows and logs orchestrator-merge-write-unread. The owner's typed override lifts a refusal. A session
# with no merge pays one MERGE_HEAD probe and reads no transcript.
FAMILY = "orchestrator-merge-write"
ORCH_RULE = "orchestrator-merge-write"
ORCH_UNREAD = ORCH_RULE + "-unread"   # the rule field of a failed read's line, named as agent-role-model-unread is
ORCH_SRC, ORCH_CLEAN, ORCH_DOCS = "src/app.py", "src/clean.py", "latest_results.md"
ORCH_FILES = {**BASE_FILES, ORCH_CLEAN: "z = 0\n"}
ORCH_LANE_TR, ORCH_COORD_TR = role_path("lane"), role_path("coordinator")
ORCH_UNREADABLE_TR = role_path("unreadable")   # a folder: the guard's open() fails on it
ORCH_CONTINUE = VCS + " merge --continue"


def _orch_mid_merge(w, conflicts, clean=(), resolve=False):
    """Cut at main. The lane changes each path in `conflicts` and main changes the same paths, so main's merge into the
    lane conflicts in each. Main also changes each path in `clean`, which the lane never touches. The merge is left in
    progress with MERGE_HEAD set. `resolve` writes each conflicted path a text neither side holds and stages it: the
    index then holds no unmerged path, while git's own merge of HEAD and MERGE_HEAD still conflicts in each."""
    main = w + "-main"
    _must(main, "checkout", "-q", "-b", "lane")
    _put_commit(main, [(rel, "lane " + rel + "\n") for rel in conflicts], "lane work")
    _must(main, "checkout", "-q", "main")
    _must(w, "reset", "-q", "--hard", "lane")
    _put_commit(main, [(rel, "main " + rel + "\n") for rel in list(conflicts) + list(clean)], "main moves")
    if run_vcs(w, *IDENT, "merge", "--no-edit", "main").returncode == 0:
        sys.exit("fixture setup failed: the merge in %r did not conflict" % w)
    for rel in conflicts:
        _require_conflict(w, rel)
    for rel in clean:
        with open(os.path.join(w, rel), encoding="utf-8") as handle:
            if handle.read() != "main " + rel + "\n":
                sys.exit("fixture setup failed: %s did not merge clean in %r" % (rel, w))
    if resolve:
        for rel in conflicts:
            write(os.path.join(w, rel), "resolved " + rel + "\n")
        _must(w, "add", "-A")


ORCH_PLAIN = diff_repo("orch-plain", lambda w: None, files=ORCH_FILES)
ORCH_PROD_OPEN = diff_repo("orch-prod-open", lambda w: _orch_mid_merge(w, [ORCH_SRC], [ORCH_CLEAN]), files=ORCH_FILES)
ORCH_PROD_DONE = diff_repo("orch-prod-done", lambda w: _orch_mid_merge(w, [ORCH_SRC], [ORCH_CLEAN], resolve=True),
                           files=ORCH_FILES)
ORCH_DOCS_OPEN = diff_repo("orch-docs-open", lambda w: _orch_mid_merge(w, [ORCH_DOCS], [ORCH_CLEAN]), files=ORCH_FILES)
ORCH_DOCS_DONE = diff_repo("orch-docs-done", lambda w: _orch_mid_merge(w, [ORCH_DOCS], [ORCH_CLEAN], resolve=True),
                           files=ORCH_FILES)
ORCH_TEST_DONE = diff_repo("orch-test-done", lambda w: _orch_mid_merge(w, [TEST_A], [ORCH_CLEAN], resolve=True),
                           files=ORCH_FILES)
ORCH_TESTMIX_OPEN = diff_repo("orch-testmix-open", lambda w: _orch_mid_merge(w, [TEST_A, ORCH_SRC], [ORCH_CLEAN]),
                              files=ORCH_FILES)
ORCH_TESTMIX_DONE = diff_repo("orch-testmix-done",
                              lambda w: _orch_mid_merge(w, [TEST_A, ORCH_SRC], [ORCH_CLEAN], resolve=True),
                              files=ORCH_FILES)
ORCH_MIXED_DONE = diff_repo("orch-mixed-done",
                            lambda w: _orch_mid_merge(w, [ORCH_DOCS, ORCH_SRC], [ORCH_CLEAN], resolve=True),
                            files=ORCH_FILES)
ORCH_NB = "notebooks/analysis.ipynb"
ORCH_NB_OPEN = diff_repo("orch-nb-open", lambda w: _orch_mid_merge(w, [ORCH_NB], [ORCH_CLEAN]),
                         files={**ORCH_FILES, ORCH_NB: '{"cells": []}\n'})


def orch_write_input(cwd, rel, tool="Edit"):
    """The tool input of one write of `rel` under `cwd`."""
    target = os.path.join(cwd, rel)
    if tool == "Write":
        return {"file_path": target, "content": "x = 7\n"}
    if tool == "MultiEdit":
        return {"file_path": target, "edits": [{"old_string": "x = 1\n", "new_string": "x = 7\n"}]}
    if tool == "NotebookEdit":
        return {"notebook_path": target, "new_source": "x = 7\n"}
    return {"file_path": target, "new_string": "x = 7\n"}


def orch_write(name, expected, cwd, rel, transcript=ORCH_LANE_TR, tool="Edit", env=ROLE_ENV, rule=None,
               silent=False, lacks=(), agent=None):
    """One write of `rel` under `cwd`. `agent` is (agent_id, agent_type) for an agent's own call, else the session's."""
    agent_id, agent_type = agent or (None, None)
    add(name, expected, rule=rule, tool=tool, cwd=cwd, transcript=transcript, env=env, silent=silent,
        lacks=lacks, agent_id=agent_id, agent_type=agent_type, **orch_write_input(cwd, rel, tool))


def orch_refuse(name, cwd, rel, transcript=ORCH_LANE_TR, tool="Edit", env=ROLE_ENV):
    """A write the rule refuses. The refusal names the rule, and names no path it refused."""
    orch_write(name, "deny", cwd, rel, transcript, tool, env, rule=ORCH_RULE, lacks=(rel,))


def orch_allow(name, cwd, rel, transcript=ORCH_LANE_TR, tool="Edit", env=ROLE_ENV, agent=None):
    """A write the rule lets through silently."""
    orch_write(name, "allow", cwd, rel, transcript, tool, env, silent=True, agent=agent)


# ---- Hit A: a lane's or coordinator's own write to a product or test file while a merge is in progress.
orch_refuse("orchestrator-merge-write: a lane's Edit of a product file its merge conflicts is refused",
            ORCH_PROD_OPEN, ORCH_SRC)
orch_refuse("orchestrator-merge-write: a lane's Write of a product file its merge conflicts is refused",
            ORCH_PROD_OPEN, ORCH_SRC, tool="Write")
orch_refuse("orchestrator-merge-write: a lane's Edit of a test file its merge conflicts is refused",
            ORCH_TESTMIX_OPEN, TEST_A)
orch_refuse("orchestrator-merge-write: a lane's Edit of a product file the merge brought in clean is refused",
            ORCH_PROD_OPEN, ORCH_CLEAN)
orch_refuse("orchestrator-merge-write: a lane's Edit of a product file in a merge whose only conflict is a doc is refused",
            ORCH_DOCS_OPEN, ORCH_CLEAN)
orch_refuse("orchestrator-merge-write: a coordinator's Edit of a product file its merge conflicts is refused",
            ORCH_PROD_OPEN, ORCH_SRC, transcript=ORCH_COORD_TR)
orch_allow("orchestrator-merge-write: a lane's Edit of a doc its merge conflicts is allowed", ORCH_DOCS_OPEN, ORCH_DOCS)
orch_allow("orchestrator-merge-write: a lane's Edit of a product file in a checkout with no merge is allowed",
           ORCH_PLAIN, ORCH_SRC)
# The record decides: a newest own record of another tier, or a stale lane read, allows; a newest lane read refuses.
orch_allow("orchestrator-merge-write: a lane's Edit is allowed after set_session_tags on its own session, which makes "
           "the lane read stale", ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("lane-then-tags"))
orch_refuse("orchestrator-merge-write: a lane's Edit is refused after set_session_tags on another session, which leaves "
            "its own lane record current", ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("lane-then-other-tags"))
orch_allow("orchestrator-merge-write: a lane's Edit is allowed after a newer untagged read of its own record",
           ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("lane-then-untagged"))
orch_allow("orchestrator-merge-write: a lane's Edit is allowed after a newer triage read of its own record",
           ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("lane-then-triage"))
orch_refuse("orchestrator-merge-write: a lane's Edit is refused after a newer lane read, when a triage read came first",
            ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("triage-then-lane"))
orch_refuse("orchestrator-merge-write: a lane's Edit is refused after a newer lane read, when an untagged read came first",
            ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("untagged-then-lane"))
orch_allow("orchestrator-merge-write: an untagged session's Edit is allowed, beside a newer lane record of another session",
           ORCH_PROD_OPEN, ORCH_SRC, transcript=role_path("foreign-lane-newest"))
orch_allow("orchestrator-merge-write: a batch runner's Edit is allowed in a merge", ORCH_PROD_OPEN, ORCH_SRC,
           transcript=role_path("runner"))
orch_allow("orchestrator-merge-write: a triage session's Edit is allowed in a merge", ORCH_PROD_OPEN, ORCH_SRC,
           transcript=role_path("triage"))
orch_allow("orchestrator-merge-write: an untagged solo session's Edit is allowed in a merge", ORCH_PROD_OPEN, ORCH_SRC,
           transcript=role_path("untagged"))
# An agent's own call passes this rule whatever its record says. Its role decides the write, and a record-writer's
# product write is refused by its own role, which this rule does not name.
orch_allow("orchestrator-merge-write: a test-author's Edit of a test file its merge conflicts is allowed",
           ORCH_TESTMIX_OPEN, TEST_A, agent=("auth-orch", "test-author"))
orch_allow("orchestrator-merge-write: a builder's Edit of a product file its merge conflicts is allowed",
           ORCH_PROD_OPEN, ORCH_SRC, agent=("bld-orch", "builder"))
orch_allow("orchestrator-merge-write: a general-purpose agent's Edit of a product file its merge conflicts is allowed",
           ORCH_PROD_OPEN, ORCH_SRC, agent=("gp-orch", "general-purpose"))
orch_write("orchestrator-merge-write: a record-writer's Edit of a product file is refused by record-writer-scope, not by this rule",
           "deny", ORCH_PROD_OPEN, ORCH_SRC, rule="record-writer-scope", lacks=(ORCH_RULE,),
           agent=("rw-orch", "record-writer"))
# MultiEdit and NotebookEdit take the same route: write_targets reads every path field of the call.
orch_refuse("orchestrator-merge-write: a lane's MultiEdit of a product file its merge conflicts is refused",
            ORCH_PROD_OPEN, ORCH_SRC, tool="MultiEdit")
orch_refuse("orchestrator-merge-write: a lane's NotebookEdit of a notebook its merge conflicts is refused",
            ORCH_NB_OPEN, ORCH_NB, tool="NotebookEdit")
orch_allow("orchestrator-merge-write: a lane's MultiEdit of a doc its merge conflicts is allowed",
           ORCH_DOCS_OPEN, ORCH_DOCS, tool="MultiEdit")
orch_allow("orchestrator-merge-write: a builder's MultiEdit of a product file its merge conflicts is allowed",
           ORCH_PROD_OPEN, ORCH_SRC, tool="MultiEdit", agent=("bld-orch", "builder"))


def orch_log_rules(config):
    """The rule field of each guard.log line in `config`."""
    return [line.split("\t")[3] for line in gs_log_lines(config) if line.count("\t") >= 3]


def orch_unread_check(key, cwd, tool_input, tool="Edit", transcript=ORCH_LANE_TR, env=ROLE_ENV, env_path=None):
    """A check that a read which fails allows silently and logs ORCH_UNREAD. The folder is this check's own, so the log
    holds this call's line and no other's."""
    config = os.path.join(ROOT, "orchcfg", key)
    case = orch_case(cwd, tool, tool_input, transcript, env, config, env_path)

    def check():
        os.makedirs(config, exist_ok=True)
        if os.path.exists(os.path.join(config, "guard.log")):
            os.remove(os.path.join(config, "guard.log"))
        got, reason = decide(case)
        if got != "allow" or reason:
            return False, "got %s (%s), want a silent allow" % (got, reason[:70])
        if ORCH_UNREAD not in orch_log_rules(config):
            return False, "guard.log holds no %s line, so the failed read left no trace" % ORCH_UNREAD
        return True, "allowed silently, and logged %s" % ORCH_UNREAD
    FIXTURELESS_CHECKS.add(check)
    return check


def orch_silent_check(key, cwd, tool_input, env=None):
    """A check that a session with no id in the env is allowed silently: no reason, and no guard.log line at all.
    The folder is this check's own, so the log holds this call's lines and no other's."""
    config = os.path.join(ROOT, "orchcfg", key)
    case = orch_case(cwd, "Edit", tool_input, ORCH_LANE_TR, env, config)

    def check():
        os.makedirs(config, exist_ok=True)
        if os.path.exists(os.path.join(config, "guard.log")):
            os.remove(os.path.join(config, "guard.log"))
        got, reason = decide(case)
        if got != "allow" or reason:
            return False, "got %s (%s), want a silent allow" % (got, reason[:70])
        lines = gs_log_lines(config)
        if lines:
            return False, "guard.log holds %d line(s), want none: %s" % (len(lines), lines[0][:90])
        return True, "allowed silently, with no guard.log line"
    FIXTURELESS_CHECKS.add(check)
    return check


def orch_case(cwd, tool, tool_input, transcript, env, config, env_path=None, agent=None):
    """The decide() case of one guard call, for a log check that builds it by hand."""
    agent_id, agent_type = agent or (None, None)
    return {"raw": None, "tool": tool, "cwd": cwd, "session": None, "env_path": env_path, "config": config,
            "agent_id": agent_id, "agent_type": agent_type, "temp": None, "env": env, "tool_input": tool_input,
            "transcript": transcript, "load": None}


# A read that fails allows, and the log names it. Each row is one way a read fails.
LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: an Edit in a merge whose transcript is unreadable is allowed and logged "
                         + ORCH_UNREAD,
                         orch_unread_check("unreadable", ORCH_PROD_OPEN, orch_write_input(ORCH_PROD_OPEN, ORCH_SRC),
                                           transcript=ORCH_UNREADABLE_TR)))
LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: an Edit in a merge whose transcript names no file is allowed and "
                         "logged " + ORCH_UNREAD,
                         orch_unread_check("missing", ORCH_PROD_OPEN, orch_write_input(ORCH_PROD_OPEN, ORCH_SRC),
                                           transcript=role_path("missing"))))
LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: an Edit in a merge with no session id in the env is allowed silently, "
                         "with no guard.log line",
                         orch_silent_check("noenv", ORCH_PROD_OPEN, orch_write_input(ORCH_PROD_OPEN, ORCH_SRC),
                                           env=None)))
LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: a commit of a merge with an unreadable transcript is allowed and "
                         "logged " + ORCH_UNREAD,
                         orch_unread_check("commit-unreadable", ORCH_PROD_DONE, {"command": COMMIT}, tool="Bash",
                                           transcript=ORCH_UNREADABLE_TR)))
if os.name == "nt":
    skip_case("orchestrator-merge-write: an Edit in a merge with git unable to answer is allowed and logged "
              + ORCH_UNREAD, NO_STAND_IN)
else:
    LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: an Edit in a merge with git unable to answer is allowed and logged "
                             + ORCH_UNREAD,
                             orch_unread_check("blind-git", ORCH_PROD_OPEN, orch_write_input(ORCH_PROD_OPEN, ORCH_SRC),
                                               env_path=GITBLIND)))


def orch_cost_check():
    """A lane's Edit with no merge in progress and no agent makes one git call that reads MERGE_HEAD, no merge-tree
    call, and no transcript read. GIT_TRACE makes each git process write its argv. A control, the same call in a merge,
    must log the failed read first, so the absent line on the no-merge call shows that the transcript was not read."""
    folder = os.path.join(ROOT, "orchcfg", "orch-cost")
    control_folder = os.path.join(ROOT, "orchcfg", "orch-cost-control")
    for path in (folder, control_folder):
        os.makedirs(path, exist_ok=True)
    trace = os.path.join(folder, "plain.trace")
    if os.path.exists(trace):
        os.remove(trace)
    plain = orch_case(ORCH_PLAIN, "Edit", orch_write_input(ORCH_PLAIN, ORCH_SRC), ORCH_UNREADABLE_TR,
                      dict(ROLE_ENV, GIT_TRACE=trace), folder)
    got, reason = decide(plain)
    if got != "allow" or reason:
        return False, "the no-merge Edit: got %s (%s), want a silent allow" % (got, reason[:70])
    lines = [line for line in gs_read(trace).splitlines() if line.strip()]
    if not lines:
        return False, "the guard's git calls wrote no trace, so a count of zero would prove nothing"
    probes = [line for line in lines if "rev-parse" in line and "MERGE_HEAD" in line]
    if len(probes) != 1:
        return False, "the no-merge Edit ran %d rev-parse calls that name MERGE_HEAD, want exactly 1" % len(probes)
    if any("merge-tree" in line for line in lines):
        return False, "the no-merge Edit ran a merge-tree call, which reads a merge that is not in progress"
    control = orch_case(ORCH_PROD_OPEN, "Edit", orch_write_input(ORCH_PROD_OPEN, ORCH_SRC), ORCH_UNREADABLE_TR,
                        ROLE_ENV, control_folder)
    decide(control)
    if ORCH_UNREAD not in orch_log_rules(control_folder):
        return False, "control: the same call in a merge logged no %s line, so the probe shows no read" % ORCH_UNREAD
    if ORCH_UNREAD in orch_log_rules(folder):
        return False, "the no-merge Edit read the transcript, and logged %s" % ORCH_UNREAD
    return True, "one MERGE_HEAD probe, no merge-tree call, no transcript read; the control in a merge logs its read"


FIXTURELESS_CHECKS.add(orch_cost_check)
LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: a call with no merge in progress makes one MERGE_HEAD probe, no "
                         "merge-tree call and no transcript read", orch_cost_check))


def orch_commit_override_check():
    """The owner's one-act override lets a refused commit through once, and the next commit is refused again. The
    rule is in no never_lifted list, so the override reaches it."""
    config, session = ov_config("orch-commit-once"), "ov-orch-commit-once"

    def call(seconds):
        return lambda: ov_call("Bash", {"command": COMMIT}, ORCH_PROD_DONE, config, session, seconds,
                               env=ROLE_ENV, transcript=ORCH_LANE_TR)
    ok, why = ov_story([("with no override", call(0), "deny", ORCH_RULE)])
    if not ok:
        return False, why
    note = ov_type(config, session, "override")
    ok, why = ov_story([("first call", call(60), "allow", ORCH_RULE),
                        ("second call, override spent", call(120), "deny", ORCH_RULE)], note)
    if not ok:
        return False, why
    return True, "refused, then allowed once by the owner's override, then refused again"


FIXTURELESS_CHECKS.add(orch_commit_override_check)
LOG_CHECKS_EXTRA.append(("orchestrator-merge-write: a one-act owner override lets a refused commit through once, then "
                         "refuses again", orch_commit_override_check))

# ---- Hit B: a lane's or coordinator's commit or merge --continue of a merge that conflicts a non-.md path. These
# merges are resolved and staged: the index holds no unmerged path, and the rule still refuses.
sh("orchestrator-merge-write: a lane's git commit of a merge that conflicts a product file is refused", COMMIT, "deny",
   rule=ORCH_RULE, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV, lacks=(ORCH_SRC,))
sh("orchestrator-merge-write: a lane's git merge --continue of a merge that conflicts a product file is refused",
   ORCH_CONTINUE, "deny", rule=ORCH_RULE, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV, lacks=(ORCH_SRC,))
sh("orchestrator-merge-write: a coordinator's git commit of a merge that conflicts a test file is refused", COMMIT,
   "deny", rule=ORCH_RULE, cwd=ORCH_TEST_DONE, transcript=ORCH_COORD_TR, env=ROLE_ENV, lacks=(TEST_A,))
sh("orchestrator-merge-write: a lane's git commit of a merge that conflicts a doc and a product file is refused",
   COMMIT, "deny", rule=ORCH_RULE, cwd=ORCH_MIXED_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV, lacks=(ORCH_SRC,))
sh("orchestrator-merge-write: a lane's git commit of a merge that conflicts a test file and a product file is refused",
   COMMIT, "deny", rule=ORCH_RULE, cwd=ORCH_TESTMIX_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV, lacks=(TEST_A,))
# The commit is found through the shell scanner: a comment opener, a multi-line quoted string and a lone quote in text
# before the real call do not hide it.
sh("orchestrator-merge-write: a comment opener inside a string does not hide a lane's commit of a conflicted merge",
   'echo "# note" && ' + COMMIT, "deny", rule=ORCH_RULE, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a multi-line quoted string does not hide a lane's commit of a conflicted merge",
   'echo "first\nline" && ' + COMMIT, "deny", rule=ORCH_RULE, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a lone quote in text does not hide a lane's commit of a conflicted merge",
   'echo "it\'s" && ' + COMMIT, "deny", rule=ORCH_RULE, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)

sh("orchestrator-merge-write: a lane's git commit of a merge that conflicts only a doc is allowed", COMMIT, "allow",
   silent=True, cwd=ORCH_DOCS_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a lane's git merge --continue of a merge that conflicts only a doc is allowed",
   ORCH_CONTINUE, "allow", silent=True, cwd=ORCH_DOCS_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a lane's git commit with no merge in progress is allowed", COMMIT, "allow", silent=True,
   cwd=ORCH_PLAIN, transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a batch runner's git commit of a conflicted merge is allowed", COMMIT, "allow",
   silent=True, cwd=ORCH_PROD_DONE, transcript=role_path("runner"), env=ROLE_ENV)
sh("orchestrator-merge-write: a triage session's git commit of a conflicted merge is allowed", COMMIT, "allow",
   silent=True, cwd=ORCH_PROD_DONE, transcript=role_path("triage"), env=ROLE_ENV)
sh("orchestrator-merge-write: an untagged solo session's git commit of a conflicted merge is allowed", COMMIT, "allow",
   silent=True, cwd=ORCH_PROD_DONE, transcript=role_path("untagged"), env=ROLE_ENV)
sh("orchestrator-merge-write: a lane's git commit is allowed after set_session_tags on its own session, which makes "
   "the lane read stale", COMMIT, "allow", silent=True, cwd=ORCH_PROD_DONE, transcript=role_path("lane-then-tags"),
   env=ROLE_ENV)
# The merge route: a test-author's commit of a merge it resolves is an agent's, not this rule's.
sh("orchestrator-merge-write: a test-author's git commit of a merge that conflicts a test file is allowed", COMMIT,
   "allow", silent=True, cwd=ORCH_TESTMIX_DONE, agent_id="auth-orch", agent_type="test-author",
   transcript=ORCH_LANE_TR, env=ROLE_ENV)
# Text that names the command is no call: quoted text, a grep pattern, a heredoc body and a trailing comment.
sh("orchestrator-merge-write: a commit named in quoted text is not a call, in a conflicted merge",
   'echo "' + COMMIT + '"', "allow", silent=True, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a commit named in a grep pattern is not a call, in a conflicted merge",
   "grep -n '" + VCS + " commit' notes.md", "allow", silent=True, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR,
   env=ROLE_ENV)
sh("orchestrator-merge-write: a commit named in a heredoc body is not a call, in a conflicted merge",
   "cat > notes.txt <<'EOF'\n" + COMMIT + "\nEOF", "allow", silent=True, cwd=ORCH_PROD_DONE,
   transcript=ORCH_LANE_TR, env=ROLE_ENV)
sh("orchestrator-merge-write: a commit named in a trailing comment is not a call, in a conflicted merge",
   "echo done # " + COMMIT, "allow", silent=True, cwd=ORCH_PROD_DONE, transcript=ORCH_LANE_TR, env=ROLE_ENV)
