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
incoming message, a peer's included; the ack of a send this turn made to the writer or the parent
starts no turn. Owner-facing session: a send to
the page writer (the `writer` in the newest meta/page read), or an ArtifactData set, update or batch under
collection items to this repo's page; the question box (main session) counts only in a repo with no page. Lane (own get_session record tagged cs-build:lane, or with a
parent): a send to @parent, the parent id or the writer; @parent counts only in a lane. A promise or a page link passes nothing. A
repo with no waiting page gets a systemMessage and no block, unless the session is a lane. This check
does not wait for a git write: the reply's labels are what it reads. Cost: no file written. Reads: the
transcript this hook already holds. Only on a turn that asks with no send to the writer: the
own-record import (hooks/own_session.py) and one more transcript read, in a session with a remote id. A lane
reads no layout; an owner-facing turn with no counted send reads it once (`decisions-reach-a-clickable-pick`).
A reply that holds Input Needed or a prose line ending in `?` also gets the past-ruling check (one Sonnet call, rule
`past-ruling`, or the Unvetted remedy) and the option-key check (rule `question-keys`), both from hooks/question_form.py.
The same pick must carry a valid "Departs from:" line in that Input Needed item (`question-departs`, judged by
hooks/question_form.py departs_hit, on landed and unlanded turns alike). Cost: one regex read of that item and one module import, no file.
On landed turns it also refuses a reply sentence that says a decision was rewritten (rewritten, rewrote,
rewrites, rewrite of) for a ruling when that decision's record was last committed before the ruling, on
every local branch, every remote branch and HEAD (`rewrite-cite-predates-ruling`, named incident F119:
a report said a decision was rewritten for a ruling that its record's last commit predates). A cited id is a word next to the rewrite word that names a file in the
decisions folder; no "decision" word is needed, and an id after under, by, per, following or see is not
checked. A queued sentence (pending, queued), or a rewrite word just after a negation or a modal (not,
no, never, will, should, must, can, may, could, needs and the like), claims no rewrite. The ruling time is
the stamp next to the word "ruling" ("the <stamp> ruling", "ruling at <stamp>", "ruling of <stamp>"):
`YYYY-MM-DD HH:MM <zone>`, or `HH:MM <zone>` on the turn's Central date, the day before when that is
later than the turn. With no such stamp the sentence passes. "In place" alone does not trigger. An id
with no record file or a failed git read passes. Cost: one regex read of the reply, and only on a reply
that matches it, one `git log -1` process per distinct cited id with a record file in the reply, at most
REWRITE_CAP; no file written, no timer, no log.

The answered-source check (rule `answered-needs-source`): on any turn, landed or not, it refuses each line of the last reply
that holds the whole word "answered" (any case, outside fences and inline code spans, not hyphen-joined to another word)
unless the same line cites a source: a URL, `#<n>`, a commit hash, a repo path, `item <n>`, `page:<n>`, an `fb-` id, a
`session_` id or `HH:MM`. A negator in the same clause before the word exempts it, as does `[question] -> answered`. One
refusal per turn lists the lines and joins any other reason. A rewrite after a missing-report refusal is checked too. Risk
kind and incident: decision answered-needs-source. Cost: regex over the reply, no file, no process.

After a compaction, each report also holds a `Recovered:` line and a `Handoff gave:` line (each
may say `none`) in the report blockquote, until one lands (`compaction-carry`, decision
precompact-handoff, item 'Recovered line after compaction'). A label counts only where it starts an item: at line start, after a
report label, or after "; " or ". ". A compaction is the newest `compact_boundary` system record.
Each line is tracked alone: any main-session reply after it that holds the line satisfies that
demand; the current reply counts by its blockquote. A bare `Recovered:` takes the lines below it as
its items; with nothing below, it is missing. While the Recovered demand is pending, each item of
the current Recovered line (split on ";" outside parentheses) names a whole-word source: git, page
or digest. An item that starts with "none" or "nothing" needs no source. The demand holds on landed turns and unlanded turns
whose reply has the report shape, and in the rewrite after a missing-report block when the rewrite
has the report shape. Cost: a scan of the records main()
already loaded (the rewrite reads the transcript once, as before); no file, log or process.
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
    ARTIFACT_DATA, is_last_human, items_write, last_incoming_index, last_reply, page_writer_id, peer_sender,
    read_transcript, records_after_last_human, send_targets, tool_uses)
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
# A bold "**Departs from:**" starts a line of the item (rule `question-departs`), and a bold
# "**Recovered:**" or "**Handoff gave:**" is a compaction-carry line below; none is a report label.
LABEL_RE = re.compile(r"^\*\*(?!(?i:Departs from|Recovered|Handoff gave))(.+?)\*\*")
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


