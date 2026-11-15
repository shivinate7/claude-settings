"""The one home of the macOS scope skip: the flags each macOS job reads, and the all-jobs-passed input that names them.

A pull request starts a macOS job only when one of that job's own scope flags is "true", so a pull request that touches
no macOS path starts no macOS runner. all-jobs-passed reads a skipped job as green only when its scope-skips input names
the job, and only while every flag the input lists is exactly "false" (actions/all-jobs-passed/check.sh).

MACOS_SCOPE_SKIPS is read by lint/test_windows_split.py and lint/test_all_jobs_passed.py, and by the scope-skips cases of
actions/all-jobs-passed/test_action.sh. Stdlib only. planned_scope_skips() gives checks.yml the scope skips and the input before
the change lands, so a case can read the planned shape on the old file.
"""
import json
import re

# Job -> the scope flags its job-level if reads, in the order its scope-skips entry lists them.
MACOS_SCOPE_SKIPS = {
    "shell-macos": ("shell_macos",),
    "checks-macos": ("checks_macos", "sweep"),
    "checks-macos-b": ("checks_macos",),
}
SCOPE_SKIPS_JSON = json.dumps({job: list(flags) for job, flags in MACOS_SCOPE_SKIPS.items()}, separators=(",", ":"))


def scope_skip_expr(job):
    """A macOS job's job-level if, without the `${{ }}` wrapper: the push guard, then its own flags on a pull_request only."""
    ors = " || ".join(f"needs.scope.outputs.{flag} == 'true'" for flag in MACOS_SCOPE_SKIPS[job])
    return f"github.event_name != 'push' && ({ors} || github.event_name != 'pull_request')"


def _job_span(text, job):
    """(start, end) of one job's block in checks.yml: its header line through the line before the next job header."""
    m = re.search(rf"^  {re.escape(job)}:\n.*?(?=^  [\w-]+:\n|\Z)", text, re.M | re.S)
    assert m, f"no {job} job: this fixture must follow checks.yml"
    return m.span()


def planned_scope_skips(text):
    """checks.yml's text with each macOS job's job-level if set to its scope skip, and all-jobs-passed given the scope-skips input.

    Each macOS job's job-level if is replaced, not matched, and it goes on the line after its `needs: scope`. The input is
    replaced in all-jobs-passed's block, so the planned text holds one canonical copy of each whatever the file held before.
    Each anchor must match exactly once, so a moved anchor fails here, not in a later assertion.
    """
    for job in MACOS_SCOPE_SKIPS:
        start, end = _job_span(text, job)
        block = text[start:end]
        assert block.count("\n    needs: scope\n") == 1, f"{job}'s needs changed: this fixture must follow it"
        block = re.sub(r"^    if: [^\n]*\n", "", block, flags=re.M)
        block = block.replace("\n    needs: scope\n", f"\n    needs: scope\n    if: ${{{{ {scope_skip_expr(job)} }}}}\n", 1)
        text = text[:start] + block + text[end:]
    start, end = _job_span(text, "all-jobs-passed")
    block = re.sub(r"^          scope-skips:[^\n]*\n", "", text[start:end], flags=re.M)
    anchor = re.search(r"^          needs: \$\{\{ toJSON\(needs\) \}\}[^\n]*\n", block, re.M)
    assert anchor and len(re.findall(r"^          needs: \$\{\{ toJSON\(needs\) \}\}", block, re.M)) == 1, \
        "all-jobs-passed's action input changed: this fixture must follow it"
    block = block[:anchor.end()] + f"          scope-skips: '{SCOPE_SKIPS_JSON}'\n" + block[anchor.end():]
    return text[:start] + block + text[end:]
