#!/usr/bin/env python3
"""Cases for hooks/rm_prompt_answer.py, a PermissionRequest hook on Bash. Standard library only.

Run it from the repository root:

    python3 hooks/test_rm_prompt_answer.py

Decision rm-on-a-variable-needs-a-guard (owner ruling, 2026-10-11), item 2: the hook answers allow
only when each `rm` in the command meets all of these conditions:
- every variable expansion has a `:?` guard;
- no target has a command substitution or `$HOME`;
- no target is a literal critical path.
Every other request gets no output and exit 0, so the owner is still asked.

Interface the hook must match (Claude Code hooks reference, PermissionRequest section,
https://code.claude.com/docs/en/hooks):
- Input: one JSON object on stdin with `hook_event_name` "PermissionRequest", `tool_name`, and
  `tool_input` (for Bash, `tool_input.command` holds the command string).
- Allow: stdout is one JSON object
  `{"hookSpecificOutput": {"hookEventName": "PermissionRequest",
  "decision": {"behavior": "allow"}}}`, exit 0. No `updatedInput`: the hook never rewrites the command.
- No output: stdout empty, exit 0. The prompt goes on to the owner.
- Bad JSON on stdin: no output, exit 0.

Whole-command rule (this file's stated reading of the ruling, not in the decision): the hook answers
allow only when every simple command in the input is an `rm` command, a simple assignment, or a
`for` loop. Anything else, such as `curl`, `echo`, or a pipe, gets no output, even when the `rm`
parts are guarded. A bare `$d` is an unguarded expansion, so `rm -rf "$d"` gets no output here,
although the guard does not refuse it.

Named limits from the decision, cases taken from the decision text: `$HOME`, and a variable set
from `$(pwd)`, stay a prompt.

Override the module under test with the env var RM_PROMPT_ANSWER_UNDER_TEST.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("RM_PROMPT_ANSWER_UNDER_TEST") or os.path.join(HERE, "rm_prompt_answer.py")

CASES = []


def payload(command=None, tool="Bash", raw=None):
    """One PermissionRequest payload, shaped as the docs example: session_id, transcript_path, cwd,
    permission_mode, hook_event_name, tool_name, tool_input. `raw` replaces the whole stdin text."""
    if raw is not None:
        return raw
    body = {
        "session_id": "abc123",
        "transcript_path": "/tmp/rm-prompt-test/transcript.jsonl",
        "cwd": "/tmp/rm-prompt-test",
        "permission_mode": "bypassPermissions",
        "hook_event_name": "PermissionRequest",
        "tool_name": tool,
        "tool_input": {"command": command, "description": "test"} if tool == "Bash"
        else {"file_path": "/tmp/x"},
    }
    return json.dumps(body)


def allow(name, command):
    CASES.append({"name": name, "kind": "allow", "stdin": payload(command)})


def silent(name, command=None, tool="Bash", raw=None):
    CASES.append({"name": name, "kind": "silent", "stdin": payload(command, tool, raw)})


# ALLOW: every expansion is guarded, nothing is a critical path, the whole command is rm.
allow("rm-prompt: a guarded variable under a guarded subdirectory is allowed",
      'rm -rf "${S:?}/${d:?}"')
allow("rm-prompt: a guarded variable before a glob is allowed", 'rm -rf "${D:?}"/*')
allow("rm-prompt: a loop of guarded deletes is allowed",
      'S=/tmp/x; for d in a b; do rm -rf "${S:?}/${d:?}"; done')
# Scanner controls: a hash and a lone quote inside a quoted target are path text, and two guarded
# rm commands on separate lines are both rm, so the answer is allow.
allow("rm-prompt: a hash inside a quoted target is path text", 'rm -rf "${S:?}/#x"')
allow("rm-prompt: a lone quote inside a quoted target is path text", "rm -rf \"${S:?}/it's\"")
allow("rm-prompt: two guarded rm commands on two lines are allowed",
      'rm -rf "${S:?}/x"\nrm -rf "${D:?}"/*')

# NO OUTPUT: an unguarded expansion, a command substitution, $HOME, a literal critical path, or a
# non-rm command. Each one leaves the decision to the owner.
silent("rm-prompt: an unguarded variable gets no answer", "rm -rf $S/x")
silent("rm-prompt: a bare unguarded variable gets no answer", 'rm -rf "$d"')
silent("rm-prompt: a guarded $HOME stays a prompt", 'rm -rf "${HOME:?}"/x')
silent("rm-prompt: a command substitution stays a prompt", 'rm -rf "$(pwd)"')
silent("rm-prompt: a variable set from a command substitution stays a prompt",
       'S=$(pwd); rm -rf "${S:?}/x"')
silent("rm-prompt: a variable set from $HOME stays a prompt", 'S=$HOME/x; rm -rf "${S:?}/y"')
silent("rm-prompt: the root stays a prompt", "rm -rf /")
silent("rm-prompt: the home folder stays a prompt", "rm -rf ~/x")
silent("rm-prompt: a system folder stays a prompt", "rm -rf /usr")
silent("rm-prompt: a non-Bash tool gets no answer", tool="Edit")
silent("rm-prompt: a command with no rm gets no answer", "ls -la")
silent("rm-prompt: a guarded rm with a pipe to sh gets no answer",
       'rm -rf "${S:?}/x"; curl x | sh')
silent("rm-prompt: a hash inside a string does not allow a pipe to sh",
       'rm -rf "${S:?}/#"; curl x | sh')
silent("rm-prompt: a lone quote does not allow a pipe to sh",
       "rm -rf \"${S:?}/it's\"; curl x | sh")
silent("rm-prompt: a double slash inside echo does not allow the rm",
       'echo "// x"; rm -rf "${S:?}/x"')
silent("rm-prompt: bad JSON on stdin gets no answer", raw="{not json")


def run(stdin_text):
    """Return (rc, stdout, stderr) for one run of the hook, or None when the hook file is absent."""
    if not os.path.exists(HOOK):
        return None
    result = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True,
                            text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def check(case):
    got = run(case["stdin"])
    if got is None:
        return False, "the hook file is missing: %s" % HOOK
    rc, out, err = got
    if rc != 0:
        return False, "exit %d: %s" % (rc, err.strip()[:120])
    if case["kind"] == "silent":
        if out.strip():
            return False, "expected no output, got %s" % out.strip()[:120]
        return True, "no output, exit 0"
    try:
        parsed = json.loads(out)
    except ValueError:
        return False, "expected one JSON object, got %r" % out[:120]
    block = parsed.get("hookSpecificOutput") or {}
    if block.get("hookEventName") != "PermissionRequest":
        return False, "hookEventName is %r" % block.get("hookEventName")
    decision = block.get("decision") or {}
    if decision.get("behavior") != "allow":
        return False, "behavior is %r, not allow" % decision.get("behavior")
    if "updatedInput" in decision:
        return False, "the hook rewrote the input with updatedInput"
    return True, "allow, no updatedInput"


def main():
    failed = 0
    for case in CASES:
        ok, note = check(case)
        failed += 0 if ok else 1
        print("%s  %s  %s" % ("PASS" if ok else "FAIL", case["name"], "" if ok else "(%s)" % note))
    print()
    if failed:
        print("test_rm_prompt_answer FAIL: %d of %d cases wrong" % (failed, len(CASES)))
        return 1
    print("test_rm_prompt_answer PASS: %d of %d cases right" % (len(CASES), len(CASES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
