# section 43724
FAMILY = "ready-mcp-mark-guard"
#
# `ready-mcp-mark-guard`. A ready mark by the GitHub MCP update tool (draft false) is allowed only when the merge tool's
# ready checks passed on the pull request's current head. `merge <pr> --ready` writes no durable record of that pass:
# run_ready_checks (merge/merge.py) prints one stdout line, `merge: the ready checks (...) pass on <sha9>.`, and the line
# reaches the guard only through the session transcript, as the result of the Bash call. So the rule reads the session's
# own transcript for a `merge <pr> --ready` call whose result names a passing run for the head the pull request now has.
#
# THE FIXTURE. The records-page-ready fixture (section 16449). GHREADY_CURRENT is feat-current, whose records page is current,
# so records-page-ready allows the mark on main. Each case below changes only its transcript (or the call's draft field),
# so the verdict comes from this rule alone. A pass on feat-current^ is a pass on an older head of the same pull request.

RPM_RULE = "ready-mcp-mark-guard"
RPM = os.path.join(ROOT, "readymark")                          # the transcripts of these cases, under this run's folder
RPM_NO_PASS = os.path.join(RPM, "no-pass.jsonl")               # a Bash call that is not a ready run
RPM_OLD_PASS = os.path.join(RPM, "pass-older-head.jsonl")      # a pass on feat-current^, the head before feat-current
RPM_PASS = os.path.join(RPM, "pass-current-head.jsonl")        # a pass on feat-current, the current head
RPM_CLAIM_PASS = os.path.join(RPM, "pass-claim-head.jsonl")    # a pass on feat-claim, then the Record-claim stop of the draft step
RPM_REMEDY = ("merge 12 --ready",)                              # the refusal names the ready run the session must make
RPM_TARGET_LACKS = ("update_pull_request", "gh pr ready")       # the refusal never names the forbidden mark (the target)
RPM_CONFIRM_PASS = os.path.join(RPM, "confirm-pass-current-head.jsonl")   # `merge 12 --confirm` on the draft: a pass on feat-current
RPM_CONFIRM_OLD = os.path.join(RPM, "confirm-pass-older-head.jsonl")      # the same run, a pass on feat-current^
RPM_FAST_PASS = os.path.join(RPM, "fast-checks-pass-current-head.jsonl")  # `merge 12 --fast-checks`: the same pass line, and no records step
RPM_NOCHECKS_PASS = os.path.join(RPM, "no-checks-current-head.jsonl")     # a ready run in a repo with no ready checks, its records line on feat-current
RPM_NOCHECKS_OLD = os.path.join(RPM, "no-checks-older-head.jsonl")        # the same run, its records line on feat-current^
RPM_DRY_PASS = os.path.join(RPM, "dry-merge-pass-current-head.jsonl")     # a ready run on a dev-base head that lacks the dev tip: the pass on its dry merge
RPM_DRY_OLD = os.path.join(RPM, "dry-merge-pass-older-head.jsonl")        # the same pass, its dry-merge line naming the head before it
RPM_NOT_DEFAULT = "merge: dev is not the default branch (main). The records page is rebuilt only for it. Nothing was pushed."
RPM_NO_CHECKS = "merge: this repo declares no ready checks (merge.readyChecks), so the draft step runs none."
RPM_DRAFT_LINE = "merge: #12 stays a draft. Mark it ready after its draft run shows."
RPM_UNCHECKED_PASS = os.path.join(RPM, "unchecked-current-head.jsonl")  # a ready run on a base other than the default, no ready checks: its unchecked line names feat-dev-behind
RPM_UNCHECKED_OLD = os.path.join(RPM, "unchecked-older-head.jsonl")     # the same run, its unchecked line naming feat-dev-behind^
RPM_CLAIM_STOP = os.path.join(RPM, "claim-stop-current-head.jsonl")     # a ready run that stops on a Record-claim head, no ready checks: the stop names feat-claim
RPM_CLAIM_STOP_OLD = os.path.join(RPM, "claim-stop-older-head.jsonl")   # the same stop, naming feat-claim^
# Background runs (`merge 12 --ready` with run_in_background). The pass reaches the guard only when the session reads the run's output
# file in the transcript: a Read or a Bash cat of its path. The guard never opens that file on disk.
RPM_BG_READ = os.path.join(RPM, "bg-read.jsonl")                # a ready run on the current head, its output read by Read
RPM_BG_CAT = os.path.join(RPM, "bg-cat.jsonl")                  # the same run, its output read by a Bash cat
RPM_BG_OLD = os.path.join(RPM, "bg-older-head.jsonl")           # a ready run whose output read shows a pass on feat-current^
RPM_BG_FAILED = os.path.join(RPM, "bg-failed.jsonl")            # a ready run whose output read shows a failed ready check on the current head
RPM_BG_NEVER = os.path.join(RPM, "bg-never-read.jsonl")         # a ready run whose output file holds the pass, and no read of it is in the transcript
RPM_BG_NOTICE = os.path.join(RPM, "bg-notice.jsonl")            # a ready run with a completed notice that names no output text, and no read of the output
RPM_BG_OTHER = os.path.join(RPM, "bg-other-job.jsonl")          # a read of the output of `sleep 600`, a background job that is no ready run
RPM_BG_FAST = os.path.join(RPM, "bg-fast-checks.jsonl")         # a background `--fast-checks` run whose output read shows the pass
RPM_OTHER_PR = os.path.join(RPM, "other-pr-pass.jsonl")         # a foreground `merge 13 --ready` whose pass is the current head of #12


