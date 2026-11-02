#!/usr/bin/env python3
"""At Stop, after a turn that ran git commit, git push or git merge, blocks once unless the reply ends with the report: the bold labels Done, Deviations, Input Needed, Next, in order. Fails open on any error.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing
transcript, or a parse error.

Stop: when this turn ran `git commit`, `git push`, `git merge`, or a GitHub MCP write tool
after the last human message, block once unless the reply ends with one blockquote holding
the bold labels Done, Deviations, Input Needed, Next, in that order (CLAUDE.md, "Reports, in
order"; the blockquote and no-fence rule lives in the `shiv-stylisms` output style). Prose may sit above the report on any turn. Nothing may follow the report.
When stop_hook_active is set, the reply is already a rewrite, so the guard stays quiet, with one
exception: a block that asked for the missing report leaves a marker file (local_time.report_marker_path,
holding the index of the turn's human record). The next stop_hook_active Stop consumes it and checks
the rewrite once for model names and the `Unstarted:` line only. A failure blocks with a correction.
Cost: one small file per missing-report block, written at that block, deleted at the next Stop with
stop_hook_active; no process, timer or log. A correction block leaves no marker, so no loop follows.

On the same landed turns it also blocks (one block, all reasons joined) when a Done item lacks
BUILT, RECORDED, or OTHER or a PR or commit ref (`reports-done-format`), or when the reply holds
a record id with no short gloss (`speak-cite-id-plus-gloss`), or when a builder, reviewer,
test-author or record-writer spawned since the last human message goes unnamed in Done, or a
named "role model" pair matches no spawn of that role (`reports-done-names-models`), or when
a turn that spawned a builder reports with no `Unstarted:` line (`reports-name-unstarted-items`).
When the report is there, each of these blocks asks for only the corrected lines, never the report again.

On any turn whose reply holds an Input Needed item that offers a pick with options, it also blocks
unless the same main-session turn opened the question box (AskUserQuestion), or the repo has a
waiting page and either the reply links it or the Input Needed item names the 5-minute wait and the
waiting page, whatever ArtifactData calls the turn made (`decisions-reach-a-clickable-pick`). This
check does not wait for a git write: the reply's labels are what it reads. Cost: one layout read per turn whose Input Needed offers a pick with no box.
The same pick must carry a valid "Departs from:" line in that Input Needed item (`question-departs`, judged by
hooks/question_form.py departs_hit, on landed and unlanded turns alike). Cost: one regex read of that item and one module import, no file.

On every Stop, landed or not, it also reads <config dir>/state/refusals/<session_id>.jsonl, which
hooks/refusal_note.py writes for each tool the auto-mode classifier refused. A pending tool the reply
does not name in its Input Needed section blocks. A built-in tool counts only in backticks; an MCP
tool counts by its full name. Each tool the reply names is cleared, on a
stop_hook_active rewrite too, which never blocks on a refusal (decision refusals-reach-the-owner).
Cost: one stat per Stop when the session had no refusal.

An Input Needed pick must also reach the owner (decision questions-go-to-owner, "Chat first, then the page"). The chat-first clause of
the pick guard stays: it passes the turn that asks. Two checks enforce what it promises. A session is a
lane when its own newest get_session record (hooks/guard_merge.py own_tier) has the tag cs-build:lane or a
parent_session_id; with no record, no own id or a read error it is owner-facing.
Owner-facing: each pick the reply offers with no box is kept in <handoffs>/<session_id>.open-picks.json
(local_time.open_picks_path) with its ask time. A later owner message, a main-session box, a send to the
page writer (or, with no writer known, a send naming the item id) or a write to the page's items clears it.
A Stop 300 s or more after the ask blocks until it is sent. A repo with no waiting page never blocks: the
check says once that it failed open and drops the item. A stop_hook_active Stop clears what was sent and
never blocks or adds.
A pick cleared by a send, box or items write is remembered by hash for 24 hours, so the same pick re-asked
later opens no item; one cleared only by an owner message is not. A send clears an item, or answers a lane,
only when its message carries the pick: the item id or the first 60 characters of the pick's first line.
Lane: a Stop whose Input Needed offers a pick blocks unless the same turn called the box or sent the pick to
the parent or the page writer. A tag-only lane (no parent known) passes on a send to the writer or to any
session, when the send carries the pick. The page words and the page link pass nothing for a lane.
Cost: no process, timer or log. One stat per Stop when no pick was ever open. One small JSON file per
session, written only at a Stop that adds or clears an item, and a second small file (<state>.sent), written
only at a Stop where a send cleared a pick and read only when a pick is added. One transcript read, which
this guard already makes. One get_session scan of that transcript per Stop whose reply offers a pick or
whose state file exists. A lane or owner-facing Stop that offers a pick loads hooks/guard.py once, for LANE_TAG.
"""
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import (  # noqa: E402
    is_last_human, last_reply, owner_text, parse_utc_timestamp, read_transcript, tool_uses)
import layout  # noqa: E402

# guard.py owns the one shell parser this repo trusts: quote-aware segment splitting,
# heredoc-body stripping, and `git_calls`, which resolves each `git` invocation past `sudo`
# and past the pre-subcommand options that take a value (`-C <dir>`, `--git-dir=<path>`, and
# the rest of `GIT_OPT_WITH_VALUE`) to the subcommand it actually runs. lint/ and hooks/ land
# side by side, both under the repo root and under ~/.claude, so the hop from one to its
# sibling holds in both places. A regex over
# the raw command text cannot tell a quoted probe string, or a heredoc body, from an
# actual git write. See docs/decisions/predicate-is-the-act.md.
# It loads only when the turn ran a shell or landing tool, so an event the guard ignores,
# a rewrite turn and an idle turn never pay for it.
guard = None


