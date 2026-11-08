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

Verdict claim (rule `verdict-claim-needs-run`, decision claims-carry-backing): a send whose message forecasts what a
named check, guard, hook, test, rule, CI, PR or source file will or would refuse, block, deny, catch, reject, flag,
fail, allow or pass is refused, unless (a) the current turn (payload transcript_path, read by lint/_transcript.py
read_turn with peers_start_turn, so a peer message starts a turn, and tool_uses) holds a Bash call that names a file
the claim names, or (b) the claim carries a backing cite that lint/stale_cites.py reads (paren_cites, cite_kind,
backing_path): `(test path::name)` backs it when `name` is defined in that file at head, `(read path)` when the path is
a file the claim names or one that defines a rule the claim names.
A claim is read as a sentence, not as a word search (is_verdict_claim). It is a forecast word (will, would, should,
'll, won't; a curly apostrophe counts), up to two of `not` and one adverb (VERDICT_ADVERBS, or a word in -ly), then a
verdict verb that acts on it, this, that, them, the send, the change or a PR, or a passive verb. The check must be the
verb's actor. For an active verb, a subject sits in the last three words of the clause before the forecast word, with
no pronoun after it. For a passive verb, a subject sits in the three words after `by`. A subject is a whole word
(check, guard, hook, test, rule, CI; "test-author" is none), `PR #n`, or a source file path. "The hook will catch
OSError", "I will block it until the check is green" and "The merge will be blocked until CI is green" are no claims.
A claim that names no file, such as one that names a check only by pull request number, needs the cite: no run can
clear it. A paren group that is no cite stays in the sentence, so "The guard (hooks/guard.py)" names its file.
Prose lines of a paragraph are joined before sentences are split. Fenced text (stale_cites.fenced_lines), quoted text
and inline code spans (stale_cites.MENTION, CODE_SPAN; a lone file path in them stays) and past tense pass. A forecast
whose clause asks for the verdict is a question, not a claim (is_ask): the clause holds an ask word (VERDICT_ASK_WORDS:
whether, if, verify, confirm, prove, probe, find out, unknown; a "re-" prefix counts, as in "Re-verify"), unless an
article sits directly before it, as in "The verify hook"; a label "Unknown:" opens it; or a "?" ends the question and
the clause opens with an auxiliary or modal (VERDICT_QUESTION_OPENERS, as in "Do you think the guard will refuse it?")
or holds a wh-word before the actor (VERDICT_WH_WORDS, as in "Which check will fail?"). An opener before an earlier
clause end does not reach the forecast: "Should I merge, given the guard will refuse it?" is a claim. A send that also fails the owner-question check is refused once, naming both rules, and both checks run
before that refusal. A send with no forecast word and verdict word exits before any import, transcript read or model
call. The refusal goes through refuse(), so the owner override lifts it. A cite whose file cannot be read at head (no
repo, no such file) backs nothing, so its claim is refused unless a run backs it. A transcript that cannot be read
allows, with one stderr line.

Fail open. Any other model error, odd answer or unreadable input allows, with one stderr line.

Cost (rule outcomes-mechanize-rules): a send without the form, a read, and a write of another collection start
no process and make no model call. A send with the form: one git process (question_form.past_rulings) and one Sonnet
call. A judged item write: one git process, the dedicated Sonnet call, and then the form judge's Opus call, so one more
Sonnet call than before. A chat box: one git process and one Opus call, as before. Nothing is written but the
guard.log line of a refusal. test_call_judge.py counts the processes and the calls.
Cost of the verdict claim rule: a send without both a forecast word and a verdict word costs two regex passes, with no
import, no process and no model call. A send with both imports lint/stale_cites.py and, for a claim that no cite backs
and that names a file, reads the transcript's turn (one file read per send); each cite to a file costs one `git show` process. It makes no model call of its
own and writes nothing but a refusal's guard.log line. An owner question that also holds a claim makes its one
past-ruling call before the refusal, as before.

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
VERDICT_CLAIM_RULE = "verdict-claim-needs-run"
VERDICT_CLAIM_CITE = "(decision claims-carry-backing, a forecast of a check's verdict needs its run or a cite)"
# The words of a verdict claim: a sentence holds one of each list. Whole words, in any case: past tense ("refused")
# is no forecast. These lists are the one home; hooks/test_call_judge.py reads them from here.
VERDICT_FORECAST_WORDS = ("will", "would", "should", "won't", "'ll")
VERDICT_WORDS = ("refuse", "block", "deny", "catch", "reject", "flag", "fail", "allow", "pass", "let through")
VERDICT_PASSIVE_WORDS = ("refused", "blocked", "denied", "caught", "rejected", "flagged", "failed", "allowed", "passed",
                         "let through")
