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
A reply that holds Input Needed or a prose line ending in `?` also gets the past-ruling check (one Sonnet call, rule
`past-ruling`, or the Unvetted remedy) and the option-key check (rule `question-keys`), both from hooks/question_form.py.
The same pick must carry a valid "Departs from:" line in that Input Needed item (`question-departs`, judged by
hooks/question_form.py departs_hit, on landed and unlanded turns alike). Cost: one regex read of that item and one module import, no file.
On landed turns it also blocks a reply sentence that says decision D was rewritten (rewritten, rewrote,
rewrites, rewrite of) for a ruling when D's record was last committed before that ruling, on the default
branch and on HEAD alike (`reports-rewrite-stamp`, named incident F119: sessions said decision ci-job-caps
was rewritten for the owner's 2026-11-01 18:44 CST ruling while main showed it last touched on Oct 28).
The ruling time is a stamp in the sentence (`YYYY-MM-DD HH:MM <zone>`, or `HH:MM <zone>` on the turn's
Central date), else, for "under" or "by" decision R, R's last commit on the default branch. "In place"
alone does not trigger. An unknown id, no time or a failed git read passes. Cost: one regex read of the
reply, and only on a reply that matches it, one `git log -1` process per cited record (at most
REWRITE_CAP) plus the default-branch lookup; no file, no timer, no log.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import (  # noqa: E402
    is_last_human, last_reply, read_transcript, records_after_last_human, tool_uses)
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


# reports-rewrite-stamp: a sentence that says decision D was rewritten for a ruling. See the module docstring.
REWRITE_RE = re.compile(r"\b(?:rewrote|rewritten|rewrites|rewrite\s+of)\b", re.I)
REWRITE_CAP = 5  # most records one reply may make this check read
_SLUG = r"[a-z0-9][a-z0-9-]*"
DECISION_ID_RE = re.compile(r"\bdecisions?\s+`?(" + _SLUG + r")`?", re.I)
RULING_BY_RE = re.compile(r"\b(?:under|by)\s+(?:decisions?\s+)?`?(" + _SLUG + r")`?", re.I)
STAMP_FULL_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})\s*(CST|CDT|UTC|GMT)\b")
STAMP_CLOCK_RE = re.compile(r"(?<![\d:-])(\d{1,2}:\d{2})\s*(CST|CDT|UTC|GMT)\b")
STAMP_ZONE_HOURS = {"CST": -6, "CDT": -5, "UTC": 0, "GMT": 0}
FENCE_RE = re.compile(r"```.*?```", re.S)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n")


def _central(at):
    """`YYYY-MM-DD HH:MM CST` (or CDT) for an instant, from the time hook's own clock."""
    import local_time
    return " ".join(local_time.line(lambda: at).split()[2:5])


def _parse_iso(value):
    from datetime import datetime, timezone
    at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def _stamp_time(sentence, human_ts):
    """The ruling instant a stamp in `sentence` names, else None. A clock-only stamp takes the Central
    date of the last human record's timestamp, else of the hook's clock."""
    from datetime import datetime, timedelta, timezone
    full = STAMP_FULL_RE.search(sentence)
    if full:
        day, clock, zone = full.groups()
    else:
        clk = STAMP_CLOCK_RE.search(sentence)
        if not clk:
            return None
        import local_time
        try:
            turn = _parse_iso(human_ts)
        except (TypeError, ValueError):
            turn = local_time.clock()
        day = _central(turn).split()[0]
        clock, zone = clk.groups()
    hour, minute = clock.split(":")
    tz = timezone(timedelta(hours=STAMP_ZONE_HOURS[zone]))
    year, month, date = (int(x) for x in day.split("-"))
    return datetime(year, month, date, int(hour), int(minute), tzinfo=tz)


