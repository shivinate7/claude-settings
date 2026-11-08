#!/usr/bin/env python3
"""The one question form and the one guard for both places a session asks the owner a question: the
chat question box (AskUserQuestion) and a write of a waiting-page item (ArtifactData). Decision
question-form holds the ruling; rule `style-question-form` holds the text.

    chat_hit(tool_input) -> (rule, matched)   an AskUserQuestion input; judges each question with 2+ options
    item_hit(op, entry, cwd) -> (rule, matched)   one waiting-page write: set, update or str_replace

("", "") is a pass. hooks/call_judge.py calls chat_hit and page_item_hit; hooks/guard.py data_tool_hit calls
page_item_hit, which filters the ArtifactData writes by collection and url and then calls item_hit; a write to another page gets only the check for an option keyed none. Nothing here writes a file. The only process it starts is the one git read of past_rulings, for a caller that makes a model call anyway.

    past_rulings(text, repo_root) -> (candidates, unknown)   the decision, debt and step rulings the judge reads
    key_overlap(reply, earlier)   -> clashing option keys     lint/report_guard.py rule question-keys

THE FORM. A decision on the page (in `context`), or a chat question with 2+ options (in `question`):

    Goal: <the goal, in the owner's terms>
    Problem (<stake>): <the problem in one plain sentence, and why it needs his word>
    Based on (<kind>): <one premise>                                  one to three lines
    Departs from: <what on main> — <what changes>                     after the form; every such line must be valid

<stake> is one of OWNER_STAKES. A stood pick (`stands: true`) may write `Problem: <text>` with no stake.
<kind> is one of PREMISE_KINDS. Each option states its gain and its loss: page `gain` and `lose` fields;
chat `Gain:` and `Lose:` in the option's description. Only a line at a line start counts.

THE OLDER RULES keep their ids and run first, in this order, then the form:
`item-field-rendered` (a field the page draws), `port-question`, `uniform-pick`, `press-link`, `command-in-item`,
`gh-login-switch`, `task-names-check`, `task-why-cited` (page items), then the form. A missing Goal, Problem or Based on line, a
Based on count outside 1-3, a kind outside
PREMISE_KINDS and an option with no gain or no loss refuse as `question-form`, and so does a Goal, Problem or
Based on line whose text is only an angle-bracket placeholder (the template copied; `<Button>` inside real
text passes). A Problem line that is
bare, or whose stake is outside OWNER_STAKES, refuses as `owner-judge`. When all of those pass, a missing
or empty `Departs from:` line (a bullet or bold label is read), a line with no separator (" — ", an unspaced
"—", " - " or " -- ") or an empty or placeholder side, and a change side whose first clause (before ";") says
nothing changes (a restatement of main) refuse as `question-departs`: the rule building-port-keeps-behaviour,
in decision port-keeps-behaviour. departs_hit is its one predicate; lint/report_guard.py calls it too.
The page writer's last two rules run after the form: `option-letter-keys` (an option's key is its
position's letter, and a label that opens with a letter tag names that letter) and `rework-off-page` (an open item never says it is being reworked).

An update is judged only for the fields it carries. A closed item passes the form: it asks the owner
nothing, and the chat-answer flow writes one. A str_replace on `context` that removes a form line is
refused.
"""
import functools
import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from precompact_handoff import PREMISE_KINDS  # noqa: E402  the one home of the premise kinds
from shared_names import GH_DEFAULT_LOGIN, GH_FALLBACK_LOGIN  # noqa: E402  the one home of the gh logins

PASS = ("", "")
FORM_RULE, STAKE_RULE = "question-form", "owner-judge"

# docs/decisions/owner-judge-test.md, rule `owner-judge`, built against a named incident (incident in
# the record): a decision about CI internals reached the owner, who had no stake in it. The Problem
# line names the stake, one of these.
OWNER_STAKES = ("goal", "money", "risk", "rule", "cannot undo")

# docs/decisions/question-form.md, rule `question-form`, built against a likely risk and a named
# incident (item 92, in the record): a decision reached the owner with no Problem line, no Based on
# line, and a widening option not marked.
_STAKES = "|".join(re.escape(s) for s in OWNER_STAKES)
GOAL_LINE = re.compile(r"^[ \t]*Goal:[ \t]*\S", re.I | re.M)
PROBLEM_LABEL = re.compile(r"^[ \t]*Problem\b", re.I | re.M)
PROBLEM_LINE = re.compile(r"^[ \t]*Problem[ \t]*\((?:%s)\):[ \t]*\S" % _STAKES, re.I | re.M)
PROBLEM_STOOD_LINE = re.compile(r"^[ \t]*Problem(?:[ \t]*\((?:%s)\))?:[ \t]*\S" % _STAKES, re.I | re.M)
# A Based on line starts `Based on (` or `Based on:`; prose that starts "Based on the log" is not one.
BASED_LABEL = re.compile(r"^[ \t]*Based on[ \t]*[(:]", re.I | re.M)
BASED_LINE = re.compile(r"^[ \t]*Based on[ \t]*\(([^()\n]*)\):[ \t]*\S", re.I | re.M)
GAIN_TEXT = re.compile(r"\bGain:[ \t]*(?!Lose:)\S", re.I)
LOSE_TEXT = re.compile(r"\bLose:[ \t]*\S", re.I)
BASED_MAX = 3
# A side or a line's text that is only an angle-bracket placeholder is the template copied verbatim. The one
# home of that check: the Goal, Problem and Based on lines and both sides of a Departs from line call it.
PLACEHOLDER_SIDE = re.compile(r"<[^<>\n]*>")
# The text after the label on each form line, for the placeholder check. Real text that holds angle
# brackets, such as `<Button>`, is no placeholder: only the whole text must be one.
FORM_LINE_TEXT = (("Goal", re.compile(r"^[ \t]*Goal:[ \t]*([^\n]*)", re.I | re.M)),
                  ("Problem", re.compile(r"^[ \t]*Problem(?:[ \t]*\([^()\n]*\))?:[ \t]*([^\n]*)", re.I | re.M)),
                  ("Based on", re.compile(r"^[ \t]*Based on[ \t]*\([^()\n]*\):[ \t]*([^\n]*)", re.I | re.M)))


def is_placeholder(text) -> bool:
    return bool(PLACEHOLDER_SIDE.fullmatch(str(text).strip()))


def placeholder_form_hit(text):
    """(rule, matched) for the first Goal, Problem or Based on line whose text is only a placeholder."""
    for label, rx in FORM_LINE_TEXT:
        if any(is_placeholder(value) for value in rx.findall(text)):
            return FORM_RULE, "%s line that is only a placeholder: write the real text" % label
    return PASS

FORM_REASON = ("A question to the owner states the form, in this order: a line \"Goal: <the goal, in his "
               "terms>\", a line \"Problem (<stake>): <the problem in one plain sentence, and why it needs "
               "his word>\" where stake is one of %s, and one to three lines \"Based on (<kind>): <one "
               "premise>\" where kind is one of %s. Each option states its gain and its loss."
               % (", ".join(OWNER_STAKES), ", ".join(PREMISE_KINDS)))
PAGE_FORM_REASON = FORM_REASON + (" On the waiting page the lines go in `context`, and each option has a "
                                  "non-empty `gain` and `lose`. If no stake fits, take your own pick and set "
                                  "stands: true.")
CHAT_FORM_REASON = FORM_REASON + (" In the question box the lines go in the question text, and each "
                                  "option's description holds \"Gain: <text>\" and \"Lose: <text>\".")
STAKE_REASON = ("A decision is the owner's only when he can judge it. Write the Problem line as "
                "\"Problem (<stake>): <the problem, and why it needs his word>\", where stake is one of %s. "
                "A stood pick may write \"Problem: <text>\". If no stake fits, take your own pick and set "
                "stands: true. (decision owner-judge-test, a decision reaches the owner only when he can judge it)"
                % ", ".join(OWNER_STAKES))


def _lines_hit(text, stands=False):
    """(rule, matched) when `text` lacks a form line or holds a malformed one. The first miss, in the
    order of the form."""
    if not GOAL_LINE.search(text):
        return FORM_RULE, "no Goal line"
    state = _problem_state(text, stands)
    if state == "missing":
        return FORM_RULE, "no Problem line"
    if state == "malformed":
        return STAKE_RULE, "Problem line with no stake, or a stake outside the set"
    hit = _based_hit(text)
    if hit[0]:
        return hit
    goal, problem, based = (rx.search(text).start() for rx in (GOAL_LINE, PROBLEM_LABEL, BASED_LABEL))
    if not goal < problem < based:
        return FORM_RULE, "lines out of order: Goal, then Problem, then Based on"
    return placeholder_form_hit(text)


def _problem_state(text, stands):
    """ok, malformed (a Problem line starts a line but is bare or names a stake outside the set), or missing."""
    if (PROBLEM_STOOD_LINE if stands else PROBLEM_LINE).search(text):
        return "ok"
    return "malformed" if PROBLEM_LABEL.search(text) else "missing"


def _based_hit(text):
    labels = BASED_LABEL.findall(text)
    if not labels:
        return FORM_RULE, "no Based on line"
    if len(labels) > BASED_MAX:
        return FORM_RULE, "%d Based on lines, one to %d allowed" % (len(labels), BASED_MAX)
    kinds = [m.group(1).strip().lower() for m in BASED_LINE.finditer(text)]
    if len(kinds) != len(labels) or any(k not in PREMISE_KINDS for k in kinds):
        return FORM_RULE, "Based on line with no kind, or a kind outside the premise kinds"
    return PASS


def _effects_hit(pairs):
    """(rule, matched) for the first option with no gain or no loss. `pairs` is (name, has_gain, has_lose)."""
    for name, has_gain, has_lose in pairs:
        if not has_gain:
            return FORM_RULE, "option %s has no gain" % name
        if not has_lose:
            return FORM_RULE, "option %s has no lose" % name
    return PASS


# ------------------------------------------------------------------ a question departs from main
#
# docs/decisions/port-keeps-behaviour.md, rule `question-departs`, built against a named incident
# (incident in the record): a lane's "departures" said "Opus above a role's row stays the
# existing ask", which restates decision agent-model-cap. A question to the owner that restates main is not a
# question (rule building-port-keeps-behaviour). Each line at a line start `Departs from: <what on main> —
# <what changes>` must hold both sides, and the change side must not say there is no change. This is the
# one predicate: the chat box, a page decision and the report's Input Needed pick all call it.
DEPARTS_RULE = "question-departs"
# The one pattern for a Departs from line: at a line start, with an optional bullet ("- ", "* ") and an
# optional bold label ("**Departs from:**"). Group 1 is the rest of the line; a CR from CRLF is no part of it.
DEPARTS_LINE = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?(?:\*\*)?Departs from(?:\*\*)?:(?:\*\*)?([^\n]*)", re.I | re.M)
# The separator: an em dash, spaced or not, or " - " or " -- ". The first one splits the line.
DEPARTS_SEPARATOR = re.compile(r"\s*\u2014\s*|\s+--?\s+")
# Whole words and phrases that say the change side restates main. "stay", "remain" and "kept" are not
# here: "Suspense cards stay in Suspense" is a port change that names where a thing goes.
NO_CHANGE = re.compile(r"(?<![\w/-])(?:none|nothing|n/a|no changes?|no difference|unchanged|stays|keeps|as today"
                       r"|as on main|as before|same as|identical to|already)(?![\w/-])", re.I)
# The new-thing change side, "adds <X>": group 1 is X.
PORT_NEW_THING = re.compile(r"adds\b\s*(.*\S)", re.I)
DEPARTS_REASON = ("A question to the owner says how the work departs from main, in a line that starts "
                  "\"Departs from: <what on main> \u2014 <what changes>\", with both sides filled and a change that "
                  "differs from main. If it is new, write \"Departs from: main \u2014 adds <X>\". If the change "
                  "only restates what main does, do not ask: act on main's behaviour.")
PAGE_DEPARTS_REASON = DEPARTS_REASON + " On the waiting page the line goes in `context`."
# The hint that departs_hit adds to the placeholder miss. A Stop refusal (lint/report_guard.py) shows the miss
# without it, since the owner reads that refusal (decision guard-remedy-not-to-owner).
PLACEHOLDER_HINT = ": write the real text"


