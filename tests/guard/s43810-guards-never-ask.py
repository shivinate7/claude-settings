# section 43810
# Decision `guard-remedy-not-to-owner`: what is read-only or harmless is allowed; what
# overwrites and is harmful is denied, with a refusal that says what the correct act is and that a refusal
# which looks wrong is to be complied with and reported. A rule that used to ask now denies, so each of its
# denials must carry that message. Each check here refuses one call, reads its printed reason, and files
# under the family of the rule the call names. The forbidden fragments and the generic hygiene check are
# the same as every other deny (names_the_target, FORBIDDEN_IN_A_REASON).

# The owner's line a refusal ends with. Its one home is guard_core.COMPLY_TAIL, imported here and never copied.
from guard_core import COMPLY_TAIL as NA_TAIL


def na_payload(command, cwd, **extra):
    """One Bash call of one command, as decide() reads it, in the given run folder."""
    case = {"raw": None, "tool": "Bash", "tool_input": {"command": command}, "cwd": cwd,
            "session": None, "env_path": None}
    case.update(extra)
    return case


def na_reason_check(case, rule, why_any, act_any, refused):
    """(ok, note): the call is denied by `rule`. Its reason ends with the owner's line, says why (one of
    `why_any`), names the correct act (one of `act_any`), names none of the refused forms, and carries
    no forbidden fragment."""
    got, reason = decide(case)
    if got != "deny":
        return False, "verdict %s, want deny: %s" % (got, reason[:110])
    problems = []
    if rule not in reason:
        problems.append("the reason does not name rule %s" % rule)
    if not reason.endswith(NA_TAIL):
        problems.append("the reason does not end with the owner's line")
    if not any(option in reason for option in why_any):
        problems.append("the reason does not say why (want one of %s)" % (why_any,))
    if not any(option in reason for option in act_any):
        problems.append("the reason does not name the correct act (want one of %s)" % (act_any,))
    named = [form for form in refused if form in reason]
    if named:
        problems.append("the reason names the refused form %r" % named[0])
    leak = names_the_target(reason, rule)
    if leak:
        problems.append("the reason carries the forbidden fragment %r" % leak)
    if problems:
        return False, "; ".join(problems)
    return True, "denied by %s, with its why, the correct act and the owner's line" % rule


def na_register(label, family, case, rule, why_any, act_any, refused):
    # LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so this check joins LOG_CHECKS directly (as
    # section 42840 does), and its family is set here.
    global LOG_CHECKS
    LOG_CHECKS = LOG_CHECKS + ((label, lambda: na_reason_check(case, rule, why_any, act_any, refused)),)
    LOG_FAMILY[label] = family


# The correct act a discard refusal names: commit the work on a branch of one's own. Named forms: the
# discards the refusal stops. A reason may say why in any of these words.
NA_DISCARD_WHY = ("lose", "uncommitted", "throw", "discard")
NA_DISCARD_ACT = ("commit", "Commit")
NA_DISCARD_REFUSED = ("reset --hard", "reset --keep", "reset --merge", "checkout -- .", "restore .")
na_register("never ask: a discard in a linked worktree is denied, and names the correct act",
            "shared-tree", na_payload(VCS + " reset --hard", GITWT), "shared-tree",
            NA_DISCARD_WHY, NA_DISCARD_ACT, NA_DISCARD_REFUSED)
na_register("never ask: a discard in the shared checkout is denied, and names the correct act",
            "shared-tree", na_payload(VCS + " reset --hard", GITMAIN), "shared-tree",
            NA_DISCARD_WHY, NA_DISCARD_ACT, NA_DISCARD_REFUSED)

# A forced push that may reach the default branch is denied. The remedy is a push of one's own branch and
# a pull request, never a lease retry: a retry would force main again.
NA_FORCE_WHY = ("rewrite", "overwrite", "history", "default branch")
NA_FORCE_ACT = ("own branch", "lane branch", "pull request")
NA_FORCE_REFUSED = ("retry with --force", "push --force", "push -f", "--force-if-includes")
na_register("never ask: a forced push to main is denied, and names no lease retry",
            "push-delete", na_payload(VCS + " push --force origin HEAD:main", PUSHFEAT), "force-push",
            NA_FORCE_WHY, NA_FORCE_ACT, NA_FORCE_REFUSED)

# A plain push of main is denied. Its remedy names the lane's own branch; it is not a prompt to approve.
NA_MAIN_WHY = ("default branch", "reviewed", "pull request", "merge tool")
NA_MAIN_ACT = ("own branch", "lane branch", "pull request", "HEAD:<")
NA_MAIN_REFUSED = ("prompt", "Approving", "push origin main", "HEAD:main")
na_register("never ask: a push of main is denied, and names the lane's own branch",
            "push-delete", na_payload(VCS + " push origin main", PUSHFEAT), "push-main",
            NA_MAIN_WHY, NA_MAIN_ACT, NA_MAIN_REFUSED)

