"""The owner override (decision owner-override): the one home of granting, spending and
reading it.

The owner starts a prompt with the word `override`. hooks/local_time.py, the prompt hook, calls grant().
refuse() in hooks/guard_core.py calls take() before it prints a deny or an ask, unless the veto that
judge() in hooks/guard.py registers finds an act no override lifts (decision owner-override).

An override is the file <config dir>/state/override/<session_id>.json, {"kind": "once"|"timed",
"until": ISO-8601 UTC}. It covers only the session that typed it. state/ is frozen against Claude's
writes, so a session cannot grant itself an override. It is valid only while now < until.
  once   `override`, or `override <reason>`: the next refused act, or 10 minutes. An agent's call
         never spends it. The reason, on one line, goes to guard.log.
  timed  `override 15m`, `override 2h`, `override 15` (minutes): every refused act until the end.
         It reaches agents. The owner picks the length, so there is no cap.
  `override off` ends any override at once. `override`, `override <n>[m|h]` and `override off` mean
  that only as the whole prompt: a word after the length or after `off` is ambiguous, so it grants
  nothing on this route (an intended "off" must never become a grant). A whole line that is a keyword form
  (`override`, `override <n>[m|h]`, `override off`, `override: <reason>`) inside a prose message grants the same, only for an owner-typed prompt:
  the gates of the plain asks (_owner_ask) refuse a notice, a fired task, an agent's `source` and a cloud session's seed brief. A line inside a backtick or tilde fence, an
  indented code line, or a pasted or notice block grants nothing, and neither does a word inside a sentence.
  A plain ask (`yes override that`, `override that for 15 minutes please`) writes the same file when a model judges the
  prompt to be the owner's own present request to override a refusal (grant_override_ask, call_judge.override_ask). Cost:
  one model call, only for an owner prompt that holds the whole word `override` outside backtick code spans and
  passes the gates below; none for any other prompt. The call fails closed. The rules:
    - The gates are the model ask's, one helper (_owner_ask): payload `source`, a notice start, pasted and notice blocks
      cut, a fired-task block, a promptSource `system` record, a cloud session's seed prompt.
    - No judge call and no new grant for: no whole word `override` outside code spans (a pasted refusal line from
      offer() holds it only inside them), a NEGATIONS word or `off` within NEGATION_SPAN words of it, a `?`, two
      lengths, a decimal or compound length, or the whole word `opus` (the model ask owns it, and it takes no prompt that holds
      `override`).
    - One length sets the time: `15m`, `15 minutes`, or a bare number right after a first word `override` (minutes).
      None: a one-act override. A judge yes for a first-word `override` with a reason and no length stays main's
      one-act override.
    - grant() defers (returns None) only for a first word `override` whose rest is no whole keyword form and holds a
      length. grant_override_ask then answers every outcome but a judge yes with grant()'s own result (a reason form:
      a one-act override, with the reason logged; `override 15m please`: nothing). A judge no or error never widens a
      one-act override to a timed one.
A held model is the file <config dir>/state/override/opus/<session_id>.json, {"kind": "opus", "until": ISO-8601 UTC,
"role": null, one role, or a sorted list of 2 or more roles, "model": a family of MODEL_FAMILIES, "at", "said"} and, for an
ask with no length of its own, "end": "report". It lives beside the override, so the two never replace each other, and it
reaches agents. The folder and the kind keep the name `opus` from when the file held Opus alone. A file with no `model`
(a keyword grant left on disk from before that route was retired) holds Opus until its time, and `opus off` ends it.
One rule lifts a spawn above its role's model (decision agent-model-cap): the owner's own typed words name that model
for the work, or he types `override`. There is no keyword form: `opus 2h`, `opus builders 2h` and `fable 1h` are plain
words, judged as `use opus for the reviewers` is. A held model lifts only a spawn on its own model: a held sonnet lifts
no Opus spawn, and a held Fable lifts a Fable spawn only. An Opus hold lifts the Opus spawn refusal of guard rule
agent-model-cap, never that rule's settings-write ask.
A plain ask (`use opus for the reviewers`, `opus builders 2h`, `run it on haiku`) writes the file when a model judges
the prompt to be the owner's own present choice of one model for the agents (grant_model_ask, call_judge.model_ask).
Cost: a prompt that names no model makes no call and reads no file. One that names a model costs one tail read, one Haiku
call and one file write or delete, plus one scope call (call_judge.opus_scope) only when the call says yes for Opus or
Fable, the ask names no role and the transcript tail holds an earlier owner prompt. The call fails closed: an error or an
odd answer writes nothing. The rules of the words:
    - The gates are the override ask's, one helper (_owner_ask), and the reply quotes are cut too (_strip_quotes): payload
      `source`, a notice start, pasted and notice blocks, a fired-task block, a promptSource `system` record, a cloud
      session's seed prompt (no earlier owner turn), and a local seed turn (_seed_turn). No call for a prompt that holds
      the whole word `override` outside code spans: the override ask judges it.
    - A model whose every mention is negated (model_mentions: `Do not use opus`) is no choice: nothing is written,
      whatever the judge says. The judge's answer must name a model the words name.
    - The roles the ask names are held, two or more as a list, only when a plain list joins them (PLAIN_LIST: commas,
      and, or, &, plus); any other words between two roles: no hold. A role word with a NEGATIONS word (not, no, don't,
      never, except, without, or an exclusion word such as skip or instead) within three words before or after it: no hold.
      A role word is MODEL_ROLES: its name, its plural, or `explorer(s)`.
    - An ask for Opus or Fable that names no role takes its roles from the owner's earlier typed prompts (decision
      owner-override: scope from context, fall back to every role), before the ask only. _context_prompts reads them from
      the one tail read (_tail_prompts), through the one owner-turn test (_owner_text), each through _strip_blocks,
      less a cloud session's seed brief (_seed_record), and scope_judge says which roles they name. Context only narrows
      the hold: the yes/no call sees the ask alone, and it never turns a no into a hold. No earlier prompt, or a scope
      read that fails, errs or names no role in ASK_ROLES: every role for the length, and it never asks. The every-role
      file is written before the scope read and narrowed after it, so a process killed in the read (the hook's timeout)
      leaves every role, with no `opus-grant` line.
    - Two or more lengths, a decimal (`1.5h`) or a compound (`1h30m`): no hold. One length sets the time: `<n>m`, `<n>h`,
      or spelled: hour(s), hr(s), min(s), minute(s). None: the hold ends at the session's next report, or after
      DEFAULT_ASK_LENGTH, whichever comes first (the one reader, model_override, tells that from the transcript, and the
      guard and the turn-end model line both call it).
A held model ends on a judge yes for another model (the file is replaced), on a judge error or timeout (the file is
deleted), on his end words `no <model>` and `<model> off` as the whole prompt (no judge call), on a turn that negates it
with no un-negated mention of it (a judge no deletes the file; the guard reads that turn too, so a call before the hook
deletes it sees no hold), at the next report for an ask with no length, and at its `until`. A judge no that does not
negate it keeps it. An old model-less file ends on `opus off` and its `until` only.
A step grant also lifts that spawn, and nothing else: the owner's grant that triage writes on the lane's
roadmap step (decision agent-model-cap). It lifts the model its `words` field names, Opus or Fable. take() reads it only
on a spawn refusal that no held model lifted, from the local ref origin/roadmap in the call's cwd, never fetched: one git
grep for the lane id, one git show per hit. The lane id is session_<x> for env CLAUDE_CODE_REMOTE_SESSION_ID=cse_<x>, else the
payload's session id. Exactly one step must bind the lane, with status not done and a grant whose role
is null or the spawn's role. A record that names the lane and cannot be read logs STEP_UNREAD.
A file that is missing, unreadable or corrupt is no override. take() never raises into the guard: an
error means no override, so the refusal stands.

A one-act override is spent by creating its claim marker, <override file>.<digest>.claim, with O_EXCL: of
calls racing for one override, exactly one creates it. A rename is no claim on Windows, where it acts on
an open handle: two racers that opened the file both rename it, and both win (CI, run 40296652083).
The digest names the override's own bytes, and each grant writes a new id, so a marker spends only the
override it was made for. The spent override file stays until a grant replaces it: a delete would make it
unreadable to a Windows racer mid-delete (CI, run 40303298492). grant() deletes markers older
than CLAIM_KEEP.
"""
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