# answered-needs-source: a reply line that says "answered" names where the answer came from. The source
# patterns reuse DONE_REF_RE (`#<n>`, PR refs, commit hashes, /pull/ and /commit/ URLs) and CODE_SPAN. Fence lines
# are found as in prose_questions. A quote pairs only inside one line. A repo path is a token with `/` that has a
# file extension or a known top dir, or a bare file name with a known extension, so "and/or" is no source.
# The word is not part of a hyphen-joined name (a rule anchor such as answered-needs-source). A negator in the
# same clause before it (a clause breaks at . ; : ! ? , or a dash) exempts it: not, n't, no, none, nothing,
# nobody, never, cannot, yet to. A line that ends in `?` asks and claims nothing.
ANSWERED_RE = re.compile(r"(?<![\w-])answered(?![\w-])", re.I)
ANSWERED_INBOX_RE = re.compile(r"\[question\]\s*(?:->|\u2192)\s*answered\b", re.I)
ANSWERED_NEGATOR_RE = re.compile(r"\bnot\b|n['\u2019]t\b|\bno(?:ne|thing|body)?\b|\bnever\b|\bcannot\b|\byet\s+to\b", re.I)
ANSWERED_CLAUSE_BREAK_RE = re.compile(r"[.;:!?,\u2014\u2013]|\s-{1,2}\s")
ANSWERED_TOP_DIRS = {"docs", "hooks", "lint", "bin", "skills", "agents", "roadmap"}
ANSWERED_FILE_RE = re.compile(
    r"\b[\w-]+\.(?:py|md|json|jsonl|js|ts|sh|txt|ya?ml|toml|html|css|log|cfg|ini)\b")
ANSWERED_SOURCE_RE = re.compile(
    r"https?://\S+|\bitem\s+\d+|\bpage:\d+|\bfb-\w+|\bsession_\w+|\b\d{1,2}:\d{2}\b", re.I)
ANSWERED_REASON = (
    "Answered guard (rule answered-needs-source): each line below says \"answered\" and cites no source. Add "
    "where the answer came from on the same line (a link, #<n>, a commit, a file path, item <n>, a session or "
    "inbox id, or the time), or say what is meant in other words. Lines: ")


def _has_path(line):
    for token in line.split():
        if "/" in token and (re.search(r"\w\.\w", token) or ANSWERED_TOP_DIRS & set(re.split(r"[/\s]+", token))):
            return True
    return bool(ANSWERED_FILE_RE.search(line))


def _claims_answered(plain):
    """True when `plain` holds the word with no negator in its clause before it."""
    for m in ANSWERED_RE.finditer(plain):
        clause = ANSWERED_CLAUSE_BREAK_RE.split(plain[:m.start()])[-1]
        if not ANSWERED_NEGATOR_RE.search(clause):
            return True
    return False