VERDICT_SUBJECT_WORDS = ("check", "checks", "guard", "guards", "hook", "hooks", "test", "tests", "rule", "rules", "CI")
# What the verdict verb acts on: a send, a change, a PR, or a pronoun for one. "will catch OSError" acts on an error
# class, so it is no forecast about a verdict. A passive verb ("will be refused") needs no object.
VERDICT_OBJECTS = r"(?:it|this|that|them|the send|the change|(?:the |a )?PRs?)\b"
# A forecast verb with no object ("The test will fail.") counts when it ends the sentence or its clause, or when an
# open paren ("will fail (see ...)") or closing emphasis ("**The guard will refuse**") follows it. It is no claim
# before an object that is not listed ("will catch OSError"), so this tail never reads past a word. Named limit: any
# word after the bare verb ("will fail on the old code", "will fail because ...", "will fail twice") is no end.
VERDICT_NO_OBJECT_END = r"(?=\s*(?:[.!?,;:(]|[*_]+(?!\w)|\s[-–—]\s|$))"
# The one adverb a forecast may carry before its verb ("will probably refuse it"); any word in -ly counts too.
VERDICT_ADVERBS = ("probably", "still", "also", "never", "then", "definitely", "likely", "surely", "certainly", "just",
                   "now", "again", "always", "only", "really", "even", "already", "ever", "simply", "clearly")
# A pronoun between a subject word and the forecast word is the actor instead: "when the test passes I will pass it".
ACTOR_PRONOUNS = ("i", "you", "we", "they", "he", "she", "it")
# The words that make a forecast's clause an ask: "Verify the check will pass it" asks for the run, it claims nothing.
VERDICT_ASK_WORDS = ("whether", "if", "verify", "confirm", "prove", "probe", "find out", "unknown")
# A wh-word asks only in a sentence that ends in "?" and comes before the actor: "Which check will fail?" asks, while
# in a statement such as "The check which fails will refuse it." the wh-word is a relative and the claim stands.
VERDICT_WH_WORDS = ("which", "what")
# A forecast's clause that opens with one of these, in a question that ends in "?", is a yes/no question: "Do you think
# the guard will refuse it?" asks, whatever sits between the opener and the forecast word in that clause.
VERDICT_QUESTION_OPENERS = ("do", "does", "did", "would", "could", "will", "can", "is", "are", "should")
# An ask word directly after one of these articles is a modifier of the subject ("The verify hook"), not an ask.
VERDICT_ACTOR_ARTICLES = ("the", "a", "an")
SHORT_QUESTION_WORDS = 6  # a question this short or shorter, after a wh-clause, finishes that clause's question
VERDICT_CLAIM_REMEDY = (
    "this message forecasts what a check will refuse, block, catch, flag, fail, allow or pass, and the turn did "
    "not run it. Run the check first, and name the file in the sentence (outside any cite) so the run backs it, or add a "
    "backing cite at head: "
    "`(test path::name)`, where the file defines that name, or `(read path:line)`, where the file is one the claim "
    "names (named in the sentence, outside the cite) or the file that defines the named rule. Or drop the forecast.")
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
    "it was set so). A question whose `Based on (ruling): ...` line names that ruling (its id or slug) passes: "
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
    text = reason + " " + {SPAWN_RULE: SPAWN_CITE, VERDICT_CLAIM_RULE: VERDICT_CLAIM_CITE}.get(rule, QUESTION_CITE)  # the text both paths below carry
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


