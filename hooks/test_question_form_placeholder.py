#!/usr/bin/env python3
"""Cases for the placeholder check on a waiting-page task's `command` (hooks/question_form.py, command_in_item_hit).

A command handed to the owner must run as it stands. A token that the owner has to fill is refused: `/dev/sdX`
with an optional digit, an angle-bracket word such as `<branch>` or `<your-path>`, a word that starts `YOUR_` or
`your-`, `REPLACE_ME`, `CHANGEME`, and a standalone `xxx` or `XXX`. The report surface (a reply's fenced shell block)
has its own cases in lint/test_report_guard_placeholder.py, and both read one detector.

Refuse cases: a token in the `mac` or the `powershell` string makes command_in_item_hit return a reason.
Allow cases: a line with a look-alike shape that is a real shell form (a heredoc, a redirect, a fd duplicate, a
variable, an all-caps env var, a real device, a regex alternation, a URL query, a git range, `xxx` inside a longer
word) returns "" from the same check, with the same frame.

The task fixture and the check harness come from hooks/test_question_form.py and hooks/test_call_judge.py, the one
home of each. Run it from the repository root:

    python3 hooks/test_question_form_placeholder.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_call_judge as tcj  # noqa: E402  check and FAILED, the case harness (one home)
import test_question_form as tqf  # noqa: E402  task_item, the waiting-page task fixture (one home)

check, FAILED = tcj.check, tcj.FAILED
question_form = tqf.question_form

STEP = "Run the command below."

# Each token sits in its own command line, which the owner would run as it stands.
REFUSE_TOKENS = (
    "sudo e2fsck -f -D /dev/sdX1",
    "sudo e2fsck -f -D /dev/sdX",
    "git checkout <branch>",
    "cd <your-path>",
    "export TOKEN=YOUR_TOKEN",
    "cd your-repo",
    "echo REPLACE_ME",
    "echo CHANGEME",
    "git commit -m xxx",
    "echo XXX",
)

# Each line is a real shell form. Each one passes. The tag-shaped words sit in a heredoc body or in a quoted
# string, where the shell reads them as text.
ALLOW_LINES = (
    "cat > f <<'EOF'\nline one\nEOF",
    "sort < in.txt",
    "sudo e2fsck -f -D /dev/sda1 2>&1",
    "cd $HOME/repo",
    "echo ${VAR}",
    "GH_TOKEN=$(...) make test",
    "sudo e2fsck -f -D /dev/sda1",
    "grep -E 'a|b' notes.txt",
    "curl -s 'https://example.com/api?x=1'",
    "git log a..b",
    "instance-type xxxlarge",
    "cat > ~/Library/LaunchAgents/x.plist <<'EOF'\n<dict>\nEOF",
    "cat > /tmp/x.html <<'EOF'\n<html>\nEOF",
    "sed 's/<br>//g' page.html",
    "grep -o '<title>.*</title>' f",
)

# The same tokens in the `powershell` string, with a plain `mac` string beside them.
POWERSHELL_REFUSE = (
    "Set-Location your-repo",
    "$env:TOKEN = 'YOUR_TOKEN'",
    "Write-Output CHANGEME",
    "Remove-Item /dev/sdX1",
)


def task_with(mac, powershell="Write-Output ok"):
    return tqf.task_item([STEP], command={"powershell": powershell, "mac": mac})


def scoped(name, item):
    """P7: the command is a well-formed {powershell, mac} pair, so only the placeholder can decide the verdict."""
    cmd = item.get("command")
    well = (isinstance(cmd, dict) and set(cmd) == {"powershell", "mac"}
            and all(isinstance(v, str) and v.strip() for v in cmd.values()))
    check("scope: " + name + " has a well-formed command", well, repr(cmd))


def verdict(item):
    """("raised", text) when the check crashes, else ("hit", reason) or ("pass", "")."""
    try:
        reason = question_form.command_in_item_hit(item)
    except Exception as exc:  # a crash is no refusal, named
        return "raised", "%s: %s" % (type(exc).__name__, exc)
    return ("hit" if reason else "pass"), reason


def must_refuse(name, item):
    scoped(name, item)
    kind, detail = verdict(item)
    check("refused: " + name, kind == "hit", "want a refusal, got %s %r" % (kind, detail))


def allow(name, item):
    scoped(name, item)
    kind, detail = verdict(item)
    check("allowed: " + name, kind == "pass", "want no refusal, got %s %r" % (kind, detail))


def main():
    for token in REFUSE_TOKENS:
        must_refuse("mac " + token, task_with(token))
    for line in ALLOW_LINES:
        allow("mac " + line.splitlines()[0], task_with(line))
    for line in POWERSHELL_REFUSE:
        must_refuse("powershell " + line, task_with("git status", powershell=line))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