def answered_problem(text):
    """The refusal for reply lines that say "answered" with no source on the line, else ''."""
    if not ANSWERED_RE.search(text):
        return ""
    bad, fence = [], ""
    for line in text.splitlines():
        body = QUOTE_PREFIX.sub("", line, count=1).strip()
        marker = body[:3] if body[:3] in ("```", "~~~") else ""
        if marker and (not fence or marker == fence):
            fence = "" if fence else marker
            continue
        if fence or body.rstrip("*_)\"' ").endswith("?"):
            continue
        plain = ANSWERED_INBOX_RE.sub(" ", CODE_SPAN.sub(" ", body))
        if not _claims_answered(plain):
            continue
        kept = CODE_SPAN.sub(lambda m: m.group(2), body)
        if DONE_REF_RE.search(kept) or ANSWERED_SOURCE_RE.search(kept) or _has_path(kept):
            continue
        bad.append(body)
    return ANSWERED_REASON + "".join("\n- " + b for b in bad) if bad else ""


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
    "23:31 CST). Send it now: %s."
)
LANE_REFUSAL = (
    "Lane pick guard: a lane's own chat does not reach the owner. Send this question to your parent "
    "(send_message session_id @parent) now."
)
NO_PAGE_NOTE = "pick not sent: this repo has no waiting page"
LANE_TAG = "cs-build:lane"
PARENT_TARGETS = {"@parent", "parent"}
# A "?" ends a question unless a word character follows it, so a URL query (a?b=1) never counts. Quoted
# text, backticked text and a blockquoted line are past words, never a question asked now. A straight
# quote, double or single, opens and closes only at a non-word edge, so a lone quote or an apostrophe
# (Don't) cannot span to the next quote.
QUOTED_RE = re.compile(r'(?<!\w)"[^"\n]*"(?!\w)|(?<!\w)\'[^\'\n]*\'(?!\w)|\u201c[^\u201d\n]*\u201d|`[^`\n]*`')
QUESTION_MARK_RE = re.compile(r"\?(?!\w)")


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


# compaction-carry: after a compaction the session reports two lines, `Recovered:` (what it got back
# from git, the page or a digest) and `Handoff gave:` (what the handoff supplied that the summary
# did not), each until one lands. A label counts only where it starts an item: at line start (after
# `>`, a bullet, and bold, backtick or quote marks), right after a report label, or after "; " or
# ". ". So a mid-sentence "recovered:" or a backticked name of the guard is never a carry line.
CARRY_MARKS = "*_`\"'“”‘’"
CARRY_START = (r"(?:^[ \t]*(?:>[ \t]*)*(?:(?:[-*+]|\d+[.)])[ \t]+)?(?:\*\*(?:%s):?\*\*:?[ \t]*)?|[.;][ \t]+)"
               r"[%s]*" % ("|".join(re.escape(label) for label in LABEL_ORDER), re.escape(CARRY_MARKS)))
CARRY_LINES = (
    ("Recovered", re.compile(CARRY_START + r"recovered(?:\*\*)?:", re.I | re.M)),
    ("Handoff gave", re.compile(CARRY_START + r"handoff gave(?:\*\*)?:", re.I | re.M)),
)
CARRY_FORMS = {
    "Recovered": "`Recovered: <each fact, with its source: git, page or digest>`, or `Recovered: none`",
    "Handoff gave": "`Handoff gave: <facts the handoff supplied that the summary did not>`, "
                    "or `Handoff gave: none`",
}
SOURCE_RE = re.compile(r"\b(?:git|page|digest)\b", re.I)
NONE_ITEM_RE = re.compile(r"(?:none|nothing)\b", re.I)


def _reply_text(rec):
    """The text of a main-session assistant record, else None."""
    if rec.get("type") != "assistant" or rec.get("isSidechain"):
        return None
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list):
        return None
    parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(parts) if parts else None


def _carry_split(rest):
    """`rest` split into items on ";" outside parentheses, each stripped of marks and a trailing . or ;."""
    items, depth, cur = [], 0, ""
    for ch in rest:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif ch == ";" and depth == 0:
            items.append(cur)
            cur = ""
            continue
        cur += ch
    items.append(cur)
    out = []
    for item in items:
        item = item.strip(" \t" + CARRY_MARKS).rstrip(" .;").strip(" \t" + CARRY_MARKS)
        if item:
            out.append(item)
    return out


def recovered_items(text):
    """The items of each Recovered line in `text`, or None when it holds no Recovered line. A line's
    text runs to the end of its line, or to a Handoff gave label on the same line. A bare
    `Recovered:` takes the lines below it, up to the next report label or carry label, as its items;
    with nothing below it is no line."""
    found = None
    lines = text.splitlines()
    rx, handoff = CARRY_LINES[0][1], CARRY_LINES[1][1]
    for n, line in enumerate(lines):
        m = rx.search(line)
        if not m:
            continue
        cut = handoff.search(line, m.end())
        items = _carry_split(line[m.end():cut.start() if cut else len(line)])
        if not items and not cut:
            for below in lines[n + 1:]:
                below = below.strip().lstrip(">").strip()
                label = LABEL_RE.match(below)
                if label and label.group(1).strip().rstrip(":").strip() in LABEL_ORDER:
                    break
                if any(r.match(below) for _, r in CARRY_LINES):
                    break
                items.extend(_carry_split(BULLET_RE.sub("", below)))
        if items:
            found = (found or []) + items
    return found


