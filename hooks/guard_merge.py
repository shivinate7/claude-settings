"""The guard's merge family: a merge made outside the merge tool, and the git and gh call readers.

guard.py is the only entry point, and it runs these checks in its fixed order (decision
guard-split-by-family). Other files reach these names through `guard`.
"""
import fnmatch
import os

from guard_core import (
    _absolute, _git, _git_subcommand_index, _segment_git_c_target, basename, cap_safe, command_root,
    inline_script, resolve_command, resolve_default_base, segment_tokens, split_segments,
)
from guard_pointer import (
    pointer_checkout,
)


# ------------------------------------------------------------------ three git acts
#
# Each clause below judges the ACT a segment performs, read off its command word (decisions/
# predicate-is-the-act.md), never a substring of the text. `echo git commit`, a `git log`, a
# quoted message and a heredoc body name an act and perform none.
#
# 1. merge-checks (CLAUDE.md `git-wait-for-required-checks`): a merge made outside the merge tool is
#    refused while the head has a check or a workflow run pending or red, or when that read could
#    not run. The merge tool (merge/merge.py) runs its own `gh pr merge` as a subprocess, so no hook
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


def gh_call_of(segment: str):
    """Return the tokens after `gh` when the segment's COMMAND WORD is gh, else None."""
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
    return tokens[index + 1:]


# ---- a merge made outside the merge tool
MERGE_TOOLS = ("mcp__github__merge_pull_request",)
MERGE_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject",
                     "--match-head-commit", "-A", "--author-email"}
# Seconds for the WHOLE read, shared: Host.head_read makes three `gh` calls that split this one
# deadline (merge.py's shared_deadline), each getting whatever of it the earlier calls left. The
# shared deadline bounds a hung `gh` to about 15 s for the whole read (pinned in test_guard.py),
# so a merge with a dead `gh` is denied fast instead of waiting out each call. Measured on
# Windows under load: `pr view` 3.0-3.8 s, `pr checks` 3.6-3.9 s, the runs read 1.3-1.4 s
# (incident 2026-10-03, worst-case sum 9.1 s). 14 s leaves headroom over that sum.
MERGE_READ_TIMEOUT = 14
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


def merge_gate(selector, repo: str, where: str):
    """Return (verdict, detail) for the head of the named pull request: green, pending, red or
    unknown. One read, no wait, run in `where` so `gh` names the repo the command names."""
    module = merge_module()
    if module is None:
        return "unknown", "the merge tool's check reader could not be loaded"
    where = os.path.normpath(where) if where else ""   # a `cd` target may carry either separator
    host = module.Host(repo=repo or None, cwd=where or None)
    return host.head_read(selector, nothing_is_green=not has_workflows(where))


MERGE_GATE_REASON = (
    "Rule (Git): this head is not settled: %s. A merge waits for every check and workflow run on "
    "the head, required or not, and a read that could not run counts as not settled. "
    "Remedy: run the merge tool, `merge <pr> --confirm`, which waits on every check, then "
    "merges the head it waited on."
)


def merge_gate_reason(verdict: str, detail: str) -> str:
    return MERGE_GATE_REASON % (verdict + (" (" + cap_safe(detail, 160) + ")" if detail else ""))


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


# ---- a lane commit of the generated records page (decision records-index-at-merge, ruling of
# 2026-10-16: "Also add a guard"; incident 2026-10-16, three batches conflicted on the page)
#
# The page is rebuilt only at merge. The commit is refused when the page it would hold differs from
# HEAD's page AND from the base tip's page: a merge of the base into the lane brings the base's page,
# so it passes. The base is `resolve_default_base`, read at its TIP (a stale local `main` is not it).
# The hook runs BEFORE the shell chain, so `commit -a`, `commit <page>` and a `git add` that reaches
# the page earlier in the same command read the working tree, and any other commit reads the index.
# Any read that fails is no hit. Limits: a `sh -c` script is not read, and `commit -a` reads the
# working tree even for an untracked page.
RECORDS_PAGE = "docs/records.md"
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
    """Return the page's blob ids at HEAD and at `base`: an id, '' for no page, None for a failed read."""
    out = []
    for rev in ("HEAD", base):
        done = _git(top, "ls-tree", rev, "--", RECORDS_PAGE)
        if done is None or done.returncode != 0:
            out.append(None)
        else:
            out.append(done.stdout.split()[2] if done.stdout.strip() else "")
    return out


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
    """Return the commit when it would hold a records page that is neither HEAD's nor the base
    tip's, else ''. Each segment is judged from its own command word."""
    staged = False   # an earlier `git add` in this command reaches the page
    for segment in split_segments(stripped):
        call = git_call_of(segment) if segment.strip() else None
        if call is None or call[0] not in ("add", "commit"):
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
        base = resolve_default_base(top)
        if base is None:
            continue
        head_id, base_id = _page_ids(top, base)
        if head_id is None or not base_id:   # a failed read, or a base with no page: no hit
            continue
        page_id = _commit_page_id(top, staged or all_flag or _names_page(specs, where, top))
        if page_id is not None and page_id not in (head_id, base_id):
            return "git commit " + RECORDS_PAGE
    return ""


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