try:  # stdlib only: the one home of the machine-text tags, the model list and the config dir
    from shared_names import MACHINE_TAGS, MODEL_FAMILIES, NOTICE_FRAMES, config_dir
    NOTICE_TAGS = MACHINE_TAGS + NOTICE_FRAMES
except ImportError:  # a missing or stale helper: the keyword grants still run, the plain ask grants nothing
    NOTICE_TAGS = ()
    MODEL_FAMILIES = ()

    def config_dir():  # a copy by need: an override file must stay readable while the helper lands late
        return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")

ONCE_WINDOW = timedelta(minutes=10)  # how long a one-act override waits for its act
CLAIM_KEEP = 2 * ONCE_WINDOW.total_seconds()  # seconds; past it, a marker's override has ended
# The first word, then one mark (`,` `.` `!` `;` or a dash) that is dropped, then the rest. A mark counts
# only with whitespace or the end after it, so `override.py` and `override-15m` grant nothing. A bare
# `:` counts as on main (`override:reason`).
PROMPT = re.compile(
    r"\s*override(?:(?=\s|$)\s*(?::|[,.!;\-\u2013\u2014](?=\s|$))?|:|[,.!;\-\u2013\u2014](?=\s|$))\s*(.*)",
    re.I | re.S)
WORD = re.compile(r"(?:(off)|(\d+)([mh])?)", re.I)  # `off` or a length, as the whole rest
# The plain ask (grant_model_ask): the whole word, the blocks that are not the owner's words, a word that may name a
# role, and a length (bounded by non-word characters, so `12 mhz` is none).
OPUS_WORD = re.compile(r"\bopus\b", re.I)
_FAMILIES = "|".join(MODEL_FAMILIES) or "(?!)"  # an empty list (a stale helper) matches nothing
MODEL_WORD = re.compile(r"(?<![A-Za-z])(%s)(?![A-Za-z])" % _FAMILIES, re.I)  # also inside claude-sonnet-5-5
# His end words for a held model, as the whole prompt: `no sonnet`, `sonnet off`, `opus off`.
END_WORD = re.compile(r"(?:no\s+(%s)|(%s)\s+off)\s*[.!]?" % (_FAMILIES, _FAMILIES), re.I)
# A reply Claude wrote that he pasted back: the marker comment of a numbered reply and each line that starts with `>`.
REPLY_QUOTES = re.compile(r"<!--\s*reply\b[^>]*-->|^[ \t]*>.*$", re.I | re.M)
PASTED = r"<pasted_content\b[^>]*>.*?</pasted_content>|<pasted_content\b.*"  # an unclosed block runs to the end
# One block per tag name in NOTICE_TAGS, so the lists stay the one home; an unclosed block, or a bracket line, runs
# to the end.
MACHINE_BLOCKS = "|".join(
    [r"<{0}[\s>].*?(?:</{0}>|$)".format(name)
     for name in sorted({m for tag in NOTICE_TAGS for m in re.findall(r"<([\w-]+)", tag)})]
    + [re.escape(tag) + ".*" for tag in NOTICE_TAGS if not tag.startswith("<")])
BLOCKS = re.compile(PASTED + "|" + MACHINE_BLOCKS, re.I | re.S)
OPUS_ASK_SOURCES = (None, "user")  # the payload `source` values a plain ask may carry: absent, null or the owner
ROLE_WORDS = re.compile(r"[A-Za-z][\w\u2019'-]*")
NEGATIONS = {"not", "no", "never", "except", "without", "dont", "don't", "don\u2019t",
             "excluding", "exclude", "skip", "ignore", "instead", "rather", "besides", "minus"}
OVERRIDE_NEGATIONS = NEGATIONS | {"off"}  # the override ask also reads a request to turn an override off as a negation
# The owner's model name (guard.owner_names_model) has its own negations. They are not the Opus-grant NEGATIONS: a
# model word is negated only by a negation that stands in its own span, so "Instead use haiku" and "Skip the checks and
# run it on haiku" name it. "instead" and "rather" negate only as the pairs in MODEL_NEGATION_PAIRS, before the model.
MODEL_NEGATIONS = {"not", "no", "never", "except", "without", "dont", "don't", "don\u2019t", "excluding", "exclude",
                   "skip", "ignore", "minus", "besides", "stop"}
MODEL_NEGATION_PAIRS = {("instead", "of"), ("rather", "than")}  # negate only when they stand just before the model word
# A span of the model word's clause ends at one of these: a negation before it reaches no further ("Not sonnet but haiku").
MODEL_SPAN_BREAKS = {"and", "but"}
MODEL_CLAUSE_BREAK = re.compile(r"[.;,!?:\n\u2013\u2014]+")  # a negation reaches only to the end of its own clause
NEGATION_SPAN = 3  # a negation within this many words before or after a role word negates it
PLAIN_LIST = re.compile(r"(?:[\s,&]|\b(?:and|or|plus)\b)*", re.I)  # the only text that may join two role words
SPELLED_UNIT = r"h(?:ours?|rs?)|m(?:ins?|inutes?)"
ASK_LENGTH = re.compile(r"(?<![\w-])(\d+)(?:([mh])|\s?(%s))(?![\w-])" % SPELLED_UNIT, re.I)
# A decimal length (`0.5h`, `1.5 hours`) or a compound one (`1h30m`): no clear length.
UNCLEAR_LENGTH = re.compile(r"[.,]\d+(?:[mh]|\s?(?:{0}))(?![\w-])|\d(?:{0}|[mh])\d".format(SPELLED_UNIT), re.I)
# The plain override ask (grant_override_ask): the whole word (not `overrides`, `re-override` or `override.py`), a backtick
# code span (a fenced block, an unclosed fence, or an inline span; a lone backtick is no span), and a bare number.
OVERRIDE_WORD = re.compile(r"(?<![\w-])override(?![\w-]|\.\w)", re.I)
CODE_SPANS = re.compile(r"```.*?```|```.*|`[^`\n]+`", re.S)
BARE_NUMBER = re.compile(r"(\d+)(?![\w.,-])")
FIRED_TASK = re.compile(r"<system-reminder>\s*This task fired at ")  # a fired scheduled task's block
COMMAND_RECORDS = ("<local-command-caveat>", "<command-name>", "<command-message>", "<local-command-stdout>")
SEED_READ_MAX = 1 << 20  # bytes of the transcript the seed check reads, from the top
DEFAULT_ASK_LENGTH = ("2", "h")
HOLD_END_REPORT = "report"  # a hold's `end` value: it ends at the session's next report
SCOPE_CONTEXT_PROMPTS, SCOPE_CONTEXT_CHARS = 10, 2000  # the newest earlier prompts the scope read sees, and the cut of each
OPUS_RULE = "agent-model-cap"  # the one rule a held model lifts, and only its spawn refusal
# The roles an Opus spawn can ask for: the agents/ roles and the built-in ones, less Plan, which runs Opus by standing
# grant (OPUS_STANDING_ROLES in hooks/guard.py). Explore is not in it: an Explore on Opus with no Audit: marker is
# refused, and a model ask for explorers (MODEL_ROLES) or `override` lifts it (decision agent-model-cap).
OPUS_ROLES = ("builder", "reviewer", "test-author", "record-writer", "claude-code-guide",
              "general-purpose", "claude")