def _word_re(word):
    """The pattern of one listed word: whole word, any case; a contraction tail such as 'll follows a word character."""
    return (r"(?<=\w)" + re.escape(word) + r"\b") if word.startswith("'") else (r"\b" + re.escape(word) + r"\b")


def _any_re(words):
    return "(?:" + "|".join(_word_re(w) for w in words) + ")"


def _has_word(text, words):
    return re.search(_any_re(words), text, re.I) is not None


_FORECAST = re.compile(_any_re(VERDICT_FORECAST_WORDS), re.I)
# What follows a forecast word: up to two of `not` and an adverb, then an active verb and its object, `let OBJ
# through`, or a passive verb. It is matched at the forecast word's end, so each forecast word of a sentence is read.
_PREDICATE = re.compile(
    r"(?:\s+(?:not|%s|[a-z]+ly)\b){0,2}\s+(?:(?:%s)\s+%s|(?:%s)%s|let\s+%s\s+through\b|(?:be|get)\s+(?P<passive>%s)\b)" % (
        "|".join(VERDICT_ADVERBS), "|".join(re.escape(w) for w in VERDICT_WORDS if " " not in w), VERDICT_OBJECTS,
        "|".join(re.escape(w) for w in VERDICT_WORDS if " " not in w), VERDICT_NO_OBJECT_END,
        VERDICT_OBJECTS, "|".join(re.escape(w) for w in VERDICT_PASSIVE_WORDS)), re.I)
_BY = re.compile(r"\s+by\s+", re.I)
_CLAUSE_END = re.compile(r"[,;:](?=\s|$)|\s[-–—]\s")  # a clause ends at , ; : or a spaced dash
_LET_ANY = re.compile(r"\blet\s+(?:\w+\s+){1,2}through\b", re.I)  # "let it through": the verb split by its object
_BULLET = re.compile(r"\s*(?:[-*+]\s|\d+[.)]\s|#|>)")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SUBJECT_WORDS = {w.lower() for w in VERDICT_SUBJECT_WORDS if w != "CI"}  # CI counts only in capitals
# A forecast in a clause that asks for the verdict is a question, not a claim: "Find out if CI will fail it".
# A word joined by a hyphen is part of a compound noun ("The unknown-reads check"), so it is no ask word; the one
# hyphen it may carry is a "re-" prefix, since "Re-verify" still asks.
_ASK_WORDS = re.compile(r"(?<![\w-])(?:re-)?(?:%s)(?![\w-])" % "|".join(w.replace(" ", r"\s+") for w in VERDICT_ASK_WORDS),
                        re.I)
_ARTICLE_BEFORE = re.compile(_any_re(VERDICT_ACTOR_ARTICLES) + r"\s+$", re.I)  # an article that ends the text
_QUESTION_OPENER = re.compile(_any_re(VERDICT_QUESTION_OPENERS), re.I)
_WH_WORDS = re.compile(_any_re(VERDICT_WH_WORDS), re.I)
_UNKNOWN_LABEL = re.compile(r"\bunknown\s*$", re.I)  # "Unknown: the check will refuse it" reports a read that did not run


def _straight(text):
    """`text` with each curly apostrophe made straight, so "won’t" reads as "won't"."""
    return text.replace("’", "'")


def is_path(word):
    """True when `word` reads as a source file path (stale_cites.SOURCE, the one home): a slash, or a dot in its last
    part. Needs lint/ on sys.path."""
    import stale_cites
    return ("." in word.split("/")[-1] or "/" in word) and stale_cites.SOURCE.match(word) is not None


def _bare(token):
    """A token cut of the marks around its word: parens, quotes, bold, end punctuation and a possessive 's."""
    word = token.strip("()[]{}\"'`*.,:;!?")
    return word[:-2] if word.endswith("'s") else word


def has_subject(tokens):
    """True when one of `tokens` names a check: a subject word (case-blind, but CI in capitals), a PR by number
    (`PR #<n>` or `PR#<n>`: a run has no file to match, so only a cite backs it), or a source file path. A token is compared whole, so "test-author" is no "test"."""
    words = [_bare(t) for t in tokens]
    for index, word in enumerate(words):
        following = words[index + 1] if index + 1 < len(words) else ""
        if word.lower() in _SUBJECT_WORDS or word == "CI" or is_path(word) or re.fullmatch(r"PRs?#\d+", word) \
                or (word in ("PR", "PRs") and re.fullmatch(r"#?\d+", following)):
            return True
    return False