def rewrite_stamp_problem(text, human_ts, cwd):
    """The refusal text when a sentence says decision D was rewritten for a ruling that is later than
    D's last commit on the default branch and on HEAD, else ''. Fails open on any unknown."""
    sentences = [s for s in SENTENCE_SPLIT_RE.split(FENCE_RE.sub(" ", text)) if REWRITE_RE.search(s)]
    if not sentences:
        return ""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import git_reads
    from datetime import datetime, timezone
    root = repo_root(cwd)
    if not root:
        return ""
    folder = layout.path(root, "decisions")
    base = git_reads.resolve_default_base(root)
    if not base:
        return ""
    reasons, seen = [], set()
    for sentence in sentences:
        by = RULING_BY_RE.search(sentence)
        cited = [m for m in DECISION_ID_RE.finditer(sentence) if not (by and by.start() <= m.start() < by.end())]
        if not cited:
            continue
        d = cited[0].group(1).lower()
        if d in seen or len(seen) >= REWRITE_CAP:
            continue
        seen.add(d)
        ruling = _stamp_time(sentence, human_ts)
        if ruling is None and by:
            r_epoch = git_reads.last_commit_epoch(root, [base], "%s/%s.md" % (folder, by.group(1).lower()))
            if r_epoch is not None:
                ruling = datetime.fromtimestamp(r_epoch, timezone.utc)
        if ruling is None:
            continue
        d_epoch = git_reads.last_commit_epoch(root, [base, "HEAD"], "%s/%s.md" % (folder, d))
        if d_epoch is None or d_epoch >= ruling.timestamp():
            continue
        reasons.append(
            "Rewrite-stamp guard: decision `%s` was last committed %s, on main and on HEAD, before the "
            "ruling %s that it is said to be rewritten for. Rewrite the record first, or say it is not "
            "rewritten yet." % (d, _central(datetime.fromtimestamp(d_epoch, timezone.utc)), _central(ruling)))
    return " ".join(reasons)


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


# A relayed question (spec past-rulings): a coordinator puts a lane's question in its reply, under Input Needed or as
# a prose line that ends in `?`, so neither check in hooks/call_judge.py sees it. This Stop hook checks it, SYNC, with
# the same candidates and the same item 8 as the question judge, and one more rule: option keys (question-keys).
# Cost: one git process and one Sonnet call (15 s) on a Stop whose reply asks something; none on any other Stop.
RELAY_RULE_REASON = (
    "Past-ruling guard (rule past-ruling): %s Remedy: drop the question, or add a `Based on (ruling): <id>` line "
    "that names that ruling and says why the owner is asked again.")
UNVETTED_REASON = (
    "Unvetted guard: the past-ruling check could not run (%s), so this question would reach the owner unchecked. "
    "Add the line `Unvetted: <why it could not be checked>` to the question and send it again.")
KEYS_REASON = (
    "Question-keys guard (rule question-keys): two questions to the owner use the option key(s) %s, so his answer "
    "could mean either. Give each question its own keys, such as 1a/1b for the first and 2a/2b for the second, and "
    "send the questions again.")
ASK_TEXT_MAX = 6000
# A `?` that ends a sentence: before white space or the line end, and after any closing mark. A `?` inside a URL or a
# code span is no question.
SENTENCE_QUESTION = re.compile(r"\?[*_)\"']*(?:\s|$)")
# A code span: a run of backticks, its text, and a closing run of the same length (CommonMark).
CODE_SPAN = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")
QUOTE_PREFIX = re.compile(r"^[ ]{0,3}(?:>[ ]?)*")
INDENTED_CODE = re.compile(r"^(?: {4}|\t)")
UNVETTED_AFTER_SENTENCE = re.compile(r"([.?!][*_)\"']*)[ \t]+(?=Unvetted:[ \t]*\S)", re.I)
LIST_ITEM = re.compile(r"^[ ]{0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")


def prose_questions(text):
    """The reply's own prose lines that hold a sentence ending in `?`, outside fenced code, indented code and code
    spans. A blockquote line counts. Indented code opens after a blank line or another code line, as in CommonMark;
    inside a list an indented line is list text, never code."""
    found, fenced, code_ok, in_list = [], False, True, False
    for line in text.splitlines():
        inner = QUOTE_PREFIX.sub("", line, count=1)
        body = inner.strip()
        if body.startswith("```"):
            fenced, code_ok = not fenced, True
            continue
        if fenced:
            continue
        if not body:
            code_ok = True
            continue
        indented = bool(INDENTED_CODE.match(inner))
        if code_ok and indented and not in_list:
            continue  # code_ok stays True: the next indented line is code too
        code_ok = False
        if LIST_ITEM.match(inner):
            in_list = True
        elif not indented:
            in_list = False
        if SENTENCE_QUESTION.search(CODE_SPAN.sub("", body)):
            found.append(body)
    return found


