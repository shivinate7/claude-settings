"""The guard's merge family: a merge made outside the merge tool, and the git and gh call readers.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import contextlib
import fnmatch
import io
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

from guard_core import (
    SHELL_TOOLS, WRITE_TOOLS, _absolute, ASSIGNMENT, _git, _git_subcommand_index, _segment_git_c_target, basename, cap_safe, command_root, GIT_WORK_TREE_RE,
    dir_before_segment, inline_script, inner_commands, resolve_command, resolve_default_base, segment_tokens, split_segments,
    is_cloud, strip_heredoc_bodies, strip_redirections,
)
import own_session  # the one home of the own get_session read, small so report_guard imports it too
from shared_names import BUILD_TAG, DATA_TOOL, LANE_GRANT_MARKER, LANE_TAG, MERGE_ROLES, TOPIC_TAG, grant_line_holds_words, is_lane_create_session, lane_head_refs, lane_tags  # the one home of the lane tags and head refs, shared with the roadmap build
from guard_pointer import (
    pointer_checkout,
)
from guard_push_delete import (
    DEFAULT_BRANCH_FALLBACK, push_calls, push_destinations, push_refspecs, push_target,
)


# ------------------------------------------------------------------ three git acts
#
# Each clause below judges the ACT a segment performs, read off its command word (decisions/
# predicate-is-the-act.md), never a substring of the text. `echo git commit`, a `git log`, a
# quoted message and a heredoc body name an act and perform none.
#
# 1. merge-checks: a merge made outside the merge tool is
#    refused while the head has a check or a workflow run pending or red, while another ready PR
#    on the same base runs CI (decision no-merge-during-batch-ci), or when that read could not run. The merge tool (merge/merge.py) runs its own `gh pr merge` as a subprocess, so no hook
#    sees it; it has already waited. The read below is the tool's own `Host.head_read`, one home.
# 2. cite-by-id (CLAUDE.md `git-cite-by-id`): a commit message or PR body that cites a record by
#    its path is refused. The id is the record's file name without folder or `.md`, the slug
#    lint/check_record_slugs.py measures, or the number the stamp claims at merge.

def git_call_of(segment: str):
    """Return (subcommand, args) when the segment's COMMAND WORD is git, else None.

    Args come from shlex, so a quoted message stays one token. A segment shlex cannot parse
    judges nothing: the same fail-open stance as `segment_tokens`.
    """
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return None
    cursor = _git_subcommand_index(tokens, index)
    if cursor >= len(tokens):
        return None
    return tokens[cursor].lower(), tokens[cursor + 1:]


def _gh_root_repo_flag(tokens, index):
    """Return how many tokens the gh root repo flag at `index` takes (0 when it is none):
    `-R o/r` and `--repo o/r` take two, `--repo=o/r` and `-Ro/r` take one."""
    token = tokens[index]
    if token in ("-R", "--repo"):
        return 2
    if token.startswith("--repo=") or (token.startswith("-R") and not token.startswith("--")):
        return 1
    return 0


def gh_call_of(segment: str):
    """Return the tokens after `gh` when the segment's COMMAND WORD is gh, else None.

    A repo flag before the verb (`gh -R o/r pr merge`) is valid gh and hid the verb from every
    caller, which read the first two words. The same flag right after the group word
    (`gh pr -R o/r comment`) hid the subcommand the same way. The flag moves to the end: gh
    reads `-R` after the verb the same, and the callers that look for the repo (merge_call_of,
    ci_wake) already read it there.
    """
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    if tokens[0].startswith("("):   # a subshell, as detached_launch_hit reads it
        tokens = [tokens[0].lstrip("(")] + tokens[1:]
        tokens[-1] = tokens[-1].rstrip(")")
        tokens = [t for t in tokens if t]
        if not tokens:
            return None
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("gh", "gh.exe"):
        return None
    rest, root, group = tokens[index + 1:], [], []
    for _ in (0, 1):   # before the group word, then right after it
        while rest and _gh_root_repo_flag(rest, 0):
            taken = _gh_root_repo_flag(rest, 0)
            root += rest[:taken]
            rest = rest[taken:]
        if group or not rest:
            break
        group, rest = rest[:1], rest[1:]
    return group + rest + root


# ---- a merge made outside the merge tool
MERGE_TOOLS = ("mcp__github__merge_pull_request",)
MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                     "--match-head-commit", "-A", "--author-email"}
# Seconds for the WHOLE read, shared: Host.head_read makes 4 `gh` REST calls (5 with a branch selector, 1 more run-list read when the check runs link more than one run; a settled head adds the
# batch read: the open pull list, then, when another ready PR is on the base, the protection (none with a pinned list) and
# 3 calls per such PR: its check runs, its commit statuses and its workflow run list) that split this one
# deadline (merge.py's shared_deadline), each getting whatever of it the earlier calls left. The shared deadline bounds a
# hung `gh` to this one budget (pinned in test_guard.py), so a merge with a dead `gh` is refused fast instead of waiting out
# each call. From a Linux cloud session, REST calls take 0.3-0.7 s. Windows REST is unmeasured, so the
# budget covers 5 calls at the 3.5 s a GraphQL call took there under load (17.5 s). The guard hook's own timeout is 60 s.
MERGE_READ_TIMEOUT = 25
MERGE_TOOL_REL = os.path.join("merge", "merge.py")


def merge_call_of(segment: str):
    """Return (selector, repo) for a `gh pr merge` segment, else None.

    `selector` is the first positional word, '' for the current branch's pull request. `--auto` is
    judged like any merge: GitHub's auto-merge waits only on REQUIRED checks, and a base with none
    merges at once.
    """
    rest = gh_call_of(segment)
    if rest is None or rest[:2] != ["pr", "merge"]:
        return None
    selector, repo = "", ""
    args = rest[2:]
    if "-h" in args or "--help" in args:
        return None   # help merges nothing
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        taken = _gh_root_repo_flag(args, index - 1)
        if taken == 2:
            repo = args[index] if index < len(args) else ""
            index += 1
        elif taken:   # `--repo=o/r`, `-Ro/r`; pflag drops the '=' of a shorthand (`-R=o/r`)
            repo = arg[len("--repo="):] if arg.startswith("--repo=") else arg[2:].removeprefix("=")
        elif arg in MERGE_VALUE_FLAGS:
            index += 1
        elif arg.startswith("-"):
            continue
        elif not selector:
            selector = arg
    return selector, repo


_MERGE_MODULE = []


def settings_roots():
    """The clones of claude-settings this guard may read a sibling file from: the one beside its
    own real path (the hooks are symlinks into the clone), then the one the global rules file
    points at."""
    roots = [os.path.dirname(os.path.dirname(os.path.realpath(__file__)))]
    pointer = pointer_checkout()
    if pointer:
        roots.append(pointer)
    return roots


def merge_module():
    """Load merge/merge.py, the merge tool, or return None. Looked up beside this file's real
    path first (the hooks are symlinks into the clone), then in the clone the global rules
    file points at. An unloadable tool is an unknown read, never a pass."""
    if _MERGE_MODULE:
        return _MERGE_MODULE[0]
    for root in settings_roots():
        path = os.path.join(root, MERGE_TOOL_REL)
        if not os.path.isfile(path):
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("merge_tool", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.SH_TIMEOUT = MERGE_READ_TIMEOUT
            _MERGE_MODULE.append(module)
            return module
        except (Exception, SystemExit):  # a tool that exits at import is unloadable too, never a pass
            continue
    return None


def has_workflows(where: str) -> bool:
    """True when the checkout at `where` holds a workflow file, or when that cannot be told: a
    head with nothing reported is then unsettled, never green."""
    try:
        folder = os.path.join(where, ".github", "workflows")
        return any(name.endswith((".yml", ".yaml")) for name in os.listdir(folder))
    except FileNotFoundError:
        return False
    except Exception:
        return True


def merge_check(selector, repo: str, where: str):
    """Return (verdict, detail) for the head of the named pull request: green, pending, red,
    batch (another ready PR on the base has a workflow run or a required check pending), or unknown. One read, no
    wait, run in `where` so `gh` names the repo the command names."""
    module = merge_module()
    if module is None:
        return "unknown", "the merge tool's check reader could not be loaded"
    where = os.path.normpath(where) if where else ""   # a `cd` target may carry either separator
    try:  # the tool's own parser; a bad entry is refused there, so it is unknown here
        ignore = next((module.ignore_checks(c) for c in _merge_configs(where) if isinstance(c["merge"], dict)), {}) if where else {}
    except Exception as e:
        return "unknown", str(e)
    host = module.Host(required=pinned_required(where) or "protection", repo=repo or None, cwd=where or None)
    # The ignore list reaches only the batch read: this head counts every check, so an ignored red check on it still refuses.
    return host.head_read(selector, nothing_is_green=not has_workflows(where), batch_ignore=ignore)


MERGE_CHECK_REASON = (
    "Rule (Git): this head is not settled: %s. A merge waits for every check and workflow run on "
    "the head, required or not, and a read that could not run counts as not settled. "
    "Remedy: run the merge tool, `merge <pr> --confirm`, which waits on the required checks, then "
    "merges the head it waited on."
)


# The merge tool refuses this case too, so the remedy is to wait, never to run another merge.
MERGE_BATCH_REASON = (
    "Rule (Git, git-no-merge-during-batch-ci): another ready PR's CI runs on this base, and its head "
    "does not contain this head: %s. A merge now moves the base that run tests. Remedy: wait for that run to end. Its run's end, or its "
    "CI-done comment on a red run, wakes the session that watches that PR. Then merge."
)


def merge_check_reason(verdict: str, detail: str) -> str:
    if verdict == "batch":
        return MERGE_BATCH_REASON % cap_safe(detail, 160)
    return MERGE_CHECK_REASON % (verdict + (" (" + cap_safe(detail, 160) + ")" if detail else ""))


def _merge_config_at(root: str):
    """The `.github/stamp.json` object in the nearest folder at or above `root` that holds `.git`,
    when it is a JSON object with a `merge` key. Any other outcome is None."""
    while not os.path.exists(os.path.join(root, ".git")):
        if os.path.dirname(root) == root:
            return None
        root = os.path.dirname(root)
    try:
        with open(os.path.join(root, ".github", "stamp.json"), encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError):
        return None
    return config if isinstance(config, dict) and "merge" in config else None


def _merge_configs(where: str):
    """The merge configs of the repo the cwd sits in. The path is walked as written AND with symlinks
    resolved: a cwd that is a symlink into a repo finds its `.git` only on the real path, and a
    symlink out of one only on the written path."""
    configs = (_merge_config_at(root) for root in dict.fromkeys((os.path.abspath(where), os.path.realpath(where))))
    return [c for c in configs if c is not None]


def uses_merge_tool(where: str) -> bool:
    """True when the repo the cwd sits in uses the merge tool (see `_merge_configs`). No root, or a
    missing, unreadable, invalid or non-object file, is False: nothing to ask."""
    return bool(_merge_configs(where))


def pinned_required(where: str):
    """The repo's pinned `merge.requiredChecks` list, when it is a non-empty list of names; else None,
    and the batch read takes the names from the branch protection."""
    for config in _merge_configs(where) if where else ():
        merge = config["merge"]
        names = merge.get("requiredChecks") if isinstance(merge, dict) else None
        if isinstance(names, list) and names and all(isinstance(k, str) and k for k in names):
            return names
    return None


BARE_MERGE_REASON = (
    "Rule (Git): this repo merges with the merge tool, and a bare `gh pr merge` skips its claim and "
    "leaves the local main behind origin. "
    "Remedy: run the merge tool, `merge <pr> --confirm`. If the tool is broken, confirm this call. "
    "(decision bare-merge-asks, a bare merge in a merge-tool repo asks the owner)"
)


DRAFT_PR_REASON = ("draft-pr: open every PR as a draft. Add --draft (or -d) to gh pr create. "
                   "Only the batch's integration PR goes ready; CI skips drafts.")


# `gh pr create` flags that take a value; the next token is data, never a flag.
PR_CREATE_VALUE_FLAGS = {"-t", "--title", "-b", "--body", "-F", "--body-file", "-B", "--base",
                         "-H", "--head", "-l", "--label", "-a", "--assignee", "-m", "--milestone",
                         "-p", "--project", "-r", "--reviewer", "-R", "--repo", "-T", "--template"}
GH_TRUE = ("1", "t", "T", "TRUE", "true", "True")
# Named limits (decision draft-until-reviewed): a `gh api` POST to the pulls endpoint and
# `hub pull-request` open a PR and are not judged here. A short-flag cluster such as `-dt x` is
# not read as a draft flag, so it is refused (a rare false alarm).


def undrafted_pr_create(segment: str) -> bool:
    """True for a `gh pr create` segment (or a `sh -c` script holding one) that ends not draft.
    The last --draft, -d or --draft=X wins."""
    tokens = segment_tokens(segment) or []
    script = inline_script(tokens) if tokens else ""
    if script:
        return any(undrafted_pr_create(part) for part in split_segments(script) if part.strip())
    rest = gh_call_of(segment)
    if rest is None or rest[:2] != ["pr", "create"]:
        return False
    args = rest[2:]
    draft, index = False, 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg in PR_CREATE_VALUE_FLAGS:
            index += 1
        elif arg in ("-h", "--help"):
            return False   # help creates nothing
        elif arg in ("-d", "--draft"):
            draft = True
        elif arg.startswith(("--draft=", "-d=")):
            draft = arg.split("=", 1)[1] in GH_TRUE   # gh's ParseBool set; any other value is false
    return not draft


# ---- a gh write in a cloud session (rule gh-write-cloud)
#
# The GitHub MCP tools and the merge tool write there; a `gh` write is refused. Judged per segment from the
# command word, so quoted text and heredoc bodies never fire. The caller applies it only when is_cloud().
GH_WRITE_CLOUD_REASON = (
    "Rule (GitHub): in a cloud session a pull request write, an issue write and an API write made with gh are "
    "refused. A GitHub write goes through the GitHub MCP tools, and the merge tool merges. "
    "Remedy: open a draft PR with mcp__github__create_pull_request, comment with mcp__github__add_issue_comment, "
    "edit or close with mcp__github__update_pull_request or mcp__github__issue_write, review with "
    "mcp__github__pull_request_review_write, and merge with `merge <pr> --confirm`. "
    "(rule gh-write-cloud, a GitHub write in a cloud session goes through the MCP tools)"
)
GH_WRITE_VERBS = {"pr": ("create", "merge", "comment", "edit", "close", "review", "ready"),
                  "issue": ("create", "comment", "edit", "close")}
GH_API_WRITE_METHODS = ("POST", "PATCH", "PUT", "DELETE")
# `gh api` flags whose next token is data, never a flag.
GH_API_VALUE_FLAGS = {"-H", "--header", "-q", "--jq", "-t", "--template", "--cache", "-p", "--preview",
                      "--hostname", "-R", "--repo"}


def _gh_api_write(args) -> str:
    """The label of a `gh api` call that writes, else "". The last method flag wins, as gh reads it; an
    explicit method alone decides, and with none a field or input flag makes it a POST."""
    method, fields, index = "", False, 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg in ("-X", "--method"):
            method = (args[index] if index < len(args) else "").upper()
            index += 1
        elif arg.startswith("--method="):
            method = arg[len("--method="):].upper()
        elif arg.startswith("-X") and not arg.startswith("--"):
            method = arg[2:].lstrip("=").upper()
        elif arg in GH_API_VALUE_FLAGS:
            index += 1
        elif arg in ("-h", "--help"):
            return ""   # help writes nothing
        elif arg.startswith(("-f", "-F")) and not arg.startswith("--") or arg in ("--field", "--raw-field", "--input") \
                or arg.startswith(("--field=", "--raw-field=", "--input=")):
            fields = True
    if method:
        return "api " + method if method in GH_API_WRITE_METHODS else ""
    return "api with fields" if fields else ""


def gh_write_of(segment: str) -> str:
    """The label of a gh write in the segment (or in a `sh -c` script it holds), else "": gh pr create,
    merge, comment, edit, close, review or ready; gh issue create, comment, edit or close; gh api with
    a write method, or with a field or input flag and no method."""
    tokens = segment_tokens(segment) or []
    script = inline_script(tokens) if tokens else ""
    if script:
        for part in split_segments(script):
            label = gh_write_of(part) if part.strip() else ""
            if label:
                return label
        return ""
    rest = gh_call_of(segment)
    if not rest or "-h" in rest or "--help" in rest:
        return ""
    if rest[0] == "api":
        return _gh_api_write(rest[1:])
    if len(rest) > 1 and rest[1] in GH_WRITE_VERBS.get(rest[0], ()):
        return rest[0] + " " + rest[1]
    return ""


# ---- a ready mark on a head whose records page is stale (rule records-page-ready, decision records-index-at-merge)
# The merge tool rebuilds the page on a draft, before the branch goes ready. Marking it ready first (MCP update_pull_request
# draft:false, or the gh ready command) skips that step, so the ready run is not the merge run. The read is merge.ready_page_state.
# Cost: only a call that marks a pull request ready starts anything. Per such call: the pull request's REST reads, one git fetch of the
# base and one of the head, a temporary worktree, one run of the generator and the worktree's removal. No file stays and no
# process outlives the call. The whole read shares READY_PAGE_TIMEOUT; the worktree's removal has its own 10 s, so the hook's
# 60 s timeout holds. A read that cannot run, or runs out of time, refuses as unknown (decision guard-hooks-fail-closed).
READY_PAGE_TIMEOUT = 40
READY_PAGE_MCP_TOOL = "mcp__github__update_pull_request"
READY_PAGE_STALE_REASON = (
    "Rule (Git, records-index-at-merge): the records page on the head of #%s is stale, and a pull request marked ready "
    "skips the step that rebuilds it, so the ready run would not be the merge run. Remedy: %s "
    "(decision records-index-at-merge, only the merge tool rebuilds the records page, before the branch goes ready)"
)
READY_PAGE_UNKNOWN_REASON = (
    "Rule (Git, guard-hooks-fail-closed): the records page on the head of this pull request could not be read, so it is "
    "unknown whether it is stale: %s. A read that cannot run refuses the ready mark. "
    "Remedy: retry when the read works, or return the pull request to draft and run the merge tool's draft step. "
    "(decision guard-hooks-fail-closed, a guard that cannot run its read refuses)"
)


def ready_page_calls(tool: str, tool_input: dict, command: str):
    """[(selector, repo)], one per call in this tool call that marks a pull request ready. The shell form is read by
    ci_wake.triggers, the one parser of the gh ready command (quotes, heredocs, comments, -R, GH_REPO, --undo). The MCP form is
    update_pull_request with draft false. Any other call is []: a text with no `ready` imports nothing and starts nothing."""
    if tool == READY_PAGE_MCP_TOOL:
        if tool_input.get("draft") is not False:
            return []
        owner, name = tool_input.get("owner"), tool_input.get("repo")
        repo = owner + "/" + name if isinstance(owner, str) and isinstance(name, str) else ""
        return [(str(tool_input.get("pullNumber")), repo)]
    if "ready" not in command.lower():
        return []
    import ci_wake
    return ci_wake.triggers(command, tool == "PowerShell")


def ready_page_read(selector: str, repo: str, where: str):
    """-> (state, detail): ("stale"/"current"/"skip", the pull request's number) or ("unknown", the one cause).
    Never raises: an unloadable tool, a Stop, a timeout and any other failure are one unknown with its cause."""
    module = merge_module()
    if module is None:
        return "unknown", "the merge tool could not be loaded"
    selector = selector[1:] if selector[:1] == "#" and selector[1:].isdigit() else selector
    try:
        with module.shared_deadline(READY_PAGE_TIMEOUT):
            host = module.Host(repo=repo or None, cwd=where)
            number = host.pr_number(selector)
            state = module.ready_page_state(where, number, host)
    except subprocess.TimeoutExpired:  # its text names the resolved program path
        return "unknown", "a read timed out after %d s" % READY_PAGE_TIMEOUT
    except Exception as e:  # a Stop, a missing gh, malformed JSON: all unread
        return "unknown", " ".join(str(e).split()) or type(e).__name__
    return state, str(number)


def ready_page_hit(tool: str, tool_input: dict, command: str, where: str):
    """(reason, matched) when a ready mark in this call must be refused, else None. Judged only in a repo that uses the
    merge tool. The first stale or unread head ends the scan."""
    if not where or not uses_merge_tool(where):
        return None
    for selector, repo in ready_page_calls(tool, tool_input, command):
        state, detail = ready_page_read(selector, repo, where)
        if state == "stale":
            remedy = merge_module().stale_page_remedy(int(detail))
            return READY_PAGE_STALE_REASON % (detail, remedy), "ready on a stale page #" + detail
        if state == "unknown":
            return READY_PAGE_UNKNOWN_REASON % cap_safe(detail, 200), "ready, page read unknown"
    return None


# ---- a lane commit of the generated records page (decision records-index-at-merge)
#
# The page is rebuilt only at merge. The commit is refused when the page it would hold differs from
# HEAD's page, the base tip's page AND origin/<base>'s page: a merge of the base into the lane brings
# the base's page, so it passes. The base is `resolve_default_base`, read at its TIP. A merge that brought
# a page the base has since moved past also passes: the page equals MERGE_HEAD's page by exact blob id, and
# one of two holds. MERGE_HEAD is on origin/<base>'s first-parent line (`rev-list --first-parent`), so a
# branch merged into the base is no pass. Or some best merge base of HEAD and MERGE_HEAD (`merge-base --all`,
# more than one after a criss-cross merge) is no ancestor of origin/<base> (`merge-base --is-ancestor` exits
# 1): the lane is stacked on a branch main has not merged, and MERGE_HEAD is that branch moved on. A lane cut
# from main has every best base on main, so it gets no pass from the second. Those reads run only on the path
# that would refuse. A failed merge-base read, or an is-ancestor exit other than 0 or 1, gives no stacked
# pass for that base and falls through to the first-parent test, which refuses unless MERGE_HEAD is on the
# base's first-parent line. A failed rev-parse or rev-list read refuses. The stacked clause cannot tell the
# lane's base from a sibling lane that shares its unmerged history: a sibling's page passes the same way,
# and the merge tool rebuilds the page before ready.
# A rebuilt page, a page of a merge of any other commit, and a page taken after the merge state is gone
# are refused.
# The hook runs BEFORE the shell chain, so `commit -a` (a tracked page), `commit <page>` and a `git add`
# that reaches the page earlier in the same command read the working tree, and any other commit reads
# the index. A commit that names paths (`--`, --only) holds only those paths. A non-git segment whose
# command word is `hook_catalog.py`, or a python interpreter whose script is `hook_catalog.py`, rewrites
# the page unless it has `--check` or `--print`. A later commit that reaches the page is then refused
# with no page id compared, while the base has a page. The rule acts only when the base tip's page
# opens with the generated header, so a hand-written page is no hit. Any read that fails is no hit. Limits: a
# `sh -c` script and `python -m` are not read, and `commit --include` is judged as `commit <paths>`.
RECORDS_PAGE = "docs/records.md"
RECORDS_HEADER = "# Records index\n"   # the first line of RECORDS_INTRO in lint/hook_catalog.py
RECORDS_PAGE_REASON = (
    "Rule (Git): this commit changes docs/records.md. The page is rebuilt only at merge, by the "
    "merge tool, and a lane never commits a change to it. A merge of the base into the lane "
    "brings the base's own page, and that is allowed. "
    "Remedy: drop the page from this commit, and leave the rebuild to the merge."
)
_COMMIT_VALUE_LETTERS = "mFCct"   # short commit flags whose value is the rest of the token, or the next
_COMMIT_VALUE_FLAGS = {"--message", "--file", "--reuse-message", "--reedit-message", "--fixup",
                       "--squash", "--template", "--author", "--date", "--cleanup", "--trailer",
                       "--pathspec-from-file"}
_ADD_ALL_FLAGS = {"-A", "--all", "-u", "--update"}


def _commit_shape(args):
    """Return (all_flag, pathspecs) of a `git commit` call: `-a` or `--all` (also in a short
    cluster such as `-am`), and the pathspecs. A value flag's value is never a pathspec."""
    all_flag, specs, index, only_paths = False, [], 0, False
    while index < len(args):
        arg = args[index]
        index += 1
        if only_paths:
            specs.append(arg)
        elif arg == "--":
            only_paths = True
        elif arg == "--all":
            all_flag = True
        elif arg in _COMMIT_VALUE_FLAGS:
            index += 1
        elif arg.startswith("--"):
            continue
        elif arg.startswith("-") and len(arg) > 1:
            for at, letter in enumerate(arg[1:], 1):
                if letter == "a":
                    all_flag = True
                elif letter in _COMMIT_VALUE_LETTERS:
                    index += 1 if at == len(arg) - 1 else 0
                    break
        else:
            specs.append(arg)
    return all_flag, specs


def _add_shape(args):
    """Return (whole_tree, pathspecs) of a `git add` call. Whole tree: `-A`, `--all`, `-u` or
    `--update` with no pathspec."""
    flags = [a for a in args if a.startswith("-") and a != "--"]
    specs = [a for a in args if not a.startswith("-") and a != "--"]
    whole = any(f in _ADD_ALL_FLAGS or (not f.startswith("--") and set(f[1:]) & set("Au")) for f in flags)
    return whole and not specs, specs


def _names_page(specs, where, top):
    """True when a pathspec, read from `where`, names the page, a folder above it, or a glob over it."""
    page = os.path.normcase(os.path.realpath(os.path.join(top, RECORDS_PAGE)))
    for spec in specs:
        if spec.startswith(":"):   # pathspec magic: not read, so it may name the page
            return True
        full = os.path.normcase(os.path.realpath(os.path.join(where, spec)))
        if page == full or page.startswith(full.rstrip(os.sep) + os.sep):
            return True
        if any(mark in spec for mark in "*?[") and fnmatch.fnmatch(page, full):
            return True
    return False


def _page_ids(top, base):
    """Return the page's blob ids at HEAD, at `base` and at `origin/<base>`: an id, '' for no page,
    None for a failed read."""
    out = []
    for rev in ("HEAD", base, base if base.startswith("origin/") else "origin/" + base):
        done = _git(top, "ls-tree", rev, "--", RECORDS_PAGE)
        if done is None or done.returncode != 0:
            out.append(None)
        else:
            out.append(done.stdout.split()[2] if done.stdout.strip() else "")
    return out


def _page_tracked(top):
    done = _git(top, "ls-files", "--", RECORDS_PAGE)
    return done is not None and done.returncode == 0 and bool(done.stdout.strip())


_GENERATOR = "hook_catalog.py"
_GENERATOR_READS = {"--check", "--print"}   # the two modes that write no page
_PYTHON_VALUE_FLAGS = {"-X", "-W"}


def _is_python(word):
    word = word.lower()
    word = word[:-4] if word.endswith(".exe") else word
    return word in ("py", "python") or (word.startswith("python") and word[6:].replace(".", "").isdigit())


def _runs_generator(segment):
    """True when the segment's command word is lint/hook_catalog.py, or a python interpreter whose
    script argument is it, and it has neither `--check` nor `--print`. The caller passes no git call."""
    tokens = list(segment_tokens(segment) or [])
    index = resolve_command(tokens) if tokens else None
    if index is None:
        return False
    word, rest = basename(tokens[index]), tokens[index + 1:]
    if _is_python(word):
        while rest and rest[0].startswith("-"):
            flag = rest.pop(0)
            if flag in ("-c", "-m", "-"):
                return False
            if flag in _PYTHON_VALUE_FLAGS and rest:
                rest.pop(0)
        if not rest:
            return False
        word, rest = basename(rest[0]), rest[1:]
    return word == _GENERATOR and not _GENERATOR_READS & set(rest)


def _merge_head_page(top, base):
    """The blob id of the page at MERGE_HEAD when a merge is in progress and one of two holds, else ''.
    (1) Some best merge base of HEAD and MERGE_HEAD is no ancestor of origin/<base>: the lane is stacked on
    a branch that main has not merged, and MERGE_HEAD is that branch moved on. (2) MERGE_HEAD is a commit on
    origin/<base>'s first-parent line (a past base tip). A merge-base read with no answer, or an
    is-ancestor exit other than 0 or 1, gives no stacked pass for that base and falls through to (2). A
    failed rev-parse or rev-list read gives ''."""
    # One read gives MERGE_HEAD's commit and its page: it fails when no merge is in progress.
    done = _git(top, "rev-parse", "MERGE_HEAD", "MERGE_HEAD:" + RECORDS_PAGE)
    ids = done.stdout.split() if done is not None and done.returncode == 0 else []
    if len(ids) != 2:
        return ""
    origin = base if base.startswith("origin/") else "origin/" + base
    meet = _git(top, "merge-base", "--all", "HEAD", "MERGE_HEAD")
    for best in meet.stdout.split() if meet is not None and meet.returncode == 0 else []:
        seen = _git(top, "merge-base", "--is-ancestor", best, origin)
        if seen is not None and seen.returncode == 1:   # 1 is "not an ancestor"; 0 is one, other is a failure
            return ids[1]
    line = _git(top, "rev-list", "--first-parent", origin)   # one id per base tip, newest first
    return ids[1] if line is not None and line.returncode == 0 and ids[0] in line.stdout.split() else ""


def _commit_page_id(top, working):
    """The blob id of the page the commit will hold: the working tree's (as `git add` would store
    it) or the index's. '' for no page, None for a failed read or an unmerged page."""
    if working:
        path = os.path.join(top, RECORDS_PAGE)
        if not os.path.isfile(path):
            return ""
        done = _git(top, "hash-object", "--path=" + RECORDS_PAGE, "--", path)
        return done.stdout.strip() if done is not None and done.returncode == 0 and done.stdout.strip() else None
    done = _git(top, "ls-files", "-s", "--", RECORDS_PAGE)
    if done is None or done.returncode != 0:
        return None
    rows = done.stdout.splitlines()
    return "" if not rows else (rows[0].split()[1] if len(rows) == 1 else None)


def records_page_hit(stripped: str, cwd: str) -> str:
    """Return the commit when it would hold a records page that is none of HEAD's, the base tip's,
    origin/<base>'s and MERGE_HEAD's (`_merge_head_page` says when MERGE_HEAD's page counts), else ''. Each segment is judged from its own command word."""
    staged = generated = False   # an earlier `git add` reaches the page / an earlier segment rewrites it
    for segment in split_segments(stripped):
        call = git_call_of(segment) if segment.strip() else None
        if call is None or call[0] not in ("add", "commit"):
            generated = generated or (call is None and bool(segment.strip()) and _runs_generator(segment))
            continue
        c_target = _segment_git_c_target(segment_tokens(segment) or [])
        root = command_root(stripped, cwd)
        where = _absolute(c_target, root) if c_target is not None else root
        done = _git(where, "rev-parse", "--show-toplevel") if where and os.path.isdir(where) else None
        if done is None or done.returncode != 0 or not done.stdout.strip():
            continue
        top = os.path.normpath(done.stdout.strip())
        if call[0] == "add":
            whole, specs = _add_shape(call[1])
            staged = staged or whole or _names_page(specs, where, top)
            continue
        all_flag, specs = _commit_shape(call[1])
        # The working tree's page rides in when a path names it, or (no paths) an add reached it, or
        # `-a` meets a tracked page. A commit with paths ignores the index.
        working = _names_page(specs, where, top) if specs else staged or (all_flag and _page_tracked(top))
        if specs and not working:
            continue
        base = resolve_default_base(top)
        if base is None:
            continue
        head_id, base_id, origin_id = _page_ids(top, base)
        if head_id is None or not base_id:   # a failed read, or a base with no page (first adoption): no hit
            continue
        opens = _git(top, "cat-file", "-p", base_id)   # a hand-written page is no generated page: no hit
        if opens is None or opens.returncode != 0 or not opens.stdout.startswith(RECORDS_HEADER):
            continue
        if generated and working:
            return "git commit " + RECORDS_PAGE
        page_id = _commit_page_id(top, working)
        if page_id is not None and page_id not in (head_id, base_id, origin_id):
            if not page_id or page_id != _merge_head_page(top, base):
                return "git commit " + RECORDS_PAGE
    return ""


# ---- conflict-markers: a Bash `git commit` or `git push` that would carry a leftover conflict marker
#
# The hook runs before the chain, so it cannot see what an earlier segment does to the tree. A commit, or
# a `merge`, `rebase` or `cherry-pick` with `--continue` (each commits the index), is judged only when
# every earlier segment is a git add, a git commit (judged on its own), a git read (status, diff, log,
# show), `true`, `false` or `cd`; after any other earlier segment (a blind one) it gives no hit at commit.
# A judged commit with pathspecs holds those working-tree files. `commit -a` and an earlier whole-tree
# `git add` hold the whole working tree, untracked files too. An add path that holds a substitution
# (`$`, a backtick, a parenthesis) counts as a whole-tree add. An earlier `git add <paths>` holds those
# paths from the working tree, and the rest from the index. Any other commit holds the index. Each is
# read against HEAD with `git diff --check`; an untracked file is read against /dev/null.
# A blind commit with a push after it in the call is refused only when the files that commit covers
# already hold a triplet, or the chain runs a conflict-making git step (merge, pull, rebase,
# cherry-pick, stash pop or apply, am). Otherwise it is no hit, and the push check judges what is sent.
# A push is judged on the commits it would send, which are real when the hook runs. For each ref it
# names, the range runs from the merge base with the remote-tracking tip of the destination, else the
# source's upstream, else the default base, up to the local source ref (HEAD for a bare push, and for a
# source that does not resolve). The range is one three-dot `git diff --check`, and the line kinds come from the
# source ref's blob, so it judges the net change sent. Only the "leftover conflict marker" findings
# count, never the exit code, so trailing whitespace passes.
# A file is a hit when its findings hold all three kinds: a start, a lone mid and an end marker line.
# Context never hides a marker: a fence, a string, a comment and a template literal are not read.
# Limits: a `sh -c` script and `eval` are not read, and a script that writes new markers in a blind chain
# is not caught (guard-guards-mistakes-only); at most _UNTRACKED_CAP untracked files are read per commit;
# a failed read, no HEAD, no resolvable range, `--all`, `--mirror` and a deletion push are no hit; an
# unmerged index judged alone (git refuses that commit itself) is no hit.
# Cost: per commit, one `git diff --check` (plus one read per file with a finding, and one `git ls-files`
# and up to _UNTRACKED_CAP `git diff --no-index` reads when an add reaches untracked files); per push,
# one `git diff --check` over `<tracking>...<source>`, built from the arguments with no spawn first (and
# one read per file with a finding). Only when the remote-tracking ref is missing does it cost more:
# a call per base tried (upstream, then default base), one `git rev-parse` of the source after the
# first rejection, and the default base's own reads once. Nothing is read when the command holds neither.
CONFLICT_MARKERS_REASON = (
    "Rule (Git, conflict-markers; decision commit-refuses-conflict-markers): this commit would hold conflict markers in {file}. "
    "Remedy: resolve the markers in that file, re-stage it, then retry."
)
CONFLICT_MARKERS_PUSH_REASON = (
    "Rule (Git, conflict-markers; decision commit-refuses-conflict-markers): this push would send commits that hold "
    "conflict markers in {file}. Remedy: resolve the markers in that file, commit the fix, then retry."
)
CONFLICT_MARKERS_CHAIN_REASON = (
    "Rule (Git, conflict-markers; decision commit-refuses-conflict-markers): the commit in this call follows a step "
    "the guard cannot read, so it cannot be checked for conflict markers before this push sends it. "
    "Remedy: run the push in a call of its own, after the commit has landed."
)
OCTOPUS_PUSH_REASON = (
    "Rule (Git, octopus-push; decision octopus-push-refused): this push would send {sha}, a merge commit of more than two parents. "
    "Remedy: redo that merge as a chain of two-parent merges, then retry the push."
)
_READ_VERBS = ("status", "diff", "log", "show")
_CONTINUE_VERBS = ("merge", "rebase", "cherry-pick")
_CONFLICT_VERBS = ("merge", "pull", "rebase", "cherry-pick", "am")
_UNTRACKED_CAP = 100
_CONFLICT_FINDING = re.compile(r"^(.+):(\d+): leftover conflict marker\s*$")
_MARKER_KINDS = {"<": "start", "=": "mid", ">": "end"}


def _diff_check(where, diff_args):
    """The finished `git diff --check` over `diff_args`, or None when git did not run."""
    return _git(where, "-c", "core.quotepath=off", "-c", "diff.relative=false", "diff", "--no-ext-diff", "--no-color", "--check", *diff_args)


def _marker_findings(where, top, diff_args, source):
    """Return {file: set of marker kinds} for the leftover conflict markers `git diff --check` reports."""
    done = _diff_check(where, diff_args)
    return {} if done is None else _kinds_of(done, top, source)


def _kinds_of(done, top, source):
    """{file: set of marker kinds} for the leftover conflict markers in a finished `git diff --check`.
    A line's kind is read from the new side of the file: `source` None is the working-tree file, ''
    the index blob, and a revision that revision's blob. Only a file with a finding costs a read."""
    wanted = {}
    for row in done.stdout.splitlines():
        found = _CONFLICT_FINDING.match(row)
        if found:
            wanted.setdefault(found.group(1), []).append(int(found.group(2)))
    kinds = {}
    for name, numbers in wanted.items():
        if source is not None:
            read = _git(top, "cat-file", "-p", source + ":" + name)
            text = read.stdout if read is not None and read.returncode == 0 else ""
        else:
            try:
                with open(os.path.join(top, name), encoding="utf-8", errors="replace", newline="") as handle:
                    text = handle.read()
            except OSError:
                text = ""
        lines = text.split("\n")
        for number in numbers:
            if 0 < number <= len(lines) and lines[number - 1][:1] in _MARKER_KINDS:
                kinds.setdefault(name, set()).add(_MARKER_KINDS[lines[number - 1][0]])
    return kinds


def _covered_by(where, specs):
    """The staged files that the pathspecs `git add` would restage, as git reads them."""
    done = _git(where, "-c", "core.quotepath=off", "diff", "--cached", "--name-only", "--", *specs)
    return set(done.stdout.splitlines()) if done is not None and done.returncode == 0 else set()


def _triplet_file(found):
    """The first file whose findings hold all three marker kinds, else ''."""
    return next((name for name, seen in found.items() if len(seen) == len(_MARKER_KINDS)), "")


_UNPLAIN_REV = re.compile(r"[\s$`*?\[\\]|\.\.|^-")


def _plain_source(source):
    """The local ref a push refspec sends, as a revision git reads literally: HEAD for an empty or `@`
    source, and for one with a substitution, a glob, an option dash or a range in it."""
    return "HEAD" if source in ("", "@") or _UNPLAIN_REV.search(source) else source


def _ref_sha(top, ref):
    """The commit a revision names, or '' when it names none."""
    if ref.startswith("-"):
        return ""
    done = _git(top, "rev-parse", "--verify", "-q", ref + "^{commit}")
    return done.stdout.strip() if done is not None and done.returncode == 0 else ""


def _checked_range(where, source, tracking, memo):
    """(finished `git diff --check <base>...<source>`, source) for the first base that git accepts, else
    (None, source). The three dots make git find the merge base itself, so no ref is read first. The
    bases are the destination's remote-tracking ref, the source's upstream, then the default base (read
    once per push, in `memo`). Only a rejected base costs more. After the first rejection the source is
    read once: one that does not resolve is read as HEAD, and the same base is tried again.
    `--check` exits 2 on a finding."""
    verified = source == "HEAD"
    step = 0
    while step < 3:
        if step == 2 and "default" not in memo:
            memo["default"] = resolve_default_base(where) or ""
        base = (tracking, source + "@{upstream}", memo.get("default"))[step]
        if base:
            done = _diff_check(where, [base + "..." + source, "--"])
            if done is None:
                return None, source
            if done.returncode in (0, 2):
                return done, source
            if not verified:
                verified = True
                if not _ref_sha(where, source):
                    source = "HEAD"
                    continue
        step += 1
    return None, source


def _push_refs(segment, stripped, cwd, args, skip=()):
    """(directory, source, destination, remote-tracking ref, remote, memo) for each ref a `git push`
    names, except a destination in `skip`. The tracking ref is `refs/remotes/<remote>/<dest>`, the named
    remote else origin. A source that does not resolve (a `$(...)`, a backtick, a glob, a typo) is read as
    HEAD. Everything comes from the arguments alone, with no git read beyond the destinations."""
    named = push_refspecs(args)
    where, overrides = push_target(segment, stripped, cwd)
    if named is None or not where or not os.path.isdir(where):
        return
    specs = named[1] or [""]
    dests = push_destinations(args, where, overrides)
    memo = {}
    remote = named[0] or "origin"
    for spec, dest in zip(specs, dests):
        source, colon, _target = spec.lstrip("+").partition(":")
        if (colon and not source) or dest in skip:
            continue
        tracking = ("refs/remotes/%s/%s" % (remote, dest)) if dest else ""
        yield where, _plain_source(source), dest, tracking, remote, memo


def _push_hit(segment, stripped, cwd, args):
    """Return the first file a `git push` would send with all three conflict markers, else ''. For each
    ref the push names, the range is the merge base with the destination's remote-tracking tip, else the
    source's upstream, else the default base, up to the local source ref: in the usual case one
    `git diff --check`, with no read of the top folder, the source or a base first."""
    for where, source, _dest, tracking, _remote, memo in _push_refs(segment, stripped, cwd, args):
        done, source = _checked_range(where, source, tracking, memo)
        if done is None:
            continue
        name = _triplet_file(_kinds_of(done, where, source))
        if name:
            return name
    return ""


_NOT_A_PLAIN_NAME = re.compile(r"[/:\\.~]")


def _remote_refs(where, remote):
    """The `git rev-list` option that selects the remote-tracking refs of `remote`. A push may name a URL
    or a path, whose refs sit under another name, so a word with a `/`, `:`, `\\`, `.` or `~` in it reads
    `git config --get remote.<word>.url` once, and an unconfigured one selects every remote's refs. A
    plain word is taken as a configured name, with no read."""
    if _NOT_A_PLAIN_NAME.search(remote):
        done = _git(where, "config", "--get", "remote." + remote + ".url")
        if done is None or done.returncode != 0:
            return "--remotes"
    return "--remotes=" + remote


def _octopus_hit(segment, stripped, cwd, args):
    """Return the short sha of the first merge of more than two parents that a `git push` would send,
    else ''. The range is what the push adds to the remote: the source ref, less every ref of the pushed
    remote, so an octopus that a remote ref already holds (a merge of origin/main brings one in) is not
    sent. A destination named like the default branch is skipped before any read: push-main asks about
    that push, and a deny from here would win over the ask. One `git rev-list` for each ref, and one
    `git config` more for a remote named by a URL or a path (`_remote_refs`)."""
    for where, source, _dest, _tracking, remote, _memo in _push_refs(
            segment, stripped, cwd, args, DEFAULT_BRANCH_FALLBACK):
        done = _git(where, "rev-list", "--merges", "--parents", source, "--not", _remote_refs(where, remote), "--")
        if done is None or done.returncode != 0:
            continue
        for line in done.stdout.splitlines():
            fields = line.split()
            if len(fields) > 3:
                return fields[0][:12]
    return ""


def octopus_push_hit(stripped: str, cwd: str, read_verb) -> str:
    """Return the short sha of the first merge of more than two parents that a `git push` in the command
    would send, else ''. Each segment is judged from its own command word. A push whose destination is
    unnamed reads its source's range all the same. `read_verb("push", args)` is true for a dry run, which
    sends nothing."""
    for segment in split_segments(stripped):
        call = git_call_of(segment) if segment.strip() else None
        if call is not None and call[0] == "push" and not read_verb("push", call[1]):
            sha = _octopus_hit(segment, stripped, cwd, call[1])
            if sha:
                return sha
    return ""


def _untracked_findings(where, top, specs):
    """Marker findings in the untracked files that `git add` would stage: all of them under `top` when
    `specs` is None, else those the pathspecs name. `git diff HEAD` skips an untracked file, so each is
    read against /dev/null. At most _UNTRACKED_CAP files are read, the first in git's order."""
    done = _git(where, "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard", "-z",
                "--full-name", *(["--", *specs] if specs else []))
    if done is None or done.returncode != 0:
        return {}
    found = {}
    for name in [n for n in done.stdout.split("\0") if n][:_UNTRACKED_CAP]:
        found.update(_marker_findings(top, top, ["--no-index", "--", "/dev/null", name], None))
    return found


def _chain_safe(segment):
    """True when the segment cannot change the tree a later commit reads: a git add, a git read,
    `true`, `false`, `cd` (the root already resolves through a cd) or a plain `VAR=value`. A commit is judged on its own, so
    the caller never asks about one."""
    call = git_call_of(segment)
    if call is not None:
        return call[0] == "add" or call[0] in _READ_VERBS
    tokens = segment_tokens(segment) or []
    if tokens and all(ASSIGNMENT.match(token) for token in tokens) and not set(segment) & set("`("):
        return True   # a plain `VAR=value` runs nothing; a substitution could, so it stays unsafe
    index = resolve_command(tokens) if tokens else None
    return index is not None and basename(tokens[index]) in ("true", "false", "cd")


def _continues(call):
    """True for a `merge`, `rebase` or `cherry-pick` with `--continue`: it commits the index."""
    return call[0] in _CONTINUE_VERBS and "--continue" in call[1]


def _makes_conflict(call):
    """True for a git step that can leave conflict markers in the tree: merge, pull, rebase,
    cherry-pick, `stash pop`, `stash apply` and am. A `--continue` or `--abort` leaves none."""
    if call[0] == "stash":
        return "pop" in call[1] or "apply" in call[1]
    return call[0] in _CONFLICT_VERBS and not {"--continue", "--abort"} & set(call[1])


def _unresolved(specs):
    """True when an add pathspec holds a substitution, which the guard cannot read."""
    return any(set(spec) & set("$`()") for spec in specs)


def _repo_of(repos, where):
    """`(top folder, has HEAD)` of the checkout at `where`, or None when it is not one. One
    `git rev-parse --show-toplevel --verify -q HEAD`, kept in `repos` by `where`: git prints the top
    folder, then HEAD when it resolves, and exits 1 only for a missing HEAD."""
    if where not in repos:
        done = _git(where, "rev-parse", "--show-toplevel", "--verify", "-q", "HEAD") if where and os.path.isdir(where) else None
        lines = done.stdout.splitlines() if done is not None and done.returncode in (0, 1) else []
        repos[where] = (os.path.normpath(lines[0].strip()), done.returncode == 0) if lines and lines[0].strip() else None
    return repos[where]


def conflict_markers_hit(stripped: str, cwd: str):
    """Return `(kind, file)` for the first commit or push that would carry all three conflict markers
    in one file, else `('', '')`. The kind is `commit`, `push`, or `chain` (a push after a commit the
    guard could not judge; the file is then `git push`). Each segment is judged from its own command
    word."""
    pending = []                        # earlier adds no commit has taken: (where, None) stages whole, (where, specs) names paths
    repos = {}                          # where -> (top, has_head), one `git rev-parse` each until the next commit
    readable = True                     # every segment so far is one that cannot change the tree
    blind_commit = blind_triplet = conflict_step = False   # a commit after a blind step / that covers a triplet / a conflict step ran
    ends = []
    segments = split_segments(stripped, ends)
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        call = git_call_of(segment)
        if call is not None and call[0] == "push":
            if blind_commit and (blind_triplet or conflict_step):
                return "chain", "git push"
            name = _push_hit(segment, stripped, cwd, call[1])
            if name:
                return "push", name
            readable = False
            continue
        if call is None or not (call[0] in ("add", "commit") or _continues(call)):
            readable = readable and _chain_safe(segment)
            conflict_step = conflict_step or (call is not None and _makes_conflict(call))
            continue
        c_target = _segment_git_c_target(segment_tokens(segment) or [])
        where = dir_before_segment(segments, number, cwd, ends, failed_cd_stays=True)   # this segment's own folder
        if c_target is not None:
            where = _absolute(c_target, where or "")
            where = where if os.path.isabs(where) else None
        tree = GIT_WORK_TREE_RE.search(segment)
        if tree and where:
            where = _absolute(tree.group(2), where)
        if call[0] == "add":   # an add reads nothing here: a commit that takes it reads its top folder
            whole, specs = _add_shape(call[1])
            if whole or _unresolved(specs):
                pending.append((where, None))
            elif specs:
                pending.append((where, specs))
            continue
        repo = _repo_of(repos, where)
        if repo is None:
            continue
        top, has_head = repo
        taken, pending = pending, []   # this commit takes the adds so far; the next starts clean
        wholes, adds = set(), []   # tops an add stages whole / (where, top, specs) of adds that name paths
        for add_where, add_paths in taken:
            add_repo = _repo_of(repos, add_where)
            if add_repo is None:
                continue
            if add_paths is None:
                wholes.add(add_repo[0])
            else:
                adds.append((add_where, add_repo[0], add_paths))
        repos.clear()   # a commit moves HEAD: the next segment reads afresh
        all_flag, specs = _commit_shape(call[1]) if call[0] == "commit" else (False, [])
        if not has_head:   # no HEAD: `git diff` would read an empty tree
            continue
        if specs:
            found = _marker_findings(where, top, ["HEAD", "--", *specs], None)
        else:
            if all_flag or top in wholes:
                found = _marker_findings(top, top, ["HEAD"], None)
            else:
                found = _marker_findings(top, top, ["--cached"], "")
            if top in wholes:
                found.update(_untracked_findings(top, top, None))
            for add_where, add_top, add_paths in adds:
                if add_top != top:
                    continue
                if not (all_flag or top in wholes):
                    for name in _covered_by(add_where, add_paths):
                        found.pop(name, None)
                    found.update(_marker_findings(add_where, top, ["HEAD", "--", *add_paths], None))
                found.update(_untracked_findings(add_where, top, add_paths))
        name = _triplet_file(found)
        if readable:
            if name:
                return "commit", name
        else:
            blind_commit = True
            blind_triplet = blind_triplet or bool(name)
    return "", ""


# ---- merge --role: the tier is read from this session's own get_session record
ROLE_TAG_PREFIX = BUILD_TAG
ROLE_REASON = (
    "merge-role-proof: this session's own record does not prove the merge tier it claims. "
    "If this session is the batch runner: run get_session (no argument) alone in its own "
    "turn, then retry. Any other session, the coordinator too: post the review record on the PR for your branch; the batch runner finds it "
    "(list_sessions, tag cs-build:batch-runner, same cs-repo, names the runner)."
)


def merge_tool_args(segment: str):
    """The arguments after the merge tool in a segment that runs it, else None. The one reader of which segment runs the merge tool.

    The command word is the shim (`merge`, `~/.claude/bin/merge`, `bin/merge`) or python on
    `merge/merge.py` or `merge/launch.py`.
    """
    tokens = segment_tokens(segment)
    if not tokens:
        return None
    index = resolve_command(tokens)
    if index is None:
        return None
    word = basename(tokens[index])
    rest = tokens[index + 1:]
    if word.startswith("python"):
        script = next((t for t in rest if not t.startswith("-")), None)
        if script is None or basename(script) not in ("merge.py", "launch.py") \
                or basename(os.path.dirname(script.replace("\\", "/"))) != "merge":
            return None
        return rest[rest.index(script) + 1:]
    return rest if word == "merge" else None


def role_call_of(segment: str):
    """Return the tier word after the role flag when the segment runs the merge tool with it, else None.

    A role flag with no value gives ''.
    """
    rest = merge_tool_args(segment)
    if rest is None:
        return None
    for at, arg in enumerate(rest):
        if arg == "--role":
            return rest[at + 1] if at + 1 < len(rest) else ""
        if arg.startswith("--role="):
            return arg[len("--role="):]
    return None


def _own_session_read(transcript: str, own_id: str, created: bool = False):
    """(tags, tagged_after): the own-record read of hooks/own_session.py, without the parent id."""
    # `created` counts a create_session call as a record too: rule lane-one-topic reads a lane by its start.
    return own_session.own_session_read(transcript, own_id, created)[:2]


def _own_get_session_tags(transcript: str, session_id: str):
    """The tags of the newest get_session result in this session's own transcript whose ccr.id is
    session_id (the session's own id, or a target's id for lane-closes-after-records), else None."""
    return _own_session_read(transcript, session_id)[0]


def role_proof_hit(stripped: str, transcript: str) -> str:
    """Return the matched call when a segment runs the merge tool with a role the own record does not
    prove, else ''. Fails closed inside the clause: any error in the reads is a refusal, because the
    allow rule has no classifier behind it and the guard-wide crash path fails open."""
    for segment in split_segments(stripped):
        tier = role_call_of(segment) if segment.strip() else None
        if tier is None:
            continue
        try:  # cost: one transcript read, only on a role-flag call
            from override import remote_session_id
            own_id = remote_session_id()
            if own_id and transcript:
                tags = _own_get_session_tags(transcript, own_id)
                if tier in MERGE_ROLES and tags is not None and ROLE_TAG_PREFIX + tier in tags:
                    continue
        except Exception:
            pass
        return "merge role " + tier
    return ""


# ---- merge --confirm: the checkout it acts in must be a repo the own record names (rule merge-confirm-repo)
REPO_REASON = (
    "merge-confirm-repo: this session's own record does not prove it may merge in the checkout this command acts in. "
    "A merge is allowed only in a repo that a cs-repo tag of the session's own get_session record names. "
    "If that repo is this session's own: run get_session (no argument) alone in its own turn, then retry. "
    "Otherwise hand the pull request to a batch runner whose cs-repo tags name the repo "
    "(list_sessions, tag cs-build:batch-runner). "
    "(decision merge-confirm-repo, a cloud merge acts only in a repo its own record names)"
)


class _FlagsUnreadable(Exception):
    """The merge tool's own parser refused a command's arguments."""


def _merge_flags(rest):
    """The merge tool's parsed arguments for `rest`, read with the tool's own parser (merge.build_parser), so the guard and the tool
    read -C, --repo-dir and --confirm alike. Raises _FlagsUnreadable when the tool is not loadable or the parser refuses."""
    module = merge_module()
    if module is None:
        raise _FlagsUnreadable("the merge tool is not loadable")
    parser = module.build_parser()

    def refuse(message):
        raise _FlagsUnreadable(message)
    parser.error = refuse
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        try:
            return parser.parse_args(list(rest))
        except SystemExit:  # --help and the like exit without calling error
            raise _FlagsUnreadable("the parser exited")


def _merge_target_repo(segments, number: int, cwd: str, ends, repo_dir):
    """The `owner/name` of the checkout the merge in `segments[number]` acts in, or None: the -C value (relative to the shell directory
    in force where that segment runs), else that directory. The directory comes from `dir_before_segment`, which walks each earlier
    segment's `cd` in order, ignores `git -C` (it does not move the shell) and returns None for a move it cannot follow (a variable,
    `cd -` with no earlier directory, `popd`): None here is a refusal. `command_root` is not used: it reads the last `cd` of the whole
    command, and its other callers want that."""
    import git_reads
    where = dir_before_segment(segments, number, cwd, ends)
    if repo_dir is not None:
        if not repo_dir:
            return None
        repo_dir = os.path.expanduser(repo_dir)
        if os.path.isabs(repo_dir):
            where = repo_dir
        else:
            where = os.path.join(where, repo_dir) if where else None
    return git_reads.github_repo(where) if where and os.path.isdir(where) else None


def repo_proof_hit(stripped: str, cwd: str, transcript: str) -> str:
    """Return a short label when a cloud session's `merge --confirm` acts in a checkout whose repo no cs-repo tag of the own newest
    get_session record names, else ''. Fails closed inside the clause, like role_proof_hit: an unparseable command, an unreadable
    checkout, no record and a set_session_tags after the record are each a refusal, because the guard-wide crash path fails open.
    --lane-lint merges nothing and is not judged. Outside the cloud nothing is judged. Cost: none for a call that is no merge confirm;
    else one parse, one read of the origin and one transcript read.

    A redirection (`2>&1`, `> run.log`) belongs to the shell, not to the merge tool, so the parser reads the segment without them
    (strip_redirections, the quote-aware reader of their shape; a quoted `<` or `>` is text and stays). When the segment no longer
    tokenizes once they are gone (a quote left open), the merge is denied, never skipped."""
    if not is_cloud():
        return ""
    return "merge --confirm" if _unproved_confirm(stripped, cwd, transcript, 0) else ""


MERGE_NEST_DEPTH = 4  # `bash -c` inside `bash -c` is followed this far; a deeper script is judged as a refusal


def _unproved_confirm(text: str, cwd: str, transcript: str, depth: int) -> bool:
    """True when a `merge --confirm` in `text` acts in a checkout the own record does not prove. `text` is the command, or a script a
    segment hands on (`bash -c`, `sh -c`, `eval`: inner_commands, the one reader of those wrappers), which runs in the directory its own
    segment is in. A `)` or `&` glued to the last word ends the merge's arguments (_command_words), so a merge closing a subshell is read."""
    ends = []
    segments = split_segments(text, ends)
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        scripts = inner_commands(tokens) if tokens else []
        if scripts:
            if depth >= MERGE_NEST_DEPTH:
                if any("--confirm" in script for script in scripts):
                    return True
            else:
                where = dir_before_segment(segments, number, cwd, ends) or ""
                if any(_unproved_confirm(script, where, transcript, depth + 1) for script in scripts):
                    return True
        if merge_tool_args(segment) is None:
            continue
        try:
            rest = _command_words(merge_tool_args(segment))
            bare = merge_tool_args(strip_redirections(segment))
            bare = None if bare is None else _command_words(bare)
            if "--confirm" not in (rest if bare is None else bare):
                continue
            if bare is None:
                raise _FlagsUnreadable("the segment does not tokenize without its redirections")
            flags = _merge_flags(bare)
            if flags.lane_lint or not flags.confirm:
                continue
            repo = _merge_target_repo(segments, number, cwd, ends, flags.repo_dir)
            from override import remote_session_id
            from shared_names import repo_tag_names
            own_id = remote_session_id()
            if repo and own_id and transcript:
                tags, tagged_after = _own_session_read(transcript, own_id)
                if tags is not None and not tagged_after and any(repo_tag_names(tag, repo) for tag in tags):
                    continue
        except Exception:
            pass
        return True
    return False


# ---- the record branch's one writer: only the triage session pushes to it (rule roadmap-one-writer)
RECORD_WRITER_TIER = "triage"
DEFAULT_RECORD_BRANCH = "roadmap"
RECORD_REASON = (
    "roadmap-one-writer: the repo's record branch has one writer, the triage session, and this session's own "
    "record does not prove it is triage. Send the step change to the triage session (list_sessions, tag "
    "cs-build:triage, same cs-repo). If this session is triage: run get_session (no argument) alone in its "
    "own turn, then retry. (decision session-tiers, the triage session is the only writer of the record branch)"
)


def _own_tier_proved(transcript: str, tier: str) -> bool:
    """True when the own newest get_session record lists cs-build:<tier> and no set_session_tags call
    follows it. Fails closed: no env id, no transcript or any read error is False."""
    try:
        from override import remote_session_id
        own_id = remote_session_id()
        if own_id and transcript:
            tags, tagged_after = _own_session_read(transcript, own_id)
            return tags is not None and not tagged_after and ROLE_TAG_PREFIX + tier in tags
    except Exception:
        pass
    return False


def _open_substitutions(text: str) -> int:
    """How many `$(` spans in `text` are still open at its end. Inside a span, a `(` opens and a `)` closes."""
    depth = index = 0
    while index < len(text):
        if text.startswith("$(", index):
            depth, index = depth + 1, index + 2
            continue
        if depth and text[index] in "()":
            depth += 1 if text[index] == "(" else -1
        index += 1
    return depth


def _command_words(args):
    """`args` up to the end of their command. The segment splitter cuts at `&&`, `||`, `;`, `|` and a
    newline, but not at `(`, `)` or a lone `&`. A `)` glued to a word closes the subshell the command
    sits in, and a glued `&` sends it to the background: either ends that word and the command.
    A `)` that closes a `$(` does neither. The words of a `$( )` span join into one word, whose text
    is unknown until the shell runs it, so `$(printf origin) main` keeps its `main`."""
    words = []
    span = ""
    for arg in args:
        arg = span + " " + arg if span else arg
        word = arg.rstrip(")&")
        tail = arg[len(word):]
        opened, closes = _open_substitutions(word), len(tail) - len(tail.lstrip(")"))
        span = arg if opened > closes else ""
        if span:
            continue
        word = arg[:len(word) + opened]
        if word != arg:
            if word:
                words.append(word)
            break
        words.append(arg)
    if span:
        words.append(span)
    return words


def _push_calls(segment: str, script: str, cwd: str):
    """(arguments, directory, config overrides) of each `git push` in one segment, and in the scripts the
    segment hands on (`bash -c`, `sh -lc`, `eval`, `ssh`): the one reader of those wrappers is inner_commands.
    `script` is the text the segment came from, which push_target reads for a leading `cd`. A script
    runs in the folder its segment's own `cd` or `git -C` names."""
    for subcommand, args in push_calls(segment, script):
        if subcommand == "push":
            where, overrides = push_target(segment, script, cwd)
            yield _command_words(args), where, overrides
    tokens = segment_tokens(segment)
    inner = inner_commands(tokens) if tokens else []
    if inner:
        inner_cwd = push_target(segment, script, cwd)[0] or cwd
        from guard_env import substitution_commands   # imported late: a family reads only the families before it
        for text in inner:
            # The shell reads the wrapped script as it reads a command: a heredoc body is data, and
            # each `$( )` or backtick text runs as a command of its own (judge_shell does the same).
            stripped = strip_heredoc_bodies(text)
            for each in (stripped, *substitution_commands(text, stripped)):
                for part in split_segments(each):
                    yield from _push_calls(part, each, inner_cwd)


def record_writer_hit(stripped: str, cwd: str, transcript: str, record_branch_of, read_verb) -> str:
    """Return the matched push when a segment pushes to the checkout's record branch, or to the default
    name `roadmap`, and the own record does not prove the triage tier, else ''. `record_branch_of(root)`
    reads the checkout's branch (lint/layout.py); a read error means the default. `read_verb(subcommand,
    args)` is guard.py's own test for a dry run, which moves nothing. The proof is read only after a push
    reaches the branch."""
    for segment in split_segments(stripped):
        for args, where, overrides in _push_calls(segment, stripped, cwd):
            if read_verb("push", args):
                continue
            top = _git(where, "rev-parse", "--show-toplevel") if where else None
            root = top.stdout.strip() if top is not None and top.returncode == 0 and top.stdout.strip() else where
            try:
                record = record_branch_of(root)
            except Exception:
                record = DEFAULT_RECORD_BRANCH
            if {record, DEFAULT_RECORD_BRANCH} & set(push_destinations(args, where, overrides)) and (
                    not _own_tier_proved(transcript, RECORD_WRITER_TIER)):
                return "git push to the record branch"
    return ""


TRUST_TOOLS = ("mcp__claude-code-remote__confirm_repository_trust", "mcp__claude-code-remote__request_computer_folder")
TRUST_REASON = (
    "trust-card-in-build: this call opens an owner card that blocks every message into the session, and "
    "this session's own record does not prove it has no cs-build tag. A cs-build session hands the act to "
    "the owner or to an untagged session. A session with no record yet: run get_session (no "
    "argument) alone in its own turn, then retry."
)


def trust_card_hit(tool: str, transcript: str) -> str:
    """Return the tool name when it opens a trust card and the own record does not prove an untagged
    session, else ''. Fails closed: any error in the reads is a refusal, because the guard-wide crash
    path fails open."""
    if tool not in TRUST_TOOLS:
        return ""
    try:  # cost: one transcript read, only on these two calls
        from override import remote_session_id
        own_id = remote_session_id()
        if own_id and transcript:
            tags, tagged_after = _own_session_read(transcript, own_id)
            if tags is not None and not tagged_after and not any(str(t).startswith(ROLE_TAG_PREFIX) for t in tags):
                return ""
    except Exception:
        pass
    return tool


# ---- archive_session: a lane closes only after its records pull request has left the open list
ARCHIVE_TOOL = "mcp__claude-code-remote__archive_session"
ARCHIVE_LANE_TAG = LANE_TAG
ARCHIVE_STEP_PREFIX, ARCHIVE_REPO_PREFIX = "cs-step:", "cs-repo:"
ARCHIVE_NO_RECORD_REASON = (
    "this session's or this agent's transcript holds no get_session record of the target, so the guard cannot tell whether "
    "the target is a lane with records still to land. Run get_session on the target alone, in its own turn, "
    "then retry. (decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_OPEN_REASON = (
    "the lane's records pull request is still open, so closing the lane now strands its records. Wait until "
    "that pull request merges or is closed as replaced, then retry. (decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_TAGS_REASON = (
    "the target's record is a lane with no cs-step tag or no cs-repo tag, so the guard cannot find its "
    "records pull request. Fix the lane's tags, run get_session on the target alone, then retry. (decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_READ_REASON = (
    "the open pull requests of the lane's repo could not be read, so the guard cannot tell whether its "
    "records have landed. Retry once gh answers. (decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_NO_PR_REASON = (
    "a branch of the lane is ahead of its repo's default branch and has no pull request that covers it, so closing "
    "the lane now strands that work. Either open a pull request for that branch and hand it to the batch runner, or "
    "push an archive copy of it under archive/, then retry. "
    "(decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_BRANCH_READ_REASON = (
    "the lane's branches or their pull requests could not be read, so the guard cannot tell whether any work of "
    "the lane is stranded. Retry once gh answers. (decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_STRANDED_MATCH = "archive of a lane with a branch that has no pull request"
_REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# A source URL on github.com (https, ssh or scp form, an optional www., any case, an optional path after owner/name): `repo`
# is its owner/name, and is None when the host is github.com but the rest is no owner/name. Another host does not match.
_SOURCE_REPO = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.-]*://)?(?:[^@/]+@)?(?:www\.)?github\.com(?=[/:]|\Z)"
    r"(?:[/:](?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?(?:/.*)?\Z)?",
    re.IGNORECASE,
)
_AHEAD = ("ahead", "diverged")
_CONTAINED = ("behind", "identical")  # a compare of base...head where the head is already in the base


