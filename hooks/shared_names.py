"""The one home of the names the guard and the config watch share. Standard library only.

The config watch's fast exit reads this before the guard loads, so nothing here may import the
guard or any sibling hook.
"""

import os

# The project's own settings files, with the leading slash the guard matches a path suffix on.
PROJECT_FROZEN_FILES = ("/.claude/settings.json", "/.claude/settings.local.json")

# A prompt that starts with one of these is a notice from a tool or an agent, never the owner.
TASK_NOTIFICATION_TAG = "<task-notification>"
MACHINE_TAGS = ("<system-reminder>", TASK_NOTIFICATION_TAG)


def config_dir() -> str:
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude"
    )