def has_input_needed(text):
    """True when the reply's Input Needed label holds an item (hooks/reply_judge.py, the one reader)."""
    if "input needed" not in text.casefold():
        return False
    try:
        sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
        from reply_judge import has_input_needed as home
        return home(text)
    except Exception:
        return True  # an unreadable reader means the item is judged, never skipped


def asked_text(text):
    """The text that asks the owner something, capped from the front so the end of a report stays: the whole text
    when Input Needed holds an item, else its prose question lines with its `Unvetted:` lines, else ''. The
    Unvetted lines stay so the Unvetted remedy can be met in a prose question."""
    if has_input_needed(text):
        return text[-ASK_TEXT_MAX:]
    questions = prose_questions(text)
    if not questions:
        return ""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import question_form  # the one home of the Unvetted line
    # An Unvetted marker after the question's own sentence, on its line, goes on a line of its own.
    questions = [UNVETTED_AFTER_SENTENCE.sub(r"\1\n", q) for q in questions]
    unvetted = [line.strip() for line in text.splitlines() if question_form.UNVETTED_LINE.match(line)]
    return "\n".join(questions + [u for u in unvetted if u not in questions])[-ASK_TEXT_MAX:]


def cannot_run(asked, why):
    """The Unvetted refusal for a check that could not run, or '' when the asked text carries its own
    `Unvetted:` line. The marker is read only here, so it never skips a check that can run."""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import question_form
    return "" if question_form.has_unvetted(asked) else UNVETTED_REASON % why


def past_ruling_problem(asked, cwd):
    """The refusal text for asked text that a past ruling settles, or that could not be checked, else ''."""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import question_form
    candidates, unknown = question_form.past_rulings(asked, repo_root(cwd) or cwd or os.getcwd())
    print(question_form.unknown_line(unknown), file=sys.stderr)
    unreadable = question_form.unreadable_sources(unknown)
    if unreadable:
        return cannot_run(asked, "; ".join(unreadable))
    import call_judge  # the one home of item 8, its model and its time limit
    import decision_watch
    prompt = ("Review this text, which a session sends the owner and which asks him something:\n<<<\n" + asked
              + "\n>>>\nJudge only item 8 below. Answer {\"ok\": true} at once when no listed ruling settles what "
              "it asks.\n8. " + call_judge.PAST_RULING_ITEM + "\nReply JSON only: {\"ok\": true} or {\"ok\": false, "
              "\"reason\": \"<the listed id, the ruling's date, and what it decides, one line>\"}."
              + question_form.candidates_block(candidates, unknown))
    verdict, error = decision_watch.invoke_model(prompt, model=call_judge.PAST_RULING_MODEL,
                                                 timeout=call_judge.PAST_RULING_TIMEOUT,
                                                 shape=call_judge.OK_SHAPE, effort=None)
    if error:
        return cannot_run(asked, " ".join(str(error).split()))
    if verdict.get("ok") is not False:
        return ""
    reason = verdict.get("reason")
    reason = reason.strip() if isinstance(reason, str) and reason.strip() else "a past ruling settles this."
    if question_form.ruling_cite(reason, question_form.candidate_ids(candidates), strict=True) != "cited":
        return cannot_run(asked, "the review cited a record that was not in the list")
    return RELAY_RULE_REASON % reason


def since_last_message(after):
    """The records after the last user record that is not a tool result: an owner message or a peer's message. A
    past-ruling check reads only the replies to that message, so an older question is not judged again."""
    start = 0
    for i, rec in enumerate(after):
        content = (rec.get("message") or {}).get("content")
        if rec.get("type") != "user" or rec.get("isSidechain"):
            continue
        if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            continue
        start = i + 1
    return after[start:]


