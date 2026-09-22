# The Stop guardrail became a command hook

The `type: agent` Stop hook in `settings.json` judged every turn for a silent
change to a decision, gate, build-order, CLAUDE.md rule, or setting. It read
`transcript_path` through the permission system. An agent hook's own tool
calls go through it like any other.

## The measurement

Every session transcript on this machine since 2026-09-15 gave 34 real flags
and about 60 "Unable to verify" answers. The unverifiable answers track the
desktop app's `auto` permission mode. There, the transcript path sits outside
the working directory. A hook agent cannot prompt to cross that. In
`bypassPermissions`, where the hook works, it still spends a full model turn
on every Stop, whether or not anything protected changed.

Sorting the 34 real flags by hand gave five shapes. A gate or decision file
changed with no visible chat approval. A decision entry widened and
self-admitted in the assistant's own report. A direct write to `main`. A
security-guard file patched through a route the assistant itself called
evasive. And one case with no local file edit at all: a `SendMessage` telling
a peer session to delete a rule from a skill file.

## What replaced it

`hooks/decision_watch.py`, a command hook. A command hook takes the same
Stop JSON, `transcript_path`, `session_id`, `cwd`, with no permission check
at all. The `auto`-mode failure above cannot happen to it.

It answers the cheap part itself. `git status` against HEAD, scoped to this
turn by mtime the same way `lint/md_sweep.py` already does, gives the files
this turn touched. A broad keyword net over each path decides whether a file
looks protected, plus `guard.is_settings_file` for the one case with a real
constant to import.

When nothing on disk looks protected, the hook prints nothing and never
spawns a model. When something does, it runs `claude -p`, isolated. It
hands that call the diff, or the new file's text, and the chat text
directly. It asks for the same ALLOW/FLAG judgment the old prompt asked for.

## The judge subprocess, isolated and tightened across three review passes

The evidence handed to the model is this turn's diff and chat text. Both
are reachable by anyone who can land text in a diff or a message this
repo carries. A first version of `invoke_model` ran `claude -p` with no
restriction flag and no `cwd`. Every omitted flag defaults to every tool,
in this project's own directory, inheriting whatever `permissions.allow`
grants at the time. A reviewer found this. An injected instruction in a
diff could drive that nested, fully-tooled call to spend a granted
permission. It could then fold what it read into the `why` field this
hook prints back to the parent session. An injection and exfiltration
channel, inside the guard built to catch that exact class of thing.

**The tool flag.** A second pass asked whether `--allowedTools ""`
actually blocks every tool, rather than trusting the flag. `claude
--help` settled it without a live call: a separate flag, `--tools`,
documents `""` as disabling all tools. `--allowedTools`'s own help names
no such meaning for an empty value. A security control must not rest on
an undocumented parse. The hook now passes `--tools ""`, plus
`--safe-mode`, documented to disable every plugin, MCP server, hook,
skill, and custom command for the session. That closes the surface
`--tools` alone does not claim to cover.

**What a live call could still not confirm.** Asked to verify this by
watching the model's own behavior, not the flag, the call was run for
real. The prompt was built to use a tool if it could. It never reached
that question. Authentication failed first, with "OAuth session expired
and could not be refreshed". A bare `claude -p "Say hello"`, with no
restriction flags and the real config directory, gave the SAME failure.
`CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH=1` says the host refreshes tokens
for its own calls. A detached subprocess gets no such refresh. This
sandbox cannot show whether tools are blocked at runtime. It shows only
that a raw subprocess call cannot authenticate here at all. That result
is UNKNOWN, not PASS, and stays recorded as exactly that.

**What the same testing did confirm, and fix.** The first isolation
pointed `CLAUDE_CONFIG_DIR` at an empty directory. Run for real, that
failed with "Not logged in", a different and earlier failure than the
sandbox's own auth ceiling above. Proof, not assumption, that wiping the
config directory wipes the login credential too, on any machine. The
hook now copies only the credential file into the isolated directory.
The same test confirmed this moves the failure from "Not logged in" to
the sandbox's own "OAuth session expired" ceiling.

**The environment.** A third pass found the child process still
inherited this session's own environment, minus one overridden key.
That carried through the host IPC socket and token, the host session
id, the OAuth scope list, and an API key when one is set. Copying the
parent's environment and subtracting cannot be complete. That is the
same shape `decisions/predicate-is-the-act.md` names for a shape list.
The hook now builds the child's environment from a named allow list
instead. It holds only the handful of variables the runtime needs to
execute and reach the API host, and nothing else. A session that
authenticates by API key, rather than the credential file, now sees the
isolated call fail closed. That reads as an UNKNOWN, never silently
carried through.

