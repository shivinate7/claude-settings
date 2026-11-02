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

On any turn whose reply holds an Input Needed item that asks the owner a question (a pick with
options, or a sentence ending in "?" outside quotes and backticks), it also blocks unless the turn
holds a qualifying act (`questions-reach-page`: every question goes to the page writer in the same
turn it is asked, no clock). The turn is every record after the last
incoming message, a peer's included. Owner-facing session: the question box (main session), a send to
the page writer (the `writer` in the newest meta/page read), or an ArtifactData set, update or batch under
collection items to this repo's page. Lane (own get_session record tagged cs-build:lane, or with a
parent): a send to @parent, the parent id or the writer. A promise or a page link passes nothing. A
repo with no waiting page gets a systemMessage and no block, unless the session is a lane. This check
does not wait for a git write: the reply's labels are what it reads. Cost: no file written. Reads: the
transcript this hook already holds; one layout read, the own-record import (hooks/own_session.py) and one
more transcript read, only on a turn that asks with no qualifying act (`decisions-reach-a-clickable-pick`).
The same pick must carry a valid "Departs from:" line in that Input Needed item (`question-departs`, judged by
hooks/question_form.py departs_hit, on landed and unlanded turns alike). Cost: one regex read of that item and one module import, no file.

On every Stop, landed or not, it also reads <config dir>/state/refusals/<session_id>.jsonl, which
hooks/refusal_note.py writes for each tool the auto-mode classifier refused. A pending tool the reply
does not name in its Input Needed section blocks. A built-in tool counts only in backticks; an MCP
tool counts by its full name. Each tool the reply names is cleared, on a
stop_hook_active rewrite too, which never blocks on a refusal (decision refusals-reach-the-owner).
Cost: one stat per Stop when the session had no refusal.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import (  # noqa: E402
    ARTIFACT_DATA, is_last_human, items_write, last_incoming_index, last_reply, page_writer_id, send_targets,
    tool_uses)
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

OWNER_REFUSAL = (
    "Pick guard: every question goes to the page writer in the same turn it is asked (owner, 2026-11-01 "
    "23:31 CST). Send it now: %s. With nothing running, the question box also counts."
)
LANE_REFUSAL = (
    "Lane pick guard: a lane's own chat does not reach the owner. Send this question to your parent "
    "(send_message session_id @parent) now."
)
NO_PAGE_NOTE = "pick not sent: this repo has no waiting page"
LANE_TAG = "cs-build:lane"
PARENT_TARGETS = ("@parent", "parent")
# A "?" ends a question only before whitespace, the end or markup, so a URL query never counts. Quoted
# text, backticked text and a blockquoted line are past words, never a question asked now. A quote opens
# only at a non-word edge, so a lone quote cannot span to the next one.
QUOTED_RE = re.compile(r'(?<!\w)"[^"\n]*"(?!\w)|\u201c[^\u201d\n]*\u201d|`[^`\n]*`')
QUESTION_MARK_RE = re.compile(r"\?(?=[^\w?]*(?:\s|$))")


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


def asks_a_question(text):
    """True when the Input Needed item holds a sentence that ends in "?" outside quotes, backticks and
    blockquoted lines (questions-reach-page: a question for the owner, whether or not it offers a pick)."""
    section = input_needed_section(text)
    kept = "\n".join(line for line in section.splitlines() if not line.lstrip().startswith(">"))
    return bool(QUESTION_MARK_RE.search(QUOTED_RE.sub("", kept)))


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


def _own_lane_read(hook, path):
    """(is_lane, parent id): this session's own get_session record in the transcript. A lane carries the
    tag cs-build:lane or a parent_session_id. No own id or no record reads as owner-facing."""
    from override import remote_session_id
    own_id = remote_session_id()
    if not own_id:
        return False, None
    import own_session
    tags, _tagged_after, parent = own_session.own_session_read(path, own_id)
    return tags is not None and (LANE_TAG in tags or bool(parent)), parent