def carry_present(name, text):
    """Whether `text` holds the carry line `name`: a Recovered line with at least one item, or a
    Handoff gave label where it starts an item."""
    if name == "Recovered":
        return recovered_items(text) is not None
    return bool(dict(CARRY_LINES)[name].search(text))


def unsourced_recovered_item(block):
    """The first item of a Recovered line in `block` that names no git, page or digest source, else ''.
    An item that starts with "none" or "nothing" needs no source."""
    for item in recovered_items(block) or []:
        if not NONE_ITEM_RE.match(item) and not SOURCE_RE.search(item):
            return item[:60]
    return ""


def recovered_problem(records, text):
    """The Recovered guard's refusal when a compaction came before `text` and a carry line is missing
    since, or a Recovered item of `text` names no source while no earlier reply has met the Recovered
    demand, else ''. The newest `compact_boundary` record anywhere in `records` marks the compaction
    (its subtype alone is read). Each line is tracked alone: a main-session reply after the boundary
    that holds it, anywhere in its text, satisfies it, and that reply is not judged for sources. The
    current reply (the last reply record, when its report block equals `text`'s) counts by its
    blockquote."""
    boundary = None
    last_text = None
    for i, rec in enumerate(records):
        if rec.get("type") == "system" and rec.get("subtype") == "compact_boundary":
            boundary = i
        if _reply_text(rec) is not None:
            last_text = i
    if boundary is None:
        return ""
    block = block_text(text)
    pending = [name for name, _ in CARRY_LINES]
    for i in range(boundary + 1, len(records)):
        reply = _reply_text(records[i])
        if reply is None:
            continue
        if i == last_text:
            if block_text(reply) == block:
                continue
            reply = block_text(reply)
        pending = [name for name in pending if not carry_present(name, reply)]
    missing = [name for name in pending if not carry_present(name, block)]
    reasons = []
    if missing:
        reasons.append("a compaction came before this report and no %s line has landed since. "
                       "Under Deviations, add %s, inside the report blockquote." %
                       (" or ".join(missing), " and ".join(CARRY_FORMS[n] for n in missing)))
    bad = unsourced_recovered_item(block) if "Recovered" in pending else ""
    if bad:
        reasons.append("the Recovered item %r names no source. End each item with git, page or "
                       "digest; items split on \";\" outside parentheses." % bad)
    return "Recovered guard: " + " ".join(reasons) if reasons else ""


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


def _own_lane_read(path, own_id):
    """(is_lane, parent id): this session's own get_session record in the transcript. A lane carries the
    tag cs-build:lane or a parent_session_id. No record reads as owner-facing."""
    import own_session
    tags, _tagged_after, parent = own_session.own_session_read(path, own_id)
    return tags is not None and (LANE_TAG in tags or bool(parent)), parent


def _turn_acts(records, turn, acks):
    """(main-session tool uses, the send targets of each) in the turn. `turn` ends at the last incoming
    message; when that message is the ack of a send from a session in `acks`, the turn reaches back past it."""
    cut = len(records) - len(turn)
    if cut and peer_sender(records[cut - 1]) in acks:
        idx = last_incoming_index(records, acks)
        turn = records if idx is None else records[idx + 1:]
    uses = [u for r in turn if not r.get("isSidechain") for u in tool_uses(r)]
    return uses, [send_targets(u) for u in uses]


