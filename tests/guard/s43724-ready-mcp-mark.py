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


def _rpm_pass(sha):
    """The stdout line of run_ready_checks on a pass, as the Bash result carries it."""
    return "merge: the ready checks (check invariants) pass on %s." % sha[:9]


def _rpm_ready_run(tool_id, *results):
    """One paired Bash call, `merge 12 --ready`, whose result lines are `results`."""
    return [role_use(tool_id, "Bash", {"command": MERGE_SHIM + " 12 --ready"}), role_result(tool_id, "\n".join(results))]


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
    lines = {
        RPM_NO_PASS: _rpm_ready_run("ready-none", "merge: #12 stays a draft. Mark it ready after its draft run shows."),
        RPM_OLD_PASS: _rpm_ready_run("ready-old", _rpm_pass(older), "merge: #12 stays a draft. Mark it ready after its draft run shows."),
        RPM_PASS: _rpm_ready_run("ready-now", _rpm_pass(current), "merge: #12 stays a draft. Mark it ready after its draft run shows."),
        RPM_CLAIM_PASS: _rpm_ready_run(
            "ready-claim", _rpm_pass(claim),
            "merge: %s on feat-claim holds a Record-claim (D-002), so the draft step adds no page commit on top of it. "
            "Mark #12 ready by hand, then run --confirm again. Nothing was pushed." % claim[:9]),
    }
    for path, rows in lines.items():
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(rows) + "\n")


lazy_fixture([RPM_NO_PASS, RPM_OLD_PASS, RPM_PASS, RPM_CLAIM_PASS], _build_readymark)


def rpm_mcp(name, expected, transcript, fake=GHREADY_CURRENT, carries=(), lacks=(), **tool_input):
    """One MCP update call judged in the records-page repo, with the transcript the case names. A deny must name RPM_RULE."""
    add(name, expected, rule=RPM_RULE if expected == "deny" else None, tool="mcp__github__update_pull_request",
        cwd=RPR_REPO, env_path=_rpr_env(fake), config=MERGECFG, transcript=transcript, carries=carries, lacks=lacks, **tool_input)


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