def _load_guard():
    global guard
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    try:
        import guard as loaded
    except ImportError:
        # A guard that cannot read cannot accuse. Fail open, the same posture every other guard
        # here takes on a missing or unreadable input: turn_landed() below reports no landing at
        # all when guard did not load, so this Stop hook never demands a report it cannot judge.
        return
    guard = loaded

GIT_LANDING_SUBCOMMANDS = {"commit", "push", "merge"}
LANDING_TOOLS = {
    "mcp__github__merge_pull_request",
    "mcp__github__create_pull_request",
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
}
LABEL_ORDER = ["Done", "Deviations", "Input Needed", "Next"]
# A bold "**Departs from:**" starts a line of the item (rule `question-departs`), never a report label.
LABEL_RE = re.compile(r"^\*\*(?!(?i:Departs from))(.+?)\*\*")
# A label may carry its colon inside the bold, as in "**Done:**". Both forms read the same,
# so the colon is stripped before the label is matched against LABEL_ORDER.

BLOCK_REASON_HEAD = (
    "Report-shape guard: this turn landed a commit, push, or merge, so the reply must end "
    "with the report. One blockquote, bold labels Done, Deviations, Input Needed, Next in "
    "that order, drop a label that does not apply, no code fence, nothing after it."
)
BLOCK_REASON_TAIL = (
    " Prose may sit above the report. Send the report now, as the next thing you write. Keep "
    "the reply above it as it stands. Do not write it again."
)
# The owner has read the report before a block lands, so a resent report doubles it. The
# missing-report block asks for the report itself, so its reply carries every other fix. Once the
# report is there, every other block asks for a short correction.
# A Stop hook cannot read a reply before it is shown. The correction runs with stop_hook_active
# set, so this guard stays quiet on it. The rewrite after a missing-report block is the one
# exception: rewrite_problems() checks it once, and its own block leaves no marker.
CORRECTION_TAIL = (
    " Post only the corrected lines, as a short correction. Never send the report again."
)

MODELS_REASON = (
    "Model-name guard: a Done item that agents built or reviewed names each one's role "
    "and model, like \"(builder sonnet, reviewer sonnet)\". Here: ")
UNSTARTED_REASON = (
    "Unstarted guard: this turn ran a builder, so Next holds an \"Unstarted:\" line. "
    "Name each queued item with every question answered that you left unstarted, with "
    "its reason, or write \"Unstarted: none\".")


# is_last_human and tool_uses live in lint/_transcript.py, imported above.


def _segment_lands_a_git_write(segment):
    """True when one of the segment's own `git` calls resolves to `commit`, `push`, or `merge`.

    `guard.git_calls` is the parser every git rule in guard.py already trusts: it walks past
    `sudo`, and past the pre-subcommand options that take a value (`-C <dir>`,
    `--git-dir=<path>`, and the rest of `GIT_OPT_WITH_VALUE`), to the subcommand a call would
    actually run. Reusing it, rather than a second hand-rolled skip, is what keeps
    `git -C /path commit` counted as a landing. `git merge-base` resolves to the subcommand
    `merge-base`, a different word than `merge`, and never matches.
    """
    for subcommand, _args in guard.git_calls(segment):
        if subcommand in GIT_LANDING_SUBCOMMANDS:
            return True
    return False


def turn_landed(records):
    if not any(b.get("name") == "Bash" or b.get("name") in LANDING_TOOLS
               for rec in records for b in tool_uses(rec)):
        return False
    if guard is None:
        _load_guard()
    if guard is None:
        return False
    for rec in records:
        for b in tool_uses(rec):
            name = b.get("name")
            if name == "Bash":
                cmd = (b.get("input") or {}).get("command") or ""
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                stripped = guard.strip_heredoc_bodies(cmd)
                for segment in guard.split_segments(stripped):
                    if _segment_lands_a_git_write(segment):
                        return True
            elif name in LANDING_TOOLS:
                return True
    return False


def find_block_start(lines):
    """Return the index of the first blockquote line, else None.

    Shared by `report_shape_ok` and by `block_text`, so a second caller (such as
    `hooks/decision_watch.py`'s merge-report check) locates the same block this guard judges,
    rather than re-deriving its own idea of where the report starts.
    """
    for i, line in enumerate(lines):
        if line.lstrip().startswith(">"):
            return i
    return None


def block_text(text, keep_indent=False):
    """Return the reply's report block, quote markers stripped, or "" when there is none.

    This does not judge shape (label order, fencing, trailing text): that is `report_shape_ok`'s
    job. It only hands back the block's own text, so a caller that needs to
    know whether the block already SAYS something (such as a PR number) can search it without
    hand-rolling a second blockquote parser.
    """
    lines = text.splitlines()
    start = find_block_start(lines)
    if start is None:
        return ""
    out = []
    for line in lines[start:]:
        if not line.strip():
            continue
        if not line.lstrip().startswith(">"):
            break
        stripped = line.lstrip()[1:]
        # keep_indent: drop `>` and one space only, so a caller can tell a sub-bullet from a bullet.
        out.append(stripped[1:] if keep_indent and stripped.startswith(" ") else
                   stripped if keep_indent else stripped.lstrip())
    return "\n".join(out)


def report_shape_ok(text):
    lines = text.splitlines()
    start = find_block_start(lines)
    if start is None:
        return False
    seen = []
    any_label = False
    for line in lines[start:]:
        if not line.strip():
            continue
        if not line.lstrip().startswith(">"):
            return False
        if "```" in line:
            return False
        stripped = line.lstrip()
        stripped = stripped[1:] if stripped.startswith(">") else stripped
        stripped = stripped.lstrip()
        m = LABEL_RE.match(stripped)
        if not m:
            continue
        label = m.group(1).strip()
        if label.endswith(":"):
            label = label[:-1].strip()
        any_label = True
        if label not in LABEL_ORDER:
            return False
        seen.append(label)
    if not any_label:
        return False
    if seen and seen[0] != "Done":
        return False
    idxs = [LABEL_ORDER.index(l) for l in seen]
    if idxs != sorted(set(idxs)) or len(set(idxs)) != len(idxs):
        return False
    return True