# The roles a plain ask or its scope read can name: OPUS_ROLES less `claude`, which in prose addresses the assistant.
ASK_ROLES = tuple(role for role in OPUS_ROLES if role != "claude")
# The roles a model ask can name: ASK_ROLES and Explore, which has no Opus form of its own (an Explore on Opus is the
# audit marker's business). A word names a role by its own name, its plural, or `explorer(s)`.
MODEL_ROLES = ASK_ROLES + ("Explore",)
ABOVE_SONNET = tuple(family for family in MODEL_FAMILIES if family not in ("haiku", "sonnet"))  # the models that need his typed grant
MODEL_ROLE_WORDS = {word: role for role in MODEL_ROLES for word in (role.lower(), role.lower() + "s")}
MODEL_ROLE_WORDS.update({"explorer": "Explore", "explorers": "Explore"})
FLOOR_RULE, ROLE_RULE = "agent-model-floor", "agent-role-model"
HOLD_ONLY_RULES = (FLOOR_RULE, ROLE_RULE)  # the rules take() reads a held model for; their refusals pass no spawn model, so it never lifts them
LOG_REASON_MAX = 300
ID_CHAR = r"[\w.-]"  # the characters of a session id, for a reader that finds one inside other text
SESSION_ID = re.compile(ID_CHAR + "{1,128}")  # the id names a file: no separator, no leading dot
LIFTED = "override"  # the log decision of a lifted act
UNREAD = "override-unread"  # the log decision when an override file cannot be read
OPUS_LIFTED = "opus-override"  # the log decision of an Opus spawn an Opus override lifted
OPUS_UNREAD = "opus-unread"  # the log decision when an Opus override file cannot be read
STEP_LIFTED = "step-grant"  # the log decision of an Opus spawn a grant on the lane's roadmap step lifted
STEP_UNREAD = "step-grant-unread"  # the log decision when a step record that names the lane cannot be read
LIFTS = (LIFTED, OPUS_LIFTED, STEP_LIFTED)  # the take() results that let the act through
STEP_REF = "refs/remotes/origin/roadmap"  # the record branch as the lane last fetched it; never fetched here
STEP_DIR = "roadmap/data/steps/"
LANE_ENV, LANE_ENV_PREFIX, LANE_PREFIX = "CLAUDE_CODE_REMOTE_SESSION_ID", "cse_", "session_"
_step_read = None  # the step id the last take() read for its step decision, for the log line
# What a refusal prints so the owner can copy the word that lifts it (step c80). The line names the
# typed word and never the refused target. A model or an agent only offers the line; text from an
# agent grants nothing, because the grant file lives in frozen state.
NO_OVERRIDE = "No override lifts this refusal."


def offer(rule, spawn_role=None, agent_id=None, spawn_model=None):
    """The line an owner types to lift a refusal of this rule, for the call that was refused. For the model ceiling's
    refusal of a spawn above its role's model, the line names no keyword and no model: the owner's own words name the
    model for this work, or `override` lifts it. `spawn_model` is accepted so a caller may pass it; the line is the same
    for every model."""
    if rule == OPUS_RULE and spawn_role is not None:
        return ("The owner lifts this by naming the model for this work in his own words, or by typing %s."
                % ("`override 15m` (a one-act `override` does not reach an agent's call)" if agent_id
                   else "`override` for this one act"))
    if agent_id:
        return ("To allow this act, type `override 15m`. A one-act `override` does not reach an agent's call.")
    return ("To allow this act, type `override` for this one act, or `override 15m` for every refused act "
            "for 15 minutes.")


def now():
    """The clock of the prompt hook (LOCAL_TIME_NOW in tests), so grant and take agree."""
    import local_time
    return local_time.clock()


def _path(session_id, *folder):
    """The session's override file, or with folder "opus" its Opus override file. None when the id
    cannot name a file."""
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id) or session_id[0] == ".":
        return None
    return os.path.join(config_dir(), "state", "override", *folder, session_id + ".json")


def _write(path, data):
    """Write an override file whole: a new file always replaces the old, unread."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    scratch = "%s.%s.tmp" % (path, uuid.uuid4().hex)
    with open(scratch, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(scratch, path)


def _length_end(at, number, unit):
    """The instant a length of `number` units (`h` hours, anything else minutes) ends, from `at`."""
    number = int(number)
    return at + (timedelta(hours=number) if unit and unit.lower() == "h" else timedelta(minutes=number))


def _write_override(session_id, path, kind, until):
    """Write the session's override file whole: the one home of its shape, for the keyword grant and the plain ask.
    Clears old claim markers first. Returns (kind, until)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _sweep_claims(os.path.dirname(path))
    _write(path, {"kind": kind, "until": until.astimezone(timezone.utc).isoformat(),
                  "id": uuid.uuid4().hex})  # the id gives each override its own claim marker
    return kind, until


def opus_role(word):
    """The role a word names, singular or plural, from OPUS_ROLES, else None."""
    word = word.lower()
    for role in OPUS_ROLES:
        if word in (role, role + "s"):
            return role
    return None


def _write_opus(session_id, path, at, length, role, said, model, end=None, log=True):
    """Write the held model's pass file for `length` = (number, unit) from `at` and log it: the one home of the file's shape,
    for grant_model_ask. `role` is None, one role, or a sorted list of 2 or more roles. `said` is the owner's words, for
    the file and the log; `log` False writes the file and no log line. The file keeps `model`, `at`, `said` and, for an ask
    with no length of its own, `end` "report": the hold then ends at the session's next report, or at `until`, whichever
    comes first. Returns ("opus" or "model", until, role, end, model)."""
    number, unit = length
    until = _length_end(at, number, unit)
    ends = until.astimezone(timezone.utc).isoformat()
    body = {"kind": "opus", "until": ends, "role": role, "model": model, "at": at.astimezone(timezone.utc).isoformat(),
            "said": " ".join((said or "").split())}
    if end:
        body["end"] = end
    _write(path, body)
    result = ("opus" if model == "opus" else "model", until, role, end, model)
    if not log:
        return result
    detail = "%s until %s" % (", ".join(role) if isinstance(role, list) else role or "every role", ends)
    if model != "opus":
        detail = "model %s, %s" % (model, detail)
    if end:
        detail += " (or the next report)"
    if said:
        detail += ": " + said[:LOG_REASON_MAX].encode("utf-8", "replace").decode("utf-8")
    _log(session_id, "opus-grant", detail)
    return result


def _strip_blocks(prompt):
    """The prompt with each pasted or machine-tag block replaced by a marker: that text is not the owner's words."""
    return BLOCKS.sub("[pasted text]", prompt)


def model_mentions(text, family):
    """(named, negated) for the whole words of `text` that hold the model family `family` (also inside claude-haiku-4-5 and
    haiku-4.5), read after the pasted and machine blocks are cut (_strip_blocks): `named` is true for a mention no negation
    reaches, `negated` for one a negation reaches. A mention is negated when, between it and the start of its clause
    (MODEL_CLAUSE_BREAK) or the nearest word of MODEL_SPAN_BREAKS before it, stands a word of MODEL_NEGATIONS or one ending
    n't; a pair of MODEL_NEGATION_PAIRS negates only when it stands just before the mention. So "Not sonnet but haiku",
    "Instead use haiku" and "Skip the checks and run it on haiku" name haiku, and "don't use haiku" negates it. The one
    reader of that reach: guard.owner_names_model (a turn that negates any mention names nothing) and the end of a held
    model (_negates: _turn_negates_hold, grant_model_ask)."""
    mention = re.compile(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(family), re.I)
    named = negated = False
    for clause in MODEL_CLAUSE_BREAK.split(_strip_blocks(text or "")):
        words = [w.lower() for w in ROLE_WORDS.findall(clause)]
        for at, word in enumerate(words):
            if not mention.search(word):
                continue
            hit = tuple(words[max(at - 2, 0):at]) in MODEL_NEGATION_PAIRS
            for i in range(at - 1, -1, -1):
                if hit or words[i] in MODEL_SPAN_BREAKS:
                    break
                hit = words[i] in MODEL_NEGATIONS or words[i].endswith(("n't", "n\u2019t"))
            named, negated = named or not hit, negated or hit
    return named, negated


def _negates(text, family):
    """True when `text` mentions the model `family` and every mention is negated (model_mentions): no un-negated mention
    is left to name it. "Do not use opus" negates it; "Don't use opus for the audit, use opus for the builders" does not."""
    named, negated = model_mentions(text, family)
    return negated and not named


