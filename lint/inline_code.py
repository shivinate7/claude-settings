"""The one home of the inline-code mask: INLINE_CODE_RE and code_span_text. It imports no other module, so the Stop
guard (lint/report_guard.py) can read it without loading the whole linter (lint/ste_lint.py, which re-exports INLINE_CODE_RE)."""
import re

# A code span opens with a whole run of backticks and closes with a run of the same length, so a backtick inside a
# double-backtick span stays inside it. The (?<!`) before the opener keeps an unclosed run from opening a shorter span
# mid-run. No re.S: a span ends at its line, so a lone backtick never hides the next line.
INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)")


def code_span_text(match):
    """The text inside one INLINE_CODE_RE match, without its backtick runs."""
    run = len(match.group(1))
    return match.group()[run:-run]