# reports-done-format: each Done item says BUILT, RECORDED, or OTHER; BUILT and RECORDED also name a PR or commit.
# A ref is `#12`, `PR 12`, a /pull/N or /commit/<sha> URL, or a hex sha of 6 to 40 digits that
# holds at least one digit (so a plain word like "added" is not a sha).
DONE_KIND_RE = re.compile(r"\b(?:BUILT|RECORDED|OTHER)\b")
DONE_REF_RE = re.compile(
    r"(?:#\d+|\bPRs?\s*#?\d+|/pull/\d+|/commit/[0-9a-f]{6,40}|\b(?=[0-9a-f]*\d)[0-9a-f]{6,40}\b)")
BULLET_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+")


def done_items(block):
    """Return the Done label's items from `block_text` output: its bullets, else its one inline text."""
    body = []
    inside = False
    for line in block.splitlines():
        m = LABEL_RE.match(line)
        if m:
            label = m.group(1).strip().rstrip(":").strip()
            if inside:
                break
            inside = label == "Done"
            if inside:
                body.append(line[m.end():].lstrip(": "))
            continue
        if inside:
            body.append(line)
    inline = body[0].strip() if body else ""
    items = []
    top = None  # indent of the first bullet; deeper bullets are details, not items
    in_detail = False
    for line in body[1:]:
        text = line.strip()
        if not text:
            continue
        indent = len(line) - len(line.lstrip())
        if BULLET_RE.match(text):
            if top is None:
                top = indent
            in_detail = indent > top
            if not in_detail:
                items.append(text)
        elif items and not in_detail:
            items[-1] += " " + text
    if items:
        return ([inline] if DONE_KIND_RE.search(inline) else []) + items
    text = " ".join(l.strip() for l in body if l.strip())
    return [text] if text else []


def done_format_problem(text):
    """Name the first Done item lacking a BUILT/RECORDED/OTHER word or a PR/commit ref, else ''."""
    for item in done_items(block_text(text, keep_indent=True)):
        kinds = set(DONE_KIND_RE.findall(item))
        if not kinds or (kinds & {"BUILT", "RECORDED"} and not DONE_REF_RE.search(item)):
            return item[:60]
    return ""


# speak-cite-id-plus-gloss: a record id is `D<digits>` or `decision <digits>`. A bare `#N` is
# NOT read as a record id: a Done line must cite PRs as `#N` (reports-done-format), so the two
# cannot be told apart. Skipped text: fenced code, inline code, URLs, markdown links. An id
# carries a gloss when 2 or more words follow it after a separator (`D12, short titles`,
# `D12: ...`, `D12 (..)`), or `D12's two words`, or it sits in parentheses after words
# (`short titles (D12)`).
CITE_ID_RE = re.compile(r"(?<![\w/.#:$-])(?:D\d{1,4}|[Dd]ecisions?\s+#?\d{1,4})(?!\w|\.\d|:[A-Z]\d)")
CITE_SKIP_RE = re.compile(r"```.*?```|`[^`\n]*`|https?://\S+|\[[^\]\n]*\]\([^)\n]*\)", re.S)
GLOSS_AFTER_RE = re.compile(
    r"""^["')\]]*\s*(?:[,:;(=—–-]|\s-{1,2}\s)\s*\(?[A-Za-z][\w'-]*\s+[\w'-]+"""
    r"""|^["')\]]*\s+(?:says|means|is|covers|rules)\s+[A-Za-z][\w'-]*\s+[\w'-]+""")
GLOSS_POSSESSIVE_RE = re.compile(r"^['’]s\s+[A-Za-z][\w'-]*\s+[\w'-]+")
GLOSS_BEFORE_RE = re.compile(r"[A-Za-z]{2,}[^\n(]{0,60}\(\s*$")
# a gloss before the id: two words, then a comma, colon, or dash, then the id
GLOSS_LEAD_RE = re.compile(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}\s*(?:[,:—–=]|--|\s-)\s*$")


def bare_cite(text):
    """Return the first record id in `text` with no short gloss beside it, else ''."""
    clean = CITE_SKIP_RE.sub(" ", text)
    for m in CITE_ID_RE.finditer(clean):
        after = clean[m.end():m.end() + 80]
        before = clean[max(0, m.start() - 80):m.start()]
        if GLOSS_AFTER_RE.match(after) or GLOSS_POSSESSIVE_RE.match(after):
            continue
        if GLOSS_BEFORE_RE.search(before) and after.lstrip().startswith(")"):
            continue
        if GLOSS_LEAD_RE.search(before) or before.rstrip().lower().endswith("vitamin"):
            continue
        return m.group(0)
    return ""


# reports-done-names-models: a Done item that agents built or reviewed names each one's role
# and model, as "(builder sonnet, reviewer sonnet)". Only these roles build or review; an Explore
# search or a Plan spawn needs no name. A Workflow agent() is unseen: its model can sit in a variable.
NAMED_ROLES = {"builder", "reviewer", "test-author", "record-writer"}
SPAWN_TOOLS = {"Agent", "Task"}
MODEL_FAMILIES = ("haiku", "sonnet", "opus", "fable")
# A model names the roles just before it: "builder sonnet", "builder: sonnet", "builder (sonnet)",
# and "builder and reviewer sonnet" all count.
_ROLE = r"(?:builder|reviewer|test-author|record-writer)"
ROLE_MODEL_RE = re.compile(
    r"\b(" + _ROLE + r"(?:\s*(?:,|/|&|\band\b)\s*" + _ROLE + r")*)\s*[:(]?\s*(haiku|sonnet|opus|fable)\b",
    re.I)
ROLE_RE = re.compile(_ROLE, re.I)
AGENTS_DIR = os.path.join(HERE, "..", "agents")


