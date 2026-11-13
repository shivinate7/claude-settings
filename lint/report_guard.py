#!/usr/bin/env python3
"""At Stop, after a turn that landed (git commit, push, merge, revert or cherry-pick, gh pr merge or create, or a GitHub MCP write tool), blocks once unless the reply ends with the report: the bold labels Done, Deviations, Input Needed, Next, in order. Fails open on any error.

Reads the hook JSON on stdin. Always exits 0. Fails open on bad input, a missing
transcript, or a parse error.

Stop: when this turn ran `git commit`, `git push`, `git merge`, `git revert` or `git cherry-pick`
(not with --abort, --quit, -n, --no-commit, -h or --help; --skip and --continue commit), `gh pr merge`,
`gh pr create` or `gh pr update-branch` (not with --help or -h, nor `--disable-auto` on merge or `--web` on create),
or a landing GitHub MCP tool (LANDING_TOOLS, which includes delete_file, update_pull_request_branch
and enable_pr_auto_merge) after the last human message, block once unless the reply ends with one blockquote holding
the bold labels Done, Deviations, Input Needed, Next, in that order (CLAUDE.md, "Reports, in
order"; the blockquote and no-fence rule lives in the `shiv-stylisms` output style). Prose may sit above the report on any turn. Nothing may follow the report.
When stop_hook_active is set, the reply is already a rewrite, so the guard stays quiet, with one
exception: a block that asked for the missing report leaves a marker file (local_time.report_marker_path,
holding the index of the turn's human record). The next stop_hook_active Stop consumes it and checks
the rewrite once for model names and the `Unstarted:` line only. A failure blocks with a correction.
Cost: one small file per missing-report block, written at that block, deleted at the next Stop with
stop_hook_active; no process, timer or log. A correction block leaves no marker, so no loop follows.

On landed turns whose report has the right shape, it also blocks a Deviations item that admits a mistake
the writer made ("I broke ...", a first-person clause with a fault word and no negator before it) and names no
guard: `step:<slug>`, the word debt, or a guard, check or hook word with a PR or commit ref
(`building-mistake-names-its-guard`). Quoted text, fences and URLs never count as an admission.

Every refusal reaches the owner in chat (decision `guard-remedy-not-to-owner`). So each opens with one
owner line from owner_line(): the check, what is wrong, and a cite of that decision. The steps to fix it live in
that record, never in the reason.

On the same landed turns it also blocks (one block, all reasons joined) when a Done item lacks
BUILT, RECORDED, or OTHER or a PR or commit ref (`reports-done-format`), or when the reply holds
a record id with no short gloss (`speak-cite-id-plus-gloss`), or when a builder, reviewer,
test-author or record-writer spawned since the last human message goes unnamed in Done, or a
named "role model" pair matches no spawn of that role (`reports-done-names-models`), or when
a turn that spawned a builder reports with no `Unstarted:` line (`reports-name-unstarted-items`).
When the report is there, no refusal holds correction text; the step lives in decision guard-remedy-not-to-owner.

On any turn whose reply holds an Input Needed item that asks the owner a question (a pick with
options, or a sentence ending in "?" outside quotes and backticks), it also blocks unless the turn
holds a qualifying act (`questions-reach-page`: every question goes to the page writer in the same
turn it is asked, no clock). The turn is every record after the last
incoming message, a peer's included; the ack of a send this turn made to the writer or the parent
starts no turn. Owner-facing session: a send to
the page writer (the `writer` in the newest meta/page read, else the one session tagged cs-build:triage and cs-repo:<repo> in the transcript's get_session or list_sessions records), or an ArtifactData set, update or batch under
collection items to this repo's page; the question box (main session) counts only in a repo with no page. Lane (own get_session record tagged cs-build:lane, or with a
parent, and not tagged cs-build:triage, the page writer): a send to @parent, the parent id or the writer; @parent counts only in a lane. A promise or a page link passes nothing. A
repo with no waiting page gets a systemMessage and no block, unless the session is a lane. This check
does not wait for a git write: the reply's labels are what it reads. Cost: no file written. Reads: the
transcript this hook already holds. Only on a turn that asks with no send to the writer: the
own-record import (hooks/own_session.py) and one more transcript read, in a session with a remote id. A lane
reads no layout; an owner-facing turn with no counted send reads the extras file for the writer key first, when the transcript has no meta/page read, then for the page; a send to the key writer returns after the first read (`decisions-reach-a-clickable-pick`).
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

The triage hold (a roadmap build's `stalled step:` lines): a session whose own newest get_session record carries
cs-build:triage (hooks/guard_merge.py _own_tier_proved) cannot end a turn while the newest roadmap build output in its
transcript (the result of a Bash run of build.py) has an entry line, `stalled step: <id> (...)` or
`stalled step: item <n> (...)`. An unknown line is no entry. The hold also covers a Stop after a refusal
(stop_hook_active), which it releases only when the report's Input Needed section names every entry's id and item
number. An owner `override` typed for the session lifts it, taken as guard_core's refuse() takes it, and the Stop
it lifts spends a one-act override. A build run through
verdict is read from the log file verdict printed (a missing log reads as no entries for that run). Cost: no
transcript read of its own on a plain Stop (it shares main's read). Only when a Bash run of build.py is in it: the
build module's import, and one log read for a verdict run. Only when an entry prints: the own-record read and one
override read.

Route-row flags (hooks/route_match.py holds the rows, the surface and the match): a refused call that a "works" row
matches gets a `route_flag` in its refusals row (hooks/refusal_note.py), and a successful call of the turn that a
"refused" row matches gets one here. Each flag rides in the systemMessage of the line this Stop prints and never
changes its decision. The dedupe file <config dir>/state/route-flags/<session_id>.json holds the keys already
shown. Cost: one small file per session, written only when a flag shows, read at Stop; its one reader and writer is
_shown_flags, and a turn with no flag and no successful call reads no rows file. Cleanup: none. Nothing prunes
state/ per session (janitor/session_end_sweep.py runs the branch and worktree sweep only), and a file holds a few
short keys, so it stays as the refusals and reply-judge counter files do.

Hand-off cite (rule output-never-hand-off-doable-step): a "Why yours:" line, in prose above the report or in the Input
Needed or Next item (plain, behind a list marker, or in bold), that gives a capability reason (can't, cannot, refuse,
refused, unable to, denied, forbidden, no access, not allowed, not permitted, unavailable, 403, blocked, not available)
must cite `(route <id>)` for a route row whose outcome on this surface is refused or asks, a
tool in backticks that hooks/refusal_note.py recorded for this session, or `(measured <date>, <check and result>)`. A
line with a choice, login or safety-kept phrase needs no cite, and "blocked until" or "not available until" is a
dependency, not a capability. A "works" row, a dead id, an undated measurement and no cite block,
with an owner line that names no act. A rows file, a refusals file or an outcome that did not read is a systemMessage with
the word UNKNOWN, never a block, and never clears a "works" row or a dead id. Cost: a reply with no such line opens nothing new and imports nothing; one with it reads
the session's refusals file, and the rows file (hooks/route_match.py read_rows) when a line carries a route cite. It
runs on landed and unlanded turns and not on a stop_hook_active rewrite.

Cannot-claim check (rule output-never-hand-off-doable-step): a prose sentence of the reply that says this session cannot do a
table act (pr-open, pr-merge, push, pr-edit, github-reach), named by the verb the phrase governs, passes only when the
turn after the last human message holds a failed try of that act, or the sentence carries a hand-off cite (a route row
that says refused or asks, a dated `(measured ...)`, or a tool the classifier refused), and the sentence names its check
(a backtick span, an MCP tool name, a word such as returned or refused, an HTTP 4xx, a non-zero exit). A try is a call
whose result has an error flag or an exit code above zero (an HTTP 4xx or 5xx counts only in an error result, or in an
agent's relayed text); a later success of the same act, program, verb and target cancels it, and a --dry-run call is no
try. A local merge is no try of pr-merge. A notice is no try. Not read: an act outside the table, a
subject that is not the writer's own, a question, a Why yours line (the hand-off guard's), a line or sentence that starts
with Unvetted:, quoted or coded text, a conditional, a dependency (until, before) and a sentence that names a rule. One
block, then the rewrite runs unchecked. A check that cannot run prints an UNKNOWN note to stderr and allows.
Cost: a regex over the reply; on a claim, one pass over the transcript this hook already holds and one refusals file read;
on a claim with a slug in parentheses, one read of the rule files per run; no file written, no timer, no log.

Review-record check (incident: on Nov 7, 3 of 67 open PRs had a review record): in a lane (own get_session record tagged cs-build:lane, or with a parent), a reply line outside fences
that holds `round <N>` or `reviewer` and a capital PASS or PASSED claims a PASS, in either order; an inline code span counts. A PASS a negation governs ("not PASS",
"did not PASS") claims nothing, nor does a PASS whose clause places it in the past ("was before the fix", "went stale"). Clauses split on `,`, `;` and `--`; a
history word in another clause hides no claim. The line claims it for each PR it names, as
`#<N>`, `PR <N>` or a github pull URL. The Stop is refused unless each such PR has a review record comment for its live head: the newest comment whose first line is
the review marker, read by merge/merge.py parse_review (never retyped here), naming the PR, and that merge/merge.py live_review_state calls done for the live head,
the one read `merge --reviewed` makes: a record survives clean merges of main, and a clean-merge read that cannot run keeps it stale, so it still blocks. A claim with no
PR on its line is refused and asks for the PR. With no record for the live head, the remedy names the act (`merge <pr> --review-record ...`, then post the
record) and never the live head; a record live_review_state reads open or held is refused with that state and its why, and no post act. A newest record that exists but does not parse is refused in its own words (PR named, "does not parse", the same
remedy as a missing record, with the post as a new comment), not as a missing record; it names the CI line as the cause only when text follows that line before the first `---` line. merge/merge.py is loaded by hooks/guard_merge.py merge_module: beside the hooks' real path (the installed symlink), then in the
checkout the global rules file names (the copied cloud layout); a tool it cannot load is UNKNOWN. Reads: `gh api` REST only, two per claimed PR
(the PR, then its issue comments, every page); a Stop with no claim, or in an owner-facing session, reads nothing. A failed read, or an error in the check, never
blocks: it adds a systemMessage that says UNKNOWN. Cost: 2 gh reads per claimed PR in a lane Stop, plus the guard_merge and merge module imports; no file,
process kept or timer. A stale record adds the clean-merge read (merge/merge.py clean_merges_after): one commit read and one compare per merge
commit, local git starts, and at most one `git fetch origin`, all inside the review check's REVIEW_CHECK_BUDGET. A stop_hook_active rewrite is not checked.
"""
import bisect
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _transcript import (  # noqa: E402
    ARTIFACT_DATA, SEND_TOOLS, delivered_tool_use_ids, is_last_human, items_write, last_incoming_index, last_reply, page_writer, page_writer_id, peer_sender,
    read_transcript, records_after_last_human, send_targets, tool_results, tool_uses)
import layout  # noqa: E402
import _clause  # noqa: E402

HOOKS_DIR = os.path.join(HERE, "..", "hooks")
_STAMP = re.compile(rb'^INSTALL_ID = "([^"]+)"', re.MULTILINE)
# The stamp sits near byte 30000 of the 320 KB hooks/guard.py; the cap leaves room for the file to grow.
_STAMP_HEAD_BYTES = 64 * 1024
_hooks_dirs_answer = None  # hooks_dirs() sets it on its first call


def hooks_dirs():
    """The hooks folders to import helpers from, first to last. The installer stamps hooks/guard.py with
    `INSTALL_ID = "<id>"` and lands guard.py, the guard_*.py files, shared_names, git_reads, question_form, own_session
    and precompact_handoff in hooks/guard.d/<id>/ (install.sh land_guard_set). A stamp with that folder present puts it
    before the flat one. A module the folder lacks falls through to the flat one. No stamp (the repo copy), an
    unreadable file or no folder gives the flat folder alone.

    The stamp is matched in the first 64 KB of bytes, never an import and never a strict decode, so a stray non-UTF-8
    byte in guard.py cannot stop this module importing. The answer is kept in a module global, so a run reads guard.py
    once however many lazy helper imports ask. A run as the script starts from a fresh module, so each hook run reads
    it once. question_form imports this module a second time, as a fresh module whose global starts empty; an install
    lands between processes, not inside one. So an import (not a run as the script) that finds shared_names already
    loaded from the flat folder or a guard.d folder takes that folder as the answer and skips the read."""
    global _hooks_dirs_answer
    if _hooks_dirs_answer is None:
        loaded = _loaded_hooks_dir() if __name__ != "__main__" else None
        _hooks_dirs_answer = loaded if loaded is not None else _find_hooks_dirs()
    return list(_hooks_dirs_answer)


def _loaded_hooks_dir():
    """The answer a shared_names already in sys.modules gives: its own folder, or None when it came from elsewhere."""
    origin = getattr(sys.modules.get("shared_names"), "__file__", None)
    if not origin:
        return None
    folder = os.path.dirname(os.path.realpath(origin))
    flat = os.path.realpath(HOOKS_DIR)
    if folder == flat:
        return [flat]
    if os.path.dirname(os.path.dirname(folder)) == flat and os.path.basename(os.path.dirname(folder)) == "guard.d":
        return [folder, flat]
    return None


def _find_hooks_dirs():
    try:
        with open(os.path.join(HOOKS_DIR, "guard.py"), "rb") as handle:
            stamp = _STAMP.search(handle.read(_STAMP_HEAD_BYTES))
    except OSError:
        stamp = None
    if stamp:
        folder = os.path.join(HOOKS_DIR, "guard.d", stamp.group(1).decode("ascii", "replace"))
        if os.path.isdir(folder):
            return [folder, HOOKS_DIR]
    return [HOOKS_DIR]


def _hooks_on_path():
    """Put hooks_dirs() at the front of sys.path, in order: the one call every lazy helper import makes."""
    for folder in reversed(hooks_dirs()):
        sys.path.insert(0, folder)


_hooks_on_path()
from shared_names import LANE_TAG  # noqa: E402  the one home of the lane tag, shared with hooks/guard.py

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
    _hooks_on_path()
    try:
        import guard as loaded
    except ImportError:
        # A guard that cannot read cannot accuse. Fail open, the same posture every other guard
        # here takes on a missing or unreadable input: turn_landed() below reports no landing at
        # all when guard did not load, so this Stop hook never demands a report it cannot judge.
        return
    guard = loaded

GIT_LANDING_SUBCOMMANDS = {"commit", "push", "merge"}
# These two make a commit unless the call carries a flag from the two tables below, which
# `_stops_before_a_commit` reads.
GIT_PICK_SUBCOMMANDS = {"revert", "cherry-pick"}
# (full flag, shortest prefix git's parse-options accepts for it: no other option of revert or
# cherry-pick shares it). `--skip` and `--continue` are absent on purpose: both commit.
# `--help` prints and stops, as `-h` does (the short-letter read below).
PICK_NO_COMMIT_FLAGS = (("--abort", "--ab"), ("--quit", "--q"), ("--no-commit", "--no-c"),
                        ("--help", "--help"))
# Short options of revert and cherry-pick that take a value, glued or as the next word: the rest of
# a cluster after one of them is its value, never more flags (`-Xignore-space-change` holds an n).
PICK_SHORT_VALUE_FLAGS = "mXS"
# `update-branch` merges the base into the PR branch: a commit on the remote.
GH_LANDING_PR_VERBS = {"merge", "create", "update-branch"}
# Per verb, the flags that make the call write nothing. `gh pr create --dry-run` is absent on
# purpose: it may still push the branch.
GH_NO_WRITE_FLAGS = {
    "merge": {"--disable-auto"},
    "create": {"--web", "-w"},
}
LANDING_TOOLS = {
    "mcp__github__merge_pull_request",
    "mcp__github__create_pull_request",
    "mcp__github__push_files",
    "mcp__github__create_or_update_file",
    "mcp__github__delete_file",
    "mcp__github__update_pull_request_branch",
    "mcp__github__enable_pr_auto_merge",
}
LABEL_ORDER = ["Done", "Deviations", "Input Needed", "Next"]
# A bold "**Departs from:**" starts a line of the item (rule `question-departs`), and a bold
# "**Recovered:**" or "**Handoff gave:**" is a compaction-carry line below; none is a report label.
LABEL_RE = re.compile(r"^\*\*(?!(?i:Departs from|Recovered|Handoff gave))(.+?)\*\*")
# A label may carry its colon inside the bold, as in "**Done:**". Both forms read the same,
# so the colon is stripped before the label is matched against LABEL_ORDER.

