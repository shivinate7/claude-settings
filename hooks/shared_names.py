"""The one home of the names the guard and the config watch share. Standard library only.

The config watch's fast exit reads this before the guard loads, so nothing here may import the
guard or any sibling hook.
"""

import os
import re
from typing import Any, Optional

# The project's own settings files, with the leading slash the guard matches a path suffix on.
PROJECT_FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")

# The one home of the claude-code-remote server name (rule agent-no-remote-tools). The guard imports it by name;
# lint/check_agent_models.py reads it from the guard.
REMOTE_SERVER = "mcp__claude-code-remote"
# The claude-code-remote tools that start, message, tag or archive sessions, set scheduled tasks or attach repos
# and computers. An agent never calls one; the session that spawned it does. settings.json's guard matcher
# must name each (lint/test_settings_matcher.py reads this tuple).
REMOTE_OUTWARD_TOOLS = tuple(REMOTE_SERVER + "__" + short for short in (
    "create_session", "send_message", "archive_session", "unarchive_session", "interrupt_session",
    "set_session_tags", "set_session_title", "create_trigger", "update_trigger", "delete_trigger",
    "fire_trigger", "send_later", "watch_url", "unwatch_url", "subscribe_pr_activity",
    "unsubscribe_pr_activity", "add_repo", "register_repo_root", "confirm_repository_trust",
    "request_computer_folder"))

# A prompt that starts with one of these is a notice from a tool or an agent, never the owner.
TASK_NOTIFICATION_TAG = "<task-notification>"
# An agent hand-back (CLI 2.1.316 text), bare or after a frame line: the plain one or the
# mid-turn one. The tag name ends at `>` or whitespace.
_HAND_BACK_TAGS = tuple("<agent-message" + end for end in "> \t\n\r")
# Bandaid (debt inbox-saves-other-notices): a peer's send_message frame, bare at the start of the
# prompt. The tag name ends at `>` or whitespace.
_PEER_FRAME_TAGS = tuple("<cross-session-message" + end for end in "> \t\n\r")
MACHINE_TAGS = ("<system-reminder>", TASK_NOTIFICATION_TAG) + _HAND_BACK_TAGS + tuple(
    frame + "\n" + tag
    for frame in ("Another Claude session sent a message:",
                  "Another Claude session sent a message while you were working:")
    for tag in _HAND_BACK_TAGS) + _PEER_FRAME_TAGS
# More notice frames that the plain Opus ask cuts (hooks/override.py). Kept apart from MACHINE_TAGS: the inbox skip
# of MACHINE_TAGS is ruled one tag at a time (debt inbox-saves-other-notices), and test_shared_names pins its copy.
NOTICE_FRAMES = tuple(tag + end for tag in ("<webhook-payload", "<wake", "<teammate-message")
                      for end in "> \t\n\r") + ("[SYSTEM NOTIFICATION",)

# An Explore may run Sonnet, above its Haiku row, only when its brief's first non-blank line carries this marker
# (rule agent-role-model). Here, not in the guard, so the spawn judge names it without importing the guard.
EXPLORE_AUDIT_MARKER = "Audit:"
# A reviewer may run Sonnet, above its Haiku row, when its brief's first non-blank line starts with this marker: the brief is a fix check.
FIX_CHECK_MARKER = "Fix check"

# THE BRIEF MARKER TABLE (rules agent-role-model, roles-third-round-steps-up; decision agent-model-cap). One row per
# marker: (kind, regex text, position). guard.marker_hits is the one scanner that reads it. Cost: a pure scan of the
# brief text, no I/O, no process, no file. Its position decides where the row reads:
#   "line-start": every line of the brief that starts with the marker, case-insensitive, leading blanks allowed.
#   "first-line": the brief's first non-blank line only, case-sensitive; a row says whether text may stand ahead of the marker
#     (the round and audit rows allow it, the fix check row does not).
# The two positions differ because the owner ruled them apart: a role word or markup ahead of `Round N of 3` on the
# first line still counts, but lowercase prose must not. A group 1 in a row is the marker's number n; a row with none
# has no n.
_N_OF_3 = r"[ \t]+(\d)[ \t]+of[ \t]+3\b"
# The round or try shape with no number group, for the lookaheads of the first-line round row.
_ANY_ROUND_SHAPE = r"(?:Round|Try)[ \t]+\d[ \t]+of[ \t]+3\b"
BRIEF_MARKERS = (
    ("round", r"(?im)^[ \t]*round" + _N_OF_3, "line-start"),
    # `Try N of 3` counts at a line start only, until note try-marker-sunset.
    ("try", r"(?im)^[ \t]*try" + _N_OF_3, "line-start"),
    # The first-line round row reads a first line that starts with no marker in any case (the whole lookahead
    # ignores case, as the line-start rows do, and leaves that line to them). On it, the leftmost marker-shaped text counts, and only when it is `Round`: the tempered
    # `.` stops at a leftmost `Try`, so a later `Round` on that line is prose and adds nothing.
    ("round", r"^(?![ \t]*(?i:(?:round|try)[ \t]+\d[ \t]+of[ \t]+3\b))(?:(?!\b" + _ANY_ROUND_SHAPE + r").)*?\bRound" + _N_OF_3,
     "first-line"),
    ("audit", r"\b" + re.escape(EXPLORE_AUDIT_MARKER), "first-line"),
    # The fix check marker must open the first line (blanks allowed): text ahead of it, as in "New lane after Fix check FAIL", does not count.
    ("fixcheck", r"^[ \t]*" + re.escape(FIX_CHECK_MARKER) + r"\b", "first-line"),
)

