"""The guard's impeccable family: the impeccable rules.

guard.py is the only entry point, and it calls these checks in its fixed order.
Other files reach these names through `guard`.

Rule index (the full entry; guard.py keeps one line):
  impeccable-review-only  deny. A build or settings-writer command of the impeccable skill.
                       (design-skills)
"""
import os
import re

from guard_core import (
    POWERSHELL_CALL, _split_heredocs, basename, inline_script, resolve_command, segment_tokens, split_segments,
    strip_heredoc_bodies,
)
from guard_core import HOOKS_HOME as _HERE
from guard_env import _substitutions


# ------------------------------------------------------------------ impeccable is review-only
#
# docs/decisions/design-skills.md, rule `impeccable-review-only`: the skill loads only for a review
# (`audit`, `critique`). Its build commands and its settings writers are refused. The reason names
# no command; the log holds what the call asked for.
IMPECCABLE_REASON = ("impeccable is for a design review only. Ask for a review of the rendered "
                     "screens; make any change to the design by hand.")
IMPECCABLE_SKILLS = ("impeccable", "impeccable:impeccable")
IMPECCABLE_REVIEWS = ("audit", "critique")
# The skill reads the FIRST word of its args as the command and the rest as target text (skills/impeccable
# SKILL.md, Routing); it asks once when two commands fit. So a `;` starts no second command, and a part
# after it is refused only when it opens with a command verb other than a review: the Commands table
# of that SKILL.md is the list, read when a review carries a `;`. `|`, `&&` and a newline always chain.
IMPECCABLE_CHAIN = re.compile(r"[|\n]|&&")
IMPECCABLE_JOINERS = ("then", "and")
IMPECCABLE_SKILL_FILE = os.path.join(_HERE, "..", "skills", "impeccable", "SKILL.md")
IMPECCABLE_VERB_ROW = re.compile(r"^\| `([a-z]+)[^`]*` \| [A-Z][a-z]+ \|", re.M)
RUNNER_WORDS = ("npx", "bunx", "node", "pnpm", "yarn", "npm", "dlx", "exec", "run", "x")
PACKAGE_FLAGS = ("-p", "--package")


def impeccable_name(token: str) -> str:
    """The package or script name of a token, without a path, a `@version` or an extension."""
    name = basename(token).split("@", 1)[0]
    return name.rsplit(".", 1)[0]


def impeccable_command_verbs():
    """The command verbs in the Commands table of the impeccable SKILL.md, or None when the file or
    the table cannot be read. Unread, every part after a `;` is refused, as it was before the table."""
    try:
        with open(IMPECCABLE_SKILL_FILE, encoding="utf-8") as handle:
            table = re.split(r"(?m)^## ", handle.read().split("\n## Commands", 1)[1], 1)[0]
    except (OSError, IndexError, UnicodeDecodeError):
        return None
    return set(IMPECCABLE_VERB_ROW.findall(table)) or None


def impeccable_skill_hit(tool_input) -> str:
    skill, args = tool_input.get("skill"), tool_input.get("args") or ""
    if not isinstance(skill, str) or skill.lstrip("/") not in IMPECCABLE_SKILLS:
        return ""
    words = args.split(";")[0].split() if isinstance(args, str) else []
    text = args.strip() if isinstance(args, str) else ""
    if words and words[0] in IMPECCABLE_REVIEWS and not IMPECCABLE_CHAIN.search(text):
        parts = [part.split() for part in text.split(";")[1:]]
        for part in parts:   # "then polish" opens with polish: read past a joining word
            while part and part[0] in IMPECCABLE_JOINERS:
                part.pop(0)
        verbs = impeccable_command_verbs() if any(parts) else set()
        if verbs is not None and not any(part[0] in verbs - set(IMPECCABLE_REVIEWS)
                                         for part in parts if part):
            return ""
    return ("skill %s %s" % (skill, args))[:100]


def impeccable_shell_hit(segment: str) -> str:
    """A segment that runs impeccable with anything but `detect ...` or `hooks status`. Shell
    wrappers (`bash -c`, `npx -c`) are unwrapped; a runner or script suffix (`.cmd`, `.exe`,
    `.mjs`) and PowerShell's call operator `&` are read through."""
    tokens = segment_tokens(segment)
    if not tokens:
        return ""
    script = inline_script(tokens)
    if script:
        return next((hit for part in split_segments(script)
                     if (hit := impeccable_shell_hit(part))), "")
    index = resolve_command(tokens)
    if index is None or index >= len(tokens):
        return ""
    while index < len(tokens) and (impeccable_name(tokens[index]) in RUNNER_WORDS
                                   or tokens[index].startswith("-")):
        if tokens[index] in ("-c", "--call") and index + 1 < len(tokens):
            return next((hit for part in split_segments(tokens[index + 1])
                         if (hit := impeccable_shell_hit(part))), "")
        index += 2 if tokens[index] in PACKAGE_FLAGS else 1
    if index >= len(tokens) or impeccable_name(tokens[index]) != "impeccable":
        return ""
    rest = tokens[index + 1:]
    while rest and rest[0].startswith("-"):   # leading flags and the `--` that ends them
        rest = rest[1:]
    if rest[:1] == ["detect"] or rest[:2] == ["hooks", "status"]:
        return ""
    return segment.strip()[:100]


# A PowerShell here-string: `@'` ... `'@` is text, `@"` ... `"@` runs its `$(...)`.
_HERE_STRING = re.compile(r"@(['\"])[ \t]*\r?\n(.*?)\r?\n\1@", re.S)


def impeccable_command_hit(raw: str) -> str:
    """Judge a whole command for impeccable. Only a body a shell reads is judged as shell lines,
    and an unquoted heredoc body or an expandable here-string is judged by the `$(...)` and
    backticks it runs. The limits: a Python, Node, Perl or Ruby
    body is not read, and a here-string body is allowed."""
    texts = []
    if POWERSHELL_CALL[0] and "@" in raw:
        def cut(found):
            if found.group(1) == '"':
                texts.extend(t for t, _ in _substitutions(found.group(2), powershell=True,
                                                          heredoc=True)[0][:-1])
            return "x"
        raw = _HERE_STRING.sub(cut, raw)
    texts.append(strip_heredoc_bodies(raw, shells_only=True))
    if "<<" in raw:
        for quote, body, _ in _split_heredocs(raw)[1]:
            if not quote:
                texts.extend(t for t, _ in _substitutions(body, heredoc=True)[0][:-1])
    for text in texts:
        for segment in split_segments(text):
            matched = impeccable_shell_hit(segment)
            if matched:
                return matched
    return ""


# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