def question_problem(records, turn, text, hook):
    """(refusal, note) for a reply whose Input Needed item asks the owner a question (a pick or a "?"
    sentence), judged on `turn`, the records after the last incoming message (questions-reach-page). The
    ack of a send this turn made to the writer or the parent starts no turn.
    Owner-facing: a send to the page writer, or an items write to this repo's page. The question box counts
    only in a repo with no waiting page. A send to @parent reaches no one there.
    Lane: a send to the parent or the page writer; a send to @parent counts only in a lane.
    Cost: nothing past the text check when the turn has no question or sends to the writer. Else the own-record
    import and a transcript read, only in a session with a remote id. A lane reads no layout; an owner-facing
    turn with no counted send reads it once."""
    if not (offers_a_pick(text) or asks_a_question(text)):
        return "", ""
    writer = page_writer_id(records)
    acks = {writer: {writer}} if writer else {}
    uses, sends = _turn_acts(records, turn, acks)
    if writer and any(writer in t for t in sends):
        return "", ""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    from override import remote_session_id
    own_id = remote_session_id()
    lane, parent = _own_lane_read(hook.get("transcript_path"), own_id) if own_id else (False, None)
    if lane:
        if parent:
            acks[parent] = {parent} | PARENT_TARGETS
            uses, sends = _turn_acts(records, turn, acks)
        wanted = ({parent} if parent else set()) | ({writer} if writer else set()) | PARENT_TARGETS
        return ("" if any(t & wanted for t in sends) else LANE_REFUSAL), ""
    root = repo_root(hook.get("cwd"))
    page = layout.waiting_page(root) if root else "unknown"
    here = None if page == "unknown" else page.rstrip("/")
    for u in uses:
        inp = u.get("input")
        if (str(u.get("name", "")).startswith(ARTIFACT_DATA) and isinstance(inp, dict) and items_write(inp)
                and (here is None or str(inp.get("url", "")).rstrip("/") == here)):
            return "", ""
    if here is None:
        # No page: the question is asked in the reply or the box, so the box counts.
        return "", ("" if any(u.get("name") == ASK_TOOL for u in uses) else NO_PAGE_NOTE)
    route = ("send_message to the writer " + writer if writer else
             "read meta/page on " + page + " with ArtifactData get, then send_message the question to its writer")
    return OWNER_REFUSAL % route, ""


# rewrite-cite-predates-ruling: a sentence that says a decision was rewritten for a ruling. See the module docstring.
REWRITE_RE = re.compile(r"\b(?:rewrote|rewritten|rewrites|rewrite\s+of)\b", re.I)
# A negation or a modal just before the rewrite word: "not rewritten yet", "no rewrite of", "will be rewritten",
# "should be rewritten", "needs a rewrite of". No rewrite has happened.
REWRITE_UNDONE_RE = re.compile(
    r"(?:(?<![\w-])(?:not|never|no|will|would|shall|should|must|can|may|could|needs?|yet)(?![\w-])|n't\b"
    r"|\bto\s+be\b|\bgoing\s+to\b)"
    r"[\w\s'`-]{0,20}$", re.I)
# A status word anywhere in the sentence: the rewrite waits in a queue.
REWRITE_QUEUED_RE = re.compile(r"(?<![\w-])(?:pending|queued)(?![\w-])", re.I)  # a hyphen keeps an id like no-x whole
REWRITE_CAP = 5  # most distinct records one reply may make this check read
SLUG = r"`?[a-z0-9]+(?:-[a-z0-9]+)*`?"
SLUG_RE = re.compile(r"(?<![\w-])[a-z0-9]+(?:-[a-z0-9]+)*(?![\w-])")
# The ids right before a rewrite word: "decision X was rewritten", "Decisions X and Y were rewritten".
IDS_BEFORE_RE = re.compile(
    r"(?<![\w-])(%s(?:\s*,\s*(?:and\s+)?%s|\s+and\s+%s)*)\s+(?:(?:decisions?|records?|was|were|is|are|has|have|been|now|also|both)\s+)*$"
    % (SLUG, SLUG, SLUG))
# The ids right after a rewrite word: "rewrote decision X", "the rewrite of X and Y". An id after under, by,
# per, following or see is never next to the rewrite word, so it is not checked.
IDS_AFTER_RE = re.compile(
    r"^\s*(?:(?:of|the|a|an|decisions?|records?)\s+)*(%s(?:\s*,\s*(?:and\s+)?%s|\s+and\s+%s)*)(?![\w-])"
    % (SLUG, SLUG, SLUG))
