"""The guard's merge family: a merge made outside the merge tool, and the git and gh call readers.

guard.py is the only entry point, and it runs these checks in its fixed order.
Other files reach these names through `guard`.
"""
import fnmatch
import json
import os
import re
import sys

from guard_core import (
    _absolute, _git, _git_subcommand_index, _segment_git_c_target, basename, cap_safe, command_root, GIT_WORK_TREE_RE,
    dir_before_segment, git_calls, inline_script, inner_commands, resolve_command, resolve_default_base, role_key, segment_tokens, split_segments,
    strip_heredoc_bodies,
    _checkout_root_by_stat, _git_common_dir, is_proxy_origin,
)
import own_session  # the one home of the own get_session read, small so report_guard imports it too
from shared_names import BUILD_TAG, LANE_TAG, TOPIC_TAG, lane_head_refs, marker_hits  # the one home of the lane tags and head refs, shared with the roadmap build
from guard_pointer import (
    pointer_checkout,
)
from guard_push_delete import (
    push_destinations, push_refspecs, push_target, push_text,
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
    caller, which read the first two words. The flag moves to the end: gh reads `-R` after the
    verb the same, and the callers that look for the repo (merge_call_of, ci_wake) already read
    it there.
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
    rest, root = tokens[index + 1:], []
    while rest and _gh_root_repo_flag(rest, 0):
        taken = _gh_root_repo_flag(rest, 0)
        root += rest[:taken]
        rest = rest[taken:]
    return rest + root


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
        if arg in ("-R", "--repo"):
            repo = args[index] if index < len(args) else ""
            index += 1
        elif arg.startswith("--repo="):
            repo = arg[len("--repo="):]
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


# ---- a lane commit of the generated records page (decision records-index-at-merge)
#
# The page is rebuilt only at merge. The commit is refused when the page it would hold differs from
# HEAD's page, the base tip's page AND origin/<base>'s page: a merge of the base into the lane brings
# the base's page, so it passes. The base is `resolve_default_base`, read at its TIP.
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
    """Return the commit when it would hold a records page that is none of HEAD's, the base tip's
    and origin/<base>'s, else ''. Each segment is judged from its own command word."""
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


def _push_hit(segment, stripped, cwd, args):
    """Return the first file a `git push` would send with all three conflict markers, else ''. For each
    ref the push names, the range is the merge base with the destination's remote-tracking tip
    (`refs/remotes/<remote>/<dest>`, the named remote else origin), else the source's upstream, else the
    default base, up to the local source ref. A source that does not resolve (a `$(...)`, a backtick, a
    glob, a typo) is read as HEAD. The range comes from the arguments alone: in the usual case one
    `git diff --check`, with no read of the top folder, the source or a base first."""
    named = push_refspecs(args)
    where, overrides = push_target(segment, stripped, cwd)
    if named is None or not where or not os.path.isdir(where):
        return ""
    specs = named[1] or [""]
    dests = push_destinations(args, where, overrides)
    memo = {}
    for spec, dest in zip(specs, dests):
        source, colon, _target = spec.lstrip("+").partition(":")
        if colon and not source:
            continue
        source = _plain_source(source)
        tracking = ("refs/remotes/%s/%s" % (named[0] or "origin", dest)) if dest else ""
        done, source = _checked_range(where, source, tracking, memo)
        if done is None:
            continue
        name = _triplet_file(_kinds_of(done, where, source))
        if name:
            return name
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
    `true`, `false` or `cd` (the root already resolves through a cd). A commit is judged on its own, so
    the caller never asks about one."""
    call = git_call_of(segment)
    if call is not None:
        return call[0] == "add" or call[0] in _READ_VERBS
    tokens = segment_tokens(segment) or []
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


def conflict_markers_hit(stripped: str, cwd: str):
    """Return `(kind, file)` for the first commit or push that would carry all three conflict markers
    in one file, else `('', '')`. The kind is `commit`, `push`, or `chain` (a push after a commit the
    guard could not judge; the file is then `git push`). Each segment is judged from its own command
    word."""
    whole_tops, add_specs = set(), []   # tops an earlier add stages whole / (where, top, specs) of earlier adds
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
        done = _git(where, "rev-parse", "--show-toplevel") if where and os.path.isdir(where) else None
        if done is None or done.returncode != 0 or not done.stdout.strip():
            continue
        top = os.path.normpath(done.stdout.strip())
        if call[0] == "add":
            whole, specs = _add_shape(call[1])
            if whole or _unresolved(specs):
                whole_tops.add(top)
            elif specs:
                add_specs.append((where, top, specs))
            continue
        wholes, adds = whole_tops, add_specs   # this commit takes the adds so far; the next starts clean
        whole_tops, add_specs = set(), []
        all_flag, specs = _commit_shape(call[1]) if call[0] == "commit" else (False, [])
        head = _git(top, "rev-parse", "--verify", "-q", "HEAD")   # no HEAD: `git diff` would read an empty tree
        if head is None or head.returncode != 0:
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
ROLE_TIERS = ("batch-runner",)
ROLE_TAG_PREFIX = BUILD_TAG
ROLE_REASON = (
    "merge-role-proof: this session's own record does not prove the merge tier it claims. "
    "If this session is the batch runner: run get_session (no argument) alone in its own "
    "turn, then retry. Any other session, the coordinator too: post the review record on the PR for your branch; the batch runner finds it "
    "(list_sessions, tag cs-build:batch-runner, same cs-repo, names the runner)."
)


def role_call_of(segment: str):
    """Return the tier word after the role flag when the segment runs the merge tool with it, else None.

    The command word is the shim (`merge`, `~/.claude/bin/merge`, `bin/merge`) or python on
    `merge/merge.py` or `merge/launch.py`. A role flag with no value gives ''.
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
        rest = rest[rest.index(script) + 1:]
    elif word != "merge":
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
                if tier in ROLE_TIERS and tags is not None and ROLE_TAG_PREFIX + tier in tags:
                    continue
        except Exception:
            pass
        return "merge role " + tier
    return ""


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


def _command_words(args):
    """`args` up to the end of their command. The segment splitter cuts at `&&`, `||`, `;`, `|` and a
    newline, but not at `(`, `)` or a lone `&`. A `)` glued to a word closes the subshell the command
    sits in, and a glued `&` sends it to the background: either ends that word and the command."""
    words = []
    for arg in args:
        word = arg.rstrip(")&")
        if word != arg:
            if word:
                words.append(word)
            break
        words.append(arg)
    return words


def _push_calls(segment: str, script: str, cwd: str):
    """(arguments, directory, config overrides) of each `git push` in one segment, and in the scripts the
    segment hands on (`bash -c`, `sh -lc`, `eval`, `ssh`): the one reader of those wrappers is inner_commands.
    `script` is the text the segment came from, which push_target reads for a leading `cd`. A script
    runs in the folder its segment's own `cd` or `git -C` names."""
    for subcommand, args in git_calls(push_text(segment)):
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
    "this session's transcript holds no get_session record of the target, so the guard cannot tell whether "
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
_REPO_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


def _head_landed(module, repo: str, row) -> bool:
    """True when the head commit of the pull request `row` is already in the repo's default branch: the row's
    base is that branch (base.repo.default_branch, so a draft stacked on another branch is not released), and
    GitHub's compare of default...sha reads behind or identical. A failed read raises, and archive_hit refuses on it."""
    base, sha = str(row["base"]["ref"]), str(row["head"]["sha"])
    if base != str(row["base"]["repo"]["default_branch"]):
        return False
    with module.shared_deadline(MERGE_READ_TIMEOUT):
        code, out = module.Host(repo=repo).api("compare/" + base + "..." + sha)
    try:
        if code:
            raise ValueError(out)
        return json.loads(out)["status"] in ("behind", "identical")
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError("the compare read failed: " + str(e))


def archive_hit(tool: str, tool_input, transcript: str):
    """Return (matched, reason) when this archive call must be refused, else None. A target whose newest
    get_session record in this session's transcript has no cs-build:lane tag passes. A lane is refused
    while any open pull request of its cs-repo has a head ref in lane_head_refs of its cs-step slug, except an open draft whose
    head commit is already in its base (compare: behind or identical). Fails closed:
    any error in the reads is a refusal, because the guard-wide crash path fails open."""
    if tool != ARCHIVE_TOOL:
        return None
    target = tool_input.get("session_id") if isinstance(tool_input, dict) else None
    try:  # cost: one transcript read per archive call
        tags = _own_get_session_tags(transcript, target) if transcript and isinstance(target, str) and target else None
    except Exception:
        tags = None
    if tags is None:
        return "archive with no record of the target", ARCHIVE_NO_RECORD_REASON
    if ARCHIVE_LANE_TAG not in tags:
        return None
    slugs = [str(t)[len(ARCHIVE_STEP_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_STEP_PREFIX)]
    repos = [str(t)[len(ARCHIVE_REPO_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_REPO_PREFIX)]
    slugs, repos = [x for x in slugs if x], [x for x in repos if x]
    if not slugs or not repos or not all(_REPO_NAME.fullmatch(r) for r in repos):
        return "archive of a lane with no step or repo tag", ARCHIVE_TAGS_REASON
    try:  # cost: one paged gh REST read per cs-repo tag (one in practice), through the merge tool's page reader
        module = merge_module()
        if module is None:
            raise RuntimeError("the merge tool could not be loaded")
        for repo in repos:
            with module.shared_deadline(MERGE_READ_TIMEOUT):
                rows = module.Host(repo=repo).pages("pulls", fields={"state": "open"})
            for row in rows:
                ref = str(row["head"]["ref"])
                slug = next((s for s in slugs if ref in lane_head_refs(s)), None)
                if slug and row.get("draft") is True and _head_landed(module, repo, row):
                    continue
                if slug:
                    return "archive of lane " + slug + " with open pull request " + str(row.get("number", "?")), ARCHIVE_OPEN_REASON
    except (Exception, SystemExit):
        return "archive with an unreadable pull request list", ARCHIVE_READ_REASON
    return None


# ---- send_message: a lane brief goes to a lane of its own topic (rule lane-one-topic)
BRIEF_TOOL = "mcp__claude-code-remote__send_message"
LANE_BRIEF_MARKER = "Lane brief:"  # the first non-blank line of a brief starts `Lane brief: <step>. Topic: <topic>.`
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


def brief_hit(tool: str, tool_input, transcript: str):
    """Return (matched, reason) when this send_message is a lane brief for a topic the target lane does not
    hold, else None. Only a message whose first non-blank line starts with LANE_BRIEF_MARKER is read; the
    transcript is read for that message alone. A target whose newest record (get_session, or the
    create_session that made it) has no cs-build:lane tag passes. A lane with a cs-topic tag is judged by the
    brief's Topic, an older lane without one by the brief's step against its cs-step tags. Fails closed: any
    error in the reads is a refusal, because the guard-wide crash path fails open."""
    if tool != BRIEF_TOOL or not isinstance(tool_input, dict):
        return None
    message = tool_input.get("message")
    first = next((line.strip() for line in message.splitlines() if line.strip()), "") if isinstance(message, str) else ""
    if not _BRIEF_MARKER_LINE.match(first):
        return None
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
    found = _BRIEF_LINE.match(first)
    step, topic = (found.group("step"), found.group("topic")) if found else (None, None)
    topics = [str(t)[len(TOPIC_TAG_PREFIX):].strip() for t in tags if str(t).startswith(TOPIC_TAG_PREFIX)]
    topics = [t for t in topics if t]
    if topics:
        if (topic or "").lower() not in [t.lower() for t in topics]:
            return "lane brief for topic " + str(topic) + " to a lane on " + ", ".join(topics), BRIEF_TOPIC_REASON
        return None
    steps = [str(t)[len(ARCHIVE_STEP_PREFIX):].strip() for t in tags if str(t).startswith(ARCHIVE_STEP_PREFIX)]
    if step not in steps:
        return "lane brief for step " + str(step) + " to a lane with no topic tag", BRIEF_STEP_REASON
    return None


# ---- the review record after a round (rule review-record-after-round, decision pr-review-record)
RECORD_SPAWN_TOOLS = ("Agent", "Task")
RECORD_REVIEWER_ROLES = ("reviewer", "design-reviewer")  # a spawn of one of these is a round
RECORD_TRIGGER_ROLES = ("builder", "test-author")  # a spawn of one of these, or a send_message, moves past the round
RECORD_COMMENT_TOOL = "mcp__github__add_issue_comment"
# The remedy's merge call takes the flags merge/merge.py's --review-record takes (its usage line and argparse), each as a placeholder.
REVIEW_RECORD_CALL = "merge <pr> --review-record --head <sha> --kind <kind> --guard <yes|no> --round <n>:<role>:<model>:<verdict>"
REVIEW_RECORD_REASON = (
    "review-record-after-round: the last reviewer spawn in this session has no review record after it, so the "
    "round is not on the pull request yet. Run `" + REVIEW_RECORD_CALL + "` with the reviewed sha, post the body "
    "it prints with the GitHub comment tool (add_issue_comment), then retry. "
    "(decision pr-review-record, a lane posts the record after each round)"
)
REVIEW_RECORD_DESIGN_NOTE = (
    " The last reviewer spawn was a design-reviewer: add its line, `Round <n>: design-reviewer, <model>, <verdict>`, "
    "to that round's record, with `" + REVIEW_RECORD_CALL.replace("<role>", "design-reviewer") + "`."
)
REVIEW_RECORD_DESIGN_REASON = REVIEW_RECORD_REASON + REVIEW_RECORD_DESIGN_NOTE


def _transcript_reader():
    """lint/_transcript.py, the one home of the transcript readers, found beside this file's folder."""
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint")
    if lint not in sys.path:
        sys.path.insert(0, lint)
    import _transcript
    return _transcript


def _is_spawn_of(use, roles) -> bool:
    given = use.get("input")
    return (use.get("name") in RECORD_SPAWN_TOOLS and isinstance(given, dict)
            and role_key(given.get("subagent_type")) in roles)


_COMMENT_PATH = re.compile(r"(?:^|/)(?:issues|pulls)/[^/\s]+/comments/?$")
_GH_BODY_FLAGS = ("-b", "--body")
_GH_FILE_FLAGS = ("-F", "--body-file")
_API_FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field")


def _flag_values(args, flags):
    """The values given for `flags` in `args`: `-b v`, `--body v`, `--body=v`, and a glued `-bv` of a short flag."""
    found = []
    for i, arg in enumerate(args):
        for flag in flags:
            if arg == flag and i + 1 < len(args):
                found.append(args[i + 1])
            elif flag.startswith("--") and arg.startswith(flag + "="):
                found.append(arg[len(flag) + 1:])
            elif not flag.startswith("--") and arg.startswith(flag) and len(arg) > len(flag):
                found.append(arg[len(flag):])
    return found


def _gh_posts_record(args, marker) -> bool:
    """True when the gh call (the tokens after `gh`) posts a PR or issue comment that holds the marker. An inline
    body must carry the marker. A body read from a file or stdin counts on its shape, because the guard cannot read it."""
    if args[:2] in (["pr", "comment"], ["issue", "comment"]):
        return bool(_flag_values(args, _GH_FILE_FLAGS)) or any(marker in body for body in _flag_values(args, _GH_BODY_FLAGS))
    if args[:1] != ["api"] or not any(_COMMENT_PATH.search(arg) for arg in args[1:]):
        return False
    if "--input" in args or any(a.startswith("--input=") for a in args):
        return True   # the whole request body comes from a file
    for field in _flag_values(args, _API_FIELD_FLAGS):
        name, _, value = field.partition("=")
        if name == "body":
            return value.startswith("@") or marker in value
    return False


def _bash_posts_record(command, marker) -> bool:
    """True when one segment of the command is a gh call that posts a review record comment. A segment that only
    names the marker (a grep, an echo) is no post. Segments come from the guard's own quote-aware splitter."""
    for segment in split_segments(command):
        args = gh_call_of(segment)
        if args and _gh_posts_record(args, marker):
            return True
    return False


def _posts_record(use, marker) -> bool:
    given = use.get("input")
    if not isinstance(given, dict):
        return False
    name = use.get("name")
    if name == RECORD_COMMENT_TOOL:
        body = given.get("body")
        return isinstance(body, str) and marker in body
    command = given.get("command")
    return name == "Bash" and isinstance(command, str) and _bash_posts_record(command, marker)


_ASYNC_LAUNCH = "Async agent launched successfully"
_LAUNCH_AGENT = re.compile(r"agentId:\s*(\S+)")
_NOTICE_TASK = re.compile(r"<task-id>\s*([^<\s]+)\s*</task-id>")
_NOTICE_COMPLETED = re.compile(r"<status>\s*completed\s*</status>")


def _spawn_events(reader, records):
    """(events, launched, done) from the main-session records, in order. `events` holds ("use", tool_use) and
    ("done", agent_id) entries, one per call and one per completion notice. `launched` maps a spawn's tool_use id to
    the agentId its launch result names, for a background spawn only. `done` maps an agentId to the position of
    its last completion notice in `events`. A notice is a task-notification block in a queued_command attachment
    (whatever the record's type) or a user line (`owner_text`); it is keyed on its task-id, never its tool-use-id, which changes on resume."""
    events, launched, done = [], {}, {}
    for rec in records:
        for use in reader.tool_uses(rec):
            events.append(("use", use))
        for res in reader.tool_results(rec):
            text = reader.result_text(res)
            found = _LAUNCH_AGENT.search(text)
            if _ASYNC_LAUNCH in text and found and isinstance(res.get("tool_use_id"), str):
                launched[res["tool_use_id"]] = found.group(1)
        att = rec.get("attachment")
        text = att.get("prompt") if isinstance(att, dict) and att.get("type") == "queued_command" else reader.owner_text(rec)
        for part in (text or "").split("<task-notification>")[1:]:
            task = _NOTICE_TASK.search(part)
            if task and _NOTICE_COMPLETED.search(part):
                events.append(("done", task.group(1)))
                done[task.group(1)] = len(events) - 1
    return events, launched, done


def _anchor_at(index, use, launched, done):
    """The position in the events after which a record must be posted for the reviewer spawn at `index`. A
    foreground spawn counts at its own position. A background spawn counts at its agent's completion notice, and
    anchors nothing while the notice is missing."""
    agent = launched.get(use.get("id"))
    return index if agent is None else done.get(agent)


def review_record_hit(tool: str, tool_input, transcript: str, agent: bool = False):
    """(reason, matched, unknown): the refusal when this builder or test-author spawn, or this send_message (the
    remote tool or the built-in SendMessage), comes after the session's last completed reviewer spawn and no later call posted
    a review record, else ("", "", unknown). A reviewer spawn whose result is an error never ran and anchors nothing.
    A background spawn counts when its completion notice arrives, a foreground spawn at once.
    `unknown` is true when the merge tool (the home of the record marker) could not be loaded: the call is
    allowed and the caller notes it. A call with an agent_id is an agent's and is not judged. A missing or
    unreadable transcript allows. Cost: one transcript read per judged call, no subprocess, no network; the merge
    tool is loaded once, and only when a reviewer spawn is found."""
    if agent or not isinstance(tool_input, dict) or not transcript:
        return "", "", False
    try:
        reader = _transcript_reader()
        judged = tool in reader.SEND_TOOLS or (tool in RECORD_SPAWN_TOOLS and role_key(tool_input.get("subagent_type")) in RECORD_TRIGGER_ROLES)
        if not judged:
            return "", "", False
        records = [rec for rec in reader.read_transcript(transcript) if not rec.get("isSidechain")]
        failed = reader.failed_tool_use_ids(records)
        events, launched, done = _spawn_events(reader, records)
    except Exception:
        return "", "", False
    anchors = [(_anchor_at(i, ev[1], launched, done), ev[1]) for i, ev in enumerate(events)
               if ev[0] == "use" and _is_spawn_of(ev[1], RECORD_REVIEWER_ROLES) and ev[1].get("id") not in failed]
    anchors = [g for g in anchors if g[0] is not None]
    if not anchors:
        return "", "", False
    anchor, last = max(anchors, key=lambda g: g[0])
    try:
        marker = merge_module().REVIEW_MARKER
    except Exception:
        marker = None
    if not isinstance(marker, str) or not marker:
        return "", "", True
    if any(_posts_record(ev[1], marker) for ev in events[anchor + 1:] if ev[0] == "use"):
        return "", "", False
    matched = "%s after a reviewer spawn with no review record" % tool
    if role_key(last["input"].get("subagent_type")) == "design-reviewer":
        return REVIEW_RECORD_DESIGN_REASON, matched, False
    return REVIEW_RECORD_REASON, matched, False


# ---- a reviewer brief names its pull request (rule review-needs-pr, decision pr-review-record)
# An orchestrator's spawn of `reviewer` must name the pull request it reviews; a `design-reviewer` spawn must when its
# brief carries a round marker. Between the PR word and the number, on one line, the form may hold space, tab, hyphen, `#`, `:`, `(`,
# markdown bold or code marks, and the word `number`; a letter other than that word breaks it ("a PR will follow").
NEEDS_PR_NAMED = re.compile(
    r"(?:\bPRs?|\bpull\s+requests?)(?:[ \t\-#:(*_`]|\bnumber\b)*\d+|github\.com/[^/\s]+/[^/\s]+/pull/\d+",
    re.IGNORECASE)
NEEDS_PR_REMOTE_URL = re.compile(r"(?:^|[/@])github\.com[:/]", re.IGNORECASE)
NEEDS_PR_REASON = (
    "review-needs-pr: this reviewer brief names no pull request. Name the pull request in the brief (`PR #<n>`; "
    "open the draft pull request first), so each round's review record can post. For a read with no pull request, "
    "spawn the Plan or Explore role. "
    "(decision pr-review-record, a lane posts the record after each round)"
)


def _has_github_remote(folder: str) -> bool:
    """True when the config of the checkout holding FOLDER has a remote whose url names github.com (https or
    scp form) or is the cloud proxy origin (git_reads.is_proxy_origin). A linked worktree reads the common config. No checkout, no config or an unreadable one is False.
    Cost: a stat walk and one config file read, no subprocess, no network."""
    try:
        root = _checkout_root_by_stat(os.path.realpath(folder))
        common = _git_common_dir(root) if root else ""
        if not common:
            return False
        with open(os.path.join(common, "config"), encoding="utf-8") as handle:
            lines = handle.read(1 << 20).splitlines()
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    in_remote = False
    for line in lines:
        line = line.strip()
        if line.startswith("["):
            in_remote = re.match(r"\[remote\s+\"", line, re.IGNORECASE) is not None
        elif in_remote:
            found = re.match(r"url\s*=\s*(.+)$", line, re.IGNORECASE)
            url = found.group(1).strip().strip('"') if found else ""
            if url and (NEEDS_PR_REMOTE_URL.search(url) or is_proxy_origin(url)):
                return True
    return False


def review_needs_pr_hit(tool: str, tool_input, cwd: str, agent: bool = False):
    """(reason, matched): the refusal when an orchestrator's Agent or Task spawn of a reviewer or design-reviewer
    names no pull request, in a repo with a github.com remote, else ("", ""). A reviewer is judged with or without a
    round marker (BRIEF_MARKERS kind round); a design-reviewer only with one. A call with an agent_id
    is an agent's and is not judged. No cwd, or a repo with no readable github remote, allows."""
    if agent or tool not in RECORD_SPAWN_TOOLS or not isinstance(tool_input, dict) or not cwd:
        return "", ""
    role = role_key(tool_input.get("subagent_type"))
    if role not in RECORD_REVIEWER_ROLES:
        return "", ""
    prompt = tool_input.get("prompt")
    if role != "reviewer" and not any(kind == "round" for kind, _ in marker_hits(prompt)):
        return "", ""
    if isinstance(prompt, str) and NEEDS_PR_NAMED.search(prompt):
        return "", ""
    if not _has_github_remote(cwd):
        return "", ""
    return NEEDS_PR_REASON, "%s of a %s with no pull request in the brief" % (tool, tool_input.get("subagent_type"))


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
