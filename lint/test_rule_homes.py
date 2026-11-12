#!/usr/bin/env python3
"""The files a rule anchor may sit in, one list for every test case that names them.

Imported by lint/test_rule_audit.py, lint/test_check_ruling_kind.py, lint/test_check_glossary.py and
lint/test_hook_catalog.py. It holds no test: run on its own, it does nothing.

DESTINATIONS are the files a rule moves into when it leaves CLAUDE.md. Each one must be read as a
rule file: an anchor there is seen by the audit, a Home may name it, a glossary home may name it,
and the records page lists it. CLAUDE.md is not here, because every case already reads it.
"""

DESTINATIONS = (
    "skills/waiting-page/SKILL.md",
    "skills/fresh-prose/SKILL.md",
    "skills/design-review/SKILL.md",
    ".claude/rules/hooks.md",
    ".claude/rules/guards.md",
)