def _read_json(host, rel: str, what: str):
    """The parsed JSON of one REST read of `host`; a failed read or a reply that is not JSON raises RuntimeError."""
    code, out = host.api(rel)
    try:
        if code:
            raise ValueError(out)
        return json.loads(out)
    except ValueError as e:
        raise RuntimeError("the " + what + " read failed: " + str(e))


def _compare_status(module, host, base: str, head: str, missing_ok: bool = False):
    """The status of GitHub's compare of base...head (the one read behind the draft, the ahead and the containment
    tests). With `missing_ok`, a 404 means the head is not in that repo and gives None. Any other failed read raises."""
    code, out = host.api("compare/" + base + "..." + head)
    if code and missing_ok and not module.is_net(code, out) and re.search(r"\bHTTP 404\b", out):
        return None
    try:
        if code:
            raise ValueError(out)
        return str(json.loads(out)["status"])
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError("the compare read failed: " + str(e))


def _head_landed(module, repo: str, row) -> bool:
    """True when the head commit of the pull request `row` is already in the repo's default branch: the row's
    base is that branch (base.repo.default_branch, so a draft stacked on another branch is not released), and
    GitHub's compare of default...sha reads behind or identical. A failed read raises, and archive_hit refuses on it.
    The caller holds the one shared deadline over this read (a nested shared_deadline would reset it)."""
    base, sha = str(row["base"]["ref"]), str(row["head"]["sha"])
    if base != str(row["base"]["repo"]["default_branch"]):
        return False
    return _compare_status(module, module.Host(repo=repo), base, sha) in _CONTAINED