def _rpm_pass(sha):
    """The stdout line of run_ready_checks on a pass, as the Bash result carries it."""
    return "merge: the ready checks (check invariants) pass on %s." % sha[:9]


def _rpm_ready_run(tool_id, *results):
    """One paired Bash call, `merge 12 --ready`, whose result lines are `results`."""
    return [role_use(tool_id, "Bash", {"command": MERGE_SHIM + " 12 --ready"}), role_result(tool_id, "\n".join(results))]


def _rpm_run(tool_id, args, *results):
    """One paired Bash call, `merge 12 <args>`, whose result lines are `results`."""
    return [role_use(tool_id, "Bash", {"command": MERGE_SHIM + " 12 " + args}), role_result(tool_id, "\n".join(results))]


def _rpm_records_current(sha):
    """The line draft_step prints when the head's records page is current (merge/merge.py, draft_step)."""
    return "merge: the records page on feat-current at %s is current. Nothing was pushed." % sha[:9]


def _rpm_dry_line(head, dry):
    """The line a dry merge must print, which merge.py does not print yet: the pull request head it merged, then the dry merge's sha.
    open_merge_worktree commits the dry merge with that head as its first parent, so the line ties the pass's sha to the head."""
    return "merge: the dry merge of %s into dev is %s." % (head[:9], dry[:9])


def _rpm_unchecked_line(head):
    """The line the draft step prints on a base other than the default, with no ready checks: the one line that names its head (merge/merge.py)."""
    return "merge: the draft step ran no checks on #12 at %s. Nothing was pushed." % head[:9]


def _rpm_claim_stop(sha):
    """The stop a head that holds a Record-claim prints on a ready run (merge/merge.py, draft_step), as the Bash result carries it."""
    return ("merge: %s on feat-claim holds a Record-claim (D-002), so the draft step adds no page commit on top of it. "
            "Mark #12 ready by hand, then run --confirm again. Nothing was pushed." % sha[:9])


def _rpm_bg_output(job):
    """The output file the harness names for background job `job`, in this run's folder."""
    return os.path.join(RPM, "bg-%s.output" % job)


def _rpm_numbered(text):
    """The text as the Read tool prints it: each line with its line number and a tab."""
    return "\n".join("%6d\t%s" % (number, line) for number, line in enumerate(text.split("\n"), 1))


def _rpm_bg_start(tool_id, job, command):
    """A Bash call that the session started with run_in_background, and its start result: the job ID and the output file it names."""
    return [role_use(tool_id, "Bash", {"command": command, "run_in_background": True}),
            role_result(tool_id, "Command running in background with ID: %s. Output is being written to: %s" % (job, _rpm_bg_output(job)))]


def _rpm_bg_read(tool_id, job, text):
    """A Read call of background job `job`'s output file, and its result."""
    return [role_use(tool_id, "Read", {"file_path": _rpm_bg_output(job)}), role_result(tool_id, _rpm_numbered(text))]


def _rpm_bg_cat(tool_id, job, text):
    """A Bash cat of background job `job`'s output file, and its result. The command names no ready flag."""
    return [role_use(tool_id, "Bash", {"command": "cat " + _rpm_bg_output(job)}), role_result(tool_id, text)]