def departs_sides(rest):
    """(main side, change side, whether a separator split it) of one Departs from line's text. The one parser."""
    parts = DEPARTS_SEPARATOR.split(rest, maxsplit=1)
    if len(parts) < 2:
        return rest.strip(), "", False
    return parts[0].strip(), parts[1].strip(), True


def departs_hit(text) -> str:
    """The miss reason when `text` lacks a valid Departs from line, else "". Every such line must hold a
    non-empty side on each side of the first separator (see DEPARTS_SEPARATOR), neither side only a
    placeholder, and no no-change word in the first clause of the change side: the part before its first
    ";", or the whole side with none. A word after the ";" says what the change does."""
    text = str(text or "")
    lines = DEPARTS_LINE.findall(text)
    if not lines:
        return "no Departs from line"
    for rest in lines:
        main, change, split = departs_sides(rest)
        if not split:
            return "Departs from line with no \u2014, - or -- separator between what is on main and what changes"
        if not main or not change:
            return "Departs from line with an empty side"
        added = PORT_NEW_THING.fullmatch(change)
        if is_placeholder(main) or is_placeholder(change) or (added and is_placeholder(added.group(1))):
            return "Departs from line with a side that is only a placeholder" + PLACEHOLDER_HINT
        word = NO_CHANGE.search(change.split(";", 1)[0])
        if word:
            return "Departs from line whose change side says no change (%r): it restates main" % word.group(0)
    return ""


# ------------------------------------------------------------------ a port question departs or is not asked
#
# docs/decisions/port-keeps-behaviour.md, rule `port-question`, built against a named incident
# (incident in the record): a waiting item about a port or redesign of an
# existing app carries a "Departs from:" line and never holds work, since the existing app answers
# the question. The item is read at the ArtifactData call that writes it.
PORT_WORD = re.compile(r"\b(?:ported|porting|port\s+of|port\s+to|ports\s+the|redesign(?:s|ed|ing)?"
                       r"|rewrite\s+of|rebuild\s+of)\b", re.I)
PORT_REASON = ("A question about a port or redesign of an existing app is asked only when the work "
               "departs from the app, and it never holds work. Add a line to context that starts "
               "\"Departs from: <file>:<symbol> — <what changes>\" (or \"Departs from: main — adds <X>\" "
               "for a new thing), leave out holds, or set port to false if this is not a port.")


# A port's Departs from line names the place on main as "<file>:<symbol>" (backticks around it are read, and
# a path may hold [id], (group) and @ for a Next.js or alias path), or says "main" for a new thing and then
# "adds <X>".
PORT_MAIN_SIDE = re.compile(r"[\w./@\[\]()-]+:(?!//)[\w.$-]+(?:\(\))?")


def port_departs_miss(text) -> str:
    """The miss reason when a port's Departs from line, any of them, is not a valid Departs from line (the
    one predicate, departs_hit: no placeholder or no-change side) or does not name `<file>:<symbol>` on main
    (or `main` with `adds <X>`). "" when each does. A text with no such line is judged elsewhere."""
    text = str(text or "")
    miss = departs_hit(text)
    if miss:
        return miss
    for rest in DEPARTS_LINE.findall(text):
        main, change, _ = departs_sides(rest)
        main = main.strip("`").strip()
        if main.lower() == "main":
            if PORT_NEW_THING.fullmatch(change):
                continue
        elif PORT_MAIN_SIDE.fullmatch(main):
            continue
        return "port item whose Departs from line names no <file>:<symbol> on main"
    return ""


def _item_text(data) -> str:
    return " ".join(str(data.get(k) or "") for k in ("title", "context", "holds"))


def port_item_hit(op: str, data) -> str:
    """The matched text when this write of a waiting item is a port question that skips the rule."""
    if not isinstance(data, dict) or ("kind" in data and data["kind"] not in ("decision", "task")):
        return ""
    if op == "set" and "kind" not in data:
        return ""
    if "port" in data:
        on_port = bool(data["port"])
    else:
        on_port = op == "set" and bool(PORT_WORD.search(_item_text(data)))
    if not on_port:
        return ""
    if data.get("holds"):
        return "port item with holds"
    if (op == "set" or "context" in data) and not DEPARTS_LINE.search(str(data.get("context") or "")):
        return "port item with no Departs from line"
    if op == "set" or "context" in data:
        return port_departs_miss(data.get("context"))
    return ""