def _branch_repos(ccr, tag_repos):
    """The repos a lane's branches may live in: its cs-repo tags, the github repos of
    session_context.sources[].git_repository.url, and each current_branches key that names owner/repo, in first-seen
    order. Shape drift raises: a sources field that is present but not a list, and a github.com URL that does not
    parse as owner/name. A URL on another host is skipped."""
    found = list(tag_repos)
    sources = (ccr.get("session_context") or {}).get("sources")
    if sources is not None and not isinstance(sources, list):
        raise RuntimeError("sources is not a list")
    named = []
    for source in sources or []:
        repo = source.get("git_repository") if isinstance(source, dict) else None
        url = repo.get("url") if isinstance(repo, dict) else None
        match = _SOURCE_REPO.match(url) if isinstance(url, str) else None
        if not match:
            continue
        if not match.group("repo"):
            raise RuntimeError("a github.com source URL is no owner/name")
        named.append(match.group("repo"))
    meta = ccr.get("external_metadata")
    keys = meta.get("current_branches") if isinstance(meta, dict) else None
    named += [k for k in keys if isinstance(k, str) and _REPO_NAME.fullmatch(k)] if isinstance(keys, dict) else []
    return found + [r for r in dict.fromkeys(named) if r not in found]


def _on_lane_form(ref: str, slugs) -> bool:
    """True when `ref` is a head form of a slug (lane_head_refs) or a `-*` variant of one, such as `lane/<slug>-r2`."""
    return any(ref == form or ref.startswith(form + "-") for slug in slugs for form in lane_head_refs(slug))


