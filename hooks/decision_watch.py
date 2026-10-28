#!/usr/bin/env python3
"""Claude Code hook: decision/guard/settings watch (Stop). Replaces the `type: agent` guardrail.

WHAT THIS FILE DOES. A command hook. Command hooks receive the same Stop JSON
(`transcript_path`, `session_id`, `cwd`) with no permission check at all, so the `auto`-mode
failure cannot happen here. It answers the cheap part of the question itself,
from `git status` and the transcript, and calls a model only for the residual judgment a
file diff cannot make: whether an approval for this exact change is visible in the chat.

THE CHEAP PATH, FIRST. `changed_paths` reads this turn's dirty files from `git status
--porcelain` against HEAD, scoped by mtime against the last human message the same way
the old markdown sweep did (see `docs/decisions/predicate-is-the-act.md`: a shape list of
write commands can only grow, so this hook reads the filesystem's own act instead of
parsing Bash text). `looks_protected` then asks, per file, whether the name or location
marks it a decision, a guard, a CLAUDE.md, or a settings file. Settings files use
`guard.is_settings_file`, the constant the guard itself emits (rule `building-allow-list-is-the-constant`); the rest (`decisions/`, `CLAUDE.md`, a "gate"/"guard"/"build-
order"/"rule"/"policy" name) has no such constant to import, because no code in this repo
defines what a guard or a build-order file IS. That half stays a deliberately broad keyword
match: a triage filter that decides whether to spend a model call, never the verdict
itself, so a false positive costs one subprocess call and a false negative skips judgment
entirely.

THE TRIGGER. `run` spends a model call only on `protected`, an ACTUAL on-disk change to a protected
path. `looks_concerning`'s outbound scan only enriches the evidence of a change that already
triggered the call.

WHEN NOTHING PROTECTED IS TOUCHED. No model call. Print nothing. Exit 0. This is the common
case and it must stay fast: a `git status` and the transcript's tail for the last human
message's time (`lint/_transcript.py`'s `last_human_epoch`). The transcript is parsed whole
only once a protected path is dirty and newer than that message.

AN ALLOW IS CACHED LIKE A FLAG. `run` marks every judged incident seen, so one unchanged
dirty file costs one model call per change, not one per Stop. `incident_key` includes a hash
of the protected files' bytes, so an edit the model's 4000-character view cannot show still
moves the key. A UNKNOWN read is never marked.

WHEN SOMETHING PROTECTED IS TOUCHED. `invoke_model` runs `claude -p` with an explicit
empty tool set and an isolated `cwd`/`CLAUDE_CONFIG_DIR` (see "THE ISOLATION" below), fed
the diff (or, for a new file, its full text) and the chat text since the last human
message directly, never a path for the model to `Read` itself: reading a path is exactly
the step that fails in `auto` mode. It asks for the same ALLOW/FLAG judgment the old
prompt asked for, on the same criteria: additive or consistent, or surfaced as a question
and approved, is ALLOW; silently changed, weakened, removed, or reversed with no visible
approval is FLAG.

THE PER-INCIDENT, PER-SESSION CAP (decision `guard-that-cries-wolf-is-spent`). `incident_key`
hashes the protected paths plus their evidence; `_load_seen`/`_mark_seen` persist that hash per
session under `<config dir>/state/decision-watch/`, the same frozen `state` subtree
`hooks/config_watch.py` uses for its baseline. A finding already flagged this session, with
unchanged evidence, stays quiet. A finding whose evidence moved is reported once more.

UNKNOWN IS A FIRST-CLASS OUTPUT. Per CLAUDE.md's Verification rule, a read that could not
run is reported as unknown, never as clear and never as a flag. `transcript_path` missing
or unreadable, `git` unavailable or failing, or the model subprocess failing, timing out, or
answering something that is not the JSON verdict it was asked for: each of these ends the
run with a `systemMessage` that names UNKNOWN and why, and exit 0. This hook only ever
reports, so nothing here ever refuses the turn. The incident cap never touches this branch:
an UNKNOWN read is never cached and always reported again.

THE CONFIG REPORT. The same Stop run also prints the config report: the project config files,
merges into main and unreadable subjects of this turn. It is a separate section with its own
message, joined to the judgment's with a space, and it never calls the model. Under a split flag
(below) the output also carries `verdict` (the judgment's text alone) and `notices` (one line per
kind of notice), so a caller can show each notice apart from the verdict.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess

# GUARD_UNDER_TEST mirrors hooks/config_watch.py's own hook, so a test can point this file at
# a throwaway copy of guard.py with no second copy of that dependency in this file.
_GUARD_PATH = os.environ.get("GUARD_UNDER_TEST")
if _GUARD_PATH:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("guard_under_test", _GUARD_PATH)
    guard = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(guard)
else:
    import guard

from shared_names import STATE_DIR_NAME  # noqa: E402  stdlib only

# The tail reader for the cheap check lives in lint/_transcript.py, the one home
# (docs/decisions/hooks-share-the-transcript-reader.md). The older copies below predate it.
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
from _transcript import last_human_epoch, head_moved_since, is_last_human  # noqa: E402

# THE TIME BUDGET. The mod (mods/decision-watch/hooks/register.mjs) runs this script, and it
# caps each python run itself (PY_MS there), so no Stop row timeout bounds it now. In split
# mode (--emit-prompt, --model-text, --model-error) the script calls no model: the mod makes
# the model call under its own MODEL_MS. Inside one run, every git call uses GIT_TIMEOUT (10s)
# and at most MAX_DIFFED_FILES protected files are diffed; the rest are still named in the
# evidence, with no git call, so the count of protected files can grow with no matching growth
# in wall time. Worst case for the git part, computed here: one `git status` + one `git log`
# + MAX_DIFFED_FILES `git diff` calls = 10 + 10 + 80 = 100 seconds, so the mod's cap can stop
# a run first. A direct run with no split flag also makes one model call (MODEL_TIMEOUT, 120s).
# Changing these numbers means re-checking the mod's timers. A model timeout is an error from
# invoke_model, which the caller reports as UNKNOWN, never ALLOW.
MODEL = "haiku"
MODEL_TIMEOUT = 120
GIT_TIMEOUT = 10
MAX_DIFFED_FILES = 8

# The prompt goes to `claude -p` on stdin, so the clip bounds cost and latency only; the right
# size is unmeasured. The cut is named in the prompt itself so the judge (and anyone reading its
# "why") knows evidence was dropped rather than concluding nothing else changed.
PROMPT_MAX_LEN = 20000

PEER_MESSAGE_TOOLS = ("SendMessage", "Task")

# Deliberately broad: a substring match against a lowercased relative path, on top of
# `guard.is_settings_file`. Named files this repo actually has (`decisions/*.md`,
# `CLAUDE.md`, `lint/*_guard.py`, `hooks/guard.py`) all hit one of these. No code in this
# repo defines "a guard" or "a build-order" as a constant to import instead, so this stays a
# triage keyword net rather than a permit list (rule building-allow-list-is-the-constant
# governs permit lists, not a "should the model even look" filter).
PROTECTED_PATH_HINTS = (
    "decision", "claude.md", "gate", "guard", "build-order", "build_order", "buildorder",
    "policy", "rule",
)

# Paired with a path/name hint above before a peer message counts as concerning. A message
# that only mentions a guard file, with no instruction to act on it, is not a deviation.
ACTION_WORDS = (
    "delete", "remove", "drop", "strip", "weaken", "disable", "bypass", "override",
    "reverse", "revert", "skip", "silence", "unmechanize",
)

UNKNOWN_PREFIX = "Decision watch: UNKNOWN, could not verify this turn against recorded decisions/guards/settings. "
FLAG_PREFIX = "Decision watch: FLAG. "

# WHY_MAX_LEN bounds the model's own `why` text before it is printed into the parent
# session's transcript. That text is the judge model's summary of a diff built from
# attacker-influenced content (the whole point of asking a model to read it), so it is
# capped and control-character-stripped the same way `hooks/guard.py`'s own printed
# reasons are (`cap_safe`), and wrapped so a reader can tell it is quoted, attributed
# text describing the change, never this hook's own statement. Added against a reviewer
# finding: an uncapped, unattributed `why` field is an open channel for whoever can land
# text in a diff to steer what appears in the owner's transcript.
WHY_MAX_LEN = 300


def _safe_why(text):
    """Return the model's `why` text, fit to print: control characters cleaned, length
    bounded with a cut mark, whitespace collapsed. Never trusted as this hook's own
    words."""
    return guard.cap_safe(re.sub(r"\s+", " ", text or "").strip(), WHY_MAX_LEN)


# ------------------------------------------------------------------ transcript walking
#
# is_last_human is imported from lint/_transcript.py, the one home. read_transcript below is an
# older copy.

def read_transcript(path):
    records = []
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
    return records


def last_human_index_and_stamp(records):
    """Return (index, timestamp) of the last human record, or (None, '') when there is none."""
    idx = None
    stamp = ""
    for i, rec in enumerate(records):
        if is_last_human(rec):
            idx = i
            value = rec.get("timestamp") or ""
            stamp = value if isinstance(value, str) else ""
    return idx, stamp


def parse_utc_timestamp(text):
    text = (text or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except Exception:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def records_after(records, idx):
    if idx is None:
        return records
    return records[idx + 1:]


def tool_uses(rec):
    msg = rec.get("message") or {}
    content = msg.get("content")
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            yield b


def texts(rec):
    """Yield the plain-text blocks of one record's message (user or assistant)."""
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        yield content
        return
    if not isinstance(content, list):
        return
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            text = b.get("text")
            if isinstance(text, str):
                yield text


