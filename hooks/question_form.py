#!/usr/bin/env python3
"""The one question form and the one guard for both places a session asks the owner a question: the
chat question box (AskUserQuestion) and a write of a waiting-page item (ArtifactData). Decision
question-form holds the ruling; rule `style-question-form` holds the text.

    chat_hit(tool_input) -> (rule, matched)   an AskUserQuestion input; judges each question with 2+ options
    item_hit(op, entry)  -> (rule, matched)   one waiting-page write: set, update or str_replace

("", "") is a pass. hooks/call_judge.py calls chat_hit; hooks/guard.py data_tool_hit calls item_hit after
its url and collection guard. Nothing here writes a file or starts a process.

THE FORM. A decision on the page (in `context`), or a chat question with 2+ options (in `question`):

    Goal: <the goal, in the owner's terms>
    Problem (<stake>): <the problem in one plain sentence, and why it needs his word>
    Based on (<kind>): <one premise>                                  one to three lines

<stake> is one of OWNER_STAKES. A stood pick (`stands: true`) may write `Problem: <text>` with no stake.
<kind> is one of PREMISE_KINDS. Each option states its gain and its loss: page `gain` and `lose` fields;
chat `Gain:` and `Lose:` in the option's description. Only a line at a line start counts.

THE OLDER RULES keep their ids and run first, in this order, then the form:
`port-question`, `uniform-pick`, `press-link`, `command-in-item`, `task-names-check` (page items), then
the form. A missing Goal, Problem or Based on line, a Based on count outside 1-3, a kind outside
PREMISE_KINDS and an option with no gain or no loss refuse as `question-form`. A Problem line that is
bare, or whose stake is outside OWNER_STAKES, refuses as `owner-judge`.

An update is judged only for the fields it carries. A closed item passes the form: it asks the owner
nothing, and the chat-answer flow writes one. A str_replace on `context` that removes a form line is
refused.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from precompact_handoff import PREMISE_KINDS  # noqa: E402  the one home of the premise kinds

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
                "stands: true." % ", ".join(OWNER_STAKES))


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
    return PASS


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


# ------------------------------------------------------------------ a port question departs or is not asked
#
# docs/decisions/port-keeps-behaviour.md, rule `port-question`, built against a named incident
# (incident in the record): a waiting item about a port or redesign of an
# existing app carries a "Departs from:" line and never holds work, since the existing app answers
# the question. The item is read at the ArtifactData call that writes it.
PORT_WORD = re.compile(r"\b(?:ported|porting|port\s+of|port\s+to|ports\s+the|redesign(?:s|ed|ing)?"
                       r"|rewrite\s+of|rebuild\s+of)\b", re.I)
DEPARTS_LINE = re.compile(r"^\s*Departs from:", re.I | re.M)
PORT_REASON = ("A question about a port or redesign of an existing app is asked only when the work "
               "departs from the app, and it never holds work. Add a line to context that starts "
               "\"Departs from: <file>:<symbol> — <what changes>\", leave out holds, or set "
               "port to false if this is not a port.")


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
    return ""


def _write_data(entry):
    """The data of one write: `data`, else the JSON in `file_path`. None when neither reads."""
    data = entry.get("data")
    path = entry.get("file_path")
    if data is None and isinstance(path, str) and path:
        try:
            with open(path, encoding="utf-8") as f:
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
WIDENS_REASON = ("A pick never names an option that widens what a shared tool accepts: it goes against "
                 "the owner's uniform ruling (t18). Make the pick an option where the repo changes to "
                 "match the shared format, or leave pick out.")
CHAT_WIDENS_REASON = ("A recommended option never widens what a shared tool accepts: it goes against the "
                      "owner's uniform ruling (t18). Recommend an option where the repo changes to match "
                      "the shared format, and give the widening option no (Recommended) label.")
WIDENS_MARK = re.compile(r"Goes against your uniform ruling \(t18\)", re.I)
RECOMMENDED = re.compile(r"\(Recommended\)", re.I)


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
           and o.get("widens") is True for o in options):
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
COMMAND_REASON = ("A step never sends the owner to a file for a command. Put the command in the item's "
                  "`command` field, and say \"paste the command below\" in the step.")
# A press: press, click, tap in any form; an imperative approve, merge, hit, turn on at the start of
# a clause, `you` allowed before it (a command to the owner, so "the PR merged" and "to merge"
# pass); mark ... ready with a PR or #N as its object, or with "on <ref>" after ready. "press on"
# is not a press, and neither is a press of the waiting page's own buttons: it needs no link.
_CLAUSE = r"(?:^|[.;:!?\n]\s*|,\s*|\b(?:and|then|or|please)\s+)(?:you\s+)?"
_PAGE_BUTTON = r"(?!\s+(?:the\s+)?[\"'“‘]?(?:send|mark\s+done|take\s+my\s+pick)\b)"
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
# "the command in/from <file>" and "its command" (after a file step) point at a file. "run the
# command" and the like count only with no `command` on the item; "the command below" never does.
COMMAND_IN_FILE = re.compile(r"\bcommands?\s+(?:in|from|of|inside)\s+(?:the\s+|this\s+)?(?:file\s+)?(?:"
                             + _FILE + ")", re.I)
COMMAND_ITS = re.compile(r"\bits\s+commands?\b", re.I)
COMMAND_VERB = re.compile(r"\b(?:run|runs|copy|paste|execute|use|type)\b[^.\n]{0,40}\bcommands?\b(?!\s+below)"
                          r"|\bcommands?\s+(?:in|from|of|inside)\b", re.I)
EFFECT_TEXT = re.compile(r"\b(?:Gain|Lose):.*?(?=\b(?:Gain|Lose):|$)", re.I | re.S)
CHAT_URL = re.compile(r"https://[^\s)>\]\"']+", re.I)


def _flat_text(value) -> str:
    """One string from a step or option field: a string as is, a dict's string values joined."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(v for v in value.values() if isinstance(v, str))
    return ""