def _is_merged(row) -> bool:
    """True when the pull request row is merged: its `merged` flag, or `merged_at` (what a list read carries)."""
    return row.get("merged") is True or bool(row.get("merged_at"))


def _is_open(rows) -> bool:
    return any(row["state"] == "open" for row in rows)


def _covered(module, host, branch: str, tip, rows, pool) -> bool:
    """True when a pull request or an archive copy holds the work of `branch`, whose pull requests in every state are
    `rows` and whose tip is `tip` (read from the branch when None, once no open pull request covers it). An open pull
    request covers. A merged one covers when its head is the tip. A closed unmerged one covers only when the tip is
    contained in the head of an open or merged pull request (compare of that head...tip reads behind or identical).
    Those heads come from `pool`, the rows already read: the repo's open list rows on a lane head form and the rows
    of every other branch of the lane that was read. A merged pull request on a head no read reached is not seen,
    so that case refuses. Last, an archive copy covers when the tip is contained in it (compare of copy...tip reads
    behind or identical). The copies are those listed at git/matching-refs/heads/archive/<branch> that are named
    exactly `archive/<branch>` or `archive/<branch>-<digits>`; any other listed name does not count, and an empty
    listing means no copy, so the branch is not covered. This adds one tip read when the caller had none, one compare
    per head to test, one copy listing and one compare per counted copy, all on the refusal path."""
    if _is_open(rows):
        return True
    if tip is None:
        tip = str(_read_json(host, "branches/" + branch, "branch")["commit"]["sha"])
    if any(str(row["head"]["sha"]) == tip for row in rows if _is_merged(row)):
        return True
    if any(row["state"] == "closed" and not _is_merged(row) for row in rows):
        heads = [str(row["head"]["sha"]) for row in [*rows, *pool] if row["state"] == "open" or _is_merged(row)]
        if any(sha == tip or _compare_status(module, host, sha, tip) in _CONTAINED for sha in dict.fromkeys(heads)):
            return True
    copy_name = re.compile(re.escape("archive/" + branch) + r"(-[0-9]+)?")
    for ref in host.pages("git/matching-refs/heads/archive/" + branch):
        name = str(ref["ref"])[len("refs/heads/"):]
        if copy_name.fullmatch(name) and _compare_status(module, host, name, tip, missing_ok=True) in _CONTAINED:
            return True
    return False