REMEDY_CITE = "decision guard-remedy-not-to-owner"


def owner_line(check, wrong):
    """The one owner line that opens every refusal: the check's name, what is wrong, and the record that
    holds the steps (the one home; no site writes its own). The owner reads each refusal in chat, so a refusal holds
    facts only, never an instruction to the session. `wrong` may hold a %s slot for the caller to fill."""
    return check + ": " + wrong + " (" + REMEDY_CITE + ")."


# Wording that tells the session what to do. A refusal reaches the owner in chat, so it holds facts only.
# `session_wording` is the one detector; the remedy suite imports it. A phrase here is matched case-insensitively.
SESSION_PHRASES = (
    "send it again", "send the report", "post only", "never send", "add the line", "remedy:",
    "do not write it again", "keep the reply", "would reach the owner", "as the next thing you write",
    "send it now", "send the questions again",
)
# A unit that opens with one of these words (after a connector such as "so") is an order to the session. "Pick" is
# left out on purpose: "Pick guard" is the check name of an owner line.
SESSION_IMPERATIVES = frozenset((
    "add", "send", "post", "keep", "write", "drop", "give", "name", "move", "run", "never", "do", "don't", "resend",
    "rewrite", "mark", "resume", "pause", "fix", "ship", "wait", "reply", "put", "cite", "check", "answer", "close",
    "open", "update", "remove", "include", "set", "make", "stop", "let", "tell", "ask", "see", "read", "dispose",
))
# A unit ends at a sentence mark, a clause mark (; : ,) or a line break, so an order after a clause is seen too.
_UNIT_END = re.compile(r"(?<=[.!?;:,])\s+|\n+")
_CONNECTORS = frozenset(("so", "then", "and", "but", "now", "first", "next", "also", "please"))
_WORD = re.compile(r"[a-z][a-z'-]*")
# A list of backtick spans ("refused `Agent`, `Write` this session") ends each unit but the last in span + comma. The
# unit after it that opens directly with a span names the next item and holds no order. A connector before the span
# ("`Next`, so `add` it") makes it an order, so the unit must open with the backtick itself. A span never crosses a
# comma, a sentence mark or a line, so a lone backtick cannot pair with a later one and hide an order.
_SPAN_COMMA_END = re.compile(r"`[^`\n.!?;:,]+`,$")
# A modal that binds the reader: "you should send it", "the reply must end with the report".
_MODAL = re.compile(r"\b(?:must|should|need to|needs to|have to|has to|ought to)\b", re.IGNORECASE)


def session_wording(text):
    """The phrase in `text` that tells the session what to do, or '' when `text` holds facts only: a listed phrase,
    a clause that opens with an order word, or a modal ("must", "should")."""
    low = text.lower()
    for phrase in SESSION_PHRASES:
        if phrase in low:
            return phrase
    previous = ""
    for unit in _UNIT_END.split(text):
        is_list_item = unit.lstrip().startswith("`") and bool(_SPAN_COMMA_END.search(previous))
        previous = unit.strip()
        if is_list_item:
            continue
        words = _WORD.findall(unit.lower())
        while words and words[0] in _CONNECTORS:
            words.pop(0)
        if words and words[0] in SESSION_IMPERATIVES:
            return unit.strip()
    found = _MODAL.search(text)
    return found.group(0) if found else ""


BLOCK_REASON = owner_line(
    "Report-shape guard",
    "this turn landed a commit, push, or merge, and the reply does not end with the report in one blockquote "
    "with the bold labels Done, Deviations, Input Needed, Next")
# The owner has read the report before a refusal lands, so a resent report doubles it. The missing-report refusal
# asks for the report itself; every other refusal asks for a short correction. Both asks live in the record.
# A Stop hook cannot read a reply before it is shown. The correction runs with stop_hook_active
# set, so this guard stays quiet on it. The rewrite after a missing-report refusal is the one
# exception: rewrite_problems() checks it once, and its own refusal leaves no marker.

MODELS_REASON = owner_line(
    "Model-name guard",
    "a Done item that agents built or reviewed does not name each one's role and model (%s)")
UNSTARTED_REASON = owner_line(
    "Unstarted guard", "this turn ran a builder, and Next holds no \"Unstarted:\" line")


# is_last_human and tool_uses live in lint/_transcript.py, imported above.


def _stops_before_a_commit(args):
    """True when a `git revert` or `git cherry-pick` call carries a flag that makes no commit:
    `--abort` and `--quit` clear the sequence, `-n` and `--no-commit` stage the change only.
    Words after `--` are paths. Short options read letter by letter, so `-nx` counts and
    `-m 1` does not read its value as flags."""
    for arg in args:
        if arg == "--":
            return False
        if arg.startswith("--"):
            if any(guard.guard_core.long_flag_abbrev(arg, full, shortest)
                   for full, shortest in PICK_NO_COMMIT_FLAGS):
                return True
        elif arg.startswith("-"):
            for letter in arg[1:]:
                if letter in "nh":
                    return True
                if letter in PICK_SHORT_VALUE_FLAGS:
                    break
    return False


GH_API_VALUE_FLAGS = {"-X", "--method", "-f", "-F", "--field", "--raw-field", "-H", "--header",
                      "--input", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p",
                      "--preview", "-R", "--repo"}
GH_API_FIELD_FLAGS = {"-f", "-F", "--field", "--raw-field", "--input"}
# A pull's merge route, and the repo's merges route (a merge commit on a branch).
GH_API_MERGE_ROUTE_RE = re.compile(r"(^|/)pulls/[^/]+/merge/?$")
GH_API_MERGES_ROUTE_RE = re.compile(r"(^|/)repos/[^/]+/[^/]+/merges/?$")


def _gh_api_lands(args):
    """True when a `gh api` call (the tokens after `api`) merges. The route is the first word that
    is no flag and no flag's value. The method is `-X`/`--method` when given, else POST once any
    field or `--input` is given (gh's own default), else GET. A PUT to a pull's merge route and a POST
    to the repo's merges route land; GET, a POST to a pull's merge route, `--help` and every other
    route do not."""
    method, has_fields, route, i = None, False, None, 0
    while i < len(args):
        arg = args[i]
        i += 1
        if arg in ("-X", "--method"):
            method = args[i].upper() if i < len(args) else method
            i += 1
        elif arg.startswith("--method=") or arg.startswith("-X"):
            method = arg.split("=", 1)[1].upper() if "=" in arg else arg[2:].upper()
        elif arg in ("--help", "-h"):
            return False   # prints help and makes no request
        elif arg in GH_API_FIELD_FLAGS:
            has_fields = True
            i += 1
        elif arg in GH_API_VALUE_FLAGS:
            i += 1
        elif arg.startswith("--"):
            has_fields = has_fields or arg.split("=", 1)[0] in GH_API_FIELD_FLAGS
        elif arg.startswith("-") and len(arg) > 1:
            has_fields = has_fields or arg[:2] in ("-f", "-F")
        elif route is None:
            route = arg.split("?", 1)[0]
    if route is None:
        return False
    method = method or ("POST" if has_fields else "GET")
    if GH_API_MERGE_ROUTE_RE.search(route):
        return method == "PUT"
    return method == "POST" and bool(GH_API_MERGES_ROUTE_RE.search(route))


def _segment_lands_a_gh_write(segment):
    """True when the segment's command word is `gh` and the call is `pr merge`, `pr create` or
    `pr update-branch` without a flag that writes nothing (GH_NO_WRITE_FLAGS, `--help`, `-h`), or
    a `gh api` merge call (`_gh_api_lands`). `guard.gh_call_of` reads the
    command word past wrappers and a subshell, the same read the merge guard takes."""
    rest = guard.gh_call_of(segment)
    if rest is not None and rest[:1] == ["api"]:
        return _gh_api_lands(rest[1:])
    if rest is None or rest[:1] != ["pr"] or rest[1:2] == [] or rest[1] not in GH_LANDING_PR_VERBS:
        return False
    no_write = GH_NO_WRITE_FLAGS.get(rest[1], set()) | {"--help", "-h"}
    return not any(arg in no_write for arg in rest[2:])


def _segment_lands_a_git_write(segment):
    """True when one of the segment's own `git` calls resolves to `commit`, `push`, or `merge`,
    or to a `revert` or `cherry-pick` that makes its commit (`_stops_before_a_commit`).

    `guard.git_calls` is the parser every git rule in guard.py already trusts: it walks past
    `sudo`, and past the pre-subcommand options that take a value (`-C <dir>`,
    `--git-dir=<path>`, and the rest of `GIT_OPT_WITH_VALUE`), to the subcommand a call would
    actually run. Reusing it, rather than a second hand-rolled skip, is what keeps
    `git -C /path commit` counted as a landing. `git merge-base` resolves to the subcommand
    `merge-base`, a different word than `merge`, and never matches.
    """
    for subcommand, args in guard.git_calls(segment):
        if subcommand in GIT_LANDING_SUBCOMMANDS:
            return True
        if subcommand in GIT_PICK_SUBCOMMANDS and not _stops_before_a_commit(args):
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
                    if _segment_lands_a_git_write(segment) or _segment_lands_a_gh_write(segment):
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
ANSWERED_REASON = owner_line(
    "Answered guard (rule answered-needs-source)",
    "each line below says \"answered\" and cites no source; a mention of the word in an inline code span is no claim") + " Lines: "


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


def _prose_lines(text, questions=False):
    """Each line of `text` that is the reply's own prose, as its body: no blockquote marker, outside fenced code, and not
    a line that ends in `?` (a question claims nothing), unless `questions` keeps those for a reader that judges a
    sentence at a time. The one line reader of the answered and cannot-claim checks."""
    fence = ""
    for line in text.splitlines():
        body = QUOTE_PREFIX.sub("", line, count=1).strip()
        marker = body[:3] if body[:3] in ("```", "~~~") else ""
        if marker and (not fence or marker == fence):
            fence = "" if fence else marker
            continue
        if fence or (not questions and body.rstrip("*_)\"' ").endswith("?")):
            continue
        yield body


def answered_problem(text):
    """The refusal for reply lines that say "answered" with no source on the line, else ''."""
    if not ANSWERED_RE.search(text):
        return ""
    bad = []
    for body in _prose_lines(text):
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


def _closed_by_notice(text):
    """The agent ids a completion notice in `text` closes: stall_watch's parser, the one home.
    It loads on first use, and a missing module closes nothing, so a spawn stays running."""
    sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
    try:
        from stall_watch import closed_by_notice
    except ImportError:
        return []
    return closed_by_notice(text)


class Spawned(dict):
    """spawn_models' map of role to model families, with `finished`: the roles that have a finished spawn."""
    finished = frozenset()


def spawn_models(records):
    """Map each named role spawned in `records` to the set of model families it ran on.

    A spawn's model is its call's `model` field, else its agent file's pin, else
    CLAUDE_CODE_SUBAGENT_MODEL; Claude Code reads them in that order. A spawn none of them
    resolve adds '' (unknown), which never counts as a mismatch.

    A running spawn has no result yet, or only a background-launch result. It joins the map
    but not `finished`.
    """
    failed, answered, agent_of, closed = set(), set(), {}, set()  # a denied or errored spawn counts for nothing
    for rec in records:
        launch = rec.get("toolUseResult")
        launched = isinstance(launch, dict) and launch.get("isAsync") is True and launch.get("status") == "async_launched"
        for b in tool_results(rec):
            if b.get("is_error"):
                failed.add(b.get("tool_use_id"))
            elif launched:
                agent_of[b.get("tool_use_id")] = launch.get("agentId")
            else:
                answered.add(b.get("tool_use_id"))
        att = rec.get("attachment")  # a completion notice that arrives as a queued command
        notice = att.get("prompt") if rec.get("type") == "attachment" and isinstance(att, dict) else None
        if isinstance(notice, str):
            closed.update(_closed_by_notice(notice))
    answered.update(t for t, agent in agent_of.items() if agent in closed)
    found, finished = Spawned(), set()
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
            if not b.get("id") or b.get("id") in answered:  # no id: no result to wait for
                finished.add(role)
    found.finished = frozenset(finished)
    return found


def done_models_problem(text, spawned, every=None):
    """Name what Done gets wrong about the spawned roles' models, else ''.

    `spawned` is the turn's spawns and sets which roles Done must name. `every` is the whole
    transcript's spawns: Done also reports a spawn that ran before the turn's window.
    Only the models an earlier spawn resolved count; its unknown '' must not hide a window mismatch.
    """
    if not spawned:
        return ""
    done = " ".join(done_items(block_text(text, keep_indent=True)))
    named = {(r.lower(), m.lower()) for roles, m in ROLE_MODEL_RE.findall(done)
             for r in ROLE_RE.findall(roles)}
    # A running role Done leaves out is not yet claimed; one Done names must carry a model.
    required = spawned.finished | {r for r in spawned if re.search(r"\b" + r + r"\b", done, re.I)}
    missing = sorted(r for r in required if not any(nr == r for nr, _ in named))
    if missing:
        return "no model named for " + ", ".join(missing)
    for role, model in sorted(named):
        ran = set(spawned.get(role, ())) | {m for m in (every or {}).get(role, ()) if m}
        if ran and "" not in ran and model not in ran:
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

OWNER_REFUSAL = owner_line(
    "Pick guard",
    "a question to the owner was not sent to the page writer in the same turn it was asked (owner ruling, "
    "2026-11-01 23:31 CST); %s")
LANE_REFUSAL = owner_line(
    "Lane pick guard",
    "a question was asked in a lane session, whose own chat does not reach the owner, and it was not sent to "
    "its parent")
NO_PAGE_NOTE = "pick not sent: this repo has no waiting page"
PARENT_TARGETS = set(layout.PARENT_TARGETS)
# A "?" ends a question unless a word character follows it, so a URL query (a?b=1) never counts. Quoted
# text, backticked text and a blockquoted line are past words, never a question asked now. A straight
# quote, double or single, opens and closes only at a non-word edge, so a lone quote or an apostrophe
# (Don't) cannot span to the next quote. A word that opens with an elided apostrophe ('til, 'Cause, '25,
# '90s) is no opening quote either: the space before it looks like one, but the apostrophe stands for dropped
# letters or digits. Text alone cannot tell a lone opener from a real one, so the elisions are named.
QUOTED_RE = re.compile(r'(?<!\w)"[^"\n]*"(?!\w)|(?<!\w)\'(?!(?i:til|till|cause|cos|bout|em|round|tis|twas|kay|nuff)\b|\d\d(?:s)?\b)[^\'\n]*\'(?!\w)|\u201c[^\u201d\n]*\u201d|`[^`\n]*`')
QUESTION_MARK_RE = re.compile(r"\?(?!\w)")


def report_section(text, label):
    """The text of the report item `label` (Done, Deviations, Input Needed or Next) from the report block, else ''.
    Only a LABEL_ORDER label ends an item, so a bold phrase at a line start inside it does not."""
    body = []
    inside = False
    for line in block_text(text, keep_indent=True).splitlines():
        m = LABEL_RE.match(line)
        name = m.group(1).strip().rstrip(":").strip() if m else None
        if name in LABEL_ORDER:
            if inside:
                break
            inside = name == label
            if inside:
                body.append(line[m.end():].lstrip(": "))
            continue
        if inside:
            body.append(line)
    return "\n".join(body)


def input_needed_section(text):
    """The Input Needed item's text from the report block, else ''."""
    return report_section(text, "Input Needed")


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
        reasons.append("a compaction came before this report and no %s line has landed since" %
                       " or ".join(missing))
    bad = unsourced_recovered_item(block) if "Recovered" in pending else ""
    if bad:
        reasons.append("the Recovered item %r names no source (git, page or digest)" % bad)
    return owner_line("Recovered guard", "; ".join(reasons)) if reasons else ""


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
    _hooks_on_path()
    import question_form
    miss = question_form.departs_hit(input_needed_section(text))
    if not miss:
        return ""
    # DEPARTS_REASON (the steps) stays for the waiting page and the question box; a Stop refusal shows the miss.
    miss = miss.removesuffix(question_form.PLACEHOLDER_HINT)
    return owner_line("Departs-from guard (rule question-departs)", "the Input Needed pick has a problem (%s)" % miss)


