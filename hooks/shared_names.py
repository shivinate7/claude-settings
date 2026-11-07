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