def model_family(text):
    text = (text or "").lower()
    return next((f for f in MODEL_FAMILIES if f in text), "")


def agent_pin(role):
    """The `model:` key of agents/<role>.md, or '' when the file or key is missing."""
    try:
        with open(os.path.join(AGENTS_DIR, role + ".md"), encoding="utf-8") as f:
            lines = f.read().split("---")[1].splitlines()
    except (OSError, IndexError):
        return ""
    for line in lines:
        key, _, value = line.partition(":")
        if key.strip() == "model":
            return value.strip()
    return ""


def spawn_models(records):
    """Map each named role spawned in `records` to the set of model families it ran on.

    A spawn's model is its call's `model` field, else its agent file's pin, else
    CLAUDE_CODE_SUBAGENT_MODEL; Claude Code reads them in that order. A spawn none of them
    resolve adds '' (unknown), which never counts as a mismatch.
    """
    failed = set()  # a denied or errored spawn ran no agent, so it counts for nothing
    for rec in records:
        content = (rec.get("message") or {}).get("content")
        for b in content if isinstance(content, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                failed.add(b.get("tool_use_id"))
    found = {}
    for rec in records:
        for b in tool_uses(rec):
            if b.get("name") not in SPAWN_TOOLS or b.get("id") in failed:
                continue
            inp = b.get("input") or {}
            role = str(inp.get("subagent_type") or "").lower()
            if role not in NAMED_ROLES:
                continue
            model = model_family(inp.get("model")) or model_family(agent_pin(role)) or \
                model_family(os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL"))
            found.setdefault(role, set()).add(model)
    return found


def done_models_problem(text, spawned):
    """Name what Done gets wrong about the spawned roles' models, else ''."""
    if not spawned:
        return ""
    done = " ".join(done_items(block_text(text, keep_indent=True)))
    named = {(r.lower(), m.lower()) for roles, m in ROLE_MODEL_RE.findall(done)
             for r in ROLE_RE.findall(roles)}
    missing = sorted(r for r in spawned if not any(nr == r for nr, _ in named))
    if missing:
        return "no model named for " + ", ".join(missing)
    for role, model in sorted(named):
        ran = spawned.get(role)
        if ran is not None and "" not in ran and model not in ran:
            return f"'{role} {model}' matches no {role} spawn, which ran " + ", ".join(sorted(ran))
    return ""


# reports-name-unstarted-items: a builder spawn marks an orchestrator's turn. Its report holds an
# `Unstarted:` line, inline after Next, after a `;` or `.`, or on its own line, in any case. It lists
# the ready items or says none. A bold `**Unstarted:**` is an unknown label, which the shape check refuses.
UNSTARTED_RE = re.compile(
    r"(?:^|[;.]\s+)(?:\*\*Next:?\*\*:?\s*)?(?:[-*+]\s+)?unstarted:", re.M | re.I)


def unstarted_problem(text, spawned):
    """True when a builder ran this turn and the report holds no `Unstarted:` line."""
    return "builder" in spawned and not UNSTARTED_RE.search(block_text(text))

# decisions-reach-a-clickable-pick: "a pick with options" in the Input Needed item is either two or
# more distinct option markers, or the phrase "A or B". A marker is a lettered or numbered item at
# a line start (`A:`, `A)`, `A.`, `A (my pick):`, `1.`, `2)`), or an inline letter A to F followed by
# `:`, `)` or a "(my pick)" / "(recommended)" tag. Once a letter carries such a tag, another bare
# capital letter A to F counts too, so "A (my pick) ... B ..." reads as two options. One marker alone
# ("You picked A on Oct 26") is a quoted answer, never a pick.
OPTION_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*)?([A-F])(?=[:).]|\s*\()", re.M)
OPTION_INLINE_RE = re.compile(r"(?<![\w'(])([A-F])(?::|\))")
OPTION_TAG_RE = re.compile(r"(?<![\w'])([A-F])\s*\((?i:my pick|recommended|pick)\)")
OPTION_BARE_RE = re.compile(r"(?<![\w'(])([A-F])(?![\w'.])")
OPTION_OR_RE = re.compile(r"(?<![\w'])[A-F] or [A-F](?![\w'])")
# Numbered items are often separate asks, and "A or B" is often plain text, so both count only
# with pick context: a tag, a lettered marker, or one of these words in the same item.
OPTION_NUM_RE = re.compile(r"(?:^|(?<=\s))(?:[-*+]\s+)?(\d{1,2})[.)](?=\s)", re.M)
PICK_WORD_RE = re.compile(r"\b(?:pick|options?|ways?|choose|recommended)\b", re.I)
ASK_TOOL = "AskUserQuestion"

# The chat-first wait (questions-go-to-owner, "Chat first, then the page"): 5 minutes, never 15, 25
# or "twenty-five". A spelled "five" after a tens word is caught in the `tens` group and refused,
# since a fixed-width lookbehind cannot hold the tens words.
FIVE_MINUTES_RE = re.compile(
    r"(?<![\w.-])(?:(?P<tens>(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[ -]+)?"
    r"five[ -]minutes?|5[ -]?min(?:ute)?s?)\b", re.I)
PAGE_WORDS_RE = re.compile(r"\bwaiting[ -]page\b", re.I)

PICK_REFUSAL = (
    "Pick guard: Input Needed offers a pick with options and gives no way to answer it. Ask in chat "
    "and say it goes to the waiting page after 5 minutes unanswered, link the waiting page, or, only "
    "with nothing running, open the question box."
)


def names_five_minutes(section):
    """True when `section` names the 5-minute wait, never 15, 25 or twenty-five minutes."""
    return any(not m.group("tens") for m in FIVE_MINUTES_RE.finditer(section))


def input_needed_section(text):
    """The Input Needed item's text from the report block, else ''."""
    body = []
    inside = False
    for line in block_text(text, keep_indent=True).splitlines():
        m = LABEL_RE.match(line)
        if m:
            if inside:
                break
            inside = m.group(1).strip().rstrip(":").strip() == "Input Needed"
            if inside:
                body.append(line[m.end():].lstrip(": "))
            continue
        if inside:
            body.append(line)
    return "\n".join(body)


def offers_a_pick(text):
    section = input_needed_section(text)
    if not section.strip():
        return False
    letters = set(OPTION_LINE_RE.findall(section)) | set(OPTION_INLINE_RE.findall(section))
    tagged = set(OPTION_TAG_RE.findall(section))
    letters |= tagged
    if tagged:
        letters |= set(OPTION_BARE_RE.findall(section))
    if len(letters) >= 2:
        return True
    numbers = set(OPTION_NUM_RE.findall(section))
    context = bool(tagged or letters or PICK_WORD_RE.search(section))
    if OPTION_OR_RE.search(section) and (context or numbers):
        return True
    return len(numbers) >= 2 and context


def repo_root(cwd):
    """The nearest folder at or above `cwd` that holds a git entry, else None."""
    here = os.path.realpath(cwd or os.getcwd())
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def departs_problem(text):
    """The refusal text when the Input Needed item offers a pick and its Departs from line is missing or
    restates main (rule `question-departs`), else ''. The predicate is question_form.departs_hit."""
    if not offers_a_pick(text):
        return ""
    # hooks/question_form.py is the one home of the predicate: the chat box, the waiting page and this
    # report all call it. lint/ and hooks/ sit side by side, in the repo and under ~/.claude. It loads only
    # for a turn that offers a pick, and an import error fails this one check open (the callers catch it).
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import question_form
    miss = question_form.departs_hit(input_needed_section(text))
    if not miss:
        return ""
    return "Departs-from guard: the Input Needed pick has a problem (" + miss + "). " + question_form.DEPARTS_REASON


def pick_has_a_control(records, text, cwd):
    """True when the main session's turn opened the question box, or this repo has a waiting page
    and the reply links it or its Input Needed item names the 5-minute wait and the page. An
    agent's own box (isSidechain) never counts."""
    for rec in records:
        if rec.get("isSidechain"):
            continue
        if any(b.get("name") == ASK_TOOL for b in tool_uses(rec)):
            return True
    root = repo_root(cwd)
    page = layout.waiting_page(root) if root else "unknown"
    if page == "unknown":
        return False
    page = page.rstrip("/")
    section = input_needed_section(text)
    if names_five_minutes(section) and PAGE_WORDS_RE.search(section):
        return True
    return bool(re.search(re.escape(page) + r"(?![\w-])", text))


def names_tool(section, tool):
    """True when the Input Needed text names `tool`. A built-in tool (Edit, Bash) is an English word,
    so only its backticked name counts. An MCP tool counts by its full name, in backticks or not;
    a short form of it (the part after the last `__`) does not."""
    if "__" in tool:
        return bool(re.search(r"(?<!\w)" + re.escape(tool) + r"(?!\w)", section))
    return ("`%s`" % tool) in section


def pending_refusals(hook, text):
    """Settle the session's refusals file against the reply and return the tool names still unnamed.

    A tool the reply names under Input Needed is dropped from the file (the file goes when none is
    left); the rest stay. One stat per Stop when the session had no refusal. Fails open: [] on any error.
    Spec: docs/decisions/refusals-reach-the-owner.md."""
    try:
        sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
        import shared_names
        path = shared_names.refusals_path(hook.get("session_id"))
        if path is None or not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            rows = []
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict) and isinstance(row.get("tool_name"), str):
                    rows.append((line.rstrip("\n"), row["tool_name"]))
        section = input_needed_section(text)
        kept = [(line, tool) for line, tool in rows
                if not names_tool(section, tool)]
        if len(kept) != len(rows):
            if kept:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("".join(line + "\n" for line, _ in kept))
            else:
                os.remove(path)
        return [tool for _, tool in kept]
    except Exception:
        return []