def _strip_quotes(text):
    """`text` less the reply quotes (REPLY_QUOTES): what he pasted back from Claude's own report is not his words."""
    return REPLY_QUOTES.sub(" ", text)


def _names_models(text):
    """The set of model families (MODEL_FAMILIES) the whole words of `text` name, lower case."""
    return {m.group(1).lower() for m in MODEL_WORD.finditer(text)}


def _family(model):
    """The family a model name holds (`claude-sonnet-5-5` is `sonnet`), the highest when it holds more than one, else
    None. The one reader of a model name here; hooks/guard.py role_model_rank ranks the same names."""
    value = str(model or "").lower()
    return next((word for word in reversed(MODEL_FAMILIES) if word in value), None)


def _ask_lengths(text, bare=None):
    """The lengths in a plain ask `text` as (number, unit letter) pairs, plus `bare` (a pair) when given, or None when
    they are unclear: two or more, a decimal or a compound length. The one length check of the plain asks."""
    found = [(m.group(1), (m.group(2) or m.group(3))[0]) for m in ASK_LENGTH.finditer(text)]
    if bare:
        found.append(bare)
    if len(found) > 1 or UNCLEAR_LENGTH.search(text):
        return None
    return found


def _near_negation(names, at, negations):
    """True when a word of `negations` stands within NEGATION_SPAN words before or after the word at names[at]. The one
    negation check of the plain asks."""
    near = names[max(0, at - NEGATION_SPAN):at] + names[at + 1:at + 1 + NEGATION_SPAN]
    return bool(negations & {w.lower() for w in near})


def model_role(word):
    """The role a word names, singular or plural, from MODEL_ROLES (MODEL_ROLE_WORDS), else None."""
    return MODEL_ROLE_WORDS.get(word.lower())


def _ask_scope(text, resolve=model_role, allowed=MODEL_ROLES):
    """(length, roles) a plain ask names, or None when the words are unclear: two lengths, a decimal or compound
    length, a role with a negation within NEGATION_SPAN words before or after it, or two role words joined by
    anything but a plain list (PLAIN_LIST). `roles` is the sorted list of the roles it names, empty when it names
    none. A role word is `resolve`d and must be in `allowed`: the model ask reads MODEL_ROLES."""
    lengths = _ask_lengths(text)
    if lengths is None:
        return None
    matches = list(ROLE_WORDS.finditer(text))
    words = [m.group() for m in matches]
    roles, last_end = set(), None
    for at, word in enumerate(words):
        role = resolve(word)
        if role not in allowed:
            continue
        if _near_negation(words, at, NEGATIONS):
            return None
        if last_end is not None and not PLAIN_LIST.fullmatch(text, last_end, matches[at].start()):
            return None
        roles.add(role)
        last_end = matches[at].end()
    return (lengths[0] if lengths else DEFAULT_ASK_LENGTH), sorted(roles)


def _file_role(roles):
    """The file's `role` value for a list of roles: None for none, the role for one, else the sorted list."""
    roles = sorted(set(roles))
    return None if not roles else roles[0] if len(roles) == 1 else roles


def _text_of(rec):
    """The owner text of one transcript record (lint/_transcript.py owner_text), or None."""
    from guard_core import lint_dir  # lazy: the one home of where lint/ is
    lint = lint_dir()
    if lint not in sys.path:
        sys.path.insert(0, lint)
    import _transcript
    return _transcript.owner_text(rec, NOTICE_TAGS)