# The owner's two gh logins on his computer. A gh command handed to him switches to the default first;
# the fallback serves only a repo the default cannot reach (decision act-in-place, rule gh-login-switch).
GH_DEFAULT_LOGIN = "shivinate7"
GH_FALLBACK_LOGIN = "ssemwal-cdc"
# The repo that holds the shared waiting-page template, and the folder of it (rule page-form-to-template: a page
# comment is rewritten into the template, never answered by a thread reply). The one home of both strings.
SETTINGS_REPO = GH_DEFAULT_LOGIN + "/claude-settings"
TEMPLATE_DIR = "skills/waiting-page"

# The tags a session carries (decision session-tiers, Tier tags). The roadmap build reads them from live sessions and
# the guard's rule lane-repo-tag checks them on a lane `create_session`, so both name the same strings.
REPO_TAG = "cs-repo:"
STEP_TAG = "cs-step:"
# A topic lane carries TOPIC_TAG; a tier session (batch-runner, triage) carries BUILD_TAG plus its tier; a lane
# session carries LANE_TAG.
TOPIC_TAG = "cs-topic:"
BUILD_TAG = "cs-build:"
LANE_TAG = BUILD_TAG + "lane"
# A lane start prompt opens with `Grant: <owner words>, <time>`; the guard reads the line by this marker (rules
# lane-effort-pin and lane-one-topic).
LANE_GRANT_MARKER = "Grant:"
CREATE_SESSION_TOOL = REMOTE_SERVER + "__create_session"


def lane_tags(tool_input: dict[str, Any]) -> list[Any]:
    """The `tags` of a call as a list: one string is a list of one; anything else that is not a list is empty."""
    tags = tool_input.get("tags")
    if isinstance(tags, str):
        return [tags]
    return tags if isinstance(tags, list) else []


def is_lane_create_session(tool: str, tool_input: dict[str, Any]) -> bool:
    """True for a create_session call that tags a lane: any tag that, stripped and casefolded, is LANE_TAG. The one
    reading of the lane tag; the lane checks and the floor's remedy choice share it."""
    return tool == CREATE_SESSION_TOOL and any(
        isinstance(t, str) and t.strip().casefold() == LANE_TAG for t in lane_tags(tool_input))


def grant_line_holds_words(line: str) -> bool:
    """True when a `Grant:` line carries the owner's words: some letter or digit after the marker, and no `<`, which
    marks a template placeholder such as `<owner words>`. The one reading, shared by rules lane-effort-pin and
    lane-one-topic."""
    words = line[len(LANE_GRANT_MARKER):].strip() if line.startswith(LANE_GRANT_MARKER) else ""
    return "<" not in words and any(c.isalnum() for c in words)


def lane_head_refs(slug: str) -> tuple[str, str]:
    """The head refs a lane's pull request may carry for its step `slug`: the bare slug and `lane/<slug>`. The one
    home, read by the roadmap build (idle lanes, stalled steps) and by the archive guard, so the two forms cannot
    drift apart."""
    return (slug, "lane/" + slug)


def repo_tag_names(tag: object, slug: str) -> bool:
    """True when `tag` is exactly REPO_TAG plus `slug` (owner/name), the slug compared without case. The one
    reading of a repo tag: no strip, the exact prefix, so a tag one reader accepts the other accepts."""
    return isinstance(tag, str) and tag.startswith(REPO_TAG) and tag[len(REPO_TAG):].lower() == slug.lower()


# The tool that reads and writes the waiting page's items (hooks/guard.py, hooks/call_judge.py).
DATA_TOOL = "ArtifactData"
# The tool that publishes a page (hooks/guard.py).
PAGE_TOOL = "Artifact"

# The artifact tools reach a session under two sets of names: the cloud three, and the Mac claude-artifacts server's
# fifteen. Each family is one constant; a settings.json matcher that names a cloud tool names its whole family
# (lint/test_settings_matcher.py), and hooks/test_shared_names.py pins the eighteen live names.
ARTIFACT_MAC_SERVER = "mcp__claude-artifacts"


def _mac(*shorts: str) -> tuple:
    return tuple(ARTIFACT_MAC_SERVER + "__" + short for short in shorts)


