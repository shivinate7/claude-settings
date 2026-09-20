# A gate's allow list is the constant

CLAUDE.md now names this rule: a gate's allow list must point at the constant
the code emits, never a copy of it.

## Scope, stated plainly

This rule governs one shape only. A gate holds a permit list, a set of what
it lets through. Somewhere else, code holds the set it actually emits or
reads. Those are two objects that must say the same thing.

This rule does not govern code duplication in general. Three functions in
this repo are copied on purpose, and none of them is a permit list.
`is_last_human` sits in `lint/md_sweep.py:116` and in
`hooks/config_report.py:58`. It is copied so each Stop hook stays in one
file, with no import between two hooks fired by the same event.
`paragraph_blocks` sits in `lint/ste_gate.py:64`, copied for the same reason
from `lint/md_sweep.py`. Each is a transcript or text helper. None decides
what a gate lets through. A reader must not point at those three files as a
violation of this rule.

## Three patterns, not one

**1. Import the constant.** The default. When a gate runs in the same
language and the same process as the code it checks, it imports the value
instead of re-deriving it.

`lint/report_gate.py` first matched a git write with a regex over the raw
command text. That regex read the words `git commit` inside a quoted
probe list as a real landing, a false positive. That false alarm is the
reason anyone touched this file.

The first fix required the subcommand to sit right after `git` in the
segment's own tokens. It killed the false positive. It also missed
`git -C /path commit`, because `-C /path` sits between the command word
and the subcommand. A real landing then went unreported, a false
negative, and a gate that stays silent says nothing.

The second fix imported `hooks/guard.py`'s own `git_calls`, which already
walks past `sudo` and every value-taking option, `-C` included, to the
real subcommand. The hand-rolled fix had re-derived one piece of that
resolver, and re-derived it short. Importing the whole resolver is what
closed both failures.

**2. Make the build emit the constant, and read what it emitted.** For a
boundary an import cannot cross. `landed-dirs.txt` is the one file
`install.sh` and both lists in `install.ps1` read at runtime. Neither
installer holds its own copy of the directory set. A shell script, a
PowerShell script, and an embedded post-merge hook string cannot import a
Python value. The shared file is the constant instead.

**3. Pin the copy with a check.** For when the copy must stay, for a reason
that outweighs the drift risk. `hooks/guard.py` keeps `CONFIG_FROZEN_DIRS` as
its own literal on purpose. Its own comment says why: "a frozen-path list
read from a file shrinks to nothing when the file is missing or
unreadable." A missing file would then quietly weaken a security control.
`lint/check_landed_dirs.py` parses that literal out of `hooks/guard.py` and
fails the build when it disagrees with `landed-dirs.txt`. The copy stays.
The check makes the two sides of it answer to each other.

This third pattern is the one the mailaudit proposal this entry replaces did
not carry. It is also the most useful of the three, because it is the
pattern for the case where the first two do not apply.

## The evidence

Commit 9c1efab pruned `land_dir` entries that the install source no longer
defined, this repo's own instance of a copy drifting from its source.
Before commit 7a035da, the set of directories landed under `~/.claude` sat
in four places. The languages were three: `install.sh`, two lists in
`install.ps1`, and `CONFIG_FROZEN_DIRS` in `hooks/guard.py`. A fifth copy in
`hooks/test_install_src.sh` checked its own hardcoded set and omitted
`agents`, so the suite could not catch a miss there either. That commit's
own message states both facts.

## The outside measurement, and its own limit

The pattern itself comes from a sibling repository, mailaudit. Its ledger
export carries a real leak check. A page decode refuses any key outside
`SEED_KEEP`, the same constant the export code emits. It never checks a
second copy of that set. Its own words carry the second half of this rule,
and it must travel with the first: "It is a backstop, not a proof: it can
only refuse the leaks someone already thought of."

The same limit holds here. `lint/check_landed_dirs.py` catches a directory
added to one side and not the other. It cannot catch a directory that never
gets written into either side in the first place. A checked allow list is
still only as good as the set of leaks someone thought to write the check
against.

## The mechanism

`lint/check_landed_dirs.py` is the mechanism for this rule, pinned by its
`CONFIG_FROZEN_DIRS` needle in `lint/rule_mechanisms.json`.
