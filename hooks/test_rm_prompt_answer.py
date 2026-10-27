#!/usr/bin/env python3
"""Cases for hooks/rm_prompt_answer.py, a PermissionRequest hook on Bash. Standard library only.

Run it from the repository root:

    python3 hooks/test_rm_prompt_answer.py

Contract, from decision rm-on-a-variable-needs-a-guard (rm on a variable path needs a `:?` guard).
The hook answers allow ONLY when all of these hold:
- the hook input has `permission_mode` == "bypassPermissions";
- each `rm` target is a `${NAME:?}` expansion followed only by plain folder names (`/a/b`): no
  `..`, no glob, no braces, no `~`, no `$HOME`, no `$PWD`, no command substitution, no second
  expansion;
- each such variable is assigned in the same command, and no value assigned to it is a critical
  path: `/`, the home folder, the cwd, or a parent of the cwd (the existing reading is
  `_rm_target_bad` in hooks/guard.py). The value is judged, not the joined path.
Every other request gets no output and exit 0, so the owner is still asked.

Interface (Claude Code hooks reference, https://code.claude.com/docs/en/hooks):
- Input: one JSON object on stdin. Common fields include `session_id`, `transcript_path`, `cwd`,
  `permission_mode` ("default", "plan", "acceptEdits", "auto", "dontAsk", "bypassPermissions"),
  `hook_event_name` "PermissionRequest", `tool_name`, and `tool_input` (`tool_input.command` for
  Bash). The docs name the mode field `permission_mode`.
- Allow: stdout is one JSON object
  `{"hookSpecificOutput": {"hookEventName": "PermissionRequest",
  "decision": {"behavior": "allow"}}}`, exit 0. No `updatedInput`: the hook never rewrites the command.
- No decision: the docs show no example. This file pins stdout empty and exit 0.
- Bad JSON on stdin: no output, exit 0.

Whole-command rule (a stated reading, not in the decision): the hook
answers allow only when every simple command in the input is an `rm` command or a simple
assignment. Anything else, such as `curl`, `echo`, a pipe, or a `for` loop, gets no output.
An `rm` target variable with no assignment in the command is unverifiable and gets no output.

Override the module under test with the env var RM_PROMPT_ANSWER_UNDER_TEST.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("RM_PROMPT_ANSWER_UNDER_TEST") or os.path.join(HERE, "rm_prompt_answer.py")

CWD = "/tmp/rm-prompt-test"
HOME = "/home/rm-test-home"  # the hook runs with HOME and USERPROFILE set to this
BYPASS = "bypassPermissions"

CASES = []


def payload(command=None, tool="Bash", raw=None, mode=BYPASS):
    """One PermissionRequest payload, shaped as the docs: session_id, transcript_path, cwd,
    permission_mode, hook_event_name, tool_name, tool_input. `raw` replaces the whole stdin text.
    `mode` None leaves permission_mode out."""
    if raw is not None:
        return raw
    body = {
        "session_id": "abc123",
        "transcript_path": "/tmp/rm-prompt-test/transcript.jsonl",
        "cwd": CWD,
        "hook_event_name": "PermissionRequest",
        "tool_name": tool,
        "tool_input": {"command": command, "description": "test"} if tool == "Bash"
        else {"file_path": "/tmp/x"},
    }
    if mode is not None:
        body["permission_mode"] = mode
    return json.dumps(body)


def allow(name, command, mode=BYPASS, real_home=False):
    CASES.append({"name": name, "kind": "allow", "stdin": payload(command, mode=mode),
                  "real_home": real_home})


def silent(name, command=None, tool="Bash", raw=None, mode=BYPASS, real_home=False):
    CASES.append({"name": name, "kind": "silent", "stdin": payload(command, tool, raw, mode),
                  "real_home": real_home})


# ALLOW: bypass mode, each target is a guarded variable plus plain folders, each value is bound
# in the command and is not a critical path, the whole command is assignments and rm.
allow("rm-prompt: bypass, a bound guarded variable plus a folder is allowed",
      'S=/tmp/x; rm -rf "${S:?}"/build')
allow("rm-prompt: bypass, the folder inside the quotes is allowed",
      'S=/tmp/x; rm -rf "${S:?}/build"')
allow("rm-prompt: bypass, a deeper plain path is allowed", 'S=/tmp/x; rm -rf "${S:?}"/a/b/c')
allow("rm-prompt: bypass, the bare guarded variable alone is allowed", 'S=/tmp/x; rm -rf "${S:?}"')
allow("rm-prompt: bypass, rm -r -f and rm -fr are allowed",
      'S=/tmp/x; rm -r -f "${S:?}"/a; rm -fr "${S:?}"/b')
allow("rm-prompt: bypass, two targets with two bound variables are allowed",
      'S=/tmp/x; T=/tmp/y; rm -rf "${S:?}"/a "${T:?}"/b')
allow("rm-prompt: bypass, a folder under the home folder is allowed",
      'S=%s/proj; rm -rf "${S:?}"/build' % HOME)
# Scanner controls: a hash and a lone quote inside a quoted value or target are path text, and
# two guarded rm commands on separate lines are both rm.
allow("rm-prompt: bypass, a hash inside a quoted value is path text",
      'S="/tmp/#x"; rm -rf "${S:?}"/y')
allow("rm-prompt: bypass, a hash inside a quoted target is path text",
      'S=/tmp/x; rm -rf "${S:?}/#x"')
allow("rm-prompt: bypass, a lone quote inside a quoted target is path text",
      "S=/tmp/x; rm -rf \"${S:?}/it's\"")
allow("rm-prompt: bypass, two guarded rm commands on two lines are allowed",
      'S=/tmp/x\nrm -rf "${S:?}/x"\nrm -rf "${S:?}/y"')

# PASS THROUGH, mode: the same good form is not answered outside bypass mode.
GOOD = 'S=/tmp/x; rm -rf "${S:?}"/build'
for _mode in ("default", "plan", "acceptEdits", "auto", "dontAsk", "", "bogus", None):
    silent("rm-prompt: good form in mode %r gets no answer" % (_mode,), GOOD, mode=_mode)
silent("rm-prompt: a non-string permission_mode gets no answer", GOOD, mode=["bypassPermissions"])
silent("rm-prompt: a non-Bash tool in bypass mode gets no answer", tool="Edit")
silent("rm-prompt: a command with no rm gets no answer", "ls -la")
silent("rm-prompt: bad JSON on stdin gets no answer", raw="{not json")
silent("rm-prompt: an empty stdin gets no answer", raw="")

# PASS THROUGH, the four inputs the first build allowed in every mode (bypass mode here).
silent("rm-prompt: bypass, rm of /Users/<name> is not allowed", "rm -rf /Users/alice")
silent("rm-prompt: bypass, rm of /home/<name> is not allowed", "rm -rf /home/alice")
silent("rm-prompt: bypass, rm of * is not allowed", "rm -rf *")
silent("rm-prompt: bypass, rm of {~,x} is not allowed", "rm -rf {~,x}")
silent("rm-prompt: bypass, a guarded variable plus /../.. is not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/../..')
silent("rm-prompt: bypass, an unbound guarded variable plus /../.. is not allowed",
       'rm -rf "${S:?}"/../..')
silent("rm-prompt: bypass, the root stays a prompt", "rm -rf /")
silent("rm-prompt: bypass, the home folder stays a prompt", "rm -rf ~/x")
silent("rm-prompt: bypass, a system folder stays a prompt", "rm -rf /usr")

# PASS THROUGH, the value of the variable is a critical path (or not a known literal).
silent("rm-prompt: bypass, S=/ is not allowed", 'S=/; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, a quoted S=/ is not allowed", 'S="/"; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S=$HOME is not allowed", 'S=$HOME; rm -rf "${S:?}"')
silent("rm-prompt: bypass, S=${HOME} is not allowed", 'S="${HOME}"; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S=~ is not allowed", 'S=~; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S=$HOME/x is not allowed", 'S=$HOME/x; rm -rf "${S:?}/y"')
silent("rm-prompt: bypass, S set to the home folder is not allowed",
       'S=%s; rm -rf "${S:?}"/x' % HOME)
silent("rm-prompt: bypass, S set to the parent of the home folder is not allowed",
       'S=/home; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S set to the cwd is not allowed",
       'S=%s; rm -rf "${S:?}"/x' % CWD)
silent("rm-prompt: bypass, S set to a parent of the cwd is not allowed",
       'S=/tmp; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S set to a value that resolves to a parent of the cwd is not allowed",
       'S=/tmp/x/..; rm -rf "${S:?}"/y')
silent("rm-prompt: bypass, S=. is not allowed", 'S=.; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S=.. is not allowed", 'S=..; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S=$PWD is not allowed", 'S=$PWD; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S=$(pwd) is not allowed", 'S=$(pwd); rm -rf "${S:?}/x"')
silent("rm-prompt: bypass, S set from backticks is not allowed", 'S=`pwd`; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S set from another variable is not allowed",
       'S=$OTHER; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S with a glob in its value is not allowed",
       'S=/tmp/*; rm -rf "${S:?}"/x')
silent("rm-prompt: bypass, S reassigned to / later is not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/a; S=/; rm -rf "${S:?}"/b')
silent("rm-prompt: bypass, an unbound guarded variable is not allowed", 'rm -rf "${S:?}"/build')
silent("rm-prompt: bypass, a variable bound to the wrong name is not allowed",
       'T=/tmp/x; rm -rf "${S:?}"/build')
# An assignment to a name that no rm target uses changes how the shell runs the rm
# (IFS splits an unquoted expansion, PATH picks another rm, CDPATH, any stray binding), so it
# stops the allow. The allow cases are the controls: every binding is used by a target.
silent("rm-prompt: bypass, IFS=: splits S into two targets, one the home folder",
       'IFS=:; S=%s:/tmp/x; rm -rf ${S:?}/y' % HOME)
silent("rm-prompt: bypass, IFS=x turns /tmp/x/a into /tmp/ and /a",
       'IFS=x; S=/tmp/x; rm -rf ${S:?}/a')
silent("rm-prompt: bypass, export IFS=: before the split is not allowed",
       'export IFS=:; S=%s:/tmp/x; rm -rf ${S:?}/y' % HOME)
silent("rm-prompt: bypass, export IFS=x before the split is not allowed",
       'export IFS=x; S=/tmp/x; rm -rf ${S:?}/a')
silent("rm-prompt: bypass, IFS=: with a quoted target is not allowed",
       'IFS=:; S=/tmp/x; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, PATH set to another folder is not allowed",
       'PATH=/tmp/evil; S=/tmp/x; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, CDPATH set is not allowed",
       'CDPATH=/; S=/tmp/x; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, a stray safe-looking binding no target uses is not allowed",
       'T=/; S=/tmp/x; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, CDPATH set to a plain folder is not allowed",
       'CDPATH=/tmp/c; S=/tmp/x; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, a stray plain-folder binding no target uses is not allowed",
       'T=/tmp/y; S=/tmp/x; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, a stray binding set after the rm is not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/a; T=/tmp/y')
# IFS and PATH are refused by name, even when a target expands the name that was bound.
silent("rm-prompt: bypass, IFS bound and expanded unquoted is not allowed",
       'IFS=t; rm -rf ${IFS:?}/home')
silent("rm-prompt: bypass, IFS bound and expanded quoted is not allowed",
       'IFS=t; rm -rf "${IFS:?}"/home')
silent("rm-prompt: bypass, PATH bound and expanded unquoted is not allowed",
       'PATH=/tmp/x; rm -rf ${PATH:?}/a')
silent("rm-prompt: bypass, PATH bound and expanded quoted is not allowed",
       'PATH=/tmp/x; rm -rf "${PATH:?}"/a')
allow("rm-prompt: bypass, control: one binding used by its target is allowed",
      'S=/tmp/x; rm -rf "${S:?}"/a')
allow("rm-prompt: bypass, control: two bindings, each used by a target, are allowed",
      'S=/tmp/x; D=/tmp/y; rm -rf "${S:?}"/a "${D:?}"/b')
# Scanner controls: a hash that opens a real comment hides a fake assignment; a hash inside a
# string does not hide the real one.
silent("rm-prompt: bypass, a comment holding a safe assignment does not bind S",
       'S=/; rm -rf "${S:?}"/x # S=/tmp/ok')
silent("rm-prompt: bypass, a hash inside a string does not hide S=/",
       'S="/#"; S=/; rm -rf "${S:?}"/x')

# PASS THROUGH, the target after the guarded variable is not plain folder names.
silent("rm-prompt: bypass, a .. in the middle is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/a/../b')
silent("rm-prompt: bypass, a trailing .. is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/a/..')
silent("rm-prompt: bypass, braces are not allowed", 'S=/tmp/x; rm -rf "${S:?}"/{a,b}')
silent("rm-prompt: bypass, a * glob is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/*')
silent("rm-prompt: bypass, a ? glob is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/a?')
silent("rm-prompt: bypass, a [..] glob is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/[ab]')
silent("rm-prompt: bypass, a ~ is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/~')
silent("rm-prompt: bypass, $HOME in the target is not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/$HOME')
silent("rm-prompt: bypass, $PWD in the target is not allowed", 'S=/tmp/x; rm -rf "${S:?}"/$PWD')
silent("rm-prompt: bypass, a command substitution in the target is not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/$(pwd)')
silent("rm-prompt: bypass, backticks in the target are not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/`pwd`')
silent("rm-prompt: bypass, a second guarded expansion in the target is not allowed",
       'S=/tmp/x; d=a; rm -rf "${S:?}/${d:?}"')
silent("rm-prompt: bypass, an unguarded second expansion is not allowed",
       'S=/tmp/x; rm -rf "${S:?}"/$d')
silent("rm-prompt: bypass, an unguarded variable is not allowed", 'S=/tmp/x; rm -rf $S/x')
silent("rm-prompt: bypass, a bare quoted variable is not allowed", 'S=/tmp/x; rm -rf "$S"/x')
silent("rm-prompt: bypass, a braced variable with no :? guard is not allowed",
       'S=/tmp/x; rm -rf "${S}"/x')
silent("rm-prompt: bypass, a :- default is not a guard", 'S=/tmp/x; rm -rf "${S:-/}"/x')
silent("rm-prompt: bypass, a guarded $HOME stays a prompt", 'rm -rf "${HOME:?}"/x')
silent("rm-prompt: bypass, a command substitution target stays a prompt", 'rm -rf "$(pwd)"')
silent("rm-prompt: bypass, a literal folder with no variable is not allowed",
       "rm -rf /tmp/x/build")

# PASS THROUGH, several commands in one request: one bad part stops the allow.
silent("rm-prompt: bypass, two rm calls, the second goes to ../..",
       'S=/tmp/x; rm -rf "${S:?}"/a; rm -rf "${S:?}"/../..')
silent("rm-prompt: bypass, two rm calls, the first goes to ../..",
       'S=/tmp/x; rm -rf "${S:?}"/../..; rm -rf "${S:?}"/a')
silent("rm-prompt: bypass, two rm calls joined by &&, the second is a *",
       'S=/tmp/x; rm -rf "${S:?}"/a && rm -rf *')
silent("rm-prompt: bypass, two rm calls on two lines, the second is a system folder",
       'S=/tmp/x\nrm -rf "${S:?}"/a\nrm -rf /usr')
silent("rm-prompt: bypass, two rm calls, the second is a brace glob",
       'S=/tmp/x; rm -rf "${S:?}"/a; rm -rf "${S:?}"/{a,b}')
silent("rm-prompt: bypass, one rm call with one good and one bad target",
       'S=/tmp/x; rm -rf "${S:?}"/a ~/x')
silent("rm-prompt: bypass, a multi-line quoted value hides no bad second rm",
       'S="/tmp/x\n# y"; rm -rf "${S:?}"/a; rm -rf ~/y')

# PASS THROUGH, whole-command rule: a non-rm command in the request.
silent("rm-prompt: bypass, a good rm with a pipe to sh gets no answer",
       'S=/tmp/x; rm -rf "${S:?}/x"; curl x | sh')
silent("rm-prompt: bypass, a hash inside a string does not allow a pipe to sh",
       'S=/tmp/x; rm -rf "${S:?}/#"; curl x | sh')
silent("rm-prompt: bypass, a lone quote does not allow a pipe to sh",
       "S=/tmp/x; rm -rf \"${S:?}/it's\"; curl x | sh")
silent("rm-prompt: bypass, a double slash inside echo does not allow the rm",
       'S=/tmp/x; echo "// x"; rm -rf "${S:?}/x"')
silent("rm-prompt: bypass, a loop with a guarded rm stays a prompt",
       'S=/tmp/x; for d in a b; do rm -rf "${S:?}"/a; done')


# WINDOWS ONLY: a Git Bash drive spelling (/c/Users/<name>) names the real folder C:/Users/<name>.
# The hook runs with the real home for these cases, so the spelling can match it.
if os.name == "nt":
    _real = os.path.expanduser("~")
    GB_HOME = "/" + _real[0].lower() + _real[2:].replace("\\", "/")
    silent("rm-prompt: bypass, S=/c/Users/<home> in Git Bash spelling is not allowed",
           'S=%s; rm -rf "${S:?}"' % GB_HOME, real_home=True)
    silent("rm-prompt: bypass, S=/c, the drive root in Git Bash spelling, is not allowed",
           'S=/%s; rm -rf "${S:?}"/x' % _real[0].lower(), real_home=True)
    allow("rm-prompt: bypass, a child of /c/Users/<home> in Git Bash spelling is allowed",
          'S=%s/rm-test-child; rm -rf "${S:?}"' % GB_HOME, real_home=True)


# The remedy of rule rm-after-cd (`cd "$S" && rm -rf dl`) gets the auto-allow. Its glob form does not.
allow("the rm-after-cd remedy, a plain target", 'S=/tmp/w; rm -rf "${S:?}"/dl')
silent("the rm-after-cd remedy, a glob target", 'S=/tmp/w; rm -rf "${S:?}"/dl/*')


def run(stdin_text, real_home=False):
    """Return (rc, stdout, stderr) for one run of the hook, or None when the hook file is absent."""
    if not os.path.exists(HOOK):
        return None
    env = os.environ.copy() if real_home else dict(os.environ, HOME=HOME, USERPROFILE=HOME)
    result = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True,
                            text=True, timeout=30, env=env)
    return result.returncode, result.stdout, result.stderr


def check(case):
    got = run(case["stdin"], case.get("real_home", False))
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
