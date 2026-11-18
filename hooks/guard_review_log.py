"""The guard's review-log family: a review log posted as a PR comment must be one the merge tool reads.

guard.py is the only entry point, and it runs these checks in its fixed order. Other files reach these names
through `guard`. The form of the log has one home, merge/merge.py (`parse_review`, `REVIEW_MARKER`, `REVIEW_SHA`),
read through guard_merge.merge_module. This module copies none of it.

Two rules judge three paths that post a comment: the GitHub add and update comment tools, a Bash `gh pr comment`
(its `--body` or `-b` word), and a Bash `gh api` call (a `body=` field). Each judges only a body whose first line
starts with the marker (a one-line body that holds a literal backslash and n is judged too):
  review-log-form  parse_review(body) is None.
  review-log-sha   a 40-hex sha on a Head or Fix check line does not resolve in the call's checkout. Judged only when
                   the call's owner and repo are the checkout's origin repo, or either is unknown.
A Bash body is read when the command line holds it as a plain word, or as a quoted heredoc: `--body "$(cat <<'EOF'`
or `-F body=@-` fed by a heredoc. A body that is a variable, another `$(...)` or a file (`--body-file`) is not read,
so it is not judged: a recorded limit.
Cost: the merge tool loads at most once per guard process, and only for a call that posts a comment body. A body with no
marker reads no git. A body with the marker runs at most one `git rev-parse` (the work-tree check), at most one
`git remote get-url` (only when the call names its repo) and at most one `git cat-file` per distinct sha, each
bounded by git_reads._git's 10 s limit. A read that cannot run allows (decision review-log-hand-form).
"""
import re

from guard_core import (HEREDOC_HEADER, SHELL_TOOLS, _git, _inside_work_tree, _split_heredocs, segment_tokens,
                        split_segments)
from guard_merge import gh_call_of, merge_module
from git_reads import github_repo, origin_slug

REVIEW_COMMENT_TOOLS = ("mcp__github__add_issue_comment", "mcp__github__update_issue_comment")

REVIEW_CITE = ("(decision review-log-hand-form, a hand-typed review log that the merge tool cannot read "
               "blocks the merge)")
# The merge tool prints the one readable form of the log. The flag name is the tool's own.
REVIEW_REMEDY = "Run `merge N --review-record --head SHA ...` and post the text it prints as it is."  # glossary-ok: the flag's name
REVIEW_FORM_REASON = (
    "This comment opens with the review log marker, but the merge tool cannot read its body, so the merge would "
    "stop on it. Do not type a review log by hand. " + REVIEW_REMEDY + " That printed text is the one source of "
    "review log text. " + REVIEW_CITE)
REVIEW_FETCH = "The commit may be on origin: fetch the branch (`git fetch origin <branch>`), then post again."
REVIEW_SHA_REASON = (
    "A sha on a head line of this review log names no commit in this checkout, so the log would record a review "
    "of a head that does not exist. Use the sha of the head the review read. " + REVIEW_FETCH + " " + REVIEW_REMEDY +
    " " + REVIEW_CITE)


def _review_log_lines(body: str, marker: str):
    """The lines of a review log, up to the `---` line that ends it, or None when the first line does not start with
    the marker. A body written with a literal backslash and n is one line, so it is judged by that line."""
    lines = body.splitlines()
    if not lines or not lines[0].startswith(marker):
        return None
    return lines[:lines.index("---")] if "---" in lines else lines


def _unresolved(lines, sha_pattern: str, where: str):
    """The first sha on a Head or Fix check line that names no commit in the checkout `where`, else ''. A check
    that cannot run (no git, or no git tree at `where`) names none."""
    shas = []
    for line in lines:
        found = re.match(r"(?:Head|Fix check): (%s)\b" % sha_pattern, line, re.ASCII)
        if found and found.group(1) not in shas:
            shas.append(found.group(1))
    if not shas or _inside_work_tree(where) is not True:
        return ""
    for sha in shas:
        done = _git(where, "cat-file", "-e", sha + "^{commit}")
        if done is None:
            return ""
        if done.returncode != 0:
            return sha
    return ""


def _field_value(arg: str, following: str):
    """The `name=value` text a `gh api` field flag carries: `-f v`, `-fv`, `--field v` or `--field=v`, else ''."""
    if arg in ("-f", "-F", "--field", "--raw-field"):
        return following
    if arg.startswith(("--field=", "--raw-field=")):
        return arg.split("=", 1)[1]
    if arg[:2] in ("-f", "-F") and not arg.startswith("--"):
        return arg[2:]
    return ""