def earlier_replies(after, text):
    """The assistant text replies since the last human message, without the reply being judged."""
    texts = []
    for rec in after:
        content = (rec.get("message") or {}).get("content")
        if rec.get("type") != "assistant" or rec.get("isSidechain") or not isinstance(content, list):
            continue
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        if parts:
            texts.append("\n".join(parts))
    if texts and texts[-1].strip() == text.strip():
        texts.pop()
    return texts


def question_keys_problem(after, text):
    """The refusal text when two questions share an option key (question_form.key_overlap), else ''."""
    if "input needed" not in text.casefold():
        return ""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    import question_form
    clash = question_form.key_overlap(text, earlier_replies(after, text))
    return KEYS_REASON % clash if clash else ""


def relay_reasons(after, text, cwd):
    """Refusals for the questions the reply relays to the owner, read from every assistant text since the last
    human message. An error in the option-key check allows, with one stderr line. An error in the past-ruling check
    is a check that could not run, so it refuses as Unvetted."""
    reasons = []
    try:
        reasons.append(question_keys_problem(after, text))
    except Exception as exc:
        print("question-keys check failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    try:
        asked = asked_text("\n\n".join(earlier_replies(since_last_message(after), text) + [text]))
        if asked:
            try:
                reasons.append(past_ruling_problem(asked, cwd))
            except Exception as exc:
                print("past-ruling check failed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
                reasons.append(cannot_run(asked, "the check failed with " + type(exc).__name__))
    except Exception as exc:
        print("past-ruling check could not start: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    return [r for r in reasons if r]


def rewrite_relay(hook):
    """The relay refusals for the rewrite that follows a block: it is checked again, so a rewrite that keeps a ruled
    question is refused again. At most one model call per Stop."""
    try:
        path = hook.get("transcript_path")
        records = read_transcript(path) if path and os.path.exists(path) else []
        return relay_reasons(records_after_last_human(records), last_reply(hook), hook.get("cwd"))
    except Exception as exc:
        print("relay check on a rewrite failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return []


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
        reasons = rewrite_problems(hook)
        reasons += rewrite_relay(hook)
        if reasons:
            print(json.dumps({"decision": "block", "reason": " ".join(reasons) + CORRECTION_TAIL}))
        return
    # A marker left by a rewrite that never ran must not reach a later turn: only the Stop
    # straight after a missing-report block may consume one.
    try:
        os.remove(_marker_path(hook))
    except Exception:
        pass

    path = hook.get("transcript_path")
    if not path or not os.path.exists(path):
        return

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
        return

    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i
    if last_human_idx is None:
        return

    after = records[last_human_idx + 1:]
    text = last_reply(hook)
    relay = relay_reasons(after, text, hook.get("cwd"))
    if not turn_landed(after):
        # An unlanded turn is judged on the pick check and the Departs from check alone. An error in
        # either fails open on its own: the Departs from check never drops the pick refusal.
        pick = []
        try:
            if offers_a_pick(text) and not pick_has_a_control(after, text, hook.get("cwd")):
                pick.append(PICK_REFUSAL)
        except Exception:
            pass
        try:
            pick.append(departs_problem(text))
        except Exception:
            pass
        pick += relay
        try:
            pick = [r for r in pick if r]
            if pick:
                reason = " ".join(pick) + (CORRECTION_TAIL if report_shape_ok(text) else "")
                print(json.dumps({"decision": "block", "reason": reason}))
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
    try:
        if offers_a_pick(text) and not pick_has_a_control(after, text, hook.get("cwd")):
            reasons.append(PICK_REFUSAL)
    except Exception:
        pass
    try:
        departs = departs_problem(text)
        if departs:
            reasons.append(departs)
    except Exception:
        pass
    reasons += relay
    try:
        rewrite = rewrite_stamp_problem(text, records[last_human_idx].get("timestamp"), hook.get("cwd"))
        if rewrite:
            reasons.append(rewrite)
    except Exception:
        pass
    cite = bare_cite(text)
    if cite:
        reasons.append(
            "Cite-gloss guard: " + repr(cite) + " is a record id with no short gloss. Write the id "
            "plus a few words, like \"D12, short titles for records\".")
    if reasons:
        reason = " ".join(reasons)
        if shape_ok:
            reason += CORRECTION_TAIL
        else:
            write_marker(hook, last_human_idx)
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