def _stranded_branch(module, ccrs, tag_repos, slugs, open_rows) -> bool:
    """True when a branch of the lane is ahead of its repo's default branch (compare status ahead or diverged) and no
    pull request covers it (_covered). The branches are the non-null values of each record's
    external_metadata.current_branches, and, in each repo, the branches under a slug form (`<slug>`, `lane/<slug>`,
    and their `-*` variants) that the records do not name, read from git/matching-refs/heads/<form>. A record with no
    branch field, an empty list or map, or only null values names none. A branch field that is not a map, and a
    value that is neither null nor a string, are shapes the read does not know, so they raise. A 404 on the compare
    means the branch is not in that repo, so it is skipped in that repo. Any other failed read raises, and
    archive_hit refuses on it. The caller holds one shared deadline over all the reads here (a nested
    shared_deadline would reset it). `open_rows` is each repo's open pull request list, already read. Every pull
    request read of a repo is judged together, so a replacement on another branch of the lane is in hand."""
    branches, repos = [], list(tag_repos)
    for ccr in ccrs:
        meta = ccr.get("external_metadata")
        named = meta.get("current_branches") if isinstance(meta, dict) else None
        if named is None or named == []:
            named = {}
        if not isinstance(named, dict):
            raise RuntimeError("current_branches is not a map")
        if any(b is not None and not isinstance(b, str) for b in named.values()):
            raise RuntimeError("a current_branches value is not a string")
        branches += [b for b in named.values() if b]
        repos += [r for r in _branch_repos(ccr, tag_repos) if r not in repos]
    branches = list(dict.fromkeys(branches))
    defaults = {}
    for repo in repos:
        host = module.Host(repo=repo)
        owner = repo.split("/")[0]
        pool = [row for row in open_rows.get(repo, []) if _on_lane_form(str(row["head"]["ref"]), slugs)]
        pending = []  # (branch, tip or None, rows) of each branch ahead of the default: judged once every row is read

        def ahead(branch):
            """True when `branch` is not the default or an archive copy, and its compare with the default reads ahead."""
            if repo not in defaults:
                defaults[repo] = str(_read_json(host, "", "repo")["default_branch"])
            if branch.startswith("archive/") or branch == defaults[repo]:
                return False
            return _compare_status(module, host, defaults[repo], branch, missing_ok=True) in _AHEAD

        for branch in branches:
            if ahead(branch):
                rows = host.pages("pulls", fields={"state": "all", "head": owner + ":" + branch})
                pool += rows
                pending.append((branch, None, rows))
        seen = set(branches)
        for slug in slugs:
            for form in lane_head_refs(slug):
                for ref in host.pages("git/matching-refs/heads/" + form):
                    name = str(ref["ref"])[len("refs/heads/"):]
                    if name in seen or not _on_lane_form(name, [slug]):
                        continue
                    seen.add(name)
                    # The branch exists (the refs read just listed it), so an open pull request covers it before any
                    # default-branch read; its tip is on the row already in hand.
                    rows = host.pages("pulls", fields={"state": "all", "head": owner + ":" + name})
                    pool += rows
                    if not _is_open(rows) and ahead(name):
                        pending.append((name, str(ref["object"]["sha"]), rows))
        if any(not _covered(module, host, branch, tip, rows, pool) for branch, tip, rows in pending):
            return True
    return False