def split_clause(prefix):
    """(head, clause) of the text before a forecast word: the clause it sits in, and what comes before that clause."""
    ends = list(_CLAUSE_END.finditer(prefix))
    return (prefix[:ends[-1].start()], prefix[ends[-1].end():]) if ends else ("", prefix)


def is_ask(prefix, question=False):
    """True when the forecast that ends `prefix` is asked, not claimed: the forecast's own clause (split_clause) holds
    an ask word with no article directly before it ("Verify the check will pass it", "Read the diff and verify CI will
    fail it"; not "The verify hook will refuse it"), the text before that clause ends in a label "Unknown:", or
    `question` (a "?" ends the sentence's question) and the clause, cut of a bullet mark and `*`, opens with an
    auxiliary or modal ("Do you think the guard will refuse it?"; not "Should I merge, given the guard will refuse
    it?") or holds a wh-word before the actor ("Which check will fail?"). This is the one home for the ask test."""
    head, clause = split_clause(prefix)
    # An article directly before an ask word makes it a modifier of the actor ("The verify hook"); else it asks.
    asked = any(_ARTICLE_BEFORE.search(clause[:word.start()]) is None for word in _ASK_WORDS.finditer(clause))
    bullet = _BULLET.match(clause)
    opener = _QUESTION_OPENER.match(clause[bullet.end() if bullet else 0:].replace("*", "").lstrip())
    return asked or _UNKNOWN_LABEL.search(head) is not None \
        or (question and (opener is not None
                          or any(has_subject(clause[wh.end():].split()) for wh in _WH_WORDS.finditer(clause))))


def actor_before(prefix):
    """True when the actor of the forecast word that ends `prefix` is a check: a subject in the last three words of
    its clause. The words are read back from the forecast word, and a pronoun stops the read, since it is the actor."""
    window = []
    for token in reversed(split_clause(prefix)[1].split()[-3:]):
        if _bare(token).lower() in ACTOR_PRONOUNS:
            break
        window.insert(0, token)
    return has_subject(window)


def actor_after_by(rest):
    """True when a passive verb's actor is a check: `rest` opens with `by`, and a subject sits in the three words
    after it, in the same clause."""
    by = _BY.match(rest)
    return bool(by) and has_subject(_CLAUSE_END.split(rest[by.end():])[0].split()[:3])


def opens_wh_question(sentence, following):
    """True when `sentence` opens with a wh-word and a check word ("Which check will fail.") and `following`, the next
    sentence, is itself a short question ("Do you know?"): one question that a full stop split in two."""
    words = sentence.split()
    opener = _WH_WORDS.match(_bare(words[0])) if words else None
    return bool(opener) and len(words) > 1 and has_subject(words[1:2]) \
        and following.rstrip().endswith("?") and len(following.split()) <= SHORT_QUESTION_WORDS


def is_verdict_claim(sentence, following=""):
    """A forecast about a check's verdict, read as a sentence: a forecast word, then a verdict verb that acts on a
    send, a change or a PR (or a passive verb), whose actor is a check. A subject word elsewhere in the sentence, as in
    "I will block it until the check is green", is no actor. `following` is the next sentence, which may finish a
    question that this one starts. Needs lint/ on sys.path."""
    sentence = _straight(sentence)
    split_question = opens_wh_question(sentence, _straight(following))
    for modal in _FORECAST.finditer(sentence):
        verb = _PREDICATE.match(sentence, modal.end())
        if not verb:
            continue
        prefix = sentence[:modal.start()]
        # A "?" after the forecast word ends the question that holds it, whatever closing mark or quote follows.
        if is_ask(prefix, "?" in sentence[modal.end():] or split_question):
            continue
        if actor_after_by(sentence[verb.end():]) if verb.group("passive") else actor_before(prefix):
            return True
    return False


