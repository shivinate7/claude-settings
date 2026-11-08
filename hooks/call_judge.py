#!/usr/bin/env python3
"""PreToolUse judge for an Agent spawn, an AskUserQuestion call, an ArtifactData write of a
waiting-page item and an owner question sent to a session. One command hook replaces the settings.json `prompt` hook on Agent and the `agent`
hook on AskUserQuestion. A prompt hook sees only the call's JSON. An agent hook reads files with tools and
returns ok. Neither has a command field, so neither runs guard_core.refuse, the one home of the owner
override (decision owner-override).

An AskUserQuestion box runs hooks/question_form.py chat_hit first. A hit refuses with the rule it
names, through the same refuse(), and makes no model call; the model sees only a box that passes.
Each call that passes gets one model verdict through decision_watch.invoke_model, the one model caller.
A verdict {"ok": false, "reason": R} refuses through guard_core.refuse(), the one home of the override
check, the override line and the guard.log line. The rules are `spawn-judge` and `question-judge`.

An ArtifactData call exits first unless its action is set, update, str_replace or batch, before any heavy import.
A call with no write on collection `items` exits before importing question_form.
For the rest, question_form.page_item_hit picks the item writes of this repo's waiting page. A write
that item_hit refuses gets no model call: guard.py refuses it. The writes that pass and carry options,
context or steps (question_form.judged_item_writes) go into one prompt, so the call makes one model call, however
many writes a batch holds. A write that is a re-ask (new `options` plus a `lastAnswer` note) adds NONE_DIRECTION_RULE
to that one prompt, once. A set or update with non-empty `options` adds WIDENING_RULE once: an option that widens what a
shared tool accepts must carry `widens: true`, and the judge refuses an unmarked one by its option key (decision
uniform-over-variants). WIDENING_RULE is built from question_form.WIDENS_KEY on each read (module `__getattr__`, no cache), so an
Agent spawn or a non-item ArtifactData call never imports question_form for it. No other write changes the prompt. The page and the chat box share judge items 1 to 7; item 8 has its own call on the page (below). A task item (kind task, or any write that carries `steps`) that carries context, steps or
options is judged too, on the same items and one task rule in PAGE_PROMPT: a step that replaces text
quotes the whole line or value and shows the line after the change in full. A str_replace on `context`
that passes item_hit is judged on its new_str alone, as a fragment: the prompt tells the model to judge
only plain words, unexplained ids and pointers outside the item, and never to flag a missing line or
option. The ArtifactData str_replace field is one top-level string key, so only `context` occurs in
practice (note page-judge-dead-fragment-fields).

Veto (an act no override lifts): an Explore spawn whose model field is neither sonnet nor opus. That
is the Explore row of agent-model-cap, a model guard. Every other refusal is liftable.

A question also gets item 8, the past-ruling check: question_form.past_rulings finds the decision, debt and step
rulings it reads. The check always runs; a task gets it too. A chat box carries item 8 in its one model call. Two
other paths have a dedicated call, lint/report_guard.py past_ruling_problem (the one past-ruling judge, also the
Stop hook's): Sonnet, item 8 alone, PAST_RULING_TIMEOUT s.
  Page item write: the dedicated call runs first. A refusal denies with rule `past-ruling` and the relay remedy
  and makes no form-judge call. Otherwise the form judge (Opus, items 1 to 7) runs, and its prompt holds no item 8.
  Every write's text reaches the dedicated call, uncut. Each question needs its own `Unvetted:` line to pass a check
  that could not run, and a form-judge error refuses as Unvetted too.
  Owner-question send: a `mcp__claude-code-remote__send_message` or `SendMessage` whose message holds a Goal line
  and a Problem line (question_form.GOAL_LINE, PROBLEM_LABEL; the Problem line needs no stake) gets the dedicated
  call before it is sent, whoever the target is. A refusal is rule `past-ruling`. Any other send exits before a heavy
  import. The form lines are read outside code, after the marks a page uses (bold, bullet, heading, quote) are cut.
  Cap rule (send_question): a message over report_guard.ASK_TEXT_MAX characters goes as that many characters from its
  first form line (Goal, Problem, Based on or Departs from). Each question in a send needs its own `Unvetted:` line,
  read in the whole message, one unit per Goal/Problem pair.
When the check cannot run (a model error, a source that exists and cannot be read, or a refusal that cites a record
the model was not shown), the question is refused with the Unvetted remedy, unless its own text carries an
`Unvetted:` line. An absent source allows, with one stderr line.

Fail open. Any other model error, odd answer or unreadable input allows, with one stderr line.

Cost (rule outcomes-mechanize-rules): a send without the form, a read, and a write of another collection start
no process and make no model call. A send with the form: one git process (question_form.past_rulings) and one Sonnet
call. A judged item write: one git process, the dedicated Sonnet call, and then the form judge's Opus call, so one more
Sonnet call than before. A chat box: one git process and one Opus call, as before. Nothing is written but the
guard.log line of a refusal. test_call_judge.py counts the processes and the calls.

One exception, opus_ask(): the owner's plain Opus ask (decision owner-override, the Opus word) fails CLOSED. It grants
an override, so a model error, a timeout or an odd answer grants nothing, with one stderr line. override.grant_opus_ask
calls it, from the prompt hook hooks/local_time.py, only for an owner prompt that carries the whole word `opus` and
no keyword form. Cost: one haiku call (low effort, OPUS_ASK_TIMEOUT s) for such a prompt, none for any other.
Its companion opus_scope() only narrows: for a plain ask that opus_ask said yes to, that names no role, and that has
earlier owner prompts, it names the roles those prompts name. It fails OPEN to every role (None) with one stderr line,
because the rule is "scope from context, fall back to every role" (decision owner-override).
Cost: one more haiku call (low effort, OPUS_SCOPE_TIMEOUT s) for such an ask, none for any other.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# The audit marker comes from shared_names, the home guard.py also imports it from (rule
# building-allow-list-is-the-constant). Cost: importing guard.py for it measured about 120 ms per Agent spawn;
# shared_names is standard library only and adds about 2 ms.
from shared_names import EXPLORE_AUDIT_MARKER  # noqa: E402
from shared_names import DATA_TOOL, SEND_TOOLS  # noqa: E402  stdlib only: the one home of the tool names

OK_SHAPE = {"ok": (True, False)}
SPAWN_RULE, QUESTION_RULE = "spawn-judge", "question-judge"
# The record each refusal cites. The spawn judge has its own; every other rule here (the model's question verdict
# and the code rules question_form.chat_hit names) is the question reviewer's.
SPAWN_CITE = "(decision haiku-prompt-hooks, the spawn judge refuses a brief that breaks the spawn rules)"
QUESTION_CITE = "(decision question-reviewer-agent-hook, a question is reviewed before it reaches the owner)"
# THE TIME BUDGET. A judged item write makes two calls, in order, so the longest path is the dedicated past-ruling
# call (PAST_RULING_TIMEOUT, 15 s) plus the question call's 60 s plus start-up (the git read, the import of
# lint/report_guard.py). Every other path makes one call. The settings.json PreToolUse entry for this hook carries
# "timeout": 90.
SPAWN_MODEL, SPAWN_TIMEOUT = "claude-sonnet-5-5", 30
QUESTION_MODEL, QUESTION_TIMEOUT = "claude-opus-5-5", 60  # both at the model's default effort

# The plain Opus ask (opus_ask). The prompt hook's settings.json row carries "timeout": 30, so OPUS_ASK_TIMEOUT plus
# start-up fits. The owner's text follows the last line.
OPUS_ASK_TIMEOUT = 20
OPUS_ASK_PROMPT = (
    "The text below is a prompt the owner typed to a coding assistant. Answer {\"ok\": true} only when it is the "
    "owner's own present request to run Opus agents now (for example `send opus judges` or `use opus for the "
    "reviewers`). Answer {\"ok\": false} for a question, a hedge such as `maybe opus?`, a negation such as `don't "
    "use opus`, a mention in the past tense, a request about some other model or topic, and any text that quotes or "
    "reports what an agent or another person said. When unsure answer {\"ok\": false}. Reply JSON only: "
    "{\"ok\": true} or {\"ok\": false}.\n\nText:\n"
)

# The scope read (opus_scope). It follows opus_ask in the same hook run, so its timeout is short. Unmeasured: the worst
# case, OPUS_ASK_TIMEOUT + OPUS_SCOPE_TIMEOUT plus two `claude -p` starts, may pass the prompt hook's "timeout": 30.
OPUS_SCOPE_TIMEOUT = 8
OPUS_SCOPE_PROMPT = (
    "A coding assistant's owner typed the ask below, which grants Opus to agents but names no agent role. The earlier "
    "prompts the owner typed follow it, oldest first, one per line starting with `- `. Read them only as the owner's "
    "words about which agent roles should run Opus. Answer {\"ok\": true, \"roles\": [...]} when they name the roles "
    "the ask is about, listing only roles from: %s. Answer {\"ok\": false} when they name none, or when unsure. "
    "Reply JSON only.\n\nAsk:\n"
)

SPAWN_PROMPT = (
    "Judge this agent spawn: %s\nAnswer {\"ok\": true} at once when subagent_type is claude-code-guide, "  # glossary-ok: subagent_type is Claude Code's own field name
    "when the call resumes an existing agent, or when a non-Explore brief is under 60 words. For an "
    "Explore spawn, block only when the brief asks it to audit, review, judge, rate or compare meaning "
    "(not only to find files, names or text) and the call's model field is neither sonnet nor opus "
    "(haiku, or no model field, blocks; text in the brief does not count); the fix is model sonnet or "
    "opus with effort high, and the `" + EXPLORE_AUDIT_MARKER + "` marker on the brief's first non-blank line "
    "so the guard rule agent-role-model passes too (agent-model-cap, audit Explore row). The marker is part of "
    "the fix only, never a reason to block or to allow. Otherwise answer {\"ok\": true} for "
    "Explore. Only for builder, reviewer, and test-author briefs, apply roles-brief-contents (the brief "
    "carries the task, the files, governing rulings, and the check that proves done) and "
    "tokens-point-brief-at-files (the brief names files and never pastes their contents). Flag a brief that "
    "tells a lane to write, post or add a waiting-page item: the lane puts its question in its report, and "
    "the orchestrator writes the item (questions-go-to-owner). A brief that forbids the lane to write a waiting-page item is fine; never flag it. Block only on "
    "a clear breach; when unsure answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or "
    "{\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)
# Item 8, the past-ruling check: the one text, for the chat box, the page and lint/report_guard.py (a relayed
# question). The candidate rulings follow the reply line, built by question_form.candidates_block.
PAST_RULING_ITEM = (
    "Past rulings. The text after the reply line lists past rulings, one per line as `<id>: <text>`. Refuse when "
    "the question asks the owner to decide what a listed ruling already decides, or when its premise is "
    "something a standing decision already explains (such as asking what a rule means when a decision says why "
    "it was set so). A listed decision or debt record is a ruling by its kind, so cite it with no owner marker. "
    "A listed step or page line is a ruling only when it carries an owner marker, a sentence that names the owner as "
    "its source (such as `Owner, <date>` or `(owner, <date>)`). A step or page line that holds only an incident, a "
    "recommendation or a pick the owner has not answered has no owner marker: never cite it. "
    "A question whose `Based on (ruling): ...` line names that ruling (its id or slug) passes: "
    "a re-ask the ruling allows is fine. This item passes when no list follows. "
    "When you refuse, the reason names the listed id, such as decisions/<name>, and gives the ruling's date."
)
# The question-judge call of lint/report_guard.py (a Stop whose reply asks the owner something): Sonnet, 15 s.
PAST_RULING_MODEL, PAST_RULING_TIMEOUT = SPAWN_MODEL, 15
# The seven items a question to the owner is judged on, for the chat box and the page. The eighth is the chat box's
# alone: the page and a send get it as a dedicated call (past_ruling_check).
ITEMS_1_TO_7 = (
    "1. The Goal is in the owner's terms.\n"
    "2. The Problem is one plain sentence that says why it needs his word.\n"
    "3. Each premise is in plain words.\n"
    "4. Each option's gain and lose are plain effects on the owner, not on a record.\n"
    "5. No unexplained ids: explain every decision id, branch, sha, key or rule name in plain words.\n"
    "6. Nothing points outside the box, such as an earlier message or an item number.\n"
    "7. One option is recommended.\n"
)
REPLY_JSON = (
    "Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<the item that misses, and the fix, "
    "one line>\"}."
)
JUDGE_ITEMS = ITEMS_1_TO_7 + "8. " + PAST_RULING_ITEM + "\n" + REPLY_JSON
PAGE_ITEMS = ITEMS_1_TO_7 + REPLY_JSON
QUESTION_PROMPT = (
    "Review this AskUserQuestion call: %s\nAnswer {\"ok\": true} at once for a question with one option "
    "or none. Otherwise judge the question box alone. Code has already checked the form lines and the "
    "marks on each option, so judge only these. Block only on a clear miss; when unsure answer "
    "{\"ok\": true}.\n" + JUDGE_ITEMS
)
# A page write carries only the fields it changes, so the prompt names the fields and judges only those.
PAGE_PROMPT = (
    "Review these writes of a waiting-page item, each as {op, doc_id, data}: %s\nThe item is a question to "
    "the owner. Its `context` holds the Goal, Problem and Based on lines. Each entry of `options` has a "
    "label, a `gain` and a `lose`. `pick` is the recommendation. Code has already checked the form lines "
    "and the marks on each option, so judge only the items below, and only the fields a write carries: a "
    "write with no `options` is not flagged for options, one with no `context` is not flagged for the "
    "Goal, Problem or premises, and one with no `pick` is not flagged for item 7, because the stored item "
    "is unseen. A write with op str_replace carries only `field` and `new_str`, a fragment of that field. "
    "Judge a fragment only for plain words, unexplained ids, and pointers outside the item (items 3 to 6), "
    "and never flag a missing line or option, because the rest of the item is unseen. A task item has "
    "`context` (the Why yours line) and `steps` (the text the owner reads and follows), and may carry "
    "options. Judge a task's `steps` and `context` on the items below, and on one more rule: a step that "
    "tells the owner to replace text quotes the whole unit it replaces, the whole line or the whole value, "
    "and shows the line after the change in full. A step that names only the changed part, such as "
    "\"find X and change it to Y\", misses that rule, because the owner then drops the rest of the line. "
    "That rule reaches a task's `steps` and `context` on a set or update; a str_replace reaches only the "
    "top-level string field `context`, never `steps`. A task item is judged only on plain words, "
    "unexplained ids, pointers outside the item and that whole-unit rule, and never on the Goal, "
    "the Problem or a recommended option, because a task has none of them. "
    "Block only on a clear miss; when unsure answer {\"ok\": true}.\n" + PAGE_ITEMS
)
# A re-ask write gives an answered item new options and carries the owner's `lastAnswer` note. The text is appended to
# the formatted PAGE_PROMPT, only for such a call (skill waiting-page, "Route and close"). It has no `%`, so it is
# never formatted.
NONE_DIRECTION_RULE = (
    "This call includes a re-ask: a write that gives an item new options and carries a `lastAnswer` note, so it asks "
    "the owner again after a \"none of these\" answer. A note that asks for other choices (cheaper, different, more) "
    "is always allowed, even with other words. Otherwise, if the note already names an act a session can take with no "
    "further pick from the owner, block it: the item should close and the note be filed as a step. "
    "The reason names no target."
)
# A write that sets options may widen what a shared tool accepts (decision uniform-over-variants). Appended like
# NONE_DIRECTION_RULE, only for such a call. The mark's key comes from question_form, the one home, so the text is built
# where it is used: the light-import exit paths never import question_form for it.
WIDENING_TEMPLATE = (
    "This call sets options. An option that widens what a shared tool accepts (a second accepted form, an allow-list "
    "entry, a per-repo exception) must carry `%s: true`, the JSON boolean true, not the string \"true\". Block an unmarked widening option, and name its option key in "
    "the reason. An option that only names a repo, or changes a repo to fit the shared tool, is not widening. A marked "
    "option passes this rule. When unsure, allow."
)


def widening_rule():
    """The widening rule's text, with the mark's key from question_form.WIDENS_KEY."""
    import question_form
    return WIDENING_TEMPLATE % question_form.WIDENS_KEY


def __getattr__(name):  # PEP 562: the module constant WIDENING_RULE costs no import until it is read
    if name == "WIDENING_RULE":
        return widening_rule()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# tool name -> (prompt, model, timeout, rule, fallback reason)
JUDGES = {
    "Agent": (SPAWN_PROMPT, SPAWN_MODEL, SPAWN_TIMEOUT, SPAWN_RULE,
              "the spawn brief breaks roles-brief-contents or the Explore row of agent-model-cap "
              "(an audit Explore: model sonnet or opus with effort high, and `" + EXPLORE_AUDIT_MARKER
              + "` on the brief's first non-blank line)."),
    "AskUserQuestion": (QUESTION_PROMPT, QUESTION_MODEL, QUESTION_TIMEOUT, QUESTION_RULE,
                        "the question box misses an item of the question format."),
    DATA_TOOL: (PAGE_PROMPT, QUESTION_MODEL, QUESTION_TIMEOUT, QUESTION_RULE,
                "the waiting-page item misses an item of the question format."),
}
# The ArtifactData actions that write an item. Any other action exits before a heavy import.
PAGE_WRITE_ACTIONS = ("set", "update", "str_replace", "batch")


def writes_an_item(args):
    """True when the call has a write on collection `items`. Plain dict reads, so no heavy import."""
    if args.get("action") == "batch":
        writes = args.get("writes")
        return any(isinstance(w, dict) and w.get("collection") == "items" for w in writes or [])
    return args.get("collection") == "items"


def sets_options(write):
    """True for a judged set or update whose data has non-empty `options`."""
    data = write.get("data") if write.get("op") in ("set", "update") else None
    return isinstance(data, dict) and bool(data.get("options"))


def is_reask(write):
    """True for a judged set or update whose data has non-empty `options` and a `lastAnswer` dict with no `choice` or
    choice "none", no `done`, and a note that is a string, non-empty after strip."""
    if not sets_options(write):
        return False
    data = write["data"]
    answer = data.get("lastAnswer")
    if not isinstance(answer, dict) or answer.get("choice", "none") != "none":
        return False  # step 4 keeps a picked choice: that write is no "none of these" re-ask
    if "done" in answer:
        return False  # a task's answer: it gives no "none of these" direction
    note = answer.get("note")
    return isinstance(note, str) and bool(note.strip())


def invoke_model(*args, **kwargs):
    """The model call. A module-level name, so a test can replace it."""
    from decision_watch import invoke_model as home
    return home(*args, **kwargs)


def opus_ask(text):
    """True only when the model answers {"ok": true} to the owner's prompt `text` as a present request to run Opus
    agents. Fails closed: an error, a timeout or an odd answer is False with one stderr line; a plain
    {"ok": false} is False with none."""
    try:
        import decision_watch  # lazy: the one home of the model's name
        verdict, error = invoke_model(OPUS_ASK_PROMPT + text, model=decision_watch.MODEL,
                                      timeout=OPUS_ASK_TIMEOUT, shape=OK_SHAPE, effort="low")
        if error:
            raise ValueError(" ".join(str(error).split()))
        ok = verdict.get("ok") if isinstance(verdict, dict) else None
        if ok is True:
            return True
        if ok is not False:
            raise ValueError("the answer has no true or false ok")
        return False
    except Exception as exc:
        print("call judge: opus ask grants nothing: %s" % " ".join(str(exc).split()), file=sys.stderr)
        return False


def opus_scope(text, context):
    """The roles the owner's earlier prompts `context` (a list of strings, oldest first) name for the plain ask `text`,
    as the model's raw role strings (a list), or None for every role. Fails open to None with one stderr line: an
    error, a timeout or an odd answer. It does not filter: override._scoped_roles is the one filter, against ASK_ROLES."""
    try:
        import decision_watch  # lazy: the one home of the model's name
        from override import ASK_ROLES  # the one home of the roles; a copy would drift
        prompt = (OPUS_SCOPE_PROMPT % ", ".join(ASK_ROLES) + text + "\n\nEarlier prompts:\n"
                  + "\n".join("- " + " ".join(entry.split()) for entry in context))
        verdict, error = invoke_model(prompt, model=decision_watch.MODEL, timeout=OPUS_SCOPE_TIMEOUT,
                                      shape=OK_SHAPE, effort="low")
        if error:
            raise ValueError(" ".join(str(error).split()))
        if verdict.get("ok") is not True:
            return None
        roles = verdict.get("roles")
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise ValueError("the answer has no list of roles")
        return roles
    except Exception as exc:
        print("call judge: opus scope grants every role: %s" % " ".join(str(exc).split()), file=sys.stderr)
        return None


def explore_off_model(tool, args):
    """True for an Explore spawn whose model field is neither sonnet nor opus: a model guard."""
    if tool != "Agent" or str(args.get("subagent_type")).strip().lower() != "explore":
        return False
    model = str(args.get("model") or "").lower()
    return "sonnet" not in model and "opus" not in model


def refuse(payload, tool, args, rule, reason):
    """Refuse through guard_core.refuse(), which lets an owner override lift it. refuse() exits."""
    reason = reason.strip()
    if reason.startswith(rule):
        reason = reason[len(rule):].lstrip(" :-")
    vetoed = explore_off_model(tool, args)
    text = reason + " " + {SPAWN_RULE: SPAWN_CITE}.get(rule, QUESTION_CITE)  # the text both paths below carry
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_override_veto(lambda: vetoed)
        guard_core.refuse(tool, "deny", rule, text, "")
    except Exception:  # no guard_core: no override can be read, so the refusal stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": rule + ": " + text}}))
    return 0


UNVETTED_REMEDY = (
    "the past-ruling check could not run (%s), so this question would reach the owner unchecked. Add the line "
    "`Unvetted: <why it could not be checked>` to the question (a page item: to `context`) and send it again. "
    "The owner then reads it marked as unchecked.")


def unvetted(payload, tool, args, rule, why, units):
    """The check could not run. Refuse with the Unvetted remedy, unless every question's own text carries the
    `Unvetted:` line (a session cannot write it ahead of time to skip a check that can run)."""
    import question_form
    if all(question_form.has_unvetted(marker) for marker, _ in units):
        return 0
    return refuse(payload, tool, args, rule, UNVETTED_REMEDY % why)


def past_ruling_context(payload, units):
    """(prompt tail, candidate ids, unreadable sources) for the questions in `units`. Prints the one stderr line for
    the sources not searched. The only process of a judged call besides the model runs here."""
    import question_form
    cwd = payload.get("cwd") or ""
    candidates, unknown = question_form.past_rulings(" ".join(words for _, words in units),
                                                     question_form._git_root_of(cwd) or cwd or os.getcwd())
    print(question_form.unknown_line(unknown), file=sys.stderr)
    return (question_form.candidates_block(candidates, unknown), question_form.candidate_ids(candidates),
            question_form.unreadable_sources(unknown))


PAST_RULING_RULE_NAME = "past-ruling"  # question_form.PAST_RULING_RULE, here so a send needs no import to name it


def past_ruling_check(payload, asked, marked, tool=None):
    """The dedicated past-ruling call (item 8 alone) for the question text `asked`: (rule, refusal text), or None when
    nothing settles it. The one judge is lint/report_guard.py past_ruling_problem, also the Stop hook's: it makes the git
    read and the Sonnet call, and its text is the relay remedy, or the Unvetted remedy for a check that could not run
    (unless `marked`: every question in the call carries its own `Unvetted:` line). `asked` is sent whole. For a page
    write (`tool` is the data tool) the Unvetted remedy also says where the line goes."""
    sys.path.insert(0, os.path.join(HERE, "..", "lint"))
    import report_guard
    problem = report_guard.past_ruling_problem(asked, payload.get("cwd") or "", marked)
    if not problem:
        return None
    relay = problem.startswith(report_guard.RELAY_RULE_REASON.split("%", 1)[0])
    if not relay and tool == DATA_TOOL:
        problem += " For a page item, put the line in `context`."
    return (PAST_RULING_RULE_NAME if relay else QUESTION_RULE), problem


SEND_HEADING_MARK = re.compile(r"^#{1,6}[ \t]+")  # a Markdown heading mark, cut like a list bullet


def send_question(message):
    """(text for the dedicated call, whether every question's Unvetted line is there) for a send that is an owner
    question: a Goal line and a Problem line in its prose, else None. Plain string tests first, so a send without the
    form never imports question_form or report_guard (a send that holds both words in prose, with no form line, does
    import them, and then returns None). The form lines are read after the marks a page uses are cut (`**`, `*`, `_`,
    a list bullet, a heading mark; prose_lines cuts `>`), and outside a code fence, through report_guard.prose_lines,
    the one reader of what is code. The Problem line is question_form.PROBLEM_LABEL, with or without a stake, so a
    plain `Problem:` line or a `Problem (<any word>):` line counts. question_form's regexes are unchanged.
    The cap rule: a message up to report_guard.ASK_TEXT_MAX characters goes whole. A longer one goes as the
    ASK_TEXT_MAX characters that start at its first form line (a Goal, Problem, Based on or Departs from line), because
    the question sits there and the tail of a long send is its log.
    Each question needs its own `Unvetted:` line, as each page write does. The message is split into one unit per
    Goal/Problem pair, read in the whole message; a unit runs from the line that opens it to the line that opens the
    next, so a marker counts for the question above it."""
    if not isinstance(message, str):
        return None
    low = message.lower().replace("*", "").replace("_", "")
    if "goal:" not in low or "problem" not in low:
        return None
    sys.path.insert(0, os.path.join(HERE, "..", "lint"))
    import question_form
    import report_guard
    forms = []  # (line index, kind) of each Goal and Problem line, in order
    first = None  # the first form line of any kind: where the capped text starts
    for index, body in report_guard.prose_lines(message):
        body = report_guard.LIST_ITEM.sub("", body.replace("*", "").replace("_", ""), count=1).strip()
        body = SEND_HEADING_MARK.sub("", body, count=1)
        kind = ("goal" if question_form.GOAL_LINE.search(body) else
                "problem" if question_form.PROBLEM_LABEL.search(body) else None)
        if kind:
            forms.append((index, kind))
        if kind or question_form.BASED_LABEL.search(body) or question_form.DEPARTS_LINE.search(body):
            first = index if first is None else first
    starts, seen = [], set()  # a unit opens at the form line that repeats a kind its unit already holds
    for index, kind in forms:
        if not starts or kind in seen:
            starts.append([index, set()])
            seen = set()
        seen.add(kind)
        starts[-1][1].add(kind)
    whole = [start for start, kinds in starts if len(kinds) == 2]  # a unit with one kind is no question
    if not whole:
        return None
    lines = message.splitlines(keepends=True)
    bounds = [0] + whole[1:] + [len(lines)]
    marked = all(question_form.has_unvetted("".join(lines[bounds[i]:bounds[i + 1]])) for i in range(len(whole)))
    asked = message
    if len(message) > report_guard.ASK_TEXT_MAX:
        start = sum(len(line) for line in lines[:first])
        asked = message[start:start + report_guard.ASK_TEXT_MAX]
    return asked, marked


def judge_send(payload, tool, args):
    """An owner question sent by a send tool gets the dedicated past-ruling call before it goes."""
    try:
        question = send_question(args.get("message"))
        found = past_ruling_check(payload, question[0], question[1]) if question else None
    except Exception as exc:
        print("call judge failed open: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()),
              file=sys.stderr)
        return 0
    return refuse(payload, tool, args, found[0], found[1]) if found else 0


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        tool, args = payload.get("tool_name"), payload.get("tool_input")
        if tool in SEND_TOOLS:
            return judge_send(payload, tool, args) if isinstance(args, dict) else 0
        if tool not in JUDGES:
            return 0
        if not isinstance(args, dict):
            raise ValueError("tool_input is not an object")
        prompt, model, timeout, rule, fallback = JUDGES[tool]
        units = []  # (Unvetted marker text, words) of each question this call asks the owner
        reask = widening = False
        if tool == "AskUserQuestion":
            import question_form
            code_rule, matched = question_form.chat_hit(args)
            if code_rule:
                reason = "%s (%s)" % (question_form.CHAT_REASONS[code_rule], matched)
                return refuse(payload, tool, args, code_rule, reason)
            shown = json.dumps(args, ensure_ascii=False)
            units = question_form.chat_units(args)
        elif tool == DATA_TOOL:
            if args.get("action") not in PAGE_WRITE_ACTIONS or not writes_an_item(args):
                return 0
            import question_form
            hit, writes = question_form.page_item_hit(args, payload.get("cwd") or "")
            judged = [] if hit[0] else question_form.judged_item_writes(writes)
            if not judged:  # guard.py refuses a hit; no write carries options, context or steps
                return 0
            shown = json.dumps(judged, ensure_ascii=False)
            units = question_form.page_units(judged)
            # Every write's text goes to the dedicated call, uncut. Each question needs its own Unvetted line.
            found = past_ruling_check(payload, "\n".join(words for _, words in units),
                                      all(question_form.has_unvetted(marker) for marker, _ in units), tool)
            if found:  # item 8 refused it, or could not run: no form-judge call
                return refuse(payload, tool, args, found[0], found[1])
            reask = any(is_reask(w) for w in judged)
            widening = any(sets_options(w) for w in judged)
        else:
            shown = json.dumps(args, ensure_ascii=False)
        tail, ids = "", []
        if units and tool == "AskUserQuestion":  # the page's rulings went to its dedicated call; units stay for Unvetted
            tail, ids, unreadable = past_ruling_context(payload, units)
            if unreadable:
                return unvetted(payload, tool, args, rule, "; ".join(unreadable), units)
        full = prompt % shown
        if reask:
            full += "\n" + NONE_DIRECTION_RULE  # after `%`, so the rule's text never meets the formatter
        if widening:
            full += "\n" + widening_rule()
        verdict, error = invoke_model(full + tail, model=model, timeout=timeout, shape=OK_SHAPE, effort=None)
    except Exception as exc:
        print("call judge failed open: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()),
              file=sys.stderr)
        return 0
    if error and units:  # a question is never judged silently: no verdict means Unvetted
        return unvetted(payload, tool, args, rule, " ".join(str(error).split()), units)
    if error:
        print("call judge failed open: %s" % " ".join(str(error).split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        reason = reason if isinstance(reason, str) and reason.strip() else fallback
        cite = question_form.ruling_cite(reason, ids) if tool == "AskUserQuestion" else ""
        if cite == "bogus":  # the answer cites a record the model was not shown: no usable verdict
            return unvetted(payload, tool, args, rule, "the review cited a record that was not in the list", units)
        return refuse(payload, tool, args, question_form.PAST_RULING_RULE if cite else rule, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