# building-mistake-names-its-guard: a Deviations admission ("I broke ...") must name the guard that would
# have stopped it. Quoted text, fences and URLs are blanked first so a report can quote the owner. A clause
# admits only when a first-person word comes before its fault word, so "The test was wrong so I re-pointed it"
# passes. A negator clears it only when at most MISTAKE_NEGATOR_GAP words sit between it and the fault word,
# so a negator that governs an earlier verb ("I did not run the check and broke it") does not.
# `step:<slug>` is checked for form only.
MISTAKE_FIRST_PERSON_RE = re.compile(r"\bI\b|\b[Mm]y\b")
# "broke the batch into three lanes" splits a thing and admits nothing: "into" is followed by a count or a
# parts noun. "broke the build into a red state" still admits. The words between may hold no "by", "when"
# or the like, so "broke main by merging into it" still admits.
_BROKE_INTO = (r"(?!\s+(?:(?!by\b|when\b|after\b|and\b|then\b|before\b|if\b|so\b)\w+\s+){0,3}into\s+"
               r"(?:\d+|two|three|four|five|six|seven|eight|nine|ten|several|multiple|smaller|separate|parts?"
               r"|chunks?|lanes?|steps?|stages?|phases?|tasks?|commits?|batch(?:es)?|prs?)\b)")
MISTAKE_FAULT_RE = re.compile(
    r"\b(?:wrong(?:ly)?|mistaken(?:ly)?|mistakes?|by accident|accidental(?:ly)?|broke" + _BROKE_INTO + r"|clobbered|overwrote|"
    r"misread|forgot|trusted (?:a stale|an old|an outdated)|"
    r"instead of checking)\b", re.I)
MISTAKE_NEGATOR_RE = re.compile(r"\bnot\b|n't\b|\bnever\b|\bno\b|\bnothing\b", re.I)
MISTAKE_NEGATOR_GAP = 3
MISTAKE_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n")
MISTAKE_CLAUSE_SPLIT_RE = re.compile(
    r"[,:;\u2014\u2013]|\s-{1,2}\s|\b(?:because|since|but|while|although)\b", re.I)
MISTAKE_URL_RE = re.compile(r"https?://\S+")
MISTAKE_STEP_RE = re.compile(r"\bstep:[a-z0-9][a-z0-9-]*")
MISTAKE_DEBT_RE = re.compile(r"\bdebts?\b", re.I)
MISTAKE_GUARD_WORD_RE = re.compile(r"\b(?:guard|check|hook)s?\b", re.I)
MISTAKE_REASON = owner_line(
    "Mistake guard (rule building-mistake-names-its-guard)",
    "Deviations admits a mistake, %s, and names no guard or check that would have stopped it")


def _admitted_clause(deviations):
    """The first clause of the Deviations text that admits a mistake the writer made, else ''."""
    plain = QUOTED_RE.sub(" ", MISTAKE_URL_RE.sub(" ", FENCE_RE.sub(" ", deviations)))
    for sentence in _sentences(plain):
        for clause in MISTAKE_CLAUSE_SPLIT_RE.split(sentence):
            for fault in MISTAKE_FAULT_RE.finditer(clause):
                before = clause[:fault.start()]
                # Split on whitespace only, so a contraction such as didn't stays one word.
                near = " ".join(before.split()[-(MISTAKE_NEGATOR_GAP + 1):])
                if MISTAKE_FIRST_PERSON_RE.search(before) and not MISTAKE_NEGATOR_RE.search(near):
                    return clause.strip()
    return ""


def _sentences(text):
    return [BULLET_RE.sub("", s.strip()) for s in MISTAKE_SENTENCE_SPLIT_RE.split(text)]


def mistake_problem(text):
    """The refusal text when Deviations admits a mistake and names no guard (rule
    `building-mistake-names-its-guard`), else ''."""
    deviations = report_section(text, "Deviations")
    clause = _admitted_clause(deviations)
    if not clause:
        return ""
    # A guard word and its ref must share a sentence, so a stray ref elsewhere does not clear the admission.
    if (MISTAKE_STEP_RE.search(deviations) or MISTAKE_DEBT_RE.search(deviations)
            or any(MISTAKE_GUARD_WORD_RE.search(s) and DONE_REF_RE.search(s) for s in _sentences(deviations))):
        return ""
    return MISTAKE_REASON % repr(clause[:80])


def _own_lane_read(path, own_id):
    """(is_lane, parent id): this session's own get_session record in the transcript. A lane carries the
    tag cs-build:lane or a parent_session_id. No record reads as owner-facing."""
    import own_session
    tags, _tagged_after, parent = own_session.own_session_read(path, own_id)
    return tags is not None and (LANE_TAG in tags or bool(parent)), parent


PAGE_WRITER_ROLE = "triage"  # the session role that always writes the waiting page