def prose_units(message):
    """The message's prose outside code fences, as paragraphs: the lines of a paragraph are joined with a space, so a
    claim split across lines reads whole. A blank line, a fence, a list bullet or a heading starts a new unit.
    Needs lint/ on sys.path."""
    import stale_cites  # the one home of what is fenced
    rows = message.split("\n")
    fenced = stale_cites.fenced_lines(rows)
    units, current = [], []
    for number, row in enumerate(rows, 1):
        if number in fenced or not row.strip() or (current and _BULLET.match(row)):
            if current:
                units.append(" ".join(current))
            current = []
        if number not in fenced and row.strip():
            current.append(row.strip())
    if current:
        units.append(" ".join(current))
    return units


def verdict_claims(message):
    """The sentences of `message` that forecast a verdict, outside code fences. A message with no forecast word and no
    verdict word is read by plain regex alone, so such a send imports nothing."""
    if not isinstance(message, str):
        return []
    message = _straight(message)
    if not _has_word(message, VERDICT_FORECAST_WORDS) \
            or not (_has_word(message, VERDICT_WORDS + VERDICT_PASSIVE_WORDS) or _LET_ANY.search(message)):
        return []
    claims = []
    for unit in prose_units(message):
        sentences = SENTENCE_END.split(blank_mentions(unit))
        claims += [sentence for index, sentence in enumerate(sentences)
                   if is_verdict_claim(sentence, sentences[index + 1] if index + 1 < len(sentences) else "")]
    return claims


def blank_mentions(unit):
    """`unit` with quoted text and inline code spans blanked, as fenced text is: a forecast quoted is a mention, not a
    claim. stale_cites holds both patterns (MENTION, CODE_SPAN). A bare file path, in a span or not, stays, since a path
    may be the claim's subject or the file a run must name."""
    import stale_cites

    def blank(match):
        inner = match.group(0).strip("`\"“”")
        return match.group(0) if stale_cites.PATH_SPAN.match(inner) or is_path(inner) else " "
    return stale_cites.MENTION.sub(blank, stale_cites.CODE_SPAN.sub(blank, unit))


def strip_cites(sentence):
    """`sentence` with each cite cut out. A cite is a paren group that stale_cites.paren_cites reads (the one cite
    parser) and whose kind is a cite kind: a premise kind, or `test`. Any other group stays, so "The guard
    (hooks/guard.py)" still names its file. A group is matched by its text as paren_cites gives it."""
    import stale_cites
    cites = set()
    for cite in stale_cites.paren_cites(sentence):
        kind = stale_cites.cite_kind(cite)[0]
        if kind in stale_cites.PREMISE_KINDS or kind == "test":
            cites.add(cite)
    return stale_cites.PAREN_GROUP.sub(
        lambda group: " " if group.group(1).replace("`", "").strip() in cites else group.group(0), sentence)


def named_files(sentence):
    """The file paths a sentence names outside its cites, each cut of its `:line` or `::name` tail. A bare `#1516`
    names none."""
    found = []
    for word in re.split(r"[\s,;()`]+", strip_cites(sentence)):
        word = word.rstrip(".:")
        if is_path(word):
            found.append(re.split(r"::?\d*", word, maxsplit=1)[0])
    return found


def file_at_head(cwd, path):
    """The text of `path` at HEAD of the repo at `cwd`, or None when it is no file there: one git process."""
    import _nowindow
    done = _nowindow.run(["git", "-C", cwd or ".", "show", "HEAD:" + path], capture_output=True)
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else None


def defines_name(text, name):
    """True when `name` is defined in `text`: a def or class for Python (stale_cites.defined_line, by the AST), else a
    whole-word match."""
    import stale_cites
    line = stale_cites.defined_line(text, name)
    return line > 0 if line is not None else re.search(r"\b%s\b" % re.escape(name), text) is not None


def defines_rule(text, slug):
    """True when `text` defines the rule `slug`: its anchor comment, or the id as a quoted string."""
    return ("<!-- rule:%s -->" % slug) in text or ('"%s"' % slug) in text or ("'%s'" % slug) in text


