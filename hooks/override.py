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
  nothing on this route (an intended "off" must never become a grant). On this keyword route, a later line starting
  with the word grants nothing. The plain ask below reads a later line with the whole word like any prompt, so
  `thanks` then `override 15m` on the next line grants 15m on a judge yes.
  A plain ask (`yes override that`, `override that for 15 minutes please`) writes the same file when a model judges the
  prompt to be the owner's own present request to override a refusal (grant_override_ask, call_judge.override_ask). Cost:
  one model call, only for an owner prompt that holds the whole word `override` outside backtick code spans and
  passes the gates below; none for any other prompt. The call fails closed. The rules:
    - The gates are the Opus ask's, one helper (_owner_ask): payload `source`, a notice start, pasted and notice blocks
      cut, a fired-task block, a promptSource `system` record, a cloud session's seed prompt.
    - No judge call and no new grant for: no whole word `override` outside code spans (a pasted refusal line from
      offer() holds it only inside them), a NEGATIONS word or `off` within NEGATION_SPAN words of it, a `?`, two
      lengths, a decimal or compound length, or the whole word `opus` (the Opus route owns it).
    - One length sets the time: `15m`, `15 minutes`, or a bare number right after a first word `override` (minutes).
      None: a one-act override. A judge yes for a first-word `override` with a reason and no length stays main's
      one-act override.
    - grant() defers (returns None) only for a first word `override` whose rest is no whole keyword form and holds a
      length. grant_override_ask then answers every outcome but a judge yes with grant()'s own result (a reason form:
      a one-act override, with the reason logged; `override 15m please`: nothing). A judge no or error never widens a
      one-act override to a timed one.
