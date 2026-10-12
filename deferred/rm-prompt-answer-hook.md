# A hook that answers the critical-path rm prompt

**What waits.** A `PermissionRequest` hook on Bash that answers allow for an `rm` prompt that
the `rm-var-unguarded` guard does not prevent. The owner chose "Ship guard now, hook later" on
2026-10-11. See decision rm-on-a-variable-needs-a-guard.

**What it must do.** It answers allow only when all of these hold:

- the session is in bypass mode;
- each target is a `${NAME:?}` expansion plus plain folder names;
- no target has `..`, a glob, braces, `~`, `$HOME`, `$PWD`, or a command substitution;
- the value set to each variable in the command is not a critical path.

Every other request goes on to the owner unchanged.

**Why it waits.** The first build (commit 18fddf9 on branch rm-var-guard) allowed
`rm -rf /Users/<you>`, `rm -rf *`, `rm -rf {~,x}` and `"${S:?}"/../..`, in every mode. Its
first test file is at commit 7ea6b65. Add the four inputs above as red tests before the
rebuild.
