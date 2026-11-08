"""The one home of the names the guard and the config watch share. Standard library only.

The config watch's fast exit reads this before the guard loads, so nothing here may import the
guard or any sibling hook.
"""

import os
import re
from typing import Optional

# The project's own settings files, with the leading slash the guard matches a path suffix on.
PROJECT_FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")

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

# THE BRIEF MARKER TABLE (rules agent-role-model, roles-third-round-steps-up; decision agent-model-cap). One row per
# marker: (kind, regex text, position). guard.marker_hits is the one scanner that reads it. Cost: a pure scan of the
# brief text, no I/O, no process, no file. Its position decides where the row reads:
#   "line-start": every line of the brief that starts with the marker, case-insensitive, leading blanks allowed.
#   "first-line": the brief's first non-blank line only, case-sensitive, with any text ahead of the marker.
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
)

# The owner's two gh logins on his computer. A gh command handed to him switches to the default first;
# the fallback serves only a repo the default cannot reach (decision act-in-place, rule gh-login-switch).
GH_DEFAULT_LOGIN = "shivinate7"
GH_FALLBACK_LOGIN = "ssemwal-cdc"

# The tags a session carries (decision session-tiers, Tier tags). The roadmap build reads them from live sessions and
# the guard's rule lane-repo-tag checks them on a lane `create_session`, so both name the same strings.
REPO_TAG = "cs-repo:"
STEP_TAG = "cs-step:"
# A topic lane carries TOPIC_TAG; a tier session (batch-runner, triage) carries BUILD_TAG plus its tier; a lane
# session carries LANE_TAG.
TOPIC_TAG = "cs-topic:"
BUILD_TAG = "cs-build:"
LANE_TAG = BUILD_TAG + "lane"


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

# The Mac names of the same tools (owner item 440, from Home transcripts). A Mac call has its own
# input shape; cloud_twin turns it into the cloud call it stands for, so every guard judges one shape.
MAC_PREFIX = "mcp__claude-artifacts__"
MAC_DATA_TOOLS = frozenset(MAC_PREFIX + name for name in ("db_write", "db_str_replace", "db_get", "db_list", "db_query"))
MAC_PAGE_TOOLS = frozenset((MAC_PREFIX + "publish_files",))
_PAGE_URL = "https://claude.ai/artifact/"  # a Mac `slug` is the artifact id: the guards compare only the id of a url
_MAC_ACTION = {"db_str_replace": "str_replace", "db_get": "get", "db_list": "list", "db_query": "query"}


def _split_path(path):
    """(collection, doc_id) of a Mac `<collection>/<id>` path: the collection is the first segment, the id is the rest.
    A path with no id (`items/`, `items`) has doc_id None."""
    collection, _, doc_id = path.partition("/")
    return collection, doc_id or None


def _mac_url(tool_input):
    slug = tool_input.get("slug")
    return {"url": _PAGE_URL + slug} if isinstance(slug, str) and slug else {}


def _mac_write(entry):
    """The cloud write of one Mac db_write op. Mac `merge` has no cloud action: it changes fields, as an update does."""
    op = entry.get("op")
    collection, doc_id = _split_path(entry.get("path") if isinstance(entry.get("path"), str) else "")
    write = {"op": "update" if op == "merge" else op, "collection": collection}
    if doc_id is not None:
        write["doc_id"] = doc_id
    if "data" in entry:
        write["data"] = entry["data"]
    return write


def cloud_twin(tool, tool_input):
    """(tool, tool_input) of the cloud call a Mac artifact call stands for. Any other call, and a Mac call whose input
    is not the shape item 440 gives, comes back unchanged. One db_write op becomes a single write, several a cloud
    batch. Assumed, not in item 440: a db_query input carries `collection` or `path` (any other key is kept as is);
    a publish_files names its page by the `files` entry whose `as` is index.html, else the first entry with a path."""
    if not isinstance(tool, str) or not isinstance(tool_input, dict):
        return tool, tool_input
    twin = _mac_url(tool_input)
    if tool in MAC_PAGE_TOOLS:
        files = [f for f in tool_input.get("files") or [] if isinstance(f, dict) and isinstance(f.get("path"), str)]
        page = next((f for f in files if f.get("as") == "index.html"), files[0] if files else None)
        twin.update({key: tool_input[key] for key in ("title", "icon") if key in tool_input})
        if page:
            twin["file_path"] = page["path"]
        return PAGE_TOOL, twin
    if tool not in MAC_DATA_TOOLS:
        return tool, tool_input
    name = tool[len(MAC_PREFIX):]
    if name == "db_write":
        ops = tool_input.get("ops")
        if not isinstance(ops, list) or not all(isinstance(o, dict) for o in ops):
            return tool, tool_input
        writes = [_mac_write(o) for o in ops]
        if len(writes) == 1:
            write = writes[0]
            twin.update(action=write.pop("op"), **write)
        else:
            twin.update(action="batch", writes=writes)
        return DATA_TOOL, twin
    path = tool_input.get("path")
    collection, doc_id = _split_path(path) if isinstance(path, str) else (tool_input.get("collection"), None)
    twin.update({k: v for k, v in tool_input.items() if k not in ("slug", "path", "collection")})
    twin.update(action=_MAC_ACTION[name], collection=collection)
    if doc_id is not None:
        twin["doc_id"] = doc_id
    return DATA_TOOL, twin

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


def route_flags_path(session_id: object) -> Optional[str]:
    """The file of route-row flags a session's Stop has already shown, so each shows once per session, or None for
    an id that is not a plain name. Written and read by lint/report_guard.py."""
    if not isinstance(session_id, str) or not re.fullmatch(r"[\w.-]+", session_id) or session_id.startswith("."):
        return None
    return os.path.join(config_dir(), STATE_DIR_NAME, "route-flags", session_id + ".json")