An Opus override is the file <config dir>/state/override/opus/<session_id>.json, {"kind": "opus",
"until": ISO-8601 UTC, "role": null, one role, or a sorted list of 2 or more roles}. It lives beside the override, so the two never
replace each other. It lifts only the Opus spawn refusal of guard rule agent-model-cap, never that
rule's settings-write ask, and it reaches agents.
  `opus 2h`, `opus 15m`: every Opus spawn until the end. The unit is required: `opus 4` may name a
         model. `opus builders 2h` (or `builder`): only spawns of that role, from OPUS_ROLES.
  `opus off` ends it. The same whole-prompt rule holds: any other text after `opus` grants nothing.
  A plain ask (`send opus judges`, `use opus reviewers for 30m`) writes the same file when a model judges the
  prompt to be the owner's own present request (grant_opus_ask, call_judge.opus_ask). Cost: one model call for an
  owner prompt that carries the whole word `opus` and takes the plain path, plus one scope call (call_judge.opus_scope)
  only when that call says yes, the ask names no role and the transcript tail holds an earlier owner prompt; none
  for any other prompt. The yes/no call fails closed: an error or an odd answer grants nothing. The plain path's rules:
    - Strip every MACHINE_TAGS or NOTICE_FRAMES block anywhere, and a pasted block, first. An unclosed block, and a
      `[SYSTEM NOTIFICATION` line, run to the end.
    - In a cloud session (env CLAUDE_CODE_REMOTE_SESSION_ID set), a prompt with no earlier owner turn in the
      transcript is a seed prompt: no judge call.
    - A first word `opus` keeps the keyword path only when the rest starts with `off`, a length, or a role then a
      length. Any other first `opus` is a plain ask.
    - `claude` is never a role word here. The keyword form `opus claude 2h` keeps it.
    - The roles the ask names are granted, two or more as a list, only when a plain list joins them (PLAIN_LIST:
      commas, and, or, &, plus); any other words between two roles: no grant. A role word with a NEGATIONS word (not,
      no, don't, never, except, without, or an exclusion word such as skip or instead) within three words before or
      after it: no grant (`builders, no problem` grants nothing too).
    - An ask that names no role takes its roles from the owner's earlier typed prompts (decision owner-override:
      scope from context, fall back to every role), before the ask only. _context_prompts reads them from
      the one tail read (_tail_prompts), through the one owner-turn test (_owner_text), each through _strip_blocks,
      less a cloud session's seed brief (_seed_record, the seed check's one home),
      and scope_judge says which roles they name. Context only narrows the grant: the yes/no call sees the ask alone,
      and it never turns a no into a grant. No earlier prompt, or a scope read that fails, errs or names no role in
      ASK_ROLES: every role for the length, and it never asks. The every-role file is written before the scope read
      and narrowed after it, so a process killed in the read (the hook's timeout) leaves every role, with no
      `opus-grant` line.
    - Two or more lengths, a decimal (`1.5h`) or a compound (`1h30m`): no grant. One length sets the time: `<n>m`, `<n>h`, or spelled: hour(s), hr(s),
      min(s), minute(s). None: DEFAULT_ASK_LENGTH.
A step grant also lifts that ask, and nothing else: the owner's grant that triage writes on the lane's
roadmap step (decision agent-model-cap). take() reads it only on an Opus spawn refusal that no Opus override
lifted, from the local ref origin/roadmap in the call's cwd, never fetched: one git grep for the lane id,
one git show per hit. The lane id is session_<x> for env CLAUDE_CODE_REMOTE_SESSION_ID=cse_<x>, else the
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

try:  # stdlib only: the one home of the machine-text tags and the config dir
    from shared_names import MACHINE_TAGS, NOTICE_FRAMES, config_dir
    NOTICE_TAGS = MACHINE_TAGS + NOTICE_FRAMES
except ImportError:  # a missing or stale helper: the keyword grants still run, the plain ask grants nothing
    NOTICE_TAGS = ()

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
OPUS_PROMPT = re.compile(r"\s*opus(?=\s|$)(.*)", re.I | re.S)  # the Opus word, then the rest
OPUS_LENGTH = re.compile(r"(\d+)([mh])", re.I)  # an Opus override needs its unit
# The plain ask (grant_opus_ask): the whole word, the blocks that are not the owner's words, a word that may name a
# role, and a length (bounded by non-word characters, so `12 mhz` is none).
OPUS_WORD = re.compile(r"\bopus\b", re.I)
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
KEYWORD_REST = re.compile(r"\s*off(?![\w-])", re.I)
DEFAULT_ASK_LENGTH = ("2", "h")
SCOPE_CONTEXT_PROMPTS, SCOPE_CONTEXT_CHARS = 10, 2000  # the newest earlier prompts the scope read sees, and the cut of each
OPUS_RULE = "agent-model-cap"  # the one rule an Opus override lifts, and only its spawn refusal
# The roles an Opus spawn can ask for: the agents/ roles and the built-in ones, less Plan, which runs Opus by standing
# grant (OPUS_STANDING_ROLES in hooks/guard.py). Explore is not in it either: an Explore on Opus with no Audit: marker is
# refused, and `opus 2h` or `override` lifts it. No scoped `opus explore` form exists (decision agent-model-cap).
OPUS_ROLES = ("builder", "reviewer", "test-author", "record-writer", "claude-code-guide",
              "general-purpose", "claude", "design-reviewer")
# The roles a plain ask or its scope read can name: OPUS_ROLES less `claude`, which in prose addresses the assistant.
ASK_ROLES = tuple(role for role in OPUS_ROLES if role != "claude")
LOG_REASON_MAX = 300
SESSION_ID = re.compile(r"[\w.-]{1,128}")  # the id names a file: no separator, no leading dot
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


def offer(rule, spawn_role=None, agent_id=None):
    """The line an owner types to lift a refusal of this rule, for the call that was refused."""
    if rule == OPUS_RULE and spawn_role is not None:
        role = opus_role(str(spawn_role))
        by_role = " or `opus %ss 2h` for this role" % role if role else ""
        return "To allow this Opus spawn, type `opus 2h` for every Opus spawn%s, or `override` for this one act." % by_role
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


def _grant_opus(session_id, rest, at):
    """`opus <n>[m|h]`, `opus <role> <n>[m|h]` or `opus off` as the whole prompt. Returns ("opus",
    until, role) for a new override, ("opus-off", None) when one was removed, else None."""
    path = _path(session_id, "opus")
    words = rest.split()
    if path is None or not words or (rest[:1] and not rest[:1].isspace()):
        return None
    if [w.lower() for w in words] == ["off"]:
        try:
            os.remove(path)
        except FileNotFoundError:
            return None
        _log(session_id, "opus-off", "")
        return "opus-off", None
    role = opus_role(words[0]) if len(words) == 2 else None
    length = OPUS_LENGTH.fullmatch(words[-1])
    if not length or len(words) > 2 or (len(words) == 2 and role is None):
        return None  # ambiguous: grants nothing
    return _write_opus(session_id, path, at, length.groups(), role)


def _write_opus(session_id, path, at, length, role, said=None, log=True):
    """Write the Opus override file for `length` = (number, unit) from `at` and log it: the one home of the file's
    shape, for the keyword grant and the plain ask. `role` is None, one role, or a sorted list of 2 or more roles.
    `said` is the owner's words, for the log; `log` False writes the file and no log line. Returns ("opus", until,
    role)."""
    number, unit = length
    until = _length_end(at, number, unit)
    stamp = until.astimezone(timezone.utc).isoformat()
    _write(path, {"kind": "opus", "until": stamp, "role": role})
    if not log:
        return "opus", until, role
    detail = "%s until %s" % (", ".join(role) if isinstance(role, list) else role or "every role", stamp)
    if said:
        detail += ": " + said[:LOG_REASON_MAX].encode("utf-8", "replace").decode("utf-8")
    _log(session_id, "opus-grant", detail)
    return "opus", until, role


def _strip_blocks(prompt):
    """The prompt with each pasted or machine-tag block replaced by a marker: that text is not the owner's words."""
    return BLOCKS.sub("[pasted text]", prompt)


def _keyword_rest(rest):
    """True when the text after a first word `opus` is a keyword form: `off`, a length, or a role then a length."""
    words = rest.split()
    if KEYWORD_REST.match(rest) or (words and OPUS_LENGTH.match(words[0])):
        return True
    return len(words) > 1 and opus_role(words[0]) is not None and OPUS_LENGTH.match(words[1]) is not None


def _ask_lengths(text, bare=None):
    """The lengths in a plain ask `text` as (number, unit letter) pairs, plus `bare` (a pair) when given, or None when
    they are unclear: two or more, a decimal or a compound length. The one length check of both plain asks."""
    found = [(m.group(1), (m.group(2) or m.group(3))[0]) for m in ASK_LENGTH.finditer(text)]
    if bare:
        found.append(bare)
    if len(found) > 1 or UNCLEAR_LENGTH.search(text):
        return None
    return found


def _near_negation(names, at, negations):
    """True when a word of `negations` stands within NEGATION_SPAN words before or after the word at names[at]. The one
    negation check of both plain asks."""
    near = names[max(0, at - NEGATION_SPAN):at] + names[at + 1:at + 1 + NEGATION_SPAN]
    return bool(negations & {w.lower() for w in near})


def _ask_scope(text):
    """(length, roles) a plain ask names, or None when the words are unclear: two lengths, a decimal or compound
    length, a role with a negation within NEGATION_SPAN words before or after it, or two role words joined by
    anything but a plain list (PLAIN_LIST). `roles` is the sorted list of the roles it names, empty when it names
    none."""
    lengths = _ask_lengths(text)
    if lengths is None:
        return None
    matches = list(ROLE_WORDS.finditer(text))
    words = [m.group() for m in matches]
    roles, last_end = set(), None
    for at, word in enumerate(words):
        role = opus_role(word)
        if role not in ASK_ROLES:
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
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lint")
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


def _owner_text(rec):
    """The words of a record that is an owner's typed turn, else None: the one test for the seed check and the scope
    context. Not an isMeta record, a promptSource "system" record, a record whose origin kind is not human, a command
    record (`/effort`) or a fired scheduled task's block."""
    if not isinstance(rec, dict) or rec.get("isMeta") or rec.get("promptSource") == "system":
        return None
    origin = rec.get("origin")
    if isinstance(origin, dict) and origin.get("kind", "human") != "human":
        return None
    text = _text_of(rec)
    if text is None or text.lstrip().startswith(COMMAND_RECORDS) or FIRED_TASK.search(text):
        return None
    return text


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
                if at != own and _owner_text(rec) is not None:
                    return at
    except OSError:
        pass
    return None


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


def _owner_ask(prompt, source, transcript, wanted):
    """The gates of the plain asks (grant_opus_ask, grant_override_ask), the one home. Returns (text, found, seed) for a
    prompt that may go to a judge, else None. `text` is the prompt less its pasted and notice blocks. `found` is the
    tail read (_tail_prompts). `seed` is a cloud session's seed record offset, else None. `wanted(text)` is the route's
    own test of the words, run before the transcript is read. None for: a non-string, a `source` outside
    OPUS_ASK_SOURCES, a missing NOTICE_TAGS, a prompt that starts with a notice, a fired-task block, words the route
    does not want, a prompt whose own record is last in the transcript with promptSource "system", and in a cloud
    session (env LANE_ENV set) a prompt with no earlier owner turn (the seed prompt)."""
    if not isinstance(prompt, str) or source not in OPUS_ASK_SOURCES:
        return None
    if not NOTICE_TAGS or prompt.lstrip().startswith(NOTICE_TAGS) or FIRED_TASK.search(prompt):
        return None  # a stored task, a notice or no tag list: not typed words
    text = _strip_blocks(prompt)
    if not wanted(text):
        return None
    found = _tail_prompts(transcript)
    if _system_prompt_last(found, prompt):
        return None
    seed = _seed_record(transcript, found, prompt) if os.environ.get(LANE_ENV) else None
    if os.environ.get(LANE_ENV) and seed is None:
        return None
    return text, found, seed


def grant_opus_ask(session_id, prompt, at, judge=None, transcript=None, source=None, scope_judge=None):
    """The owner's plain Opus ask (`send opus judges`): an Opus override written when the model says the prompt is the
    owner's own present request to run Opus agents (decision owner-override). `judge` is call_judge.opus_ask and
    `scope_judge` is call_judge.opus_scope unless a caller passes another. Returns ("opus", until, role) for a new
    override, else None. The module docstring holds the rules of the words and of the scope. `source`, the payload's
    field, must be in OPUS_ASK_SOURCES; any other value, an unknown one too, grants nothing.
    Cost: one tail read (_tail_prompts) when the prompt carries the whole word `opus`; the judge sees the stripped
    ask alone. The judge is not called for a non-string, a fired-task block in the prompt, an id that cannot name a
    file, a machine-tag start, a keyword form, text with no whole word `opus` left after _strip_blocks, or a cloud
    session's seed prompt (no owner turn in the transcript at path `transcript`), or a prompt whose own record, last in
    the transcript, has promptSource "system". The scope read is called once, only after a yes, for an ask that names
    no role and has an earlier owner prompt in the tail. The every-role file is written before that call and a valid
    answer rewrites it narrowed (same end), so a kill during the call (the prompt hook's timeout) leaves every role
    with no `opus-grant` line.
    The one `opus-grant` line logs the final scope; an interrupt or exit in the call logs the every-role line. The guard.log line `opus-grant` holds the words that were
    judged."""
    path = _path(session_id, "opus")
    if path is None or not isinstance(prompt, str):
        return None
    first = OPUS_PROMPT.match(prompt)
    if PROMPT.match(prompt) or (first and _keyword_rest(first.group(1))):
        return None
    gated = _owner_ask(prompt, source, transcript, lambda text: OPUS_WORD.search(text) is not None)
    if gated is None:
        return None
    text, found, seed = gated
    if judge is None:
        from call_judge import opus_ask as judge
    if judge(text) is not True:
        return None
    scope = _ask_scope(text)
    if scope is None:
        return None
    length, roles = scope
    said = " ".join(text.split())
    context = [] if roles else _context_prompts(found, prompt, seed)
    if context:
        # No scope means every role, so that file goes down first: the prompt hook's timeout can kill the process in the
        # scope read, and a kill must leave the every-role file. A valid answer then narrows it.
        _write_opus(session_id, path, at, length, None, said, log=False)
        if scope_judge is None:
            from call_judge import opus_scope as scope_judge
        try:
            roles = _scoped_roles(scope_judge, text, context)
        except BaseException:  # an interrupt or an exit during the read: log the every-role grant that stands
            _write_opus(session_id, path, at, length, None, said)
            raise
    return _write_opus(session_id, path, at, length, _file_role(roles), said)


def grant(session_id, prompt, at, defer=True):
    """Write, replace or remove the session's override for one owner prompt. Returns (kind, until) for a
    new override, ("off", None) when `override off` removed one, the _grant_opus result for the Opus word,
    else None: the prompt is not a word. With `defer`, a first word `override` whose rest is no whole keyword form and
    holds a length returns None too, so the plain ask (grant_override_ask) judges it; grant_override_ask calls again
    with `defer` False for main's result."""
    opus = OPUS_PROMPT.match(prompt) if isinstance(prompt, str) else None
    if opus:
        return _grant_opus(session_id, opus.group(1), at)
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
        return grant(session_id, prompt, at, defer=False) if keyword else None

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


def _take_opus(session_id, spawn_role, at):
    """OPUS_LIFTED when the session's Opus override covers a spawn of spawn_role now, OPUS_UNREAD when the
    file exists but cannot be read, else None."""
    path = _path(session_id, "opus")
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
        until, role = datetime.fromisoformat(data["until"]), data["role"]
        roles = role if isinstance(role, list) else [role]  # null, one role, or a list of roles
        if (data["kind"] != "opus" or until.tzinfo is None or (isinstance(role, list) and not role)
                or any(r is not None and (not isinstance(r, str) or opus_role(r) != r) for r in roles)):
            return OPUS_UNREAD
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return OPUS_UNREAD
    if isinstance(role, list) and str(spawn_role).lower() in role:
        role = str(spawn_role).lower()  # a list that names the spawn's role covers it as that one role
    if at >= until or (role is not None and role != str(spawn_role).lower()):
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


def _take_step(session_id, spawn_role, cwd):
    """STEP_LIFTED when the one step bound to this lane grants an Opus spawn of spawn_role, STEP_UNREAD
    when a record that names the lane cannot be read or has the wrong shape, else None. Sets _step_read
    to the step the decision names."""
    global _step_read
    _step_read = None
    lane = _lane_id(session_id)
    if lane is None or not isinstance(cwd, str) or not cwd:
        return None
    import git_reads  # lazy: only an Opus spawn refusal that no Opus override lifted needs it
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
            roles = [_grant_role(grant) for grant in grants]
        except (ValueError, KeyError, TypeError, AttributeError):
            return STEP_UNREAD
        bound.append((str(step.get("id") or _step_read), step["status"], roles))
    _step_read = None
    if len(bound) != 1:
        return None  # no step or two steps bind the lane: no lift
    step_id, status, roles = bound[0]
    role = str(spawn_role).lower()
    if status == "done" or not any(r is None or r == role for r in roles):
        return None
    _step_read = step_id
    return STEP_LIFTED


def step_read():
    """The step the last take() named for a step decision, or None."""
    return _step_read


def take(session_id, agent_id, at, rule=None, spawn_role=None, cwd=None):
    """LIFTED when the override lifts this refusal (a one-act override is spent), UNREAD when its file
    exists but cannot be read, else None. Of calls racing for one one-act override, only the one that
    creates its claim marker wins. For the Opus spawn refusal (rule OPUS_RULE with a spawn_role) the Opus
    override is read first, then the step grant (STEP_LIFTED or STEP_UNREAD), so a lift either one covers
    spends no one-act override. `cwd` is the call's directory, where the step grant is read."""
    opus = _take_opus(session_id, spawn_role, at) if rule == OPUS_RULE and spawn_role is not None else None
    if opus == OPUS_LIFTED:
        return opus
    step = None
    if rule == OPUS_RULE and spawn_role is not None:
        try:  # an error in the step read is no lift, and it never stops the override read below
            step = _take_step(session_id, spawn_role, cwd)
        except Exception:
            step = None
        if step == STEP_LIFTED:
            return step
    return _take_override(session_id, agent_id, at) or opus or step


def _take_override(session_id, agent_id, at):
    path = _path(session_id)
    if path is None:
        return None
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
    if at >= until or (kind == "once" and agent_id):
        return None
    if kind == "timed":
        return LIFTED
    if not _claim(path, raw):
        return None
    return LIFTED