def _archive_transcripts(transcript: str, agent_id):
    """The transcripts that hold the record of an archive's target: the main transcript and, for an agent's call
    (agent_id already checked by the caller), the agent's own. The one home of that choice."""
    return [transcript] + ([own_session.agent_transcript_path(transcript, agent_id)] if agent_id else [])


def _archive_records(transcript: str, target, agent_id):
    """The `ccr` of the target's newest get_session record in each transcript of _archive_transcripts, None where one
    holds none. Each transcript is read once, and the tags and the branch read both come from that read. An agent file
    that does not exist holds no record; one that exists and cannot be read as a file (a folder, no read access)
    raises, because own_session_ccr reads it as no record. cost: one transcript read per transcript, no file written,
    no gh call."""
    ccrs = []
    for path in _archive_transcripts(transcript, agent_id):
        ccr = own_session.own_session_ccr(path, target)
        if ccr is None and os.path.lexists(path) and not (os.path.isfile(path) and os.access(path, os.R_OK)):
            raise OSError("the transcript is not a readable file: " + path)
        ccrs.append(ccr)
    return ccrs


def _archive_tags(ccrs):
    """The tags that decide an archive, or None when no record of the target exists. A record with the lane tag decides:
    its tags, or the two records' tags joined when both are lanes. Else the first record decides."""
    records = [c["tags"] for c in ccrs if isinstance(c, dict) and isinstance(c.get("tags"), list)]
    lanes = [tags for tags in records if ARCHIVE_LANE_TAG in tags]
    if lanes:
        return [tag for tags in lanes for tag in tags]
    return records[0] if records else None