def refusal_reason(tools):
    """The block reason for refused tools the reply has not raised, or ''."""
    if not tools:
        return ""
    names = ", ".join("`%s`" % tool for tool in tools)
    return (
        "Refusal guard: the auto-mode classifier refused %s this session, and the reply does not "
        "raise it with the owner. Add an Input Needed line \"allow `<tool_name>`?\" for each tool, "
        "and a line in the repo's debt notes file (notes.md) that names it." % names)


# questions-go-to-owner, "Chat first, then the page": an Input Needed pick has to reach the owner. The pick guard above passes the turn
# that asks on a promise (the 5-minute wait and the waiting page); these checks enforce the promise.
PICK_WAIT_SECONDS = 300
CARRY_CHARS = 60      # a send carries a pick when it holds this many chars of the first line, or the item id
SENT_KEEP_SECONDS = 24 * 3600   # how long a pick cleared by a send is remembered
OPEN_PICK_REASON = (
    "Open-pick guard: an Input Needed pick has waited 5 minutes or more and no send, owner reply or box "
    "answered it: %s. Send each question to %s by send_message, with the item id in the message. A session "
    "that is the page writer writes the item itself: an ArtifactData write to the items collection naming the item id.")
NO_PAGE_NOTICE = ("Open-pick guard: failed open. The repo has no waiting page, so the pick %s was dropped "
                  "after 5 minutes and nothing was blocked.")
LANE_REASON = (
    "Lane pick guard: Input Needed offers a pick, and this turn sent it nowhere. A lane's own chat does "
    "not reach the owner. Send the question to %s by send_message in this turn, with the item id %s in the message.")


def now():
    """The clock of the 5-minute wait. One home, so a test can patch it."""
    return time.time()


def _hooks():
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))


