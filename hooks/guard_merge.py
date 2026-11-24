"""The guard's merge family: a merge made outside the merge tool, and the git and gh call readers.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import contextlib
import fnmatch
import importlib
import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from guard_core import (
    COMPLY_TAIL, SHELL_TOOLS, WRITE_TOOLS, _absolute, ASSIGNMENT, GIT_WRITES, _git, _git_subcommand_index, _segment_git_c_target, basename, cap_safe, command_root, GIT_WORK_TREE_RE,
    REPLAY_MARKS, command_indexes, dir_before_segment, heredoc_heads, inline_script, inner_commands, own_heredoc_bodies, resolve_command, resolve_default_base, segment_tokens, split_segments,
    is_cloud, lint_dir, shell_abs, strip_heredoc_bodies, strip_redirections,
)
import own_session  # the one home of the own get_session read, small so report_guard imports it too
from required_check import REQUIRED_CHECK  # the one home of the rollup job's name
from shared_names import opens_fence, BUILD_TAG, CONSULTANT_TAG, CREATE_SESSION_TOOL, DATA_TOOL, LANE_BRIEF_MARKER, LANE_GRANT_MARKER, LANE_TAG, REPO_TAG, STEP_TAG, TOPIC_TAG, grant_line_holds_words, is_lane_create_session, lane_head_refs, lane_tags, repo_tag_names  # the one home of the lane tags and head refs, shared with the roadmap build
from guard_pointer import (
    pointer_checkout,
)
from guard_push_delete import (
    ARCHIVE_COPY_SUFFIX, ARCHIVE_PREFIX, DEFAULT_BRANCH_FALLBACK, push_calls, push_destinations, push_is_plain, push_refspecs,
    push_target,
)


# ------------------------------------------------------------------ three git acts
#
# Each clause below judges the ACT a segment performs, read off its command word (decisions/
# predicate-is-the-act.md), never a substring of the text. `echo git commit`, a `git log`, a
# quoted message and a heredoc body name an act and perform none.
#
# 1. merge-checks: a merge made outside the merge tool is
#    refused while the head has a check or a workflow run pending or red, or when that read could not run, or while another ready PR on the
#    base has CI running and its head does not hold this one (`Host.batch_running`).
#    The merge tool (merge/merge.py) runs its own `gh pr merge` as a subprocess, so no hook
#    sees it; it has already read the head green. The read below is the tool's own `Host.head_read`, one home.
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
# The two auto-merge tools arm the same merge: GitHub merges once the head's checks pass, so each is judged on the same head read.
# The desktop app's switch names its pull request by URL and carries `enabled`; turning it off merges nothing.
APP_AUTO_MERGE_TOOL = "mcp__ccd_pr__set_auto_merge"
MERGE_TOOLS = ("mcp__github__merge_pull_request", "mcp__github__enable_pr_auto_merge", APP_AUTO_MERGE_TOOL)
APP_PR_URL_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)", re.I)


def merge_tool_merges(tool: str, tool_input: dict) -> bool:
    """False for the app's auto-merge switch turned off, which merges nothing. Any other value of `enabled`, or none, is judged."""
    return not (tool == APP_AUTO_MERGE_TOOL and tool_input.get("enabled") is False)


def merge_tool_target(tool: str, tool_input: dict):
    """The (number, repo) a MERGE_TOOLS call names, or None for the app's switch whose url names no github.com pull
    request. The caller refuses None: reading the checkout's own branch pull request instead could allow another one.
    A host tool call with no number gives ("", repo), which `merge_check` reads from the checkout."""
    if tool == APP_AUTO_MERGE_TOOL:
        url = tool_input.get("url")
        found = APP_PR_URL_RE.match(url.strip()) if isinstance(url, str) else None
        return (found.group(3), found.group(1) + "/" + found.group(2)) if found else None
    owner, name, number = (tool_input.get(k) for k in ("owner", "repo", "pullNumber"))
    repo = owner + "/" + name if isinstance(owner, str) and isinstance(name, str) else ""
    return "" if number is None else str(number), repo


MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                     "--match-head-commit", "-A", "--author-email"}
# Seconds for the WHOLE read, shared: Host.head_read makes 4 `gh` REST calls (5 with a branch selector, 1 more run-list read when the check runs link more than one run; a settled head adds the
# protection read, none with a pinned list) that split this one
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
    """Return (verdict, detail) for the head of the named pull request: green, pending, red, or unknown. One read, no
    wait, run in `where` so `gh` names the repo the command names."""
    module = merge_module()
    if module is None:
        return "unknown", "the merge tool's check reader could not be loaded"
    where = os.path.normpath(where) if where else ""   # a `cd` target may carry either separator
    host = module.Host(required=pinned_required(where) or "protection", repo=repo or None, cwd=where or None)
    # No ignore list: this head counts every check, so an ignored red check on it still refuses.
    # The other ready pull requests on the base may not have CI running (decision no-merge-during-batch-ci), but an ignored check or run never counts.
    try:
        host.batch_brake = ignored_checks(module, where)
    except module.Stop as e:
        return "unknown", str(e)
    return host.head_read(selector, nothing_is_green=not has_workflows(where))


MERGE_CHECK_REASON = (
    "Rule (Git): this head is not settled: %s. A merge waits for every check and workflow run on "
    "the head, required or not, and a read that could not run counts as not settled. "
    "It also waits while another ready pull request on the base has CI running, unless that head holds this one "
    "(decision no-merge-during-batch-ci). "
    "Remedy: run the merge tool, `merge <pr> --confirm`, which waits on the required checks, then "
    "merges the head it waited on."
)


def merge_check_reason(verdict: str, detail: str) -> str:
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
    """The repo's pinned `merge.requiredChecks`: the string "none", or a non-empty list of names; else None,
    and the batch read takes the names from the branch protection. "none" is the merge tool's value for a repo
    that requires no check (decision private-repos-no-ci), so a head with no check and no run reads green here too."""
    for config in _merge_configs(where) if where else ():
        merge = config["merge"]
        names = merge.get("requiredChecks") if isinstance(merge, dict) else None
        if names == "none":
            return names
        if isinstance(names, list) and names and all(isinstance(k, str) and k for k in names):
            return names
    return None


def ignored_checks(module, where: str):
    """The repo's `merge.ignoreChecks` as {name: reason}: the checks and runs another ready pull request may have
    running without holding a merge. {} with no such list. A bad entry raises the merge tool's Stop."""
    for config in _merge_configs(where) if where else ():
        merge = config["merge"]
        if isinstance(merge, dict) and "ignoreChecks" in merge:
            return module.ignore_checks(config)
    return {}