def _write_data(entry, cwd=""):
    """The data of one write: `data`, else the JSON in `file_path`, a relative path read against the
    payload's `cwd` (the hook process's own cwd is not the session's). None when neither reads."""
    data = entry.get("data")
    path = entry.get("file_path")
    if data is None and isinstance(path, str) and path:
        try:
            with open(os.path.join(cwd, path) if cwd else path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
    return data


# ------------------------------------------------------------------ a pick never widens a shared tool
#
# docs/decisions/uniform-over-variants.md, rule `uniform-pick`, built against a named incident
# (incident in the record): a repo that differs from a shared format changes to match, so an
# option marked `widens: true` is never the item's `pick`, a str or any key in a list `pick`. In the
# chat box the mark is the words below in an option's label or description, and such an option's label
# never carries (Recommended). Read at the same ArtifactData call.
WIDENS_TEXT = "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo"
WIDENS_REASON = ("A pick never names an option that widens what a shared tool accepts: the owner ruled that "
                 "a repo changes to fit a shared tool, never the tool to fit a repo. Make the pick an option "
                 "where the repo changes to match the shared format, or leave pick out.")
CHAT_WIDENS_REASON = ("A recommended option never widens what a shared tool accepts: the owner ruled that a "
                      "repo changes to fit a shared tool, never the tool to fit a repo. Recommend an option "
                      "where the repo changes to match the shared format, and give the widening option no "
                      "(Recommended) label.")
# Older sessions still write these words in chat; the mark keeps refusing them. No card, rule text or
# reason carries them.
LEGACY_WIDENS_TEXT = "Goes against your uniform ruling (t18)"


def _words_pattern(text):
    # Any run of whitespace between words, so a reflowed or wrapped sentence still matches.
    return r"\s+".join(re.escape(w) for w in text.split())


WIDENS_MARK = re.compile("|".join(_words_pattern(t) for t in (WIDENS_TEXT, LEGACY_WIDENS_TEXT)), re.I)
RECOMMENDED = re.compile(r"\(Recommended\)", re.I)


WIDENS_KEY = "widens"  # the Python home of the mark's key; call_judge.WIDENING_RULE names it too, and skills/waiting-page/page.html reads the literal in JS


def widens_pick_hit(data) -> str:
    """The matched text when this write's `pick` (a str, or a list of keys) names an option it marks
    `widens: true`. An update that carries `pick` without `options` cannot see the stored options and passes."""
    if not isinstance(data, dict) or data.get("kind", "decision") != "decision":
        return ""
    options, pick = data.get("options"), data.get("pick")
    if isinstance(pick, str):
        pick = [pick]
    if not isinstance(pick, list) or not isinstance(options, list):
        return ""  # an absent or null pick picks nothing, so it never matches a keyless option
    keys = {p for p in pick if isinstance(p, str)}
    if any(isinstance(o, dict) and isinstance(o.get("key"), str) and o["key"] in keys
           and o.get(WIDENS_KEY) is True for o in options):
        return "pick names a widening option"
    return ""


# ------------------------------------------------------------------ the owner acts in place
#
# docs/decisions/act-in-place.md, rules `press-link` and `command-in-item`, built against a named
# incident (incident in the record): an option or step that asks the owner to press in a web app
# carries a link to that exact page, and a step never sends him to a file for a command. Both are
# read at the same ArtifactData call. In the chat box a link is an https:// url in the option's description.
PRESS_LINK_REASON = ("An option or step that asks the owner to press in a web app carries a link to "
                     "that exact page. Put links: [{label, url}] on that option (a task: on the item), "
                     "with the url of the page where he presses; for a pull request or an issue, the "
                     "url of that number.")
CHAT_PRESS_LINK_REASON = ("An option that asks the owner to press in a web app carries a link to that exact "
                          "page. Put an https:// url of the page where he presses in that option's "
                          "description; for a pull request or an issue, the url of that number.")
COMMAND_REASON = ("A step never sends the owner to a file for a command, and never holds one. Put the "
                  "command in the item's `command` field as {powershell, mac}: a PowerShell 5.1-safe "
                  "string (no &&, ||, <<, <<<, /dev/null or export) and a bash or zsh string for the Mac, both non-empty. "
                  "Say \"paste the command below\" in the step. A folder at a path ends with /. "
                  "No pipe into head, tail, grep, xargs, sed, awk, cut, wc, uniq, tr, tac, jq or less, "
                  "no NAME=value before a command, no [ ] test, no backslash line end.")
# A press: press, click, tap in any form; an imperative approve, merge, hit, turn on at the start of
# a clause, `you` allowed before it (a command to the owner, so "the PR merged" and "to merge"
# pass); mark ... ready with a PR or #N as its object, or with "on <ref>" after ready. "press on"
# is not a press, and neither is a press of the waiting page's own buttons or of this item on the
# page: it needs no link. "this item's" link may lead off the page, so it stays a press.
_CLAUSE = r"(?:^\s*|[.;:!?\n]\s*|,\s*|\b(?:and|then|or|please)\s+)(?:you\s+)?"
_PAGE_BUTTON = (r"(?!\s+(?:the\s+)?[\"'“‘]?(?:send|mark\s+done|take\s+my\s+pick)\b"
                r"|\s+this\s+item\b(?!['’]s))")
# An item or step number on the page, "item #47" or "step #2", is not a PR ref.
_REF = r"(?<!\bitem\s)(?<!\bstep\s)(?<!\bitem)(?<!\bstep)#\s*(\d+)"
PRESS_VERB = re.compile(r"\b(?:press(?!\s+on\b(?!\s+(?:the|this|that)\b))(?:es|ed|ing)?"
                        r"|click(?:s|ed|ing)?|tap(?:s|ped|ping)?)\b" + _PAGE_BUTTON +
                        r"|" + _CLAUSE + r"(?:approve|merge|hit|turn\s+(?:it\s+)?on)\b"
                        r"|\bmark(?:s|ed|ing)?\b[^.\n]*?(?:\bprs?\b|pull\s+requests?|" + _REF + r")[^.\n]*?\bready\b"
                        r"|\bmark(?:s|ed|ing)?\b[^.\n]*?\bready\b(?:\s+for\s+review)?\s+(?:on|in|at)\s+"
                        r"(?:the\s+)?(?:[\w./-]*" + _REF + r"|prs?\b|pull\s+requests?|github)",
                        re.I | re.M)
# A web page: GitHub, a PR, a pull request, a ref `home#374`, or Settings as a page name (capital S,
# or "settings page"; never settings.json or claude-settings).
WEB_MARKER = re.compile(r"github|\bpr\b|\bprs\b|pull\s+requests?|" + _REF +
                        r"|(?-i:(?<![\w-])Settings\b(?!\.\w))|\bsettings\s+page\b", re.I)
PRESS_REF = re.compile(_REF, re.I)
_FILE = (r"[\w./-]+\.(?:md|txt|sh|json|py|ps1|ya?ml|toml|html|log|csv)\b"
         r"|\b(?:plans|docs|notes)/[\w./-]+")
COMMAND_FILE = re.compile(_FILE, re.I)
# "the command in/from <file>", and "its command" with a file named, point at a file even with a
# `command` on the item. "run the command" and the like, with a file named, point at a file only when
# the item has no `command`: the step may mean the item's own block. "the command below" never does.
COMMAND_IN_FILE = re.compile(r"\bcommands?\s+(?:in|from|of|inside)\s+(?:the\s+|this\s+)?(?:file\s+)?(?:"
                             + _FILE + ")", re.I)
COMMAND_ITS = re.compile(r"\bits\s+commands?\b", re.I)
_RUN_VERB = r"\b(?:run|runs|copy|paste|execute|use|type)\b"
COMMAND_VERB = re.compile(_RUN_VERB + r"[^.\n]{0,40}\bcommands?\b(?!\s+below)"
                          r"|\bcommands?\s+(?:in|from|of|inside)\b", re.I)
# A task's `command` is {powershell, mac}, each a non-empty string, so the owner's own shell gets a
# block that runs in it. PowerShell 5.1 has none of the bash syntax below: the operators, the
# /dev/null path and an export statement, at a line start or after `;`. A line holding one fails there.
# Four more bash forms are read on the text with strings, comments and here-strings blanked out
# (_ps_bash_form), so PowerShell text that only looks like one passes: a pipe to a Unix-only program
# (PowerShell has `Sort-Object`, `Tee-Object` and `more`, so those are left out; `jq` and `less` are in), a leading `NAME=value`
# before a command (a `}` ends the value, so a hashtable's `b=2}` is none, unless it closes a `${...}` expansion, nested
# two deep as in `${A:-${B:-${C}}}`; each expansion holds no other `{` or `;`, so a failed read backtracks in linear time), a `[ ... ]` or `[[ ... ]]` test after a statement start or `if`, and a backslash that ends a line
# after a space with a line after it (a `C:\repo\` path ends in no space before its backslash, and a
# lone backslash argument ends the text: `cd \`, and a `cd \` line before a line with no flag is a path).
COMMAND_SHELLS = ("powershell", "mac")
PS_BASH_OPERATOR = re.compile(r"&&|\|\||<<|/dev/null|(?:^|;)\s*export\s", re.M)
# A pipe may end a line, so `|`, a newline, then the program is a pipe to it. A NAME=value value may hold `$(...)`
# (one nested level) with spaces, read whole so a failed read backtracks in linear time. A value ending in `,` that
# another `Name=` follows is a wrapped attribute list (`Mandatory=$true, Position=0`), not a prefix before a command.
# A bracket test is one whitespace char, then any text, then whitespace and the closing bracket: `[ \t]` then
# `[^\]\n]*` never take the same run twice, so one match start costs one pass over its line. A single `[` is a test
# only when a test operator stands inside it as its own word: a `-flag` (`-f`, `-eq`) or `=`, `==`, `!=`. So a spaced
# PowerShell cast `( [ int ] 5 )` or array `[ 1, 2 ]` is text. A lookahead reads the operator: it stops at the first
# `]` or line end and does not backtrack once it holds, so the start still costs one pass for the lookahead and one
# for the bracket.
PS_BASH_FORMS = re.compile(
    r"\|[ \t]*(?:\r?\n[ \t]*)?(?:head|tail|grep|xargs|sed|awk|cut|wc|uniq|tr|tac|jq|less)(?![\w-])"
    r"|(?:^|;)[ \t]*[A-Za-z_][A-Za-z0-9_]*="
    r"(?:\$\{(?:\$\{(?:\$\{[^{}\s;]*\}|[^{}\s;])*\}|[^{}\s;])*\}|\$\((?:[^()]|\([^()]*\))*\)|(?!\$\()[^\s;}])*"
    r"(?:(?<!,)[ \t]+[A-Za-z./]|(?<=,)[ \t]+(?![A-Za-z_][A-Za-z0-9_]*=)[A-Za-z./])"
    r"|(?:^|[;(]|\b(?:if|elif|while|until)\b)[ \t]*"
    r"(?:\[(?=[^\]\n]*?[ \t](?:-[A-Za-z]+|!?==?)[ \t])[ \t][^\]\n]*[ \t]\]|\[\[[ \t][^\]\n]*[ \t]\]\])",
    re.M | re.I)
# A backslash that ends a line after a space, with a line after it. When the backslash is the line's only
# argument (`cd \`, the drive root) and the next line does not start with a flag, it is a path, not a continuation.
PS_BASH_CONTINUATION = re.compile(r"^([^\n]*[ \t])\\[ \t]*\r?\n[ \t]*(\S)", re.M)
# A shell line in a step's backtick span or fence, read by guard_core's quote-aware reader. A span
# with a chain (an operator, or two lines) is a shell line when one segment plainly runs a command:
# its command word, after any `VAR=value`, `env`, `time`, `sudo` or `$(` prefix, is in SHELL_PROGRAMS,
# is a hyphenated cmdlet (`get-process`), or is a lowercase word with an argument after it (`grep -n
# x`, `cmd /c git log`). A span with no chain is a shell line when its command is a Verb-Noun cmdlet,
# or a SHELL_PROGRAMS program with an argument, or a lowercase word whose second word is a flag
# (`chmod +x f`). Plain text is no command: `foo|bar` (no space), `title;
# subtitle`, `// a | b` and a markdown table row. A program alone (`git`) names the tool in prose, and
# any other backticked word (`main`) or a file name is not a shell line. A path that starts ./ or ../ is
# a shell line when an argument follows it, when its name has no extension (`./build`), or when it ends
# in a script extension and a run verb comes before the span in its sentence, or the span is a fence.
# `./docs/a.md` and an edited `./hooks/guard.py` are files.
SHELL_PROGRAMS = frozenset(("git", "gh", "cd", "npm", "npx", "node", "python", "python3", "pip", "curl",
                            "brew", "bash", "sh", "zsh", "pwsh", "powershell", "claude", "rm", "mv", "cp",
                            "ls", "cat", "echo", "export", "sudo", "make", "pytest", "docker", "mkdir",
                            "gcloud", "bq", "winget", "gsutil", "kubectl", "terraform", "yarn", "pnpm", "aws",
                            "az", "helm"))
# A span whose command word is any lowercase word and whose second word is a flag (`grep -r x`, `chmod +x
# f`) is a shell line too, unless that word is a determiner (`the -x flag`), as is one whose program is listed. A command word with a path is read by its
# basename, so `/usr/bin/chmod +x f` and `scripts/run.py --x` are shell lines.
SPAN_FLAG = re.compile(r"(?:--?|\+)[A-Za-z]")
# A determiner first word marks prose: `the -x flag` names a flag and runs nothing, so the span-flag rule skips it.
SPAN_DETERMINERS = frozenset(("the", "a", "an", "this", "its", "your", "that", "these", "those", "each", "every", "my",
                              "our", "some"))
# The approved PowerShell verbs, the Get-Verb list. A Verb-Noun at an absolute path is a cmdlet only when its verb is one
# of these, so a folder whose last segment is Title-Hyphen (`~/Documents/Claude-Settings`) is text.
PS_VERBS = ("Add", "Clear", "Close", "Copy", "Enter", "Exit", "Find", "Format", "Get", "Hide", "Join", "Lock", "Move",
            "New", "Open", "Optimize", "Pop", "Push", "Redo", "Remove", "Rename", "Reset", "Resize", "Search", "Select",
            "Set", "Show", "Skip", "Split", "Step", "Switch", "Undo", "Unlock", "Watch",
            "Backup", "Checkpoint", "Compare", "Compress", "Convert", "ConvertFrom", "ConvertTo", "Dismount", "Edit",
            "Expand", "Export", "Group", "Import", "Initialize", "Limit", "Merge", "Mount", "Out", "Publish", "Restore",
            "Save", "Sync", "Unpublish", "Update",
            "Approve", "Assert", "Build", "Complete", "Confirm",
            "Deny",  # glossary-ok: Deny is a Get-Verb verb, not a refusal
            "Deploy", "Disable", "Enable", "Install",
            "Invoke", "Register", "Request", "Restart", "Resume", "Start", "Stop", "Submit", "Suspend", "Uninstall",
            "Unregister", "Wait",
            "Debug", "Measure", "Ping", "Repair", "Resolve", "Test", "Trace",
            "Connect", "Disconnect", "Read", "Receive", "Send", "Write",
            "Block", "Grant", "Protect", "Revoke", "Unblock", "Unprotect", "Use")
# A PS_VERBS cmdlet at an absolute path: a drive (`C:`), `~`, `$HOME` or `${HOME}`, or none, then `/` or `\`. It reads a
# word (`C:/tools/Get-Thing`, `$HOME/bin/Get-Item`) and the raw segment, since guard_core's POSIX reader strips the
# backslashes of `C:\tools\Get-Thing` and `~\Get-Item`. Each component ends in a separator, so the run reads in one pass.
ABS_CMDLET_PATH = re.compile(r"(?:[A-Za-z]:|~|\$HOME|\$\{HOME\})?[\\/](?:[^\s\\/]+[\\/])*"
                             r"(?:" + "|".join(PS_VERBS) + r")-[A-Z][A-Za-z]+(?=\s|$)")
# PowerShell's own pipeline cmdlets, whose verbs are no Get-Verb verbs (so they stay out of PS_VERBS) and which Claude
# writes in a pipeline (`ForEach-Object { $_ }`). SHELL_CMDLET reads them as a cmdlet verb beside PS_VERBS.
PS_NONSTANDARD_VERBS = ("ForEach",)
SHELL_CMDLET = re.compile(r"(?:[A-Z][a-z]+|" + "|".join(PS_VERBS + PS_NONSTANDARD_VERBS) + r")-[A-Z][A-Za-z]+")
# What may come before a cmdlet path in a segment: `&`, then any `VAR=value` or command-wrapper word. The wrapper
# words come from guard_core's COMMAND_WRAPPERS, the list its token reader unwraps, so the two readers agree.
@functools.lru_cache(maxsize=1)
def _cmdlet_prefix():
    import guard_core
    words = "|".join(re.escape(w) for w in sorted(guard_core.COMMAND_WRAPPERS - {"&"}))
    return re.compile(r"\s*(?:&\s+)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=\S*|" + words + r")\s+)*")
# What the refusal prints for a Verb-Noun at an absolute path: a folder written with a trailing `/` is text.
SHELL_LINE_HIT = "step holds a shell line"
ABS_CMDLET_HIT = SHELL_LINE_HIT + " (a Verb-Noun at a path reads as a cmdlet). If it names a folder, end it with /."
# In a chain a cmdlet may be any case (`get-process`), and a command may be any lowercase word.
CHAIN_CMDLET = re.compile(r"[A-Za-z]+-[A-Za-z]+")
CHAIN_COMMAND = re.compile(r"[a-z][a-z0-9._-]*")
ENV_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
SHELL_SCRIPT_EXT = (".sh", ".ps1", ".py", ".bat", ".cmd")
# A run verb in the step text before a span, back to the last sentence break.
SPAN_RUN_VERB = re.compile(_RUN_VERB + r"(?:(?![.;!?](?:\s|$)).)*$", re.I | re.S)
EFFECT_TEXT = re.compile(r"\b(?:Gain|Lose):.*?(?=\b(?:Gain|Lose):|$)", re.I | re.S)
CHAT_URL = re.compile(r"https://[^\s)>\]\"']+", re.I)


def _flat_text(value) -> str:
    """One string from a step or option field: a string as is, a dict's string values joined."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(v for v in value.values() if isinstance(v, str))
    return ""


# A clause whose subject is the session ("The session merges it after your pick.", "Claude merges it ...") and that names
# no `you` and no owner who acts ("the owner clicks Approve", "Shivam approves it"): the session makes
# that press, so the owner presses nothing. Only that clause is excused. A press in another clause
# stays ("..., then press Merge", "...: press Merge", "... but click Merge"). An owner's name with no
# act after it ("as the owner asked", "after Shivam's OK"), a past act ("after he approved it") and a
# press of the page's own button ("after he hits Send") ask the owner for nothing.
SESSION_PRESS = re.compile(r"^\s*(?:(?:the|a|this)\s+session|claude)\b", re.I)
# A session clause that asks someone for something ("Claude asks the owner for a click on Merge"), or names a
# press that is not past ("after your click on Merge", "after the owner's press"), hands the press on, so it is
# never excused. "as he asked" and "after he clicked Approve" are past acts and ask for nothing.
SESSION_HANDS_ON = re.compile(r"\b(?:ask|asks|asking|request|requests|requesting|tell|tells|telling|remind|reminds"
                          r"|reminding|click|clicks|clicking|press|presses|pressing|tap|taps|tapping)\b", re.I)
# SESSION_PRESS_OWN is the session's own press verb right after its subject ("The session clicks Merge"): it is
# no hand-on, so it is cut before SESSION_HANDS_ON reads the clause. "after your click" still hands on.
SESSION_PRESS_OWN = re.compile(r"^(\s*(?:(?:the|a|this)\s+session|claude)(?:\s+(?:then|also|\w+ly))*)"
                               r"\s+(?:clicks|presses|taps)\b", re.I)
# "and approves" stays in its clause: "the owner reviews and approves it" is one owner act, not two clauses.
# A bare "and approve" is an order to the owner, so it still starts a clause.
_CLAUSE_BREAK = re.compile(r",|;|:|\(|\s-\s|(?<=[.!?])\s+|\n|\b(?:then|but|so|or)\b"
                           r"|\band\b(?!\s+approv(?:es|ing)\b)", re.I)
# The clauses left after the excused ones are joined with `;`: PRESS_VERB reads it as a clause start, so
# "... but you approve it" stays a press, and mark ... ready reads across it, as across the cut break.
_CLAUSE_JOIN = "; "
OWNER_YOU = re.compile(r"\byou\b", re.I)
OWNER_NAME = re.compile(r"\b(?:the\s+(?:owner|user)|shivam|he|him)\b", re.I)
# The act is the verb the name is subject of: a modal, "to", "just", "please" or an -ly word may come
# between, so "Shivam will approve it" and "the user to just click Merge" act, and "the owner clicked
# Approve" (the button's name, after a past act) does not.
# "the owner's merge" and "the owner's approval" are presses not yet made, as "the owner's click" is, unless the
# approval is already in ("the owner's approval is in"). "merge" is a press only as the last word of its phrase:
# a noun after it ("the owner's merge commit", "merge queue", "merge button") names a thing, not his act.
# "has to", "needs to" and "reviews and" stand before the act as a modal does. A bare "has" does not: "the owner
# has merge rights" names no act, and "the owner has hit Merge" is a past one.
OWNER_ACT = re.compile(r"(?:(?:\s+(?:will|can|must|should|may|then|also|first|now|to|just|please"
                       r"|(?:has|have|needs?)\s+to|\w+ly|\w+s\s+and))*\s+"
                       r"(?:press(?:es|ing)?|click(?:s|ing)?|tap(?:s|ping)?|approv(?:e|es|ing)"
                       r"|merg(?:e|es|ing)|hit(?:s|ting)?|turn(?:s|ing)?\s+(?:it\s+)?on)"
                       r"|['\u2019]s\s+(?:merge(?=\s*(?:[^\w\s]|$)|\s+(?:on|in|at|of|by|for|from|with|before|after"
                       r"|first|and|or|then|so|but|once|when)\b)"
                       r"|approval(?!\s+(?:is|was|has|are|came|comes|arrives?)\b)))\b" + _PAGE_BUTTON, re.I)
_PRESS_LEAD = frozenset(("you", "and", "then", "or", "please"))


def _owner_acts(clause) -> bool:
    """True when an owner's name in `clause` is the subject of a present or future press or act."""
    return any(OWNER_ACT.match(clause, m.end()) for m in OWNER_NAME.finditer(clause))


def _owner_press_text(label, how) -> tuple:
    """(text, press_text) of one option, for _press_field_ok. `text` is the label and the how, one
    text. `press_text` is the label and the how without each clause of the how that the session
    presses (SESSION_PRESS). The label stays a press when it asks for one, unless every press verb in
    it is a verb that such a clause also holds: "Merge it" beside "The session merges it
    after your pick." is the session's act, and "Click Merge on GitHub" is the owner's."""
    text = label + ". " + how
    clauses = [c for c in _CLAUSE_BREAK.split(how) if c and c.strip()]
    session = [c for c in clauses if SESSION_PRESS.search(c) and not OWNER_YOU.search(c)
               and not SESSION_HANDS_ON.search(SESSION_PRESS_OWN.sub(r"\1", c, count=1)) and not _owner_acts(c)]
    if not session:
        return text, text
    # The session's own click ("The session clicks Merge") excuses no "Click" in the label: that asks the owner.
    done = " ".join(SESSION_PRESS_OWN.sub(r"\1", c, count=1) for c in session).lower()
    verbs = [next((w for w in re.findall(r"[a-z]+", m.group().lower()) if w not in _PRESS_LEAD), "")
             for m in PRESS_VERB.finditer(label)]
    label_ok = all(v and re.search(r"\b" + v, done) for v in verbs)
    rest = _CLAUSE_JOIN.join(c for c in clauses if c not in session)
    return text, ("" if label_ok else label + ".\n") + rest


def _press_field_ok(text, links, context="", press_text=None) -> bool:
    """True when this field asks for no web press, or `links` holds a link to the exact page. The
    press verb is read in `press_text`, which is `text` unless the caller leaves out a press the
    session makes (_owner_press_text). The page, and each `#N` that needs a url with /pull/N or
    /issues/N at a number boundary, is read in `text`, or in `context` when `text` names no page."""
    if not PRESS_VERB.search(text if press_text is None else press_text):
        return True
    page = text if WEB_MARKER.search(text) else context
    if not WEB_MARKER.search(page):
        return True
    # A link counts as the page draws it: a string url and a string label (skills/waiting-page/page.html
    # isLink). A link the page does not draw shows the owner nothing to press. `links` that is not a
    # list holds no link.
    urls = [l["url"] for l in (links if isinstance(links, list) else [])
            if isinstance(l, dict) and isinstance(l.get("url"), str) and isinstance(l.get("label"), str)]
    if not urls:
        return False
    return all(any(re.search(r"/(?:pull|issues)/%s(?!\d)" % n, u) for u in urls)
               for n in PRESS_REF.findall(page))


def press_link_hit(op, data) -> str:
    """The matched text when this write names a press in a web app with no link to the exact page.
    The link sits on the option that presses, or on the task. An update of `steps` with no `links`
    cannot see the stored links and passes."""
    if not isinstance(data, dict) or data.get("kind", "decision") not in ("decision", "task"):
        return ""
    options, steps = data.get("options"), data.get("steps")
    if isinstance(options, list):
        for o in options:
            if not isinstance(o, dict):
                continue
            # label and how are one text: the ref may sit in one and the press in the other
            text, press_text = _owner_press_text(_flat_text(o.get("label")), _flat_text(o.get("how")))
            if not _press_field_ok(text, o.get("links"), press_text=press_text):
                return "option presses in a web app with no link to the page"
    if isinstance(steps, list) and (op == "set" or "links" in data):
        # the steps are one text, as command-in-item reads them: the page may sit in one step and
        # the press in another. The title names the page only when the steps name none, and a
        # title alone never makes a press.
        joined = "\n".join(_flat_text(s) for s in steps)
        if not _press_field_ok(joined, data.get("links"), _flat_text(data.get("title"))):
            return "step presses in a web app with no link to the page"
    return ""


def _command_ok(command) -> bool:
    """True when `command` is {powershell, mac} with both a non-empty string."""
    return isinstance(command, dict) and all(isinstance(command.get(k), str) and command[k].strip()
                                             for k in COMMAND_SHELLS)


def _code_spans(text) -> list:
    """Each backtick span and fenced block in `text`, read in one pass, as (start, body, fenced). A
    run of n backticks opens a span that the next run of exactly n closes, as Markdown pairs them; a
    run with no closer is plain text. A fence's first line is its info string and is dropped."""
    spans, i, end = [], 0, len(text)
    while i < end:
        if text[i] != "`":
            i += 1
            continue
        j = i
        while j < end and text[j] == "`":
            j += 1
        run, k, close = j - i, j, -1
        while k < end:
            if text[k] != "`":
                k += 1
                continue
            m = k
            while m < end and text[m] == "`":
                m += 1
            if m - k == run:
                close = k
                break
            k = m
        if close < 0:
            i = j
            continue
        body = text[j:close]
        fenced = run >= 3 and "\n" in body
        if fenced:
            body = body.split("\n", 1)[1]
        spans.append((i, body, fenced))
        i = close + run
    return spans


def _relative_run(words, run) -> bool:
    """True when `words`, whose first word starts ./ or ../, runs that path (see SHELL_PROGRAMS).
    `run` is True when a run verb comes before the span or the span is a fence."""
    name = words[0].rsplit("/", 1)[-1]
    return len(words) >= 2 or "." not in name or (run and name.lower().endswith(SHELL_SCRIPT_EXT))


def _chain_command(word, args) -> bool:
    """True when the command `word`, with `args` words after it, plainly runs a command in a chain."""
    return (word in SHELL_PROGRAMS or bool(CHAIN_CMDLET.fullmatch(word))
            or (args >= 1 and bool(CHAIN_COMMAND.fullmatch(word))))


def _cmdlet_at_path(first, segment) -> bool:
    """True when the first word `first` of `segment` is a Verb-Noun cmdlet, bare, or at an absolute path with a
    PS_VERBS verb (see ABS_CMDLET_PATH). A relative path (`docs/Read-Me`, `Microsoft.PowerShell.Management/Get-Item`)
    or a URL names a doc or a module, not a program. The basename keeps its case."""
    return bool(SHELL_CMDLET.fullmatch(first) or ABS_CMDLET_PATH.fullmatch(first)
                or ABS_CMDLET_PATH.match(segment, _cmdlet_prefix().match(segment).end()))


def _shell_line(span, run) -> str:
    """The refusal text when a segment of this code span runs a shell line (see SHELL_PROGRAMS), else "". The text
    is ABS_CMDLET_HIT when the line is a Verb-Noun at an absolute path, SHELL_LINE_HIT otherwise. `run` is as for
    _relative_run. The segments, their prefixes and their command words come from guard_core, the one
    quote-aware shell reader, so a quote or a comment opener in text hides no command. A line that
    starts with `|` (a table row) or `//` is text and is left out."""
    import guard_core   # loads only for a step that holds a code span
    kept = [line for line in span.splitlines() if not line.strip().startswith(("|", "//"))]
    segments = guard_core.split_segments(guard_core.PosixScript("\n".join(kept)))
    spaced = bool(re.search(r"\s", "\n".join(kept).strip()))   # `foo|bar` is an alternation, not a pipe
    chained = len(segments) >= 2 and spaced
    for segment in segments:
        tokens = guard_core.segment_tokens(segment)
        if tokens is not None:
            found = guard_core.command_indexes(tokens)
            words = list(tokens[found[0]:]) if found else []
        else:   # unparseable text: its first word after any VAR=value is the command
            words = segment.split()
            while words and ENV_ASSIGNMENT.match(words[0]):
                words.pop(0)
        if not words:
            continue
        word = guard_core.basename(words[0])
        if words[0].startswith(("./", "../")):
            if _relative_run(words, run):
                return SHELL_LINE_HIT
        elif _cmdlet_at_path(words[0], segment):
            return SHELL_LINE_HIT if SHELL_CMDLET.fullmatch(words[0]) else ABS_CMDLET_HIT
        elif chained and _chain_command(word, len(words) - 1):
            return SHELL_LINE_HIT
        elif len(words) >= 2 and (word in SHELL_PROGRAMS
                                  or (CHAIN_COMMAND.fullmatch(word) and word not in SPAN_DETERMINERS
                                      and SPAN_FLAG.match(words[1]))):
            return SHELL_LINE_HIT
    return ""


def _ps_bash_form(text) -> bool:
    """True when PowerShell text holds a bash-only form. PS_BASH_OPERATOR reads the text as it stands;
    PS_BASH_FORMS reads it with each quoted string, here-string and comment blanked to `_` (newlines kept),
    found by guard_core's PowerShell quote walk, the one home of that reading."""
    if PS_BASH_OPERATOR.search(text):
        return True
    import guard_core   # loads only for a task that has a command
    script = guard_core.PowerShellScript(text)
    out = []
    for index, char, quote in guard_core.walk_quotes(script, line_comments=True):
        out.append("_" if quote and char != "\n" else char)
    blanked = "".join(out)
    if PS_BASH_FORMS.search(blanked):
        return True
    for match in PS_BASH_CONTINUATION.finditer(blanked):
        lone = len(match.group(1).split()) == 1
        if not (lone and match.group(2) != "-"):
            return True
    return False


def command_in_item_hit(data) -> str:
    """The matched text when a task's `command` is not {powershell, mac}, when its powershell string
    holds bash syntax, when its steps, joined, send the owner to a file for a command, or when a
    step holds a shell line in backticks. A `command` on the item excuses only the loose verb match
    (COMMAND_VERB); "the command in <file>" and "its command" still point at the file. An update
    with no `command` key leaves the stored one alone."""
    if not isinstance(data, dict) or data.get("kind", "task") != "task":
        return ""
    has_command = _command_ok(data.get("command"))
    if "command" in data and not has_command:
        return "command is not {powershell, mac}"
    if has_command and _ps_bash_form(data["command"]["powershell"]):
        return "powershell command holds a bash operator"
    steps = data.get("steps")
    if not isinstance(steps, list):
        return ""
    texts = [_flat_text(s) for s in steps]
    joined = "\n".join(texts)
    has_file = COMMAND_FILE.search(joined)
    if COMMAND_IN_FILE.search(joined) or (has_file and COMMAND_ITS.search(joined)) \
            or (has_file and not has_command and COMMAND_VERB.search(joined)):
        return "steps send the owner to a file for a command"
    for text in texts:
        for start, body, fenced in _code_spans(text):
            hit = _shell_line(body, fenced or bool(SPAN_RUN_VERB.search(text[:start])))
            if hit:
                return hit
    return ""


# ------------------------------------------------------------------ a gh command switches login first
#
# docs/decisions/act-in-place.md, rule `gh-login-switch`, built against a named incident (incident in
# the record): a task's `command` runs on the owner's computer as whichever gh login is active there.
GH_LOGINS = (GH_DEFAULT_LOGIN, GH_FALLBACK_LOGIN)
GH_LOGIN_REASON = ("A gh command handed to the owner runs as whichever gh login is active on his computer. "
                   "Put `gh auth switch -u %s` in the item's `command` before its first gh command. "
                   "Switch to %s instead only for a repo %s cannot reach."
                   % (GH_DEFAULT_LOGIN, GH_FALLBACK_LOGIN, GH_DEFAULT_LOGIN))
GH_NO_SWITCH = "gh command with no gh auth switch before it"
GH_WORD = re.compile(r"(?<![\w-])gh(?![\w-])")


def _switch_login(args) -> str:
    """The login a `gh auth switch` names with -u, --user or --user=, else ""."""
    for i, arg in enumerate(args):
        if arg in ("-u", "--user") and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith("--user="):
            return arg[len("--user="):]
    return ""


def _shell_reading(guard_core, script):
    """[(segment, its tokens or None when the reader cannot parse it)] for one script type."""
    return [(segment, guard_core.segment_tokens(segment)) for segment in guard_core.split_segments(script)]


def _gh_calls(guard_core, reading):
    """Each gh command of one shell's `reading`, in order, as its tokens from the word gh on. A segment
    the reader cannot parse that names gh yields None: a gh command, never a switch."""
    for segment, tokens in reading:
        if tokens is None:
            if GH_WORD.search(segment):
                yield None
            continue
        for i in guard_core.command_indexes(tokens):
            if guard_core.basename(tokens[i]) in ("gh", "gh.exe"):
                yield tokens[i:]


def _gh_script_hit(guard_core, reading, command) -> str:
    """The matched text when one shell's `reading` of `command` runs a gh command other than
    `gh auth ...` with no switch to a login in GH_LOGINS before it, or runs one as GH_FALLBACK_LOGIN
    while `command` names a GH_DEFAULT_LOGIN repo. A segment the reader cannot parse counts as a gh
    command when the word gh is in it, and never as a switch: the check fails closed there."""
    names_default_repo = (GH_DEFAULT_LOGIN + "/").lower() in command.lower()
    login = ""
    for call in _gh_calls(guard_core, reading):
        if call is not None and list(call[1:2]) == ["auth"]:
            if list(call[2:3]) == ["switch"]:
                login = _switch_login(list(call[3:]))
            continue
        if login not in GH_LOGINS:
            if login:
                return "gh command after a switch to %s, a login outside the pair" % login
            return GH_NO_SWITCH
        if login == GH_FALLBACK_LOGIN and names_default_repo:
            return "gh command as %s on a %s/ repo" % (GH_FALLBACK_LOGIN, GH_DEFAULT_LOGIN)
    return ""


def _command_reading(guard_core, shell, text):
    """One shell's reading of `text`. The script type picks the rules, never the tool this call came
    from. A `shell` of "" is a str_replace string: bash's rules read it, or PowerShell's when bash
    cannot read some segment and PowerShell reads every one."""
    if shell == "powershell":
        return _shell_reading(guard_core, guard_core.PowerShellScript(text))
    reading = _shell_reading(guard_core, guard_core.PosixScript(text))
    if not shell and any(tokens is None for _, tokens in reading):
        powershell = _shell_reading(guard_core, guard_core.PowerShellScript(text))
        if all(tokens is not None for _, tokens in powershell):
            return powershell
    return reading


def _gh_counts(text):
    """(gh commands other than `gh auth ...`, `gh auth switch` commands) in a command string."""
    if not GH_WORD.search(text):
        return 0, 0
    import guard_core
    commands = switches = 0
    for call in _gh_calls(guard_core, _command_reading(guard_core, "", text)):
        if call is not None and list(call[1:2]) == ["auth"]:
            switches += list(call[2:3]) == ["switch"]
        else:
            commands += 1
    return commands, switches


def gh_edit_hit(old, new) -> str:
    """The matched text when a str_replace on `command` turns `old` into `new` and leaves a gh command
    that gh_login_hit refuses. The stored command is unseen, so `new` is judged alone, except that the
    one reason GH_NO_SWITCH is excused for an edit that only changes gh commands `old` already held: it
    adds no gh command, and it holds no switch in `old` or `new` for the edit to remove or move, so the
    switch the stored command keeps still stands. Every other reason stands. So does an edit that adds
    a GH_DEFAULT_LOGIN repo name, since the stored login may be GH_FALLBACK_LOGIN."""
    hit = gh_login_hit({"command": new})
    if hit != GH_NO_SWITCH:
        return hit
    old_gh, old_switch = _gh_counts(old)
    new_gh, new_switch = _gh_counts(new)
    if not old_gh or new_gh > old_gh or old_switch or new_switch:
        return hit
    repo = GH_DEFAULT_LOGIN + "/"
    if new.lower().count(repo) > old.lower().count(repo):
        return "gh edit that names a %s/ repo, and the stored login is unseen" % GH_DEFAULT_LOGIN
    return ""


def gh_login_hit(data) -> str:
    """The matched text when a task's `command` fails _gh_script_hit in one shell. Each shell of
    {powershell, mac} is judged on its own and needs its own switch: `powershell` by PowerShell's
    rules, where `\\` is a path character, and `mac` by bash's rules. A `command` held as one string
    is a `str_replace` new_str: bash's rules read it, or PowerShell's when bash cannot read some
    segment and PowerShell reads every one."""
    if not isinstance(data, dict) or data.get("kind", "task") != "task":
        return ""
    command = data.get("command")
    if isinstance(command, dict):
        scripts = [(k, command.get(k)) for k in COMMAND_SHELLS]
    else:
        scripts = [("", command)]
    # guard_core holds the one quote-aware shell reader, for bash and PowerShell. It loads only when a
    # command names gh, so the chat-box path loads nothing more.
    for shell, text in scripts:
        if not isinstance(text, str) or not GH_WORD.search(text):
            continue
        import guard_core
        hit = _gh_script_hit(guard_core, _command_reading(guard_core, shell, text), text)
        if hit:
            return "%s: %s" % (shell, hit) if shell else hit
    return ""


# ------------------------------------------------------------------ a task names why only the owner can do it
#
# docs/decisions/task-names-its-check.md, rule `task-names-check`, built against a named incident
# (incident in the record): a waiting-page task handed the owner a job a session on his computer then
# did. A task carries a "Why yours:" line naming the check that showed no session could do it.
WHY_YOURS_LINE = re.compile(r"^\s*Why yours:[ \t]*\S", re.I | re.M)
WHY_YOURS_LABEL = re.compile(r"^[ \t]*Why yours\b", re.I | re.M)
TASK_REASON = ("A task is yours to hand over only when no session can do it. If the cloud refused the "
               "act, ask a session on the owner's computer first (list_computer_folders, then "
               "request_computer_folder). Then add a line to context that starts \"Why yours: "
               "<the check that showed no session could do it>\".")


WHY_RULE = "task-why-cited"
WHY_CITED_REASON = ("A Why yours line that says a session cannot do the act must cite what shows it. End the line with "
                    "\"(route <id>)\", an id from the route rows file whose row on this surface says refused or asks, or "
                    "with \"(measured <YYYY-MM-DD>, <the check and its result>)\". A row that says the act works, an "
                    "id no row holds, and a measurement with no date do not count. The page reads no refusals file, so "
                    "a tool name in backticks is no cite. (decision claims-carry-backing, part (v), rule task-why-cited)")
# lint/report_guard.py why_yours_verdict kinds that refuse on the page, with the cause the refusal's `matched` carries.
# "unknown" (a file or row that did not read) and "unread" never refuse: a read that could not run is not a finding.
WHY_CAUSES = {"none": "no cite", "undated": "undated measured", "works": "works row", "dead": "unknown id"}


def _report_guard():
    """lint/report_guard.py, loaded here and not at import, as hooks/reply_judge.py loads it."""
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    import report_guard
    return report_guard


def why_cited_hit(text: str, fragments: bool = False) -> str:
    """The cause when a Why yours line of `text` gives a capability reason its cite does not back, else "". The page
    accepts a route cite and a dated measured cite, and reads no refusals file. A line with no route cite never reads
    the rows file. With `fragments`, each other line of `text` has its cite tokens judged on their own: a str_replace
    that swaps only a cite carries no Why yours line, and `new_str` must still hold a cite that backs."""
    lines = text.splitlines()
    labelled = [line for line in lines if WHY_YOURS_LINE.match(line)]
    # A plain substring gate, so report_guard (which holds the cite regexes) loads only for a line that may hold a cite.
    # A Based on line is the form's own premise line: "Based on (measured): ..." names a kind, not a dated cite.
    loose = [line for line in lines if fragments and not WHY_YOURS_LINE.match(line) and not BASED_LABEL.match(line)
             and ("(route" in line.casefold() or "(measured" in line.casefold())]
    if not (labelled or loose):
        return ""
    guard = _report_guard()
    for line in labelled:
        cause = WHY_CAUSES.get(guard.why_yours_verdict(None, line.strip())[0])
        if cause:
            return cause
    for line in loose:
        cause = WHY_CAUSES.get(guard.cite_tokens_verdict(line.strip())[0])
        if cause:
            return cause
    return ""


def task_check_hit(op: str, data):
    """(rule, matched) when this write of a waiting-page task has no Why yours line, or a line whose capability reason
    its cite does not back. An update that carries no `context` cannot change the line and passes, as does one with
    no `kind`."""
    if not isinstance(data, dict) or data.get("kind") != "task":
        return PASS
    if not (op == "set" or "context" in data):
        return PASS
    context = str(data.get("context") or "")
    if not WHY_YOURS_LINE.search(context):
        return "task-names-check", "task with no Why yours line"
    cause = why_cited_hit(context)
    return (WHY_RULE, cause) if cause else PASS


def task_str_replace_hit(entry):
    """(rule, matched) when a str_replace on `context` removes the Why yours line or its label, or adds one whose
    capability reason its cite does not back. It carries no `data`, so it is read from old_str and new_str; the
    guard cannot see the stored kind, so it judges a context edit that touches the line, whatever the item's kind.
    An edit that removes only the reason after the label passes: the stored line is unseen, so old_str is no
    different from any prose."""
    if entry.get("field") != "context":
        return PASS
    old, new = str(entry.get("old_str") or ""), str(entry.get("new_str") or "")
    if WHY_YOURS_LINE.search(old) and not WHY_YOURS_LINE.search(new):
        return "task-names-check", "context edit that removes the Why yours line"
    if len(WHY_YOURS_LABEL.findall(old)) > len(WHY_YOURS_LABEL.findall(new)):
        return "task-names-check", "context edit that removes the Why yours label"
    cause = why_cited_hit(new, fragments=True)
    return (WHY_RULE, cause) if cause else PASS


# ------------------------------------------------------------------ a page decision states the form


def decision_form_hit(op: str, data):
    """(rule, matched) when this write of a waiting-page decision breaks the form. A closed item and a
    record that is not a decision pass. An update is judged for the fields it carries, and only with kind
    decision: the guard cannot see the stored kind."""
    if not isinstance(data, dict) or data.get("status") == "closed":
        return PASS
    if op == "set":
        if data.get("kind") not in (None, "decision"):
            return PASS
    elif data.get("kind") != "decision":
        return PASS
    judged_context = op == "set" or "context" in data
    if judged_context:
        hit = _lines_hit(str(data.get("context") or ""), data.get("stands") is True)
        if hit[0]:
            return hit
    options = data.get("options")
    if (op == "set" or "options" in data) and isinstance(options, list):
        hit = _effects_hit([("%d" % i, _filled(o.get("gain")), _filled(o.get("lose")))
                            for i, o in enumerate(options, 1) if isinstance(o, dict)])
        if hit[0]:
            return hit
    if judged_context:
        miss = departs_hit(str(data.get("context") or ""))
        if miss:
            return DEPARTS_RULE, miss
    return PASS


def _filled(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def form_str_replace_hit(entry):
    """(rule, matched) when a str_replace on `context` removes a Goal, Problem or Based on line, or swaps
    the Problem line for a malformed one. It carries no `data`, so it is read from old_str and new_str.
    The stored `stands` is unseen, so new_str may drop a stake only where old_str had none."""
    if entry.get("field") != "context":
        return PASS
    old, new = str(entry.get("old_str") or ""), str(entry.get("new_str") or "")
    if GOAL_LINE.search(old) and not GOAL_LINE.search(new):
        return FORM_RULE, "context edit that removes the Goal line"
    # A stake in old_str stays a stake: a stood pick's bare `Problem:` is unseen here, so only a line that
    # had no stake may stay without one.
    if PROBLEM_LINE.search(old) and not PROBLEM_LINE.search(new):
        if PROBLEM_LABEL.search(new):
            return STAKE_RULE, "context edit that leaves a Problem line with no stake, or one outside the set"
        return FORM_RULE, "context edit that removes the Problem line"
    if PROBLEM_STOOD_LINE.search(old) and not PROBLEM_STOOD_LINE.search(new):
        if PROBLEM_LABEL.search(new):
            return STAKE_RULE, "context edit that leaves a Problem line with no stake, or one outside the set"
        return FORM_RULE, "context edit that removes the Problem line"
    if BASED_LABEL.search(old) and not BASED_LABEL.search(new):
        return FORM_RULE, "context edit that removes the Based on line"
    hit = placeholder_form_hit(new)
    if hit[0]:
        return hit
    # A context edit that holds a Departs from line in old_str or new_str keeps a valid one: dropping it, or
    # writing one that restates main, is refused. An edit with no such line in either is not judged.
    if DEPARTS_LINE.search(old) or DEPARTS_LINE.search(new):
        miss = departs_hit(new)
        if miss:
            return DEPARTS_RULE, "context edit that leaves no valid Departs from line (%s)" % miss
    return PASS


def item_hit(op, entry, cwd=""):
    """(rule, matched) for one write of a waiting item that a rule refuses, else ("", "")."""
    data = _write_data(entry, cwd)
    hit = item_field_hit(op, entry, data)
    if hit:
        return "item-field-rendered", hit
    if op == "str_replace":
        hit = task_str_replace_hit(entry)
        if hit[0]:
            return hit
        if entry.get("field") == "command":
            # The stored command is unseen: gh_edit_hit judges new_str, less an edit that only changes
            # a gh command old_str held.
            hit = gh_edit_hit(str(entry.get("old_str") or ""), entry.get("new_str"))
            if hit:
                return "gh-login-switch", hit
        hit = form_str_replace_hit(entry)
        if hit[0]:
            return hit
        # The stored item is unseen, so the two text rules judge the text this edit adds, in any field.
        new = [str(entry.get("new_str") or "")]
        hit = key_named_hit(new)
        if hit:
            return "option-letter-keys", hit
        hit = reworked_hit(new)
        if hit:
            return "rework-off-page", hit
        return PASS
    hit = port_item_hit(op, data)
    if hit:
        return "port-question", hit
    hit = widens_pick_hit(data)
    if hit:
        return "uniform-pick", hit
    hit = press_link_hit(op, data)
    if hit:
        return "press-link", hit
    hit = command_in_item_hit(data)
    if hit:
        return "command-in-item", hit
    hit = gh_login_hit(data)
    if hit:
        return "gh-login-switch", hit
    hit = task_check_hit(op, data)
    if hit[0]:
        return hit
    hit = decision_form_hit(op, data)
    if hit[0]:
        return hit
    hit = option_letter_hit(op, data)
    if hit:
        return "option-letter-keys", hit
    hit = rework_off_page_hit(data)
    if hit:
        return "rework-off-page", hit
    return PASS


# ------------------------------------------------------------------ the writes of a waiting page, one filter
#
# The one home of "which ArtifactData writes are waiting-page item writes". hooks/guard.py (the form
# check) and hooks/call_judge.py (the model review) both read it, so the two never disagree on a write.
WAITING_ITEMS = "items"
ITEM_OPS = ("set", "update", "str_replace")


def _git_root_of(cwd):
    here = os.path.realpath(cwd or os.getcwd())
    while True:
        if os.path.exists(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def _layout():
    """lint/layout.py, the one home of the layout and the mockup home."""
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    import layout
    return layout


def waiting_page_root(tool_input, cwd):
    """The git root of cwd's repo when the call's url is that repo's waiting page (lint/layout.py, the one
    home), else None. A repo with no page reads as unknown; only the none-key check judges its calls."""
    layout = _layout()
    root = _git_root_of(cwd)
    return root if root and layout.is_waiting_page_url(root, tool_input.get("url")) else None


def design_file_problems(writes, root):
    """[(doc_id, slug, sentence)] for each `designs` entry in `writes` (design_writes' picture writes) that has no
    `file`, or whose `file` lint/layout.py mockup_home_problem refuses against this machine's home. The sentence names
    the design folder and the field, never the refused path. An entry that is no dict has no file. Judges the shape
    only: it does not ask origin, and starts no process (rule mockup-home)."""
    layout = _layout()
    found = []
    for _op, doc_id, data in design_writes(writes):
        designs = data.get("designs")
        for entry in designs if isinstance(designs, list) else []:
            entry = entry if isinstance(entry, dict) else {}
            problem = layout.mockup_home_problem(root, entry.get("file"))
            if problem:
                found.append((doc_id, str(entry.get("slug") or "?"), problem))
    return found


def is_waiting_page(tool_input, cwd) -> bool:
    """True when the call's url is this repo's waiting page."""
    return waiting_page_root(tool_input, cwd) is not None


def page_item_hit(tool_input, cwd=""):
    """((rule, matched), writes) for one ArtifactData call. `writes` are the (op, entry) item writes of
    this repo's waiting page, empty for a read, another collection or another page (such a write still gets the check for an option keyed none). The hit is the first
    write that a rule refuses, else ("", "")."""
    if not isinstance(tool_input, dict):
        return PASS, []
    if tool_input.get("action") == "batch":
        entries = [(w.get("op"), w) for w in tool_input.get("writes") or [] if isinstance(w, dict)]
    else:
        entries = [(tool_input.get("action"), tool_input)]
    writes = [(op, e) for op, e in entries if op in ITEM_OPS and e.get("collection") == WAITING_ITEMS]
    if not writes:  # a read or another collection loads nothing more
        return PASS, []
    if not is_waiting_page(tool_input, cwd):
        # The cwd's page is unknown, or the url is another's: only the option-key check still reads the
        # write, and refuses only a key none. No writes return, so no other check or model review follows.
        return keyed_options_hit(writes, cwd), []
    for op, entry in writes:
        hit = item_hit(op, entry, cwd)
        if hit[0]:
            return hit, writes
    return PASS, writes


def keyed_options_hit(writes, cwd=""):
    """(rule, matched) for the first of `writes` that has the waiting-page decision shape (an `options`
    list) and an option keyed none, else ("", ""). Only the key none: the page reserves it, so it blocks the
    item. Judged whatever page the call names, since the page cannot be named reliably (another checkout's
    page, or a repo with no page key). Any other key, and any other shape, is no waiting-page item to this
    check, so it passes. A task, a note and a closed item pass, as in option_letter_hit."""
    for op, entry in writes:
        if op == "str_replace":  # carries no options: its shape, and so its page, is unseen
            continue
        data = _write_data(entry, cwd)
        options = data.get("options") if _open_decision(data) else None
        if isinstance(options, list) and any(_keyed_none(o) for o in options):
            return "option-letter-keys", NONE_KEY_HIT
    return PASS


def design_writes(writes):
    """The (op, doc_id, data) of each set or update in `writes` whose data carries a picture: a non-empty
    `designs` list, or an option with a `design`. Rule page-item-design reads only these, so a write with no
    picture never starts the checker."""
    found = []
    for op, entry in writes:
        data = _write_data(entry) if op in ("set", "update") else None
        if not isinstance(data, dict) or data.get("status") == "closed":  # a closed item is not drawn
            continue
        options = data.get("options")
        has_option = isinstance(options, list) and any(isinstance(o, dict) and o.get("design") for o in options)
        if data.get("designs") or has_option:
            found.append((op, entry.get("doc_id"), data))
    return found


def _judged_fragment(field):
    """True for a str_replace field the model review reads: `context`, `options`, or a subfield of `options`.
    The ArtifactData str_replace `field` is one top-level string key, so `steps` (a list) never reaches it."""
    return field in ("context", "options") or str(field).startswith("options.")


def judged_item_writes(writes):
    """The writes of a page item that the model review reads. A set or update is read as
    {"op", "doc_id", "data"} when it is not closed and either writes a decision (an update with no kind is
    read, as decision_form_hit cannot see the stored kind) that carries `options` or `context`, or writes a
    task that carries `context`, `steps` or `options`. A task is kind task, or any write that carries
    `steps`, since steps are task-only. A str_replace on `context` or `options` (a subfield too) is
    read as {"op", "doc_id", "field", "new_str"}: its new_str alone, never old_str, because the rest of the
    item is unseen."""
    judged = []
    for op, entry in writes:
        if op == "str_replace":
            if _judged_fragment(entry.get("field")) and isinstance(entry.get("new_str"), str):
                judged.append({"op": op, "doc_id": entry.get("doc_id"), "field": entry.get("field"),
                               "new_str": entry["new_str"]})
            continue
        data = _write_data(entry)
        if op not in ("set", "update") or not isinstance(data, dict) or data.get("status") == "closed":
            continue
        if data.get("kind") == "task" or data.get("steps"):
            if not (data.get("context") or data.get("steps") or data.get("options")):
                continue
        elif data.get("kind", "decision") != "decision" or not (data.get("options") or data.get("context")):
            continue
        judged.append({"op": op, "doc_id": entry.get("doc_id"), "data": data})
    return judged


# ------------------------------------------------------------------ an option's key is its position's letter
#
# docs/decisions/option-keys-are-letters.md, rule `option-letter-keys`, built against a named incident
# (incident in the record): the page shows an option by its position, so an option keyed a that sat second
# showed as B and the owner's answer was misread. The page's letter for index i is
# String.fromCharCode(65 + i % 26) (skills/waiting-page/page.html, symbol letterOf); the key is that letter
# in lowercase. The page reads the key "none" (symbol NONE, same file) as "none of these".
OPTION_NONE_KEY = "none"
# An option named in item text by a letter-and-digit key, as in "option e2": the word, then the key, both in
# any case, since the page shows the key's letter in capitals and Claude can write "Option E2". Only D12, a
# decision id, and t18, the owner's uniform-ruling topic id, are exempt, each in its own case. No shared
# constant lists record ids: lint/report_guard.py CITE_ID_RE holds D-ids only, and roadmap step ids such as
# c188 live on the roadmap branch, so a cell like A1, a lowercase id like c188 or a key like d4 reads as a key.
KEY_NAMED = re.compile(
    r"\b(?i:options?|picks?|keys?)[\s:(\[*_\"'`\u201c\u2018]+(?!D\d|t\d)(?i:[a-z])\d+\b")
LETTER_KEYS_REASON = ("Each option's key is the letter the page shows for its position, in lowercase. Key the "
                      "options a, b, c in the order shown, each once, never none, and name an option in the "
                      "item's text by that letter (option A, pick b), never by any other key. An option's "
                      "label carries no letter of its own: the page's key is the only letter, so a label "
                      "never opens with a tag such as B: or Option B.")

# A label's opening letter tag. Incident, Nov 1 16:12 CST: options keyed a-d carried the labels "B: ...",
# "D: ...", "A: ...", "C: ...", so the owner's answer letter named two options. Only an opening tag counts:
# `X:` `X)` `X.` `X]` before a space or end, `(X)`, `[X]`, a spaced dash after X, or the words "Option X". A
# letter word ("A rail"), "A/B", "AI-first", "B2B" and "E.g." are text, not tags.
LABEL_TAG = re.compile(r"""^\s*(?:\*\*)?(?:
    (?i:option)\s+(?P<word>[A-Za-z])(?![\w-])
    |\((?P<paren>[A-Za-z])\)
    |\[(?P<square>[A-Za-z])\]
    |(?P<plain>[A-Za-z])(?:\*\*)?(?:[:).\]](?=[\s*]|$)|\s[\u2014\u2013-]\s)
    )""", re.X)


def _letter_of(index: int) -> str:
    """The lowercase form of the page's letterOf for position `index`."""
    return chr(97 + index % 26)


def _item_text_fields(data):
    """The item's own text: title, context, why, each option's fields and each step."""
    out = [data.get(k) for k in ("title", "context", "why")]
    for o in data.get("options") if isinstance(data.get("options"), list) else []:
        out.append(_flat_text(o))
    for st in data.get("steps") if isinstance(data.get("steps"), list) else []:
        out.append(_flat_text(st))
    return [t for t in out if isinstance(t, str)]


def key_named_hit(texts) -> str:
    """The matched text when one of `texts` names an option by a letter-and-digit key, else ""."""
    for text in texts:
        m = KEY_NAMED.search(text)
        if m:
            return "item text names an option by a key: " + m.group(0)
    return ""


NONE_KEY_HIT = "option keyed none"


def _open_decision(data) -> bool:
    """True for the data of an open decision. A task, a note and a closed item are not judged. The one filter
    of option_letter_hit and keyed_options_hit."""
    return isinstance(data, dict) and data.get("kind", "decision") == "decision" and data.get("status") != "closed"


def _keyed_none(option) -> bool:
    """True for an option keyed none, the key the page reserves for its own "none of these"."""
    return isinstance(option, dict) and option.get("key") == OPTION_NONE_KEY


def option_letter_hit(op: str, data) -> str:
    """The matched text when this write of a waiting-page decision keys an option by anything but its
    position's letter, has a label that opens with another letter's tag, or names an option in its text by a
    letter-and-digit key. A task, a note and a
    closed item pass; an update that carries no `options` has no keys to judge."""
    if not _open_decision(data):
        return ""
    options = data.get("options")
    if isinstance(options, list):
        seen = set()
        for i, o in enumerate(options):
            key = o.get("key") if isinstance(o, dict) else None
            if not isinstance(key, str):
                return "option with no string key"
            if _keyed_none(o):
                return NONE_KEY_HIT
            if key in seen:
                return "option key that repeats"
            seen.add(key)
            if key != _letter_of(i):
                return "option key that is not its position's letter"
            m = LABEL_TAG.match(o.get("label")) if isinstance(o.get("label"), str) else None
            if m and next(v for v in m.groupdict().values() if v).lower() != key:
                return "option label that opens with a letter tag other than its key: " + m.group(0).strip()
    return key_named_hit(_item_text_fields(data))


# ------------------------------------------------------------------ a reworked item is not answered on the page
#
# docs/decisions/rework-leaves-page.md, rule `rework-off-page`, built against a named incident (incident in
# the record): an item whose options were being reworked stayed open, so the owner could answer options about
# to change. Any item text counts, and a str_replace is judged on the text it adds.
REWORKED = re.compile(r"\b(?:being\s+re-?worked|under\s+re-?work)\b", re.I)
REWORK_REASON = ("An open item is for the owner to answer now, so it never says its options are being "
                 "reworked. Close the item with a home that names the rework, and add a fresh item when the "
                 "options are ready.")


def reworked_hit(texts) -> str:
    """The matched text when one of `texts` says the item is being reworked, else ""."""
    for text in texts:
        m = REWORKED.search(text)
        if m:
            return "item text says it is being reworked: " + m.group(0)
    return ""


def rework_off_page_hit(data) -> str:
    """The matched text when this write puts "being reworked" in the item's text with no status closed."""
    if not isinstance(data, dict) or data.get("status") == "closed":
        return ""
    return reworked_hit(_item_text_fields(data))


# ------------------------------------------------------------------ an item field the page renders
#
# docs/decisions/item-field-rendered.md, rule `item-field-rendered`, built against a named incident
# (incident in the record): 37 live items carried `reply` and the page drew none. A write of a waiting
# item names only top-level fields that the page's own block lists, <script type="application/json"
# id="itemFields">. That block is the one list: this code reads it and holds no copy.
ITEM_FIELDS_SEAM = "GUARD_ITEM_FIELDS_PAGE"
ITEM_FIELDS_PAGE = os.path.join(HERE, "..", "skills", "waiting-page", "page.html")
ITEM_FIELD_REASON = ("The waiting page draws only the top-level item fields that its itemFields block "
                     "lists (skills/waiting-page/page.html). Draw the field on the page and add it to "
                     "that block, or leave it out of the write. An update may remove a stored field "
                     "with {\"__delete__\": true}. "
                     "(decision item-field-rendered, a waiting item names only fields the page draws)")


def _item_fields(path):
    """The list in the page's itemFields block, found with an HTML parser (script text is data, so a
    string or a template literal holds no block). None when the file, the block or the list does not read,
    and when the list is empty: a block that names no field is not a list to judge by."""
    class Block(HTMLParser):
        text, done = None, False

        def handle_starttag(self, tag, attrs):
            if tag == "script" and self.text is None and dict(attrs).get("id") == "itemFields":
                self.text = []

        def handle_data(self, data):
            if self.text is not None and not self.done:
                self.text.append(data)

        def handle_endtag(self, tag):
            if tag == "script" and self.text is not None:
                self.done = True

    try:
        with open(path, encoding="utf-8") as f:
            block = Block()
            block.feed(f.read())
            block.close()
        fields = json.loads("".join(block.text or []))
    except Exception:
        return None
    return fields if isinstance(fields, list) and fields and all(isinstance(x, str) for x in fields) else None


def item_field_hit(op, entry, data) -> str:
    """The matched text when this write of a waiting item names a top-level field outside the page's
    itemFields block. An update may remove a field with {"__delete__": true}. A str_replace names its
    field in `field`. A page with no readable block, or an empty one, reads as unknown, and the write passes."""
    fields = _item_fields(os.environ.get(ITEM_FIELDS_SEAM) or ITEM_FIELDS_PAGE)
    if fields is None:
        return ""
    if op == "str_replace":
        field = entry.get("field")
        top = field.split(".", 1)[0] if isinstance(field, str) else ""
        return "str_replace on " + top if top and top not in fields else ""
    if not isinstance(data, dict):
        return ""
    for key, value in data.items():
        if key in fields or (op == "update" and isinstance(value, dict) and value.get("__delete__") is True):
            continue
        return "field " + str(key)
    return ""


# ------------------------------------------------------------------ the chat question box


def _option_text(option, key) -> str:
    return option.get(key) if isinstance(option.get(key), str) else ""


def chat_hit(tool_input):
    """(rule, matched) for the first question of an AskUserQuestion input that breaks a rule, else
    ("", ""). A question with fewer than two options asks the owner no choice and passes."""
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    for question in questions if isinstance(questions, list) else []:
        options = question.get("options") if isinstance(question, dict) else None
        options = [o for o in options if isinstance(o, dict)] if isinstance(options, list) else []
        if len(options) < 2:
            continue
        hit = _chat_question_hit(question, options)
        if hit[0]:
            return hit
    return PASS


def _chat_question_hit(question, options):
    for o in options:
        label, desc = _option_text(o, "label"), _option_text(o, "description")
        if RECOMMENDED.search(label) and WIDENS_MARK.search(label + " " + desc):
            return "uniform-pick", "recommended option goes against the uniform ruling"
    for o in options:
        label, desc = _option_text(o, "label"), _option_text(o, "description")
        # a url in the description shows as its own text, so it is its own label
        links = [{"label": u, "url": u} for u in CHAT_URL.findall(desc)]
        # the page scans label and how; Gain and Lose text says what the pick does to the owner, not what he presses
        text, press_text = _owner_press_text(label, EFFECT_TEXT.sub("", desc))
        if not _press_field_ok(text, links, press_text=press_text):
            return "press-link", "option presses in a web app with no url to the page"
    text = str(question.get("question") or "")
    hit = _lines_hit(text)
    if hit[0]:
        return hit
    hit = _effects_hit([("'%s'" % (_option_text(o, "label") or i), bool(GAIN_TEXT.search(_option_text(o, "description"))),
                         bool(LOSE_TEXT.search(_option_text(o, "description"))))
                        for i, o in enumerate(options, 1)])
    if hit[0]:
        return hit
    miss = departs_hit(text)
    return (DEPARTS_RULE, miss) if miss else PASS


# ------------------------------------------------------------------ the reasons, one table per surface

PAGE_REASONS = {"port-question": PORT_REASON, "uniform-pick": WIDENS_REASON, "press-link": PRESS_LINK_REASON,
                "command-in-item": COMMAND_REASON, "gh-login-switch": GH_LOGIN_REASON,
                "task-names-check": TASK_REASON, WHY_RULE: WHY_CITED_REASON,
                FORM_RULE: PAGE_FORM_REASON, STAKE_RULE: STAKE_REASON, "item-field-rendered": ITEM_FIELD_REASON,
                DEPARTS_RULE: PAGE_DEPARTS_REASON,
                "option-letter-keys": LETTER_KEYS_REASON, "rework-off-page": REWORK_REASON}
CHAT_STAKE_REASON = ("A question is the owner's only when he can judge it. Write the Problem line as "
                     "\"Problem (<stake>): <the problem, and why it needs his word>\", where stake is one of %s. "
                     "(decision owner-judge-test, a decision reaches the owner only when he can judge it)"
                     % ", ".join(OWNER_STAKES))
CHAT_REASONS = {"uniform-pick": CHAT_WIDENS_REASON, "press-link": CHAT_PRESS_LINK_REASON,
                FORM_RULE: CHAT_FORM_REASON, STAKE_RULE: CHAT_STAKE_REASON, DEPARTS_RULE: DEPARTS_REASON}


# ------------------------------------------------------------------ past rulings: the owner is never asked twice
#
# Decision question-form holds the ruling. `past_rulings` gathers what the owner already decided, so the one
# question judge (hooks/call_judge.py, and lint/report_guard.py for a relayed question) can refuse a question a
# standing record settles. Sources: docs/decisions and docs/debts (every record, one index line each), and the
# ruling sentences of the `roadmap` ref's step notes (the 30 with the most word overlap). Closed page items are
# always unknown: a hook cannot call the Artifact tool, and the decision records carry their rulings.
# Cost: one git process, only when the caller already makes a model call; no file written.
PAST_RULING_RULE = "past-ruling"
UNVETTED_LINE = re.compile(r"^[ \t>*+-]*Unvetted:[ \t]*\S", re.I | re.M)
UNREADABLE = "unreadable"
CLOSED_ITEMS = "closed page items"
INDEX_CAP, STEP_TOP, STEP_GIT_TIMEOUT = 800, 30, 10
RULING_HEADING = re.compile(r"^##[ \t]+The ruling[ \t]*$", re.I | re.M)
RULING_WORDS = re.compile(r"ruling|owner|shiv", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
WORD = re.compile(r"[a-z]{4,}")
STOPWORDS = frozenset(("that", "this", "with", "from", "have", "will", "should", "would", "could", "there", "their",
                       "about", "which", "when", "what", "were", "been", "into", "than", "then", "them", "they",
                       "your", "also", "only", "does", "each", "more", "most", "must", "never", "other", "some",
                       "such", "same", "after", "before", "because", "owner", "ruling", "rulings"))
# An id a refusal may cite: `decisions/<stem>` or `debts/<stem>`.
RECORD_REF = re.compile(r"(?<![\w/-])(?:decisions|debts)/[\w.-]*\w")


def has_unvetted(text) -> bool:
    """True when the text carries an `Unvetted: <reason>` line: the question was sent knowingly unchecked."""
    return bool(UNVETTED_LINE.search(text or ""))


def _words(text) -> set:
    return set(WORD.findall(str(text).lower())) - STOPWORDS


def _ruling_text(body) -> str:
    """The whole `## The ruling` section (to the next `## `), else the body after the title line, white space
    collapsed and capped."""
    match = RULING_HEADING.search(body)
    if match:
        section = body[match.end():]
        nxt = re.search(r"^##[ \t]", section, re.M)
        text = " ".join((section[:nxt.start()] if nxt else section).split())
        if text:
            return text[:INDEX_CAP]
    lines = body.splitlines()
    if lines and lines[0].startswith("#"):
        lines = lines[1:]
    return " ".join(" ".join(lines).split())[:INDEX_CAP]


def _record_index(root, folder, unknown, label, seen):
    """(folder exists, index lines `<folder>/<stem>: <ruling>`) for the records of root/docs/<folder>. A record
    or folder that cannot be read adds an unreadable source to `unknown`."""
    path = os.path.join(root, "docs", folder)
    if not os.path.isdir(path):
        return False, []
    lines = []
    try:
        names = sorted(n for n in os.listdir(path) if n.endswith(".md") and n.lower() != "readme.md"
                       and not (folder == "debts" and n.lower() == "notes.md"))  # the notes file holds no ruling
    except OSError as exc:
        unknown.append("%s (%s: %s)" % (label, UNREADABLE, type(exc).__name__))
        return True, lines
    for name in names:
        record_id = "%s/%s" % (folder, name[:-3])
        if record_id in seen:
            continue
        try:
            with open(os.path.join(path, name), encoding="utf-8") as handle:
                body = handle.read()
        except (OSError, UnicodeDecodeError):
            unknown.append("%s (%s: %s)" % (label, UNREADABLE, name))
            continue
        seen.add(record_id)
        lines.append("%s: %s" % (record_id, _ruling_text(body)))
    return True, lines


def _tree_names(body, hash_size):
    """(name, hex sha) for each file entry of a raw git tree object."""
    out, pos = [], 0
    while pos < len(body):
        end = body.index(b"\0", pos)
        mode, _, name = body[pos:end].partition(b" ")
        sha = body[end + 1:end + 1 + hash_size]
        pos = end + 1 + hash_size
        if mode != b"40000":
            out.append((name.decode("utf-8", "replace"), sha.hex()))
    return out


def _read_steps(root):
    """({step id: (note, why)}, state) from roadmap/data/steps of the local ref `roadmap`, else `origin/roadmap`,
    through ONE `git cat-file --batch` process. state is "ok", "absent" (no repo, no ref or no folder) or
    "unreadable: <why>" (git failed, odd answer, bad JSON). Never fetches."""
    if _git_root_of(root) is None:
        return {}, "absent"
    import subprocess
    import _nowindow  # the one home of a no-window child start
    try:
        proc = _nowindow.Popen(["git", "-C", root, "cat-file", "--batch"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError:
        return {}, UNREADABLE + ": git did not start"
    try:
        entries = None
        for ref in ("roadmap", "origin/roadmap"):
            try:
                proc.stdin.write(("%s:roadmap/data/steps\n" % ref).encode())
                proc.stdin.flush()
            except BrokenPipeError:
                # git exited before it read the request; its stderr says why. The wait is bounded, and the
                # `finally` below kills and reaps the process on every path.
                proc.wait(timeout=STEP_GIT_TIMEOUT)
                if b"not a git repository" in proc.stderr.read(4096):
                    return {}, "absent"
                return {}, UNREADABLE + ": git exited early"
            head = proc.stdout.readline().split()
            if len(head) == 2 and head[1] == b"missing":
                continue
            if not head and b"not a git repository" in proc.stderr.read():
                return {}, "absent"  # a folder with a .git entry that is no repository holds no roadmap
            if len(head) != 3 or head[1] != b"tree":
                return {}, UNREADABLE + ": git gave no tree"
            body = proc.stdout.read(int(head[2]))
            proc.stdout.read(1)
            entries = [(n, s) for n, s in _tree_names(body, len(head[0]) // 2) if n.endswith(".json")]
            break
        if entries is None:
            return {}, "absent"
        out, _ = proc.communicate("".join(s + "\n" for _, s in entries).encode(), timeout=STEP_GIT_TIMEOUT)
        steps, pos = {}, 0
        for name, _sha in entries:
            nl = out.index(b"\n", pos)
            head = out[pos:nl].split()
            if len(head) != 3 or head[1] != b"blob":
                return {}, UNREADABLE + ": git gave no blob for " + name
            size = int(head[2])
            data = json.loads(out[nl + 1:nl + 1 + size].decode("utf-8"))
            pos = nl + 1 + size + 1
            if not isinstance(data, dict):
                return {}, UNREADABLE + ": bad JSON in " + name
            steps[name[:-5]] = (data.get("note"), data.get("why"))
        return steps, "ok"
    except Exception as exc:
        return {}, "%s: %s" % (UNREADABLE, type(exc).__name__)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for pipe in (proc.stdin, proc.stdout, proc.stderr):
            try:
                pipe.close()
            except Exception:
                pass


def _step_rulings(steps, words):
    """The top STEP_TOP ruling units of the step notes by word overlap with `words`, as `<step id>: <text>`
    lines. A unit is a sentence holding Ruling, owner or shiv, plus the sentence after it (a ruling's detail
    often sits there). Overlap 0 never counts."""
    scored = []
    for step_id, fields in sorted(steps.items()):
        sentences = [s for f in fields if isinstance(f, str) for s in SENTENCE_SPLIT.split(f.strip()) if s]
        for i, sentence in enumerate(sentences):
            if not RULING_WORDS.search(sentence):
                continue
            tail = sentences[i + 1] if i + 1 < len(sentences) and not RULING_WORDS.search(sentences[i + 1]) else ""
            unit = (sentence + " " + tail).strip()
            overlap = len(_words(unit) & words)
            if overlap:
                scored.append((-overlap, len(scored), "%s: %s" % (step_id, unit)))
    return [line for _, _, line in sorted(scored)[:STEP_TOP]]


def past_rulings(question_text, repo_root):
    """(candidates, unknown). `candidates` are lines `<id>: <text>`: every decision and debt record, then the step
    rulings that share words with the question. `unknown` lists each source not searched: "<source> (absent)"
    for a source the repo does not have, "<source> (unreadable: ...)" for one that exists and failed, and always
    "closed page items". Absent sources never refuse; unreadable ones do (see unreadable_sources)."""
    candidates, unknown, seen = [], [], set()
    roots = [repo_root]
    try:
        import guard_pointer  # the claude-settings checkout: the one home of the pointer line
        other = guard_pointer.pointer_checkout()
    except Exception:
        other = ""
    if not other:
        unknown.append("claude-settings decision records (absent)")
    elif os.path.realpath(other) != os.path.realpath(repo_root):
        roots.append(other)
    for folder, label in (("decisions", "decision records"), ("debts", "debt records")):
        found = False
        for root in roots if folder == "decisions" else roots[:1]:
            exists, lines = _record_index(root, folder, unknown, label, seen)
            found = found or exists
            candidates += lines
        if not found:
            unknown.append("%s (absent)" % label)
    steps, state = _read_steps(repo_root)
    if state == "ok":
        candidates += _step_rulings(steps, _words(question_text))
    elif state == "absent":
        unknown.append("roadmap step notes (absent)")
    else:
        unknown.append("roadmap step notes (%s)" % state)
    unknown.append(CLOSED_ITEMS)
    return candidates, unknown


def unreadable_sources(unknown) -> list:
    """The unknown sources that exist and failed to read: they refuse as Unvetted. Absent ones and the closed page
    items never do."""
    return [u for u in unknown if "(%s" % UNREADABLE in u]


def unknown_line(unknown) -> str:
    """The one stderr line for the sources not searched."""
    return "past-ruling search unknown: " + ", ".join(unknown)


def candidate_ids(candidates) -> list:
    return [c.split(": ", 1)[0] for c in candidates]


def candidates_block(candidates, unknown) -> str:
    """The text added after the judge prompt's reply line: the candidate rulings, then the sources not searched."""
    text = "\n\nPast rulings (item 8), one per line as `<id>: <text>`:\n" + (
        "\n".join(candidates) if candidates else "(none found)")
    if unknown:
        text += ("\nNot searched: %s. A source not searched never means the question is clear."
                 % ", ".join(unknown))
    return text


def ruling_cite(reason, ids, strict=False) -> str:
    """Classify a refusal reason against the ids the model was shown. "bogus" when the reason opens with a
    `decisions/..` or `debts/..` record that was not shown. With `strict` (a call that judges item 8 alone), also
    "bogus" when it names such a record anywhere, or names no shown id. "cited" when it names a shown id and is not
    bogus. "" for any other refusal (a form item): without `strict`, an unshown id named mid-reason stays one."""
    # `docs/decisions/<stem>.md` is the same record as `decisions/<stem>`.
    reason = re.sub(r"(?<=[\w-])\.md\b", "", re.sub(r"(?<![\w/-])docs/(?=(?:decisions|debts)/)", "", reason))

    def names(i):
        return re.search(r"(?<![\w/-])%s(?![\w/-])" % re.escape(i), reason)
    shown = [i for i in ids if names(i) or ("/" in i and names(i.split("/", 1)[1]))]
    opening = RECORD_REF.match(reason.lstrip(" \t\n*_`'\"([>"))
    if opening and opening.group(0) not in ids:
        return "bogus"
    if strict and [r for r in RECORD_REF.findall(reason) if r not in ids]:
        return "bogus"
    if shown:
        return "cited"
    return "bogus" if strict else ""


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _all_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _all_strings(v)


def chat_units(tool_input) -> list:
    """(marker text, words text) for each question of a box with 2+ options: the question text that may carry the
    Unvetted line, and every string of the question, for the word overlap."""
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    units = []
    for q in questions if isinstance(questions, list) else []:
        options = q.get("options") if isinstance(q, dict) else None
        if isinstance(options, list) and len([o for o in options if isinstance(o, dict)]) >= 2:
            units.append((str(q.get("question") or ""), " ".join(_all_strings(q))))
    return units


def page_units(judged) -> list:
    """(marker text, words text) for each write of `judged_item_writes`, a task too (every question is vetted).
    The marker text is the item's `context`, or a str_replace's new_str."""
    units = []
    for write in judged:
        data = write.get("data")
        if "new_str" in write:
            units.append((write["new_str"], write["new_str"]))
        elif isinstance(data, dict):
            units.append((str(data.get("context") or ""), " ".join(_all_strings(data))))
    return units


# ------------------------------------------------------------------ option keys: one letter, one question

# The key of an option line: `a)`, `(a)`, `a.`, `a:`, `**a**`, `**a)**`, with a bullet and a digit prefix (`1a`)
# allowed. The line must go on with text, so a sentence that opens with a one-letter word is no key. A bullet with
# a colon (`- a: 3 files`) is a list item, never a key.
OPTION_KEY = re.compile(r"^[ \t]*(?P<bullet>[-*+][ \t]+)?(?:\*\*|\()?(?P<key>\d*[A-Za-z])(?P<close>\)|\.|:|\*\*)"
                        r"(?:\*\*)?[ \t]+\S", re.M)


def _option_keys(reply) -> list:
    """(key, question line, option text) for each option line of the reply's Input Needed item. The question line
    is the last non-option line with a `?` before the option, else the item's first line. The option text is the
    line after its key. Both are lowercased with spaces folded."""
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.append(lint)
    from report_guard import input_needed_section  # the one reader of the Input Needed item
    found, asked, first = [], "", ""
    for line in input_needed_section(reply).splitlines():
        match = OPTION_KEY.match(line)
        if match and not (match.group("bullet") and match.group("close") == ":"):
            option = " ".join(line[match.end() - 1:].lower().split())
            found.append((match.group("key").lower(), asked or first, option))
            continue
        plain = " ".join(line.lower().split())
        if plain:
            first = first or plain
            asked = plain if "?" in plain else asked
    return found


def _same_question(one, other) -> bool:
    """True when two (question line, option text) pairs are one question sent again: the option texts are equal,
    and the question lines, reworded or not, share at least half of their words (lowercase words of 4+ letters,
    minus the stop words). Lines with no such word compare as text."""
    (one_q, one_option), (other_q, other_option) = one, other
    if one_option != other_option:
        return False
    a, b = _words(one_q), _words(other_q)
    return one_q == other_q or (bool(a | b) and len(a & b) * 2 >= len(a | b))


def key_overlap(reply, earlier_replies) -> str:
    """The option keys, comma joined, that two questions share. A key used twice in the Input Needed of `reply` is
    a clash. So is a key that an assistant reply since the last human message also uses under a different question
    line or option text. The same key, option text and question, reworded or not, is a question sent again, never a
    clash. '' when none clash."""
    seen, clash = {}, set()
    for key, question, option in _option_keys(reply):
        if key in seen:
            clash.add(key)
        seen.setdefault(key, (question, option))
    for earlier in earlier_replies:
        for key, question, option in _option_keys(earlier):
            if key in seen and not _same_question(seen[key], (question, option)):
                clash.add(key)
    return ", ".join(sorted(clash))