def _load_records(path):
    """The transcript's records, or None when it is missing or unreadable."""
    if not path or not os.path.exists(path):
        return None
    try:
        return read_transcript(path)
    except Exception:
        return None


def _norm(text):
    return " ".join((text or "").split()).casefold()


def _blocks(rec):
    content = (rec.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _result_text(block):
    body = block.get("content")
    if isinstance(body, list):
        body = "".join(b.get("text", "") for b in body if isinstance(b, dict))
    return body if isinstance(body, str) else ""


def _find_writer(node, depth=0):
    if isinstance(node, dict):
        if isinstance(node.get("writer"), str) and node["writer"]:
            return node["writer"]
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    if depth >= 3:
        return None
    for child in children:
        found = _find_writer(child, depth + 1)
        if found:
            return found
    return None


def _reads_meta_page(tool_input):
    if not isinstance(tool_input, dict) or tool_input.get("action") != "get":
        return False
    doc = tool_input.get("doc_id") or tool_input.get("path")
    return (tool_input.get("collection") == "meta" and doc == "page") or doc == "meta/page"


def _feedback_guard():
    _hooks()
    import feedback_guard
    return feedback_guard


def pick_keys(section):
    """(hash, id, first) of an Input Needed section: the sha1 of its normalized text, the item id
    `ask-<8 hex>` and its normalized first non-blank line. One home of an item's identity."""
    digest = hashlib.sha1(_norm(section).encode("utf-8")).hexdigest()
    lines = [line for line in section.splitlines() if line.strip()]
    return digest, "ask-" + digest[:8], _norm(lines[0]) if lines else ""


def carries(message, item_id, first):
    """True when a message carries the pick: it names the item id as a whole token, or holds the first
    CARRY_CHARS characters of the item's first line."""
    return isinstance(message, str) and (
        _feedback_guard().names_token(message, item_id) or bool(first) and first[:CARRY_CHARS] in _norm(message))


def _writes_item(node, item_id, first):
    """True when a set, update or batch write to the page's items holds the item's id as a whole token or
    its first line. The walker is feedback_guard's `writes_where`."""
    fg = _feedback_guard()

    def test(d):
        return any(isinstance(v, str) and (fg.names_token(v, item_id) or bool(first) and first in _norm(v))
                   for v in d.values())
    return fg.writes_where(node, test)


def _send_target(use):
    inp = use.get("input") if isinstance(use.get("input"), dict) else {}
    return inp.get("session_id") if str(use.get("name")).endswith("send_message") else inp.get("to")


def _facts(records):
    """The page writer and the events the open-pick checks read: (writer, events). An event is
    (time or None, kind, tool_use or None), kind owner, box, send or write. A call made inside another
    agent's run (isSidechain) and a call whose result is an error count for nothing."""
    fg = _feedback_guard()
    import shared_names
    failed, reads, writer, events = set(), set(), None, []
    for rec in records:
        for b in _blocks(rec):
            if b.get("type") == "tool_result" and b.get("is_error"):
                failed.add(b.get("tool_use_id"))
    for rec in records:
        at = parse_utc_timestamp(rec.get("timestamp"))
        if owner_text(rec, shared_names.MACHINE_TAGS) is not None:
            events.append((at, "owner", None))
        for b in _blocks(rec):
            kind, name = b.get("type"), str(b.get("name") or "")
            if kind == "tool_result" and b.get("tool_use_id") in reads and not b.get("is_error"):
                try:
                    writer = _find_writer(json.loads(_result_text(b))) or writer
                except Exception:
                    pass
            elif kind == "tool_use" and not rec.get("isSidechain") and b.get("id") not in failed:
                if name.startswith(fg.ARTIFACT_DATA):
                    if _reads_meta_page(b.get("input")):
                        reads.add(b.get("id"))
                    else:
                        events.append((at, "write", b))
                elif name == ASK_TOOL:
                    events.append((at, "box", None))
                elif name in fg.SEND_TOOLS:
                    events.append((at, "send", b))
    return writer, events


def _answers(item, writer, events, timed=True):
    """The kinds of event (owner, box, send, write) that answered the item (questions-go-to-owner, "Chat
    first, then the page"). A send counts when it goes to the writer (any session when no writer is known)
    and carries the pick. `timed` False takes every event given, for an item new this Stop."""
    first = pick_keys(item.get("text") or "")[2]
    kinds = set()
    for at, kind, use in events:
        if timed and (at is None or at <= item["asked"]):
            continue
        if kind in ("owner", "box"):
            kinds.add(kind)
        elif kind == "send":
            if (writer is None or _send_target(use) == writer) and carries(
                    (use.get("input") or {}).get("message"), item["id"], first):
                kinds.add(kind)
        elif kind == "write" and _writes_item(use.get("input"), item["id"], first):
            kinds.add(kind)
    return kinds


def own_tier(hook):
    """(tags, parent) of this session's own newest get_session record, (None, None) on any failure."""
    try:
        _hooks()
        import guard_merge
        import override
        return guard_merge.own_tier(hook.get("transcript_path"), override.remote_session_id())
    except Exception:
        return None, None


def lane_parent(hook):
    """(is_lane, parent): a lane has the lane tag (hooks/guard.py LANE_TAG) or a parent session.
    Owner-facing otherwise."""
    tags, parent = own_tier(hook)
    if guard is None:
        _load_guard()
    tag = getattr(guard, "LANE_TAG", None)
    return (tag in (tags or []) or bool(parent)), parent


def _message_text(rec):
    if rec.get("type") == "attachment":
        att = rec.get("attachment")
        text = att.get("prompt") if isinstance(att, dict) else None
    else:
        text = (rec.get("message") or {}).get("content")
    if isinstance(text, list):
        text = "\n".join(b.get("text", "") for b in text if isinstance(b, dict) and b.get("type") == "text")
    return text if isinstance(text, str) else ""


def _turn_boundary(rec):
    """True for a record that starts a turn: an owner, peer or system-reminder message or a queued command.
    A machine notice (a task notification or an agent hand-back) does not."""
    if rec.get("isSidechain"):
        return False
    if rec.get("type") == "attachment":
        att = rec.get("attachment")
        started = isinstance(att, dict) and att.get("type") == "queued_command"
    elif rec.get("type") != "user":
        return False
    else:
        blocks = _blocks(rec)
        started = isinstance((rec.get("message") or {}).get("content"), str) or (
            any(b.get("type") == "text" for b in blocks)
            and not any(b.get("type") == "tool_result" for b in blocks))
    if not started:
        return False
    import shared_names
    return not _message_text(rec).strip().startswith(shared_names.NOTICE_TAGS)


def lane_reason(records, parent, text):
    """The lane check's refusal when this lane's turn did not send its pick, else ''. The turn starts at
    the last record that holds a message. A send passes when it carries the pick (item id or first line)
    and, with a parent known, goes to the parent or the page writer."""
    _hooks()
    _digest, item_id, first = pick_keys(input_needed_section(text))
    start = max((i for i, rec in enumerate(records) if _turn_boundary(rec)), default=-1)
    writer = _facts(records)[0]
    ids = {x for x in (parent, writer) if x}
    for _at, kind, use in _facts(records[start + 1:])[1]:
        if kind == "box" or (kind == "send" and (not parent or _send_target(use) in ids) and carries(
                (use.get("input") or {}).get("message"), item_id, first)):
            return ""
    return LANE_REASON % ("your parent session (%s)" % parent if parent else
                          "the page writer (read `ArtifactData get meta/page`) or your parent session", item_id)


def _load_items(path):
    try:
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
    except Exception:
        return []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get("id"), str)
            and isinstance(i.get("asked"), (int, float))] if isinstance(items, list) else []


