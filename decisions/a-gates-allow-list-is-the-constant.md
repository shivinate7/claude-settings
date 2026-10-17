# A gate's allow list is the constant

## The ruling

CLAUDE.md `building-allow-list-is-the-constant`: a gate's allow list must point at the constant the code emits, never a copy of it.

Scope: one shape only. A gate holds a permit list, a set of what it lets through. Elsewhere, code holds the set it actually emits or reads. Those two objects must say the same thing. The rule does not govern code duplication in general. A transcript reader or a text helper is not a permit list.

Three patterns:

1. **Import the constant.** The default, when a gate runs in the same language and process as the code it checks. `lint/report_gate.py` imports `hooks/guard.py`'s `git_calls`. A hand-rolled copy missed `git -C /path commit` (`guard-that-cries-wolf-is-spent`).
2. **Make the build emit the constant, and read what it emitted.** For a boundary an import cannot cross. `landed-dirs.txt` is the one file `install.sh` and both lists in `install.ps1` read at runtime. A shell script, a PowerShell script and an embedded post-merge hook string cannot import a Python value.
3. **Pin the copy with a check.** For a copy that must stay. `hooks/guard.py` keeps `CONFIG_FROZEN_DIRS` as its own literal on purpose, because a frozen-path list read from a file shrinks to nothing when the file is missing or unreadable. `lint/check_landed_dirs.py` parses that literal and fails the build when it disagrees with `landed-dirs.txt`.

The mechanism is `lint/check_landed_dirs.py`, pinned by its `CONFIG_FROZEN_DIRS` needle in `lint/rule_mechanisms.json`.

Limit: a checked allow list is a backstop, not a proof. It catches a directory added to one side and not the other. It cannot catch a directory that neither side holds. For the one bad edit that must mute one reporter and never all four, see `hooks-share-the-transcript-reader`.

Kind: process
Home: rule:building-allow-list-is-the-constant
