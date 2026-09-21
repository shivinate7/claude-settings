#!/usr/bin/env python3
"""Claude Code hook: config-edit report (Stop).

Decision 7 ("Project config edits: allow and report") lets a session edit a project's own
`.claude/hooks/*`, `.claude/settings.json`, or `.claude/settings.local.json` without a permission
prompt. This hook is how the owner still SEES the edit at turn end: it prints a `systemMessage`
naming every such file changed since the last human message, so the reply can name it under
Deviations.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing transcript, or a
parse error, and on any failure to import `guard.py` (the path test then never fires, which is a
missed report, never a wrong one).

Stop: when this turn edited a project config file (an `Edit`/`Write`/`MultiEdit`/`NotebookEdit`
tool_use, or a `Bash`/`PowerShell` command that writes to one) after the last human message, print
`{"systemMessage": "..."}` naming the files. Otherwise print nothing. When `stop_hook_active` is
set, the reply is already a rewrite, so the gate stays quiet.

It also surfaces the guard's `noted`/`subject-unread` lines. The shared-tree rule reads the
SUBJECT of a discarding git call, and a subject it could not read is allowed rather than refused
on a guess. That allow must not be silent, so the guard logs one line and this hook names it at
turn end. The lines come from `guard.log`, bounded by the timestamp of the last human message, so
an older turn's line is not reported again. The guard writes a LOCAL time and the transcript
carries a UTC time, so the bound is converted to local time rather than compared across zones,
and one second is taken off it because the guard truncates its stamp to whole seconds.

Decision 8 ("Merge into main: allow and report") makes this hook also surface a merge into main
landed this turn: a `Bash`/`PowerShell` tool_use whose command matches `gh pr merge`, and any
`mcp__github__merge_pull_request` tool_use. The guard already allows and logs these; this hook is
how the owner still SEES them at turn end, so the reply can name them under Done.

The merge notice is a CHECK, not a blind reminder (decisions/merge-notice-checks-the-report.md).
It stays quiet when the reply's own report block already names the merge, so a turn that named it
under Done does not also get told to name it. That "does the report already say this" read reuses
`lint/report_gate.py`'s `block_text`, the same blockquote extraction `report_gate.py`'s own shape
check runs on, rather than a second hand-rolled parser (CLAUDE.md, "a gate's allow list must point
at the constant the code emits"). It also identifies each merge by PR NUMBER, pulled from the `gh
pr merge` call's own arguments (never from the raw command line, so a command chained onto it with
`;` or `&&` cannot ride along), or from the MCP tool's pull-number input. A merge whose number
cannot be read falls back to a short, fixed label instead of the raw command text.

Importing `report_gate` pulls in its own import of `hooks/guard.py` (the same module this hook
already imports for the config-path test below), so this hook keeps no separate copy of that
dependency; it still avoids `lint/ste_gate.py` and the STE lint package, which it never needed.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
LINT_DIR = os.path.join(HERE, "..", "lint")
sys.path.insert(0, HERE)
sys.path.insert(0, LINT_DIR)
from _transcript import is_last_human, tool_uses, records_after_last_human, read_transcript  # noqa: E402

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
MERGE_TOOLS = {"mcp__github__merge_pull_request"}

GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
PR_NUM_TOKEN = re.compile(r"^(\d+)$")
PR_NUM_URL = re.compile(r"/pull/(\d+)")

CONFIG_MESSAGE = "Config files changed this turn: %s."
MERGE_MESSAGE = "Merges into main this turn: %s."
UNREAD_MESSAGE = (
    "The guard could not read the subject of these commands, and allowed them: %s."
)
TAIL = " Name them in the report."
UNREAD_RULE = "subject-unread"

# Fallback label for a merge whose PR number this hook could not read from the command or the
# MCP tool's own input (for example `gh pr merge` run with no number and no PR checked out by
# convention this hook can resolve). Short and fixed, never the raw command line.
UNNUMBERED_MERGE = "an unnumbered merge"

MCP_PR_NUMBER_KEYS = ("pullNumber", "pull_number", "prNumber", "pr_number", "number", "pr")


# ------------------------------------------------------------------ transcript walking
#
# is_last_human, tool_uses, records_after_last_human, and read_transcript live in
# lint/_transcript.py, imported above. This hook already imports lint/report_gate.py (which
# already imports lint/ste_gate.py) for the merge-notice check below, so importing
# lint/_transcript.py adds no new dependency.


# ------------------------------------------------------------------ the path test

def collect_paths(records, cwd):
    """Return the project config paths this turn's tools touched, in first-seen order."""
    try:
        import guard  # PreToolUse guard.py, same directory
    except Exception:
        guard = None

    seen = []

    def note(path):
        if path and path not in seen:
            seen.append(path)

    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in FILE_TOOLS:
                target = (
                    inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                )
                if not isinstance(target, str) or not target:
                    continue
                if guard is None:
                    continue
                try:
                    hit = guard.is_project_config(target, cwd)
                except Exception:
                    hit = False
                if hit:
                    note(target)
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                if guard is None:
                    continue
                try:
                    matched = guard.project_config_shell_hit(cmd, cwd)
                except Exception:
                    matched = ""
                if matched:
                    note(matched)
    return seen


