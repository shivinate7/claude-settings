"""The guard's review-record family: a review log posted as a PR comment must be one the merge tool reads.

guard.py is the only entry point, and it runs these checks in its fixed order. Other files reach these names
through `guard`. The form of the log has one home, merge/merge.py (`parse_review`, `REVIEW_MARKER`, `REVIEW_SHA`),
read through guard_merge.merge_module. This module copies none of it.

Two rules judge the GitHub add and update comment tools, only for a body whose first line is the marker:
  review-record-form  parse_review(body) is None.
  review-record-sha   a 40-hex sha on a Head or Fix check line does not resolve in the call's checkout.
Cost: the merge tool loads once per guard process, and only for a call to one of the two comment tools. A body
with no marker reads no git. A body with the marker runs one `git rev-parse` and one `git cat-file` per distinct sha,
each bounded by git_reads._git's 10 s limit. A read that cannot run allows (decision review-record-hand-form).
"""
import re

from guard_core import _git, _inside_work_tree
from guard_merge import merge_module

REVIEW_COMMENT_TOOLS = ("mcp__github__add_issue_comment", "mcp__github__update_issue_comment")

REVIEW_CITE = ("(decision review-record-hand-form, a hand-typed review log that the merge tool cannot read "  # glossary-ok: the decision's slug
               "blocks the merge)")
# The merge tool prints the one readable form of the log. The flag name is the tool's own.
REVIEW_REMEDY = "Run `merge N --review-record --head SHA ...` and post the text it prints as it is."  # glossary-ok: the flag's name
REVIEW_FORM_REASON = (
    "This comment opens with the review log marker, but the merge tool cannot read its body, so the merge would "
    "stop on it. Do not type a review log by hand. " + REVIEW_REMEDY + " That printed text is the one source of "
    "review log text. " + REVIEW_CITE)
REVIEW_SHA_REASON = (
    "A sha on a head line of this review log names no commit in this checkout, so the log would record a review "
    "of a head that does not exist. Use the sha of the head the review read. " + REVIEW_REMEDY + " " + REVIEW_CITE)


def _record_lines(body: str, marker: str):
    """The lines of a review log, up to the `---` line that ends it, or None when the first line is not the marker."""
    lines = body.splitlines()
    if not lines or lines[0] != marker:
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


def review_log_hit(tool: str, tool_input, cwd: str):
    """(rule, reason, matched) for a comment tool call whose review log is refused, else None. The form is judged
    first: a body the merge tool cannot read needs no sha read."""
    if tool not in REVIEW_COMMENT_TOOLS or not isinstance(tool_input, dict):
        return None
    body = tool_input.get("body")
    merge = merge_module()
    if not isinstance(body, str) or merge is None:
        return None
    lines = _record_lines(body, merge.REVIEW_MARKER)
    if lines is None:
        return None
    if merge.parse_review(body) is None:
        shown = (lines[1] if len(lines) > 1 else "marker alone")[:100]
        return "review-record-form", REVIEW_FORM_REASON, "unreadable review log: " + shown  # glossary-ok: rule id
    sha = _unresolved(lines, merge.REVIEW_SHA, cwd)
    if sha:
        return "review-record-sha", REVIEW_SHA_REASON, "unresolved sha " + sha  # glossary-ok: rule id
    return None

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