def _tail_prompts(transcript):
    """[(offset, record)] for each owner prompt record in the last SEED_READ_MAX bytes, in order. Attachment, assistant
    and other non-prompt records are left out. Cost: one open, one read of that tail."""
    if not isinstance(transcript, str):  # no transcript_path in the payload; an int would open a descriptor
        return []
    try:
        with open(transcript, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            at = max(0, handle.tell() - SEED_READ_MAX)
            handle.seek(at)
            lines = handle.read().splitlines(True)
    except OSError:
        return []
    found = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if isinstance(rec, dict) and _text_of(rec) is not None:
            found.append((at, rec))
        at += len(line)
    return found


def _owner_text(rec, typed=True):
    """The words of a record that is an owner's typed turn, else None: the one test for the seed check and the scope
    context. Not an isMeta record, a compaction summary, a promptSource "system" record, a record whose origin kind is
    not human, a command record (`/effort`) or a fired scheduled task's block. With `typed`, a record whose
    `turnOrigin` is neither absent nor "human" is not his either: a session's seed brief (host_synthetic, sdk) is the
    session that started it speaking. The seed check passes typed False so it still finds that first turn."""
    if not isinstance(rec, dict) or rec.get("isMeta") or rec.get("isCompactSummary") or rec.get("promptSource") == "system":
        return None
    if typed and rec.get("turnOrigin") not in (None, "human"):
        return None
    origin = rec.get("origin")
    if isinstance(origin, dict) and origin.get("kind", "human") != "human":
        return None
    text = _text_of(rec)
    if text is None or text.lstrip().startswith(COMMAND_RECORDS) or FIRED_TASK.search(text):
        return None
    return text


def latest_owner_text(transcript):
    """The words of the owner's last typed turn in the transcript at path `transcript`, or None: no path, an unreadable or
    empty transcript, or no owner turn in it. The one reader of the last turn for a guard that lets the owner's own word
    through (hooks/guard.py owner_names_model). Reads backward from the end in SEED_READ_MAX chunks and stops at the first
    owner turn, so the latest turn is found however far back it sits. Cost, on demand: one open and one chunk read (at
    most 1 MiB) when the turn is in the last MiB, one more chunk per MiB of reply after it, and the whole file once when
    it holds no owner turn."""
    for rec in _records_backward(transcript):
        text = _owner_text(rec)
        if text is not None:
            return text
    return None


def _records_backward(transcript, only=None):
    """Each JSON record of the transcript at path `transcript`, last first, read in SEED_READ_MAX chunks from the end
    and only as far as the caller goes: the one backward reader (the owner's last turn, the report after a hold). A
    missing or unreadable file, or no path, yields nothing. `only` is a compiled bytes pattern: a line that does not
    match it is skipped unparsed, so a caller that wants one kind of record pays no parse for the rest."""
    if not isinstance(transcript, str):  # no transcript_path in the payload; an int would open a descriptor
        return
    try:
        with open(transcript, "rb") as handle:
            end, carry = handle.seek(0, os.SEEK_END), b""
            while end > 0:
                start = max(0, end - SEED_READ_MAX)
                handle.seek(start)
                lines = (handle.read(end - start) + carry).split(b"\n")
                # lines[0] may be a cut line: it joins the next chunk back
                carry, body = (lines[0], lines[1:]) if start else (b"", lines)
                for line in reversed(body):
                    if only is not None and not only.search(line):
                        continue
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
                end = start
    except OSError:
        return


def _own_record(found, prompt):
    """Offset of the prompt's own record among `found` (_tail_prompts): the last owner prompt record whose text equals
    the prompt, or None."""
    own = [at for at, rec in found if _text_of(rec).strip() == prompt.strip()]
    return own[-1] if own else None


def _seed_record(transcript, found, prompt):
    """Offset of the first owner turn (_owner_text) in the transcript at path `transcript` other than the prompt's own
    record (_own_record in `found`, the _tail_prompts read), else None. In a cloud session it is the seed brief. Cost:
    one open, lines read from the top until the first owner turn, at most SEED_READ_MAX bytes."""
    if not isinstance(transcript, str):
        return None
    own = _own_record(found, prompt)
    try:
        with open(transcript, "rb") as handle:
            while handle.tell() < SEED_READ_MAX:
                at = handle.tell()
                line = handle.readline(SEED_READ_MAX)
                if not line:
                    return None
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if at != own and _owner_text(rec, typed=False) is not None:
                    return at
    except OSError:
        pass
    return None


def _seed_turn(found, prompt):
    """True when the prompt's own record among `found` (_own_record) has a turnOrigin that is neither absent nor "human": a
    session's seed brief (host_synthetic, sdk), in a local session as in a cloud one. No own record is no seed turn."""
    at = _own_record(found, prompt)
    rec = next((r for pos, r in found if pos == at), None) if at is not None else None
    return isinstance(rec, dict) and rec.get("turnOrigin") not in (None, "human")


def _system_prompt_last(found, prompt):
    """True when the last owner prompt record of `found` is the prompt itself with promptSource "system": a timed
    check-in or other harness turn."""
    return bool(found) and found[-1][1].get("promptSource") == "system" and _text_of(found[-1][1]).strip() == prompt.strip()


def _context_prompts(found, prompt, seed=None):
    """The owner's earlier typed prompts for the scope read, oldest first: the records of `found` before the prompt's own
    record that pass _owner_text, less the record at offset `seed` (a cloud session's seed brief, _seed_record), each
    through _strip_blocks and cut to SCOPE_CONTEXT_CHARS, the newest SCOPE_CONTEXT_PROMPTS of them. The ask's own
    words, agent text, notices, pasted content and the seed brief never reach it."""
    own = _own_record(found, prompt)
    texts = []
    for at, rec in found:
        text = _owner_text(rec) if (own is None or at < own) and at != seed else None
        text = _strip_blocks(text).strip() if text is not None else ""
        if text:
            texts.append(text[:SCOPE_CONTEXT_CHARS])
    return texts[-SCOPE_CONTEXT_PROMPTS:]


def _scoped_roles(scope_judge, text, context):
    """The roles the scope read names from `context`, sorted, each one of ASK_ROLES; empty (every role) when the read
    raises, answers anything but a list of strings, or names no role of ASK_ROLES. The read only narrows the grant."""
    try:
        named = scope_judge(text, context)
    except Exception as exc:
        print("override: scope read grants every role: %s" % " ".join(str(exc).split()), file=sys.stderr)
        return []
    if not isinstance(named, (list, tuple)):
        return []
    return sorted({w.strip().lower() for w in named if isinstance(w, str)} & set(ASK_ROLES))


def _owner_ask(prompt, source, transcript, wanted, strip_quotes=False):
    """The gates of the plain asks (grant_model_ask, grant_override_ask), the one home. Returns (text, found, seed) for a
    prompt that may go to a judge, else None. `text` is the prompt less its pasted and notice blocks. `found` is the
    tail read (_tail_prompts). `seed` is a cloud session's seed record offset, else None. `wanted(text)` is the route's
    own test of the words, run before the transcript is read. None for: a non-string, a `source` outside
    OPUS_ASK_SOURCES, a missing NOTICE_TAGS, a prompt that starts with a notice, a fired-task block, words the route
    does not want, a prompt whose own record is last in the transcript with promptSource "system", and in a cloud
    session (env LANE_ENV set) a prompt with no earlier owner turn (the seed prompt). With `strip_quotes`, the reply
    quotes (_strip_quotes) are cut from `text` too, before `wanted` reads it and before any judge sees it."""
    if not isinstance(prompt, str) or source not in OPUS_ASK_SOURCES:
        return None
    if not NOTICE_TAGS or prompt.lstrip().startswith(NOTICE_TAGS) or FIRED_TASK.search(prompt):
        return None  # a stored task, a notice or no tag list: not typed words
    text = _strip_blocks(prompt)
    if strip_quotes:
        text = _strip_quotes(text)
    if not wanted(text):
        return None
    found = _tail_prompts(transcript)
    if _system_prompt_last(found, prompt):
        return None
    seed = _seed_record(transcript, found, prompt) if os.environ.get(LANE_ENV) else None
    if os.environ.get(LANE_ENV) and seed is None:
        return None
    return text, found, seed


def _model_wanted(text):
    """True when the model ask may go to its judge on its words alone: a whole model word, Opus and Fable included, and no
    whole word `override` outside code spans (the override ask judges that prompt, except one that names Opus)."""
    return bool(_names_models(text)) and OVERRIDE_WORD.search(_outside_code(text)) is None


def _end_hold(session_id, path, family=None, why=""):
    """End the session's held model: delete its pass file when it holds `family` (any model when None, and a file that
    cannot be read). Returns ("opus-off", None) for an Opus hold, ("model-off", None, family) for another, else None when
    there was nothing to end or it holds another model. One `opus-off` line to guard.log."""
    hold = _read_hold(path)
    if hold is None or (isinstance(hold, dict) and family not in (None, hold["model"])):
        return None
    held = hold["model"] if isinstance(hold, dict) else family or "opus"
    try:
        os.remove(path)
    except FileNotFoundError:
        return None
    _log(session_id, "opus-off", ("%s: %s" % (held, why)) if why else held)
    return ("opus-off", None) if held == "opus" else ("model-off", None, held)


def _grant_end_word(session_id, prompt):
    """His end word as the whole prompt, after pasted blocks and reply quotes are cut: `no sonnet` or `sonnet off`. It ends
    the session's held model when it is that one (_end_hold). Never a model call. Returns what _end_hold returns, else None."""
    path = _path(session_id, "opus")
    said = END_WORD.fullmatch(_strip_quotes(_strip_blocks(prompt)).strip()) if path and isinstance(prompt, str) else None
    return _end_hold(session_id, path, (said.group(1) or said.group(2)).lower()) if said else None


def grant_model_ask(session_id, prompt, at, judge=None, transcript=None, source=None, scope_judge=None):
    """The owner's plain model ask (`use opus for the reviewers`, `opus builders 2h`, `run it on haiku`): the model he chose,
    held in the session's pass file, when a model says the prompt is his own present choice of one model (decision
    agent-model-cap, the owner's model name). `judge` is call_judge.model_ask unless a caller passes another: it returns the
    model family, False for a plain no, None for an error, a timeout or an odd answer. `scope_judge` is call_judge.opus_scope
    unless a caller passes another. Returns ("model" or "opus", until, role, end, model) for a hold written,
    ("opus-off" or "model-off", ...) when a judge no or an error ended a held model, else None.
    The words: a whole model word, outside pasted blocks, notices and reply quotes, from an owner prompt that passes the
    gates of _owner_ask and is no seed brief (_seed_turn, local or cloud), with no whole word `override` outside code spans.
    One prompt reaches one judge. The roles named and the length are _ask_scope's reading (MODEL_ROLES): a length he states
    is the hold's `until`; with none it ends at the next report or after DEFAULT_ASK_LENGTH. A prompt whose every mention of
    the judged model is negated writes nothing, whatever the judge says (model_mentions); a question mark refuses nothing.
    A held model ends on a judge yes for another model (the file is replaced), a judge error (the file is deleted:
    his words could not be read, so no model he named earlier stays on), his end words (_grant_end_word), or a judge no
    when this turn negates the held model with no un-negated mention of it ("Do not use haiku": model_mentions; a later
    model word ends the earlier one). A judge no that negates another model, or names the held one un-negated, keeps it.
    A judge that answers a model the words do not name is an odd answer, so an error.
    A yes for Opus or Fable that names no role reads the owner's earlier typed prompts for the roles they name
    (_context_prompts, `scope_judge`), once, only when such a prompt exists: the every-role file goes down first and a valid
    answer narrows it, so a kill in the read (the prompt hook's timeout) leaves every role with no `opus-grant` line.
    Cost: for a prompt that names no model, nothing: the word test runs before any file read. For one that does, one tail
    read, one judge call (call_judge.model_ask, a Haiku call of at most OPUS_ASK_TIMEOUT s), one file write or delete, and
    that one scope call."""
    path = _path(session_id, "opus")
    if path is None or not isinstance(prompt, str):
        return None
    gated = _owner_ask(prompt, source, transcript, _model_wanted, strip_quotes=True)
    if gated is None:
        return None
    text, found, seed = gated
    if _seed_turn(found, prompt):
        return None  # a seed brief is the session that started this one speaking, never the owner's choice of a model
    try:
        if judge is None:
            from call_judge import model_ask as judge
        family = judge(text)
    except Exception as exc:
        print("override: model ask clears the held model: %s" % " ".join(str(exc).split()), file=sys.stderr)
        family = None
    if family is not False and family not in _names_models(text):  # an error, an odd answer, or a model the words do not name
        return _end_hold(session_id, path, why="the judge could not read the owner's words")
    if family is False or not model_mentions(text, family)[0]:
        hold = _read_hold(path)  # a no, or a yes the words negate, keeps the held model unless this turn negates it
        ends = isinstance(hold, dict) and hold["judged"] and _negates(text, hold["model"])
        return _end_hold(session_id, path, hold["model"], "the owner's turn negates it") if ends else None
    scope = _ask_scope(text)
    if scope is None:
        return None
    length, roles = scope
    said = " ".join(text.split())
    end = None if _ask_lengths(text) else HOLD_END_REPORT  # a length he states is his; with none, the report ends it
    context = [] if roles or family not in ABOVE_SONNET else _context_prompts(found, prompt, seed)
    if context:
        # No scope means every role, so that file goes down first: the prompt hook's timeout can kill the process in the
        # scope read, and a kill must leave the every-role file. A valid answer then narrows it.
        _write_opus(session_id, path, at, length, None, said, family, end, log=False)
        if scope_judge is None:
            from call_judge import opus_scope as scope_judge
        try:
            roles = _scoped_roles(scope_judge, text, context)
        except BaseException:  # an interrupt or an exit during the read: log the every-role hold that stands
            _write_opus(session_id, path, at, length, None, said, family, end)
            raise
    return _write_opus(session_id, path, at, length, _file_role(roles), said, family, end)


# One prose line that is the whole keyword form (an override line inside a prose message counts):
# `override`, `override <n>[m|h]`, `override off`, or `override: <reason>`.
FENCED = re.compile(r"```.*?```|```.*|~~~.*?~~~|~~~.*", re.S)
INDENTED = re.compile(r"(?: {4}|\t)")  # markdown's code block: a line that starts with 4 spaces or a tab
KEYWORD_LINE = re.compile(r"override(?:\s*:\s*(\S.*)|\s+(off|\d+[mh]?))?", re.I)


def _keyword_line(prompt):
    """The prompt text a prose line grants: the first whole line that is a keyword form, after pasted or machine blocks,
    fenced blocks (backtick or tilde) and indented code lines are left out, as an `override ...` string for the one
    grant path. None for no such line. A mention inside a sentence is no whole line, so it never grants."""
    if not isinstance(prompt, str):
        return None
    for line in FENCED.sub("\n", BLOCKS.sub("\n", prompt)).splitlines():
        if not INDENTED.match(line) and KEYWORD_LINE.fullmatch(line.strip()):
            return line.strip()
    return None


def grant(session_id, prompt, at, defer=True, transcript=None, source=None):
    """Write, replace or remove the session's override for one owner prompt. A keyword line inside a prose message
    counts (_keyword_line) when the first-word form of the prompt grants nothing, and only for an owner-typed prompt:
    the plain asks' gates (_owner_ask) refuse a notice, a fired task, an agent's `source`, and in a cloud session the
    seed brief, which its coordinator wrote. Only the line route reads the transcript."""
    got = _grant_first_word(session_id, prompt, at, defer)
    if got is None:
        got = _grant_end_word(session_id, prompt)
        if got is not None:
            return got
        line = _keyword_line(prompt)
        if line is not None and line != (prompt.strip() if isinstance(prompt, str) else None):
            try:
                gated = _owner_ask(prompt, source, transcript, lambda text: True)
            except Exception as exc:  # a gate that cannot run grants nothing
                print("override: prose line grants nothing: %s" % " ".join(str(exc).split()), file=sys.stderr)
                return None
            if gated is not None:
                return _grant_first_word(session_id, line, at, False)
    return got


def _grant_first_word(session_id, prompt, at, defer=True):
    """Write, replace or remove the session's override for one owner prompt. Returns (kind, until) for a
    new override, ("off", None) when `override off` removed one, else None: the prompt is not a word. With `defer`, a
    first word `override` whose rest is no whole keyword form and holds a length returns None too, so the plain ask (grant_override_ask) judges it; grant_override_ask calls again
    with `defer` False for main's result."""
    said = PROMPT.match(prompt) if isinstance(prompt, str) else None
    path = _path(session_id)
    if not said or path is None:
        return None
    reason = " ".join(said.group(1).split())  # one log line: newlines and tabs fold to spaces
    word = WORD.fullmatch(reason)
    if not word and WORD.fullmatch(reason.split(" ")[0]):
        return None  # a word after `off` or a length: ambiguous, grants nothing
    if not word and defer and ASK_LENGTH.search(reason):
        return None  # a plain ask with a length: grant_override_ask judges it
    off, number, unit = word.groups() if word else (None, None, None)
    if off:
        try:
            os.remove(path)
        except FileNotFoundError:
            return None
        return "off", None
    if number is None:
        kind, until = "once", at + ONCE_WINDOW
    else:
        kind, until = "timed", _length_end(at, number, unit)
    _write_override(session_id, path, kind, until)
    if reason and kind == "once":
        _log_reason(session_id, reason, at)
    return kind, until


def _outside_code(text):
    """`text` with each backtick code span (a fenced block, an unclosed fence to the end, or an inline span) replaced by a
    space: a word inside one is quoted, never the owner's own."""
    return CODE_SPANS.sub(" ", text)


def _override_wanted(text):
    """True when the plain override ask may go to the judge on its words alone: the whole word `override` outside code
    spans with no NEGATIONS word or `off` within NEGATION_SPAN words of it, no `?`, and no whole word `opus`."""
    clean = _outside_code(text)
    starts = {m.start() for m in OVERRIDE_WORD.finditer(clean)}
    if not starts or "?" in text or OPUS_WORD.search(text):
        return False
    words = list(ROLE_WORDS.finditer(clean))
    names = [m.group().lower() for m in words]
    return not any(_near_negation(names, at, OVERRIDE_NEGATIONS)
                   for at, match in enumerate(words) if match.start() in starts)


def _override_length(text):
    """(number, unit) of the one length in the plain override ask `text`, None for no length, False for words that are
    unclear (_ask_lengths). A bare number right after the prompt's own first word `override` is minutes: that word is
    read on `text` as typed, so a code span before it makes no first word. Code spans do not count."""
    first = PROMPT.match(text)
    rest = first.group(1) if first else ""
    bare = BARE_NUMBER.match(rest)
    lengths = _ask_lengths(_outside_code(text), (bare.group(1), "m") if bare and not ASK_LENGTH.match(rest) else None)
    return False if lengths is None else lengths[0] if lengths else None


def grant_override_ask(session_id, prompt, at, judge=None, transcript=None, source=None):
    """The owner's plain override ask (`yes override that`, `override that for 15 minutes please`): an override written
    when the model says the prompt is the owner's own present request to override a refusal (decision owner-override).
    `judge` is call_judge.override_ask unless a caller passes another. Returns (kind, until) for a new override, else
    None. A timed override for the one length in the words, else a one-act override with the ONCE_WINDOW. The module
    docstring holds the rules. Cost: one tail read and one judge call, only for a prompt that holds the whole word
    `override` outside code spans and passes _override_wanted and the gates (_owner_ask); the judge sees the stripped
    ask alone.
    A first word `override` is a keyword form grant() deferred. Every outcome but a judge yes for a timed override
    (a gate, unclear words, a judge no, an error or an odd answer) returns grant(defer=False): a reason form stays a
    one-act override with its reason logged, `override 15m please` stays nothing. A judge error never widens it."""
    path = _path(session_id)
    if path is None or not isinstance(prompt, str):
        return None
    keyword = PROMPT.match(prompt) is not None

    def main():
        return _grant_first_word(session_id, prompt, at, defer=False) if keyword else None

    try:  # a gate that raises (a transcript read, an import) leaves main's result standing
        gated = _owner_ask(prompt, source, transcript, _override_wanted)
        length = _override_length(gated[0]) if gated else False
    except Exception as exc:
        print("override: plain ask grants nothing new: %s" % " ".join(str(exc).split()), file=sys.stderr)
        return main()
    if gated is None or length is False:
        return main()
    try:
        if judge is None:
            from call_judge import override_ask as judge
        said_yes = judge(gated[0]) is True
    except Exception as exc:
        print("override: plain ask grants nothing new: %s" % " ".join(str(exc).split()), file=sys.stderr)
        said_yes = False
    if not said_yes or (length is None and keyword):
        return main()
    if length is None:
        done = _write_override(session_id, path, "once", at + ONCE_WINDOW)
        _log_reason(session_id, " ".join(gated[0].split()), at)  # the keyword once logs its reason the same way
        return done
    return _write_override(session_id, path, "timed", _length_end(at, *length))


def _sweep_claims(folder):
    """Delete claim markers older than CLAIM_KEEP. A newer one may still stop a racer that read its
    override before the override was spent."""
    import time
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.endswith(".claim"):
            marker = os.path.join(folder, name)
            try:
                if time.time() - os.path.getmtime(marker) > CLAIM_KEEP:
                    os.remove(marker)
            except OSError:
                pass


def _claim(path, raw):
    """True for the one call that creates this override's claim marker, else False."""
    marker = "%s.%s.claim" % (path, hashlib.sha256(raw).hexdigest()[:32])
    try:
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except OSError:
        return False  # another call claimed it first, or the marker cannot be made: no override
    return True


def _log_reason(session_id, reason, at):
    """Write the owner's reason as one guard.log line through the guard's own locked writer. A lone
    surrogate cannot be encoded, so it becomes `?` before the write rather than losing the line."""
    _log(session_id, "override-reason", reason[:LOG_REASON_MAX].encode("utf-8", "replace").decode("utf-8"),
         "owner-override")


def _log(session_id, decision, detail, rule=OPUS_RULE):
    import guard_core  # lazy: only a grant that logs needs it
    guard_core.set_log_session(session_id)
    guard_core.record("UserPromptSubmit", decision, rule, detail)


def _parse_when(text):
    """An ISO-8601 time (a trailing Z is UTC, a time with no offset is read as UTC) as an aware datetime, else None."""
    if not isinstance(text, str):
        return None
    try:
        when = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)


