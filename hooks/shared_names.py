"""The one home of the names the guard and the config watch share. Standard library only.

The config watch's fast exit reads this before the guard loads, so nothing here may import the
guard or any sibling hook.
"""

import os

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

# The tags a session carries (decision session-tiers, Tier tags). The roadmap build reads them from live sessions and
# the guard's rule lane-repo-tag checks them on a lane `create_session`, so both name the same strings.
REPO_TAG = "cs-repo:"
STEP_TAG = "cs-step:"

# The tool that reads and writes the waiting page's items (hooks/guard.py, hooks/call_judge.py).
DATA_TOOL = "ArtifactData"

# The folder under the config dir that holds per-hook state files.
STATE_DIR_NAME = "state"


def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