def archive_hit(tool: str, tool_input, transcript: str, agent_id=None):
    """Return (matched, reason) when this archive call must be refused, else None. A target whose newest
    get_session record in this session's transcript, or for an agent's call (`agent_id`, checked by the caller
    against guard.AGENT_ID) in the agent's own transcript too, has no cs-build:lane tag passes. A lane in either
    record is a lane. A lane is refused while any open pull request of its cs-repo has a head ref in
    lane_head_refs of its cs-step slug, except an open draft whose head commit is already in its base (compare:
    behind or identical). A lane is also refused while a branch of it (the records' current_branches, and the
    repos' branches under its slug forms) is ahead of the repo's default branch with no covering pull request
    (_stranded_branch). Fails closed: any error in the reads is a refusal, because the guard-wide crash path fails
    open. A failed open-list read (the list and the draft compares) and a failed branch read each refuse with their
    own reason. All the gh reads share one MERGE_READ_TIMEOUT."""
    if tool != ARCHIVE_TOOL:
        return None
    target = tool_input.get("session_id") if isinstance(tool_input, dict) else None
    try:  # cost: one read of each transcript per archive call (two for an agent's call), for the tags and the branches
        ccrs = _archive_records(transcript, target, agent_id) if transcript and isinstance(target, str) and target else []
    except Exception:
        ccrs = []
    tags = _archive_tags(ccrs)
    if tags is None:
        return "archive with no record of the target", ARCHIVE_NO_RECORD_REASON
    if ARCHIVE_LANE_TAG not in tags:
        return None
    slugs = [str(t)[len(ARCHIVE_STEP_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_STEP_PREFIX)]
    repos = [str(t)[len(ARCHIVE_REPO_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_REPO_PREFIX)]
    slugs, repos = list(dict.fromkeys(x for x in slugs if x)), list(dict.fromkeys(x for x in repos if x))
    if not slugs or not repos or not all(_REPO_NAME.fullmatch(r) for r in repos):
        return "archive of a lane with no step or repo tag", ARCHIVE_TAGS_REASON
    lanes = [c for c in ccrs if isinstance(c, dict) and isinstance(c.get("tags"), list) and ARCHIVE_LANE_TAG in c["tags"]]
    reading_branches = False  # picks the reason a failed read refuses with
    try:  # cost, all under one shared MERGE_READ_TIMEOUT: one paged gh REST read per cs-repo tag (one in practice), through
        # the merge tool's page reader; one compare read per open draft of the lane; per repo, one matching-refs read per
        # slug form (a paged read); and, for each branch the records name, one repo read per repo, one compare read per
        # repo x branch, and one pulls read per branch that is ahead. A branch under a slug form adds one pulls read, and
        # one compare read when no open pull request covers it. A branch with a pull request adds one tip read, and a
        # closed unmerged one adds one compare read per distinct open or merged head among the rows already read.
        module = merge_module()
        if module is None:
            raise RuntimeError("the merge tool could not be loaded")
        open_rows = {}
        with module.shared_deadline(MERGE_READ_TIMEOUT):
            for repo in repos:
                rows = open_rows[repo] = module.Host(repo=repo).pages("pulls", fields={"state": "open"})
                for row in rows:
                    ref = str(row["head"]["ref"])
                    slug = next((s for s in slugs if ref in lane_head_refs(s)), None)
                    if slug and row.get("draft") is True and _head_landed(module, repo, row):
                        continue
                    if slug:
                        return "archive of lane " + slug + " with open pull request " + str(row.get("number", "?")), ARCHIVE_OPEN_REASON
            reading_branches = True
            stranded = _stranded_branch(module, lanes, repos, slugs, open_rows)
    except (Exception, SystemExit):
        if reading_branches:
            return "archive with an unreadable branch read", ARCHIVE_BRANCH_READ_REASON
        return "archive with an unreadable pull request list", ARCHIVE_READ_REASON
    if stranded:
        return ARCHIVE_STRANDED_MATCH, ARCHIVE_NO_PR_REASON
    return None


# ---- send_message: a lane brief goes to a lane of its own topic (rule lane-one-topic)
BRIEF_TOOL = "mcp__claude-code-remote__send_message"
LANE_BRIEF_MARKER = "Lane brief:"  # the first non-blank line of a brief (after its Grant line, if any) starts `Lane brief: <step>. Topic: <topic>.`
TOPIC_TAG_PREFIX = TOPIC_TAG
_MARKDOWN_LEAD = r"[#*_>\s]*"  # a brief may open with markdown: a heading, bold, a quote
_BRIEF_MARKER_LINE = re.compile(_MARKDOWN_LEAD + re.escape(LANE_BRIEF_MARKER), re.IGNORECASE)
_BRIEF_LINE = re.compile(
    _MARKDOWN_LEAD + re.escape(LANE_BRIEF_MARKER) + r"[\s*_]*(?P<step>[A-Za-z0-9_-]+)\s*\.(?:\s*Topic:\s*(?P<topic>[A-Za-z0-9_-]+))?",
    re.IGNORECASE)
BRIEF_NO_RECORD_REASON = (
    "this session's transcript holds no get_session or create_session record of the target, so the guard "
    "cannot tell which topic the lane holds. Run get_session on the target alone, in its own turn, then retry. "
    "(decision session-tiers, a lane holds one topic)"
)
BRIEF_STALE_REASON = (
    "a set_session_tags call on the target followed this session's newest record of it, so the guard cannot tell "
    "which topic or steps the lane holds now. Run get_session on the target alone, in its own turn, then retry. "
    "(decision session-tiers, a lane holds one topic)"
)
BRIEF_TOPIC_REASON = (
    "this brief names a topic the lane does not hold. A lane holds one topic, and a brief's first line is "
    "`Lane brief: <step>. Topic: <topic>.` with the lane's own cs-topic. Work on another topic goes to a new "
    "lane: start one with create_session. (decision session-tiers, a lane holds one topic)"
)
BRIEF_STEP_REASON = (
    "this brief names a step the lane does not carry, and the lane has no cs-topic tag to judge its Topic by. "
    "Work on another step goes to a new lane: start one with create_session. "
    "(decision session-tiers, a lane holds one topic)"
)
BRIEF_START_TOPIC_REASON = (
    "this start's brief names a topic that the start's cs-topic tag does not hold. A lane holds one topic. Set the "  # glossary-ok: session-tiers is the decision's file name
    "cs-topic tag to the brief's Topic, or put the lane's own topic on the brief's first line: "
    "`Lane brief: <step>. Topic: <topic>.` (decision session-tiers, a lane holds one topic)"
)
BRIEF_START_STEP_REASON = (
    "this start carries no cs-topic tag, and no cs-step tag for the brief's step, to judge its brief by. Add a "  # glossary-ok: session-tiers is the decision's file name
    "cs-topic tag that matches the brief's Topic, or a cs-step tag for its step. "
    "(decision session-tiers, a lane holds one topic)"
)
BRIEF_PLACE_REASON = (
    "this start's prompt holds a `Lane brief:` line that is not the first line after the Grant line, so no reader "  # glossary-ok: session-tiers is the decision's file name
    "judges its topic. Move that line up: the first line after the Grant line is "
    "`Lane brief: <step>. Topic: <topic>.` (decision session-tiers, a lane holds one topic)"
)

BRIEF_GRANT_REASON = (
    "this brief opens with a Grant line that is empty or a placeholder: it holds a `<`, or no letter or digit, "
    "after `Grant:`. A template placeholder is no grant. Put the grant and its time after `Grant:`, as the "
    "owner gave them. (decision agent-model-cap, the lane start)"
)


def topic_hit(first: str, tags, start: bool = False):
    """(matched, reason) when the brief line `first` names a topic the lane holding `tags` does not hold, else None.
    A lane with a cs-topic tag is judged by the brief's Topic, an older lane without one by the brief's step against
    its cs-step tags. The one judge for a send_message brief and a create_session start prompt. `start` picks the
    start's reasons, which name the missing tag, in place of the steer to start a new lane."""
    found = _BRIEF_LINE.match(first)
    step, topic = (found.group("step"), found.group("topic")) if found else (None, None)
    topics = [str(t)[len(TOPIC_TAG_PREFIX):].strip() for t in tags if str(t).startswith(TOPIC_TAG_PREFIX)]
    topics = [t for t in topics if t]
    if topics:
        if (topic or "").lower() not in [t.lower() for t in topics]:
            return "lane brief for topic " + str(topic) + " to a lane on " + ", ".join(topics), \
                BRIEF_START_TOPIC_REASON if start else BRIEF_TOPIC_REASON
        return None
    steps = [str(t)[len(ARCHIVE_STEP_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_STEP_PREFIX)]
    if step not in steps:
        return "lane brief for step " + str(step) + " to a lane with no topic tag", \
            BRIEF_START_STEP_REASON if start else BRIEF_STEP_REASON
    return None


def brief_hit(tool: str, tool_input, transcript: str):
    """Return (matched, reason) when this send_message is a lane brief for a topic the target lane does not
    hold, else None. Only a message whose first non-blank line (after its Grant line, if any) starts with
    LANE_BRIEF_MARKER is read; the transcript is read for that message alone. A Grant line before such a brief
    must hold the owner's words (grant_line_holds_words). A target whose newest record (get_session, or the
    create_session that made it) has no cs-build:lane tag passes. A lane with a cs-topic tag is judged by the
    brief's Topic, an older lane without one by the brief's step against its cs-step tags (topic_hit). A
    create_session call that tags a lane is judged the same way, by its prompt against its own tags, with no
    transcript read. Fails closed: any error in the reads is a refusal, because the guard-wide crash path fails open."""
    if not isinstance(tool_input, dict):
        return None
    if tool == BRIEF_TOOL:
        text = tool_input.get("message")
    elif is_lane_create_session(tool, tool_input):
        text = tool_input.get("prompt")
    else:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()] if isinstance(text, str) else []
    grant = None
    if lines and lines[0].startswith(LANE_GRANT_MARKER):  # a lane brief opens with the owner's Grant line; the marker line follows it
        grant, lines = lines[0], lines[1:]
    first = lines[0] if lines else ""
    if not _BRIEF_MARKER_LINE.match(first):
        if tool != BRIEF_TOOL and any(_BRIEF_MARKER_LINE.match(line) for line in lines[1:]):  # a start's marker past its first line is read by no one
            return "lane start whose brief marker is not on the first line after the Grant line", BRIEF_PLACE_REASON
        return None
    if grant is not None and not grant_line_holds_words(grant):
        return "lane brief under an empty or placeholder Grant line", BRIEF_GRANT_REASON
    if tool != BRIEF_TOOL:
        return topic_hit(first, lane_tags(tool_input), start=True)
    target = tool_input.get("session_id")
    try:  # cost: one transcript read per brief
        tags, tagged_after = _own_session_read(transcript, target, created=True) \
            if transcript and isinstance(target, str) and target else (None, False)
    except Exception:
        tags, tagged_after = None, False
    if tags is None:
        return "lane brief to a target with no record", BRIEF_NO_RECORD_REASON
    if ARCHIVE_LANE_TAG not in tags:
        return None
    if tagged_after:  # a set_session_tags call on the target followed its record, so the topic or steps may have changed
        return "lane brief to a target whose record is stale", BRIEF_STALE_REASON
    return topic_hit(first, tags)


# ---- send_message: a header stamp matches the clock (rule message-time-matches-clock)
STAMP_LIMIT_MINUTES = 1  # a header stamp this far ahead of the clock passes; one more minute ahead is refused
STAMP_QUOTE_MINUTES = 60  # an undated stamp more than this far ahead reads as a quote from an earlier day, and passes
# A header is a label of 1 to 4 words, then `,` or `:` or a dash spaced on both sides, an optional date, then
# `H:MM` or `HH:MM`, an optional `:SS`, and `CST` or `CDT` in any case. Anything may follow.
_STAMP_HEADER = re.compile(
    _MARKDOWN_LEAD + r"[^\s,:]+(?:\s+[^\s,:]+){0,3}(?:[,:]|\s[-\u2014\u2013])\s*"
    r"(?:(?P<date>\d{4}-\d{2}-\d{2})\s+)?"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::\d{2})?\s+(?P<zone>CST|CDT)\b", re.IGNORECASE)
_STAMP_OFFSET_HOURS = {"CST": -6, "CDT": -5}
STAMP_REASON = (
    "this message's header stamp is wrong for the clock: {why}. "
    "The time is {now}: re-stamp your own header with that time, then send it again. Read the time with "
    "`~/.claude/bin/now-central`, never from memory. If the first line quotes "
    "someone else's time in header form, open the message with your own label first. "
    "If the first line names a future time, such as a deadline or an ETA, move it off the first line. "
    "(decision local-time-central, sessions speak times in US Central)"
)
STAMP_AHEAD_WHY = "it is {off} minutes ahead, and the limit is " + str(STAMP_LIMIT_MINUTES)
STAMP_ZONE_WHY = "it says {zone}, and the clock's zone now is {name}"


def _minutes_ahead(then, now) -> int:
    """Whole minutes an instant is ahead of the clock: negative when it is behind. Both are cut to the minute
    first, so the header stamp and an ISO instant compare one way (rule message-time-matches-clock)."""
    return int((then.replace(second=0, microsecond=0) - now.replace(second=0, microsecond=0)).total_seconds() // 60)


def stamp_hit(tool: str, tool_input):
    """Return (matched, reason) when this send_message opens with a header stamp that is wrong for the clock, else
    None. Only the first non-blank line is read, and only its header stamp. Wrong means one of three things. The
    zone name is not the clock's own (local_time's DST rule names the current zone), whatever the minutes. A dated
    stamp is more than STAMP_LIMIT_MINUTES ahead, compared as an instant with its zone's offset, with no upper limit.
    An undated stamp is between STAMP_LIMIT_MINUTES (exclusive) and STAMP_QUOTE_MINUTES (inclusive) ahead, as a
    signed minute-of-day offset modulo 1440 in [-720, 720). An undated stamp further ahead is read as a quote from
    an earlier day and passes, as does any stamp behind the clock.
    The clock is local_time.clock(), and the reason's time comes from local_time.central_hhmm: one home of the
    clock and its DST rule. Cost: one clock read, no transcript, no file, no process. Fails open: the stamp is
    advice about a time, so a missing clock module or an impossible date lets the message through."""
    if tool != BRIEF_TOOL or not isinstance(tool_input, dict):
        return None
    message = tool_input.get("message")
    first = next((ln.strip() for ln in message.splitlines() if ln.strip()), "") if isinstance(message, str) else ""
    found = _STAMP_HEADER.match(first)
    if not found:
        return None
    try:
        import local_time
        now = local_time.clock().replace(second=0, microsecond=0)  # whole minutes: both forms compare one way
        clock_zone = local_time.central_hhmm(now).split()[1]
        stamp_zone = found.group("zone").upper()
        hour, minute = int(found.group("hour")), int(found.group("minute"))
        if hour > 23 or minute > 59:
            return None
        if stamp_zone != clock_zone:
            why = STAMP_ZONE_WHY.format(zone=stamp_zone, name=clock_zone)
        else:
            zone = timezone(timedelta(hours=_STAMP_OFFSET_HOURS[stamp_zone]))
            if found.group("date"):
                stamped = datetime.fromisoformat(found.group("date")).replace(hour=hour, minute=minute, tzinfo=zone)
                off = _minutes_ahead(stamped, now)
                late = off > STAMP_LIMIT_MINUTES
            else:
                there = now.astimezone(zone)
                off = (hour * 60 + minute - (there.hour * 60 + there.minute) + 720) % 1440 - 720
                late = STAMP_LIMIT_MINUTES < off <= STAMP_QUOTE_MINUTES
            if not late:
                return None
            why = STAMP_AHEAD_WHY.format(off=off)
        return "header stamp " + found.group(0).strip(), STAMP_REASON.format(why=why, now=local_time.central_hhmm(now))
    except (ImportError, ValueError, OverflowError):
        return None


# Written values: an ISO instant with an offset, in three places (rule message-time-matches-clock). The Bash scan
# reads the command as text, not as tokens: a quote-aware reader skips a literal inside a quoted string or after
# a lone apostrophe, which is where an incident's literal sat. It reads the key `updatedAt`, bare or quoted, with
# an optional `]` after it. Then `:`, `=` or jq's `|=`, then a single- or double-quoted value, closed by the
# same quote. It skips `==`, `!=` and `>`.
_ISO_INSTANT = r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})"
_ISO_FULL = re.compile(_ISO_INSTANT)
_UPDATED_AT = re.compile(r"""updatedAt\\?["']?\]?\s*(?:\|=|:|=(?!=))\s*\\?(["'])""" + _ISO_INSTANT + r"\\?\1")
# A str_replace of `added` may carry only the time part of the value, such as `T20:24:00Z`.
_TIME_FRAGMENT = re.compile(r"T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})")
_STEP_FILE = re.compile(r"(?:^|/)roadmap/data/steps/[^/]+\.json$")
WRITTEN_ITEMS = "items"  # the ArtifactData collection whose `added` is judged
WRITTEN_REASON = (
    "this written time ({what}) is {off} minutes ahead of the clock, and the limit is " + str(STAMP_LIMIT_MINUTES) + ". "
    "The time is {now}, which is {central} and {utc}: write that time, then run the call again. "
    "Read the time with `~/.claude/bin/now-central --iso`, never from memory. "
    "(decision local-time-central, sessions speak times in US Central)"
)


def _offset(zone):
    """The timezone of an ISO offset, `Z` or `[+-]HH[:]MM`. Raises ValueError for an impossible offset."""
    if zone == "Z":
        return timezone.utc
    digits = zone[1:].replace(":", "")
    return timezone(timedelta(hours=int(digits[:2]), minutes=int(digits[2:])) * (-1 if zone[0] == "-" else 1))


def _instant(found):
    """The aware datetime of an _ISO_INSTANT match, or None for an impossible date or offset."""
    year, month, day, hour, minute, zone = found.groups()
    try:
        return datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=_offset(zone))
    except ValueError:
        return None


