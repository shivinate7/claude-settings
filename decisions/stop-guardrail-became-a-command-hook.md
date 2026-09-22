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
constant to import. The same net runs over this turn's outbound
`SendMessage`/`Task` calls. That is how the fifth flag shape stays caught
with no file edit at all.

When nothing looks protected, the hook prints nothing and never spawns a
model. When something does, it runs `claude -p` with no tools. It hands
that call the diff, or the new file's text, and the chat text directly.
It asks for the same ALLOW/FLAG judgment the old prompt asked for.

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

## What this leaves thin

`permissions.allow` in `settings.json` now also carries
`Read(~/.claude/projects/**)`. That entry exists mainly for the interim, and
for any future `type: agent` hook that still needs it. A command hook never
passes through the permission system. So this hook needs no permission at
all to read `transcript_path`. The allow rule is not load-bearing for this
hook's own operation.

## The mechanism

`hooks/decision_watch.py`, tested by `hooks/test_decision_watch.py`.
`lint/rule_mechanisms.json`'s `roles-orchestrator-never-builds` entry names
it in place of the old agent hook.