STAMP_FULL_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})\s*(CST|CDT|UTC|GMT)\b")
STAMP_CLOCK_RE = re.compile(r"(?<![\d:-])(\d{1,2}:\d{2})\s*(CST|CDT|UTC|GMT)\b")
RULING_WORD_RE = re.compile(r"\brulings?\b", re.I)
STAMP_AFTER_RULING_RE = re.compile(r"^\s+(?:at|of)\s+$", re.I)  # "ruling at <stamp>", "ruling of <stamp>"
STAMP_BEFORE_RULING_RE = re.compile(r"^\s*(?:owner(?:'s)?\s+)?$", re.I)  # "the <stamp> ruling"
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


def _claims_a_rewrite(sentence):
    """True when the sentence is not queued, and a rewrite word in it has no negation or modal just before it."""
    if REWRITE_QUEUED_RE.search(sentence):
        return False
    return any(not REWRITE_UNDONE_RE.search(sentence[max(0, m.start() - 40):m.start()])
               for m in REWRITE_RE.finditer(sentence))


def _rewritten_ids(sentence):
    """The words next to each rewrite word that may name a record, in order, with no repeat."""
    found = []
    for m in REWRITE_RE.finditer(sentence):
        if REWRITE_UNDONE_RE.search(sentence[max(0, m.start() - 40):m.start()]):
            continue
        for near in (IDS_BEFORE_RE.search(sentence[max(0, m.start() - 200):m.start()]),
                     IDS_AFTER_RE.match(sentence[m.end():])):
            if near:
                found += [w for w in SLUG_RE.findall(near.group(1).replace("`", " ")) if w not in found]
    return found


def _ruling_stamp(sentence):
    """(day, clock, zone) of the stamp next to the word "ruling" in `sentence`, else None. The stamp sits right
    before the word ("the YYYY-MM-DD HH:MM CST ruling"), or follows it after "at" or "of" ("ruling of
    YYYY-MM-DD HH:MM CST"). Any other stamp, such as a merge time, is not the ruling time. `day` is None for a
    clock-only stamp."""
    stamps = [(m.start(), m.end(), m.groups()) for m in STAMP_FULL_RE.finditer(sentence)]
    for m in STAMP_CLOCK_RE.finditer(sentence):
        if not any(s <= m.start() < e for s, e, _ in stamps):
            stamps.append((m.start(), m.end(), (None,) + m.groups()))
    for word in RULING_WORD_RE.finditer(sentence):
        for start, end, groups in sorted(stamps):
            if start >= word.end() and STAMP_AFTER_RULING_RE.match(sentence[word.end():start]):
                return groups
            if end <= word.start() and STAMP_BEFORE_RULING_RE.match(sentence[end:word.start()]):
                return groups
    return None


def _stamp_time(stamp, human_ts):
    """The instant a (day, clock, zone) stamp names. A clock-only stamp takes the turn's Central date: the last
    human record's timestamp, else the hook's clock. A clock later than the turn names the day before."""
    from datetime import datetime, timedelta, timezone
    day, clock, zone = stamp
    tz = timezone(timedelta(hours=STAMP_ZONE_HOURS[zone]))
    hour, minute = (int(x) for x in clock.split(":"))
    if day is not None:
        year, month, date = (int(x) for x in day.split("-"))
        return datetime(year, month, date, hour, minute, tzinfo=tz)
    import local_time
    try:
        turn = _parse_iso(human_ts)
    except (TypeError, ValueError):
        turn = local_time.clock()
    year, month, date = (int(x) for x in _central(turn).split()[0].split("-"))
    at = datetime(year, month, date, hour, minute, tzinfo=tz)
    return at - timedelta(days=1) if at > turn else at