**What remains.** `cwd` and `CLAUDE_CONFIG_DIR` both point at a fresh,
empty directory, never this project. There is no `.claude/settings.json`
there to inherit a permission from, and no `hooks/` wired to a Stop
event either. A nested call cannot fire this same hook at its own turn
end. The object a recursive call would need is not there to find.

## The `why` field is capped, cleaned, and attributed

A third pass also found the model's own `why` text printed straight into
the parent session's transcript. It carried no length cap and no
control-character stripping. It also carried no wording to tell a
reader the text came from the judge model reading attacker-influenced
content, not from this hook itself. The text is now bounded to 300
characters. It is cleaned the same way `hooks/guard.py`'s own printed
reasons are, and quoted as "the judge model reported" rather than
stated plainly.

## The gate, corrected against an independent audit

An earlier version of this hook also spawned a model call on an outbound
`SendMessage`/`Task` alone, with no matching disk change. That was meant to
catch the fifth flag shape above. An independent audit of all 34 historical
flags found that shape gave a false positive of its own. A peer was told to
act on something that had not run yet. Two more of the audit's three false
positives shared the same root cause. A role question, and a probe of a
scratch copy, neither one a write to the real protected path.

The gate now reads: an ACTUAL on-disk change to a protected path, full
stop. An outbound message can still enrich the evidence once a real change
already triggered the call. It cannot trigger the call by itself. Being
told to do something is not the act this hook exists to catch. Doing it is.

## The per-incident, per-session cap

The same audit found 34 raw flags collapsing to 8 real incidents. One
unresolved finding was re-flagged at every Stop while the owner had not yet
answered, ten times in one case. `decisions/guard-that-cries-wolf-is-
spent.md` names this shape. A guard that fires when nothing new is wrong is
spent.

`hooks/decision_watch.py` now hashes the protected paths plus their
evidence into one incident key. It persists seen keys per session under
`<config dir>/state/decision-watch/`, the same frozen `state` subtree
`hooks/config_watch.py` already uses. A finding already flagged this
session, with unchanged evidence, stays quiet at the next Stop. A finding
whose evidence moved further is a new incident, and is reported once more.
This cap never applies to an UNKNOWN read, which is always reported again.

## The time budget, proved rather than assumed

A reviewer also found the timeouts did not fit their own hook entry.
`settings.json` gave this hook 100 seconds. `GIT_TIMEOUT` (20) ran once for
`git status` and once per protected file for `git diff`, and `MODEL_TIMEOUT`
was 90. One protected file alone summed to 130 seconds. A harness kill at
100 prints nothing at all, which reads exactly like "nothing protected
changed," the failure this whole rewrite exists to prevent.

`GIT_TIMEOUT` is now 10 and `MODEL_TIMEOUT` is now 60. `MAX_DIFFED_FILES`
(8) bounds how many `git diff` calls one Stop spends. The sum then cannot
grow past a fixed number, no matter how many protected paths one turn
touches: 10 + 8 * 10 + 60 = 150 seconds. `settings.json`'s own entry for
this hook is now 170. That is twenty seconds of margin over the proved
sum, not zero.

## What stayed the same

The judgment criteria did not change. Additive or consistent is ALLOW.
Silently changed, weakened, removed, or reversed with no visible approval is
FLAG. Only how the judge receives its evidence changed, from a `Read` call
the model makes itself to a diff handed to it directly.

## What is still a triage filter, not a verdict

No code in this repository defines what a gate or a build-order file is, the
way `guard.is_settings_file` defines a settings file. The path/name net stays
a deliberately broad keyword match. A false positive there costs one model
call. A false negative skips judgment entirely, the worse of the two. It
decides whether to ask, never what the answer is.

## UNKNOWN, named on every failing read

Three reads can fail. `transcript_path` can be missing. `git` can be
unavailable or fail. The model subprocess can fail, time out, or answer
something other than the asked JSON verdict. Each one prints a
`systemMessage` that says UNKNOWN and names why. None of these collapse into
silence or into a flag. This is `CLAUDE.md`'s Verification rule, applied to
the hook's own failure branches.

## What this hook needs no permission for

A command hook never passes through the permission system. This hook needs
no `permissions.allow` entry at all to read `transcript_path` or to run
`git`. A separate `Read(~/.claude/projects/**)` grant, if the owner adds
one, is not for this hook: see the standalone entry that proposes it.

## The mechanism

`hooks/decision_watch.py`, tested by `hooks/test_decision_watch.py`.
`lint/rule_mechanisms.json`'s `roles-orchestrator-never-builds` entry names
it in place of the old agent hook.