def _lower_roles(role):
    """The file's `role` (None, one role, a list) with each role lower case, the form a spawn's role is compared in."""
    return [r.lower() for r in role] if isinstance(role, list) else role.lower() if isinstance(role, str) else None


def _read_hold(path):
    """The session's pass file at `path` as a dict {model, until, role, end, at, said, judged}, None when it is absent,
    OPUS_UNREAD when it cannot be read or has the wrong shape. `model` is the family it holds, Opus when the file has none
    (an old keyword grant wrote none); `judged` is true only when the file names its model, as a judged plain ask writes it.
    `role` is None, one role or a list, lower case; the roles of an Opus file must be OPUS_ROLES or Explore, those of
    another model's file any names (MODEL_ROLES: Explore too). `end` is None or HOLD_END_REPORT; `at` is None when the file has
    none or none that reads."""
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
        until, role = datetime.fromisoformat(data["until"]), data["role"]
        model = data.get("model", "opus")
        roles = role if isinstance(role, list) else [role]  # null, one role, or a list of roles
        if (data["kind"] != "opus" or until.tzinfo is None or (isinstance(role, list) and not role)
                or (model != "opus" and model not in MODEL_FAMILIES) or data.get("end") not in (None, HOLD_END_REPORT)
                or any(r is not None and (not isinstance(r, str) or (model == "opus" and opus_role(r) != r and r != "Explore"))
                       for r in roles)):
            return OPUS_UNREAD
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return OPUS_UNREAD
    said = data.get("said")
    return {"model": model, "until": until, "role": _lower_roles(role), "end": data.get("end"),
            "at": _parse_when(data.get("at")), "said": said if isinstance(said, str) else "",
            "judged": "model" in data}