def rewrite_stamp_problem(text, human_ts, cwd):
    """The refusal text when a sentence says a decision was rewritten for a ruling that is later than the
    record's last commit on every local branch, every remote branch and HEAD, else ''. A cited id is a word next
    to the rewrite word that names a file in the decisions folder of the checkout. Fails open on any unknown: no
    record file, no stamp next to "ruling", a failed read. Git runs once per distinct cited id in the reply, and
    not at all for an id with no record file. A shallow clone shows a later last commit than the real one, so
    it can miss a stale rewrite and never refuses a fresh one."""
    sentences = [s for s in SENTENCE_SPLIT_RE.split(FENCE_RE.sub(" ", text))
                 if REWRITE_RE.search(s) and _claims_a_rewrite(s)]
    if not sentences:
        return ""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    from datetime import datetime, timezone
    root = repo_root(cwd)
    if not root:
        return ""
    folder = layout.path(root, "decisions")
    reasons, epochs = [], {}
    for sentence in sentences:
        ids = [d for d in _rewritten_ids(sentence)
               if os.path.isfile(os.path.join(root, *folder.split("/"), d + ".md"))]
        stamp = _ruling_stamp(sentence) if ids else None
        if stamp is None:
            continue
        ruling = _stamp_time(stamp, human_ts)
        import git_reads
        for d in ids:
            if d not in epochs:
                if len(epochs) >= REWRITE_CAP:
                    continue
                epochs[d] = git_reads.last_commit_epoch(root, "%s/%s.md" % (folder, d))
            d_epoch = epochs[d]
            if d_epoch is None or d_epoch >= ruling.timestamp():
                continue
            reason = (
                "Rewrite-stamp guard: decision `%s` was last committed %s, on every branch and HEAD, before the "
                "ruling %s that it is said to be rewritten for. Rewrite the record, fetch the branch that holds "
                "the rewrite, or say it is not rewritten yet."
                % (d, _central(datetime.fromtimestamp(d_epoch, timezone.utc)),
                   ruling.strftime("%Y-%m-%d %H:%M ") + stamp[2]))
            if reason not in reasons:
                reasons.append(reason)
    return " ".join(reasons)


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
        "and a line in the repo's debt notes file (notes.md) that names it "
        "(decision refusals-reach-the-owner)." % names)


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
        answered = answered_problem(text)
        if answered:
            reasons.append(answered)
        recovered = recovered_problem(records, text) if report_shape_ok(text) else ""
        if recovered:
            reasons.append(recovered)
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
        pending_refusals(hook, last_reply(hook))  # clears what the rewrite names; never blocks on a refusal
        reasons = rewrite_problems(hook)
        reasons += rewrite_relay(hook)
        if reasons:
            print(json.dumps({"decision": "block", "reason": " ".join(reasons) + " (rule reports-order-of-labels)" + CORRECTION_TAIL}))
        return
    # A marker left by a rewrite that never ran must not reach a later turn: only the Stop
    # straight after a missing-report block may consume one.
    try:
        os.remove(_marker_path(hook))
    except Exception:
        pass

    # Every Stop, landed or not, settles the refusals file; the reason joins whichever block follows.
    pending = pending_refusals(hook, last_reply(hook))
    refusal = refusal_reason(pending)

    def stop_for_refusal():
        if refusal:
            print(json.dumps({"decision": "block", "reason": refusal_reason(pending)}))

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
    relay = []
    if last_human_idx is not None:  # a transcript with no human message never ran the relay and answered checks
        relay = relay_reasons(after, text, hook.get("cwd"))
        try:
            relay.append(answered_problem(text))  # one block per turn, joined with any other reason, landed or not
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
        pick += relay
        try:
            if report_shape_ok(text):
                pick.append(recovered_problem(records, text))
        except Exception:
            pass
        try:
            pick.append(refusal)
            pick = [r for r in pick if r]
            if pick:
                reason = " ".join(pick) + " (rule reports-order-of-labels)" + (CORRECTION_TAIL if report_shape_ok(text) else "")
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
    reasons += [r for r in relay if r]
    try:
        rewrite = rewrite_stamp_problem(text, records[last_human_idx].get("timestamp"), hook.get("cwd"))
        if rewrite:
            reasons.append(rewrite)
    except Exception:
        pass
    try:
        recovered = recovered_problem(records, text) if shape_ok else ""
        if recovered:
            reasons.append(recovered)
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
        reason = " ".join(reasons) + " (rule reports-order-of-labels)" + (CORRECTION_TAIL if shape_ok else "")
        if not shape_ok:
            write_marker(hook, last_human_idx)
        print(json.dumps({"decision": "block", "reason": reason}))
    elif note:
        print(json.dumps({"systemMessage": note}))


if __name__ == "__main__":
    main()
