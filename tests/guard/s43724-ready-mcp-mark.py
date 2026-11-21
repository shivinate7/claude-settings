# section 43724
FAMILY = "ready-mcp-mark-guard"
#
# `ready-mcp-mark-guard`. A ready mark by the GitHub MCP update tool (draft false) is allowed only when the merge tool's
# ready checks passed on the pull request's current head. `merge <pr> --ready` writes no durable record of that pass:
# run_ready_checks (merge/merge.py) prints one stdout line, `merge: the ready checks (...) pass on <sha9>.`, and the line
# reaches the guard only through the session transcript, as the result of the Bash call. So the rule reads the session's
# own transcript for a `merge <pr> --ready` call whose result passes on the head the pull request now has.
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
    _rpr_need(_rpr_git(RPR_DEV_BEHIND_CLONE, "rev-parse", dry + "^1") == dev_behind
              and _rpr_git(RPR_DEV_BEHIND_CLONE, "rev-parse", dry + "^2") == dev_tip,
              "the dry merge does not hold the head as its first parent and the dev tip as its second")
    lines = {
        RPM_NO_PASS: _rpm_ready_run("ready-none", "merge: #12 stays a draft. Mark it ready after its draft run shows."),
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
    }
    for path, rows in lines.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")


lazy_fixture([RPM_NO_PASS, RPM_OLD_PASS, RPM_PASS, RPM_CLAIM_PASS, RPM_CONFIRM_PASS, RPM_CONFIRM_OLD, RPM_FAST_PASS,
              RPM_NOCHECKS_PASS, RPM_NOCHECKS_OLD, RPM_DRY_PASS, RPM_DRY_OLD], _build_readymark)


def rpm_mcp(name, expected, transcript, fake=GHREADY_CURRENT, carries=(), lacks=(), cwd=RPR_REPO, **tool_input):
    """One MCP update call judged in the folder `cwd` (the records-page repo by default), with the transcript the case names.
    A deny must name RPM_RULE."""
    add(name, expected, rule=RPM_RULE if expected == "deny" else None, tool="mcp__github__update_pull_request",
        cwd=cwd, env_path=_rpr_env(fake), config=MERGECFG, transcript=transcript, carries=carries, lacks=lacks, **tool_input)


# Refused: a ready mark with no ready pass on the head, and a ready pass on an older head. The refusal names the ready run.
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