def cite_backs(sentence, cwd):
    """True when a paren cite of `sentence` backs it (stale_cites, the one cite parser). A `test path::name` cite backs
    it when `name` is defined in the file at head. A `read path` cite backs it when the file at head is one the claim
    names, or defines a rule the claim names."""
    import stale_cites
    bare = strip_cites(sentence)
    for cite in stale_cites.paren_cites(sentence):
        kind, rest = stale_cites.cite_kind(cite)
        path = stale_cites.backing_path(kind, rest)
        if not path or kind not in ("test", "read"):
            continue
        text = file_at_head(cwd, path)
        if text is None:
            continue
        if kind == "test":
            if defines_name(text, rest.split("::")[-1]):
                return True
        elif path in named_files(bare) or any(
                defines_rule(text, slug) for slug in re.findall(r"(?<![\w/.-])[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?![\w/.-])", bare)):
            return True
    return False


def turn_commands(transcript_path):
    """The Bash commands of the current turn, read by lint/_transcript.py (the one turn reader). A peer message starts
    a turn here, so a run made before the newest one clears no later claim."""
    import _transcript
    _, turn = _transcript.read_turn(transcript_path, peers_start_turn=True)
    return [str((use.get("input") or {}).get("command", "")) for rec in turn for use in _transcript.tool_uses(rec)
            if use.get("name") == "Bash"]