# A bare merge in a repo that uses the merge tool is denied. The remedy is the merge tool itself.
NA_MERGE_WHY = ("claim", "skips", "leaves")
NA_MERGE_ACT = ("merge tool",)
NA_MERGE_REFUSED = ("confirm this call", "asks the owner", "gh pr merge")
na_register("never ask: a bare merge in a merge-tool repo is denied, and names the merge tool",
            "merge", na_payload("gh pr merge 12 --squash", STAMPREPO, env_path=GREEN_ON, config=MERGECFG),
            "bare-merge", NA_MERGE_WHY, NA_MERGE_ACT, NA_MERGE_REFUSED)


# A command that would have asked, chained with two commands no harmless lead or tail names (`make test`,
# `make lint`). The guard must deny the chain, and the deny must not be the run-alone ask, which says the command
# needs the owner's answer. The deny ends with the owner's line.
NA_CHAIN_TAIL = " && make test && make lint"
NA_OWNER_ANSWER = "owner's answer"


def na_chained_check(case):
    """(ok, note): the chained call is denied, its reason does not say the command needs the owner's answer, and
    it ends with the owner's line. It carries no forbidden fragment."""
    got, reason = decide(case)
    if got != "deny":
        return False, "verdict %s, want deny: %s" % (got, reason[:110])
    if NA_OWNER_ANSWER in reason:
        return False, "the reason says the command needs the owner's answer (the run-alone ask)"
    if not reason.endswith(NA_TAIL):
        return False, "the reason does not end with the owner's line"
    leak = names_the_target(reason)
    if leak:
        return False, "the reason carries the forbidden fragment %r" % leak
    return True, "denied, with no owner's-answer ask, and the owner's line last"


def na_chained_register(label, family, case):
    global LOG_CHECKS
    LOG_CHECKS = LOG_CHECKS + ((label, lambda: na_chained_check(case)),)
    LOG_FAMILY[label] = family


na_chained_register("never ask: a forced push to main, chained with two commands, is denied, not run-alone asked",
                    "push-delete", na_payload(VCS + " push --force origin HEAD:main" + NA_CHAIN_TAIL, PUSHFEAT))
na_chained_register("never ask: a push of main, chained with two commands, is denied, not run-alone asked",
                    "push-delete", na_payload(VCS + " push origin main" + NA_CHAIN_TAIL, PUSHFEAT))
na_chained_register("never ask: a bare merge in a merge-tool repo, chained with two commands, is denied, "
                    "not run-alone asked",
                    "merge", na_payload("gh pr merge 12 --squash" + NA_CHAIN_TAIL, STAMPREPO, env_path=GREEN_ON,
                                        config=MERGECFG))


# A push of main in a repo that does not use the merge tool: a plain checkout with an origin and no
# .github/stamp.json, so there is no pull request flow. Its remedy names a branch to push the commit to, and never
# a pull request or the merge tool.
NOMERGEPUSH = os.path.join(ROOT, "nomergepush")   # a plain checkout, origin set, no merge tool
make_repo(NOMERGEPUSH, {"README.md": "plain\n"})
run_vcs(NOMERGEPUSH, "remote", "add", "origin", PUSHREMOTE)
NA_BRANCH = "branch"
NA_PULL_REQUEST = "pull request"
NA_MERGE_TOOL = "merge tool"


def na_plain_check(case):
    """(ok, note): the push of main is denied in a repo with no merge tool. Its reason names a branch, names no pull
    request and no merge tool, ends with the owner's line, and carries no forbidden fragment."""
    got, reason = decide(case)
    if got != "deny":
        return False, "verdict %s, want deny: %s" % (got, reason[:110])
    if NA_BRANCH not in reason:
        return False, "the reason does not name a branch to push the commit to"
    if NA_PULL_REQUEST in reason:
        return False, "the reason names a pull request, and this repo has no pull request flow"
    if NA_MERGE_TOOL in reason:
        return False, "the reason names the merge tool, and this repo does not use it"
    if not reason.endswith(NA_TAIL):
        return False, "the reason does not end with the owner's line"
    leak = names_the_target(reason)
    if leak:
        return False, "the reason carries the forbidden fragment %r" % leak
    return True, "denied, with a branch to name in the report, and the owner's line last"


def na_plain_register(label, family, case):
    global LOG_CHECKS
    LOG_CHECKS = LOG_CHECKS + ((label, lambda: na_plain_check(case)),)
    LOG_FAMILY[label] = family


na_plain_register("never ask: a push of main in a repo with no merge tool is denied, "
                  "and names a branch, not a pull request",
                  "push-delete", na_payload(VCS + " push origin main", NOMERGEPUSH))