def _pr_number_from_segment(segment):
    """Return the PR number a `gh pr merge` call in `segment` names, else None.

    Reads only the tokens that follow the call's own `gh pr merge` words, so a command chained
    onto it with `;` or `&&` (already split into its own segment by the caller) can never
    supply the number for this call.
    """
    m = GH_PR_MERGE.search(segment)
    if not m:
        return None
    for tok in segment[m.end():].split():
        if tok.startswith("-"):
            continue
        num = PR_NUM_TOKEN.match(tok)
        if num:
            return num.group(1)
        url = PR_NUM_URL.search(tok)
        if url:
            return url.group(1)
    return None


def _pr_number_from_mcp_input(inp):
    for key in MCP_PR_NUMBER_KEYS:
        value = inp.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and value.strip().isdigit():
            return value.strip()
    return None


def collect_merges(records):
    """Return the merges into main this turn's tools named, as display labels, in first-seen
    order: `#<N>` when a PR number could be read, else UNNUMBERED_MERGE.
    """
    try:
        import guard  # PreToolUse guard.py, same directory
    except Exception:
        guard = None

    seen = []

    def note(number):
        label = "#%s" % number if number else UNNUMBERED_MERGE
        if label not in seen:
            seen.append(label)

    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in MERGE_TOOLS:
                note(_pr_number_from_mcp_input(inp))
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                if guard is not None:
                    try:
                        stripped = guard.strip_heredoc_bodies(cmd)
                        segments = guard.split_segments(stripped)
                    except Exception:
                        segments = [cmd]
                else:
                    segments = [cmd]
                for segment in segments:
                    if GH_PR_MERGE.search(segment):
                        note(_pr_number_from_segment(segment))
    return seen


def already_named(labels, report_block):
    """Return the labels from `labels` that `report_block` does not already name.

    `#75` is looked for both as written and as `PR 75` / `PR#75` (case-insensitive), since a
    report is free to spell it either way. UNNUMBERED_MERGE is looked for verbatim: it is
    already the short, fixed string a report would have to repeat to name it.
    """
    if not report_block:
        return list(labels)
    remaining = []
    for label in labels:
        if label in report_block:
            continue
        if label.startswith("#"):
            num = label[1:]
            alt = re.compile(r"\bpr\s*#?\s*" + re.escape(num) + r"\b", re.IGNORECASE)
            if alt.search(report_block):
                continue
        remaining.append(label)
    return remaining


def last_human_stamp(records):
    """Return the timestamp of the last human message, else ''."""
    stamp = ""
    for rec in records:
        if is_last_human(rec):
            value = rec.get("timestamp") or ""
            stamp = value if isinstance(value, str) else ""
    return stamp


def _turn_bound(stamp):
    """Return the last human message time as a naive LOCAL datetime, else None.

    The transcript stamp is UTC and the guard's log stamp is local, so the bound is converted
    rather than compared across zones. One second is taken off, because the guard truncates its
    own stamp to whole seconds and a line written in the same second would otherwise be dropped.
    """
    text = (stamp or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except Exception:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment - timedelta(seconds=1)


def collect_unread(stamp):
    """Return the matched text of each `noted`/`subject-unread` guard line from this turn."""
    bound = _turn_bound(stamp)
    if bound is None:
        return []
    try:
        import guard  # PreToolUse guard.py, same directory
        path = os.path.join(guard.config_dir(), "guard.log")
    except Exception:
        return []
    if not os.path.exists(path):
        return []
    seen = []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except Exception:
        return []
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 5 or fields[3] != UNREAD_RULE:
            continue
        try:
            when = datetime.fromisoformat(fields[0])
        except Exception:
            continue
        if when < bound:
            continue
        text = fields[4].strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    if hook.get("stop_hook_active"):
        return

    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return

    try:
        records = read_transcript(path)
    except Exception:
        return

    after = records_after_last_human(records)
    if not after:
        return

    cwd = hook.get("cwd") or ""
    if not isinstance(cwd, str):
        cwd = ""

    hits = collect_paths(after, cwd)
    merges = collect_merges(after)
    if merges:
        try:
            import report_gate  # lint/report_gate.py, same-repo sibling package
            from ste_gate import last_reply  # lint/ste_gate.py
            reply_text = last_reply(hook)
            block = report_gate.block_text(reply_text)
            merges = already_named(merges, block)
        except Exception:
            # Cannot tell whether the report already named the merge: fail open the same way
            # this hook fails open elsewhere, by still naming it, not by going quiet.
            pass
    unread = collect_unread(last_human_stamp(records))
    if not hits and not merges and not unread:
        return

    parts = []
    if hits:
        parts.append(CONFIG_MESSAGE % ", ".join(hits))
    if merges:
        parts.append(MERGE_MESSAGE % ", ".join(merges))
    if unread:
        parts.append(UNREAD_MESSAGE % ", ".join(unread))
    print(json.dumps({"systemMessage": " ".join(parts) + TAIL}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