def _is_page_writer(path):
    """True when this session's own newest get_session record carries cs-build:triage: the triage session is the
    repo's page writer, whatever parent id its record names (guard_merge's one triage reader)."""
    _hooks_on_path()
    from guard_merge import _own_tier_proved as session_role_proved  # glossary-ok: the name guard_merge exports
    return session_role_proved(path, PAGE_WRITER_ROLE)


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
    Owner-facing: a send to the page writer, or an items write to this repo's page. The writer is the newest
    meta/page read's; with none, the one session its triage tag names for this repo (`_transcript.page_writer`), read
    from the get_session and list_sessions records of this transcript (its ack starts no turn either). A tag
    writer counts only for a send whose own result shows delivery (`delivered_tool_use_ids`); a send with no result,
    a failed result or a non-delivered one does not. A transcript writer counts on the send alone. With no writer
    named, or two triage sessions, the refusal says to run list_sessions in its own turn first. The question box
    counts only in a repo with no waiting page. A send to @parent reaches no one there.
    Lane: a send to the parent or the page writer; a send to @parent counts only in a lane. A session whose own
    newest get_session record carries cs-build:triage is the page writer, not a lane, though its record names a
    parent: it is owner-facing, so its items write to this repo's page passes.
    Cost: nothing past the text check when the turn has no question or sends to the writer. Else the own-record
    import and a transcript read, only in a session with a remote id. A lane reads no layout; an owner-facing
    turn with no counted send reads the repo name (git's config file) and the transcript's session records for the
    tag writer when it has no meta/page writer, then the waiting page (`layout.waiting_page`); a delivered send to
    the tag writer returns after the first read."""
    if not (offers_a_pick(text) or asks_a_question(text)):
        return "", ""
    writer = page_writer_id(records)
    acks = {writer: {writer}} if writer else {}
    uses, sends = _turn_acts(records, turn, acks)
    if writer and any(writer in t for t in sends):
        return "", ""
    _hooks_on_path()
    from override import remote_session_id
    own_id = remote_session_id()
    lane, parent = _own_lane_read(hook.get("transcript_path"), own_id) if own_id else (False, None)
    if lane:
        if parent:
            acks[parent] = {parent} | PARENT_TARGETS
            uses, sends = _turn_acts(records, turn, acks)
        wanted = ({parent} if parent else set()) | ({writer} if writer else set()) | PARENT_TARGETS
        if any(t & wanted for t in sends):
            return "", ""
        if not _is_page_writer(hook.get("transcript_path")):
            return LANE_REFUSAL, ""
        # The triage session names a parent id in its record but is the page writer: its items write counts too.
    root = repo_root(hook.get("cwd"))
    if not writer and root:
        writer = page_writer(records, layout.repo_name(root))
        if writer:
            acks[writer] = {writer}
            uses, sends = _turn_acts(records, turn, acks)
            # Only the cloud body {"status":"delivered"} counts; the local SendMessage success shape is not measured.
            delivered = delivered_tool_use_ids(records)
            if any(writer in t and u.get("id") in delivered for u, t in zip(uses, sends)):
                return "", ""
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
    return OWNER_REFUSAL % (("the page writer is session " + writer) if writer else
                            "the page writer is not known to this session; the waiting page is " + page + ". Run list_sessions "
                            "(tag cs-build:triage, the same cs-repo tag as this repo) in its own turn first, so the one triage "
                            "session is named, then send the question to it"), ""


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
    _hooks_on_path()
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
            reason = owner_line(
                "Rewrite-stamp guard (rule rewrite-cite-predates-ruling)",
                "decision `%s` was last committed %s, on every branch and HEAD, before the ruling %s that it is "
                "said to be rewritten for"
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


PHRASE = r"`?\s*:?\s*refusal (?:was|is) right"
HEDGE_RE = re.compile(r"\?|\bor\b|\bnot sure\b|\bunsure\b|\bmaybe\b|\bwhether\b|\bif\b", re.I)


def says_refusal_right(text, tool):
    """True when the reply says "refusal was right" or "refusal is right" directly after `tool`'s name
    (as names_tool counts a name; an optional colon may sit between), on any line. A hedge in the same
    clause, before the name or after the phrase ("not sure", "or wrong", "?"), does not clear. The
    guard's own refusal never clears: it puts the phrase after the placeholder `<tool_name>`. A
    plural ("refusals were right") does not clear."""
    if "__" in tool:
        pattern = re.compile(r"(?<!\w)" + re.escape(tool) + r"(?!\w)" + PHRASE + r"(?!\w)", re.I)
    else:
        pattern = re.compile("`" + re.escape(tool) + PHRASE + r"(?!\w)", re.I)
    for line in text.splitlines():
        for hit in pattern.finditer(line):
            before = re.split(r"[.;]", line[:hit.start()])[-1]
            after = re.split(r"[.;]", line[hit.end():], maxsplit=1)[0]
            if not HEDGE_RE.search(before) and not HEDGE_RE.search(after):
                return True
    return False


def _tool_use_ids(records):
    return {u.get("id") for r in records for u in tool_uses(r)}


def tool_use_sources(transcript_path):
    """(ids of agent calls, ids of orchestrator calls) in the session's transcripts, or None when the
    transcript cannot be read.

    An agent's calls are sidechain records. Claude Code writes them to
    <session>/subagents/agent-<id>.jsonl beside the transcript <session>.jsonl (measured on a real
    session's transcripts), and a sidechain record in the transcript itself counts too. The orchestrator's
    calls are the transcript's other records. An agent file that cannot be read adds nothing."""
    try:
        records = read_transcript(transcript_path)
    except Exception:
        return None
    agent = _tool_use_ids(r for r in records if r.get("isSidechain"))
    orchestrator = _tool_use_ids(r for r in records if not r.get("isSidechain"))
    import own_session  # the one home of the agent transcript folder
    folder = own_session.agent_transcript_dir(transcript_path)
    try:
        names = sorted(n for n in os.listdir(folder) if n.endswith(".jsonl"))
    except OSError:
        names = []
    for name in names:
        try:
            agent |= _tool_use_ids(read_transcript(os.path.join(folder, name)))
        except Exception:
            continue
    return agent, orchestrator


def refusal_rows(path, skipped=None):
    """(line, row) for each row of the refusals file at `path` that holds a tool_name. A bad line is skipped, and
    appended to `skipped` when the caller passes a list, for the reader that must report an unread file."""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                if skipped is not None and line.strip():
                    skipped.append(line)
                continue
            if isinstance(row, dict) and isinstance(row.get("tool_name"), str):
                rows.append((line.rstrip("\n"), row))
    return rows


def _read_raised(path):
    """The (tool_name, reason) pairs recorded in the raised-refusals file at `path`; [] when it is missing or bad."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    pairs = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
            pairs.append((item[0], item[1]))
    return pairs


def pending_refusals(hook, text):
    """Settle the session's refusals file against the reply and return the tool names still unnamed.

    A row leaves the file when the reply names its tool under Input Needed, or says "refusal was right" /
    "refusal is right" directly after its name (says_refusal_right); or when the refused call was an
    agent's: the row has agent_id, or its tool_use_id is a tool_use in an agent record. A row whose
    tool_use_id is in an orchestrator record stays, even with agent_id. A row with no tool_use_id, a
    tool_use_id found nowhere (not yet flushed) or an unreadable transcript stays, unless it has agent_id.
    A row cleared by name is also recorded as (tool_name, reason) in the session's raised-refusals file, and a
    later row with the same tool_name and the same reason, not blank after strip, is dropped without blocking: the owner
    already heard of it. A different reason or tool, or a blank reason, still blocks. The refusals file goes
    when none is left. One stat per Stop when the session had no refusal; the raised file is read only when
    the refusals file has rows, and written only when a row is cleared by name. Fails open: [] on any error;
    a raised file that cannot be written only means the repeat blocks once more.
    Spec: docs/decisions/refusals-reach-the-owner.md."""
    try:
        _hooks_on_path()
        import shared_names
        path = shared_names.refusals_path(hook.get("session_id"))
        if path is None or not os.path.exists(path):
            return []
        rows = refusal_rows(path)
        if not rows:
            return []
        section = input_needed_section(text)
        agent_ids, orchestrator_ids = set(), set()
        transcript = hook.get("transcript_path")
        if transcript and any(r.get("tool_use_id") for _, r in rows):
            agent_ids, orchestrator_ids = tool_use_sources(transcript) or (set(), set())
        raised_path = shared_names.raised_refusals_path(hook.get("session_id"))
        raised = _read_raised(raised_path) if raised_path else []
        newly_raised = []
        kept = []
        for line, row in rows:
            tool = row["tool_name"]
            use_id = row.get("tool_use_id")
            reason = row.get("reason")
            has_reason = isinstance(reason, str) and bool(reason.strip())
            from_agent = (row.get("agent_id") or use_id in agent_ids) and use_id not in orchestrator_ids
            if from_agent:
                continue
            if names_tool(section, tool) or says_refusal_right(text, tool):
                if has_reason and (tool, reason) not in raised + newly_raised:
                    newly_raised.append((tool, reason))
                continue
            if has_reason and (tool, reason) in raised:
                continue
            kept.append((line, tool))
        if newly_raised and raised_path:
            try:
                os.makedirs(os.path.dirname(raised_path), exist_ok=True)
                with open(raised_path, "w", encoding="utf-8") as f:
                    json.dump([list(pair) for pair in raised + newly_raised], f)
            except OSError:
                pass
        if len(kept) != len(rows):
            if kept:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("".join(line + "\n" for line, _ in kept))
            else:
                os.remove(path)
        return [tool for _, tool in kept]
    except Exception:
        return []


def hold_reason(entries):
    """The refusal for the triage hold, naming its `entries` (joined)."""
    return HOLD_REASON % entries


def _shown_flags(hook, flags):
    """The texts of `flags`, (key, text) pairs, that this session's Stop has not shown yet. It records their keys
    in <config dir>/state/route-flags/<session_id>.json, so each shows once per session. [] when the session has
    no plain id or the record cannot be written: a flag that cannot be counted would repeat on every Stop."""
    if not flags:
        return []
    try:
        _hooks_on_path()
        import shared_names
        path = shared_names.route_flags_path(hook.get("session_id"))
        if path is None:
            return []
        try:
            with open(path, encoding="utf-8") as f:
                seen = json.load(f)
            seen = [k for k in seen if isinstance(k, str)] if isinstance(seen, list) else []
        except (OSError, ValueError):
            seen = []
        fresh = []
        for key, text in flags:
            if key not in seen:
                seen.append(key)
                fresh.append(text)
        if fresh:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(seen, f)
        return fresh
    except Exception:
        return []


def refusal_route_flags(hook):
    """The `route_flag` of each row in the session's refusals file that hooks/refusal_note.py wrote for a refusal a
    route row contradicts, once each per session. Read before pending_refusals settles the file. This is the
    named reader of those flags, so a flag is never written unread: it shows them and never refuses on one."""
    try:
        _hooks_on_path()
        import shared_names
        path = shared_names.refusals_path(hook.get("session_id"))
        if path is None or not os.path.exists(path):
            return []
        flags = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if isinstance(row, dict) and isinstance(row.get("route_flag"), str) and row["route_flag"]:
                    flags.append(("refused:" + row["route_flag"], row["route_flag"]))
        return _shown_flags(hook, flags)
    except Exception:
        return []


def success_route_flags(hook, after):
    """One flag per route row that says an act is refused, and that a call of the turn `after` matched and
    succeeded in (a tool_result without is_error), once per row per session. The match and the surface are
    hooks/route_match.py. Fails open: [] on any error."""
    try:
        failed = {b.get("tool_use_id") for r in after for b in tool_results(r) if b.get("is_error")}
        answered = {b.get("tool_use_id") for r in after for b in tool_results(r)}
        calls = [(u.get("name"), u.get("input")) for r in after for u in tool_uses(r)
                 if u.get("id") in answered and u.get("id") not in failed]
        _hooks_on_path()
        if not calls:  # a turn with no successful call reads no rows file
            return []
        import route_match
        flags = []
        for row in route_match.matching_rows(route_match.load_rows(), "refused", calls):
            key = "succeeded:%s" % row.get("id")
            if all(key != k for k, _ in flags):
                flags.append((key, "route row %s contradicted: it says this call is refused on %s, and it succeeded."
                              % (row.get("id"), row.get("surface"))))
        return _shown_flags(hook, flags)
    except Exception:
        return []


# The hand-off cite (rule output-never-hand-off-doable-step). A "Why yours:" line in prose above the report, or in the
# Input Needed or Next item, says why an act is the owner's. When it gives a capability reason (the owner's session can do
# what this one cannot), it must cite a route row that says the act is not doable here, a tool the classifier refused
# this session, or a dated measurement. A check name is no cite. A line with a choice, login or safety-kept phrase needs
# no cite, even beside a capability verb: the owner keeps the act whatever this session can do.
ROUTE_CITE_RE = re.compile(r"\(route\s+([\w.-]+)\)", re.I)
MEASURED_RE = re.compile(r"\(measured\b([^)]*)\)", re.I)
MEASURED_OK_RE = re.compile(r"\s+(\d{4}-\d{2}-\d{2}),\s*\S")
def _forms_re(forms):
    return r"\b(?:%s)\b" % "|".join(_clause.form_pattern(form) for form in forms)


# The capability words both readers share: the three _clause.CANT_FORMS (the start of _clause.CANNOT_FORMS), refused,
# denied, forbidden, no access, not allowed or permitted, unavailable, the 403 token, and blocked or not available.
# "blocked until" and "not available until" wait on another act, so they are a dependency, not a capability.
_CAPABILITY_CORE = _forms_re(_clause.CANT_FORMS) + (
    r"|\brefuse[sd]?\b|\bdenied\b|\bforbidden\b|\bno access\b|\b(?:isn['’]t|not)\s+(?:allowed|permitted)\b"
    r"|\bunavailable\b|\b403\b|\bblocked\b(?!\s+until\b)|\bnot available\b(?!\s+until\b)")
# The words only the hand-off cite reads: the two _clause.COULD_NOT_FORMS, the reject forms, and the 401 token.
_CAPABILITY_CITE_ONLY = _forms_re(_clause.COULD_NOT_FORMS) + r"|\breject(?:s|ed|ing)?\b|\b401\b"
# The hand-off cite reads both pieces: the five forms (CANT_FORMS and COULD_NOT_FORMS), the reject forms, the 401 or 403
# token, and the other core words.
CAPABILITY_RE = re.compile(_CAPABILITY_CORE + "|" + _CAPABILITY_CITE_ONLY, re.I)
# cannot_lines leaves a Why yours line to the hand-off guard when it reads one of the core words. A line whose only
# capability word is a could-not form, a reject form or 401 stays in the cannot-claim check, which asks for the check that
# failed.
CAPABILITY_SKIP_RE = re.compile(_CAPABILITY_CORE, re.I)
CHOICE_RE = re.compile(
    r"\byour choice\b|\byour call\b|\bneeds your login\b|\bsign in as you\b|\ba safety rule\b.*?\bstays yours\b"
    r"|\bthe safety rules keep\b", re.I)
# question_form.WHY_YOURS_LINE judges a waiting-page task's context, where the label starts the line. A reply carries it
# behind a list marker or in bold, so this reader allows those forms. Widening WHY_YOURS_LINE itself would let a page
# task pass in forms the page refuses today.
WHY_YOURS_FORM_RE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*|__)?Why yours(?:\*\*|__)?:(?:\*\*|__)?[ \t]*\S", re.I)
HAND_OFF_TAIL = " (rule output-never-hand-off-doable-step)"
HAND_OFF_CHECK = "Hand-off guard"
HAND_OFF_NO_CITE = owner_line(HAND_OFF_CHECK, "a Why yours line gives a capability reason with no cite")
HAND_OFF_NO_DATE = owner_line(
    HAND_OFF_CHECK, "a Why yours line carries a measured premise with no date, or with no check and result")


def hand_off_lines(text, anywhere=False):
    """Each Why yours line of the reply, without its quote marker, from the prose above the report and from the Input
    Needed and Next items. The label counts at line start, behind a list marker or in bold. With `anywhere`, from
    every line of the reply: hooks/reply_judge.py reads the route a line cites, wherever the line sits, and the
    hand-off guard's own call keeps the narrower reading."""
    lines = text.splitlines()
    if anywhere:
        return [line.strip() for line in (l.lstrip("> \t") for l in lines) if WHY_YOURS_FORM_RE.match(line.strip())]
    start = find_block_start(lines)
    above = lines if start is None else lines[:start]
    sources = above + input_needed_section(text).splitlines() + report_section(text, "Next").splitlines()
    return [line.strip() for line in sources if WHY_YOURS_FORM_RE.match(line.strip())]


def _cited_refusal(hook, line):
    """True when the Why yours `line` names a tool in this session's refusals file, False when it does not, None when
    the file did not read (it cannot be opened, is not UTF-8, or a line in it is not JSON) and names none. The file is
    read here, before pending_refusals settles it: a reply that names the tool under Input Needed clears its row."""
    _hooks_on_path()
    import shared_names
    path = shared_names.refusals_path(hook.get("session_id"))
    if path is None or not os.path.exists(path):
        return False
    skipped = []
    try:
        rows = refusal_rows(path, skipped)
    except (OSError, UnicodeDecodeError):  # a directory, a lost file or bytes that are not UTF-8: this read only
        return None
    if any(names_tool(line, row["tool_name"]) for _, row in rows):
        return True
    return None if skipped else False


def _measured(line):
    """'ok' for a `(measured <date>, <check and result>)` cite with a real date, 'bad' for one without, else ''."""
    found = MEASURED_RE.search(line)
    if not found:
        return ""
    dated = MEASURED_OK_RE.match(found.group(1))
    try:
        datetime.date.fromisoformat(dated.group(1))
    except (AttributeError, ValueError):
        return "bad"
    return "ok"


def _route_verdict(ids):
    """(kind, text) for the route ids a Why yours line cites: kind "ok", "works" (a row says the act is doable),
    "dead" (no row holds the id), or "unknown" (the file or the row's outcome on this surface did not read). Reads the
    rows file once, through hooks/route_match.py. A row of another surface says nothing here, so it reads unknown."""
    _hooks_on_path()
    import route_match
    rows = route_match.read_rows()
    if rows is None:
        return "unknown", ("the route rows file did not read, so the route cite %s went unchecked"
                           % ", ".join(ids))
    here = route_match.surface()
    kinds = []
    for rid in ids:
        held = [row for row in rows if row.get("id") == rid]
        row = next((r for r in held if r.get("surface") == here), None)
        if not held:
            kinds.append(("dead", "route id %s is in no row of the route rows file" % rid))
        elif row is None or row.get("outcome") not in ("refused", "asks", "works"):
            kinds.append(("unknown", "route row %s has no readable outcome on %s" % (rid, here)))
        elif row["outcome"] == "works":
            kinds.append(("works", "route row %s says this act works on %s, so it is not the owner's to do; the route is %s"
                          % (rid, here, row.get("route") or "the one that row names")))
        else:
            return "ok", ""
    for kind in ("works", "dead", "unknown"):
        for found, text in kinds:
            if found == kind:
                return kind, text


def cite_tokens_verdict(line):
    """(kind, detail) for the route and measured cite tokens of `line` alone, with no capability verb needed: the page
    reads a str_replace fragment that swaps only a cite (hooks/question_form.py). Kind is "undated" (a `(measured ...)`
    token with no date or no check and result), "works", "dead", "unknown" as `_route_verdict` gives them, or "ok"
    (no token, or a route token whose row says refused or asks). A line with no route token reads no file."""
    found = MEASURED_RE.search(line)
    if found and found.group(1).strip() and _measured(line) == "bad":  # a bare "(measured)" is a premise kind, not a cite
        return "undated", ""
    ids = ROUTE_CITE_RE.findall(line)
    return _route_verdict(ids) if ids else ("ok", "")


def why_yours_verdict(hook, line):
    """(kind, detail) for one Why yours `line`. Kind is "ok" (a choice phrase, no capability verb, or a cite that holds),
    "none" (a capability reason with no cite), "undated" (a `(measured ...)` cite with no date or no check and result),
    "works" (a cited row says the act is doable), "dead" (a cited id no row holds), "unknown" (the rows file or the
    row's outcome on this surface did not read) or "unread" (the refusals file did not read). Detail is the text of the
    last three. A `hook` of None reads no refusals file: the waiting page (hooks/question_form.py) accepts a route cite
    and a dated measured cite only. The refusals file is read for a capability line, the rows file only for a line
    with a route cite."""
    if CHOICE_RE.search(line) or not CAPABILITY_RE.search(line):
        return "ok", ""
    refused = _cited_refusal(hook, line) if hook is not None else False
    measured = _measured(line)
    if refused or measured == "ok":
        return "ok", ""
    ids = ROUTE_CITE_RE.findall(line)
    kind, detail = _route_verdict(ids) if ids else ("none", "")
    if kind != "none":
        return kind, detail
    if measured == "bad":
        return "undated", ""
    return ("unread", "") if refused is None else ("none", "")


def hand_off_problem(hook, text):
    """(refusal, note) for the reply's Why yours lines, else ('', ''). A line with a choice phrase, or with no
    capability verb, needs no cite. A capability line passes on a tool this session's classifier refused, a dated `(measured ...)` cite, or a route cite
    whose row says refused or asks. A "works" row, a dead id, an undated measurement or no cite is refused. A file or row
    that did not read is a note that says UNKNOWN. Cost: the reply's text; the refusals file and the rows file are
    read only for a reply that holds a capability Why yours line, the rows file only for a line with a route cite."""
    refusals, notes = [], []
    for line in hand_off_lines(text):
        kind, detail = why_yours_verdict(hook, line)
        if kind == "ok":
            continue
        if kind == "undated":
            refusals.append(HAND_OFF_NO_DATE)
        elif kind == "unread":
            notes.append("Hand-off guard: UNKNOWN, this session's refusals file did not read, so the cite went unchecked.")
        elif kind == "none":
            refusals.append(HAND_OFF_NO_CITE)
        elif kind == "unknown":
            notes.append("Hand-off guard: UNKNOWN, " + detail + ".")
        elif kind == "works":
            refusals.append(owner_line(HAND_OFF_CHECK, detail))
        else:
            refusals.append(owner_line(HAND_OFF_CHECK, "the Why yours line cites a route id the route rows file "
                                       "does not hold (%s)" % detail))
    unique = list(dict.fromkeys(refusals))
    return (" ".join(unique) + HAND_OFF_TAIL if unique else ""), " ".join(dict.fromkeys(notes))


# The cannot-claim check (rule output-never-hand-off-doable-step). A reply sentence that says this session cannot do a table
# act is a claim, so the turn must show a failed try of that act, or the sentence must carry a hand-off cite, and it must
# name its check. A notice (a connect-failure attachment, say) is no try: only a tool call with a failed result is.
# Why: a notice alone can make a reply hand the owner an act the session can do, such as a PR that the GitHub MCP
# create-PR tool opens on its first call. Record: decision claims-carry-backing.
_NOT_NAME = r"(?<![\w-])"  # a phrase inside a hyphenated name (a branch called cannot-claim-x) is no phrase
# The phrases, the permission forms too, are _clause.CANNOT_FORMS.
# A hyphen just before or after a phrase makes it part of a name, so the match refuses it.
CANNOT_RE = re.compile(
    _NOT_NAME + "(?:%s)(?![\\w-])" % "|".join(_clause.form_pattern(form) for form in _clause.CANNOT_FORMS),
    re.I)
# The words just before the phrase must hold the writer's own subject (_clause.own_subject), or the phrase opens its clause.
# Any other subject (it, the guard, the lane, the session, a builder in this session, a draft PR) is another party, so the
# sentence is no claim about this session. A conditional or a negator just before the phrase (_clause.conditional,
# _clause.negated_near) is no claim. A passive act whose clause says where it runs ("can't be merged from here",
# _clause.FROM_HERE_RE) is a claim whatever its subject.
# After the phrase: a doubt, a promise or a wait is no claim. "be" skips only before these words: "can't be merged" claims.
CANNOT_SKIP_NEXT_RE = re.compile(
    r"^\s*(?:be\s+(?:undone|reverted|reversed|sure|certain)|tell|say|know|guarantee|promise|recall|wait|help)\b", re.I)
CANNOT_DEPENDENCY_RE = re.compile(r"\b(?:until|before)\b|\bwithout\s+your\b", re.I)
# A blocker is a true reason, not a hand-off: the act waits on a blocker in a state (CI is red, the batch run is in
# progress, a hold is on). A blocker noun followed by a tool noun (the checks tool, the review tool, a connector on hold)
# is an outage and stays a claim, and so does the lock in index.lock. A reason word (because, while) opens the blocker in
# the phrase's sentence part, before or after it. A bare blocker state skips the claim when a join ties it to the claim
# clause: before it, ending at a semicolon, a colon, a dash, or a comma with so ("CI is red, so I can't merge."); after
# it, past a semicolon, a colon or a dash, or in parentheses in the clause ("I can't merge PR 12 (CI is red).").
# A failing word followed by to and a verb of _clause.OUTAGE_VERBS (start, connect, respond, authenticate, clone ...) names an
# outage ("failing to start"), not a red check ("because CI is failing to go green" skips). A sentence that ties a red
# state to its claim by a so comma or by because is no claim: "CI is red, so I can't merge." and "Because CI is red I cannot
# merge." skip. A no-try "cannot" without that join blocks: "CI is red so I cannot merge." (no comma) and "CI is failing to
# go green, so I cannot merge." (the state is not right before the comma). A checks noun after a noun of
# _clause.OUTAGE_NOUNS (connection, network, auth, proxy, health ...) is an outage too.
_FAIL_END = r"(?!\s+to\s+(?:%s)\b)" % "|".join(_clause.OUTAGE_VERBS)  # the verbs have one home, lint/_clause.py
_CI_CHECKS = "".join("(?<!%s )" % noun for noun in _clause.OUTAGE_NOUNS) + "checks?"
_BLOCKER_TAIL = (
    r"(?:is|are|was|were)\s+(?:still\s+)?(?:red|running|pending|in\s+progress|failing%s)" % _FAIL_END
    + r"|(?:is|are|was|were)(?:\s+not|n['’]t)\s+green|ha(?:s|ve)(?:\s+not|n['’]t)\s+passed")
# Each blocker state gates the acts it stops (None: every table act). A red check, a pending review or a hold stops a
# merge, and main's protection stops a push or a merge. A claim of any other act has no blocker among them.
_BLOCKER_STATES = (
    (("pr-merge",), r"(?<![\w.])(?:CI|%s|(?:the\s+)?batch(?:\s+run)?)\s+(?:%s)" % (_CI_CHECKS, _BLOCKER_TAIL)),
    (("pr-merge",), r"(?<![\w.])review\s+is\s+pending"),
    (("pr-merge",), r"(?<![\w.])(?:hold|freeze)\s+is\s+on|\bunder\s+(?:the\s+)?(?:hold|freeze)\b"),
    (("push", "pr-merge"), r"(?<![\w.])main\s+is\s+protected"),
    (None, r"\bno\s+grant\b"),
)
_BLOCKER_RES = {}


def _blocker_res(act):
    """The compiled blocker readers for a claim of `act`, cached: (state, reason word then state, a state that ends just
    before the claim, a state that follows it past a semicolon, colon or dash, a state in parentheses). All read the
    states in _BLOCKER_STATES that gate `act`."""
    if act not in _BLOCKER_RES:
        state = "|".join(pattern for acts, pattern in _BLOCKER_STATES if acts is None or act in acts)
        _BLOCKER_RES[act] = (
            re.compile(r"(?:%s)\b" % state, re.I),
            re.compile(r"\b(?:because|while|since|as\s+long\s+as|unless)\b[^;]{0,60}?(?:%s)\b" % state, re.I),
            re.compile(r"(?:%s)\b[\s)*_]*(,|[;:—–]|\s-{1,2}\s)$" % state, re.I),
            re.compile(r"^(?:[;:—–]|\s-{1,2}\s)\s*(?:%s)\b" % state, re.I),
            re.compile(r"\(\s*(?:%s)\b" % state, re.I))
    return _BLOCKER_RES[act]


# A rule id in parentheses after the act names the rule that stops it. It has two hyphens or more, so "(read-only)" is a
# capability and stays a claim, and it must be a real rule or decision id (_names_rule_id): "(pre-push-hook)" claims.
CANNOT_RULE_ID_RE = re.compile(r"\(\s*([a-z][a-z0-9]*(?:-[a-z0-9]+){2,})\s*\)", re.I)
# A sentence that names a rule states the rule, so it is not the session's claim. A semicolon ends that sentence: the
# clause after it is judged on its own.
CANNOT_RULE_RE = re.compile(r"\b(?:rule|ruling|decision|grant)s?\b", re.I)
# The past-ruling guard's own remedy says why its check could not run. A line or a sentence that starts with its label is
# that form; the guard lets the label follow a question on the same line.
CANNOT_UNVETTED_RE = re.compile(r"^(?:[-*+]|\d+[.)])?\s*(?:\*\*)?Unvetted:", re.I)
# A phrase in the past tense reports a failure (_clause.past): could not, wasn't able, or any phrase right after was or were.
# Emphasis marks (**cannot**, _push_, a lone ** after a word) are no part of a word; a mark between two word characters
# (snake_case) stays. cannot_lines reads each line with the marks removed (_strip_emphasis).
CANNOT_EMPHASIS_RE = re.compile(r"(?<!\w)(?:\*\*|__|\*|_)|(?:\*\*|__|\*|_)(?!\w)")
# A code span of one act verb (`push`) names the act like the bare word.
CANNOT_VERB_SPAN_RE = re.compile(r"^`(open|create|make|raise|file|submit|merge|push|close|comment|mark|edit|update)`", re.I)
_PR = r"(?:PRs?|pull[- ]requests?)"
# A preposition ends the pr-open object: "open the logs for PR 12" opens the logs, not a PR.
_PREPOSITION = "(?:%s)" % "|".join(_clause.PREPOSITIONS)  # the prepositions have one home, lint/_clause.py
CANNOT_PR_RE = re.compile(r"\b" + _PR + r"\b", re.I)
# Act -> the words that name it, read from the verb the phrase governs: each pattern is anchored at the start of the
# window, so a later noun ("the merge commit") names no act. A claim of an act outside this table is no claim.
CANNOT_ACTS = (
    ("pr-open", re.compile(r"^(?:open(?:ing)?|creat(?:e|ing)|mak(?:e|ing)|rais(?:e|ing)|fil(?:e|ing)|submit(?:ting)?)\b(?:\s+(?!(?:%s)(?![\w-]))\S+){0,4}?\s+%s\b" % (_PREPOSITION, _PR), re.I)),
    ("pr-merge", re.compile(r"^(?:be\s+)?merg(?:e|ed|ing)\b", re.I)),
    ("push", re.compile(r"^(?:git\s+)?(?:be\s+)?push(?:ed|ing)?\b", re.I)),
    ("pr-edit", re.compile(r"^(?:clos(?:e|ing)|comment(?:ing)?|mark(?:ing)?|edit(?:ing)?|updat(?:e|ing))\b(?:\s+\S+){0,3}\s+%s\b" % _PR, re.I)),
    ("github-reach", re.compile(
        r"^(?:reach(?:ing)?|us(?:e|ing)|access(?:ing)?|connect(?:ing)?\s+to)\s+(?:the\s+)?`?(?:mcp__github__\w*|github\b|gh(?![\w-])|api\.github\.com)",
        re.I)),
)
# A passive form that names the PR elsewhere in its clause: "the PR can't be opened".
# The nouns that, as the object of open, merge, close, comment or update, name no PR: "merge the config files" and "update
# the docs for PR 12" merge and update files. A PR named in the object (not as a possessor) keeps the claim: "open the CI
# logs and PR".
CANNOT_NON_PR_OBJECTS = ("file", "files", "config", "configs", "doc", "docs", "document", "documents", "log", "logs",
                         "diff", "diffs", "tag", "tags", "readme")
_PR_WORDS = ("pr", "prs", "pull-request", "pull-requests", "pull", "request", "requests")
# The route a run names: "run gh pr create", "run `git push`".
CANNOT_RUN_ROUTE_RE = re.compile(r"^run\s+`?(?=gh pr |git (?:push|merge)(?![\w-]))", re.I)
CANNOT_PASSIVE_ACTS = (
    ("pr-open", re.compile(r"^be\s+(?:opened|created|raised|filed|submitted)\b", re.I)),
    ("pr-edit", re.compile(r"^be\s+(?:closed|edited|updated|marked)\b", re.I)),
)
CANNOT_GITHUB_SPAN_RE = re.compile(r"^`(?:gh\b|mcp__github__)", re.I)
GITHUB_REACH = "github-reach"
# The act each tool is a route of. Every mcp__github__ tool is also a route of github-reach. The Bash routes are read from
# the command by _segment_tries.
CANNOT_TOOL_ACTS = {
    "mcp__github__create_pull_request": "pr-open",
    "mcp__github__merge_pull_request": "pr-merge", "mcp__github__enable_pr_auto_merge": "pr-merge",
    "mcp__github__push_files": "push", "mcp__github__create_or_update_file": "push",
    "mcp__github__delete_file": "push",
    "mcp__github__update_pull_request": "pr-edit", "mcp__github__add_issue_comment": "pr-edit",
    "mcp__github__update_pull_request_branch": "pr-edit",
}
# `gh pr <verb>` -> act; a verb not here is no route of a table act.
CANNOT_GH_PR_ACTS = {"create": "pr-open", "merge": "pr-merge", "close": "pr-edit", "comment": "pr-edit",
                     "ready": "pr-edit", "edit": "pr-edit"}
CANNOT_GIT_REACH = {"fetch", "push", "ls-remote"}  # the git calls that reach the remote
CANNOT_HTTP_TOOLS = {"curl", "wget", "http", "https"}
# A command or script whose name holds the act word is a route of that act: the repo's merge tool (`merge`) for pr-merge,
# open-pr.sh for pr-open, push.sh for push. The word is a whole part of the name (split at - _ .), so pushd is no push.
CANNOT_SCRIPT_ACTS = (
    ("pr-open", re.compile(
        r"(?:^|[-_.])(?:(?:open|create)[-_]?(?:pr|pull[-_]?request)|(?:pr|pull[-_]?request)[-_]?(?:open|create))(?:[-_.]|$)")),
    ("pr-merge", re.compile(r"(?:^|[-_.])merge(?:[-_.]|$)")),
    ("push", re.compile(r"(?:^|[-_.])push(?:[-_.]|$)")),
)
# A script named for a test (test_merge.py, test-push.sh, push_test.sh) tests the act; its failure is no try of it.
CANNOT_TEST_SCRIPT_RE = re.compile(r"^test[-_]|[-_.]test\b")
CANNOT_INTERPRETER_RE = re.compile(r"^(?:bash|sh|zsh|node|python[\d.]*)$")  # a script runs as the word after these
# The runners that name a script or target as an argument, with the flags that take a value, which are skipped.
CANNOT_RUNNERS = {
    "make": {"-C", "-f", "-I", "-o", "-W", "--directory", "--file", "--include-dir", "--old-file", "--what-if"},
    "gmake": {"-C", "-f", "-I", "-o", "-W", "--directory", "--file", "--include-dir", "--old-file", "--what-if"},
    "npm": {"--prefix", "-w", "--workspace"}, "yarn": {"--cwd"}, "pnpm": {"-C", "--dir", "--filter", "-F"}}
# The input fields that name a GitHub MCP call's target, read in this order.
CANNOT_TARGET_FIELDS = ("pullNumber", "pull_number", "branch", "head")
# A failed try: the result's error flag or an exit code above zero as the shell result reports it. An HTTP 4xx or 5xx
# in an ok result is output text, not a failure; only a relayed agent result, which has no exit of its own, reads it.
# A loose word such as refused in a successful call's output is none of these.
CANNOT_FAIL_RE = re.compile(r"^Exit code [1-9]")
CANNOT_RELAY_FAIL_RE = re.compile(r"\bHTTP(?:/[\d.]+)?\s+[45]\d\d\b")
CANNOT_PULLS_RE = re.compile(r"(?:^|/)pulls(/\d+)?(/merge)?/?(?:\?\S*)?$")
CANNOT_TEXT_ROUTE_RE = re.compile(r"\bgh pr (create|merge|close|comment|ready|edit)\b|\bgit (push)\b")
# Before the phrase, a bare check word with the writer as subject names no call: "I tried; I cannot push." names no check,
# while "the push failed, so I could not push" does (_clause.check_word_counts).
_CHECK_WORD = "(?:%s)" % "|".join(_clause.CHECK_WORDS)  # the words have one home, lint/_clause.py
CANNOT_CHECK_WORD_RE = re.compile(_CHECK_WORD, re.I)
_BACK = _clause.BACK_PATTERN  # "sent back 403": a status the call answered with; the words have one home, lint/_clause.py
_STATUS = _clause.STATUS_PATTERN  # an HTTP status that no hyphen joins and no size unit follows
CANNOT_CHECK_RE = re.compile(
    r"`[^`\n]+`|\bmcp__\w+|\b" + _CHECK_WORD + r"\b|\bexit(?: code)? [1-9]"
    r"|(?:\b(?:HTTP(?:/[\d.]+)?|status|returned|answered|code|error|got|with|gave|hit|a|" + _BACK + r")\s+(?:a\s+)?"
    r"|(?:[(:,;—–]|\s-{1,2})\s*)" + _STATUS,
    re.I)
# With a failed try of the act in the turn, the line may name its check as a reason instead. A reason is a clause of three
# words or more with a verb (is, was, not, rejected ...), read only after the phrase: in parentheses, after a colon, a
# semicolon, a comma or a dash, after because, or the sentence next to the claim (_clause.reasons, _clause.is_reason). A
# bare claim has none of these, and neither has a noun phrase such as "the 450-line diff" or a lead-in before the phrase
# ("Sorry, I could not push."). A clause that a conjunction opens ("..., but I can open a PR") is another clause, not a reason.


def _gives_reason(head, tail, following):
    """True when `tail`, the sentence after the phrase, carries a reason that no conjunction opens, or the sentence that
    `following` names is one, or a clause of `head`, the sentence up to the end of the phrase, says why before it
    (_clause.reasons_before)."""
    tail, head, following = (_strip_emphasis(t)[0] for t in (tail, head, following))
    return any(_clause.is_reason(g) and not _clause.opens_with_joiner(g) for g in _clause.reasons(tail)) \
        or _clause.is_reason(following) or bool(_clause.reasons_before(head))


CANNOT_HEAD = "Cannot-claim guard (rule output-never-hand-off-doable-step): a line says an act cannot be done and "
CANNOT_NO_TRY = (
    CANNOT_HEAD + "this turn shows no failed try of it. A notice is no try. Remedy: run the act on one route; if it "
    "fails, name on the line what you ran and what it returned, or end the line with `(route <id>)` for a route row "
    "that says refused or asks, or with `(measured <date>, <check and result>)`. Lines:")
CANNOT_NO_CHECK = (
    CANNOT_HEAD + "names no check. Remedy: name the tool in backticks and its error. Lines:")


def _mask(text):
    """`text` with each code span and quoted span blanked to spaces of the same length, so a position in the mask is a
    position in the text. A phrase inside either is a mention, never a claim."""
    blank = lambda found: " " * len(found.group())  # noqa: E731
    return QUOTED_RE.sub(blank, CODE_SPAN.sub(blank, text))


def _non_pr_object(window):
    """True when the object of the verb that starts `window` is a file, doc, log or the like and names no PR of its own."""
    found = _clause.head_objects(_clause.words(window), 1)
    return bool(found) and found[-1][0] in CANNOT_NON_PR_OBJECTS and not any(
        word in _PR_WORDS and not possessive for word, possessive in found)


def _window_act(window, clause):
    """The table act the verb at the start of `window` names, else None. `clause` is the phrase's whole clause, where a
    passive form looks for the PR. A code span at the start is read as a route: `gh pr create` is pr-open, and so is a
    run of that route. An object that names a file, doc or log and no PR is no PR act (_non_pr_object)."""
    window = _clause.strip_adverbs(window)
    span = CANNOT_VERB_SPAN_RE.match(window)
    window = span.group(1) + window[span.end():] if span else window
    if window.startswith("`"):
        acts = sorted(_text_acts(window[1:].split("`", 1)[0]))
        return acts[0] if acts else GITHUB_REACH if CANNOT_GITHUB_SPAN_RE.match(window) else None
    if CANNOT_RUN_ROUTE_RE.match(window):
        acts = sorted(_text_acts(window[3:].lstrip().lstrip("`")))
        return acts[0] if acts else None
    for act, rx in CANNOT_ACTS:
        if rx.match(window):
            return None if act in ("pr-open", "pr-merge", "pr-edit") and not window.lower().startswith("be ") \
                and _non_pr_object(window) else act
    for act, rx in CANNOT_PASSIVE_ACTS:
        if rx.match(window) and CANNOT_PR_RE.search(clause):
            return act
    return None


def _scan(parts):
    """(parts, starts, conjs) of one sentence's clauses (_clause.clauses): where each starts, and the clauses that a comma
    and an and, but or or open."""
    return parts, [c.start for c in parts], [c for c in parts if c.lead == "," and c.join in ("and", "but", "or")]


def _claim(body, mask, hit, floor, scan):
    """(act, window, past) when the phrase `hit` claims this session cannot do a table act, else None. `body` and `mask` are one
    sentence and `scan` its clauses (_scan); `floor` is where the previous phrase of the sentence ended, so words that
    condition it do not condition this one. The phrase's clause starts after the last separator (a comma, a dash, but, a
    stop) before it and ends at the first stop after it (a comma does not end it). Not a claim: a conditional or a negator
    just before the phrase, a subject that is not the writer's own (_clause.own_subject), a verb of telling or waiting
    after it, a dependency (until, before, without your) in its clause, a verb that names no table act, a blocker of that
    act (_blocker_res) in its own clause (a comma and, but or or starts another) or in the part after the next semicolon
    or joined to the clause (_joined_blocker), a sentence that names a rule, or a real rule or decision id in parentheses
    in its clause (_names_rule_id, read last, so only a line that is otherwise a claim pays its file read)."""
    parts, starts, conjs = scan
    at = max(bisect.bisect_right(starts, hit.start()) - 1, 0)
    first = at
    while first and parts[first].join in _clause.REASON_LINKS and not parts[first].lead:  # because ends no scope
        first -= 1
    opener = parts[first]
    start = max(opener.start + len(opener.join) if opener.join == "but" else opener.lead_end if opener.lead else opener.start,
                floor)
    end = parts[at].hard_end
    before, after = body[start:hit.start()], body[hit.end():end]
    shown = _clause.veil(before, mask[start:hit.start()])  # a code span or quote negates and conditions nothing
    if _clause.conditional(shown) or _clause.negated_near(shown):
        return None
    words = after.split()
    if not words or CANNOT_SKIP_NEXT_RE.match(after) or CANNOT_DEPENDENCY_RE.search(
            _clause.veil(after, mask[hit.end():end])):  # "until" in a code span waits on nothing
        return None
    if not _clause.own_subject(before) and not (
            after.lstrip().lower().startswith("be ") and _clause.FROM_HERE_RE.search(after)):
        return None
    left = mask.rfind(";", 0, hit.start()) + 1  # the sentence part between the semicolons around the phrase
    right = mask.find(";", hit.end())
    right = len(mask) if right < 0 else right
    if CANNOT_RULE_RE.search(_clause.veil(body[left:right], mask[left:right])):  # `rules.md` names no rule
        return None
    window = _clause.first_words(after)
    act = _window_act(window, before + " " + after)
    if not act:
        return None
    state_re, reason_re = _blocker_res(act)[:2]
    clause_left = max((c.start + len(c.join) for c in conjs if c.lead_at >= left and c.start + len(c.join) <= hit.start()),
                      default=left)
    conj = next((c.lead_at for c in conjs if c.lead_at >= hit.end() and c.start + len(c.join) <= right), None)
    if reason_re.search(body[clause_left:right if conj is None else conj]):
        return None
    if right < len(mask):
        reach = mask.find(";", right + 1)
        if state_re.search(body[right + 1:len(mask) if reach < 0 else reach]):
            return None
    so = _clause.opens_with(before, "so")
    if _joined_blocker(act, body[floor:start], so, after, body[end:]) or _names_rule_id(after):
        return None
    return act, window, _clause.past(hit.group(), before)


def _joined_blocker(act, lead, so, after, tail):
    """True when a bare blocker state of `act` is joined to the claim clause. `lead` is the sentence up to the clause start,
    `so` whether the clause opens with so, `after` the clause after it, and `tail` the sentence from the clause
    break on. Before: the state ends at a semicolon, colon or dash, or at a comma that so follows. After: a semicolon,
    colon or dash, then the state, or the state in parentheses in the clause."""
    _, _, before_re, after_re, paren_re = _blocker_res(act)
    hit = before_re.search(lead)
    if hit and (hit.group(1) != "," or so):
        return True
    return bool(after_re.match(tail) or paren_re.search(after))


_RULE_IDS = []  # (roots, anchors), read once per hook run on the first slug that follows a claim


def _names_rule_id(clause):
    """True when a slug in parentheses in `clause` (CANNOT_RULE_ID_RE) is a real rule or decision id: a `rule:<id>`
    anchor in the rule files (rule_audit.RULE_FILES, the one home of that list) or an <id>.md file in the decisions
    folder (layout.path). Both are read in this file's checkout and in the checkout the global CLAUDE.md points at
    (guard.pointer_checkout): an installed copy holds only the pointer and no decisions. Cost: on the first such slug of
    a hook run, the guard import (cannot_problem needs it next anyway), one read of the pointer, of each rule file and
    of the layout per checkout; per slug, one file stat per checkout. A guard that does not load prints UNKNOWN and
    reads this checkout alone. A checkout whose layout path does not read uses the layout's default; when that does not
    read either, the hook prints UNKNOWN and the slug skips. When no checkout's rule files can be read, the slug skips
    with no note: a guard that cannot read cannot accuse."""
    slugs = [m.group(1).lower() for m in CANNOT_RULE_ID_RE.finditer(clause)]
    if not slugs:
        return False
    if not _RULE_IDS:
        import rule_audit
        if guard is None:  # the Stop run judges claims before cannot_problem loads the guard
            _load_guard()
        if guard is None:
            print("cannot-claim guard: UNKNOWN, the guard did not load, so the pointer checkout's rule ids went unread.",
                  file=sys.stderr)
        pointer = guard.pointer_checkout() if guard is not None else ""
        roots = list(dict.fromkeys(os.path.realpath(r) for r in (os.path.join(HERE, ".."), pointer) if r))
        ids, read = set(), False
        for root in roots:
            try:
                ids.update(rule_audit.claude_md_anchors(rule_audit.rule_text(root)))
                read = True
            except (OSError, UnicodeDecodeError):
                continue
        folders = []  # each checkout's decisions folder: its layout path, else the layout's default path, else unknown
        for root in roots:
            folder = None
            for read_folder in (lambda: layout.path(root, "decisions"), lambda: layout.kinds()["decisions"]["path"]):
                try:
                    folder = os.path.join(root, *read_folder().strip("/").split("/"))
                    break
                except (layout.LayoutError, OSError, KeyError):
                    continue
            folders.append(folder)
        if None in folders:
            print("cannot-claim guard: UNKNOWN, the layout did not read, so a slug in parentheses was not checked "
                  "against the decisions.", file=sys.stderr)
        _RULE_IDS.append((folders, ids if read else None))
    folders, ids = _RULE_IDS[0]
    return ids is None or None in folders or any(
        slug in ids or any(os.path.isfile(os.path.join(folder, slug + ".md")) for folder in folders) for slug in slugs)


def _report_label_end(body):
    """Where a bold report label (LABEL_ORDER) that starts `body` ends, else 0. "**Input Needed** Could not ..." opens
    its clause after the label, so the phrase has no other subject."""
    m = LABEL_RE.match(body)
    return m.end() if m and m.group(1).strip().rstrip(":").strip() in LABEL_ORDER else 0


def _strip_emphasis(text):
    """(`text` with each emphasis mark (CANNOT_EMPHASIS_RE) removed, `keep`), where keep[i] is the index in `text` of
    character i of the stripped text and keep[-1] is len(text). The one home of the emphasis strip."""
    out, keep, last = [], [], 0
    for mark in CANNOT_EMPHASIS_RE.finditer(text):
        out.append(text[last:mark.start()])
        keep.extend(range(last, mark.start()))
        last = mark.end()
    out.append(text[last:])
    keep.extend(range(last, len(text) + 1))
    return "".join(out), keep


def cannot_lines(text):
    """(sentence, act, window, past, prior, following, tail) for each phrase of the reply's prose that claims a table act
    cannot be done; `tail` is the sentence after the phrase. The text is read a sentence at a time, with emphasis marks
    removed (_strip_emphasis); the sentences returned keep them. A sentence that ends in `?` asks and claims nothing, one
    that starts with Unvetted: (the past-ruling guard's form) is not read, and neither is a line that starts with it or a
    Why yours line (the hand-off guard's). Every phrase of a sentence is judged."""
    if not CANNOT_RE.search(CANNOT_EMPHASIS_RE.sub("", text)):
        return []
    found, hand_off = [], None
    for raw in _prose_lines(text, questions=True):
        body, keep = _strip_emphasis(raw)
        if CANNOT_UNVETTED_RE.match(raw) or not CANNOT_RE.search(_mask(body)):
            continue
        if hand_off is None:
            hand_off = {line for line in hand_off_lines(text) if CHOICE_RE.search(line) or CAPABILITY_SKIP_RE.search(line)}
        if raw in hand_off:
            continue
        mask = _mask(body)
        flags = [char != blank for char, blank in zip(body, mask)]  # True where the mask hides a character
        spans = _clause.sentences(body, flags)
        label = _report_label_end(raw)
        at = lambda i: keep[i - 1] + 1 if i else 0  # noqa: E731  where stripped index i starts in `raw`, marks before it kept
        for k, (begin, stop) in enumerate(spans):
            piece, shadow = body[begin:stop], mask[begin:stop]
            sentence = raw[at(begin):keep[stop]].strip()
            if sentence.rstrip("*_)\"' ").endswith("?") or CANNOT_UNVETTED_RE.match(sentence):
                continue
            # a report label opens the clause after it
            floor = next((i for i, at in enumerate(keep) if at >= label), 0) if begin == 0 and label else 0
            scan = _scan(_clause.clauses(piece, flags[begin:stop]))
            for hit in CANNOT_RE.finditer(shadow):
                claim = _claim(piece, shadow, hit, floor, scan)
                floor = hit.end()
                if claim:
                    prior = raw[at(spans[k - 1][0]):keep[spans[k - 1][1]]].strip() if k else ""
                    following = raw[at(spans[k + 1][0]):keep[spans[k + 1][1]]].strip() if k + 1 < len(spans) else ""
                    tail = raw[keep[begin + hit.end()]:keep[stop]]
                    found.append((sentence, claim[0], claim[1], claim[2], prior, following, tail))
    return found


def _pulls_act(token):
    """The act of a GitHub pulls URL or API path: pr-merge for .../pulls/<n>/merge, pr-edit for .../pulls/<n>, pr-open
    for .../pulls, else ''."""
    hit = CANNOT_PULLS_RE.search(token.strip("\"'"))
    return "" if not hit else "pr-merge" if hit.group(2) else "pr-edit" if hit.group(1) else "pr-open"


def _script_tries(tokens):
    """{(act, key)} when the command word of one shell segment (or the script an interpreter runs) names an act, else
    empty. The key is the command's name and its first plain argument, so a later success of the same call cancels it."""
    index = guard.resolve_command(tokens)
    if index is None:
        return set()
    if CANNOT_INTERPRETER_RE.match(os.path.basename(tokens[index]).lower()):
        index = next((i for i in range(index + 1, len(tokens)) if not tokens[i].startswith("-")), None)
        if index is None:
            return set()
    name = os.path.basename(tokens[index]).lower()
    plain, skip = [], False
    for token in tokens[index + 1:]:
        if skip:
            skip = False
        elif token.startswith("-"):
            skip = token in CANNOT_RUNNERS.get(name, ())
        else:
            plain.append(token)
    if name in CANNOT_RUNNERS:
        scripted = plain[:1] in (["run"], ["run-script"])
        if name == "npm" and not scripted:  # npm has no push or merge command: only npm run names a script
            return set()
        plain = plain[1:] if scripted and name not in ("make", "gmake") else plain
        if not plain:
            return set()
        name, plain = os.path.basename(plain[0]).lower(), plain[1:]
    if CANNOT_TEST_SCRIPT_RE.search(name):
        return set()
    target = plain[0] if plain else ""
    return {(act, ("script", name, target)) for act, rx in CANNOT_SCRIPT_ACTS if rx.search(name)}


def _gh_target(verb, args, branch=""):
    """The target of a `gh pr <verb>` call. A create names no PR, so its target is its --head branch, else `branch` (the
    branch the same command checked out). Any other verb names its PR by number or URL wherever it sits among the flags,
    else by its first plain argument; a number is qualified by its --repo, so a PR of another repo is another target. A
    URL names its own repo, so it matches a number only when --repo names the URL's repo. A call that names no
    target is keyed by its own arguments, tagged so they match no named target: an identical retry is the same call, and
    a call with other arguments is not. A call with no arguments has the empty target ''."""
    flags = {"--head": "head", "-H": "head", "--repo": "repo", "-R": "repo"}
    named, plain = {}, []
    for k, token in enumerate(args):
        name, _, value = token.partition("=")
        if name in flags:
            named.setdefault(flags[name], value or (args[k + 1] if k + 1 < len(args) else ""))
        elif token.startswith("-") or k and args[k - 1] in flags:
            continue
        else:
            plain.append(token)
    own = "args " + " ".join(args) if args else ""
    if verb == ["create"]:
        return named.get("head") or branch or own
    for token in plain:
        if re.fullmatch(r"#?\d+", token) or "/pull/" in token:
            url = re.search(r"([^/]+/[^/]+)/pull/(\d+)", token)
            if url:  # a PR's URL names its repo, as --repo does
                return url.group(1) + "#" + url.group(2)
            return (named["repo"] + "#" if named.get("repo") and "/pull/" not in token else "") + token.lstrip("#")
    return (named["repo"] + "#" if named.get("repo") else "") + plain[0] if plain else own


def _checked_out(segment):
    """The branch a `git checkout` or `git switch` in `segment` moves to, else ''."""
    for subcommand, args in guard.git_calls(segment):
        if subcommand in ("checkout", "switch"):
            for k, arg in enumerate(args):
                if arg in ("-b", "-B", "-c", "-C"):
                    return args[k + 1] if k + 1 < len(args) else ""
            return next((a for a in args if not a.startswith("-")), "")
    return ""


def _segment_tries(segment, branch=""):
    """{(act, key)} for the routes one shell segment is a try of: gh (every gh call reaches GitHub; gh pr and gh api
    name table acts), git push, fetch and ls-remote, curl, wget or httpie to github.com, and a command or script
    whose name holds an act word (_script_tries). The key is the
    program, its verb and the target the call names (a PR number, a branch or a URL), so a later success cancels only
    a failure of the same call. A gh pr call that names no target is keyed by its own arguments (_gh_target);
    `branch` is the branch an earlier segment of the same command checked out, the target of a create with no --head.
    A segment with --dry-run is no try."""
    tokens = guard.segment_tokens(segment) or segment.split()
    if "--dry-run" in tokens:
        return set()
    tries = set()
    rest = guard.gh_call_of(segment)
    if rest is not None:
        pr = rest[:1] == ["pr"]
        key = ("gh " + " ".join(rest[:2] if pr else rest[:1]), _gh_target(rest[1:2], rest[2:], branch) if pr else " ".join(rest[1:2]))
        tries.add((GITHUB_REACH, key))
        if pr and rest[1:2]:
            tries.add((CANNOT_GH_PR_ACTS.get(rest[1], ""), key))
        elif rest[:1] == ["api"]:
            tries.update((_pulls_act(token), key) for token in rest[1:])
    for subcommand, args in guard.git_calls(segment):
        key = ("git " + subcommand, " ".join(a for a in args if not a.startswith("-")))
        if subcommand in CANNOT_GIT_REACH:
            tries.add((GITHUB_REACH, key))
        if subcommand == "push":
            tries.add(("push", key))
    tries |= _script_tries(tokens)
    if any(os.path.basename(t) in CANNOT_HTTP_TOOLS for t in tokens):
        for token in (t for t in tokens if "github.com" in t):
            tries.add((GITHUB_REACH, ("http", token)))
            if "api.github.com" in token:
                tries.add((_pulls_act(token.split("api.github.com", 1)[1]), ("http", token)))
    return {(act, key) for act, key in tries if act}


def _text_acts(text):
    """The acts whose routes a text names: a route tool, `gh pr <verb>` or `git push`. A GitHub MCP tool
    name is also github-reach."""
    acts = {act for tool, act in CANNOT_TOOL_ACTS.items() if tool in text}
    if "mcp__github__" in text:
        acts.add(GITHUB_REACH)
    for hit in CANNOT_TEXT_ROUTE_RE.finditer(text):
        acts.add(CANNOT_GH_PR_ACTS[hit.group(1)] if hit.group(1) else "push")
    return acts


def _is_relay(use):
    return use.get("name") in SPAWN_TOOLS or use.get("name") in SEND_TOOLS


def _tool_acts(name):
    """The acts a tool name is a route of: its table act, and github-reach for every GitHub MCP tool."""
    acts = {CANNOT_TOOL_ACTS[name]} if name in CANNOT_TOOL_ACTS else set()
    if isinstance(name, str) and name.startswith("mcp__github__"):
        acts.add(GITHUB_REACH)
    return acts


def _call_tries(use, text):
    """{(act, key)} for one tool call. A shell call is read a segment at a time; a relay (an agent spawn or a send) by the
    route its result text names; any other tool by its name, keyed by the target its input names."""
    name = use.get("name")
    given = use.get("input") if isinstance(use.get("input"), dict) else {}
    if name == "Bash":
        command = given.get("command")
        tries = set()
        if isinstance(command, str):
            branch = ""
            for segment in guard.split_segments(guard.strip_heredoc_bodies(command)):
                tries |= _segment_tries(segment, branch)
                branch = _checked_out(segment) or branch
        return tries
    if _is_relay(use):
        return {(act, ("relay", use.get("id"))) for act in _text_acts(text)}
    target = next((str(given[f]) for f in CANNOT_TARGET_FIELDS if given.get(f) not in (None, "")), "")
    return {(act, (name, target)) for act in _tool_acts(name)}


def failed_tries(records, refused=(), recovered=None):
    """{act: {key, ...}} for each failed tool try in `records`, sidechains skipped. A call failed when its result has
    is_error or an exit code above zero as a shell result reports it (CANNOT_FAIL_RE); a relay's text also fails on an HTTP
    4xx or 5xx (CANNOT_RELAY_FAIL_RE), an ok call's does not. A later call
    that did not fail cancels the earlier failures of the same act and key (the same program, verb and target). A gh pr
    act verb (CANNOT_GH_PR_ACTS) with no arguments has the empty target, which is no identity and cancels nothing; a relay's
    text is no call of its own, so it cancels nothing. A tool in `refused` (the classifier's refusals file) counts as a
    failed try. When `recovered` is a set, each act whose failure a later call cancelled is added to it."""
    uses, tries = {}, {}
    for rec in records:
        if rec.get("isSidechain"):
            continue
        for use in tool_uses(rec):
            if use.get("id"):
                uses[use["id"]] = use
        for result in tool_results(rec):
            use = uses.get(result.get("tool_use_id"))
            if use is None:
                continue
            text = _result_text(result.get("content"))
            found = _call_tries(use, text)
            if (result.get("is_error") is True or CANNOT_FAIL_RE.search(text)
                    or (_is_relay(use) and CANNOT_RELAY_FAIL_RE.search(text))):
                for act, key in found:
                    tries.setdefault(act, set()).add(key)
            elif not _is_relay(use):
                for act, key in found:
                    if not key[1] and key[0].startswith("gh pr ") and key[0][6:] in CANNOT_GH_PR_ACTS:
                        # CANNOT_GH_PR_ACTS holds every act verb: each one with no arguments has the empty key
                        continue  # a bare `gh pr merge` or `gh pr create` names no PR: it cancels nothing
                    if key in tries.get(act, ()) and recovered is not None:
                        recovered.add(act)
                    tries.get(act, set()).discard(key)
    for tool in refused:
        for act in _tool_acts(tool):
            tries.setdefault(act, set()).add(("refused", tool))
    return tries


def refused_tools(hook):
    """The tool names in this session's refusals file, () when it holds none. Raises on a file that cannot be read.
    Called before pending_refusals settles the file away."""
    _hooks_on_path()
    import shared_names
    path = shared_names.refusals_path(hook.get("session_id"))
    if path is None or not os.path.exists(path):
        return ()
    return tuple(row["tool_name"] for _, row in refusal_rows(path))


def _cited(line, refused, act):
    """True when the claim `line` of `act` carries a hand-off cite: a dated measurement, a tool the classifier refused that
    is a route of that act, or a route row that says refused or asks."""
    if _measured(line) == "ok" or any(act in _tool_acts(tool) and names_tool(line, tool) for tool in refused):
        return True
    ids = ROUTE_CITE_RE.findall(line)
    return bool(ids) and _route_verdict(ids)[0] == "ok"


CANNOT_MERGE_TOOL_RE = re.compile(r"\bthe\s+merge\s+tool\b", re.I)  # the repo's merge tool, named in prose


def _backed(tries, act, sentence):
    """True when a failed try of `act` backs `sentence`. A try read from a command's name (a script, a make target; its key
    starts with "script") backs only a line that names it: the name as a whole token. A name that is only the act word
    (merge, push) is named only inside a backtick span, since the prose of any such claim holds that word."""
    for key in tries.get(act, ()):
        if key[0] != "script" or key[1] == "merge" and CANNOT_MERGE_TOOL_RE.search(sentence):
            return True
        token = r"(?<![\w.-])%s(?![\w-])" % re.escape(key[1])
        if re.search(r"`[^`\n]*%s[^`\n]*`" % token if re.fullmatch(r"\w+", key[1]) else token, sentence, re.I):
            return True
    return False


def _head(sentence, tail):
    """`sentence` up to the end of the phrase: what is left once `tail`, the text after the phrase, is cut off."""
    return sentence[:len(sentence) - len(tail.rstrip())]


def _names_a_call(text, writer_counts=False):
    """True when `text` holds a check (CANNOT_CHECK_RE) that names a call. A bare check word (CANNOT_CHECK_WORD_RE) counts
    only when it lies outside a claim phrase ("blocked from" is the claim, not its check) and _clause.check_word_counts
    accepts it: the writer as its subject names no call ("I tried"), unless `writer_counts`, and a speech word needs a
    tool, hook, check, command or remote as its subject. The one home of that test."""
    phrases = [hit.span() for hit in CANNOT_RE.finditer(_mask(text))]
    return any(not CANNOT_CHECK_WORD_RE.fullmatch(m.group()) or (
        _clause.check_word_counts(text[:m.start()], m.group(), writer_counts)
        and not any(a <= m.start() < b for a, b in phrases))
        for m in CANNOT_CHECK_RE.finditer(text))


def _names_check(sentence, tail):
    """True when `sentence` names its check (CANNOT_CHECK_RE), read with its emphasis marks removed (_strip_emphasis). In
    `tail`, the text after the phrase, any form counts but a bare check word that the phrase holds or that a speech word
    with no tool, hook, check, command or remote as its subject makes. Before the phrase, a bare check word counts only when the
    writer is not its subject (_names_a_call)."""
    head = _strip_emphasis(_head(sentence, tail))[0]
    return _names_a_call(_strip_emphasis(tail)[0], writer_counts=True) or _names_a_call(head)


# The act a sentence's own words are about: the verb of a table act, a PR act's verb only beside the PR word. github-reach
# has no prose word: a sentence about GitHub is about every act.
CANNOT_PROSE_ACTS = (
    ("push", re.compile(r"\bpush(?:ed|es|ing)?\b", re.I)),
    ("pr-merge", re.compile(r"\bmerg(?:e|es|ed|ing)\b", re.I)),
    ("pr-open", re.compile(r"\b(?:open(?:ed|ing|s)?|creat(?:e|es|ed|ing)|rais(?:e|es|ed|ing)|fil(?:e|es|ed|ing)|submit\w*)\b", re.I)),
    ("pr-edit", re.compile(r"\b(?:clos(?:e|es|ed|ing)|comment\w*|edit\w*|updat(?:e|es|ed|ing)|mark(?:s|ed|ing)?)\b", re.I)),
)


def _prose_acts(prose):
    """The table acts the words of `prose` (a sentence without its code spans) are about; a PR act needs the PR word."""
    prose = _clause.unopen(prose)  # "PR 12 is open" is a state, so it opens no PR
    return {act for act, rx in CANNOT_PROSE_ACTS
            if rx.search(prose) and (act in ("push", "pr-merge") or CANNOT_PR_RE.search(prose))}


def _prior_names_check(prior, act):
    """True when the sentence before a claim of `act` names a check of that act: a check word (CANNOT_CHECK_RE) outside
    code spans, in a sentence that is not about another act alone ("The push failed." checks no merge), or a code span that
    names a route of `act`, in a sentence that names no route of another act. A route of another act ("`gh pr create`
    returned 403") is the check of that act, and a span of another command ("`ls` printed a list") names no check."""
    prior = _strip_emphasis(prior)[0]
    acts = _text_acts(prior)
    if acts and act not in acts:
        return False
    prose = CODE_SPAN.sub(" ", prior)
    about = _prose_acts(prose)
    return _names_a_call(prose) and (not about or act in about or act == GITHUB_REACH) or any(
        act in _text_acts(span.group(2)) for span in CODE_SPAN.finditer(prior))


def cannot_problem(records, text, refused=()):
    """The refusal for reply sentences that claim a table act cannot be done, else ''. `records` are those after the last
    human message. A sentence passes when a failed try of its act sits in them (failed_tries) or it carries a cite
    (_cited), and it names its check (_names_check, or a reason when a failed try sits in the turn: _gives_reason). A
    sentence in the past tense (could not) whose failed try a later call of the same act and target cancelled reports a past
    failure and is let pass; a present claim (cannot) after that later success still blocks.
    A sentence with no try is listed under the no-try reason, one with a try and no check under the no-check reason. The remedy names no act (git-remedy-never-names-target)."""
    claims = cannot_lines(text)
    if not claims:
        return ""
    if guard is None:
        _load_guard()
    if guard is None:  # a guard that cannot read cannot accuse
        print("cannot-claim guard: UNKNOWN, the transcript parser did not load, so the claims went unchecked.",
              file=sys.stderr)
        return ""
    recovered = set()
    tries = failed_tries(records, refused, recovered)
    no_try, no_check = [], []
    for sentence, act, _, past, prior, following, tail in claims:
        backed = _backed(tries, act, sentence)
        if past and not tries.get(act) and act in recovered:  # every failed try of the act was later cancelled
            continue
        if not backed and not _cited(sentence, refused, act):
            if sentence not in no_try:
                no_try.append(sentence)
        elif not (_names_check(sentence, tail) or backed and (_prior_names_check(prior, act)
                                                                  or _gives_reason(_head(sentence, tail), tail, following))) \
                and sentence not in no_check:
            no_check.append(sentence)
    return " ".join(head + "".join("\n- " + line for line in lines)
                    for head, lines in ((CANNOT_NO_TRY, no_try), (CANNOT_NO_CHECK, no_check)) if lines)


# Review-record check: a lane's round PASS claim needs a review record for the PR's live head. See the module docstring.
REVIEW_TRIGGER_RE = re.compile(r"(?i:\bround\s+\d+\b|\breviewer\b)")
REVIEW_PASS_RE = re.compile(r"\bPASS(?:ED)?\b")
# A PASS that a negator governs: the negator, at most one word, then PASS.
REVIEW_NEGATED_RE = re.compile(r"(?i:(?:\b(?:not|never|nor|cannot)|n't)\s+(?:\w+\s+)?)PASS(?:ED)?\b")
# A clause that puts its PASS in the past: stale, replaced, or "was ... before/earlier".
REVIEW_HISTORY_RE = re.compile(
    r"(?i:\b(?:stale|outdated|superseded|invalidated|previously|formerly|no longer)\b"
    r"|\b(?:was|were)\s+(?:\w+\s+){0,2}(?:before|prior|earlier)\b)")
REVIEW_CLAUSE_SPLIT_RE = re.compile(r"[,;]|--")
REVIEW_PR_RE = re.compile(r"(?<![\w&])#(\d+)\b|\bPRs?\s*#?(\d+)\b|/pull/(\d+)\b", re.I)
REVIEW_READ_TIMEOUT = 30  # seconds for one gh read
REVIEW_CHECK_BUDGET = 70  # seconds for the whole review check of one reply, under the Stop hook's 80 s timeout (settings.json); the question and relay checks run outside this budget
REVIEW_NO_PR = (
    "Review-record guard: a line of this reply claims a review PASS but names no pull request. Name it as #<n> on that "
    "line, and give it a review record for its live head (`merge <pr> --review-record ...`, then post the record on the PR)."
)
REVIEW_NO_RECORD = (
    "Review-record guard: this reply claims a review PASS for PR #%d, and that PR has no review record for its live head. "
    "Remedy: have the reviewer run `merge %d --review-record --head <the head the reviewer read> --kind <kind> --guard "
    "<yes|no> --round <N:ROLE:MODEL:VERDICT>`, post the record it prints as a comment on PR #%d, then report again."
)
# The record for the live head is posted, but merge's review_state reads it open or held: name that state and its why.
REVIEW_NOT_DONE = (
    "Review-record guard: this reply claims a review PASS for PR #%d, but merge reads its review record for the live head "
    "as %s: %s. Review is not done, so no PASS claim yet. Report the review state as it stands."
)
REVIEW_UNPARSED = (
    "Review-record guard: this reply claims a review PASS for PR #%d, and the newest review record on that PR does not parse, "
    "so merge reads no record from it.%s Remedy: have the reviewer run `merge %d --review-record --head <the head the reviewer "
    "read> --kind <kind> --guard <yes|no> --round <N:ROLE:MODEL:VERDICT>`, post the record it prints as a new comment on "
    "PR #%d, then report again."
)
REVIEW_UNPARSED_CI = (" Cause: the CI line must be the last line before `---`, and nothing may follow it; a line after the CI "
                      "line makes the record unreadable.")


def review_claims(text):
    """The reply lines that claim a review PASS, outside fences: [(line, PR numbers on it)]. Inline code spans are read as
    their content. A negated PASS, and a PASS whose clause places it in the past, claim nothing."""
    claims, fence = [], ""
    for line in text.splitlines():
        body = QUOTE_PREFIX.sub("", line, count=1).strip()
        marker = body[:3] if body[:3] in ("```", "~~~") else ""
        if marker and (not fence or marker == fence):
            fence = "" if fence else marker
            continue
        if fence:
            continue
        plain = CODE_SPAN.sub(lambda m: m.group(2), body)
        if not REVIEW_TRIGGER_RE.search(plain):
            continue
        if not any(REVIEW_PASS_RE.search(REVIEW_NEGATED_RE.sub(" ", clause)) and not REVIEW_HISTORY_RE.search(clause)
                   for clause in REVIEW_CLAUSE_SPLIT_RE.split(plain)):
            continue
        numbers = [int(g) for m in REVIEW_PR_RE.finditer(plain) for g in m.groups() if g]
        claims.append((body, list(dict.fromkeys(numbers))))
    return claims


def _time_left(end):
    """Seconds left of the whole-check budget that ends at `end`, or raises: no time left is a read that could not run."""
    import time
    left = end - time.monotonic()
    if left <= 0:
        raise TimeoutError("the review check's time budget is spent")
    return left


def _gh_json(args, cwd, end):
    """The parsed JSON of one `gh api` read, or raises: a failed or unparseable read is never an answer. The read ends at REVIEW_READ_TIMEOUT or
    at `end`, the end of the whole check's budget, whichever is first."""
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
    run = _nowindow.run(["gh", "api", *args], cwd=cwd or None, capture_output=True, text=True,
                        timeout=min(REVIEW_READ_TIMEOUT, _time_left(end)))
    if run.returncode:
        raise RuntimeError("gh api exited %d" % run.returncode)
    return json.loads(run.stdout)


def _newest_record(n, comments, merge_mod):
    """(parsed record, body) of the newest review record comment of `comments` (oldest first). No marked comment is
    (None, None); a marked comment that does not parse is (None, its body), so the caller needs no second read."""
    bodies = [c.get("body") or "" for c in comments if isinstance(c, dict)]
    marked = [b for b in bodies if b.splitlines()[:1] == [merge_mod.REVIEW_MARKER]]
    return (merge_mod.parse_review(marked[-1]), marked[-1]) if marked else (None, None)


def _text_after_ci_line(body, merge_mod):
    """True when non-blank text follows the last CI line before the first `---` line: the one cause named for an unparsed record."""
    lines = body.splitlines()
    if "---" in lines:
        lines = lines[:lines.index("---")]
    at = [i for i, line in enumerate(lines) if line == merge_mod.REVIEW_CI_LINE]
    return bool(at) and any(line.strip() for line in lines[at[-1] + 1:])


def review_record_problem(hook, text):
    """(refusal, note) for a lane reply that claims a review PASS. A reply with no claim, or a session that is not a lane,
    reads nothing. A claim with no PR is refused. Else two REST reads (the PR's live head, its issue comments); the newest
    review log must name the PR, and merge's live_review_state must call it done for the live head (_live_state). A read
    of the PR or its comments that could not run, or a merge tool that could not load, is a note with UNKNOWN, never a block.
    A clean-merge read that could not run keeps a stale record stale, so it blocks, with a note that says so."""
    claims = review_claims(text)
    if not claims:
        return "", ""
    import time
    end = time.monotonic() + REVIEW_CHECK_BUDGET  # one budget for every claimed PR and every read, so the hook ends under its timeout
    _hooks_on_path()
    from override import remote_session_id
    own_id = remote_session_id()
    if not own_id or not _own_lane_read(hook.get("transcript_path"), own_id)[0]:
        return "", ""
    unnamed = [c for c in claims if not c[1]]
    numbers = list(dict.fromkeys(n for _line, nums in claims for n in nums))
    reasons, notes = ([REVIEW_NO_PR] if unnamed else []), []
    for n in numbers:
        try:
            from guard_merge import merge_module  # the one home of the merge tool lookup (hooks/guard_merge.py)
            merge_mod = merge_module()
            if merge_mod is None:
                raise ImportError("merge/merge.py not found")
            cwd = hook.get("cwd")
            live = _gh_json(["repos/{owner}/{repo}/pulls/%d" % n], cwd, end)["head"]["sha"]
            pages = _gh_json(["repos/{owner}/{repo}/issues/%d/comments" % n, "-X", "GET", "-f", "per_page=100",
                              "--paginate", "--slurp"], cwd, end)
            comments = [c for page in pages for c in (page if isinstance(page, list) else [page])]
            rec, body = _newest_record(n, comments, merge_mod)
        except Exception as err:  # a read that could not run is UNKNOWN, never clear and never a block
            notes.append("Review-record guard: UNKNOWN, the check read nothing for PR #%d (%s)." % (n, type(err).__name__))
            continue
        if rec is None and body is not None:
            cause = REVIEW_UNPARSED_CI if _text_after_ci_line(body, merge_mod) else ""
            reasons.append(REVIEW_UNPARSED % (n, cause, n, n))
        elif not rec or rec["n"] != n:
            reasons.append(REVIEW_NO_RECORD % (n, n, n))
        else:
            state, why = _live_state(merge_mod, rec, live, cwd, end)
            if state in ("open", "held"):
                reasons.append(REVIEW_NOT_DONE % (n, state, why))
            elif state != "done":
                reasons.append(REVIEW_NO_RECORD % (n, n, n))
            if getattr(merge_mod, "REVIEW_SURVIVAL_UNKNOWN", None) and merge_mod.REVIEW_SURVIVAL_UNKNOWN in why:
                notes.append("Review-record guard: PR #%d reads stale: %s." % (n, why))
    return " ".join(reasons), " ".join(notes)


def _live_state(merge_mod, rec, live, cwd, end):
    """(state, why) of `rec` for the live head, from merge/merge.py live_review_state: the one read `merge --reviewed` makes, so the guard and
    the list agree on a record that survives clean merges of main. Its reads share the time left of the whole check's budget (`end`). Any error reads as stale, so
    a record this check cannot prove done still blocks, as a stale record did before the clean-merge read."""
    try:
        with merge_mod.shared_deadline(_time_left(end)):
            host = merge_mod.Host(cwd=cwd or None)
            return merge_mod.live_review_state(host, rec, live, host.base)  # a fresh Host: its base is main, as `merge --reviewed` reads it
    except Exception as err:  # never a pass: the record is not proven done
        return "stale", "%s: %s" % (getattr(merge_mod, "REVIEW_SURVIVAL_UNKNOWN", "the clean-merge read is unknown"), type(err).__name__)


def refusal_reason(tools, hold=""):
    """The refusal for refused tools the reply has not raised, and for the triage hold's entries, or ''."""
    held = hold_reason(hold) if hold else ""
    if not tools:
        return held
    names = ", ".join("`%s`" % tool for tool in tools)
    return (held + " " if held else "") + owner_line(
        "Refusal guard (decision refusals-reach-the-owner)",
        "the auto-mode classifier refused %s this session, and the reply does not raise it with the owner. "
        "A refused tool clears when the reply names it in backticks under Input Needed, "
        "or writes \"`<tool_name>`: refusal was right\". "
        "An MCP tool counts by its full name, with or without backticks" % names)


def _marker_path(hook):
    _hooks_on_path()
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
        models = done_models_problem(text, spawned, spawn_models(records))
        if models:
            reasons.append(MODELS_REASON % models)
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
# Cost: one git process and one Sonnet call (60 s) on a Stop whose reply asks something; none on any other Stop.
RELAY_RULE_REASON = owner_line("Past-ruling guard (rule past-ruling)", "%s")
UNVETTED_REASON = owner_line(
    "Unvetted guard (rule past-ruling)",
    "a question to the owner went out without the past-ruling check, which could not run (%s)")
KEYS_REASON = owner_line(
    "Question-keys guard (rule question-keys)",
    "two questions to the owner use the option key(s) %s, so his answer could mean either")
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
        _hooks_on_path()
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
    _hooks_on_path()
    import question_form  # the one home of the Unvetted line
    # An Unvetted marker after the question's own sentence, on its line, goes on a line of its own.
    questions = [UNVETTED_AFTER_SENTENCE.sub(r"\1\n", q) for q in questions]
    unvetted = [line.strip() for line in text.splitlines() if question_form.UNVETTED_LINE.match(line)]
    return "\n".join(questions + [u for u in unvetted if u not in questions])[-ASK_TEXT_MAX:]


def cannot_run(asked, why):
    """The Unvetted refusal for a check that could not run, or '' when the asked text carries its own
    `Unvetted:` line. The marker is read only here, so it never skips a check that can run."""
    _hooks_on_path()
    import question_form
    return "" if question_form.has_unvetted(asked) else UNVETTED_REASON % why


def past_ruling_problem(asked, cwd):
    """The refusal text for asked text that a past ruling settles, or that could not be checked, else ''."""
    _hooks_on_path()
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
    if session_wording(reason):
        # The judge's reason holds an order to the session. The owner reads it in chat, so only the ruling id stays.
        cited = [i for i in question_form.candidate_ids(candidates) if i in reason or i.split("/", 1)[-1] in reason]
        reason = "a past ruling settles this (%s)." % ", ".join(cited[:3]) if cited else "a past ruling settles this."
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
    _hooks_on_path()
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


HOLD_TIER = "triage"
HOLD_REASON = owner_line(
    "Triage hold (decision session-tiers)",
    "the newest roadmap build prints stalled step lines for %s, and the reply does not name each one under "
    "Input Needed")
# A Bash command that runs the roadmap build: python, its flags, then a path that ends in build.py. A quoted or
# piped mention (cat build.py, grep 'python3 build.py') is no run.
BUILD_CALL_RE = re.compile(r"(?:^|[\s;&|(])python[\d.]*\s+(?:-\S+\s+)*(?:\S*/)?build\.py(?=[\s;&|)]|$)")


def _roadmap_build_prefix():
    """build.STALLED_LINE, the one emitter's line prefix (skills/roadmap/build.py), loaded only when a build ran."""
    import importlib.util
    path = os.path.join(HERE, "..", "skills", "roadmap", "build.py")
    spec = importlib.util.spec_from_file_location("roadmap_build_for_hold", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    spec.loader.exec_module(module)
    return module.STALLED_LINE


def _result_text(content):
    if isinstance(content, list):
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content if isinstance(content, str) else ""


# The verdict line bin/verdict prints for a run: `PASS|FAIL|SKIP <cmd> ... log=<path>`.
VERDICT_LOG_RE = re.compile(r"^(?:PASS|FAIL|SKIP) .* log=(\S+)\s*$", re.M)
VERDICT_RUN_HEADER = "=== verdict run "


def _verdict_log_text(path):
    """The last run's text in the verdict log at `path` (a log can hold several runs, each under a header line),
    or None when the file is missing or unreadable."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except Exception:
        return None
    cut = text.rfind(VERDICT_RUN_HEADER)
    return text if cut < 0 else text[cut:]


def stalled_entries(records):
    """The entries ("<step id>" or "item <n>") of the newest roadmap build output in `records`: each line
    `<STALLED_LINE>: <id> (...)` or `<STALLED_LINE>: item <n> (...)`. An unknown line is no entry. A newer build
    that prints none leaves none. Cost: no process, and the build module loads only when a build ran."""
    runs, text = set(), None
    for rec in records:
        if rec.get("isSidechain"):
            continue
        for use in tool_uses(rec):
            inp = use.get("input")
            if use.get("name") == "Bash" and isinstance(inp, dict) and BUILD_CALL_RE.search(str(inp.get("command", ""))):
                runs.add(use.get("id"))
        for result in tool_results(rec):
            if result.get("tool_use_id") in runs:
                shown = _result_text(result.get("content"))
                logged = VERDICT_LOG_RE.search(shown)
                if logged:  # a run through verdict shows failure lines only; its log holds the build's own lines
                    shown = _verdict_log_text(logged.group(1))
                    if shown is None:
                        continue  # a missing or unreadable log reads as no entries for this run; the older ones stand
                text = shown
    if not text:
        return []
    line = re.compile(r"^%s: (?:item (\d+)|(?!unknown )([^\s()]+)) \(" % re.escape(_roadmap_build_prefix()), re.M)
    return ["item " + n if n else step for n, step in line.findall(text)]


def _names_every(section, entries):
    for entry in entries:
        item = re.fullmatch(r"item (\d+)", entry)
        pattern = r"(?<![\w-])item\s+%s(?!\d)" % item.group(1) if item else r"(?<![\w-])%s(?![\w-])" % re.escape(entry)
        if not re.search(pattern, section, re.I if item else 0):
            return False
    return True


def triage_hold(hook, records, active):
    """The entries, joined, when this is a triage session whose newest roadmap build prints a stalled entry, else ''.
    A Stop after a refusal is released when Input Needed names every entry. An owner override lifts the hold, and a
    one-act override is spent here, after every other release has been ruled out. Fails open on any error."""
    try:
        entries = stalled_entries(records)
        if not entries:
            return ""
        _hooks_on_path()
        from guard_merge import _own_tier_proved
        if not _own_tier_proved(hook.get("transcript_path"), HOLD_TIER):
            return ""
        if active and _names_every(input_needed_section(last_reply(hook)), entries):
            return ""
        import override
        if override.take(hook.get("session_id"), None, override.now()) in override.LIFTS:
            return ""
        return ", ".join(entries)
    except Exception as exc:
        print("triage hold failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return ""


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    if not isinstance(hook, dict):
        return
    if hook.get("hook_event_name") != "Stop":
        return
    path = hook.get("transcript_path")
    hold = ""
    active = bool(hook.get("stop_hook_active"))
    records, read_failed = [], False
    if path and os.path.exists(path):
        try:
            records = read_transcript(path)  # the one read of a plain Stop: the hold and the checks below share it
        except Exception:
            read_failed = True
        try:
            hold = triage_hold(hook, records, active)
        except Exception:
            pass
    if active:
        pending_refusals(hook, last_reply(hook))  # clears what the rewrite names; never blocks on a refusal
        reasons = rewrite_problems(hook)
        reasons += rewrite_relay(hook)
        if hold and not reasons:
            print(json.dumps({"decision": "block", "reason": hold_reason(hold)}))
            return
        if hold:
            reasons.insert(0, hold_reason(hold))
        if reasons:
            print(json.dumps({"decision": "block", "reason": " ".join(reasons) + " (rule reports-order-of-labels)"}))
        return
    # A marker left by a rewrite that never ran must not reach a later turn: only the Stop
    # straight after a missing-report block may consume one.
    try:
        os.remove(_marker_path(hook))
    except Exception:
        pass

    # Route-row flags ride in the systemMessage of whichever line this Stop prints, and never change its decision.
    # The refusals file is read for them before pending_refusals settles it.
    route = refusal_route_flags(hook)

    def finish(payload):
        if route:
            payload = dict(payload or {})
            payload["systemMessage"] = " ".join(filter(None, [payload.get("systemMessage"), *route]))
        if payload:
            print(json.dumps(payload))

    # The hand-off cite reads the refusals file before pending_refusals settles it away.
    reply = last_reply(hook)  # one read of the reply for the hand-off cite, the refusals and the report checks
    hand_off, hand_note = "", ""
    try:
        _hooks_on_path()
        hand_off, hand_note = hand_off_problem(hook, reply)
    except Exception as err:  # a read that could not run is UNKNOWN, never clear
        hand_note = "Hand-off guard: UNKNOWN, the check did not run (%s)." % type(err).__name__

    # The cannot-claim check reads the refusals file here too, and only when a line claims. A read that fails skips it.
    cannot_refused = ()
    try:
        if cannot_lines(reply):
            cannot_refused = refused_tools(hook)
    except Exception as exc:
        cannot_refused = None
        print("cannot-claim guard: UNKNOWN, the check did not run (%s), so the claims went unchecked."
              % type(exc).__name__, file=sys.stderr)

    # Every Stop, landed or not, settles the refusals file; the reason joins whichever block follows.
    pending = pending_refusals(hook, reply)
    refusal = refusal_reason(pending, hold)  # the triage hold joins the refusals

    def stop_for_refusal():
        finish({"decision": "block", "reason": refusal} if refusal else None)

    if not path or not os.path.exists(path):
        return stop_for_refusal()

    if read_failed:
        return stop_for_refusal()

    last_human_idx = None
    for i, rec in enumerate(records):
        if is_last_human(rec):
            last_human_idx = i

    text = reply
    # The pick check reads the turn after the last incoming message, a peer's included (a lane's input),
    # and runs whether or not the transcript holds a human record. Landing and the report's shape still
    # anchor on the last human message.
    incoming = last_incoming_index(records)
    turn = records if incoming is None else records[incoming + 1:]
    after = [] if last_human_idx is None else records[last_human_idx + 1:]
    route += success_route_flags(hook, after)
    note = ""
    pick_reason = ""
    try:
        pick_reason, note = question_problem(records, turn, text, hook)
    except Exception:
        pass
    review, review_note = "", ""
    try:
        review, review_note = review_record_problem(hook, text)
    except Exception as err:  # a check that could not run is UNKNOWN, never silence and never a block
        review_note = "Review-record guard: UNKNOWN, the check did not run (%s)." % type(err).__name__
    note = " ".join(filter(None, [note, hand_note, review_note]))
    relay = []
    if last_human_idx is not None:  # a transcript with no human message never ran the relay and answered checks
        relay = relay_reasons(after, text, hook.get("cwd"))
        try:
            relay.append(answered_problem(text))  # one block per turn, joined with any other reason, landed or not
        except Exception:
            pass
    cannot = ""
    if last_human_idx is not None and cannot_refused is not None:
        try:
            # A try backs a claim only in this turn: after the last message, a peer's included. A peer's reply to a send of
            # this turn is an ack and starts no turn, as in the question check.
            acks = {sender: {sender} | PARENT_TARGETS for sender in map(peer_sender, records) if sender}
            idx = last_incoming_index(records, acks)
            ack_turn = records if idx is None else records[idx + 1:]
            cannot = cannot_problem(ack_turn, text, cannot_refused)
        except Exception as exc:
            print("cannot-claim guard: UNKNOWN, the check did not run (%s), so the claims went unchecked."
                  % type(exc).__name__, file=sys.stderr)
    if last_human_idx is None or not turn_landed(after):
        # An unlanded turn is judged on the question check and the Departs from check alone. An error in
        # either fails open on its own: the Departs from check never drops the question refusal.
        pick = [pick_reason]
        try:
            pick.append(departs_problem(text))
        except Exception:
            pass
        pick += relay
        pick.append(hand_off)
        pick.append(cannot)
        pick.append(review)
        try:
            if report_shape_ok(text):
                pick.append(recovered_problem(records, text))
        except Exception:
            pass
        try:
            pick.append(refusal)
            pick = [r for r in pick if r]
            if pick:
                reason = " ".join(pick) + " (rule reports-order-of-labels)"
                finish({"decision": "block", "reason": reason})
            else:
                finish({"systemMessage": note} if note else None)
        except Exception:
            pass
        return

    shape_ok = report_shape_ok(text)
    reasons = [] if shape_ok else [BLOCK_REASON]
    item = done_format_problem(text) if shape_ok else ""
    if item:
        reasons.append(owner_line(
            "Report-shape guard",
            "a Done line does not say BUILT, RECORDED or OTHER, or says BUILT or RECORDED with no PR or commit: "
            + repr(item)))
    spawned = spawn_models(after)
    models = done_models_problem(text, spawned, spawn_models(records)) if shape_ok else ""
    if models:
        reasons.append(MODELS_REASON % models)
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
    if shape_ok:
        try:
            mistake = mistake_problem(text)
            if mistake:
                reasons.append(mistake)
        except Exception as exc:
            print("mistake check failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
    reasons += [r for r in relay if r]
    if hand_off:
        reasons.append(hand_off)
    if cannot:
        reasons.append(cannot)
    if review:
        reasons.append(review)
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
        reasons.append(owner_line("Cite-gloss guard (rule speak-cite-id-plus-gloss)",
                                  "%r is a record id with no short gloss" % cite))
    if refusal:
        reasons.append(refusal)
    if reasons:
        reason = " ".join(reasons) + " (rule reports-order-of-labels)"
        if not shape_ok:
            write_marker(hook, last_human_idx)
        finish({"decision": "block", "reason": reason})
    else:
        finish({"systemMessage": note} if note else None)


if __name__ == "__main__":
    main()