def _gh_comment_body(rest):
    """The body a `gh pr comment` or `gh api` call posts (`rest` is its tokens after `gh`), else None. A `gh api`
    field `body=@-` reads stdin, so its value is `@-`."""
    if rest[0] == "pr" and len(rest) > 1 and rest[1] == "comment":
        for index, arg in enumerate(rest):
            if arg in ("--body", "-b") and index + 1 < len(rest):
                return rest[index + 1]
            if arg.startswith("--body="):
                return arg[len("--body="):]
    elif rest[0] == "api":
        for index, arg in enumerate(rest):
            value = _field_value(arg, rest[index + 1] if index + 1 < len(rest) else "")
            if value.startswith("body="):
                return value[len("body="):]
    return None


_PR_URL = re.compile(r"github\.com/([^/\s]+/[^/\s]+)/(?:pull|issues)/\d+")
_API_PATH = re.compile(r"^/?repos/([^/\s{}]+/[^/\s{}]+)/")


def _gh_repo(rest):
    """The `owner/name` a `gh pr comment` or `gh api` call names (`-R`, `--repo`, a pull request URL, or a
    `repos/owner/name/` path), else None: the call then acts on the checkout's own repo."""
    for index, arg in enumerate(rest):
        if arg in ("-R", "--repo") and index + 1 < len(rest):
            return origin_slug(rest[index + 1])
        if arg.startswith("--repo="):
            return origin_slug(arg[len("--repo="):])
        found = _PR_URL.search(arg) if rest[0] == "pr" else _API_PATH.match(arg) if rest[0] == "api" else None
        if found:
            return found.group(1)
    return None


def _heredoc_reads_body(header: str):
    """The tokens after `gh` of the command a heredoc header opens, when that command reads its body from the heredoc
    (`--body "$(cat <<'EOF'`, or a `gh api` `body=@-` field), else None. The header line is read with the heredoc
    mark dropped; the `"$(cat` that held the mark is read as the stdin word `@-`."""
    line = re.sub(r'"\$\(\s*cat\s*$', "@-", HEREDOC_HEADER.sub("", header, count=1).rstrip())
    for segment in split_segments(line):
        rest = gh_call_of(segment) if segment.strip() and segment_tokens(segment) is not None else None
        if rest and _gh_comment_body(rest) == "@-":
            return rest
    return None


def _shell_bodies(command: str):
    """The (body, repo) pairs that the segments of a shell command post through `gh`, in order. A body is a plain
    word, or the text of a heredoc that the command reads. The repo is the one the call names, else None."""
    bodies = []
    for segment in split_segments(command):
        if not segment.strip() or segment_tokens(segment) is None:
            continue
        rest = gh_call_of(segment)
        body = _gh_comment_body(rest) if rest else None
        if body is not None and body != "@-":
            bodies.append((body, _gh_repo(rest)))
    if "<<" in command:
        for _, text, header in _split_heredocs(command)[1]:
            rest = _heredoc_reads_body(header)
            if rest:
                bodies.append((text, _gh_repo(rest)))
    return bodies


def _bodies(tool: str, tool_input):
    """The (body, repo) pairs a call posts: the comment tools' `body`, or the bodies of the `gh` words in a shell
    command."""
    if tool in REVIEW_COMMENT_TOOLS:
        body = tool_input.get("body")
        owner, name = tool_input.get("owner"), tool_input.get("repo")
        repo = "%s/%s" % (owner, name) if isinstance(owner, str) and isinstance(name, str) and owner and name else None
        return [(body, repo)] if isinstance(body, str) else []
    command = tool_input.get("command")
    if tool in SHELL_TOOLS and isinstance(command, str):
        return _shell_bodies(command)
    return []


def _other_repo(repo, where: str) -> bool:
    """True when the call names a repo and `where` is a checkout of a different one. An unknown on either side
    is False: the sha is then judged, as it was before the repo was read."""
    if not repo:
        return False
    mine = github_repo(where)
    return bool(mine) and mine.lower() != repo.lower()


def review_log_hit(tool: str, tool_input, cwd: str):
    """(rule, reason, matched) for a comment call whose review log is refused, else None. The form is judged
    first: a body the merge tool cannot read needs no sha read."""
    if not isinstance(tool_input, dict):
        return None
    bodies = _bodies(tool, tool_input)
    merge = merge_module() if bodies else None
    if merge is None:
        return None
    for body, repo in bodies:
        lines = _review_log_lines(body, merge.REVIEW_MARKER)
        if lines is None:
            continue
        if merge.parse_review(body) is None:
            shown = (lines[1] if len(lines) > 1 else "marker alone")[:100]
            return "review-log-form", REVIEW_FORM_REASON, "unreadable review log: " + shown
        if _other_repo(repo, cwd):
            continue   # a sha of another repo's branch names no commit here
        sha = _unresolved(lines, merge.REVIEW_SHA, cwd)
        if sha:
            return "review-log-sha", REVIEW_SHA_REASON, "unresolved sha " + sha
    return None

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
