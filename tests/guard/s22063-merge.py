# section 22063
FAMILY = "merge"


def gh_root_flag_verb_check(segment, verb):
    """True when gh_call_of's first two words are the verb, so a repo flag in front of the verb, or after the
    group word, is read past."""
    guard = _load_guard_module()
    rest = guard.gh_call_of(segment)
    if rest is None:
        return False, "gh_call_of reads no gh call in %r" % segment
    if rest[:2] != verb:
        return False, "gh_call_of(%r) gives %r, so its first two words are not %r" % (segment, rest, verb)
    return True, "gh_call_of(%r) reads %r past the repo flag" % (segment, verb)


def gh_root_dash_r_check():
    return gh_root_flag_verb_check("gh -R o/r pr merge 12", ["pr", "merge"])


def gh_root_repo_equals_check():
    return gh_root_flag_verb_check("gh --repo=o/r pr merge 12", ["pr", "merge"])


def gh_root_repo_spaced_check():
    return gh_root_flag_verb_check("gh --repo o/r pr create --fill", ["pr", "create"])


# The same flag after the group word (`gh pr -R o/r merge`): gh reads it there too. Each form has a check. A repo
# value that reads as a verb is the value, never the verb.
def gh_group_dash_r_check():
    return gh_root_flag_verb_check("gh pr -R o/r merge 12", ["pr", "merge"])


def gh_group_repo_equals_check():
    return gh_root_flag_verb_check("gh pr --repo=o/r merge 12", ["pr", "merge"])


def gh_group_repo_spaced_check():
    return gh_root_flag_verb_check("gh issue --repo o/r comment 3 --body x", ["issue", "comment"])


def gh_group_joined_dash_r_check():
    return gh_root_flag_verb_check("gh pr -Ro/r merge 12", ["pr", "merge"])


def gh_group_value_verb_check():
    return gh_root_flag_verb_check("gh pr -R list comment 5", ["pr", "comment"])


FIXTURELESS_CHECKS.update((gh_root_dash_r_check, gh_root_repo_equals_check, gh_root_repo_spaced_check,
                           gh_group_dash_r_check, gh_group_repo_equals_check, gh_group_repo_spaced_check,
                           gh_group_joined_dash_r_check, gh_group_value_verb_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a -R root flag", gh_root_dash_r_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a --repo=<repo> root flag",
                         gh_root_repo_equals_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a spaced --repo <repo> root flag",
                         gh_root_repo_spaced_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a -R flag after the group word",
                         gh_group_dash_r_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a --repo=<repo> flag after the group word",
                         gh_group_repo_equals_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the issue verb past a spaced --repo <repo> flag after the group word",
                         gh_group_repo_spaced_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a joined -R<repo> flag after the group word",
                         gh_group_joined_dash_r_check))
LOG_CHECKS_EXTRA.append(("merge: gh_call_of reads the pr verb past a repo value that looks like a verb, "
                         "after the group word", gh_group_value_verb_check))


# ---- merge: merge_call_of reads the repo value, not only the verb. A repo flag joined to its value (-Ro/r) gave
# repo '', which is the working directory's repo, so the merge check read the wrong repo. The spaced and equals forms
# are controls: they read the repo already. Each check asserts the selector (scope) before the repo (subject).
def merge_call_repo_check(segment, want_repo):
    """True when merge_call_of reads the pull request '12' and the repo `want_repo` from a `gh pr merge` segment."""
    guard = _load_guard_module()
    got = guard.merge_call_of(segment)
    if got is None:
        return False, "merge_call_of reads no gh pr merge in %r" % segment
    selector, repo = got
    if selector != "12":
        return False, "merge_call_of(%r) gives selector %r, not '12'" % (segment, selector)
    if repo != want_repo:
        return False, "merge_call_of(%r) gives repo %r, not %r" % (segment, repo, want_repo)
    return True, "merge_call_of(%r) reads repo %r" % (segment, want_repo)


def merge_repo_joined_before_verb_check():
    return merge_call_repo_check("gh -Ro/r pr merge 12", "o/r")


def merge_repo_joined_after_group_check():
    return merge_call_repo_check("gh pr -Ro/r merge 12", "o/r")


def merge_repo_joined_after_verb_check():
    return merge_call_repo_check("gh pr merge 12 -Ro/r", "o/r")


def merge_repo_spaced_dash_r_check():
    return merge_call_repo_check("gh pr merge 12 -R o/r", "o/r")


def merge_repo_spaced_repo_check():
    return merge_call_repo_check("gh pr merge 12 --repo o/r", "o/r")


def merge_repo_equals_check():
    return merge_call_repo_check("gh pr merge 12 --repo=o/r", "o/r")


FIXTURELESS_CHECKS.update((merge_repo_joined_before_verb_check, merge_repo_joined_after_group_check,
                           merge_repo_joined_after_verb_check, merge_repo_spaced_dash_r_check,
                           merge_repo_spaced_repo_check, merge_repo_equals_check))
LOG_CHECKS_EXTRA.append(("merge: merge_call_of reads the repo from a joined -R<repo> flag before the verb",
                         merge_repo_joined_before_verb_check))
LOG_CHECKS_EXTRA.append(("merge: merge_call_of reads the repo from a joined -R<repo> flag after the group word",
                         merge_repo_joined_after_group_check))
LOG_CHECKS_EXTRA.append(("merge: merge_call_of reads the repo from a joined -R<repo> flag after the verb",
                         merge_repo_joined_after_verb_check))
LOG_CHECKS_EXTRA.append(("merge: merge_call_of reads the repo from a spaced -R <repo> flag after the verb",
                         merge_repo_spaced_dash_r_check))
LOG_CHECKS_EXTRA.append(("merge: merge_call_of reads the repo from a spaced --repo <repo> flag after the verb",
                         merge_repo_spaced_repo_check))
LOG_CHECKS_EXTRA.append(("merge: merge_call_of reads the repo from a --repo=<repo> flag after the verb",
                         merge_repo_equals_check))

# ---- draft-pr: an unclosed quote in a PowerShell here-string command leaves no guard-crash line. Each run's log holds
# none; the verdicts are the sh() cases in the draft-pr section.
def draft_here_string_no_crash_case():
    """No run of the unclosed-quote here-string commands logs a guard-crash line."""
    for name, command in (("the iex-run body", DRAFT_CRASH_CMD), ("the control with a later delete", UNCLOSED_THEN_DELETE),
                          ("the unclosed quote in a pipe stage", UNCLOSED_PIPE_CMD)):
        folder = os.path.join(ROOT, "draft-here-crash")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "guard.log")
        if os.path.exists(path):
            os.remove(path)
        decide({"raw": None, "tool": "PowerShell", "cwd": NOGIT, "session": None, "env_path": None,
                "config": folder, "tool_input": {"command": command}})
        rows = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                rows = handle.read().splitlines()
        for row in rows:
            fields = row.split("\t")
            if fields[2:4] == ["crash", "guard-crash"]:
                return False, "%s crashed the guard: %s" % (name, fields[4][:100])
    return True, "no guard-crash line for the iex-run body, the control or the pipe stage"


LOG_CHECKS_EXTRA.append(("draft-pr: an unclosed quote ahead of a PowerShell here-string logs no guard-crash line",
                         draft_here_string_no_crash_case))

# ---- lane-closes-after-records: the two checks that are log checks, not cases. The override is a story over
# several calls on one clock (see the owner-override family), and the matcher reads settings.json, as the
# impeccable check does. Both register here, where LOG_CHECKS_EXTRA exists, under this family.