BARE_MERGE_REASON = (
    "Rule (Git): this repo merges with the merge tool, and a bare merge skips its claim and "
    "leaves the local main behind origin "
    "(decision bare-merge-asks, decision guard-remedy-not-to-owner). "
    "Remedy: run the merge tool, `merge <pr> --confirm`. "
    + COMPLY_TAIL
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
# process outlives the call. One call's ready reads (the page read, the worktree's removal and the head read of rule
# ready-mcp-mark-guard) share READY_HOOK_BUDGET, counted from the first read, so a passing call ends well under the hook's 60 s
# timeout, which a guard that runs past lets the call through. A page read gets at most READY_PAGE_TIMEOUT of it and keeps
# READY_PAGE_CLEANUP_SECONDS back for the removal. A read that cannot run, or runs out of time, refuses as unknown (decision guard-hooks-fail-closed).
READY_PAGE_TIMEOUT = 40
READY_PAGE_CLEANUP_SECONDS = 10  # merge.py's own removal budget (READY_PAGE_CLEANUP_SECONDS there), kept back here
READY_HOOK_BUDGET = 50
_READY_START = []  # the monotonic time of the first ready read in this hook process: one call per process


def ready_budget_left() -> float:
    """Seconds left of READY_HOOK_BUDGET. The clock starts at the first call."""
    if not _READY_START:
        _READY_START.append(time.monotonic())
    return READY_HOOK_BUDGET - (time.monotonic() - _READY_START[0])
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

READY_PAGE_BEHIND_REASON = (
    "Rule (Git, guard-hooks-fail-closed): the records page on the head of this pull request could not be read, so it is "
    "unknown whether it is stale: %s. The merge tool the guard loaded is behind origin/main, and a tool that old can "
    "fail this read. A read that cannot run refuses the ready mark. "
    "Remedy: from the claude-settings clone, run merge/install_from_main.sh (the reinstall from main), then retry. "
    "(decision guard-hooks-fail-closed, a guard that cannot run its read refuses)"
)


def merge_tool_behind_main() -> bool:
    """True when the checkout that holds the loaded merge tool is behind origin/main (its HEAD is an ancestor of
    origin/main and not equal to it). Any read that fails is False: the plain unknown reason then stands."""
    module = merge_module()
    path = getattr(module, "__file__", None)
    if not path:
        return False
    root = os.path.dirname(os.path.dirname(os.path.realpath(path)))
    ref = resolve_default_base(root) or "origin/main"  # the short ref name already holds the remote
    if not ref.startswith("origin/"):
        return False
    head, tip = _git(root, "rev-parse", "HEAD"), _git(root, "rev-parse", ref)
    if not head or not tip or head.returncode or tip.returncode or head.stdout.strip() == tip.stdout.strip():
        return False
    ancestor = _git(root, "merge-base", "--is-ancestor", "HEAD", ref)
    return ancestor is not None and ancestor.returncode == 0


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
    seconds = min(READY_PAGE_TIMEOUT, ready_budget_left() - READY_PAGE_CLEANUP_SECONDS)
    if seconds < 1:
        return "unknown", "the call's read budget of %d s ran out" % READY_HOOK_BUDGET
    try:
        with module.shared_deadline(seconds):
            host = module.Host(repo=repo or None, cwd=where)
            number = host.pr_number(selector)
            state = module.ready_page_state(where, number, host)
    except subprocess.TimeoutExpired:  # its text names the resolved program path
        return "unknown", "a read timed out after %d s" % seconds
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
            reason = READY_PAGE_BEHIND_REASON if merge_tool_behind_main() else READY_PAGE_UNKNOWN_REASON
            return reason % cap_safe(detail, 200), "ready, page read unknown"
    return None



# ---- a push to the branch of a ready pull request (rule ready-pr-push): one CI run per pull request, never restarted by a push
# A push cancels the ready pull request's running CI run (checks.yml cancels in progress), and the run is the one the merge
# reads. The push is refused while that run is running, queued or green. Allowed: a draft, no pull request for the branch, a
# run with a red job (the push may fix it), a push to another branch, an archive push, a repo with no CI run to cancel, and a
# push whose pull request read fails (a destination git cannot name is read the same way: the list read still runs, and
# matches no branch): one stderr line, never a refusal, since a refusal on a failed read would block every push while GitHub
# is out of reach. The merge tool's own pushes run as subprocesses no hook sees; a segment that runs the tool is skipped.
# Cost: only a call that holds a `git push` reads GitHub, and only in a repo that uses the merge tool. Per such
# push: one open-pull-request list read (a draft, no pull request or another branch ends there), and, when a ready pull request
# holds the branch, one read of its head's check runs. Two gh calls at most, one deadline each. No other tool call reads anything.
READY_PUSH_RED = ("failure", "timed_out", "startup_failure")  # a check run conclusion that is a red job; cancelled and skipped are not
READY_PUSH_LIST_SECONDS = 10  # the list read's share of the hook's budget; head_read keeps its own MERGE_READ_TIMEOUT
READY_PUSH_REASON = (
    "Rule (Git, one CI run per pull request): this push goes to the branch of #%s, a ready pull request whose CI run is %s. "
    "A push cancels that run, and the merge needs the run to finish on this head. "
    "Remedy: wait for the run to finish. To push before then, return the pull request to draft with `gh pr ready --undo %s`, "
    "push, and mark it ready again with the merge tool. When the run has a red job, a push may go ahead and fix it. "
    "(decision standing-merge-grant, a ready pull request takes no push; owner ruling 13:05 CST Nov 23, 2026) "
    + COMPLY_TAIL
)
READY_PUSH_WARNING = "ready-pr-push: the pull request list read failed (%s), so the push is allowed unchecked (decision standing-merge-grant)"


def _ready_push_branches(args, where: str, overrides):
    """(names, archive_only): the branches this `git push` writes, an unreadable one left out, and whether every destination
    is an archive name. An archive-only push can hold no ready pull request, so it reads nothing."""
    found = push_destinations(args, where, overrides)
    names = [name for name in found if name and not name.startswith(ARCHIVE_PREFIX)]
    return names, bool(found) and all(name and name.startswith(ARCHIVE_PREFIX) for name in found)


def ready_push_hit(stripped: str, cwd: str, read_verb):
    """None, or ("deny", reason, matched) for a push to the branch of a ready pull request whose run is running, queued or
    green, or ("warn", line, "") when the pull request read failed and the push passes. `read_verb(subcommand, args)` is
    guard.py's test for a dry run, which writes nothing. One list read serves every push of the call."""
    pulls = {}  # where -> (host, open pull requests) or the failure text: one read per folder
    warning = None
    for segment in split_segments(stripped):
        if merge_tool_args(segment) is not None:
            continue
        for args, where, overrides in _push_calls(segment, stripped, cwd):
            if not where or read_verb("push", args) or not uses_merge_tool(where):
                continue
            branches, archive_only = _ready_push_branches(args, where, overrides)
            if archive_only or pinned_required(where) == "none":  # a repo that runs no CI has no run to cancel
                continue
            if where not in pulls:
                pulls[where] = _ready_push_pulls(where)
            host, rows = pulls[where]
            if host is None:
                if warning is None:
                    warning = ("warn", READY_PUSH_WARNING % cap_safe(rows, 120), "")
                continue
            for number, info in rows:
                same_repo = info["head_repo"] in (None, info["base_repo"])
                if info["branch"] in branches and not info["draft"] and same_repo:
                    verdict, detail = _ready_push_run(host, number, info["head"])
                    if verdict == "unknown":
                        if warning is None:
                            warning = ("warn", READY_PUSH_WARNING % cap_safe(detail, 120), "")
                    elif verdict != "red":
                        state = "running or queued" if verdict == "pending" else "finished green"
                        return "deny", READY_PUSH_REASON % (number, state, number), "push to ready #%d" % number
    return warning


def _ready_push_pulls(where: str):
    """(host, [(number, pull request fields)]) of the open pull requests, or (None, why) when the read cannot run."""
    module = merge_module()
    if module is None:
        return None, "the merge tool could not be loaded"
    try:
        with module.shared_deadline(READY_PUSH_LIST_SECONDS):
            host = module.Host(required=pinned_required(where) or "protection", cwd=os.path.normpath(where))
            return host, host.open_prs()
    except subprocess.TimeoutExpired:  # its text names the resolved program path
        return None, "a read timed out after %d s" % READY_PUSH_LIST_SECONDS
    except Exception as e:  # a Stop, a missing gh, malformed JSON: all unread
        return None, " ".join(str(e).split()) or type(e).__name__


def _ready_push_run_id(row):
    """The workflow run id in a check row's job link (`/actions/runs/<id>/job/<id>`), or None when the row has no such link."""
    m = re.search(r"/actions/runs/(\d+)/", row.get("details_url") or row.get("html_url") or "")
    return m.group(1) if m else None


def _ready_push_run(host, number: int, head: str):
    """(verdict, detail) of the ready pull request's head, from one read of its check runs: "red" when a job failed or timed out
    in the run that carries the rollup job (any run, when none carries it; the push may fix it, even while the run goes on), "pending" for any other state, including no job reported yet, and
    "unknown" with the cause when the read cannot run."""
    try:
        with merge_module().shared_deadline(MERGE_READ_TIMEOUT):
            rows = host.pages(f"commits/{head}/check-runs", "check_runs")
    except subprocess.TimeoutExpired:  # its text names the resolved program path
        return "unknown", "a read timed out after %d s" % MERGE_READ_TIMEOUT
    except Exception as e:  # a Stop, a missing gh, malformed JSON: all unread
        return "unknown", " ".join(str(e).split()) or type(e).__name__
    gating = {_ready_push_run_id(r) for r in rows if r.get("name") == REQUIRED_CHECK}  # the run that carries the rollup job
    counted = [r for r in rows if _ready_push_run_id(r) in gating] if gating else rows  # another run's red row, or a row with no run link, is not the gating run's
    if any(r.get("status") == "completed" and r.get("conclusion") in READY_PUSH_RED for r in counted):
        return "red", ""
    done = rows and all(r.get("status") == "completed" for r in rows)
    return ("green" if done else "pending"), ""


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
        elif arg.startswith("--") or arg.startswith("<<"):   # a heredoc header (`-F - <<EOF`) is no pathspec
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
# red-run (decision red-run-trailer-on-test-commits) rides the same push check: after the marker read finds
# nothing, `check_red_run.gaps` reads the accepted base up to the source in one `git log --no-merges
# --numstat -z`, so a push costs one more `git log`, and nothing else when no commit is a gap. A push that
# carries a gap costs more: the rollout's `git ls-tree` (the source, then each flagged commit's parent), the
# default base's reads (once, in `memo`), and a second `git log` without the default base's commits, which a
# merge or a rebase brings in and which are not the lane's, then one `git rev-parse` of the source, and one
# `git merge-base --is-ancestor` (one `git rev-parse --is-shallow-repository` more when it says no). The
# guard passes its own `is_test_rel`, so the lazy import of check_red_run loads no second guard. A commit in the same call as the push lands after the
# guard reads: its `-m` paragraphs are read as its message (an `--amend` with none keeps the commit's own),
# and the test lines it stages are read the way the marker read reads its tree (`_commit_test_adds`: one
# `git diff --numstat`, and one `git ls-files --others` for each add that names paths). Only a commit with a
# push after it costs that read. A message the guard cannot read (`-F`, `-C`, `-c`, an editor) makes the whole
# push a no-hit, except an `-m "$(cat <<'EOF' ...)"` message and an `-F - <<'EOF'` message, which are read from their heredoc body. A failed
# read, a copy of the hooks with no lint folder beside it, and a default base that cannot be read are no hit.
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
CONFLICT_MARKERS_CD_REASON = (
    "Rule (Git, conflict-markers; decision commit-refuses-conflict-markers, decision refuse-git-after-missing-cd; "
    "ruling own-476-c-refuse-cd-missing-folder): "
    "the cd before this git write names a folder that does not exist, so the cd failed and the shell stays in the "
    "current folder. The write would land in the current folder's repository, which is not the one you named. "
    "Remedy: check the folder path, or join the cd to the git command with `&&`, then retry."
)
RED_RUN_PUSH_REASON = (
    "Rule (Git, red-run; decision red-run-trailer-on-test-commits): this push would send test commits with no "
    "valid Red-run trailer: {flagged}. Remedy: {fix}"
)
# A flagged commit that is not the tip: a trailer-only commit named `amend! <sha>` carries the new message, and
# the autosquash rebase folds it into that commit. No editor opens (`fixup -C`, and `merge -C` for a merge), so a
# session can drive it. `--rebase-merges` keeps a merge in the range: without it the rebase flattens the merge
# and replays main's commits under new shas, which the check then judges as the lane's. The sha is the one the
# refusal lists for the flagged commit. The editors are set by `-c`, and the parent is `<sha>~1`, so the same
# text runs in bash, PowerShell and cmd.exe: `NAME=value git` is bash only, and a trailing caret joins lines in cmd.exe.
RED_RUN_BELOW_FIX = (
    "Reword each flagged commit by its sha, listed above: `git commit --allow-empty -m \"amend! <sha>\" "
    "-m \"<subject>\" -m \"Red-run: ...\"`, then `git -c sequence.editor=true -c core.editor=false rebase -i "
    "--autosquash --rebase-merges <sha>~1`, then `git push`."
)
# A branch rewritten since it was pushed: the remote holds an earlier form of the flagged commits, so a reword
# changes pushed history, which no session does.
RED_RUN_PUSHED_FIX = (
    "These commits were pushed before, and the branch has been rewritten since, so a reword would rewrite "
    "pushed history. This needs the owner: ask the owner to reword them."
)
# A lone commit that has not landed: nothing is pushed or amended yet, so the fix is the same commit with the trailer.
RED_RUN_COMMIT_REASON = (
    "Rule (Git, red-run; decision red-run-trailer-on-test-commits): this commit adds lines to {paths} and its -m "
    "message holds no valid Red-run trailer. Remedy: {form} Re-run the commit with the trailer in -m."
)
RED_RUN_SHOWN = 3   # flagged commits a red-run refusal lists, the rest counted
OCTOPUS_PUSH_REASON = (
    "Rule (Git, octopus-push; decision octopus-push-refused): this push would send {sha}, a merge commit of more than two parents. "
    "Remedy: redo that merge as a chain of two-parent merges, then retry the push."
)
OCTOPUS_PUSH_STALE = (" The remote's tracking refs could not be refreshed, so a merge the remote already holds may show as new."
                      " Run `git fetch <remote>` and push again. If that merge is still listed, redo it as two-parent merges.")
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
    """(finished `git diff --check <base>...<source>`, source, base) for the first base that git accepts, else
    (None, source, ''). The three dots make git find the merge base itself, so no ref is read first. The
    bases are the destination's remote-tracking ref, the source's upstream, then the default base (read
    once per push, in `memo`). Only a rejected base costs more. After the first rejection the source is
    read once: one that does not resolve is read as HEAD, and the same base is tried again.
    `--check` exits 2 on a finding. The red-run check reads the same base, so it resolves none of its own."""
    verified = source == "HEAD"
    step = 0
    while step < 3:
        if step == 2 and "default" not in memo:
            memo["default"] = resolve_default_base(where) or ""
        base = (tracking, source + "@{upstream}", memo.get("default"))[step]
        if base:
            done = _diff_check(where, [base + "..." + source, "--"])
            if done is None:
                return None, source, ""
            if done.returncode in (0, 2):
                return done, source, base
            if not verified:
                verified = True
                if not _ref_sha(where, source):
                    source = "HEAD"
                    continue
        step += 1
    return None, source, ""


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


def _red_run_module():
    """lint/check_red_run.py, imported from the lint folder beside this file's folder, the one home of the
    rule. It waits for the first push that needs it, and raises ImportError in a copy of the hooks with no lint
    folder beside it. The caller reads that as no hit."""
    lint = lint_dir()
    if lint not in sys.path:
        sys.path.append(lint)
    import check_red_run
    return check_red_run


def _red_run_present():
    """True when check_red_run imports, the same gate `_red_run_found` uses for a copy with no lint folder."""
    try:
        _red_run_module()
    except ImportError:
        return False
    return True


def _red_run_found(where, source, base, memo, is_test_rel, virtual):
    """`(found, last)` from check_red_run.judge for the commits a push of `source` sends from `base` (the one the
    conflict check accepted), else `([], '')`. `virtual` holds the commits of the same call that have not landed.
    A push that carries a gap is read again without the commits the default base holds, which are not the
    lane's: a merge or a rebase brings them in. The default base is read only then, once per push in `memo`. A
    default base that cannot be read is no hit, for the push would judge main's commits. So is a failed read in
    either pass, a message the guard cannot read, and a copy of the hooks with no check_red_run beside it."""
    if is_test_rel is None or virtual["unreadable"]:
        return [], ""
    try:
        check_red_run = _red_run_module()
    except ImportError:
        return [], ""
    extra = {"is_test_rel": is_test_rel, "tip": virtual["tip"], "pending": virtual["pending"]}
    try:
        found, last = check_red_run.judge(where, base, source, **extra)
        if found:
            if "default" not in memo:
                memo["default"] = resolve_default_base(where) or ""
            default = memo["default"]
            if not default:
                return [], ""
            if default != base.removeprefix("refs/remotes/"):
                found, last = check_red_run.judge(where, base, source, default, **extra)
    except (check_red_run.Unknown, OSError):
        return [], ""
    return found, last


def red_run_reason(matched, commit=False):
    """`(reason, shown)` for a red-run hit `(found, tip, rewritten)`: the refusal text, and the first flagged commit
    for the log. A lone commit's hit (`commit`) prints the first line of `REMEDY` and RED_RUN_COMMIT_REASON's
    re-run with the trailer in `-m`, and no amend: the commit has not landed. `tip` is the pushed source's own short sha, or `new` for a commit of the same call. The remedy is
    the first two lines of check_red_run's own (`REMEDY`); the third names a branch switch, which a refusal never
    names. A flagged commit that is not the tip (a commit under a merge at the tip included) prints the trailer line
    of `REMEDY` and RED_RUN_BELOW_FIX in place of the amend, which reaches only the tip. A rewritten branch
    (`rewritten`) prints RED_RUN_PUSHED_FIX alone: no command rewrites pushed history."""
    try:
        found, tip, rewritten = matched
        found = [tuple(row) for row in found]
        if not found or any(len(row) != 3 for row in found):
            raise ValueError("not a red-run hit")
    except (TypeError, ValueError):
        # conflict_markers_hit never builds this shape; the deny check still answers, with the remedy and no rows.
        found, tip, rewritten = [], "", False
    check_red_run = _red_run_module()
    rows = ["%s %s: adds lines to %s" % row for row in found[:RED_RUN_SHOWN]] or ["a pushed test commit"]
    more = " and %d more" % (len(found) - RED_RUN_SHOWN) if len(found) > RED_RUN_SHOWN else ""
    lines = [line.removeprefix("check_red_run: ")[:1].upper() + line.removeprefix("check_red_run: ")[1:]
             for line in check_red_run.REMEDY[:2]]
    if commit and found:
        return RED_RUN_COMMIT_REASON.format(paths=cap_safe(found[0][2], 300), form=lines[0]), cap_safe(rows[0], 120)
    below = any(row[0] not in (tip, "new") for row in found)
    fix = RED_RUN_PUSHED_FIX if rewritten else " ".join(lines[:1] + [RED_RUN_BELOW_FIX] if below else lines)
    return RED_RUN_PUSH_REASON.format(flagged=cap_safe("; ".join(rows), 600) + more, fix=fix), cap_safe(rows[0], 120)


def _rewritten(where, tracking, base, source):
    """True when the range base is the destination's remote-tracking ref and `source` no longer holds it: the branch
    was rewritten after it was pushed, so its flagged commits are copies of pushed ones. An unknown answer (a failed
    read, or a shallow clone that cut the history) is False."""
    if not tracking or base != tracking:
        return False
    import git_reads  # branch_is_ancestor is the one home of the ancestry read and its shallow-clone unknown
    return git_reads.branch_is_ancestor(where, source, base) is False


def _push_hit(segment, stripped, cwd, args, is_test_rel=None, virtual=None):
    """Return `("push", file)` for the first file a `git push` would send with all three conflict markers,
    else `("red-run", (found, last, rewritten))` for the first ref that sends a test commit with no valid Red-run trailer
    (`_red_run_found`), else `("", "")`. For each ref the push names, the range is the merge base with the
    destination's remote-tracking tip, else the source's upstream, else the default base, up to the local
    source ref: in the usual case one `git diff --check`, with no read of the top folder, the source or a base
    first. The red-run check then adds one `git log` over the same base, and on a hit one `git rev-parse` of the
    source (the tip an amend reaches) and one `git merge-base --is-ancestor`, plus one shallow probe when that says
    no: a destination tracking ref the source no longer holds is a branch rewritten since its push."""
    virtual = virtual or {"tip": None, "pending": [], "unreadable": False}
    for where, source, _dest, tracking, _remote, memo in _push_refs(segment, stripped, cwd, args):
        done, source, base = _checked_range(where, source, tracking, memo)
        if done is None:
            continue
        name = _triplet_file(_kinds_of(done, where, source))
        if name:
            return "push", name
        found, last = _red_run_found(where, source, base, memo, is_test_rel, virtual)
        if found:
            # `last` is the newest non-merge commit, which a merge at the tip sits above; an amend reaches only the tip.
            tip = last if last == "new" else _ref_sha(where, source)[:7]
            return "red-run", (found, tip, _rewritten(where, tracking, base, source))
    return "", ""


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


def _octopus_in_range(where, source, refs):
    """The short sha of the first merge of more than two parents in `source` less `refs`, else ''. A failed read is ''."""
    done = _git(where, "rev-list", "--merges", "--parents", source, "--not", refs, "--")
    if done is None or done.returncode != 0:
        return ""
    for line in done.stdout.splitlines():
        fields = line.split()
        if len(fields) > 3:
            return fields[0][:12]
    return ""


def _octopus_hit(segment, stripped, cwd, args):
    """Return `(sha, stale)`: the short sha of the first merge of more than two parents that a `git push` would send,
    else `("", False)`. The range is what the push adds to the remote: the source ref, less every ref of the pushed
    remote, so an octopus that a remote ref already holds (a merge of origin/main brings one in) is not
    sent. A clone's tracking refs can lag the remote, and a lagging ref hides an octopus the remote holds. So on a
    hit, and only then, the tracking refs of a configured remote are refreshed once (`git_reads.fetch_remote`, once per
    directory and remote in the call) and the range is read again; the refusal stands only when the hit survives. A
    refresh that fails or times out keeps the refusal, with `stale` True so the reason says so. A destination named
    like the default branch is skipped before any read: push-main asks about that push, and a deny from here would
    win over the ask. One `git rev-list` for each ref, one `git config` more for a remote named by a URL or a path
    (`_remote_refs`), and on a hit one `git fetch` of a plain remote name (a URL or a path has no tracking refs)."""
    refreshed = {}
    for where, source, _dest, _tracking, remote, _memo in _push_refs(
            segment, stripped, cwd, args, DEFAULT_BRANCH_FALLBACK):
        refs = _remote_refs(where, remote)
        sha = _octopus_in_range(where, source, refs)
        if not sha:
            continue
        if refs == "--remotes":
            return sha, False
        key = (where, remote)
        if key not in refreshed:
            import git_reads  # the one home of a git call and its timeout
            refreshed[key] = git_reads.fetch_remote(where, remote)
            sha = _octopus_in_range(where, source, refs)
            if not sha:
                continue
        return sha, not refreshed[key]
    return "", False


def octopus_push_hit(stripped: str, cwd: str, read_verb):
    """Return `(sha, stale)` as `_octopus_hit` does for the first merge of more than two parents that a `git push` in
    the command would send, else `("", False)`. Each segment is judged from its own command word. A push whose
    destination is unnamed reads its source's range all the same. `read_verb("push", args)` is true for a dry run,
    which sends nothing."""
    for segment in split_segments(stripped):
        call = git_call_of(segment) if segment.strip() else None
        if call is not None and call[0] == "push" and not read_verb("push", call[1]):
            sha, stale = _octopus_hit(segment, stripped, cwd, call[1])
            if sha:
                return sha, stale
    return "", False


def _untracked_names(where, specs):
    """The untracked, not-ignored files that `git add` would stage: all of them under the top folder when `specs`
    is None, else those the pathspecs name. At most _UNTRACKED_CAP, in git's order. A failed read gives none."""
    done = _git(where, "-c", "core.quotepath=off", "ls-files", "--others", "--exclude-standard", "-z",
                "--full-name", *(["--", *specs] if specs else []))
    if done is None or done.returncode != 0:
        return []
    return [n for n in done.stdout.split("\0") if n][:_UNTRACKED_CAP]


def _untracked_findings(where, top, specs):
    """Marker findings in the untracked files that `git add` would stage (`_untracked_names`).
    `git diff HEAD` skips an untracked file, so each is read against /dev/null."""
    found = {}
    for name in _untracked_names(where, specs):
        found.update(_marker_findings(top, top, ["--no-index", "--", "/dev/null", name], None))
    return found


def _numstat_test_adds(where, diff_args, is_test_rel):
    """The test paths on which `git diff --numstat <diff_args>` shows added lines, or a binary file. The test is
    check_red_run's own: a row whose added count is not 0. A failed read gives none."""
    done = _git(where, "-c", "core.quotepath=off", "-c", "diff.relative=false", "diff", "--no-ext-diff",
                "--no-renames", "--numstat", "-z", *diff_args)
    if done is None or done.returncode != 0:
        return []
    paths = []
    for row in done.stdout.split("\0"):
        parts = row.lstrip("\n").split("\t", 2)
        if len(parts) == 3 and parts[0] != "0" and is_test_rel(parts[2]):
            paths.append(parts[2])
    return paths


def _untracked_test_adds(where, top, specs, is_test_rel):
    """The non-empty untracked files on a test path that `git add` would stage (`_untracked_names`)."""
    paths = []
    for name in _untracked_names(where, specs):
        try:
            if is_test_rel(name) and os.path.getsize(os.path.join(top, name)) > 0:
                paths.append(name)
        except OSError:
            continue
    return paths


def _commit_test_adds(where, top, all_flag, specs, wholes, adds, is_test_rel):
    """The test paths a commit adds lines to, read from the tree the marker read uses: the index, else the working
    tree for `-a`, a pathspec, a whole-tree add (`wholes` holds the tops) and the pathspecs of earlier adds
    (`adds`). No diff form shows an untracked file, so each add's untracked paths are read in every form."""
    if specs:
        return _numstat_test_adds(where, ["HEAD", "--", *specs], is_test_rel)
    whole = all_flag or top in wholes
    paths = _numstat_test_adds(top, ["HEAD"] if whole else ["--cached"], is_test_rel)
    if top in wholes:
        paths += _untracked_test_adds(top, top, None, is_test_rel)
    for add_where, add_top, add_paths in adds:
        if add_top == top:
            if not whole:
                paths += _numstat_test_adds(add_where, ["HEAD", "--", *add_paths], is_test_rel)
            paths += _untracked_test_adds(add_where, top, add_paths, is_test_rel)
    return list(dict.fromkeys(paths))


_MESSAGE_ELSEWHERE = {"--file", "--reuse-message", "--reedit-message", "--fixup", "--squash", "--template"}


def _commit_paragraphs(args, bodies=()):
    """The message paragraphs of a `git commit` call, in order, or None when its message comes from a place the guard
    cannot read: `-F` (a file, or `-` with no heredoc body), `-C`, `-c`, `-t`, `--fixup`, `--squash`, or no `-m` at all
    with no `--amend` (an editor). `-F -` (also `--file=-`, `-F-`) with a heredoc on its own segment reads the
    heredoc `bodies` as the message: the body is in the command, so no file or stdin read is needed."""
    paragraphs, elsewhere, index = [], False, 0
    stdin_text = "\n\n".join(bodies)
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            break
        if arg.startswith("--"):
            name, equals, value = arg.partition("=")
            if name == "--message":
                if equals:
                    paragraphs.append(value)
                elif index < len(args):
                    paragraphs.append(args[index])
                    index += 1
                continue
            if name == "--file":
                source = value if equals else (args[index] if index < len(args) else "")
                if source == "-" and stdin_text:
                    paragraphs.append(stdin_text)
                else:
                    elsewhere = True
            else:
                elsewhere = elsewhere or name in _MESSAGE_ELSEWHERE
            if name in _COMMIT_VALUE_FLAGS and not equals:
                index += 1
        elif arg.startswith("-") and len(arg) > 1:
            for at, letter in enumerate(arg[1:], 1):
                if letter in _COMMIT_VALUE_LETTERS:
                    rest = arg[at + 1:]
                    if letter == "m":
                        if rest:
                            paragraphs.append(rest)
                        elif index < len(args):
                            paragraphs.append(args[index])
                    elif letter == "F":
                        source = rest or (args[index] if index < len(args) else "")
                        if source == "-" and stdin_text:
                            paragraphs.append(stdin_text)
                        else:
                            elsewhere = True
                    else:
                        elsewhere = True
                    index += 0 if rest else 1
                    break
    if elsewhere or (not paragraphs and "--amend" not in args):
        return None
    return paragraphs


def _commit_message(args, bodies=()):
    """`(readable, message)` of a `git commit` call. A message the guard cannot read (`_commit_paragraphs` gives None)
    is `(False, None)`; an `--amend` with no `-m` keeps the commit's own message, `(True, None)`. `bodies` are the
    heredoc bodies of the commit's own segment: an `-m` that holds a `$(cat <<'EOF' ...)` takes its message from
    them, so they join the paragraphs; an `-F -` takes them as its whole message. The guard's strip leaves them out of
    the segment text."""
    paragraphs = _commit_paragraphs(args, bodies)
    if paragraphs is None:
        return False, None
    if bodies and any("<<" in paragraph for paragraph in paragraphs):
        paragraphs = paragraphs + list(bodies)
    return True, "\n\n".join(paragraphs) if paragraphs else None


def _note_commit(virtual, args, paths, bodies=()):
    """Records a `git commit` of this call in `virtual`, for the red-run read of a push after it: a new commit adds
    a (message, test paths) to `pending`, and an `--amend` rewrites the newest pending commit, else the tip, where
    a message of its own replaces the old one. A message the guard cannot read makes the push a no-hit."""
    readable, message = _commit_message(args, bodies)
    if not readable:
        virtual["unreadable"] = True
        return
    if "--amend" not in args:
        virtual["pending"].append((message, paths))
        return
    if virtual["pending"]:
        old_message, old_paths = virtual["pending"][-1]
        virtual["pending"][-1] = (old_message if message is None else message, list(dict.fromkeys(old_paths + paths)))
    else:
        old_message, old_paths = virtual["tip"] or (None, [])
        virtual["tip"] = (old_message if message is None else message, list(dict.fromkeys(old_paths + paths)))


def _replaying(top):
    """True when a merge or another replay is in progress at TOP: MERGE_HEAD or a `REPLAY_MARKS` entry sits in its git
    dir, which is `.git`, or the folder a `.git` file names. Read from files alone: no git is spawned. Its commit
    holds lines that other commits already carry, so it is not judged."""
    git_dir = os.path.join(top, ".git")
    try:
        if not os.path.isdir(git_dir):
            with open(git_dir, encoding="utf-8") as handle:
                first = handle.readline(4096).strip()
            if not first.startswith("gitdir:"):
                return False
            git_dir = os.path.join(top, first[len("gitdir:"):].strip())
    except (OSError, UnicodeDecodeError):
        return False
    return any(os.path.exists(os.path.join(git_dir, mark)) for mark in ("MERGE_HEAD", *REPLAY_MARKS))


def _commit_red_run(args, bodies, check_red_run, top, read_adds):
    """`([row], "new", False)` for a lone `git commit` (no push after it in the call) that adds lines to a test path
    and whose own `-m` message holds no valid Red-run trailer, else None. `read_adds()` gives the test paths the
    commit stages (`_commit_test_adds`): the one git read, made only when the message could be a gap. No hit for a
    message the guard cannot read (`_commit_message`; an `-m` with a `$` or a backtick but no heredoc body is a
    substitution it cannot read), an `--amend` with no `-m`, a merge or another replay in progress, a revert's own
    message, and a commit with no test line added."""
    readable, message = _commit_message(args, bodies)
    if not readable or message is None or (not bodies and set(message) & set("$`")):
        return None
    if check_red_run.has_trailer(message) or _replaying(top):
        return None
    row = check_red_run.pending_gap(message, read_adds())
    return ([row], "new", False) if row else None


def _chain_safe(segment):
    """True when the segment cannot change the tree a later commit reads: a git add, a git read,
    `true`, `false`, `cd` (the root already resolves through a cd), `mkdir` (git tracks no empty folder) or a plain
    `VAR=value`. A commit is judged on its own, so
    the caller never asks about one."""
    call = git_call_of(segment)
    if call is not None:
        return call[0] == "add" or call[0] in _READ_VERBS
    tokens = segment_tokens(segment) or []
    if tokens and all(ASSIGNMENT.match(token) for token in tokens) and not set(segment) & set("`("):
        return True   # a plain `VAR=value` runs nothing; a substitution could, so it stays unsafe
    index = resolve_command(tokens) if tokens else None
    if index is not None and basename(tokens[index]) == "mkdir":
        return not set(segment) & set("`(")   # a substitution in its operands could run anything
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


def _after_missing_cd(segments, number, cwd, ends, made=frozenset()):
    """True when a `cd` ahead of `segments[number]` named a folder that is missing now and the segment still runs: the
    shell stayed where it was. The walk that reads a failed cd as staying (`failed_cd_stays`) and the one that does
    not trust it (None) differ only there, so a folder in the first and None in the second marks that cd. A folder in
    `made` (`_made_folders`) is read as present."""
    return (dir_before_segment(segments, number, cwd, ends, failed_cd_stays=True, made=made) is not None
            and dir_before_segment(segments, number, cwd, ends, made=made) is None)


_MKDIR_VALUE_FLAGS = ("-m", "--mode", "--context")
_CLONE_VALUE_FLAGS = ("-b", "--branch", "-o", "--origin", "-c", "--config", "-u", "--upload-pack", "-j", "--jobs",
                      "--depth", "--reference", "--reference-if-able", "--separate-git-dir", "--template", "--filter",
                      "--shallow-since", "--shallow-exclude", "--server-option", "--bundle-uri", "--ref-format")
_WORKTREE_ADD_VALUE_FLAGS = ("-b", "-B", "--reason")
_INIT_VALUE_FLAGS = ("-b", "--initial-branch", "--template", "--separate-git-dir", "--object-format", "--ref-format")


def _operands(args, value_flags):
    """The operands of a command's args: a flag is skipped, and so is the value of one in `value_flags`. After `--`
    every arg is an operand."""
    found, skip, ended = [], False, False
    for arg in args:
        if skip:
            skip = False
        elif ended or not arg.startswith("-") or arg == "-":
            found.append(arg)
        elif arg == "--":
            ended = True
        else:
            skip = arg in value_flags
    return found


def _made_folders(segments, number, cwd, ends):
    """The normalized folders that a segment ahead of `segments[number]` makes: a `mkdir`'s operands, a `git clone`'s
    target (git's default name when none is given), a `git init`'s folder and a `git worktree add`'s path, each with its
    parents. A `mkdir`'s parents count only with `-p`; without it the folder counts only when its parent is present
    (a folder on disk, or one made earlier), because the mkdir fails otherwise. Each is resolved against the folder its own segment runs in. Parsing only: no process is
    spawned."""
    made = set()
    for at in range(number):
        tokens = segment_tokens(segments[at]) if segments[at].strip() else None
        index = resolve_command(tokens) if tokens else None
        if index is None:
            continue
        paths, call, parents = [], git_call_of(segments[at]), True
        if basename(tokens[index]) == "mkdir":
            paths = _operands(tokens[index + 1:], _MKDIR_VALUE_FLAGS)
            parents = any(arg == "--parents" or re.match(r"-[a-zA-Z]*p", arg) for arg in tokens[index + 1:])
        elif call is not None and call[0] == "clone":
            operands = _operands(call[1], _CLONE_VALUE_FLAGS)
            if len(operands) > 1:
                paths = [operands[1]]
            elif operands:
                default = operands[0].rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
                paths = [default[:-4] if default.endswith(".git") else default]
        elif call is not None and call[0] == "init":
            paths = _operands(call[1], _INIT_VALUE_FLAGS)[:1]
        elif call is not None and call[0] == "worktree" and call[1][:1] == ["add"]:
            paths = _operands(call[1][1:], _WORKTREE_ADD_VALUE_FLAGS)[:1]
        if not paths:
            continue
        base = dir_before_segment(segments, at, cwd, ends, failed_cd_stays=True, made=frozenset(made))
        c_target = _segment_git_c_target(tokens) if call is not None else None
        if c_target is not None:
            base = _absolute(c_target, base or "")
        for path in paths:
            target = shell_abs(path, base)
            while target and os.path.isabs(target):
                target = os.path.normpath(target)
                if target in made or os.path.dirname(target) == target:
                    break
                parent = os.path.dirname(target)
                if not parents and parent not in made and not os.path.isdir(parent):
                    break   # a mkdir without -p fails when its parent is missing, so nothing is made
                made.add(target)
                target = os.path.dirname(target) if parents else None
    return frozenset(made)


def conflict_markers_hit(stripped: str, cwd: str, is_test_rel=None, raw=None, written_test=None):
    """Return `(kind, file)` for the first commit or push that would carry all three conflict markers
    in one file, else `('', '')`. The kind is `commit`, `push`, `chain` (a push after a commit the
    guard could not judge; the file is then `git push`), or `cd` (a git write, any verb in `GIT_WRITES`, after a `cd`
    into a folder that is missing now and that no earlier segment makes (`_made_folders`), which the shell survives:
    the file is then `git <verb>`; the reason prints no folder, ruling own-476-c-refuse-cd-missing-folder). A push that carries no marker but sends a test
    commit with no valid Red-run trailer returns `('red-run', (found, last, rewritten))` (`_red_run_found`); a caller that
    passes no `is_test_rel` reads no red-run hit. A lone commit (no push after it in the call) that adds test lines with no
    valid trailer in its `-m` returns `('red-run-commit', (found, 'new', False))` (`_commit_red_run`). Each segment is judged from its own command word. `raw` is the
    command before the heredoc strip: a commit's `-m "$(cat <<'EOF' ...)"` message is read from it."""
    pending = []                        # earlier adds no commit has taken: (where, None) stages whole, (where, specs) names paths
    repos = {}                          # where -> (top, has_head), one `git rev-parse` each until the next commit
    readable = True                     # every segment so far is one that cannot change the tree
    blind_commit = blind_triplet = conflict_step = False   # a commit after a blind step / that covers a triplet / a conflict step ran
    ends = []
    segments = split_segments(stripped, ends)
    calls = [git_call_of(segment) if segment.strip() else None for segment in segments]
    # A commit with no push after it lands before any push reads a range, so it needs no red-run read.
    last_push = max((number for number, call in enumerate(calls) if call is not None and call[0] == "push"), default=-1)
    virtual = {"tip": None, "pending": [], "unreadable": False}   # commits of this call that have not landed, for the red-run read
    heads_before = 0                    # heredoc headers in the segments ahead, which picks a segment's own bodies in `raw`
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        call = calls[number]
        before, heads_before = heads_before, heads_before + len(heredoc_heads(segment)[0])
        if call is not None and call[0] in GIT_WRITES and _segment_git_c_target(segment_tokens(segment) or []) is None:
            if (_after_missing_cd(segments, number, cwd, ends)
                    and _after_missing_cd(segments, number, cwd, ends, _made_folders(segments, number, cwd, ends))
                    and _repo_of(repos, dir_before_segment(segments, number, cwd, ends, failed_cd_stays=True)) is not None):
                return "cd", "git " + call[0]
        if call is not None and call[0] == "push":
            if blind_commit and (blind_triplet or conflict_step):
                return "chain", "git push"
            kind, found = _push_hit(segment, stripped, cwd, call[1], is_test_rel, virtual)
            if kind:
                return kind, found
            virtual = {"tip": None, "pending": [], "unreadable": False}   # this push sent them
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
        red_hit = None
        if not has_head:   # no HEAD: `git diff` would read an empty tree
            continue
        # An earlier step of this call may edit a test file the commit then takes (`sed -i f && git commit -a`): the hook
        # runs before the shell, so the tree it reads is still clean. `written_test` names the test paths those steps write.
        earlier = " && ".join(prior for prior in segments[:number] if prior.strip()) if (
            written_test and number and (all_flag or specs or wholes or adds)) else ""

        def test_adds(where=where, top=top, all_flag=all_flag, specs=specs, wholes=wholes, adds=adds, earlier=earlier):
            paths = _commit_test_adds(where, top, all_flag, specs, wholes, adds, is_test_rel)
            return list(dict.fromkeys(paths + (written_test(earlier) if earlier else [])))

        if call[0] == "commit" and number < last_push and is_test_rel is not None and _red_run_present():
            bodies = own_heredoc_bodies(segment, raw, before) if raw and "<<" in segment else ()
            _note_commit(virtual, call[1], test_adds(), bodies)
        elif call[0] == "commit" and is_test_rel is not None and _red_run_present():
            bodies = own_heredoc_bodies(segment, raw, before) if raw and "<<" in segment else ()
            red_hit = _commit_red_run(call[1], bodies, _red_run_module(), top, test_adds)
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
        if readable and name:
            return "commit", name
        if red_hit:   # read from the index at hook time, whatever command runs before the commit: a miss costs a later push refusal
            return "red-run-commit", red_hit
        if not readable:
            blind_commit = True
            blind_triplet = blind_triplet or bool(name)
    return "", ""


# ---- merge --role: the role is read from this session's own get_session record
ROLE_TIERS = ("batch-runner", "lane", "standing")  # glossary-ok: ROLE_TIERS is the existing name; merge.py MERGE_ROLES names the same roles
LOCAL_ROLE_TIERS = ("batch-runner",)  # glossary-ok: the name a test reads; the roles a local role file may name (merge.py LOCAL_MERGE_ROLES), the lane role is a cloud role only
ROLE_WITH_STEP = "lane"  # the role whose call also names a step (--step), proved by a cs-step tag of the own record
STANDING_ROLE = "standing"  # ruling own-tiny-fixes-b: a standing session, not a batch runner, merges its own pull request
STANDING_HOLDERS = ("coordinator", "triage", CONSULTANT_TAG.split(":", 1)[1])  # the cs-build tags that prove the standing session role (decision session-tiers)  # glossary-ok: session-tiers is the decision
LANE_MERGE_REPO = "shivinate7/claude-settings"  # the one repo whose lanes hold the lane merge role; agrees with merge.py LANE_MERGE_REPO, which this module cannot import
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
    """Return the role word after the role flag when the segment runs the merge tool with it, else None.

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


def role_step_of(segment: str) -> str:
    """The value after the step flag when the segment runs the merge tool with it (`--step X` or `--step=X`), else ''. The last flag wins, as argparse reads it."""
    rest = merge_tool_args(segment) or []
    step = ""
    for at, arg in enumerate(rest):
        if arg == "--step":
            step = rest[at + 1] if at + 1 < len(rest) else ""
        elif arg.startswith("--step="):
            step = arg[len("--step="):]
    return step


def _own_session_read(transcript: str, own_id: str, created: bool = False):
    """(tags, tagged_after): the own-record read of hooks/own_session.py, without the parent id."""
    # `created` counts a create_session call as a record too: rule lane-one-topic reads a lane by its start.
    return own_session.own_session_read(transcript, own_id, created)[:2]


def _own_get_session_tags(transcript: str, session_id: str):
    """The tags of the newest get_session result in this session's own transcript whose ccr.id is
    session_id (the session's own id, or a target's id for lane-closes-after-records), else None."""
    return _own_session_read(transcript, session_id)[0]


def _nested_segments(text: str, depth: int = 0):
    """Yield (segment, too_deep) for each non-blank segment of `text`, then for each script a segment hands on (inner_commands, the one reader of
    `bash -c`, `$(...)` and the other wrappers), down to MERGE_NEST_DEPTH, and for each command substitution of `text`. A script nested deeper, or text whose
    substitutions nest too deep to cut, is yielded whole, with too_deep True."""
    try:
        from guard_env import _substitutions  # the one cut of `$(...)`, backtick and process substitutions outside single quotes
        found, deep = _substitutions(text)
        texts = [part for part, _in_message in found]
    except Exception:
        texts, deep = [text], True   # an unreadable cut is read whole and judged as a refusal where it holds the flag
    if deep:
        yield text, True
    for part in texts:
        for segment in split_segments(part):
            if not segment.strip():
                continue
            yield segment, False
            tokens = segment_tokens(segment)
            for script in (inner_commands(tokens) if tokens else []):
                if depth >= MERGE_NEST_DEPTH:
                    yield script, True
                else:
                    yield from _nested_segments(script, depth + 1)


def _tags_name_lane_merge_repo(tags) -> bool:
    """True when a cs-repo tag of the own record names LANE_MERGE_REPO: the only repo whose lanes hold the lane merge role. Own tags only, no REST read."""
    return any(repo_tag_names(tag, LANE_MERGE_REPO) for tag in tags)


def role_proof_hit(stripped: str, transcript: str) -> str:
    """Return the matched call when a segment runs the merge tool with a role the own record does not
    prove, else ''. Fails closed inside the clause: any error in the reads is a refusal, because the
    allow rule has no classifier behind it and the guard-wide crash path fails open.
    A script a wrapper hands on (`bash -c`, `$(...)`: _nested_segments) is judged as a top-level call is; one nested deeper than
    MERGE_NEST_DEPTH that holds a role flag is refused."""
    if "--role" not in stripped:   # the cheap filter: every spelling of the flag holds this text, so no other call is cut or read
        return ""
    for segment, too_deep in _nested_segments(stripped):
        if too_deep:
            if "--role" in segment:
                return "merge role in a deep wrapper"
            continue
        role = role_call_of(segment)
        if role is None:
            continue
        try:  # cost: one transcript read, only on a role-flag call
            from override import remote_session_id
            own_id = remote_session_id()
            if own_id and transcript:
                if role == STANDING_ROLE:  # a tag set after the record may have changed the role, so that record proves nothing
                    tags, tagged_after = _own_session_read(transcript, own_id)
                    if tags is not None and not tagged_after and any(ROLE_TAG_PREFIX + r in tags for r in STANDING_HOLDERS):
                        continue
                    return "merge role " + role
                tags = _own_get_session_tags(transcript, own_id)
                if role in ROLE_TIERS and tags is not None and ROLE_TAG_PREFIX + role in tags:  # glossary-ok: ROLE_TIERS is the existing name
                    step = role_step_of(segment)
                    # a lane's step must be a cs-step tag of its own record, exactly, and its record must name the lane-merge repo
                    if role != ROLE_WITH_STEP or (step and STEP_TAG + step in tags and _tags_name_lane_merge_repo(tags)):
                        continue
        except Exception:
            pass
        return "merge role " + role
    return ""


# ---- self-role-claim: a session does not start a child session that claims a role (decision session-tiers)
SELF_ROLE_VARIABLE = "CS_SESSION_ROLE"
SELF_ROLE_LAUNCHERS = ("claude-role", "claude-role.cmd")
SELF_ROLE_REASON = (
    "self-role-claim: a session does not claim a role for a session it starts, because a role proves who may merge and who writes "
    "the roadmap. The owner starts a role session from his own terminal. Do the work in this session, or ask the owner to start "
    "the session he wants. "
    "(decision session-tiers, a local role comes from the owner's launcher, never from a session's own call)"  # glossary-ok: session-tiers is the decision's file name
)


def _set_environment_variable_names(lowered) -> bool:
    """True when a `SetEnvironmentVariable(` call in the lowered tokens takes the role variable as its first argument. The tokenizer drops
    the quotes and leaves the paren glued, so the name is the rest of the call's token, or the next token when that rest is empty."""
    variable = SELF_ROLE_VARIABLE.lower()
    for at, token in enumerate(lowered):
        call = token.find("setenvironmentvariable")
        if call < 0:
            continue
        first = token[call + len("setenvironmentvariable"):].lstrip("( ")
        if not first and at + 1 < len(lowered):
            first = lowered[at + 1]
        if first.strip("'\"(), ") == variable:
            return True
    return False


def _claims_a_role(tokens) -> bool:
    """True when one tokenized command sets the role variable (a `VAR=x` prefix, also glued to a subshell's `(`, `env VAR=x`, `export VAR=x`,
    PowerShell `$env:VAR=x`, `Set-Item` or `New-Item` on `Env:VAR`, `SetEnvironmentVariable('VAR', ...)`) or runs the launcher, as its command
    word or as the script of a python call. A PowerShell read of `Env:VAR` (Test-Path, Get-Item, Remove-Item) is no claim."""
    index = resolve_command(tokens)
    before = tokens if index is None else tokens[:index]
    if any(t.lstrip("(").startswith(SELF_ROLE_VARIABLE + "=") for t in before):
        return True
    lowered = [t.lower() for t in tokens]
    variable = SELF_ROLE_VARIABLE.lower()
    if any(t.startswith("$env:" + variable) and t[len("$env:" + variable):].lstrip().startswith("=") for t in lowered):
        return True
    if any(t == "$env:" + variable for t in lowered) and any(t.startswith("=") for t in lowered):
        return True
    if _set_environment_variable_names(lowered):
        return True
    if index is None:
        return False
    word = basename(tokens[index])
    rest = tokens[index + 1:]
    if word.lower() in ("set-item", "new-item") and any(t in ("env:" + variable, "env:\\" + variable) for t in lowered):
        return True
    if word in ("export", "declare", "typeset", "setenv") and any(t.startswith(SELF_ROLE_VARIABLE + "=") for t in rest):
        return True
    if word in SELF_ROLE_LAUNCHERS:
        return True
    if word.startswith("python"):
        script = next((t for t in rest if not t.startswith("-")), None)
        return script is not None and basename(script) in SELF_ROLE_LAUNCHERS
    return False


def _self_role_hit(text: str, depth: int, judge=None, unreadable: bool = True) -> bool:
    """True when `judge` (default `_claims_a_role`) is true of any command the text runs, reading the same places each time.
    `unreadable` is the answer for a segment that cannot be tokenized (a quote left open): True refuses it, as a claim must."""
    judge = judge or _claims_a_role
    from guard_env import substitution_commands   # imported late: a family reads only the families before it
    stripped = strip_heredoc_bodies(text)
    # Each `$( )` or backtick text runs as a command of its own, as judge_shell reads it. A nest too deep to read gives no inner text,
    # so a claim buried that deep passes: only a forger writes one (rule guard-guards-mistakes-only).
    for each in substitution_commands(text, stripped, outer=True):
        for segment in split_segments(each):
            if not segment.strip():
                continue
            tokens = segment_tokens(segment)
            if tokens is None:
                if unreadable:
                    return True   # a quote left open: the segment names what the judge looks for and cannot be read, so it is refused
                continue
            if judge(tokens):
                return True
            for script in inner_commands(tokens):
                if _self_role_hit(script, depth + 1, judge, unreadable) if depth < MERGE_NEST_DEPTH else unreadable:
                    return True
    return False


def self_role_hit(stripped: str) -> str:
    """Return a short label when a Bash or PowerShell call sets the role variable or runs the launcher, else ''. Reads each segment, each `$( )` or
    backtick text, and each script a `bash -c`, `sh -c` or `eval` hands on, so quoted text, `echo $VAR`, `grep claude-role` and `cat bin/claude-role` are no claim.
    Fails closed inside the clause: a call that names the variable or the launcher and cannot be read is refused, because the guard-wide crash
    path fails open. Cost: one substring test per call; a parse only for a call that names the variable or the launcher."""
    lowered = stripped.lower()
    if SELF_ROLE_VARIABLE.lower() not in lowered and "claude-role" not in lowered:
        return ""
    try:
        return "a session claims a role" if _self_role_hit(stripped, 0) else ""
    except Exception:
        return "a session claims a role"


# ---- self-role-claim, child start: a session that holds a role does not start claude (decision session-tiers)
SELF_ROLE_CHILD_REASON = (
    "self-role-claim: a claude this call starts would hold a role. Either this session holds one and the child inherits it, or the call "
    "resumes (--resume, -r, -c) a session whose role file exists, and a resume keeps that file. The child would gain a merge or a "
    "roadmap push that a cloud child does not have. Do the work in this session, or ask the owner to start the session he wants "
    "from his own terminal. "
    "(decision session-tiers, a session with a role does not start a child session)"  # glossary-ok: session-tiers is the decision's file name
)


def _program_word(token: str) -> str:
    """The lowercase program name of a command word: the base name, with a `.exe` suffix dropped."""
    word = basename(token.lstrip("(")).lower()
    return word[:-len(".exe")] if word.endswith(".exe") else word


def _starts_claude(tokens) -> bool:
    """True when one tokenized command starts a claude session: `claude` as a command word (behind a wrapper, a subshell `(` or a PowerShell
    `&`), or PowerShell `Start-Process` of it. `claude --version` alone starts none. Reads each command word of the segment."""
    for at in command_indexes(tokens):
        if tokens[at] in ("&", "."):   # PowerShell's call operator: the program is the next word
            at += 1
            if at >= len(tokens):
                continue
        word = _program_word(tokens[at])
        rest = tokens[at + 1:]
        if word == "claude":
            if rest != ["--version"]:
                return True
        elif word in ("start-process", "saps", "start") and any(_program_word(t) == "claude" for t in rest):
            return True
    return False


def _resume_target(tokens):
    """None when no claude start in one tokenized command resumes a session. Else the value the resume names, as written ('' for `-c`, `--continue`
    and a `--resume` or `-r` with no value). Reads the same command words as _starts_claude; a `Start-Process` argument string is split into words."""
    for at in command_indexes(tokens):
        if tokens[at] in ("&", "."):
            at += 1
            if at >= len(tokens):
                continue
        word = _program_word(tokens[at])
        rest = tokens[at + 1:]
        if word in ("start-process", "saps", "start") and any(_program_word(t) == "claude" for t in rest):
            rest = [w for t in rest for w in t.split()]
        elif word != "claude":
            continue
        for place, arg in enumerate(rest):
            if arg in ("-c", "--continue"):
                return ""
            if arg in ("--resume", "-r"):
                value = rest[place + 1] if place + 1 < len(rest) else ""
                return "" if value.startswith("-") else value
            if arg.startswith("--resume="):
                return arg[len("--resume="):]
    return None


def _resume_names_role(target: str, cwd: str, transcript: str) -> bool:
    """True when a resume that names `target` would bring back a session whose role file is valid. A session id of the id shape with its own role
    file counts. An id-shaped value with no role file is a known non-role session only when `<value>.jsonl` sits in this project's folder; any other
    such value (a title like `batch-runner` fits the id shape) is judged as a value that names no id. A value that names no id (`-c`, a bare
    `--resume`, a title) can reach any role session whose transcript sits in the project's folder (the folder of the own transcript, else the one
    the cwd names under the config dir); with no such folder to read, any valid role file counts, except for an id-shaped value, taken as a session id."""
    import re
    import session_role
    id_shaped = bool(target) and session_role.valid_id(target)
    if id_shaped and session_role.own_record(target) is not None:
        return True
    records = session_role.all_records()
    if not records:
        return False
    folder = os.path.dirname(transcript) if transcript else ""
    if not folder and cwd:
        folder = os.path.join(session_role.roles_dir().parent.parent, "projects", re.sub(r"[^A-Za-z0-9]", "-", cwd))
    if not folder or not os.path.isdir(folder):
        return not id_shaped   # no folder to read: an id-shaped value is taken as a session id, as before; any other value counts any role file
    if id_shaped and os.path.exists(os.path.join(folder, target + ".jsonl")):
        return False
    return any(os.path.exists(os.path.join(folder, record["session"] + ".jsonl")) for record in records)


def self_role_child_hit(stripped: str, cwd: str = "", transcript: str = "") -> str:
    """Return a short label when a Bash or PowerShell call starts claude and the child would hold a role, else ''. Two ways. (1) The guard's own
    environment holds a non-empty CS_SESSION_ROLE: the child inherits it and its SessionStart hook would write its own role file. (2) The call
    resumes (`--resume <id>`, `-r`, `-c`, `--continue`) a session whose role file is valid: the start keeps that file (session_role.write), so a
    role-less session would take the role over. Way (1) fails closed inside the clause: a call that names claude and cannot be read is refused,
    because the guard-wide crash path fails open. Way (2) lets an unreadable call pass, since it needs a role file to exist and a real resume.
    Cost: one environment read per call; a parse only when the call names claude; one folder listing of the role files for a resume."""
    if "claude" not in stripped.lower():
        return ""
    if os.environ.get(SELF_ROLE_VARIABLE):
        try:
            return "a role session starts claude" if _self_role_hit(stripped, 0, _starts_claude) else ""
        except Exception:
            return "a role session starts claude"
    def resumes_a_role(tokens) -> bool:
        target = _resume_target(tokens)
        return target is not None and _resume_names_role(target, cwd, transcript)
    try:
        return "a resume names a session that holds a role" if _self_role_hit(stripped, 0, resumes_a_role, unreadable=False) else ""
    except Exception:
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


LOCAL_REPO_REASON = (
    "merge-confirm-repo: the role file recorded for this session does not prove it may merge in the checkout "
    "this command acts in. A local merge runs only from a session whose own role file names the batch runner for that repo. "
    "Hand the pull request to the batch runner, or ask the owner. "
    "(decision merge-confirm-repo, a merge acts only in a repo its own record names)"
)


def local_session_id(session_id: str) -> str:
    """The session id a local role file may prove the record writer for: the hook payload's own id, else ''. The environment's
    CLAUDE_CODE_SESSION_ID names no file here, since a file for the env id alone is not this session's. The reader tests the id's shape."""
    return session_id if isinstance(session_id, str) else ""


def _local_role_proves(session_id: str, roles, repo) -> bool:
    """True when the launcher's role file for this local session names one of `roles` and the repo `repo`. Any failure is False."""
    try:
        import session_role
        record = session_role.own_record(local_session_id(session_id))
        return bool(record and record["role"] in roles and repo and record.get("repo") == repo)
    except Exception:
        return False


def repo_proof_hit(stripped: str, cwd: str, transcript: str, session_id: str = "") -> str:
    """Return a short label when a cloud session's `merge --confirm` or `merge --ready` acts in a checkout whose repo no cs-repo tag of the own newest
    get_session record names, else ''. Fails closed inside the clause, like role_proof_hit: an unparseable command, an unreadable
    checkout, no record and a set_session_tags after the record are each a refusal, because the guard-wide crash path fails open.
    --lane-lint merges no pull request and is not judged. Cost: none for a call that is no merge confirm;
    else one parse, one read of the origin and one transcript read.

    A local session is judged on `--confirm` only, by its OWN record (session_role.local_judgement, rules a, b, c): an own file must name
    batch-runner and the repo the merge acts in, and CS_SESSION_ROLE set with no matching own file refuses. A session with neither is not judged.

    A redirection (`2>&1`, `> run.log`) belongs to the shell, not to the merge tool, so the parser reads the segment without them
    (strip_redirections, the quote-aware reader of their shape; a quoted `<` or `>` is text and stays). When the segment no longer
    tokenizes once they are gone (a quote left open), the merge is denied, never skipped."""
    if not is_cloud():
        if "--confirm" not in stripped:   # the cheap filter: no listing of the role folder for a call that merges nothing
            return ""
        try:
            import session_role
            if not session_role.local_judgement(session_id)[0]:   # rule (b): no own file and no launcher role, so today's behaviour
                return ""
        except Exception:
            pass   # a reader that cannot run judges the call, so the clause fails closed
        return "merge --confirm" if _unproved_confirm(stripped, cwd, transcript, 0, session_id) else ""
    return "merge --confirm or --ready" if _unproved_confirm(stripped, cwd, transcript, 0) else ""


MERGE_NEST_DEPTH = 4  # `bash -c` inside `bash -c` is followed this far; a deeper script is judged as a refusal
PROVED_FLAGS = ("--confirm", "--ready")  # each pushes to the pull request's branch from the checkout it acts in, so each takes the repo proof


def _unproved_confirm(text: str, cwd: str, transcript: str, depth: int, local_session: str = None) -> bool:
    """True when a `merge --confirm` or `merge --ready` (PROVED_FLAGS) in `text` acts in a checkout the own record does not prove. `text` is the command, or a script a
    segment hands on (`bash -c`, `sh -c`, `eval`: inner_commands, the one reader of those wrappers), which runs in the directory its own
    segment is in. A `)` or `&` glued to the last word ends the merge's arguments (_command_words), so a merge closing a subshell is read.
    `local_session` is None for a cloud session. For a local session it is the hook payload's session id (own id; "" is no id): only `--confirm` is judged."""
    ends = []
    segments = split_segments(text, ends)
    for number, segment in enumerate(segments):
        if not segment.strip():
            continue
        tokens = segment_tokens(segment)
        scripts = inner_commands(tokens) if tokens else []
        if scripts:
            if depth >= MERGE_NEST_DEPTH:
                if any(f in script for script in scripts for f in PROVED_FLAGS):
                    return True
            else:
                where = dir_before_segment(segments, number, cwd, ends) or ""
                if any(_unproved_confirm(script, where, transcript, depth + 1, local_session) for script in scripts):
                    return True
        if merge_tool_args(segment) is None:
            continue
        try:
            rest = _command_words(merge_tool_args(segment))
            bare = merge_tool_args(strip_redirections(segment))
            bare = None if bare is None else _command_words(bare)
            if not any(f in (rest if bare is None else bare) for f in PROVED_FLAGS):
                continue
            if bare is None:
                raise _FlagsUnreadable("the segment does not tokenize without its redirections")
            flags = _merge_flags(bare)
            if flags.lane_lint or not (flags.confirm or flags.ready):
                continue
            repo = _merge_target_repo(segments, number, cwd, ends, flags.repo_dir)
            if local_session is not None:
                if not flags.confirm:
                    continue
                import session_role
                judged, record = session_role.local_judgement(local_session)
                if not judged or (record and record["role"] in LOCAL_ROLE_TIERS and repo and record.get("repo") == repo):  # glossary-ok: LOCAL_ROLE_TIERS is the existing name
                    continue
                return True
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


LANE_READY_REASON = (
    "merge-role-proof: this session's own record is a claude-settings lane's. A lane marks only its own pull request ready, once, "
    "through the merge tool: the tool's role flag with its own step, then the pull request number and the ready flag, on a pull request whose head is that step's branch. "
    "Any other ready mark waits for the batch runner (list_sessions, tag cs-build:batch-runner, same cs-repo). "
    "(decision session-tiers, a session's role decides which merge acts it may run)"  # glossary-ok: session-tiers is the decision's file name
)


def lane_ready_hit(stripped: str, transcript: str) -> str:
    """Return a label when a cloud session whose own newest get_session record carries cs-build:lane and a cs-repo tag naming LANE_MERGE_REPO runs the
    merge tool's ready mark, else ''. A call is let through only when it names the lane role and a --step that is a cs-step tag of that record, and the pull
    request it names has a head that is one of lane_head_refs of that step (_lane_ready_own_pr). A batch runner, a lane of another repo or with no cs-repo tag, a session with another or no cs-build tag, and a
    session with no readable record are not judged here: the repo proof
    (repo_proof_hit) still judges each. A script a wrapper hands on is read as a top-level call is (_nested_segments); one nested deeper
    than MERGE_NEST_DEPTH that holds the flag counts as a call. Cost: one parse per merge-tool segment, one transcript read when a ready flag is found,
    and one pull request read when the call names the lane role."""
    if not is_cloud() or "--ready" not in stripped:   # the cheap filter: a call with no ready flag reads no transcript
        return ""
    for segment, too_deep in _nested_segments(stripped):
        if too_deep:
            called = "--ready" in segment
        else:
            rest = merge_tool_args(segment)
            try:
                called = rest is not None and "--ready" in _command_words(rest)
            except Exception:
                called = True   # an unreadable merge-tool segment fails closed, as the other clauses do
        if not called:
            continue
        if _own_record_is_lane(transcript) and (too_deep or not _lane_ready_own_pr(segment, transcript)):
            return "merge --ready from a lane"
    return ""


def _lane_ready_own_pr(segment: str, transcript: str) -> bool:
    """True when the merge-tool call in `segment` is a lane's ready mark of its own pull request: the lane role with a step that is a cs-step tag of the own
    record, the ready flag without --confirm, a pull request number, and a head on that number in LANE_MERGE_REPO that is one of lane_head_refs of the step.
    The read is the merge tool's own Host, so the guard and the tool read a head alike. Any failure is False: an unread pull request is refused."""
    try:
        bare = merge_tool_args(strip_redirections(segment))
        if bare is None:
            return False
        flags = _merge_flags(_command_words(bare))
        if flags.role != ROLE_WITH_STEP or not flags.step or not flags.ready or flags.confirm or not str(flags.pr or "").isdigit():
            return False
        from override import remote_session_id
        own_id = remote_session_id()
        tags = _own_get_session_tags(transcript, own_id) if own_id and transcript else None
        if tags is None or STEP_TAG + flags.step not in tags:
            return False
        module = merge_module()
        if module is None:
            return False
        with module.shared_deadline(MERGE_READ_TIMEOUT):
            info = module.Host(repo=LANE_MERGE_REPO).pr(int(flags.pr))
        return info["branch"] in lane_head_refs(flags.step)
    except Exception:
        return False


def _own_record_is_lane(transcript: str) -> bool:
    """True when the own newest get_session record in `transcript` carries cs-build:lane and a cs-repo tag naming LANE_MERGE_REPO. No id, no transcript,
    no record and a failed read are False: the callers refuse only a session that proves it is a claude-settings lane, and the repo proof judges the rest."""
    try:
        from override import remote_session_id
        own_id = remote_session_id()
        tags = _own_get_session_tags(transcript, own_id) if own_id and transcript else None
    except Exception:
        return False
    return tags is not None and LANE_TAG in tags and _tags_name_lane_merge_repo(tags)


def lane_mcp_ready_hit(tool: str, tool_input, transcript: str) -> str:
    """Return a label when a cloud session whose own record is a claude-settings lane's (_own_record_is_lane) marks a pull request ready through the MCP update tool (draft false), else ''.
    Only a draft of exactly False counts: a title edit, no draft field and draft true mark nothing ready. The refusal is LANE_READY_REASON, as for
    lane_ready_hit. Cost: none for another tool; one transcript read for a draft-false update."""
    if tool != READY_PAGE_MCP_TOOL or not is_cloud() or not isinstance(tool_input, dict) or tool_input.get("draft") is not False:
        return ""
    return "update_pull_request draft false from a lane" if _own_record_is_lane(transcript) else ""


# ---- a ready mark by MCP with no ready run that stood for the head (rule ready-mcp-mark-guard, decision ready-mcp-mark-guard)
# `merge <pr> --ready` and `merge <pr> --confirm` on a draft run the draft step, which writes no durable record of its pass. It prints lines (merge/merge.py READY_*_FMT),
# and they reach the guard only as the result of the Bash call in this session's transcript (read by lint/_transcript.py, the one home).
# The patterns are built from those templates (ready_line_pattern), never copied here. A run stands for a head when its pass line names it, when a dry-merge line maps the
# pass's sha to it, or, in a repo with no ready checks, when a line of the step names it. `--fast-checks` prints the pass line but builds no records page: it stands for nothing.
# Cost: a call that marks nothing ready reads nothing: a shell text holding `ready` is only parsed (ready_page_calls). A ready mark costs one transcript read, then the merge
# tool's load and one pull request read when a stood head is found; that read takes what is left of READY_HOOK_BUDGET after the records-page read.
# A call with no transcript, or one that cannot be read, is allowed, as the other transcript rules allow it.
READY_MARK_READ_TIMEOUT = 20
READY_RUN_FLAGS = ("--ready", "--confirm")
READY_MARK_REASON = (
    "Rule (Git, ready-mcp-mark-guard): no `merge %(n)s --ready` run in this session passed its ready checks on %(head)s. A ready mark made without that pass "
    "skips the ready checks and the records step, so the confirm refuses it and costs a second CI run (PR 3255 and PR 3472, 2026-11-15). "
    "Remedy: run `merge %(n)s --ready` in this session and let it pass, then retry this call once its draft run shows. "
    "(decision ready-mcp-mark-guard, a ready mark needs a ready pass on the head)"
)


def _ready_stood_shas(text: str, merge) -> set:
    """The shas (7 to 40 hex chars) that the ready run whose result is `text` stands for: its pass shas, the head a dry-merge line maps a pass sha to, and,
    when the run declared no ready checks, the head each sha-bearing line of the draft step names. `merge` is the merge tool module, the home of the line templates."""
    pattern = merge.ready_line_pattern
    shas = {m.group("sha") for m in pattern(merge.READY_PASS_FMT).finditer(text)}
    for m in pattern(merge.READY_DRY_FMT).finditer(text):
        if any(sha.startswith(m.group("dry")) or m.group("dry").startswith(sha) for sha in shas):
            shas.add(m.group("head"))
    if merge.READY_NO_CHECKS_LINE in text:
        for fmt in (merge.READY_UNCHECKED_FMT, merge.READY_RECORDS_CURRENT_FMT, merge.READY_RECORDS_PUSHED_FMT, merge.READY_MERGED_FMT,
                    merge.READY_CLAIM_STOP_FMT):
            shas.update(m.group("sha") for m in pattern(fmt).finditer(text))
    return shas


def _ready_pass_shas(transcript: str, merge):
    """The shas that a `--ready` or `--confirm` Bash or PowerShell call of this transcript stood for (_ready_stood_shas), or None when the
    transcript cannot be read. A run in the background stands for its shas once the transcript reads its output: a Read of the output file, or a
    Bash or PowerShell command that names it, whose result holds the run's lines. The output path is the one the run's start result names
    (stall_watch RESULT_PATH, the one home of that format), so a pass in any other file counts for nothing. The guard never opens the file."""
    from guard_core import lint_dir  # lazy: the one home of where lint/ is
    lint = lint_dir()
    if lint not in sys.path:
        sys.path.insert(0, lint)
    try:
        import _transcript
        records = _transcript.read_transcript(transcript)
        result_path = importlib.import_module("stall_watch").RESULT_PATH
    except Exception:
        return None
    ready_calls = set()
    read_calls = set()
    outputs = set()  # output files of the background ready runs seen so far
    shas = set()
    for rec in records:
        for use in _transcript.tool_uses(rec):
            tool_input = use.get("input") or {}
            command = tool_input.get("command")
            if not isinstance(use.get("id"), str):
                continue
            shell = use.get("name") in ("Bash", "PowerShell") and isinstance(command, str)
            if shell and any(flag in command for flag in READY_RUN_FLAGS):
                ready_calls.add(use["id"])
            elif use.get("name") == "Read" and tool_input.get("file_path") in outputs:
                read_calls.add(use["id"])
            elif shell and any(path in command for path in outputs):
                read_calls.add(use["id"])
        for result in _transcript.tool_results(rec):
            content = result.get("content")
            text = content if isinstance(content, str) else " ".join(
                b.get("text", "") for b in content or [] if isinstance(b, dict) and isinstance(b.get("text"), str))
            if result.get("tool_use_id") in read_calls:
                shas |= _ready_stood_shas(text, merge)
            elif result.get("tool_use_id") in ready_calls:
                shas |= _ready_stood_shas(text, merge)
                started = result_path.search(text)
                if started:
                    outputs.add(started.group(1))
    return shas


def ready_mark_hit(tool: str, tool_input, transcript: str, where: str, command: str = ""):
    """(reason, matched) when a ready mark, by MCP update with draft false or by the shell `gh pr ready` (ready_page_calls, the one parser of both),
    marks a pull request ready and this session's transcript shows no `merge <pr> --ready` or `--confirm` run that stood for the head the pull request
    has now, else None. Judged only in a repo that uses the merge tool. A call that marks nothing ready, a missing or unreadable transcript, an unloadable
    merge tool and an unreadable head pass (the records-page-ready rule reads the same head and refuses an unreadable one first). An MCP selector may carry a
    leading `#`, as ready_page_read reads it; a shell selector may also be a branch, a URL or empty, which `Host.pr_number` resolves."""
    mcp = tool == READY_PAGE_MCP_TOOL
    if mcp and (not isinstance(tool_input, dict) or tool_input.get("draft") is not False):
        return None
    if not mcp and (not isinstance(command, str) or "ready" not in command.lower()):
        return None
    if not isinstance(transcript, str) or not transcript or not where or not uses_merge_tool(where):
        return None
    calls = ready_page_calls(tool, tool_input if isinstance(tool_input, dict) else {}, command)  # before the merge tool loads: a text with no ready call starts nothing
    if not calls:
        return None
    module = merge_module()
    if module is None:
        return None
    shas = _ready_pass_shas(transcript, module)
    if shas is None:
        return None
    for selector, repo in calls:
        selector = selector[1:] if selector[:1] == "#" and selector[1:].isdigit() else selector
        if mcp and not selector.isdigit():
            continue
        number = selector if selector.isdigit() else "<pr>"
        head = ""
        if shas:  # no stood sha at all refuses without a head read
            seconds = min(READY_MARK_READ_TIMEOUT, ready_budget_left())
            if seconds < 1:  # the page read spent the call's budget: an unreadable head passes
                continue
            try:
                with module.shared_deadline(seconds):
                    host = module.Host(repo=repo or None, cwd=where)
                    resolved = host.pr_number(selector)
                    number = str(resolved)
                    head = host.pr(int(resolved))["head"]
            except Exception:
                continue
            if any(head.startswith(sha) for sha in shas):
                continue
        named = "its current head " + head[:9] if head else "its current head"
        return READY_MARK_REASON % {"n": number, "head": named}, "ready mark with no ready pass #" + number
    return None


# ---- a pull request opened by MCP with no closing link of this session (rule pr-create-session-link, decision pr-create-session-link)
# The merge tool refuses `--confirm` for a body with no link to the merging session (merge/merge.py own_session_link, the one reader of the link). The agent that opens the
# pull request is the one that can add it, so the refusal comes at creation. Only the MCP create tool is judged: in a cloud session, the only place the session id is
# known, a `gh pr create` is already refused (rule gh-write-cloud). Cost: one env read, and the merge tool load only in a cloud session.
# A local session (no session id), a repo with no merge tool and an unloadable merge tool pass.
CREATE_PR_MCP_TOOL = "mcp__github__create_pull_request"
PR_SESSION_LINK_FMT = "Session: https://claude.ai/code/%s"
PR_SESSION_LINK_REASON = (
    "Rule (Git, pr-create-session-link): this pull request's body has no link to this session. The merge tool reads that link to know who may merge, "
    "and it refuses the merge without it. Remedy: add this line to the body, on its own line, then retry: `%(line)s`. "
    "(decision pr-create-session-link, a pull request body carries its session's link)"
)


def create_pr_link_hit(tool: str, tool_input, where: str):
    """(reason, matched) when an MCP create call's body lacks this session's closing link, else None. The link is judged by the merge tool's own_session_link,
    and the line to add is built from the session id that override.remote_session_id reads, so neither reader is copied here."""
    if tool != CREATE_PR_MCP_TOOL or not isinstance(tool_input, dict):
        return None
    from override import remote_session_id
    own = remote_session_id()
    if not own or not where or not uses_merge_tool(where):
        return None
    module = merge_module()
    if module is None:
        return None
    body = tool_input.get("body")
    if module.own_session_link(body if isinstance(body, str) else ""):
        return None
    return PR_SESSION_LINK_REASON % {"line": PR_SESSION_LINK_FMT % own}, "create_pull_request body without session link"


# ---- the record branch's one writer: only the triage session pushes to it (rule roadmap-one-writer)
RECORD_WRITER_TIER = "triage"
DEFAULT_RECORD_BRANCH = "roadmap"
RECORD_DECISION_CITE = "(decision session-tiers, the triage session is the only writer of the record branch)"  # glossary-ok: session-tiers is the decision's file name
RECORD_CITE = (
    "own turn, then retry. Before this session asks the owner to push a commit, run `git fetch origin <record "
    "branch>`, then `git merge-base --is-ancestor <commit> origin/<record branch>`: exit 0 means the commit is "
    "already there, so ask the owner only when it is not. "
    + RECORD_DECISION_CITE
)
RECORD_REASON = (
    "roadmap-one-writer: the repo's record branch has one writer, the triage session, and this session's own "
    "record does not prove it is triage. Send the step change to the triage session (list_sessions, tag "
    "cs-build:triage, same cs-repo). A lane may push only its own roadmap/outbox/<slug>-handoff.md, as plain commits that "
    "each add or change that file alone, with no force, lease or tags. If the lane's push was refused for that "
    "form: fetch the record branch's origin tip (a single-branch clone widens its fetch refspec first), then rebase "
    "the commits onto that tip, with no merge commit, since a pull's merge commit is refused. Make each commit in its "
    "own call first, then retry the handoff push in a later call: a push chained after a commit is read before that "
    "commit exists. If this session is triage: run get_session (no argument) alone in its "
    + RECORD_CITE
)

# A push whose folder still holds a variable or a substitution after the command's own assignments are read: the
# folder is the shell's to know, so the push's repo and record branch are unknown. A cloud triage proof reads the
# transcript, never the folder, so it still lets the push through.
RECORD_FOLDER_MATCH = "git push to the record branch through an unreadable folder: "
RECORD_FOLDER_REASON = (
    "roadmap-one-writer: this push to the record branch runs in a folder this guard cannot read, because it holds "
    "{names} that the command does not assign. The push's repo and record branch are unknown, so a local "
    "role file cannot be matched to its repo. Write the folder as a literal path, or assign the variable earlier in the same command "
    "(`W=<folder>; git -C \"$W\" push ...`), then retry. "
    + RECORD_DECISION_CITE
)
UNREAD_FOLDER = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|\$\(|`")


def _unread_folder_names(where: str) -> str:
    """The variables and substitutions still in the folder WHERE, comma-joined, else ''."""
    names = dict.fromkeys(UNREAD_FOLDER.findall(where or ""))
    return ", ".join("a command substitution" if name in ("$(", "`") else name for name in names)


def record_reason(matched: str) -> str:
    """The refusal text for a record_writer_hit result, with its names filled in."""
    if matched.startswith(RECORD_FOLDER_MATCH):
        return RECORD_FOLDER_REASON.format(names=matched[len(RECORD_FOLDER_MATCH):])
    return RECORD_REASON


def _own_proved_tags(transcript: str):
    """The tags of the own newest get_session record when no set_session_tags call follows it, else None.
    Fails closed: no cloud id (a local session), no transcript or any read error is None."""
    try:
        from override import remote_session_id
        own_id = remote_session_id()
        if own_id and transcript:
            tags, tagged_after = _own_session_read(transcript, own_id)
            if tags is not None and not tagged_after:
                return tags
    except Exception:
        pass
    return None


def _own_role_proved(transcript: str, role: str, session_id: str = "", root=None) -> bool:
    """True when the own newest get_session record lists cs-build:<role> and no set_session_tags call
    follows it. A session with no cloud id is local: it is proved when the launcher's role file for its own id (the hook payload's id,
    local_session_id) names `role` and the repo of the checkout at `root`. Fails closed: no id, no transcript or any read error is False."""
    try:
        from override import remote_session_id
        own_id = remote_session_id()
        if not own_id:
            import git_reads
            return _local_role_proves(session_id, (role,), git_reads.github_repo(root) if root and os.path.isdir(root) else None)
        if transcript:
            tags, tagged_after = _own_session_read(transcript, own_id)
            return tags is not None and not tagged_after and ROLE_TAG_PREFIX + role in tags
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


HANDOFF_SLUG =re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # no `/` and no `.`, so a slug is one plain file-name part
HANDOFF_PATH = re.compile(r"roadmap/outbox/(" + HANDOFF_SLUG.pattern + r")-handoff\.md")


def _lane_handoff_holds(args, where: str, overrides, root: str, destination, tags) -> bool:
    """True when a lane's push of `args` to the record branch sends only commits that each change one path
    against their parent, that path is roadmap/outbox/<slug>-handoff.md in every commit, the change is an add
    or a modify, and the slug is the lane's own: a slug of one of its cs-step tags, else its checkout's branch
    with a leading `lane/` cut. The range is the commits from the record branch's origin tip to the pushed
    source, read per commit, so a file added in one commit and removed in a later one is seen. Fails closed:
    a force, a lease of any form, `--force-if-includes`, a `+` refspec, a delete, a mirror, `--tags`,
    `--follow-tags`, an unnamed remote or source, no origin tip, an unreadable range, a merge or root commit,
    a rename, a delete or an empty range is False. Cost: two git processes, `rev-list --parents` for the
    range and one `diff-tree --stdin` for every commit's paths (a `symbolic-ref` follows only when no cs-step
    tag names the slug)."""
    named = push_refspecs(args)  # None for a mirror, `--all`, a delete or a tags-only push
    if named is None or not named[0] or destination is None or not push_is_plain(args):
        return False
    remote, specs = named
    if len(specs) > 1:
        return False
    source = specs[0].partition(":")[0] if specs else "HEAD"
    if not source or source.startswith("-"):
        return False
    walk = _git(root, "rev-list", "--parents", "refs/remotes/" + remote + "/" + destination + ".." + source, "--")
    if walk is None or walk.returncode != 0:
        return False
    commits = []
    for line in walk.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:  # a root commit (1 field) or a merge (3 or more) hides its paths from diff-tree
            return False
        commits.append(fields[0])
    if not commits:
        return False
    done = _git(root, "diff-tree", "--stdin", "--no-commit-id", "--no-renames", "-r", "--name-status",
                stdin="\n".join(commits) + "\n")
    if done is None or done.returncode != 0:
        return False
    changes = [line.split("\t") for line in done.stdout.splitlines() if line.strip()]
    if not changes or any(len(change) != 2 or change[0] not in ("A", "M") for change in changes):
        return False
    slugs = set()
    for change in changes:
        found = HANDOFF_PATH.fullmatch(change[1])
        if not found:
            return False
        slugs.add(found.group(1))
    if len(slugs) != 1:  # every commit names the one own handoff path
        return False
    slug = slugs.pop()
    if slug in [str(t)[len(ARCHIVE_STEP_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_STEP_PREFIX)]:
        return True
    branch = _git(root, "symbolic-ref", "-q", "--short", "HEAD")
    if branch is None or branch.returncode != 0:
        return False
    return branch.stdout.strip() in lane_head_refs(slug)


def record_writer_hit(stripped: str, cwd: str, transcript: str, record_branch_of, read_verb, session_id: str = "") -> str:
    """Return the reason text when a segment pushes to the checkout's record branch, or to the default
    name `roadmap`, and the own record proves neither the triage role nor a lane's own handoff push, else ''.
    The text is "git push to the record branch", or `RECORD_FOLDER_MATCH` plus the unread variable names when
    the push goes to `roadmap` from a folder the command names with a variable or substitution it does not assign.
    `record_branch_of(root)` reads the checkout's branch (lint/layout.py); a read error means the default.
    `read_verb(subcommand, args)` is guard.py's own test for a dry run, which moves nothing. The proof is
    read only after a push reaches the branch. `session_id` is the hook payload's id, which a local session's
    role file is read for. Triage is allowed with no diff read. A lane is allowed only for its own handoff
    file (`_lane_handoff_holds`), which reads the pushed range's paths in two git processes."""
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
            destinations = push_destinations(args, where, overrides)
            if not {record, DEFAULT_RECORD_BRANCH} & set(destinations):
                continue
            if _own_role_proved(transcript, RECORD_WRITER_TIER, session_id, root):  # glossary-ok: RECORD_WRITER_TIER is the existing name
                continue
            unread = _unread_folder_names(where)
            if unread and DEFAULT_RECORD_BRANCH in destinations:
                return RECORD_FOLDER_MATCH + unread
            tags = _own_proved_tags(transcript)
            if (tags is not None and LANE_TAG in tags and len(destinations) == 1 and root
                    and _lane_handoff_holds(args, where, overrides, root, destinations[0], tags)):
                continue
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
ARCHIVE_STEP_PREFIX, ARCHIVE_REPO_PREFIX = STEP_TAG, REPO_TAG
ARCHIVE_CITE = (
    "(decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_NO_RECORD_REASON = (
    "this session's or this agent's transcript holds no get_session record of the target, so the guard cannot tell whether "
    "the target is a lane with records still to land. Run get_session on each target in one message, "
    "then archive them in the next message. " + ARCHIVE_CITE
)
ARCHIVE_OPEN_REASON = (
    "the lane's records pull request is still open, so closing the lane now strands its records. Wait until "
    "that pull request merges or is closed as replaced, then retry. (decision session-tiers, a lane closes only after its records pull request has landed)"
)
ARCHIVE_TAGS_REASON = (
    "the target's record is a lane with no cs-step tag or no cs-repo tag, so the guard cannot find its "
    "records pull request. Fix the lane's tags, run get_session on each target in one message, then archive them in the next message. " + ARCHIVE_CITE
)
# A template: {remedy} is archive_read_remedy's wording.
ARCHIVE_READ_REASON = (
    "the open pull requests of the lane's repo could not be read, so the guard cannot tell whether its "  # glossary-ok: session-tiers is the decision's file name
    "records have landed. {remedy} (decision session-tiers, a lane closes only after its records pull request has landed)"  # glossary-ok: session-tiers is the decision's file name
)
ARCHIVE_NO_PR_REASON = (
    "a branch of the lane is ahead of its repo's default branch and has no pull request that covers it, so closing "
    "the lane now strands that work. Either open a pull request for that branch and hand it to the batch runner, or "
    "push an archive copy of it under archive/, then retry. If the branch was archived under another name, push one "
    "more copy under the stranded branch's own name, archive/<branch> (archive/<branch>-<n> when that is taken), at the branch tip, then retry. "
    + ARCHIVE_CITE
)
# A template, as ARCHIVE_READ_REASON.
ARCHIVE_BRANCH_READ_REASON = (
    "the lane's branches or their pull requests could not be read, so the guard cannot tell whether any work of "  # glossary-ok: session-tiers is the decision's file name
    "the lane is stranded. {remedy} (decision session-tiers, a lane closes only after its records pull request has landed)"  # glossary-ok: session-tiers is the decision's file name
)


_ATTACH_STATUSES = (403, 404)  # the answers of a repo this session cannot read: 403 for an unattached repo (measured), 404 for one gh cannot find


def archive_read_remedy(repo, status) -> str:
    """The remedy of an unreadable archive read. Only a 403 or 404 on the read of `repo` names its add_repo act; every other
    failure (a 500, a timeout, no gh, text that is not JSON, a shape the read does not know) says to retry. The one home of the wording."""
    if repo and status in _ATTACH_STATUSES:
        # Push access, not read: a lane that archives must push an archive/ branch, so a read-only attach would only move the refusal.
        return "This session cannot read that repo until it is attached: add_repo " + repo + " access push, then retry."
    return "Retry once gh answers."


_HTTP_TAIL = re.compile(r"\bHTTP (\d{3})\)?\s*\Z")  # the end of a failed `gh api` reply: "gh: <message> (HTTP 403)"


def _http_status(out: str):
    """The HTTP status that a failed gh reply ends with, or None."""
    match = _HTTP_TAIL.search(out)
    return int(match.group(1)) if match else None


class _GhReadFailed(RuntimeError):
    """A gh read failed. `status` is the HTTP status gh printed, None when the read failed another way (a reply that is no JSON, a shape the read does not know)."""

    def __init__(self, message: str, status=None):
        super().__init__(message)
        self.status = status


class _ArchiveReadFailed(Exception):
    """A gh read of the branch arm failed in `repo` with HTTP `status` (None when it has none), so archive_hit can word the remedy."""

    def __init__(self, repo: str, status=None):
        super().__init__(repo)
        self.repo, self.status = repo, status


def _read_status(module, exc):
    """The HTTP status of a failed read, or None. A network error (NetStop, a rate limit included) has none: it is no answer about the repo."""
    if isinstance(exc, (_ArchiveReadFailed, _GhReadFailed)):
        return exc.status
    if module is not None and isinstance(exc, module.Stop) and not isinstance(exc, module.NetStop):
        return _http_status(str(exc))  # Host.pages raises a Stop whose message ends with the failed reply
    return None


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
    """The parsed JSON of one REST read of `host`; a failed read or a reply that is not JSON raises _GhReadFailed."""
    code, out = host.api(rel)
    try:
        if code:
            raise ValueError(out)
        return json.loads(out)
    except ValueError as e:
        raise _GhReadFailed("the " + what + " read failed: " + str(e), _http_status(out) if code else None)


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
        raise _GhReadFailed("the compare read failed: " + str(e), _http_status(out) if code else None)


def _head_landed(module, repo: str, row) -> bool:
    """True when the head commit of the pull request `row` is already in the repo's default branch: the row's
    base is that branch (base.repo.default_branch, so a draft stacked on another branch is not released), and
    GitHub's compare of default...sha reads behind or identical. A failed read raises, and archive_hit refuses on it.
    The caller holds the one shared deadline over this read (a nested shared_deadline would reset it)."""
    base, sha = str(row["base"]["ref"]), str(row["head"]["sha"])
    if base != str(row["base"]["repo"]["default_branch"]):
        return False
    return _compare_status(module, module.Host(repo=repo), base, sha) in _CONTAINED


def open_pull_rows(module, repo: str):
    """The open pull request rows of `repo`, every page, read through the merge tool's page reader `module` with the
    session's token. The one home of this read: rules lane-closes-after-records and lane-step-dup call it. A repo the
    session has not attached is not read. On the archive caller's 403 or 404 the refusal names the add_repo access push
    (owner, page item 937 b, 14:20 CST Nov 17); step_pr_hit keeps its own STEP_PR_READ_REASON. A failed read raises. The caller holds the one shared deadline over the read (a nested
    shared_deadline would reset it). Cost: one gh call per page."""
    return module.Host(repo=repo).pages("pulls", fields={"state": "open"})


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
    copy_name = re.compile(re.escape(ARCHIVE_PREFIX + branch) + ARCHIVE_COPY_SUFFIX)
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
    archive_hit refuses on it, naming the repo whose read failed (_ArchiveReadFailed). The caller holds one shared deadline over all the reads here (a nested
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
        try:
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
        except (Exception, SystemExit) as exc:
            raise _ArchiveReadFailed(repo, _read_status(module, exc)) from exc

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
    reading = None  # the repo whose read is under way, the one an unreadable read's remedy may name
    module = None
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
                reading = repo
                rows = open_rows[repo] = open_pull_rows(module, repo)
                for row in rows:
                    ref = str(row["head"]["ref"])
                    slug = next((s for s in slugs if ref in lane_head_refs(s)), None)
                    if slug and row.get("draft") is True and _head_landed(module, repo, row):
                        continue
                    if slug:
                        return "archive of lane " + slug + " with open pull request " + str(row.get("number", "?")), ARCHIVE_OPEN_REASON
            reading_branches, reading = True, None
            stranded = _stranded_branch(module, lanes, repos, slugs, open_rows)
    except (Exception, SystemExit) as exc:
        if isinstance(exc, _ArchiveReadFailed):
            reading = exc.repo
        remedy = archive_read_remedy(reading, _read_status(module, exc))
        if reading_branches:
            return "archive with an unreadable branch read", ARCHIVE_BRANCH_READ_REASON.format(remedy=remedy)
        return "archive with an unreadable pull request list", ARCHIVE_READ_REASON.format(remedy=remedy)
    if stranded:
        return ARCHIVE_STRANDED_MATCH, ARCHIVE_NO_PR_REASON
    return None


# ---- send_message: a lane brief goes to a lane of its own topic (rule lane-one-topic)
BRIEF_TOOL = "mcp__claude-code-remote__send_message"
# The first non-blank line of a brief (after its Grant line, if any) starts `Lane brief: <step>. Topic: <topic>.`
# (LANE_BRIEF_MARKER, shared_names).
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


# ---- one lane per step (rule lane-step-dup)
STEP_DUP_TAIL = " (decision session-tiers, a step has one lane)"  # glossary-ok: session-tiers is the decision's file name
STEP_DUP_REASON = (
    "session %s is live and carries cs-step:%s in the same repo, so this would start a second lane on one step. "
    "Send the work to that session with send_message instead." + STEP_DUP_TAIL
)
STEP_DUP_UNKNOWN_REASON = (
    "this session's transcript does not prove that no other live session carries cs-step:%s in this repo: it holds "
    "no whole list_sessions read (a read with no cursor, then reads that each pass the last session id of the page "
    "before as after_id, the last with has_more false, none with tags or mine), the brief's target has no current "
    "record, or the subject has no cs-repo tag. Run list_sessions in its own turn that way, run get_session on the "
    "target alone, check that the target or the new lane carries a cs-repo tag, then retry." + STEP_DUP_TAIL
)


STEP_PR_REASON = (
    "open pull request #%(pr)s of this repo has the head of step %(step)s, so a lane already holds the step. Send the work to "
    "that lane, or say in the brief that it `continues #%(pr)s` or `replaces #%(pr)s`, then retry." + STEP_DUP_TAIL
)
STEP_PR_READ_REASON = (
    "the open pull requests of this repo, or the subject's record, could not be read, so the guard cannot tell whether "
    "a lane pull request holds cs-step:%s. Retry once gh answers and the target has a current record." + STEP_DUP_TAIL
)
_STEP_CONTINUES = re.compile(r"\b(?:continues|replaces)\s+#(\d+)", re.IGNORECASE)  # a brief that names the pull request it takes over


def _tag_values(tags, prefix: str):
    """The lower-cased, non-empty values of the tags that start with `prefix`, stripped."""
    return [v.lower() for v in (str(t)[len(prefix):].strip() for t in tags if str(t).startswith(prefix)) if v]


def _step_call(tool: str, tool_input):
    """(steps, target) of a lane brief (a send_message whose first non-blank line after any Grant line is `Lane brief:
    <step>. Topic: <topic>.`) or of a create_session tagged cs-step:<step>, else None. Steps are lower case; `target`
    is the brief's session id, None for a create."""
    if not isinstance(tool_input, dict):
        return None
    if tool == BRIEF_TOOL:
        message = tool_input.get("message")
        lines = [line.strip() for line in message.splitlines() if line.strip()] if isinstance(message, str) else []
        if lines and lines[0].startswith(LANE_GRANT_MARKER):
            lines = lines[1:]
        found = _BRIEF_LINE.match(lines[0]) if lines and _BRIEF_MARKER_LINE.match(lines[0]) else None
        return ([found.group("step").lower()], tool_input.get("session_id")) if found else None
    if tool == CREATE_SESSION_TOOL:
        tags = tool_input.get("tags")
        steps = _tag_values(tags, ARCHIVE_STEP_PREFIX) if isinstance(tags, list) else []
        return (steps, None) if steps else None
    return None


def _step_subject(tool_input, transcript: str, target):
    """(tags, mine) of the subject of a step call: the create's own tags, or the target's newest record in the
    transcript, and the steps that subject carries. Raises ValueError when a brief's target has no current record."""
    if target is None:
        return tool_input["tags"], []
    tags, tagged_after = _own_session_read(transcript, target, created=True) \
        if transcript and isinstance(target, str) and target else (None, False)
    if tags is None or tagged_after:
        raise ValueError("no current record of the target")
    return tags, _tag_values(tags, ARCHIVE_STEP_PREFIX)


def step_dup_hit(tool: str, tool_input, transcript: str):
    """Return (matched, reason) when this call would put a second live session on a step, else None. The call is a lane
    brief or a create_session tagged cs-step:<step> (_step_call). It is refused when another live session, not the
    brief's target, carries that step and shares a cs-repo tag with the subject (_step_subject); the reason names that
    session. A brief to a target that carries the step itself starts no new lane, so it passes before any list read.
    Steps and tags match without case. A session is live unless its newest row in the transcript's list_sessions reads
    is archived (own_session.list_sessions_read). A session an earlier create_session of this transcript started and no
    archive_session names is live too, when no list row shows it (own_session.created_sessions). A carrier on any page, whole read or not, is refused. With no
    carrier found, no whole list read, a brief whose target has no current record, or a subject with no cs-repo tag is
    refused too: unknown is never an allow, and the guard-wide crash path fails open, so any error here is a refusal.
    Known limit: only this transcript is read, so a session another transcript started after its newest list read is not seen.
    Cost: one transcript read per brief or create with a step, plus one for the target's record; no file written, no
    process, no extra tool call."""
    call = _step_call(tool, tool_input)
    if call is None:
        return None
    steps, target = call
    try:
        subject, mine = _step_subject(tool_input, transcript, target)
        steps = [s for s in steps if s not in mine]
        if not steps:
            return None
        repos = set(_tag_values(subject, ARCHIVE_REPO_PREFIX))
        if not repos:
            raise ValueError("no cs-repo tag")
        rows, whole = own_session.list_sessions_read(transcript)
        live = [(sid, tags) for sid, (tags, archived) in rows.items() if not archived]
        # A session a create_session of this transcript started is no row unless a later read showed it; a row,
        # archived or not, is newer than the create and decides.
        live += [(sid, tags) for sid, tags in own_session.created_sessions(transcript).items() if sid not in rows]
        for sid, tags in live:
            if sid == target:
                continue
            for step in steps:
                if step in _tag_values(tags, ARCHIVE_STEP_PREFIX) and repos & set(_tag_values(tags, ARCHIVE_REPO_PREFIX)):
                    return "lane step " + step + " carried by " + sid, STEP_DUP_REASON % (sid, step)
        if not whole:
            raise ValueError("no whole list read")
    except (Exception, SystemExit):
        return "lane step with no proof", STEP_DUP_UNKNOWN_REASON % steps[0]
    return None


def step_pr_hit(tool: str, tool_input, transcript: str):
    """Return (matched, reason) when this call would start a second lane on a step an open lane pull request holds, else
    None (rule lane-step-dup, part two). The call is a step call (_step_call). An open pull request in a cs-repo of the
    subject whose head is lane_head_refs(step) refuses it, and the reason names the pull request. The brief's own text
    (the message of a brief, the prompt of a create) lifts it when it says `continues #N` or `replaces #N` and N is
    such an open pull request, whichever the list reads first; any other N lifts nothing. A brief to a target that carries the step passes too. The
    read is open_pull_rows, the one reader lane-closes-after-records uses. A failed read, a repo tag that is no
    owner/name, or a brief target with no current record is a refusal: the guard-wide crash path fails open.
    Cost: one paged gh read per cs-repo tag, for each step call."""
    call = _step_call(tool, tool_input)
    if call is None:
        return None
    steps, target = call
    text = tool_input.get("message" if tool == BRIEF_TOOL else "prompt")
    taken = set(_STEP_CONTINUES.findall(text)) if isinstance(text, str) else set()
    try:
        subject, mine = _step_subject(tool_input, transcript, target)
        steps = [s for s in steps if s not in mine]
        if not steps:
            return None
        module = merge_module()
        if module is None:
            raise RuntimeError("the merge tool could not be loaded")
        first = None
        for repo in dict.fromkeys(_tag_values(subject, ARCHIVE_REPO_PREFIX)):
            if not _REPO_NAME.fullmatch(repo):
                raise ValueError("not an owner/name repo tag")
            with module.shared_deadline(MERGE_READ_TIMEOUT):
                pulls = open_pull_rows(module, repo)
            for row in pulls:
                ref = str(row["head"]["ref"]).lower()
                for step in steps:
                    if ref in lane_head_refs(step):
                        if str(row.get("number")) in taken:
                            return None
                        first = first or (row, step)
        if first:
            row, step = first
            return ("lane step " + step + " has open pull request " + str(row.get("number", "?")),
                    STEP_PR_REASON % {"pr": row.get("number", "?"), "step": step})
    except (Exception, SystemExit):
        return "lane step with an unreadable pull request list", STEP_PR_READ_REASON % steps[0]
    return None


# ---- a build spawn names the prior work it searched (rule spawn-searches-existing-builds)
# The line is `Prior work: #N (state) | <branch> | none found`, on a line of its own, with some text after the colon. The
# text is not checked against GitHub: the guard reads the brief only. A line inside a ``` fence is a quoted example and
# does not count. The marker matches without case, after optional markdown lead characters.
PRIOR_WORK_LINE = "Prior work:"
PRIOR_WORK_REASON = (
    "this build spawn has no `Prior work:` line with text after it. Search the open and closed pull requests, the "
    "branches and main for an existing build first, then add one line to the brief: `Prior work: #N (state) | <branch> "
    "| none found`. A bare `Prior work:` line does not count. "
    "(decision spawn-searches-existing-builds, a build spawn names the prior work it searched)"
)
# The colon may sit outside bold (`**Prior work**: x`), and a numbered-list lead (`1. `) may come before the marker.
_PRIOR_WORK_LINE = re.compile(
    r"[-#*_>\s]*(?:\d+[.)]\s+)?[-#*_>\s]*" + re.escape(PRIOR_WORK_LINE[:-1]) + r"[*_]*:[ \t*_]*(?P<text>\S.*)?$",
    re.IGNORECASE)
# An unfilled template placeholder (`<what you searched>`) names nothing.
_PLACEHOLDER = re.compile(r"<[^<>]*>")


def prior_work_named(text) -> bool:
    """True when `text` has a Prior work line with text after the marker, outside a fence. Text that is only angle-bracket
    placeholders does not count."""
    if not isinstance(text, str):
        return False
    fenced = False
    for line in text.split("\n"):
        if opens_fence(line.strip()):
            fenced = not fenced
            continue
        found = None if fenced else _PRIOR_WORK_LINE.match(line.rstrip())
        if found and found.group("text") and _PLACEHOLDER.sub("", found.group("text")).strip(" \t|,;"):
            return True
    return False


def prior_work_lane_hit(tool: str, tool_input):
    """Return (matched, reason) when a lane start or a lane brief names no prior work, else None. A lane start is a
    create_session that tags a lane (its prompt). A lane brief is a send_message whose first non-blank line after any
    Grant line starts the Lane brief marker (its message), read as _step_call reads it. Pure text work: no read, no file.
    The Agent side of the rule is guard.prior_work_agent_hit."""
    if not isinstance(tool_input, dict):
        return None
    if tool == BRIEF_TOOL:
        message = tool_input.get("message")
        lines = [line.strip() for line in message.splitlines() if line.strip()] if isinstance(message, str) else []
        if lines and lines[0].startswith(LANE_GRANT_MARKER):
            lines = lines[1:]
        if not (lines and _BRIEF_MARKER_LINE.match(lines[0])):
            return None
        text, matched = message, "lane brief with no Prior work line"
    elif is_lane_create_session(tool, tool_input):
        text, matched = tool_input.get("prompt"), "lane start with no Prior work line"
    else:
        return None
    return None if prior_work_named(text) else (matched, PRIOR_WORK_REASON)


# ---- A lane brief names a slug or a role, never a session id (rule brief-ids-in-roster)
# A session id as a brief types it, in any case. SESSION_ID_RE (guard_shared_tree) is a full match, so this scans: the id
# is `session_`, a digit, then letters and digits, so a parameter name such as `session_id` is no id, and a `.md`, a dot or
# a dash after the id is not part of it.
_BRIEF_ID = re.compile(r"(?<![A-Za-z0-9_])session_[0-9][A-Za-z0-9]*", re.IGNORECASE)
_DATA_QUOTES = "`\""  # an id with one of these right before it and right after it is data (an incident quote)
# A line that opens a brief: an optional markdown lead, then Grant: or Lane brief:. The lead is _MARKDOWN_LEAD plus the
# list dash, which the other readers of the lead do not take.
_BRIEF_LEAD = r"[-#*_>\s]*"
# The standing sessions' briefs open with a role word (decision brief-ids-in-roster): `Brief:`, `Triage brief:`, `Batch runner brief:`.
ROLE_BRIEF_MARKERS = ("Brief:", "Triage brief:", "Batch runner brief:")
_BRIEF_OPENER = re.compile(_BRIEF_LEAD + r"(?:" + re.escape(LANE_GRANT_MARKER) + r"|(?i:"
                           + "|".join(re.escape(m) for m in (LANE_BRIEF_MARKER,) + ROLE_BRIEF_MARKERS) + r"))")
BRIEF_ID_REASON = (
    "this brief names a session id. A hand-typed id can wake the wrong session or none. Name the lane's slug or the "
    "session's role instead, and the lane looks the id up in the roster. "
    "(decision brief-ids-in-roster, a lane brief names a slug or a role, never a session id)"
)


def _bare_ids_in(text: str) -> list[str]:
    """The ids not wrapped in a quote on both sides. A quote elsewhere on the line hides nothing."""
    bare = []
    for found in _BRIEF_ID.finditer(text):
        before = text[found.start() - 1] if found.start() else ""
        after = text[found.end()] if found.end() < len(text) else ""
        if not (before and before in _DATA_QUOTES and after and after in _DATA_QUOTES):
            bare.append(found.group(0).lower())
    return bare


def brief_roster_hit(tool: str, tool_input, cwd: str):
    """Return (matched, reason) when a session brief names a bare session id, else None. Read: a create_session that tags a
    lane (its prompt), and a send_message with a line that starts LANE_GRANT_MARKER, LANE_BRIEF_MARKER or a role-word
    marker (ROLE_BRIEF_MARKERS), whatever session it goes to (its message). An id inside backticks or double quotes is
    data and passes. The send_message target is judged by target_roster_hit. No git read and no file written: the text alone decides. Fails open on any error in the read. `cwd` is unused; the call site passes it."""
    if not isinstance(tool_input, dict):
        return None
    if tool == BRIEF_TOOL:
        text = tool_input.get("message")
        if not isinstance(text, str) or not any(_BRIEF_OPENER.match(ln) for ln in text.splitlines()):
            return None
    elif is_lane_create_session(tool, tool_input):
        text = tool_input.get("prompt")
    else:
        return None
    if not isinstance(text, str) or "session_" not in text.lower():
        return None
    try:
        bare = _bare_ids_in(text)
    except Exception:
        return None
    if not bare:
        return None
    return "session brief naming " + ", ".join(sorted(set(bare))), BRIEF_ID_REASON


# ---- A send_message goes to an id the roster knows (rule target-id-in-roster)
TARGET_ROSTER_REASON = (
    "the target session id is in no roster source: not in the Standing sessions rows of the roadmap record, and not in "
    "what your own list_sessions, get_session and create_session results show for this repo. A hand-typed id can wake "
    "the wrong session or none. {rows} Copy the id from a row, or run list_sessions (every page, tag cs-repo:<owner>/<name>) "
    "and take it from there, then send again. "
    "(decision brief-ids-in-roster, every session knows the right ids from the harness)"
)
TARGET_UNKNOWN_LINE = ("target-id-in-roster: the roster is unknown (the roadmap record and the transcript could not be "
                       "read), so the target session id is not checked")


def _parent_targets():
    """PARENT_TARGETS of lint/layout.py, the one home of the send targets that name the parent."""
    lint = lint_dir()
    if lint not in sys.path:
        sys.path.append(lint)
    import layout
    return layout.PARENT_TARGETS


def _sender_facts(transcript: str, own_id):
    """(slugs, parent, made) from one read of the sender's transcript. slugs: the owner/name repos named by the cs-repo
    tags of the sender's own newest record, lowercased, or None when that record is unread or carries none. The
    checkout's origin is not used: a session may coordinate one repo from another's checkout, so only its own record
    says which repo its sessions belong to. parent: the parent_session_id of that record, or None. made: the lanes
    the sender created, {id: tags}. Each is empty or None when the transcript does not read."""
    if not (own_id and transcript):
        return None, None, {}
    try:
        tags, parent, made = own_session.own_record_and_created(transcript, own_id)
    except Exception:
        return None, None, {}
    slugs = {t[len(REPO_TAG):].lower() for t in tags or () if isinstance(t, str) and t.startswith(REPO_TAG)}
    return slugs or None, parent, made


def target_roster_hit(tool: str, tool_input, cwd: str, transcript: str = ""):
    """Return (matched, reason) when a send_message names a target session id that is in no roster source, else None.
    The parent alias (layout.PARENT_TARGETS) passes with no read. The roster is the Standing sessions rows of the
    roadmap record (own_session.roster_rows), the sender's parent id (parent_session_id of its own get_session record),
    every lane the sender created whatever its cs-repo tag, and every id the sender's own transcript shows from
    list_sessions, get_session and create_session with a cs-repo tag of the sender's repo (the cs-repo tags of its own
    record; with none read, every sighting counts). A lane has no row, so it counts only when the sender saw or made
    it. The reason prints the record's rows and never the target. Cost: one local git read of the record, two
    transcript reads (own_session.own_record_and_created, own_session.sessions_seen), on a send_message only; no
    network, no file. Fails open with one stderr line when neither source reads, and on any error: the roster is advice
    about an id."""
    if tool != BRIEF_TOOL or not isinstance(tool_input, dict):
        return None
    target = tool_input.get("session_id")
    if not isinstance(target, str) or not target:
        return None
    try:
        from override import remote_session_id
        if target in _parent_targets():
            return None
        text = own_session.roster_record(cwd)
        rows = own_session.roster_rows(text) if text is not None else None
        slugs, parent, made = _sender_facts(transcript, remote_session_id())
        seen = None
        if isinstance(transcript, str) and transcript:
            seen = own_session.sessions_seen(transcript)
        if rows is None and seen is None:
            print(TARGET_UNKNOWN_LINE, file=sys.stderr)
            return None
        known = {row[2] for row in rows or ()} | set(made)
        if parent:
            known.add(parent)
        known |= {sid for sid, tags in seen or () if (slugs is None or any(repo_tag_names(t, s) for t in tags for s in slugs))}
        if target in known:
            return None
        if rows is None:
            listing = "The roadmap record could not be read."
        elif not rows:
            listing = "The roadmap record holds no standing session rows."
        else:
            listing = "The standing sessions: " + "; ".join(
                "%s%s %s" % (role, " " + title if title else "", sid) for role, title, sid in rows) + "."
        return "send_message to a session id in no roster source", TARGET_ROSTER_REASON.format(rows=listing)
    except Exception:
        return None


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


def header_time_hit(tool: str, tool_input):
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
    only for an items write that carries `file_path` and no inline data; no transcript or process. Fails open, like header_time_hit."""
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