REPORT_BLOCK = re.compile(r"^\s*>", re.M)  # a report is a block of `>` lines, so a reply with none is no report
ASSISTANT_LINE = re.compile(rb'"type":\s*"assistant"')  # the transcript lines that can hold a reply, found before any parse


def _assistant_text(rec):
    """The text blocks of an assistant record joined by newlines, else ""."""
    message = rec.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        return "\n".join(b["text"] for b in content if isinstance(b, dict) and isinstance(b.get("text"), str))
    return content if isinstance(content, str) else ""


def _report_shape_ok():
    """lint/report_guard.py report_shape_ok, the one test of a report's shape. Imported on demand: only a hold that ends at
    the report, with a reply after it that holds a block of `>` lines, needs it."""
    from guard_core import lint_dir
    lint = lint_dir()
    if lint not in sys.path:
        sys.path.insert(0, lint)
    import report_guard
    return report_guard.report_shape_ok


def _report_since(at, transcript, records=None, report_ok=None):
    """True when an assistant reply stamped after `at` is a report (`report_ok`, report_guard.report_shape_ok by default). The
    reads go backward from the end of the transcript at path `transcript` (_records_backward), or through the parsed
    `records` the caller already holds, and stop at the first record stamped at or before `at`, so the cost is the
    replies since the hold. An agent's own record (isSidechain) is no report of the session. A transcript that cannot be
    read finds no report: the hold stays until `until`. A shape test that cannot load or run counts the reply as a report,
    so the hold ends."""
    for rec in reversed(records) if records is not None else _records_backward(transcript, ASSISTANT_LINE):
        if not isinstance(rec, dict):
            continue
        sent = _parse_when(rec.get("timestamp"))
        if sent is not None and sent <= at:
            return False
        if rec.get("type") != "assistant" or rec.get("isSidechain"):
            continue
        text = _assistant_text(rec)
        if not REPORT_BLOCK.search(text):
            continue
        try:
            report_ok = report_ok or _report_shape_ok()
            if report_ok(text):
                return True
        except Exception:
            return True  # an unreadable shape test ends the hold: with no hold the guard refuses, the stricter side
    return False


def _turn_negates_hold(hold, transcript=None, records=None):
    """True when `hold` is a judged hold and the owner's latest typed turn (the transcript at path `transcript`, or the
    parsed `records`) negates its model with no un-negated mention of it (_negates): "Do not use haiku" after a held haiku,
    or "don't use opus for the audit" after a held Opus; "don't use haiku, use opus" keeps a held Opus. A later model word
    ends the earlier one, and the prompt hook ends the hold on a judge no or an error (grant_model_ask); this read ends it
    for a call that comes before the hook has deleted the file, or when the hook did not run. A model-less file (a keyword
    grant left on disk) ends only on `opus off` and its own length. Cost, on demand: one backward read to the owner's last
    turn."""
    if not hold["judged"]:
        return False
    if records is not None:
        text = next((t for t in (_owner_text(rec) for rec in reversed(records)) if t is not None), None)
    else:
        text = latest_owner_text(transcript)
    return _negates(text, hold["model"])


def model_override(session_id, transcript=None, records=None, report_ok=None, at=None):
    """The session's live model hold as a dict (_read_hold), else None: the one reader the guard and the turn-end model line
    share, so the two cannot disagree. Live means the pass file reads, `at` (now by default) is before its `until`, a
    hold with `end` "report" has no report after it (_report_since, from the transcript at path `transcript` or the parsed
    `records`), and the owner's latest typed turn does not negate its model (_turn_negates_hold). A file with no `at`
    cannot tell, so only `until` ends it. Cost, on demand: one open of the pass file; for a hold that ends at the report,
    the replies since it; for a judged hold of a model other than Opus, one read of the owner's last turn. It writes nothing."""
    path = _path(session_id, "opus")
    hold = _read_hold(path) if path else None
    if not isinstance(hold, dict) or (now() if at is None else at) >= hold["until"]:
        return None
    if hold["end"] == HOLD_END_REPORT and hold["at"] is not None and _report_since(hold["at"], transcript, records, report_ok):
        return None
    if _turn_negates_hold(hold, transcript, records):
        return None
    return hold