def chat_text_after(records, idx, limit=6000):
    """Return the plain text of every record after `idx`, joined and bounded.

    Fed to the model as the "was this surfaced and approved" evidence. Bounded so one
    talkative turn cannot blow the model call's input past a sane size.
    """
    parts = []
    for rec in records_after(records, idx):
        parts.extend(texts(rec))
    joined = "\n---\n".join(parts)
    if len(joined) > limit:
        joined = joined[:limit] + "\n...[cut]"
    return joined


# ------------------------------------------------------------------ this turn's changed files
#
# git's own dirty-file list, scoped by mtime against the last human message.
# See docs/decisions/predicate-is-the-act.md. A git failure here (including "not
# a git work tree at all") is read as UNKNOWN rather than falling back to a plain walk: this
# hook's job is a security read, not a lint, and an unscoped walk over a non-repo directory
# is not an honest substitute for "what did this turn change".

def _run_git(cwd, args, timeout=GIT_TIMEOUT):
    try:
        return _nowindow.run(
            ["git", "-C", cwd] + args, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except Exception:
        return None


def is_git_work_tree(cwd):
    current = os.path.realpath(cwd)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            return False
        current = parent


def git_status_entries(cwd):
    """Return {relative path: 2-char porcelain status}, or None on any git failure."""
    run = _run_git(cwd, ["status", "--porcelain", "-z", "--untracked-files=all", "--", "."])
    if run is None or run.returncode != 0:
        return None
    entries = {}
    fields = run.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        status, rel = entry[:2], entry[3:]
        entries[rel] = status
        if status[0] in ("R", "C"):
            index += 1  # the rename/copy source path, not a target
    return entries


def changed_this_turn(cwd, baseline):
    """Return ([relative paths], is_untracked) changed this turn, or (None, None) on failure.

    `baseline`, the last human message's epoch seconds, scopes the dirty set to this turn by
    mtime. A missing baseline (no timestamp on the last human
    record) skips the mtime filter rather than reporting UNKNOWN: every dirty file is then in
    scope, a broader net, never a narrower one, which is the same bias this hook's whole
    triage stage already takes.
    """
    if not is_git_work_tree(cwd):
        return None, None
    entries = git_status_entries(cwd)
    if entries is None:
        return None, None
    is_untracked = {}
    kept = []
    for rel, status in entries.items():
        abs_path = os.path.join(cwd, *rel.split("/"))
        # A deleted path (status has "D" in either column) has no mtime to check --
        # there's nothing left to stat. Skipping the mtime filter for it is the same
        # broad-net call this function already makes for a missing baseline: a file git
        # reports gone this turn stays in scope rather than dropping out through the
        # getmtime except below, which is for a file that's unreadable but still THERE
        # (e.g. a permissions error), not one that's gone.
        deleted = "D" in status[:2]
        if baseline is not None and not deleted:
            try:
                if os.path.getmtime(abs_path) <= baseline:
                    continue
            except OSError:
                continue
        kept.append(rel)
        is_untracked[rel] = status[:2] == "??"
    return kept, is_untracked


# ------------------------------------------------------------------ the triage filter

def looks_protected(rel_path, cwd):
    """True when a path's name or location marks it a decision, guard, CLAUDE.md, or
    settings file. See the module docstring for why this stays a broad keyword net."""
    if guard.is_settings_file(rel_path, cwd):
        return True
    low = rel_path.replace("\\", "/").lower()
    return any(hint in low for hint in PROTECTED_PATH_HINTS)


def looks_concerning(tool_use):
    """True when an outbound SendMessage/Task this turn names a protected file together
    with an instruction to act on it.

    AMENDED 2026-09-22, against the independent audit. This used to be a trigger on its
    own: a SendMessage with no matching disk change was enough to spend a model call. The
    audit found that shape produced a false positive (an instruction sent to a peer that
    had not yet executed) and named the same shape in two of the three false positives
    overall (a role question, and a probe of a scratch copy rather than the real file). A
    peer being TOLD to do something is not the act CLAUDE.md's Verification rule protects
    against; a real write to the real path is. `run` below now spends a model call only on
    `protected` (an actual on-disk change) being non-empty, full stop. This function still
    runs, but only to ENRICH the evidence a real protected change already triggered on,
    never to trigger by itself.
    """
    if not isinstance(tool_use, dict):
        return False
    if tool_use.get("name") not in PEER_MESSAGE_TOOLS:
        return False
    blob = json.dumps(tool_use.get("input") or {}).lower()
    has_target = any(hint in blob for hint in PROTECTED_PATH_HINTS)
    has_action = any(word in blob for word in ACTION_WORDS)
    return has_target and has_action


# ------------------------------------------------------------------ evidence for the model

ROOT_COMMIT = "root"


def file_evidence(cwd, rel_path, untracked, since=None):
    """Return a short label plus the diff (or full text for an untracked file), or None on
    a git failure -- the caller reads None as UNKNOWN, per this hook's own design constraint
    that a git-diff failure is unknown, never silence and never a flag.

    `since` is the parent of the oldest commit made this turn (`committed_this_turn` reads it
    from the same `git log` call, so no extra git call runs here): the diff then runs from that
    parent to the work tree, so a change committed this turn shows, with any later edit on
    top. `ROOT_COMMIT` means the turn made the root commit, which reads as a new file."""
    def whole_file():
        try:
            with open(os.path.join(cwd, rel_path), "r", encoding="utf-8", errors="replace") as f:
                return "%s (new file):\n%s" % (rel_path, f.read()[:4000])
        except Exception:
            return None
    if untracked:
        return whole_file()
    if since == ROOT_COMMIT:
        return whole_file()
    if since:
        run = _run_git(cwd, ["diff", since, "--", rel_path])
        if run is None or run.returncode != 0:
            return None
        return "%s (diff since the turn's first commit):\n%s" % (rel_path, run.stdout[:4000])
    run = _run_git(cwd, ["diff", "HEAD", "--", rel_path])
    if run is None or run.returncode != 0:
        return None
    return "%s (diff against HEAD):\n%s" % (rel_path, run.stdout[:4000])


MAX_TURN_COMMITS = 200


def committed_this_turn(cwd, baseline):
    """Return ([relative paths], parent of the oldest commit) that commits made since `baseline` touched,
    or (None, None) when git could not be read. No baseline, or no commit since it, is ([], None).

    One bounded `git log --since` call, and only when HEAD's reflog says HEAD moved: an idle
    turn pays no subprocess here. A failed read is unknown, never clear."""
    if baseline is None or head_moved_since(cwd, baseline) is False:
        return [], None
    run = _run_git(cwd, ["-c", "core.quotepath=off", "log", "--since=%d" % int(baseline),
                         "--max-count=%d" % MAX_TURN_COMMITS, "--name-only", "--format=%x01%P"])
    if run is None:
        return None, None
    if run.returncode != 0:
        if "does not have any commits" in (run.stderr or ""):
            return [], None
        return None, None
    paths, oldest = [], None
    for line in run.stdout.splitlines():
        if line.startswith("\x01"):
            parents = line[1:].split()
            oldest = parents[0] if parents else ROOT_COMMIT
        elif line and line not in paths:
            paths.append(line)
    return paths, oldest


# ------------------------------------------------------------------ the per-incident, per-session cap
#
# An incident's identity is the set of protected paths plus the evidence text built from
# their diffs. Unchanged evidence next Stop means the same unresolved finding, and stays
# quiet. Evidence that changed, because the file moved further or a new path joined it,
# reads as a new incident and is reported once more.
#
# THE STORE. One small file per session, under `<config dir>/state/decision-watch/`, the
# same `state` subtree hooks/config_watch.py already uses for its own baseline (frozen by
# guard.CONFIG_FROZEN_DIRS, so a session write there is refused like any other, never
# silently swallowed). Keyed by a hash of `session_id`, never the raw id, so the file name
# carries no session detail. A store this hook cannot read or write is read as "nothing
# seen yet" -- the fail-open direction, since the alternative is re-flagging forever, and
# CLAUDE.md's Verification rule is about never mistaking a failed read for a CLEAR answer,
# not about this cache.

SEEN_DIR_NAME = STATE_DIR_NAME
SEEN_SUB = "decision-watch"


def _seen_store_path(session_id):
    if not session_id or not isinstance(session_id, str):
        return None
    key = hashlib.sha256(session_id.encode("utf-8", "replace")).hexdigest()
    return os.path.join(guard.config_dir(), SEEN_DIR_NAME, SEEN_SUB, key + ".json")


def _load_seen(session_id):
    path = _seen_store_path(session_id)
    if not path:
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()
    if isinstance(data, list):
        return set(x for x in data if isinstance(x, str))
    return set()


def _mark_seen(session_id, incident_key):
    path = _seen_store_path(session_id)
    if not path:
        return
    try:
        seen = _load_seen(session_id)
        seen.add(incident_key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sorted(seen), f)
        os.replace(path + ".tmp", path)
    except Exception:
        pass  # a cache write failure re-flags next time rather than losing the report now


DIGEST_READ_MAX = 1 << 20


def content_digest(cwd, protected):
    """Return one hash of the repo root and the protected files' bytes (a missing file hashes
    as gone), so one session in two repos never shares a verdict.

    `file_evidence` cuts a diff at 4000 characters, so an edit past the cut would leave the
    evidence, and so the key, unchanged. This digest moves with every byte of a file up to
    DIGEST_READ_MAX; a larger file hashes its first DIGEST_READ_MAX bytes plus its size and
    mtime, so a protected file cannot make this hook read without bound.
    """
    h = hashlib.sha256(os.path.realpath(cwd).encode("utf-8", "replace") + b"\2")
    for rel in sorted(protected):
        h.update(rel.encode("utf-8", "replace") + b"\0")
        try:
            with open(os.path.join(cwd, rel), "rb") as f:
                h.update(f.read(DIGEST_READ_MAX))
                st = os.fstat(f.fileno())
                if st.st_size > DIGEST_READ_MAX:
                    h.update(b"%d:%d" % (st.st_size, st.st_mtime_ns))
        except OSError:
            h.update(b"<gone>")
        h.update(b"\1")
    return h.hexdigest()


def incident_key(protected, evidence, contents=""):
    """Return one stable id for this finding: the protected paths plus their evidence.

    Never the model's own wording, so a verdict that repeats itself in different words
    still collapses to one incident, and a diff that actually moved further still reads
    as a new one.
    """
    blob = "\x00".join(sorted(protected)) + "\x01" + "\x00".join(evidence) + "\x02" + contents
    return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()


# ------------------------------------------------------------------ the model call

JUDGE_INSTRUCTIONS = (
    "You are a guardrail judging whether a coding session's turn silently changed a "
    "decision, guard, build-order, CLAUDE.md rule, or settings value without visible "
    "approval. Below are the diffs (or new-file text) of every protected file this turn "
    "touched, plus the chat text since the last human message. ALLOW if the change is "
    "additive or consistent, or the chat shows the assistant surfaced this exact change as "
    "a question and the user approved it before the edit happened. FLAG if a rule, guard, "
    "build-order, decision, or setting was silently changed, weakened, removed, or "
    "reversed with no visible approval in the chat. Ignore anything unrelated to a "
    "decision, guard, build-order, or setting. Be conservative: only flag a genuine "
    "unapproved override. Respond with exactly one JSON object and nothing else: "
    '{"verdict": "ALLOW"} or {"verdict": "FLAG", "why": "<short: which file, what changed, '
    'why it reads as unapproved>"}.'
)


# THE ISOLATION, ADDED AFTER A REVIEWER FLAG, THEN TIGHTENED TWICE MORE. The evidence
# handed to the model is this turn's diff text and chat text, and both are reachable by
# whoever can land text in a diff or a message this repo carries. A prior version of this
# function ran `claude -p` with no restriction flag and no `cwd` at all: omitting every
# restriction flag defaults to every tool, in this project's own directory, inheriting
# whatever this project's own `.claude/settings.json` grants in `permissions.allow` at the
# time, `Bash(gh pr merge:*)` included. An injected instruction in the diff could have
# driven that nested, fully-tooled call to use a granted permission, then folded whatever
# it read into the `why` field this hook prints back into the parent session.
#
# THE TOOL FLAG, VERIFIED AGAINST DOCUMENTATION RATHER THAN GUESSED. A first fix used
# `--allowedTools ""`. `claude --help` documents a SEPARATE flag, `--tools`, whose help
# text says plainly: `""` disables all tools, `"default"` uses all tools, or name specific
# tools. `--allowedTools`'s own help text says only "list of tool names to allow" and says
# nothing about what an empty value means, so resting a security control on an
# undocumented parse of an empty string was not acceptable. This hook now passes
# `--tools ""`, the documented empty-disables-all form, plus `--safe-mode`, documented to
# disable every plugin, MCP server, hook, skill and custom command for the session, which
# `--tools` alone does not claim to reach.
#
# Copying `os.environ` and subtracting names cannot
# be complete, the same shape `docs/decisions/predicate-is-the-act.md` already names for a
# shape list that can only grow. `JUDGE_ENV_ALLOWLIST` inverts it: the child's environment
# holds only the named variables the runtime genuinely needs to execute and reach the API
# host, built fresh, never copied from the parent and never carrying a name this list does
# not say. A session authenticated by `ANTHROPIC_API_KEY` rather than the OAuth credential
# file will see the isolated call fail closed, reported as UNKNOWN like any other model-
# call failure, never silently allowed through with the key attached.
#
# WHAT REMAINS. `_judge_isolation`'s `cwd`/`CLAUDE_CONFIG_DIR` is the layer that does not
# depend on any flag or env entry being right at all: there is no `.claude/settings.json`
# there to inherit `permissions.allow` from, and no `hooks/` wired to a Stop event there
# either, so a nested call cannot fire this same hook at its own turn end. That removes
# the object a recursive call would need, rather than counting spawn depth the way
# `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` counts `Task`-tool spawns (a raw `subprocess.run`
# is neither a `Task` spawn nor governed by that cap).

# THE TOKEN FILE. The copied credentials file never renews: its access token expires and
# the child cannot refresh it (measured expiry 2026-09-23). `state/hook-token` in the config
# directory holds a one-year token. `_hook_token` reads it; the child gets it as
# `CLAUDE_CODE_OAUTH_TOKEN`. No file, an empty one, or one that cannot be opened means the old
# path. A file that opens but is not text fails closed: no call is made. The
# parent's own env token is never passed (the allowlist stays closed), and `invoke_model`
# scrubs the token from any error text it returns. See docs/decisions/reply-judge-samples-never-refuses.md.
CREDENTIALS_FILENAME = ".credentials.json"
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"


class TokenUnreadable(Exception):
    """The token file exists but cannot be decoded. Carries no file bytes."""


def _hook_token():
    """Return the stripped token from `<config dir>/state/hook-token`, or '' if none.
    Raise `TokenUnreadable` when the file opens but does not decode as text."""
    try:
        with open(os.path.join(guard.config_dir(), "state", "hook-token"), "rb") as f:
            raw = f.read()
    except Exception:
        return ""  # a read error (absent, a directory) means no token file
    enc = "utf-16" if raw[:2] in (bytes([0xFF, 0xFE]), bytes([0xFE, 0xFF])) else "utf-8-sig"
    try:
        return raw.decode(enc).replace("\0", "").strip()
    except Exception:
        raise TokenUnreadable() from None  # not text: fail closed; `from None` drops the bytes

# The only variables the judgment subprocess's environment is built from -- never a copy
# of the parent's environment with entries removed. `PATH` to find the `claude` binary and
# any interpreter it shells to. `SystemRoot`/`windir` because Windows subprocess creation
# and DLL loading rely on them being present. `HOME`/`USERPROFILE`/`APPDATA`/
# `LOCALAPPDATA`/`TEMP`/`TMP` because a Node-based CLI resolves its own cache, npm config,
# and scratch files from them, on whichever of Windows/POSIX the host is running.
# `ANTHROPIC_BASE_URL` because an organization behind a custom API endpoint needs it to
# reach the right host at all; it names a destination, never a secret. Deliberately
# absent: `CLAUDE_CODE_MESSAGING_SOCKET`, `CLAUDE_CODE_MESSAGING_TOKEN`,
# `CLAUDE_CODE_HOST_SESSION_ID`, `CLAUDE_CODE_OAUTH_SCOPES`, and `ANTHROPIC_API_KEY`: the
# host IPC channel, the session identifier, and a secret this call does not need to do its
# one job of reading text and returning a verdict.
JUDGE_ENV_ALLOWLIST = (
    "PATH", "SystemRoot", "windir", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
    "TEMP", "TMP", "ANTHROPIC_BASE_URL",
)


def _judge_isolation():
    """Return (cwd, env) for the judgment subprocess: an empty directory that is not this
    project, holding only a copy of the login credential, and an environment built from
    `JUDGE_ENV_ALLOWLIST`, plus `TOKEN_ENV` when the token file holds a readable token, never
    copied from this process's own environment, so
    there is nothing here for a tool call to inherit, write into, or signal back to, even
    if one somehow ran, and the call can still authenticate and reach the API host."""
    token = _hook_token()  # first, so a TokenUnreadable leaves no temp dir behind
    root = tempfile.mkdtemp(prefix="decision_watch_judge_")
    config_dir = os.path.join(root, "config")
    os.makedirs(config_dir, exist_ok=True)
    real_config_dir = guard.config_dir()
    creds = os.path.join(real_config_dir, CREDENTIALS_FILENAME)
    if os.path.isfile(creds):
        try:
            shutil.copyfile(creds, os.path.join(config_dir, CREDENTIALS_FILENAME))
        except Exception:
            pass  # no credential to copy: the call below fails closed, as an auth error
    env = {name: os.environ[name] for name in JUDGE_ENV_ALLOWLIST if name in os.environ}
    env["CLAUDE_CONFIG_DIR"] = config_dir
    if token:
        env[TOKEN_ENV] = token
    return root, env


VERDICT_SHAPE = {"verdict": ("ALLOW", "FLAG")}


def invoke_model(prompt, model=MODEL, timeout=MODEL_TIMEOUT, shape=VERDICT_SHAPE, effort="xhigh"):
    """Run the judgment prompt through `claude -p`, isolated. Return (verdict_dict, error).

    `verdict_dict` is `{"verdict": "ALLOW"}` or `{"verdict": "FLAG", "why": "..."}` on
    success, and `error` is None. On any failure -- the binary missing, a timeout, a
    non-zero exit, or output that is not the JSON verdict asked for -- `verdict_dict` is
    None and `error` names why, for the caller to report as UNKNOWN rather than guess.

    `shape` is the caller's accepted answer: one key and the values it may hold. The default
    is this hook's own ALLOW/FLAG verdict. `hooks/reply_judge.py` passes `{"ok": (True, False)}`.
    `effort` None passes no --effort, so the model runs at its default, as a prompt hook does.
    """
    try:
        root, env = _judge_isolation()
    except TokenUnreadable:
        return None, "token file could not be read"
    token = env.get(TOKEN_ENV, "")
    scrub = lambda text: text.replace(token, "[token]") if token else text
    try:
        run = _nowindow.run(
            [
                "claude", "-p",  # prompt goes on stdin: a Windows command line caps at 32,767 chars
                "--model", model,
            ] + (["--effort", effort] if effort else []) + [
                "--output-format", "json",
                "--tools", "",
                "--safe-mode",
                "--permission-mode", "plan",
            ],
            input=prompt.encode("utf-8", "replace"), capture_output=True,  # bytes: text mode turns LF into CRLF on Windows
            timeout=timeout, cwd=root, env=env,
        )
    except subprocess.TimeoutExpired:
        return None, "model subprocess timed out"  # fixed text: never put str(exc) in the report
    except Exception as exc:
        return None, scrub("model subprocess failed to start: %s" % exc)
    finally:
        try:
            shutil.rmtree(root, ignore_errors=True)
        except Exception:
            pass
    # Bytes from the pipe; a str passes through, which a stubbed `subprocess.run` may return.
    text_of = lambda raw: raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw or ""
    stdout, stderr = text_of(run.stdout), text_of(run.stderr)
    if run.returncode != 0:
        return None, "model exited %s: %s" % (run.returncode, scrub(stderr)[:200])
    try:
        envelope = json.loads(stdout)
    except Exception:
        return None, "model output was not JSON"
    text = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(text, str):
        return None, "model output carried no result text"
    return parse_verdict(text, shape)


def parse_verdict(text, shape=VERDICT_SHAPE):
    """Return (verdict_dict, error) from the model's reply text. The one home of this parse:
    `invoke_model` and the `--model-text` entry below both call it."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None, "model result carried no JSON verdict"
    try:
        verdict = json.loads(match.group(0))
    except Exception:
        return None, "model result's JSON verdict did not parse"
    (key, values), = shape.items()
    if verdict.get(key) not in values:
        return None, "model result named neither %s" % " nor ".join(map(str, values))
    return verdict, None


# ------------------------------------------------------------------ orchestration

def run(hook, model_call=invoke_model, expect_key=None):
    """Return a systemMessage string, or '' when there is nothing to report.

    `model_call` is swapped in tests, so a case can assert it was never called (the common,
    nothing-protected-touched path) or stub its answer without a real subprocess.

    `expect_key` is the key phase 1 printed (the mod's `--key`). A live key that differs means
    the evidence moved between the two phases, so the reply is not used and the answer is UNKNOWN
    (SAFETY HOLE 1 of decision decision-watch-mod-limits).
    """
    path = hook.get("transcript_path")
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return UNKNOWN_PREFIX + "transcript_path is missing or does not exist."

    cwd = hook.get("cwd") or ""
    if not isinstance(cwd, str) or not cwd or not os.path.isdir(cwd):
        return UNKNOWN_PREFIX + "cwd from the hook input is missing or not a directory."

    # THE CHEAP CHECK RUNS BEFORE THE TRANSCRIPT IS PARSED. The turn's start comes from the
    # transcript's tail (`last_human_epoch`), not a whole-file read. A tail that gives no
    # baseline (None) skips the mtime filter, the same broad net the full read gave.
    baseline = last_human_epoch(path)
    changed, untracked = changed_this_turn(cwd, baseline)
    if changed is None:
        return UNKNOWN_PREFIX + "git status could not be read for this working directory."

    protected = [rel for rel in changed if looks_protected(rel, cwd)]

    # A protected file committed this turn is clean in `git status`, and agents commit.
    committed, oldest = committed_this_turn(cwd, baseline)
    if committed is None:
        return UNKNOWN_PREFIX + "git log could not be read for this working directory."
    committed = [rel for rel in committed if looks_protected(rel, cwd)]
    protected += [rel for rel in committed if rel not in protected]

    # TRIGGER: an actual on-disk change to a protected path, full stop. An outbound
    # SendMessage/Task alone no longer triggers a model call (see looks_concerning's
    # docstring for why the independent audit corrected this). Nothing executed yet is
    # not the act this hook exists to catch.
    if not protected:
        return ""

    try:
        records = read_transcript(path)
    except Exception as exc:
        return UNKNOWN_PREFIX + "the transcript could not be read (%s)." % exc
    idx, _stamp = last_human_index_and_stamp(records)

    # MAX_DIFFED_FILES bounds the number of `git diff` calls, so this loop's wall time
    # cannot grow past the fixed sum the module docstring proves against the hook's own
    # timeout, no matter how many protected paths one turn touches. A path past the cap
    # is still named in the evidence, with no git call spent on it.
    evidence = []
    for rel in protected[:MAX_DIFFED_FILES]:
        piece = file_evidence(cwd, rel, untracked.get(rel, False), oldest if rel in committed else None)
        if piece is None:
            return UNKNOWN_PREFIX + "git diff could not be read for %s." % rel
        evidence.append(piece)
    for rel in protected[MAX_DIFFED_FILES:]:
        evidence.append("%s (name only, over the per-Stop diff budget)" % rel)

    # Outbound SendMessage/Task calls only ENRICH the evidence once a real change has
    # already triggered the call; they cannot trigger it by themselves.
    outbound = [
        tu
        for rec in records_after(records, idx)
        for tu in tool_uses(rec)
        if looks_concerning(tu)
    ]
    for tu in outbound:
        evidence.append(
            "outbound %s: %s" % (tu.get("name"), json.dumps(tu.get("input") or {})[:1000])
        )

    # CAP: this exact finding (these protected paths, this evidence) already flagged once
    # in this session. Stay quiet until it changes. See "the per-incident, per-session
    # cap" above.
    session_id = hook.get("session_id") or ""
    key = incident_key(protected, evidence, content_digest(cwd, protected))
    if expect_key is not None and key != expect_key:
        return MOVED_MESSAGE
    if key in _load_seen(session_id):
        return ""

    prompt = "%s\n\n%s\n\nCHAT SINCE THE LAST HUMAN MESSAGE:\n%s" % (
        JUDGE_INSTRUCTIONS,
        "\n\n".join(evidence),
        chat_text_after(records, idx),
    )
    if len(prompt) > PROMPT_MAX_LEN:
        cut = len(prompt) - PROMPT_MAX_LEN
        prompt = prompt[:PROMPT_MAX_LEN] + (
            "\n\n[TRUNCATED: %d characters cut here to stay under the command-line "
            "length this prompt is passed with.]" % cut
        )

    try:
        verdict, error = model_call(prompt)
    except NeedsModel as need:
        raise NeedsModel(need.args[0], key)
    if error is not None:
        return UNKNOWN_PREFIX + "the model judgment could not be completed (%s)." % error
    # An ALLOW is cached like a FLAG: one model call per change, not one per Stop. The key
    # holds the files' bytes, so an edited file is judged again.
    _mark_seen(session_id, key)
    if verdict.get("verdict") == "FLAG":
        why = _safe_why(verdict.get("why") or "an unapproved change to a protected file")
        return FLAG_PREFIX + 'the judge model reported: "%s"' % why
    return ""


# ------------------------------------------------------------------ the config report
#
# Decision 7 ("Project config edits: allow and report") lets a session edit a project's own
# `.claude/hooks/*`, `.claude/settings.json`, or `.claude/settings.local.json` without a prompt.
# This section is how the owner still SEES the edit at turn end: it names every such file changed
# since the last human message, so the reply can name it under Deviations. It also names each
# merge into main landed this turn (Decision 8), unless the reply's own report block already
# names it, and each `noted`/`subject-unread` guard
# line from this turn, because the guard allows a subject it could not read and that allow must
# not be silent. The guard writes a LOCAL time and the transcript a UTC time, so the turn bound is
# converted to local time, minus one second, because the guard truncates its stamp to whole
# seconds. Fails open: any failure prints nothing, a missed report and never a wrong one.

LINT_DIR = os.path.join(HERE, "..", "lint")


def _shared_transcript():
    """Return `lint/_transcript.py`, the one home of the transcript readers
    (docs/decisions/hooks-share-the-transcript-reader.md). This section reads through it, never through
    the older copies above."""
    if LINT_DIR not in sys.path:
        sys.path.insert(0, LINT_DIR)
    import _transcript
    return _transcript

FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
MERGE_TOOLS = {"mcp__github__merge_pull_request"}

GH_PR_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")
PR_NUM_TOKEN = re.compile(r"^(\d+)$")
PR_NUM_URL = re.compile(r"/pull/(\d+)")

CONFIG_MESSAGE = "Config files changed this turn: %s."
MERGE_MESSAGE = "Merges into main this turn: %s."
UNREAD_MESSAGE = (
    "The guard could not read the subject of these commands, and allowed them: %s."
)
TAIL = " Name them in the report."
UNREAD_RULE = "subject-unread"

# Fallback label for a merge whose PR number this hook could not read from the command or the
# MCP tool's own input (for example `gh pr merge` run with no number and no PR checked out by
# convention this hook can resolve). Short and fixed, never the raw command line.
UNNUMBERED_MERGE = "an unnumbered merge"

MCP_PR_NUMBER_KEYS = ("pullNumber", "pull_number", "prNumber", "pr_number", "number", "pr")


def collect_paths(records, cwd):
    """Return the project config paths this turn's tools touched, in first-seen order."""
    reader = _shared_transcript()
    seen = []

    def note(path):
        if path and path not in seen:
            seen.append(path)

    for rec in records:
        for b in reader.tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in FILE_TOOLS:
                target = (
                    inp.get("file_path") or inp.get("path") or inp.get("notebook_path") or ""
                )
                if not isinstance(target, str) or not target:
                    continue
                try:
                    hit = guard.is_project_config(target, cwd)
                except Exception:
                    hit = False
                if hit:
                    note(target)
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                try:
                    matched = guard.project_config_shell_hit(cmd, cwd)
                except Exception:
                    matched = ""
                if matched:
                    note(matched)
    return seen


def _pr_number_from_segment(segment):
    """Return the PR number a `gh pr merge` call in `segment` names, else None.

    Reads only the tokens that follow the call's own `gh pr merge` words, so a command chained
    onto it with `;` or `&&` (already split into its own segment by the caller) can never
    supply the number for this call.
    """
    m = GH_PR_MERGE.search(segment)
    if not m:
        return None
    for tok in segment[m.end():].split():
        if tok.startswith("-"):
            continue
        num = PR_NUM_TOKEN.match(tok)
        if num:
            return num.group(1)
        url = PR_NUM_URL.search(tok)
        if url:
            return url.group(1)
    return None


def _pr_number_from_mcp_input(inp):
    for key in MCP_PR_NUMBER_KEYS:
        value = inp.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and value.strip().isdigit():
            return value.strip()
    return None


def collect_merges(records):
    """Return the merges into main this turn's tools named, as display labels, in first-seen
    order: `#<N>` when a PR number could be read, else UNNUMBERED_MERGE.
    """
    reader = _shared_transcript()
    seen = []

    def note(number):
        label = "#%s" % number if number else UNNUMBERED_MERGE
        if label not in seen:
            seen.append(label)

    for rec in records:
        for b in reader.tool_uses(rec):
            name = b.get("name")
            inp = b.get("input") or {}
            if not isinstance(inp, dict):
                continue
            if name in MERGE_TOOLS:
                note(_pr_number_from_mcp_input(inp))
            elif name in SHELL_TOOLS:
                cmd = inp.get("command") or ""
                if not isinstance(cmd, str) or not cmd.strip():
                    continue
                try:
                    stripped = guard.strip_heredoc_bodies(cmd)
                    segments = guard.split_segments(stripped)
                except Exception:
                    segments = [cmd]
                for segment in segments:
                    if GH_PR_MERGE.search(segment):
                        note(_pr_number_from_segment(segment))
    return seen


def already_named(labels, report_block):
    """Return the labels from `labels` that `report_block` does not already name.

    `#75` is looked for both as written and as `PR 75` / `PR#75` (case-insensitive), since a
    report is free to spell it either way. UNNUMBERED_MERGE is looked for verbatim: it is
    already the short, fixed string a report would have to repeat to name it.
    """
    if not report_block:
        return list(labels)
    remaining = []
    for label in labels:
        if label in report_block:
            continue
        if label.startswith("#"):
            num = label[1:]
            alt = re.compile(r"\bpr\s*#?\s*" + re.escape(num) + r"\b", re.IGNORECASE)
            if alt.search(report_block):
                continue
        remaining.append(label)
    return remaining


def last_human_stamp(records):
    """Return the timestamp of the last human message, else ''."""
    reader = _shared_transcript()
    stamp = ""
    for rec in records:
        if reader.is_last_human(rec):
            value = rec.get("timestamp") or ""
            stamp = value if isinstance(value, str) else ""
    return stamp


def _turn_bound(stamp):
    """Return the last human message time as a naive LOCAL datetime, else None.

    The transcript stamp is UTC and the guard's log stamp is local, so the bound is converted
    rather than compared across zones. One second is taken off, because the guard truncates its
    own stamp to whole seconds and a line written in the same second would otherwise be dropped.
    """
    text = (stamp or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except Exception:
        return None
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment - timedelta(seconds=1)


def collect_unread(stamp):
    """Return the matched text of each `noted`/`subject-unread` guard line from this turn."""
    bound = _turn_bound(stamp)
    if bound is None:
        return []
    try:
        # The mod runs this script with CLAUDE_CONFIG_DIR set to its own state folder, and hands
        # the real config folder in DW_REAL_CONFIG_DIR. guard.log lives in the real one.
        real = os.environ.get("DW_REAL_CONFIG_DIR")
        if not real:
            real = guard.config_dir()
            if os.path.basename(real).startswith("decision-watch-"):
                print("decision_watch: DW_REAL_CONFIG_DIR is not set under the mod, so unread-subject "
                      "notices read guard.log from the mod state folder " + real, file=sys.stderr)
        path = os.path.join(real, "guard.log")
    except Exception:
        return []
    if not os.path.exists(path):
        return []
    seen = []
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except Exception:
        return []
    reader = None
    try:
        if LINT_DIR not in sys.path:
            sys.path.insert(0, LINT_DIR)
        import guard_log_report  # lint/guard_log_report.py, the one reader of guard.log lines
        reader = guard_log_report
    except Exception:
        pass  # an unimportable reader falls back to a local split below: no note vanishes
    for line in lines:
        if reader is not None:
            row = reader.parse_line(line)
            parsed = None if row is None else (row.rule, row.when, row.matched)
        else:
            # Fallback, a second parser on purpose: the first five tab fields, extras ignored.
            fields = line.split("\t")[:5]
            try:
                parsed = (fields[3], datetime.fromisoformat(fields[0]), fields[4])
            except Exception:
                parsed = None
        if parsed is None or parsed[0] != UNREAD_RULE or parsed[1] < bound:
            continue
        text = parsed[2].strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def config_report(hook):
    """Return the config-report systemMessage for this turn, or '' for nothing to say."""
    return _report_text(config_notices(hook))


def _report_text(parts):
    return " ".join(parts) + TAIL if parts else ""


def config_notices(hook):
    """Return this turn's config notices, one string per kind, without TAIL. [] for none."""
    if hook.get("stop_hook_active"):
        return []  # a rewrite of an earlier reply: stay quiet, as `main` does for `run`
    path = hook.get("transcript_path")
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return []
    try:
        reader = _shared_transcript()
        human, after = reader.read_turn(path)
        if not after:
            return []
        cwd = hook.get("cwd") or ""
        if not isinstance(cwd, str):
            cwd = ""
        # Only this turn's records are read (the tail reader), so an idle turn costs a few KB.
        merges = collect_merges(after)
        hits = collect_paths(after, cwd)
        if merges:
            try:
                import report_guard  # lint/report_guard.py, same-repo sibling package
                merges = already_named(merges, report_guard.block_text(reader.last_reply(hook)))
            except Exception:
                # Cannot tell whether the report already named the merge: still name it.
                pass
        unread = collect_unread(last_human_stamp([human] if human else []))
    except Exception:
        return []
    if not hits and not merges and not unread:
        return []
    parts = []
    if hits:
        parts.append(CONFIG_MESSAGE % ", ".join(hits))
    if merges:
        parts.append(MERGE_MESSAGE % ", ".join(merges))
    if unread:
        parts.append(UNREAD_MESSAGE % ", ".join(unread))
    return parts


LOST_MESSAGE = UNKNOWN_PREFIX + "verdict lost: the model reply was not used (the watch ended before the model step)."


MOVED_MESSAGE = UNKNOWN_PREFIX + "the evidence changed between the two phases, so the model reply was not used."


class NeedsModel(Exception):
    """`--emit-prompt`: the cheap path ended at the model call. `args[0]` is the prompt, `args[1]`
    the evidence key phase 2 gets back as `--key`."""


def _model_call_from_argv(argv):
    """Pick `run`'s model_call. Default: `claude -p`. A caller with its own model login (a
    Claude Code mod) splits the call in two runs of this file, same Stop JSON on stdin each:
      --emit-prompt       prints {"needs_model": true, "prompt", "model"} and exits, only when
                          a model call is due; otherwise the normal output (usually nothing).
      --model-text TEXT   the model's reply text; parsed by parse_verdict, then normal output.
      --model-error TEXT  the call failed; prints the UNKNOWN message, never a pass.
    Phase 2 may end with `--key K`, the "key" phase 1 printed; `main` strips it (`_split_key`).
    Under any of these flags, printed output also carries `verdict` and `notices` (see `main`)."""
    if argv[:1] == ["--emit-prompt"] and len(argv) == 1:
        def emit(prompt):
            raise NeedsModel(prompt)
        return emit
    if argv[:1] == ["--model-text"] and len(argv) == 2:
        return lambda prompt: parse_verdict(argv[1])
    if argv[:1] == ["--model-error"] and len(argv) == 2:
        return lambda prompt: (None, argv[1][:200])
    return invoke_model


def _split_key(args):
    """Return (args without a trailing `--key K`, K or None). Only a reply flag takes a key."""
    if len(args) == 4 and args[0] in ("--model-text", "--model-error") and args[2] == "--key":
        return args[:2], args[3]
    return args, None


def main():
    guard._force_utf8_streams()
    try:
        hook = json.load(sys.stdin)
    except Exception:
        print(json.dumps({"systemMessage": UNKNOWN_PREFIX + "hook input was not readable JSON."}))
        sys.exit(0)
    if not isinstance(hook, dict):
        print(json.dumps({"systemMessage": UNKNOWN_PREFIX + "hook input was not a JSON object."}))
        sys.exit(0)
    if hook.get("stop_hook_active"):
        sys.exit(0)  # this Stop firing is already a rewrite; do not re-judge it

    try:
        argv, expect_key = _split_key(sys.argv[1:])
        model_call = _model_call_from_argv(argv)
        used = []

        def tracked(prompt):
            used.append(True)
            return model_call(prompt)

        message = run(hook, tracked, expect_key)
        handed_reply = sys.argv[1:2] in (["--model-text"], ["--model-error"]) and model_call is not invoke_model
        if handed_reply and not message and not used:
            # A reply was handed in, but the run ended before the model step (the turn's verdict
            # is already recorded). Silence here would read as an ALLOW. Say it was lost.
            message = LOST_MESSAGE
    except NeedsModel as need:
        print(json.dumps({"needs_model": True, "prompt": need.args[0], "model": MODEL, "key": need.args[1]}))
        sys.exit(0)
    except Exception as exc:
        print(json.dumps({"systemMessage": UNKNOWN_PREFIX + "the watch itself raised (%s)." % exc}))
        sys.exit(0)

    notices = config_notices(hook)
    joined = " ".join(m for m in (message, _report_text(notices)) if m)
    if joined:
        out = {"systemMessage": joined}
        if model_call is not invoke_model:
            # A split caller (a mod) shows the verdict and each notice apart (decision
            # decision-watch-mod-limits). The default output keeps the one Stop-hook field only.
            out.update(verdict=message, notices=[n + TAIL for n in notices])
        print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()