def _save_items(path, items):
    try:
        if items:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f)
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _has_page(hook):
    root = repo_root(hook.get("cwd"))
    return bool(root) and layout.waiting_page(root) != "unknown"


def open_picks_file(hook):
    """The state file path of this session, or None."""
    _hooks()
    import local_time
    return local_time.open_picks_path(hook.get("session_id"))


def _sent_path(path):
    return path + ".sent"


def _sent_hashes(path):
    """The hashes of picks a send, box or items write cleared within SENT_KEEP_SECONDS."""
    try:
        with open(_sent_path(path), encoding="utf-8") as f:
            rows = json.load(f)
    except Exception:
        return []
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get("hash"), str)
            and isinstance(r.get("at"), (int, float)) and now() - r["at"] < SENT_KEEP_SECONDS]


def _remember_sent(path, hashes):
    """Add `hashes` to the sent memory and prune it. Written only when a pick was cleared by a send."""
    if not hashes:
        return
    rows = [r for r in _sent_hashes(path) if r["hash"] not in hashes] + [{"hash": h, "at": now()} for h in hashes]
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(_sent_path(path), "w", encoding="utf-8") as f:
            json.dump(rows, f)
    except Exception:
        pass


def open_pick_check(hook, records, text, after, active):
    """The owner-facing check (questions-go-to-owner, "Chat first, then the page"): (reason, notice).

    Step a clears each item the transcript shows sent or answered; step b keeps this reply's pick open
    unless a send, box or items write of this turn, or of an earlier clearing within 24 hours, sent it;
    step c blocks at 300 s unsent; step d writes the state when it changed. A rewrite Stop (`active`) runs
    step a only. Fails open on any error."""
    try:
        path = open_picks_file(hook)
        if path is None:
            return "", ""
        items = _load_items(path) if os.path.exists(path) else []
        before = list(items)
        writer, sent = None, []
        if items:
            writer, events = _facts(records)
            kept = []
            for i in items:
                kinds = _answers(i, writer, events)
                if kinds - {"owner"}:  # an owner answer is not remembered: he may ask again
                    sent.append(i["hash"])
                if not kinds:
                    kept.append(i)
            items = kept
        reason = notice = ""
        if not active:
            boxed = any(not rec.get("isSidechain") and any(b.get("name") == ASK_TOOL for b in tool_uses(rec))
                        for rec in after)
            if offers_a_pick(text) and not boxed:
                section = input_needed_section(text)
                digest, item_id, _first = pick_keys(section)
                if not any(i.get("hash") == digest for i in items) and not any(
                        r["hash"] == digest for r in _sent_hashes(path)):
                    item = {"id": item_id, "hash": digest, "asked": now(), "text": section[:200]}
                    # A send, box or items write made earlier in this turn answers the pick: judge a new item
                    # against the turn's own calls (not its owner message), not against its ask time.
                    writer, _ = _facts(records)
                    turn = [e for e in _facts(after)[1] if e[1] != "owner"]
                    if _answers(item, writer, turn, timed=False):
                        sent.append(digest)
                    else:
                        items.append(item)
            late = [i for i in items if now() - i["asked"] >= PICK_WAIT_SECONDS]
            if late:
                names = ", ".join("%s (%s)" % (i["id"], ((i.get("text") or "").splitlines() or [""])[0][:160])
                                  for i in late)
                if _has_page(hook):
                    writer = writer or _facts(records)[0]
                    reason = OPEN_PICK_REASON % (
                        names, "the page writer (%s)" % writer if writer else
                        "the page writer: read `ArtifactData get meta/page`")
                else:
                    notice = NO_PAGE_NOTICE % ", ".join(i["id"] for i in late)
                    items = [i for i in items if i not in late]
        if items != before:
            _save_items(path, items)
        _remember_sent(path, sent)
        return reason, notice
    except Exception:
        return "", ""