def _rpm_bg_notice(job, command_text):
    """The completion notice of background job `job` as the transcript holds it: a task-harness user record with the status and a
    summary, and no output text. The origin sits at the record's top level, as test_local_time writes it."""
    body = ("<task-notification>\n<task-id>%s</task-id>\n<output-file>%s</output-file>\n<status>completed</status>\n"
            "<summary>Background command \"%s\" completed (exit code 0)</summary>\n</task-notification>"
            % (job, _rpm_bg_output(job), command_text))
    return json.dumps({"type": "user", "origin": {"kind": "task-notification"}, "message": {"role": "user", "content": body}})


def _build_readymark():
    materialize(RPR)  # the records-page fixture: its heads and fake gh answers are the ones these transcripts name
    os.makedirs(RPM, exist_ok=True)
    current = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-current")
    older = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-current^")
    claim = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-claim")
    # Scope before subject: the older head is an ancestor of the current head, and the claim head is another pull request's head.
    _rpr_need(run_vcs(RPR_SEED, "merge-base", "--is-ancestor", older, current).returncode == 0,
              "feat-current^ is not an ancestor of feat-current, so it is no older head of it")
    _rpr_need(older != current and claim != current, "the heads of the ready-mark cases are not distinct")
    dev_behind = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-dev-behind")
    dev_behind_older = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-dev-behind^")
    dev_tip = _rpr_git(RPR_SEED, "rev-parse", "--verify", "dev")
    # Scope before subject: the dev-base head lacks the dev tip, its older head is its parent, the records-page repo declares no
    # ready checks, and the dev-base clone declares them. The dry merge is built the way open_merge_worktree builds it.
    _rpr_need(run_vcs(RPR_SEED, "merge-base", "--is-ancestor", dev_tip, dev_behind).returncode == 1,
              "feat-dev-behind holds the dev tip, so its dry merge is not the one the case names")
    _rpr_need(run_vcs(RPR_SEED, "merge-base", "--is-ancestor", dev_behind_older, dev_behind).returncode == 0,
              "feat-dev-behind^ is not an ancestor of feat-dev-behind, so it is no older head of it")
    _rpr_need("readyChecks" not in _rpr_git(RPR_REPO, "show", "HEAD:.github/stamp.json"),
              "the records-page repo declares ready checks, so its ready run would print a pass line")
    _rpr_need("readyChecks" in _rpr_git(RPR_DEV_BEHIND_CLONE, "show", "HEAD:.github/stamp.json"),
              "the dev-base clone declares no ready checks, so its ready run would print no dry-merge pass")
    dry_tree = _rpr_git(RPR_DEV_BEHIND_CLONE, "merge-tree", "--write-tree", dev_behind, dev_tip)
    dry = _rpr_git(RPR_DEV_BEHIND_CLONE, "commit-tree", dry_tree, "-p", dev_behind, "-p", dev_tip,
                   "-m", "dry merge of %s into dev" % dev_behind[:9])
    claim_older = _rpr_git(RPR_SEED, "rev-parse", "--verify", "feat-claim^")
    _rpr_need(run_vcs(RPR_SEED, "merge-base", "--is-ancestor", claim_older, claim).returncode == 0,
              "feat-claim^ is not an ancestor of feat-claim, so it is no older head of it")
    _rpr_need(_rpr_git(RPR_DEV_BEHIND_CLONE, "rev-parse", dry + "^1") == dev_behind
              and _rpr_git(RPR_DEV_BEHIND_CLONE, "rev-parse", dry + "^2") == dev_tip,
              "the dry merge does not hold the head as its first parent and the dev tip as its second")
    # The output file of each background job, as the run wrote it. The file is on disk for every job, so a guard that opened it would
    # see the pass of the never-read case. Scope before subject: each job has its own file, and the one never read exists on disk.
    ready_out = _rpm_pass(current) + "\n" + RPM_DRAFT_LINE
    outputs = {
        "bgread": ready_out,
        "bgcat": ready_out,
        "bgold": _rpm_pass(older) + "\n" + RPM_DRAFT_LINE,
        "bgfail": "the ready checks of %s against main FAIL:\n  lint: fail\n#12 stays a draft and nothing was pushed. "
                  "Fix it on the branch, push, and run --confirm again." % current[:9],
        "bgnever": ready_out,
        "bgnote": ready_out,
        "bgsleep": _rpm_pass(current),
        "bgfast": _rpm_pass(current),
    }
    for job, text in outputs.items():
        with open(_rpm_bg_output(job), "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    _rpr_need(len({_rpm_bg_output(job) for job in outputs}) == len(outputs), "two background jobs share an output file")
    _rpr_need(os.path.isfile(_rpm_bg_output("bgnever")), "the never-read output file is missing, so that case would pin nothing")
    lines = {
        RPM_NO_PASS: _rpm_ready_run("ready-none","merge: #12 stays a draft. Mark it ready after its draft run shows."),
        RPM_OLD_PASS: _rpm_ready_run("ready-old", _rpm_pass(older), "merge: #12 stays a draft. Mark it ready after its draft run shows."),
        RPM_PASS: _rpm_ready_run("ready-now", _rpm_pass(current), "merge: #12 stays a draft. Mark it ready after its draft run shows."),
        RPM_CLAIM_PASS: _rpm_ready_run(
            "ready-claim", _rpm_pass(claim),
            "merge: %s on feat-claim holds a Record-claim (D-002), so the draft step adds no page commit on top of it. "
            "Mark #12 ready by hand, then run --confirm again. Nothing was pushed." % claim[:9]),
        RPM_CONFIRM_PASS: _rpm_run("confirm-now", "--confirm", _rpm_pass(current), _rpm_records_current(current), RPM_DRAFT_LINE),
        RPM_CONFIRM_OLD: _rpm_run("confirm-old", "--confirm", _rpm_pass(older), RPM_DRAFT_LINE),
        RPM_FAST_PASS: _rpm_run("fast-now", "--fast-checks", _rpm_pass(current)),
        RPM_NOCHECKS_PASS: _rpm_ready_run("nochecks-now", RPM_NO_CHECKS, _rpm_records_current(current), RPM_DRAFT_LINE),
        RPM_NOCHECKS_OLD: _rpm_ready_run("nochecks-old", RPM_NO_CHECKS, _rpm_records_current(older), RPM_DRAFT_LINE),
        RPM_DRY_PASS: _rpm_ready_run("dry-now", RPM_NOT_DEFAULT, _rpm_dry_line(dev_behind, dry), _rpm_pass(dry), RPM_DRAFT_LINE),
        RPM_DRY_OLD: _rpm_ready_run("dry-old", RPM_NOT_DEFAULT, _rpm_dry_line(dev_behind_older, dry), _rpm_pass(dry), RPM_DRAFT_LINE),
        RPM_UNCHECKED_PASS: _rpm_ready_run("unchecked-now", RPM_NO_CHECKS, RPM_NOT_DEFAULT, _rpm_unchecked_line(dev_behind), RPM_DRAFT_LINE),
        RPM_UNCHECKED_OLD: _rpm_ready_run("unchecked-old", RPM_NO_CHECKS, RPM_NOT_DEFAULT, _rpm_unchecked_line(dev_behind_older), RPM_DRAFT_LINE),
        RPM_CLAIM_STOP: _rpm_ready_run("claim-stop-now", RPM_NO_CHECKS, _rpm_claim_stop(claim)),
        RPM_CLAIM_STOP_OLD: _rpm_ready_run("claim-stop-old", RPM_NO_CHECKS, _rpm_claim_stop(claim_older)),
        RPM_BG_READ: _rpm_bg_start("bg-read-start", "bgread", MERGE_SHIM + " 12 --ready") + _rpm_bg_read("bg-read-read", "bgread", outputs["bgread"]),
        RPM_BG_CAT: _rpm_bg_start("bg-cat-start", "bgcat", MERGE_SHIM + " 12 --ready") + _rpm_bg_cat("bg-cat-read", "bgcat", outputs["bgcat"]),
        RPM_BG_OLD: _rpm_bg_start("bg-old-start", "bgold", MERGE_SHIM + " 12 --ready") + _rpm_bg_read("bg-old-read", "bgold", outputs["bgold"]),
        RPM_BG_FAILED: _rpm_bg_start("bg-failed-start", "bgfail", MERGE_SHIM + " 12 --ready") + _rpm_bg_read("bg-failed-read", "bgfail", outputs["bgfail"]),
        RPM_BG_NEVER: _rpm_bg_start("bg-never-start", "bgnever", MERGE_SHIM + " 12 --ready"),
        RPM_BG_NOTICE: _rpm_bg_start("bg-notice-start", "bgnote", MERGE_SHIM + " 12 --ready") + [_rpm_bg_notice("bgnote", "merge 12 --ready")],
        RPM_BG_OTHER: _rpm_bg_start("bg-other-start", "bgsleep", "sleep 600") + _rpm_bg_read("bg-other-read", "bgsleep", outputs["bgsleep"]),
        RPM_BG_FAST: _rpm_bg_start("bg-fast-start", "bgfast", MERGE_SHIM + " 12 --fast-checks") + _rpm_bg_read("bg-fast-read", "bgfast", outputs["bgfast"]),
        RPM_OTHER_PR: [role_use("other-pr-ready", "Bash", {"command": MERGE_SHIM + " 13 --ready"}),
                       role_result("other-pr-ready", _rpm_pass(current))],
    }
    for path, rows in lines.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")


lazy_fixture([RPM_NO_PASS, RPM_OLD_PASS, RPM_PASS, RPM_CLAIM_PASS, RPM_CONFIRM_PASS, RPM_CONFIRM_OLD, RPM_FAST_PASS,
              RPM_NOCHECKS_PASS, RPM_NOCHECKS_OLD, RPM_DRY_PASS, RPM_DRY_OLD,
              RPM_UNCHECKED_PASS, RPM_UNCHECKED_OLD, RPM_CLAIM_STOP, RPM_CLAIM_STOP_OLD,
              RPM_BG_READ, RPM_BG_CAT, RPM_BG_OLD, RPM_BG_FAILED, RPM_BG_NEVER, RPM_BG_NOTICE, RPM_BG_OTHER, RPM_BG_FAST,
              RPM_OTHER_PR], _build_readymark)


def rpm_mcp(name, expected, transcript, fake=GHREADY_CURRENT, carries=(), lacks=(), cwd=RPR_REPO, **tool_input):
    """One MCP update call judged in the folder `cwd` (the records-page repo by default), with the transcript the case names.
    A deny must name RPM_RULE."""
    add(name, expected, rule=RPM_RULE if expected == "deny" else None, tool="mcp__github__update_pull_request",
        cwd=cwd, env_path=_rpr_env(fake), config=MERGECFG, transcript=transcript, carries=carries, lacks=lacks, **tool_input)


# Refused: a ready mark with no ready pass in the transcript, and one whose only ready pass is on an older head. The refusal names the ready run.
rpm_mcp("ready-mcp-mark: MCP draft false with no ready pass in the transcript is refused", "deny", RPM_NO_PASS,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a ready pass on an older head is refused", "deny", RPM_OLD_PASS,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
# Allowed: the pass on the current head, and the two calls that mark nothing ready (the false-alarm controls).
rpm_mcp("ready-mcp-mark: MCP draft false after a ready pass on the current head is allowed", "allow", RPM_PASS,
        owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft true with no ready pass is allowed", "allow", RPM_NO_PASS,
        owner="y", repo="x", pullNumber=12, draft=True)
rpm_mcp("ready-mcp-mark: an MCP body-only update with no ready pass is allowed", "allow", RPM_NO_PASS,
        owner="y", repo="x", pullNumber=12, body="Updated the description only.")
# Allowed: the draft step's own Record-claim stop follows its pass on the claim head, so the pass stands for that head.
rpm_mcp("ready-mcp-mark: MCP draft false after a ready pass then the Record-claim stop on the claim head is allowed", "allow",
        RPM_CLAIM_PASS, fake=GHREADY_CLAIM, owner="y", repo="x", pullNumber=12, draft=False)
# F1. `merge <pr> --confirm` on a draft runs the same ready checks, then the records step, and prints the same pass line,
# so its pass on the current head stands. --fast-checks prints that line too, but it builds no records page, so it stands for no mark.
rpm_mcp("ready-mcp-mark: MCP draft false after a confirm pass on the current head is allowed", "allow", RPM_CONFIRM_PASS,
        owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a confirm pass on an older head is refused", "deny", RPM_CONFIRM_OLD,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after --fast-checks passed on the current head is refused", "deny", RPM_FAST_PASS,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
# F2. A repo with no merge.readyChecks prints no pass line. Its ready run prints the no-checks line and the records line instead,
# and that run stands for the head its records line names. The older-head control holds the head tie in this route too.
rpm_mcp("ready-mcp-mark: MCP draft false after a ready run in a repo with no ready checks, on the current head, is allowed", "allow",
        RPM_NOCHECKS_PASS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a ready run with no ready checks, on an older head, is refused", "deny",
        RPM_NOCHECKS_OLD, carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
# F3. A dev-base head that lacks the dev tip: the pass names the sha of its dry merge, not the head. The dry-merge line ties that sha to
# the head. The control's deny names this rule, which shows records-page-ready passes this fixture (the dev base skips the page).
rpm_mcp("ready-mcp-mark: MCP draft false after a dry-merge pass for this head is allowed", "allow", RPM_DRY_PASS,
        fake=GHREADY_DEV_BEHIND, cwd=RPR_DEV_BEHIND_CLONE, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a dry-merge pass for an older head is refused", "deny", RPM_DRY_OLD,
        fake=GHREADY_DEV_BEHIND, cwd=RPR_DEV_BEHIND_CLONE, carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS,
        owner="y", repo="x", pullNumber=12, draft=False)
# I1. A ready run on a base that is not the default, in a repo with no ready checks, has no worktree, so the unchecked line is the
# only line that names its head. The run stands for the head that line names. Green on the built guard: it pins that line.
rpm_mcp("ready-mcp-mark: MCP draft false after an unchecked ready run on a base that is not the default is allowed", "allow",
        RPM_UNCHECKED_PASS, fake=GHREADY_DEV_BEHIND, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after an unchecked ready run on an older head is refused", "deny", RPM_UNCHECKED_OLD,
        fake=GHREADY_DEV_BEHIND, carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
# I3. A ready run that stops on a Record-claim head, in a repo with no ready checks, names that head in its stop line. The stop's remedy
# marks the head ready by hand, so the mark after it stands for that head. Red on the built guard: it reads no line of the stop.
rpm_mcp("ready-mcp-mark: MCP draft false after a Record-claim stop with no ready checks, on the claim head, is allowed", "allow",
        RPM_CLAIM_STOP, fake=GHREADY_CLAIM, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a Record-claim stop with no ready checks, naming an older head, is refused", "deny",
        RPM_CLAIM_STOP_OLD, fake=GHREADY_CLAIM, carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
# B1. A background ready run's pass reaches the guard only through the session's own read of its output file, here a Read of the path
# or a Bash cat of it. Each shows the pass for the run's head. Red on main: main reads a Bash result only when that call is itself a ready run.
rpm_mcp("ready-mcp-mark: MCP draft false after a background ready pass read by Read is allowed", "allow", RPM_BG_READ,
        owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a background ready pass read by a Bash cat is allowed", "allow", RPM_BG_CAT,
        owner="y", repo="x", pullNumber=12, draft=False)
# B2. Controls, green on main: each is refused now and must stay refused. Each pins one way a background run could pass for a
# ready pass by mistake. The never-read case's output file holds the pass on disk, so a guard that opened the file would allow it.
rpm_mcp("ready-mcp-mark: MCP draft false after a background ready pass read on an older head is refused", "deny", RPM_BG_OLD,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a background ready run whose output was never read is refused", "deny", RPM_BG_NEVER,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a background ready run whose read output is a failed check is refused", "deny", RPM_BG_FAILED,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a read of a background job that is no ready run is refused", "deny", RPM_BG_OTHER,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a read of a background --fast-checks run is refused", "deny", RPM_BG_FAST,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
rpm_mcp("ready-mcp-mark: MCP draft false after a background ready run completed, with no read of its output, is refused", "deny", RPM_BG_NOTICE,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
# X1. The pass line names a sha and no pull request, and main matches a pass by the head sha alone (note ready-mark-pass-matched-by-sha).
# The decision names `merge <pr> --ready` on that pull request's current head, so a pass from `merge 13 --ready` is no pass for #12. Red on main.
rpm_mcp("ready-mcp-mark: MCP draft false after a ready pass from another pull request's run, on this head, is refused", "deny", RPM_OTHER_PR,
        carries=RPM_REMEDY, lacks=RPM_TARGET_LACKS, owner="y", repo="x", pullNumber=12, draft=False)
