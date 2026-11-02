"""The one home of the names the guard and the config watch share. Standard library only.

The config watch's fast exit reads this before the guard loads, so nothing here may import the
guard or any sibling hook.
"""

import json
import os
import pathlib

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

# An Explore may run Sonnet, above its Haiku row, only when its brief's first non-blank line carries this marker
# (rule agent-role-model). Here, not in the guard, so the spawn judge names it without importing the guard.
EXPLORE_AUDIT_MARKER = "Audit:"

# The owner's two gh logins on his computer. A gh command handed to him switches to the default first;
# the fallback serves only a repo the default cannot reach (decision act-in-place, rule gh-login-switch).
GH_DEFAULT_LOGIN = "shivinate7"
GH_FALLBACK_LOGIN = "ssemwal-cdc"

# The tool that reads and writes the waiting page's items (hooks/guard.py, hooks/call_judge.py).
DATA_TOOL = "ArtifactData"

# The folder under the config dir that holds per-hook state files.
STATE_DIR_NAME = "state"


def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )


# The tiers that may run `merge <pr> --confirm` in a cloud session. The guard's coordinator-scope
# rule reads the same file for the same session, so the reader lives here once.
MERGE_ROLES = {"coordinator", "batch-runner"}


def role_path():
    return pathlib.Path(config_dir()) / STATE_DIR_NAME / "merge-role.json"


def read_recorded_role():
    """The role string this session's own role file records, any tier, or None: no session id, no file, unreadable or
    malformed, another session's, or a role that is no string. A file that gives a role decides the tier alone."""
    sid = os.environ.get("CLAUDE_CODE_REMOTE_SESSION_ID")
    if not sid:
        return None
    try:
        data = json.loads(role_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        return None
    if not isinstance(data, dict) or data.get("session") != sid:
        return None
    role = data.get("role")
    return role if isinstance(role, str) else None


def read_merge_role():
    """This session's recorded merge role, or None: no session id, no file, unreadable or malformed, another session's, or a tier outside MERGE_ROLES.
    Every failure is None, so a gate built on it fails closed. An absent id never equals an absent record.
    The id is the environment's CLAUDE_CODE_REMOTE_SESSION_ID (cse_<id>), never a hook payload's session_id."""
    role = read_recorded_role()
    return role if role in MERGE_ROLES else None