def question_problem(records, turn, text, hook):
    """(refusal, note) for a reply whose Input Needed item asks the owner a question (a pick or a "?"
    sentence), judged on `turn`, the records after the last incoming message (questions-reach-page).
    Owner-facing: the question box, a send to the page writer, or an items write to this repo's page.
    Lane: a send to the parent or the page writer. A send to @parent passes in any session. Cost: nothing
    past the text check when the turn has no question or sends to @parent; else the own-record import and a
    transcript read, and the layout read only when no question box or writer send is in the turn."""
    if not (offers_a_pick(text) or asks_a_question(text)):
        return "", ""
    main = [r for r in turn if not r.get("isSidechain")]
    uses = [u for r in main for u in tool_uses(r)]
    sends = [send_targets(u) for u in uses]
    if any(t & set(PARENT_TARGETS) for t in sends):
        return "", ""
    writer = page_writer_id(records)
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    lane, parent = _own_lane_read(hook, hook.get("transcript_path"))
    if lane:
        wanted = ({parent} if parent else set()) | ({writer} if writer else set())
        return ("" if any(t & wanted for t in sends) else LANE_REFUSAL), ""
    if any(u.get("name") == ASK_TOOL for u in uses):
        return "", ""
    if writer and any(writer in t for t in sends):
        return "", ""
    root = repo_root(hook.get("cwd"))
    page = layout.waiting_page(root) if root else "unknown"
    here = None if page == "unknown" else page.rstrip("/")
    for u in uses:
        inp = u.get("input")
        if (str(u.get("name", "")).startswith(ARTIFACT_DATA) and isinstance(inp, dict) and items_write(inp)
                and (here is None or str(inp.get("url", "")).rstrip("/") == here)):
            return "", ""
    if here is None:
        return "", NO_PAGE_NOTE
    route = ("send_message to the writer " + writer if writer else
             "read meta/page on " + page + " with ArtifactData get, then send_message the question to its writer")
    return OWNER_REFUSAL % route, ""


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

    def stop_for_refusal():
        if refusal:
            print(json.dumps({"decision": "block", "reason": refusal}))

    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return stop_for_refusal()

    records = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    records.append(rec)
    except Exception:
        return stop_for_refusal()

    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i

    text = last_reply(hook)
    # The pick check reads the turn after the last incoming message, a peer's included (a lane's input),
    # and runs whether or not the transcript holds a human record. Landing and the report's shape still
    # anchor on the last human message.
    incoming = last_incoming_index(records)
    turn = records if incoming is None else records[incoming + 1:]
    after = [] if last_human_idx is None else records[last_human_idx + 1:]
    note = ""
    pick_reason = ""
    try:
        pick_reason, note = question_problem(records, turn, text, hook)
    except Exception:
        pass
    if last_human_idx is None or not turn_landed(after):
        # An unlanded turn is judged on the question check and the Departs from check alone. An error in
        # either fails open on its own: the Departs from check never drops the question refusal.
        pick = [pick_reason]
        try:
            pick.append(departs_problem(text))
        except Exception:
            pass
        try:
            pick.append(refusal)
            pick = [r for r in pick if r]
            if pick:
                reason = " ".join(pick) + (CORRECTION_TAIL if report_shape_ok(text) else "")
                print(json.dumps({"decision": "block", "reason": reason}))
            elif note:
                print(json.dumps({"systemMessage": note}))
        except Exception:
            pass
        return

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
    if pick_reason:
        reasons.append(pick_reason)
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
    if reasons:
        reason = " ".join(reasons)
        if shape_ok:
            reason += CORRECTION_TAIL
        else:
            write_marker(hook, last_human_idx)
        print(json.dumps({"decision": "block", "reason": reason}))
    elif note:
        print(json.dumps({"systemMessage": note}))


if __name__ == "__main__":
    main()
