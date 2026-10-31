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
MACHINE_TAGS = ("<system-reminder>", TASK_NOTIFICATION_TAG)

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


def read_merge_role():
    """This session's recorded merge role, or None: no session id, no file, unreadable or malformed, another session's, or a tier outside MERGE_ROLES.
    Every failure is None, so a gate built on it fails closed. An absent id never equals an absent record.
    The id is the environment's CLAUDE_CODE_REMOTE_SESSION_ID (cse_<id>), never a hook payload's session_id."""
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
    return role if isinstance(role, str) and role in MERGE_ROLES else None  # a list is unhashable: test the type first