# The programs that execute a file given as an argument. A read (cat, grep, sed, git show, python3 -c) is not one: it
# names the file and runs nothing, so it backs no forecast about the file. A versioned name (python3.12) is its base.
RUN_COMMANDS = frozenset({"python3", "python", "node", "bash", "sh", "pytest"})
# shlex gives a run of these characters as one token. Such a token ends a command when it holds a SEPARATOR_CHARS
# character or is `&` or `&&`: `;`, `|`, `||`, `|&`, `(`, `)`, `$(`'s `(`, `<(` and a backtick. Any other one is a
# redirect (`<`, `>`, `>>`, `>&`, `<<`), and the word after it is its target, which runs nothing.
SHELL_PUNCTUATION = "();<>|&`"
SEPARATOR_CHARS = "();|`"
# Words that open a command without being it: `if python3 x; then`, `do python3 x`, `! python3 x`, `{ python3 x; }`.
SHELL_KEYWORDS = frozenset({"if", "then", "else", "elif", "do", "while", "until", "!", "{"})
# Programs that run the command after them. The words they take before it are skipped: an option, its value where it
# has one, and for `timeout` the duration. `verdict`, `time` and `nohup` take none.
WRAPPER_COMMANDS = frozenset({"verdict", "timeout", "env", "time", "nice", "nohup"})
WRAPPER_VALUE_OPTIONS = frozenset({"-s", "-k", "-u", "-n", "-C", "--signal", "--kill-after", "--unset", "--adjustment"})
# Shells run the string after `-c` as a command line; `-n` only parses the script. Their `-e` is errexit, not code.
SHELL_RUNNERS = frozenset({"bash", "sh"})
# Per runner, the flags whose next word is code, not a file. node's `-c` is `--check`, so it is not here.
CODE_STRING_FLAGS = {"python": frozenset({"-c"}), "node": frozenset({"-e", "--eval", "-p", "--print"})}
# Per runner, the flags that parse or list the file and run none of it. node reads them only before the script, so
# the arguments loop meets them first; pytest reads them anywhere, so its whole argument list is searched.
CHECK_ONLY_FLAGS = {"node": frozenset({"--check", "-c"}), "pytest": frozenset({"--collect-only", "--co"})}
PYTHON_VALUE_FLAGS = frozenset({"-W", "-X"})
# unittest options that take a value. `discover` reads its start dir from -s (default ".") and its file pattern from
# -p (default "test*.py").
UNITTEST_VALUE_OPTIONS = frozenset({"-k", "-s", "-p", "-t", "--start-directory", "--pattern", "--top-level-directory"})
UNITTEST_DEFAULT_PATTERN = "test*.py"
# A here-document opener: `<<EOF`, `<<-'EOF'`, `<< "EOF"`, but not a `<<<` here-string. Its body lines are text, not
# commands, unless a shell reads them (`bash <<EOF`).
HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*\\?(['\"]?)([A-Za-z_][\w-]*)\1")
# How deep a quoted `$( )` or backtick is read inside another one.
SUBSTITUTION_DEPTH = 3


def runs_file(command, name, _depth=0):
    """True when a Bash `command` runs the file `name`: a runner from RUN_COMMANDS (or `python3 -m pytest` / `-m
    unittest`) with the file as an argument, a wrapper (WRAPPER_COMMANDS, `uv run`) or shell keyword around one, a
    `bash -c` string, `$( )` or backtick that does, or the file path as the command. Each command between separators is
    read alone, a redirect target is no argument, a here-document body is text unless a shell reads it, a quoted
    string that spans lines is one word, and text shlex cannot parse is no run. A check that runs nothing from the file (`bash -n`, `node --check`, `pytest --co`,
    `python3 -m py_compile`) is no run."""
    import fnmatch
    import shlex

    def is_file(word):
        word = word.split("::")[0]
        return word == name or word.endswith("/" + name)

    def strip_head(part):
        """`part` from its command word on: shell keywords, `VAR=value` words and wrappers dropped."""
        while part:
            head = os.path.basename(part[0])
            if part[0] in SHELL_KEYWORDS or re.match(r"\w+=", part[0]):
                part = part[1:]
            elif head in WRAPPER_COMMANDS:
                rest = part[1:]
                while rest and rest[0].startswith("-"):
                    rest = rest[2:] if rest[0] in WRAPPER_VALUE_OPTIONS else rest[1:]
                if head == "timeout":
                    rest = rest[1:]
                part = rest
            elif head == "uv" and part[1:2] == ["run"]:
                part = part[2:]
                while part and part[0].startswith("-"):
                    part = part[1:]
            else:
                break
        return part

    def split_line(line):
        """The commands of one line, each a word list with redirects and their targets dropped, and the plain words;
        None when shlex cannot parse it."""
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=SHELL_PUNCTUATION)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return None
        parts, part, words, skip = [], [], [], False
        for token in tokens:
            if token and all(char in SHELL_PUNCTUATION for char in token):
                if any(char in SEPARATOR_CHARS for char in token) or token in ("&", "&&"):
                    parts.append(part)
                    part, skip = [], False
                else:
                    skip = True
                continue
            words.append(token)
            if skip:
                skip = False
            else:
                part.append(token)
        parts.append(part)
        return parts, words

    def feeds_shell(prefix):
        """True when the here-document opened after `prefix` is read by a bare shell, as in `bash <<EOF`."""
        split = split_line(prefix)
        part = strip_head(split[0][-1]) if split else []
        return bool(part) and os.path.basename(part[0]) in SHELL_RUNNERS and all(
            word.startswith("-") and not re.match(r"-[^-]*c", word) for word in part[1:])

    def pytest_runs(args):
        if any(word in CHECK_ONLY_FLAGS["pytest"] for word in args):
            return False
        index = 0
        while index < len(args):
            if args[index] == "-c":
                index += 2
                continue
            if is_file(args[index]):
                return True
            index += 1
        return False

    def unittest_runs(args):
        """A test name that is the file runs it. `discover`, or no test name, runs each file in the start dir that
        matches the pattern."""
        options, names, index = {}, [], 0
        while index < len(args):
            word = args[index]
            if word in UNITTEST_VALUE_OPTIONS:
                options[word] = args[index + 1] if index + 1 < len(args) else ""
                index += 2
                continue
            if not word.startswith("-"):
                names.append(word)
            index += 1
        if names and names[0] != "discover":
            return any(is_file(word) for word in names)
        positional = names[1:]
        start = options.get("-s") or options.get("--start-directory") or (positional[0] if positional else ".")
        pattern = options.get("-p") or options.get("--pattern") or (
            positional[1] if len(positional) > 1 else UNITTEST_DEFAULT_PATTERN)
        base = os.path.basename(name)
        return fnmatch.fnmatch(base, pattern) and is_file(os.path.normpath(os.path.join(start, base)))

    def part_runs(part):
        part = strip_head(part)
        if not part:
            return False
        if is_file(part[0]):
            return True
        runner = re.sub(r"^(python)[\d.]+$", r"\1", os.path.basename(part[0]))
        if runner not in RUN_COMMANDS:
            return False
        args, index = part[1:], 0
        if runner == "pytest":
            return pytest_runs(args)
        while index < len(args):
            word = args[index]
            if runner in SHELL_RUNNERS and re.match(r"-[^-]*c", word):
                return index + 1 < len(args) and runs_file(args[index + 1], name, _depth + 1)
            if runner in SHELL_RUNNERS and re.match(r"-[^-]*n", word):
                return False
            if word in CODE_STRING_FLAGS.get(runner, ()) or word in CHECK_ONLY_FLAGS.get(runner, ()):
                return False
            if runner == "python" and word == "-m":
                module, rest = args[index + 1:index + 2], args[index + 2:]
                if module == ["pytest"]:
                    return pytest_runs(rest)
                return module == ["unittest"] and unittest_runs(rest)
            if runner == "python" and word in PYTHON_VALUE_FLAGS:
                index += 2
                continue
            if is_file(word):
                return True
            index += 1
        return False

    heredoc, unclosed = None, ""
    for line in command.replace("\\\n", "").splitlines():
        if heredoc:
            delimiter, read_body = heredoc
            if line.strip() == delimiter:
                heredoc = None
                continue
            if not read_body:
                continue
        else:
            opener = HEREDOC.search(line)
            if opener:
                heredoc = (opener.group(2), feeds_shell(line[:opener.start()]))
        # A line with an open quote is joined to the next, so a multi-line quoted string stays one word and its
        # inner lines are not read as commands.
        line = unclosed + "\n" + line if unclosed else line
        split = split_line(line)
        if split is None:
            unclosed = line
            continue
        unclosed = ""
        parts, words = split
        if any(part_runs(part) for part in parts):
            return True
        # A word that still holds `$(` or a backtick came from a quoted string: read the command inside it. shlex
        # drops the quote kind, so a word that sits in single quotes on the line, where bash runs nothing, is passed
        # over. This is a bandaid: a word quoted in parts by both kinds can still be read.
        if _depth < SUBSTITUTION_DEPTH and any(
                ("$(" in word or "`" in word) and "'" + word + "'" not in line and runs_file(word, name, _depth + 1)
                for word in words):
            return True
    return False


def verdict_claim_problem(payload, message):
    """The refusal text for an unbacked verdict forecast in `message`, or None. A claim is backed by a cite, or by a
    Bash call in this turn that runs a file the claim names (`runs_file`). A read of the file backs nothing."""
    lint = os.path.join(HERE, "..", "lint")
    if lint not in sys.path:
        sys.path.insert(0, lint)
    claims = verdict_claims(message)
    if not claims:
        return None
    cwd, commands = payload.get("cwd") or "", None
    for sentence in claims:
        if cite_backs(sentence, cwd):
            continue
        files = named_files(sentence)
        if files and commands is None:
            path = payload.get("transcript_path")
            try:
                commands = turn_commands(path) if path else []
            except OSError as exc:
                print("verdict claim check unknown: transcript unreadable (%s)" % exc.__class__.__name__,
                      file=sys.stderr)
                return None
        if not any(runs_file(command, name) for name in files for command in commands or ()):
            return VERDICT_CLAIM_REMEDY
    return None


def judge_send(payload, tool, args):
    """A send that forecasts a check's verdict needs its run or a cite, and an owner question sent by a send tool gets
    the dedicated past-ruling call before it goes. Both are computed first, and a send that fails both is refused
    once, naming both rules, so an owner override that lifts the refusal never skips the second check."""
    try:
        verdict = verdict_claim_problem(payload, args.get("message"))
    except Exception as exc:
        print("call judge failed open: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()),
              file=sys.stderr)
        verdict = None
    found = None
    try:
        question = send_question(args.get("message"))
        found = past_ruling_check(payload, question[0], question[1]) if question else None
    except Exception as exc:
        print("call judge failed open: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()),
              file=sys.stderr)
    if verdict and found:
        return refuse(payload, tool, args, VERDICT_CLAIM_RULE,
                      "%s Also rule %s: %s" % (verdict, found[0], found[1]))
    if verdict:
        return refuse(payload, tool, args, VERDICT_CLAIM_RULE, verdict)
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