# Reads and writes of the page's database.
ARTIFACT_DATA_TOOLS = (DATA_TOOL,) + _mac("db_get", "db_list", "db_query", "db_str_replace", "db_usage", "db_write")
# Publishes and reads of the page itself, and the capability and guide tools.
ARTIFACT_PAGE_TOOLS = (PAGE_TOOL,) + _mac(
    "declare_capabilities", "describe_capabilities", "get_artifact", "guide", "list_artifacts", "publish_files",
    "read_artifact")
# Comments on a page. No guard judges them today; the names sit here so a matcher can name them.
ARTIFACT_COMMENTS_TOOLS = ("ArtifactComments",) + _mac("read_comments", "watch")

_MAC_DB_WRITE_OPS = {"set": "set", "merge": "update", "update": "update", "delete": "delete"}


def _split_doc_path(path: object) -> Optional[tuple]:
    """(collection, doc_id) of a `collection/doc_id` path, the doc id being the rest of the path, else None."""
    if not isinstance(path, str):
        return None
    collection, _, doc_id = path.partition("/")
    return (collection, doc_id) if collection and doc_id else None


def _canonical_mac_call(short: str, tool_input: dict) -> Optional[tuple]:
    """The (name, input) of one Mac call in the shape of its cloud twin, or None when it is not mapped or is malformed."""
    rest = dict(tool_input)
    if short == "db_write":
        ops = rest.pop("ops", None)
        if not isinstance(ops, list):
            return None
        writes = []
        for op in ops:
            if not isinstance(op, dict) or op.get("op") not in _MAC_DB_WRITE_OPS:
                return None
            parts = _split_doc_path(op.get("path"))
            if parts is None:
                return None
            write = {"op": _MAC_DB_WRITE_OPS[op["op"]], "collection": parts[0], "doc_id": parts[1]}
            for key in ("data", "ifVersion"):
                if key in op:
                    write[key] = op[key]
            writes.append(write)
        return DATA_TOOL, dict(rest, action="batch", writes=writes)
    if short in ("db_get", "db_str_replace"):
        parts = _split_doc_path(rest.pop("path", None))
        if parts is None:
            return None
        if short == "db_str_replace" and not all(isinstance(rest.get(k), str) for k in ("field", "old_str", "new_str")):
            return None
        return DATA_TOOL, dict(rest, action="get" if short == "db_get" else "str_replace",
                               collection=parts[0], doc_id=parts[1])
    if short in ("db_list", "db_query"):
        if not isinstance(rest.get("collection"), str) or not rest["collection"]:
            return None
        return DATA_TOOL, dict(rest, action="list" if short == "db_list" else "query")
    if short == "publish_files":
        files = rest.pop("files", None)
        if not isinstance(files, list):
            return None
        for entry in files:
            if isinstance(entry, dict) and entry.get("as") == "index.html" and isinstance(entry.get("path"), str):
                return PAGE_TOOL, dict(rest, action="publish", file_path=entry["path"])
        return None
    return None


def canonical_artifact_call(tool_name: object, tool_input: object) -> tuple:
    """(name, input) of a Mac claude-artifacts db or publish call mapped to its cloud twin's shape (ArtifactData or
    Artifact), so each later check reads one shape. Any other call, and any malformed one, comes back unchanged. Pure:
    it never raises and never changes the caller's input. Assumed, not confirmed: a Mac call carries its page's url
    as tool_input.url."""
    prefix = ARTIFACT_MAC_SERVER + "__"
    if not isinstance(tool_name, str) or not tool_name.startswith(prefix) or not isinstance(tool_input, dict):
        return tool_name, tool_input
    try:
        mapped = _canonical_mac_call(tool_name[len(prefix):], tool_input)
    except Exception:
        mapped = None
    return mapped if mapped is not None else (tool_name, tool_input)

# The folder under the config dir that holds per-hook state files.
STATE_DIR_NAME = "state"


def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


def refusals_path(session_id: object) -> Optional[str]:
    """The file of tool refusals a session has not yet raised with the owner, or None for an id that
    is not a plain name. Written by hooks/refusal_note.py, read and trimmed by lint/report_guard.py."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[\w.-]+", session_id) or session_id.startswith("."):
        return None
    return os.path.join(config_dir(), STATE_DIR_NAME, "refusals", session_id + ".jsonl")


def raised_refusals_path(session_id: object) -> Optional[str]:
    """The file of (tool_name, reason) pairs a session's replies have already raised with the owner, so the same
    tool refused again for the same reason does not block again, or None for an id that is not a plain name.
    Written and read by lint/report_guard.py, beside the refusals file."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[\w.-]+", session_id) or session_id.startswith("."):
        return None
    return os.path.join(config_dir(), STATE_DIR_NAME, "refusals-raised", session_id + ".json")


def route_flags_path(session_id: object) -> Optional[str]:
    """The file of route-row flags a session's Stop has already shown, so each shows once per session, or None for
    an id that is not a plain name. Written and read by lint/report_guard.py."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[\w.-]+", session_id) or session_id.startswith("."):
        return None
    return os.path.join(config_dir(), STATE_DIR_NAME, "route-flags", session_id + ".json")