def _press_field_ok(text, links, context="") -> bool:
    """True when this field asks for no web press, or `links` holds a link to the exact page. The
    press verb is read in `text`. The page, and each `#N` that needs a url with /pull/N or
    /issues/N at a number boundary, is read in `text`, or in `context` when `text` names no page."""
    if not PRESS_VERB.search(text):
        return True
    page = text if WEB_MARKER.search(text) else context
    if not WEB_MARKER.search(page):
        return True
    urls = [l["url"] for l in links or [] if isinstance(l, dict) and isinstance(l.get("url"), str)]
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
            text = _flat_text(o.get("label")) + ". " + _flat_text(o.get("how"))
            if not _press_field_ok(text, o.get("links")):
                return "option presses in a web app with no link to the page"
    if isinstance(steps, list) and (op == "set" or "links" in data):
        # the steps are one text, as command-in-item reads them: the page may sit in one step and
        # the press in another. The title names the page only when the steps name none, and a
        # title alone never makes a press.
        joined = "\n".join(_flat_text(s) for s in steps)
        if not _press_field_ok(joined, data.get("links"), _flat_text(data.get("title"))):
            return "step presses in a web app with no link to the page"
    return ""


def command_in_item_hit(data) -> str:
    """The matched text when a task's steps, joined, send the owner to a file for a command. A
    `command` on the item does not excuse it: the step still points at the file."""
    if not isinstance(data, dict) or data.get("kind", "task") != "task":
        return ""
    steps = data.get("steps")
    if not isinstance(steps, list):
        return ""
    joined = "\n".join(_flat_text(s) for s in steps)
    has_file = COMMAND_FILE.search(joined)
    has_command = isinstance(data.get("command"), str) and data["command"].strip()
    if COMMAND_IN_FILE.search(joined) or (has_file and COMMAND_ITS.search(joined)) \
            or (has_file and not has_command and COMMAND_VERB.search(joined)):
        return "steps send the owner to a file for a command"
    return ""