def _take_opus(session_id, spawn_role, at, transcript=None, model=None):
    """OPUS_LIFTED when the session's pass file covers a spawn of spawn_role on `model` now, OPUS_UNREAD when the file
    exists but cannot be read, else None. A held model lifts only a spawn on that model (`model` None is an Opus spawn,
    the Opus ceiling's own call): a held sonnet lifts no Opus ceiling, a model-less file (Opus) lifts no Fable
    spawn, and a held Fable lifts a Fable spawn only. A hold that ends at the report is not read as live after a report in
    the transcript at path `transcript`, and a judged hold the owner's latest typed turn negates is not live (_turn_negates_hold)."""
    path = _path(session_id, "opus")
    if path is None:
        return None
    hold = _read_hold(path)
    if not isinstance(hold, dict):
        return hold
    until, role = hold["until"], hold["role"]
    if isinstance(role, list) and str(spawn_role).lower() in role:
        role = str(spawn_role).lower()  # a list that names the spawn's role covers it as that one role
    if at >= until or (role is not None and role != str(spawn_role).lower()):
        return None
    if hold["model"] != ("opus" if model is None else _family(model)):
        return None
    if hold["end"] == HOLD_END_REPORT and hold["at"] is not None and _report_since(hold["at"], transcript):
        return None
    if _turn_negates_hold(hold, transcript):
        return None
    return OPUS_LIFTED


def remote_session_id():
    """The session record id (session_<x>) the env names as cse_<x>, or None when the env is unset or of another shape."""
    remote = os.environ.get(LANE_ENV) or ""
    rest = remote[len(LANE_ENV_PREFIX):] if remote.startswith(LANE_ENV_PREFIX) else ""
    return LANE_PREFIX + rest if rest else None


def _lane_id(session_id):
    """The lane's id as a step's `lane` field names it, or None. A set env value of another shape is no id."""
    if os.environ.get(LANE_ENV):
        lane = remote_session_id()
    else:
        lane = session_id
    if not isinstance(lane, str) or not SESSION_ID.fullmatch(lane) or lane[0] == ".":
        return None
    return lane


def _grant_role(grant):
    """The role a well-formed grant covers: None for every role, else one role from OPUS_ROLES. Raises
    ValueError for a grant of the wrong shape or an unknown role."""
    if (not isinstance(grant, dict) or "role" not in grant or grant.get("by") != "triage"
            or not isinstance(grant.get("words"), str) or not grant["words"].strip()):
        raise ValueError("grant shape")
    if datetime.fromisoformat(grant["at"]).tzinfo is None:
        raise ValueError("grant time has no offset")
    role = grant["role"]
    if role is not None and (not isinstance(role, str) or opus_role(role) != role):
        raise ValueError("unknown role")
    return role


def _grant_family(grant):
    """The model a well-formed grant lifts: the one model its `words` name, Opus when they name none (a grant written
    before the owner's words named a model), else None for words that name two or more, which lift nothing."""
    named = _names_models(grant["words"])
    return "opus" if not named else next(iter(named)) if len(named) == 1 else None


def _take_step(session_id, spawn_role, cwd, family="opus"):
    """STEP_LIFTED when the one step bound to this lane grants a spawn of spawn_role on the model `family`, STEP_UNREAD
    when a record that names the lane cannot be read or has the wrong shape, else None. A grant lifts the model its words
    name (_grant_family), Opus or Fable alike. Sets _step_read to the step the decision names."""
    global _step_read
    _step_read = None
    lane = _lane_id(session_id)
    if lane is None or not isinstance(cwd, str) or not cwd:
        return None
    import git_reads  # lazy: only a spawn refusal that no held model lifted needs it
    hits = git_reads._git(cwd, "grep", "-l", "-F", "-e", lane, STEP_REF, "--", STEP_DIR)
    if hits is None or hits.returncode != 0:
        return None  # no ref, no repository, no hit or a git error: no lift
    bound = []
    for name in hits.stdout.splitlines():
        if not name.strip():
            continue
        _step_read = name.rsplit("/", 1)[-1]
        shown = git_reads._git(cwd, "show", name)
        try:
            if shown is None or shown.returncode != 0:
                raise ValueError("unread")
            step = json.loads(shown.stdout)
            if not isinstance(step, dict):
                raise ValueError("not a record")
            if step.get("lane") != lane:
                continue  # the id appears in another field or as part of a longer id
            grants = step.get("grants", [])
            if not isinstance(grants, list) or not isinstance(step.get("status"), str):
                raise ValueError("record shape")
            roles = [(_grant_role(grant), _grant_family(grant)) for grant in grants]
        except (ValueError, KeyError, TypeError, AttributeError):
            return STEP_UNREAD
        bound.append((str(step.get("id") or _step_read), step["status"], roles))
    _step_read = None
    if len(bound) != 1:
        return None  # no step or two steps bind the lane: no lift
    step_id, status, roles = bound[0]
    role = str(spawn_role).lower()
    if status == "done" or not any((r is None or r == role) and held == family for r, held in roles):
        return None
    _step_read = step_id
    return STEP_LIFTED


def step_read():
    """The step the last take() named for a step decision, or None."""
    return _step_read


def take(session_id, agent_id, at, rule=None, spawn_role=None, cwd=None, transcript=None, model=None):
    """LIFTED when the override lifts this refusal (a one-act override is spent), UNREAD when its file
    exists but cannot be read, else None. Of calls racing for one one-act override, only the one that
    creates its claim marker wins. For the Opus ceiling refusal (rule OPUS_RULE with a spawn_role: a spawn on Opus or
    on Fable) the pass file is read first, on the spawn's own model (_take_opus), then the step grant (STEP_LIFTED or
    STEP_UNREAD) on the spawn's own model (_take_step), so a lift either one covers spends no one-act override. `cwd` is the call's directory, where the step grant is read.
    For the model floor and the role row (HOLD_ONLY_RULES) it reads the pass file for a spawn on `model`, but those
    refusals pass no spawn model, so the file never matches and a held model lifts neither (the floor reads the owner's
    word, `owner_names_model`; the row reads the hold, `role_hold_verdict`, both in the guard). `transcript` is the
    session's, where a hold that ends at the report is read."""
    opus = _take_opus(session_id, spawn_role, at, transcript, model) if rule == OPUS_RULE and spawn_role is not None else None
    if rule in HOLD_ONLY_RULES:
        opus = _take_opus(session_id, spawn_role, at, transcript, model or "")
    if opus == OPUS_LIFTED:
        return opus
    step = None
    family = _family(model or "opus")
    if rule == OPUS_RULE and spawn_role is not None and family in ABOVE_SONNET:  # a step grant lifts the model its words name
        try:  # an error in the step read is no lift, and it never stops the override read below
            step = _take_step(session_id, spawn_role, cwd, family)
        except Exception:
            step = None
        if step == STEP_LIFTED:
            return step
    return _take_override(session_id, agent_id, at) or opus or step


def _read_override(path):
    """(kind, until, raw) of a once or timed override file, None when it is absent, UNREAD when it cannot be read."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        data = json.loads(raw.decode("utf-8"))
        kind = data["kind"]
        until = datetime.fromisoformat(data["until"])
        if kind not in ("once", "timed") or until.tzinfo is None:
            return UNREAD
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return UNREAD
    return kind, until, raw


def timed_live(session_id, at):
    """True when the session holds a timed override that is live at `at`. It only reads: a one-act override is never
    spent, and an unreadable file is no grant."""
    path = _path(session_id)
    read = _read_override(path) if path else None
    return isinstance(read, tuple) and read[0] == "timed" and at < read[1]


def _take_override(session_id, agent_id, at):
    path = _path(session_id)
    if path is None:
        return None
    read = _read_override(path)
    if not isinstance(read, tuple):
        return read
    kind, until, raw = read
    if at >= until or (kind == "once" and agent_id):
        return None
    if kind == "timed":
        return LIFTED
    if not _claim(path, raw):
        return None
    return LIFTED