def open_pick_reasons(hook, records, text, after):
    """(lane, reasons, notice) for a non-rewrite Stop: the lane and owner-facing checks. `lane` is None
    when the reply offers no pick and no state file exists (no tier read is made then)."""
    lane = parent = None
    try:
        path = open_picks_file(hook)
        state = bool(path) and os.path.exists(path)
        if offers_a_pick(text) or state:
            lane, parent = lane_parent(hook)
    except Exception:
        return None, [], ""
    if lane:
        try:
            reason = lane_reason(records, parent, text) if offers_a_pick(text) else ""
        except Exception:
            reason = ""
        return lane, [reason] if reason else [], ""
    if lane is None:
        return None, [], ""
    reason, notice = open_pick_check(hook, records, text, after, False)
    return False, [reason] if reason else [], notice


def _marker_path(hook):
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import local_time
    return local_time.report_marker_path(hook.get("session_id"))


def rewrite_problems(hook):
    """Reasons for the rewrite that follows a missing-report block, or []. The marker is
    consumed before any check, so a second rewrite finds none and stays quiet. It holds the
    index of the turn's human record, so the spawns are read from the same turn whether or not
    the hook's feedback record counts as human. Fails open on any error."""
    try:
        marker = _marker_path(hook)
        if marker is None:
            return []
        with open(marker, encoding="utf-8") as f:
            idx = int(f.read().strip())
        os.remove(marker)
        path = hook.get("transcript_path")
        if not path or not os.path.exists(path):
            return []
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    records.append(rec)
        if idx >= len(records):
            return []
        text = last_reply(hook)
        spawned = spawn_models(records[idx + 1:])
        reasons = []
        models = done_models_problem(text, spawned)
        if models:
            reasons.append(MODELS_REASON + models + ".")
        if unstarted_problem(text, spawned):
            reasons.append(UNSTARTED_REASON)
        return reasons
    except Exception:
        return []


def write_marker(hook, idx):
    try:
        marker = _marker_path(hook)
        if marker is not None:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(str(idx))
    except Exception:
        pass


def emit(old, new, tail, notice):
    """Print the Stop answer: one block holding the old reasons (then `tail`) and the new ones, and the notice."""
    out = {}
    reasons = ([" ".join(old) + tail] if old else []) + new
    if reasons:
        out = {"decision": "block", "reason": " ".join(reasons)}
    if notice:
        out["systemMessage"] = notice
    if out:
        print(json.dumps(out))


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    if hook.get("hook_event_name") != "Stop":
        return
    if hook.get("stop_hook_active"):
        pending_refusals(hook, last_reply(hook))  # clears what the rewrite names; never blocks on a refusal
        try:
            path = open_picks_file(hook)
            if path and os.path.exists(path):  # a rewrite Stop clears what was sent, and never blocks or adds
                open_pick_check(hook, _load_records(hook.get("transcript_path")) or [], "", [], True)
        except Exception:
            pass
        reasons = rewrite_problems(hook)
        if reasons:
            print(json.dumps({"decision": "block", "reason": " ".join(reasons) + CORRECTION_TAIL}))
        return
    # A marker left by a rewrite that never ran must not reach a later turn: only the Stop
    # straight after a missing-report block may consume one.
    try:
        os.remove(_marker_path(hook))
    except Exception:
        pass

    # Every Stop, landed or not, settles the refusals file; the reason joins whichever block follows.
    refusal = refusal_reason(pending_refusals(hook, last_reply(hook)))

    records = _load_records(hook.get("transcript_path"))
    if records is None:
        return emit([refusal] if refusal else [], [], "", "")

    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i
    after = records[last_human_idx + 1:] if last_human_idx is not None else []
    text = last_reply(hook)
    # The lane and owner-facing pick checks. A lane's pick is judged by the lane check alone: the chat-first
    # promise and the page link pass nothing for it, so the pick guard below skips it.
    lane, new, notice = open_pick_reasons(hook, records, text, after)
    if last_human_idx is None:
        return emit([refusal] if refusal else [], new, "", notice)

    if not turn_landed(after):
        # An unlanded turn is judged on the pick check and the Departs from check alone. An error in
        # either fails open on its own: the Departs from check never drops the pick refusal.
        pick = []
        try:
            if not lane and offers_a_pick(text) and not pick_has_a_control(after, text, hook.get("cwd")):
                pick.append(PICK_REFUSAL)
        except Exception:
            pass
        try:
            pick.append(departs_problem(text))
        except Exception:
            pass
        pick.append(refusal)
        pick = [r for r in pick if r]
        return emit(pick, new, CORRECTION_TAIL if report_shape_ok(text) else "", notice)

    shape_ok = report_shape_ok(text)
    reasons = [] if shape_ok else [BLOCK_REASON_HEAD + BLOCK_REASON_TAIL]
    item = done_format_problem(text) if shape_ok else ""
    if item:
        reasons.append(
            "Report-shape guard: each Done line must say BUILT, RECORDED, or OTHER. BUILT and "
            "RECORDED must also name a PR or commit. This one does not: " + repr(item) + ".")
    spawned = spawn_models(after)
    models = done_models_problem(text, spawned) if shape_ok else ""
    if models:
        reasons.append(MODELS_REASON + models + ".")
    if shape_ok and unstarted_problem(text, spawned):
        reasons.append(UNSTARTED_REASON)
    try:
        if not lane and offers_a_pick(text) and not pick_has_a_control(after, text, hook.get("cwd")):
            reasons.append(PICK_REFUSAL)
    except Exception:
        pass
    try:
        departs = departs_problem(text)
        if departs:
            reasons.append(departs)
    except Exception:
        pass
    cite = bare_cite(text)
    if cite:
        reasons.append(
            "Cite-gloss guard: " + repr(cite) + " is a record id with no short gloss. Write the id "
            "plus a few words, like \"D12, short titles for records\".")
    if refusal:
        reasons.append(refusal)
    if reasons and not shape_ok:
        write_marker(hook, last_human_idx)
    emit(reasons, new, CORRECTION_TAIL if shape_ok else "", notice)


if __name__ == "__main__":
    main()