# ------------------------------------------------------------------ a task names why only the owner can do it
#
# docs/decisions/task-names-its-check.md, rule `task-names-check`, built against a named incident
# (incident in the record): a waiting-page task handed the owner a job a session on his computer then
# did. A task carries a "Why yours:" line naming the check that showed no session could do it.
WHY_YOURS_LINE = re.compile(r"^\s*Why yours:[ \t]*\S", re.I | re.M)
TASK_REASON = ("A task is yours to hand over only when no session can do it. If the cloud refused the "
               "act, ask a session on the owner's computer first (list_computer_folders, then "
               "request_computer_folder). Then add a line to context that starts \"Why yours: "
               "<the check that showed no session could do it>\".")


def task_check_hit(op: str, data) -> str:
    """The matched text when this write of a waiting-page task has no Why yours line. An update that
    carries no `context` cannot change the line and passes, as does one with no `kind`."""
    if not isinstance(data, dict) or data.get("kind") != "task":
        return ""
    if (op == "set" or "context" in data) and not WHY_YOURS_LINE.search(str(data.get("context") or "")):
        return "task with no Why yours line"
    return ""


def task_str_replace_hit(entry) -> str:
    """The matched text when a str_replace on `context` removes the Why yours line. It carries no
    `data`, so it is read from old_str and new_str; the guard cannot see the stored kind, so it
    judges a context edit that touches the line, whatever the item's kind."""
    if entry.get("field") != "context":
        return ""
    old, new = str(entry.get("old_str") or ""), str(entry.get("new_str") or "")
    if WHY_YOURS_LINE.search(old) and not WHY_YOURS_LINE.search(new):
        return "context edit that removes the Why yours line"
    return ""


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
    if op == "set" or "context" in data:
        hit = _lines_hit(str(data.get("context") or ""), data.get("stands") is True)
        if hit[0]:
            return hit
    options = data.get("options")
    if (op == "set" or "options" in data) and isinstance(options, list):
        return _effects_hit([("%d" % i, _filled(o.get("gain")), _filled(o.get("lose")))
                             for i, o in enumerate(options, 1) if isinstance(o, dict)])
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
    return PASS


def item_hit(op, entry):
    """(rule, matched) for one write of a waiting item that a rule refuses, else ("", "")."""
    if op == "str_replace":
        hit = task_str_replace_hit(entry)
        if hit:
            return "task-names-check", hit
        return form_str_replace_hit(entry)
    data = _write_data(entry)
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
    hit = task_check_hit(op, data)
    if hit:
        return "task-names-check", hit
    return decision_form_hit(op, data)


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
        links = [{"url": u} for u in CHAT_URL.findall(desc)]
        # the page scans label and how; Gain and Lose text says what the pick does to the owner, not what he presses
        if not _press_field_ok(label + ". " + EFFECT_TEXT.sub("", desc), links):
            return "press-link", "option presses in a web app with no url to the page"
    hit = _lines_hit(str(question.get("question") or ""))
    if hit[0]:
        return hit
    return _effects_hit([("'%s'" % (_option_text(o, "label") or i), bool(GAIN_TEXT.search(_option_text(o, "description"))),
                          bool(LOSE_TEXT.search(_option_text(o, "description"))))
                         for i, o in enumerate(options, 1)])


# ------------------------------------------------------------------ the reasons, one table per surface

PAGE_REASONS = {"port-question": PORT_REASON, "uniform-pick": WIDENS_REASON, "press-link": PRESS_LINK_REASON,
                "command-in-item": COMMAND_REASON, "task-names-check": TASK_REASON,
                FORM_RULE: PAGE_FORM_REASON, STAKE_RULE: STAKE_REASON}
CHAT_STAKE_REASON = ("A question is the owner's only when he can judge it. Write the Problem line as "
                     "\"Problem (<stake>): <the problem, and why it needs his word>\", where stake is one of %s."
                     % ", ".join(OWNER_STAKES))
CHAT_REASONS = {"uniform-pick": CHAT_WIDENS_REASON, "press-link": CHAT_PRESS_LINK_REASON,
                FORM_RULE: CHAT_FORM_REASON, STAKE_RULE: CHAT_STAKE_REASON}
