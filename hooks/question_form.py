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
`item-field-rendered` (a field the page draws), `port-question`, `uniform-pick`, `press-link`, `command-in-item`,
`gh-login-switch`, `task-names-check` (page items), then the form. A missing Goal, Problem or Based on line, a
Based on count outside 1-3, a kind outside
PREMISE_KINDS and an option with no gain or no loss refuse as `question-form`. A Problem line that is
bare, or whose stake is outside OWNER_STAKES, refuses as `owner-judge`.
The page writer's last two rules run after the form: `option-letter-keys` (an option's key is its
position's letter) and `rework-off-page` (an open item never says it is being reworked).

An update is judged only for the fields it carries. A closed item passes the form: it asks the owner
nothing, and the chat-answer flow writes one. A str_replace on `context` that removes a form line is
refused.
"""
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
COMMAND_REASON = ("A step never sends the owner to a file for a command, and never holds one. Put the "
                  "command in the item's `command` field as {powershell, mac}: a PowerShell 5.1-safe "
                  "string (no &&, ||, <<, <<<, /dev/null or export) and a bash or zsh string for the Mac, both non-empty. "
                  "Say \"paste the command below\" in the step.")
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
COMMAND_SHELLS = ("powershell", "mac")
PS_BASH_OPERATOR = re.compile(r"&&|\|\||<<|/dev/null|(?:^|;)\s*export\s", re.M)
# A shell line in a step's backtick span or fence: it chains with an operator, its first word is a
# Verb-Noun cmdlet, or its first word is a program the owner would run with an argument after it. A
# program alone (`git`) names the tool in prose, and any other backticked word (`main`) or a file name
# is not a shell line. A path that starts ./ or ../ is a shell line when an argument follows it, when
# its name has no extension (`./build`), or when it ends in a script extension and a run verb comes
# before the span in its sentence, or the span is a fence. `./docs/a.md` and an edited
# `./hooks/guard.py` are files.
SHELL_PROGRAMS = frozenset(("git", "gh", "cd", "npm", "npx", "node", "python", "python3", "pip", "curl",
                            "brew", "bash", "sh", "zsh", "pwsh", "powershell", "claude", "rm", "mv", "cp",
                            "ls", "cat", "echo", "export", "sudo", "make", "pytest", "docker", "mkdir",
                            "gcloud", "bq", "winget"))
SHELL_CMDLET = re.compile(r"[A-Z][a-z]+-[A-Z][A-Za-z]+")
SHELL_OPERATOR = re.compile(r"&&|<<<|[|;]")
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


def _shell_line(span, run) -> bool:
    """True when a line of this code span is a shell line (see SHELL_PROGRAMS). `run` is as for
    _relative_run."""
    for line in span.splitlines():
        words = line.split()
        if SHELL_OPERATOR.search(line):
            return True
        if not words:
            continue
        if words[0].startswith(("./", "../")):
            if _relative_run(words, run):
                return True
        elif SHELL_CMDLET.fullmatch(words[0]) or (len(words) >= 2 and words[0] in SHELL_PROGRAMS):
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
    if has_command and PS_BASH_OPERATOR.search(data["command"]["powershell"]):
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
    if any(_shell_line(body, fenced or bool(SPAN_RUN_VERB.search(text[:start])))
           for text in texts for start, body, fenced in _code_spans(text)):
        return "step holds a shell line"
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


def gh_login_hit(data) -> str:
    """The matched text when a task's `command` runs a gh command other than `gh auth ...` with no
    `gh auth switch -u <a login in GH_LOGINS>` before it, or runs one as GH_FALLBACK_LOGIN while the
    command names a GH_DEFAULT_LOGIN repo. A segment the shell reader cannot parse counts as a gh
    command when the word gh is in it, and never as a switch: the check fails closed there.

    Bash's rules read the command. When bash cannot read some segment and PowerShell's rules read
    every one, the command is a PowerShell block and PowerShell's reading is judged: there `\\` is a
    path character, so `Set-Location "C:\\repo\\"` closes its quote."""
    if not isinstance(data, dict) or data.get("kind", "task") != "task":
        return ""
    command = data.get("command")
    if not isinstance(command, str) or not GH_WORD.search(command):
        return ""
    # guard_core holds the one quote-aware shell reader, for bash and PowerShell. It loads here, so the
    # chat-box path loads nothing more.
    import guard_core
    # The script type picks the rules, never the tool this call came from.
    reading = _shell_reading(guard_core, guard_core.PosixScript(command))
    if any(tokens is None for _, tokens in reading):
        powershell = _shell_reading(guard_core, guard_core.PowerShellScript(command))
        if all(tokens is not None for _, tokens in powershell):
            reading = powershell
    names_default_repo = (GH_DEFAULT_LOGIN + "/").lower() in command.lower()
    login = ""
    for segment, tokens in reading:
        if tokens is None:
            if not GH_WORD.search(segment):
                continue
            calls = [None]   # unreadable text that names gh: a gh command, never a switch
        else:
            calls = [tokens[i:] for i in guard_core.command_indexes(tokens)
                     if guard_core.basename(tokens[i]) in ("gh", "gh.exe")]
        for call in calls:
            if call is not None and list(call[1:2]) == ["auth"]:
                if list(call[2:3]) == ["switch"]:
                    login = _switch_login(list(call[3:]))
                continue
            if login not in GH_LOGINS:
                if login:
                    return "gh command after a switch to %s, a login outside the pair" % login
                return "gh command with no gh auth switch before it"
            if login == GH_FALLBACK_LOGIN and names_default_repo:
                return "gh command as %s on a %s/ repo" % (GH_FALLBACK_LOGIN, GH_DEFAULT_LOGIN)
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
    data = _write_data(entry)
    hit = item_field_hit(op, entry, data)
    if hit:
        return "item-field-rendered", hit
    if op == "str_replace":
        hit = task_str_replace_hit(entry)
        if hit:
            return "task-names-check", hit
        if entry.get("field") == "command":
            # The stored command is unseen, so new_str is judged as the whole command.
            hit = gh_login_hit({"command": entry.get("new_str")})
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
    if hit:
        return "task-names-check", hit
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
                      "item's text by that letter (option A, pick b), never by any other key.")


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


def option_letter_hit(op: str, data) -> str:
    """The matched text when this write of a waiting-page decision keys an option by anything but its
    position's letter, or names an option in its text by a letter-and-digit key. A task, a note and a
    closed item pass; an update that carries no `options` has no keys to judge."""
    if not isinstance(data, dict) or data.get("kind", "decision") != "decision":
        return ""
    if data.get("status") == "closed":
        return ""
    options = data.get("options")
    if isinstance(options, list):
        seen = set()
        for i, o in enumerate(options):
            key = o.get("key") if isinstance(o, dict) else None
            if not isinstance(key, str):
                return "option with no string key"
            if key == OPTION_NONE_KEY:
                return "option keyed none"
            if key in seen:
                return "option key that repeats"
            seen.add(key)
            if key != _letter_of(i):
                return "option key that is not its position's letter"
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
                     "with {\"__delete__\": true}.")


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
                "command-in-item": COMMAND_REASON, "gh-login-switch": GH_LOGIN_REASON,
                "task-names-check": TASK_REASON,
                FORM_RULE: PAGE_FORM_REASON, STAKE_RULE: STAKE_REASON, "item-field-rendered": ITEM_FIELD_REASON,
                "option-letter-keys": LETTER_KEYS_REASON, "rework-off-page": REWORK_REASON}
CHAT_STAKE_REASON = ("A question is the owner's only when he can judge it. Write the Problem line as "
                     "\"Problem (<stake>): <the problem, and why it needs his word>\", where stake is one of %s."
                     % ", ".join(OWNER_STAKES))
CHAT_REASONS = {"uniform-pick": CHAT_WIDENS_REASON, "press-link": CHAT_PRESS_LINK_REASON,
                FORM_RULE: CHAT_FORM_REASON, STAKE_RULE: CHAT_STAKE_REASON}