def _fragment_ahead(found, now):
    """Minutes a _TIME_FRAGMENT match is ahead of `now`, or None for an impossible time or offset. The guard reads
    no page, so the date the fragment lands on is unknown. It takes the day that puts the time nearest the clock,
    a signed offset in [-720, 720) as an undated header stamp has. So a behind fragment passes, and yesterday's
    late time does not read as almost a day ahead after UTC midnight. It is not refused outright, because a value
    behind the clock passes."""
    hour, minute, zone = int(found.group(1)), int(found.group(2)), found.group(3)
    if hour > 23 or minute > 59:
        return None
    try:
        there = now.astimezone(_offset(zone))
    except ValueError:
        return None
    return (hour * 60 + minute - (there.hour * 60 + there.minute) + 720) % 1440 - 720


def _document_added(entry, cwd):
    """The `added` string of one ArtifactData write's document, or None. The document is the inline `data` (a dict,
    or a JSON string), else the local JSON file named by `file_path`, read against `cwd` when the path is relative:
    the one file read this rule costs, made only for a write to collection items with no inline data. A file that
    does not read or parse holds nothing to judge."""
    data = entry.get("data")
    path = entry.get("file_path")
    try:
        if data is None and isinstance(path, str) and path:
            with open(os.path.join(cwd, path) if cwd else path, encoding="utf-8") as handle:
                data = json.load(handle)
        elif isinstance(data, str):
            data = json.loads(data)
    except (OSError, ValueError):
        return None
    added = data.get("added") if isinstance(data, dict) else None
    return added.strip() if isinstance(added, str) else None


def _written_texts(tool: str, tool_input: dict, cwd: str = ""):
    """The text of each written value this call carries that holds an ISO instant or time fragment to judge: an
    `added` alone, each offset instant in a step edit's new text, or each literal `updatedAt` in a step's content
    or a command."""
    if tool == DATA_TOOL:
        action = tool_input.get("action")
        writes = [(w.get("op") or w.get("action"), w) for w in tool_input.get("writes") or [] if isinstance(w, dict)] \
            if action == "batch" else [(action, tool_input)]
        for op, entry in writes:
            if entry.get("collection") != WRITTEN_ITEMS:
                continue
            if op == "str_replace":  # the new text of the `added` field is the value the document ends with
                new = entry.get("new_str")
                added = new.strip() if entry.get("field") == "added" and isinstance(new, str) else None
            else:
                added = _document_added(entry, cwd) if op in ("set", "update") else None
            if added:
                yield "added " + added, added
        return
    if tool in WRITE_TOOLS:
        paths = [v.replace("\\", "/") for k in ("file_path", "path") if isinstance(v := tool_input.get(k), str)]
        if any(_STEP_FILE.search(p) for p in paths):
            content = tool_input.get("content")
            if isinstance(content, str) and "updatedAt" in content:
                for found in _UPDATED_AT.finditer(content):
                    yield found.group(0), found.group(0)
            # An edit can replace the value alone, with no key in its new text. Every time a step holds is past
            # by nature (createdAt, updatedAt), so each offset instant an edit writes is judged.
            news = [tool_input.get("new_string")]
            news += [e.get("new_string") for e in tool_input.get("edits") or [] if isinstance(e, dict)]
            for new in news:
                if isinstance(new, str):
                    for found in _ISO_FULL.finditer(new):
                        yield found.group(0), found.group(0)
        return
    command = tool_input.get("command")
    if tool in SHELL_TOOLS and isinstance(command, str) and "updatedAt" in command:
        # Only the last literal is judged: the new value comes last in `s/old/new/`, `.replace(old, new)` and an
        # assignment, so a repair that rewrites an ahead value to the right time passes.
        last = None
        for last in _UPDATED_AT.finditer(command):
            pass
        if last:
            yield last.group(0), last.group(0)


def written_time_hit(tool: str, tool_input, cwd: str = ""):
    """Return (matched, reason) when a written ISO instant is more than STAMP_LIMIT_MINUTES ahead of the clock,
    else None. A value behind the clock passes: a kept old value is always behind. Judged: `added` in an
    ArtifactData set, update or batch write to collection items (the document inline or through `file_path`), and
    the new text of a str_replace on `added`, a whole instant or a time fragment such as `T20:24:00Z`. In a
    roadmap/data/steps/<name>.json file: `updatedAt` in a Write, and each instant in an Edit's or MultiEdit's new
    text. In a shell command: the last literal `updatedAt` key with a single- or double-quoted value. Only a value
    with an offset is read. Cost: one clock read, and only when a judged value is present; one local file read,
    only for an items write that carries `file_path` and no inline data; no transcript or process. Fails open, like stamp_hit."""
    if not isinstance(tool_input, dict):
        return None
    judged = []
    for what, text in _written_texts(tool, tool_input, cwd):
        found = _ISO_FULL.search(text)
        if found:
            then = _instant(found)
            if then:
                judged.append((what, then))
        elif fragment := _TIME_FRAGMENT.fullmatch(text):
            judged.append((what, fragment))
    if not judged:
        return None
    try:
        import local_time
        now = local_time.clock().replace(second=0, microsecond=0)
        for what, then in judged:
            off = _minutes_ahead(then, now) if isinstance(then, datetime) else _fragment_ahead(then, now)
            if off is not None and off > STAMP_LIMIT_MINUTES:
                return what, WRITTEN_REASON.format(
                    what=what, off=off, now=local_time.central_hhmm(now), central=local_time.central_iso(now, seconds=False),
                    utc=now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
    except (ImportError, ValueError, OverflowError):
        return None

# ------------------------------------------------------------------ hook-bypass
#
# A git commit, merge or push that points git's hooks elsewhere or skips them. Read off the parsed tokens
# of a segment whose COMMAND WORD is git, so a quoted mention, a commit message value and a heredoc body
# are never read. The forms: `-c core.hooksPath=...` before the verb, `--no-verify` on commit, merge or
# push, `-n` on commit alone (on push it is --dry-run, on merge --no-stat), the key set in the environment
# through GIT_CONFIG_KEY_<n> or GIT_CONFIG_PARAMETERS, and a `git config` write of the key followed by a
# commit, merge or push anywhere later in the command. A shell, `eval`, `env -S` or runner text is read by
# the same walk (inner_commands); words an `echo` pipes to `xargs git` count as the call's last words. The
# key is read without case, as git reads it. Known limits: `--config-env`, and an environment set in one
# segment and used in another. hooks/mutate_shared.py sets the key inside Python, which no segment shows.
HOOK_BYPASS_REASON = (
    "Rule (Git): {what}. Git hooks are the checks that run before a commit, merge or push lands, and a "
    "call that points them elsewhere lets a defect through unseen. "
    "Remedy: run the {verb} with the repo's own hooks on. If a hook fails wrongly, fix the hook, or "
    "report the hook to the owner. "
    "(decision commit-hook-bypass-refused, a hook skip or redirect is refused)"
)
_HOOKS_KEY = "core.hookspath"
_HOOK_VERBS = ("commit", "merge", "push")
_HOOK_VALUE_LETTERS = {"commit": _COMMIT_VALUE_LETTERS, "merge": "mFsX", "push": "o"}   # short flags that take a value
_HOOK_VALUE_FLAGS = {
    "commit": _COMMIT_VALUE_FLAGS,
    "merge": {"--strategy", "--strategy-option", "--message", "--file", "--into-name"},
    "push": {"--repo", "--receive-pack", "--exec", "--push-option"},
}
_HOOKS_PARAMETER = re.compile(r"(?:^|['\s])core\.hookspath(?:['=\s]|$)", re.IGNORECASE)
_CONFIG_READ_FLAGS = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--unset", "--unset-all", "--list", "-l",
                      "--edit", "-e", "--remove-section", "--rename-section"}
_CONFIG_VALUE_FLAGS = {"-f", "--file", "--blob", "--type", "--default", "-t"}


def _env_hooks_path(assignments) -> bool:
    """True when the `NAME=value` words name core.hooksPath through GIT_CONFIG_PARAMETERS or a
    GIT_CONFIG_KEY_n whose value is that key."""
    for word in assignments:
        name, _, value = word.partition("=")
        if name == "GIT_CONFIG_PARAMETERS" and _HOOKS_PARAMETER.search(value):
            return True
        if name.startswith("GIT_CONFIG_KEY_") and value.lower() == _HOOKS_KEY:
            return True
    return False


def _verb_bypass_flag(verb: str, args) -> str:
    """The flag in a commit, merge or push argument list that skips the hooks, else ''. A flag's value
    is skipped, so `-m "-n"` and `-mn` name a message; `--` ends the flags."""
    letters, value_flags = _HOOK_VALUE_LETTERS[verb], _HOOK_VALUE_FLAGS[verb]
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "--":
            return ""
        if arg.startswith("--"):
            if arg.split("=", 1)[0] in value_flags:
                skip = "=" not in arg
            elif len(arg.split("=", 1)[0]) >= len("--no-v") and "--no-verify".startswith(arg.split("=", 1)[0]):
                return "--no-verify"
            continue
        if arg.startswith("-") and len(arg) > 1:
            for at, letter in enumerate(arg[1:], 1):
                if letter in letters or letter in "uS":   # the rest of the cluster is the value
                    skip = letter in letters and at == len(arg) - 1
                    break
                if letter == "n" and verb == "commit":
                    return "-n"
    return ""


def _config_writes_hooks_path(args) -> bool:
    """True when the arguments of `git config` set core.hooksPath: the key is the first word that is no flag
    and no flag's value, and a value word follows it. A read, `--get`, `--unset` and a list write nothing."""
    words, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in _CONFIG_READ_FLAGS:
            return False
        elif arg in _CONFIG_VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            words.append(arg)
    if words[:1] == ["set"]:   # `git config set <key> <value>`
        words = words[1:]
    return len(words) >= 2 and words[0].lower() == _HOOKS_KEY


def _fed_words(tokens, index: int, fed: str):
    """The words an `echo` or `printf` in the pipe's previous segment hands `xargs`, when the git word at
    `index` runs under xargs: xargs puts them after the call's own words. Else []."""
    if not fed or not any(basename(word) == "xargs" for word in tokens[:index]):
        return []
    feeder = segment_tokens(fed)
    at = resolve_command(feeder) if feeder else None
    if at is None or basename(feeder[at]) not in ("echo", "printf"):
        return []
    return [word for word in feeder[at + 1:] if word not in ("-n", "-e", "-E")]


def _segment_events(segment: str, fed: str = ""):
    """The hook-relevant act of one segment whose command word is git, as a tuple: ("bypass", matched, verb,
    what), ("config", matched) for a core.hooksPath write, ("run", verb) for a commit, merge or push that
    skips nothing, else (). A segment shlex cannot parse judges nothing (the fail-open stance)."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ()
    index = resolve_command(tokens)
    if index is None or basename(tokens[index]) not in ("git", "git.exe"):
        return ()
    cursor = _git_subcommand_index(tokens, index)
    if cursor >= len(tokens):
        return ()
    verb = tokens[cursor]
    if verb == "config":
        if _config_writes_hooks_path(tokens[cursor + 1:]):
            return ("config", " ".join(tokens[index:cursor + 1]) + " " + _HOOKS_KEY)
        return ()
    if verb not in _HOOK_VERBS:
        return ()
    matched = " ".join(tokens[index:cursor + 1])
    options = tokens[index + 1:cursor]
    for at, word in enumerate(options):
        if word == "-c" and at + 1 < len(options) and options[at + 1].partition("=")[0].lower() == _HOOKS_KEY:
            return ("bypass", matched, verb, "this " + verb + " points git's hooks at another folder (core.hooksPath on the command)")
    if _env_hooks_path(tokens[:index]):
        return ("bypass", matched, verb, "this " + verb + " points git's hooks at another folder (core.hooksPath in the environment)")
    flag = _verb_bypass_flag(verb, tokens[cursor + 1:] + _fed_words(tokens, index, fed))
    if flag:
        return ("bypass", matched + " " + flag, verb, "this " + verb + " skips the git hooks (" + flag + ")")
    return ("run", verb)


def _hook_events(text: str):
    """The events of a command text in order: each segment's own, then the texts it hands on (`bash -c`, `sh -lc`,
    `eval`, `env -S`, runners: inner_commands is the one reader), each judged as a command with its heredoc
    bodies dropped and its `$( )` texts as commands of their own."""
    ends = []
    segments = split_segments(text, ends)
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        fed = segments[number - 1] if number and number - 1 < len(ends) and ends[number - 1] == "|" else ""
        event = _segment_events(segment, fed)
        if event:
            yield event
        tokens = segment_tokens(segment)
        if tokens:
            from guard_env import substitution_commands   # imported late: a family reads only the families before it
            for inner in inner_commands(tokens):
                stripped = strip_heredoc_bodies(inner)
                for each in (stripped, *substitution_commands(inner, stripped)):
                    yield from _hook_events(each)


def hook_bypass_hit(texts):
    """Return (matched text, verb, what) for the first call in `texts` (the command and its `$( )` texts) that
    skips or redirects the git hooks, else None. A `git config` write of core.hooksPath counts when a commit,
    merge or push runs after it, anywhere later in the command. A lone write is allowed on purpose: setting a
    repo's own hooks path is a normal setup step. A later commit in another call passes, a known limit
    (decision commit-hook-bypass-refused)."""
    for text in texts:
        written = ""
        for event in _hook_events(text):
            if event[0] == "bypass":
                return event[1], event[2], event[3]
            if event[0] == "config":
                written = event[1]
            elif written:
                return written, event[1], "this " + event[1] + " runs after core.hooksPath is written, so git's hooks point at another folder"
    return None


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
