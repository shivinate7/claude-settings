# The Stop guardrail became a command hook

## The ruling

The `type: agent` Stop hook is out of `settings.json`. It read `transcript_path` through the permission
system, and in the desktop app's `auto` permission mode the sandbox denied it `Read` and `Bash`. It then
blocked with "unable to verify", which cost a turn and resolved nothing. The owner approved this disarm
on 2026-09-22.

`hooks/decision_watch.py`, a command hook, replaces it. A command hook takes the same Stop JSON
(`transcript_path`, `session_id`, `cwd`) with no permission check, so the `auto`-mode failure cannot
happen to it. It needs no `permissions.allow` entry to read `transcript_path` or to run `git`. The mod
`mods/decision-watch` runs the script on every Stop and makes the model call itself
(`decision-watch-mod-limits`). No `settings.json` Stop row runs the script. A direct run of the script
with no split flag runs `claude -p`, isolated, as below.

**The gate is an ACTUAL on-disk change to a protected path.** `git status` against HEAD, scoped to this
turn by mtime the way `lint/md_sweep.py` does it, gives the files this turn touched. A broad keyword net
over each path decides whether a file looks protected, plus `guard.is_settings_file` for the one case
with a real constant to import. When nothing on disk looks protected, the hook prints nothing and never
spawns a model. When something does, the judge gets the diff, or the new file's text, and the chat text
directly. An outbound `SendMessage` or `Task` can enrich the evidence once a real change triggered the
call. It cannot trigger the call by itself, because being told to do something is not the act the hook
exists to catch. Doing it is.

**Judgment criteria.** Additive or consistent is ALLOW. Silently changed, weakened, removed, or reversed
with no visible approval is FLAG.

**Triage filter, not a verdict.** No code defines what a gate or a build-order file is. The path/name net
stays a deliberately broad keyword match. A false positive costs one model call. A false negative skips
judgment, the worse of the two. It decides whether to ask, never what the answer is.

**The judge subprocess is isolated.** The evidence is this turn's diff and chat text, which anyone who
can land text in a diff or a message can reach. An injected instruction must not drive a tooled call.

- `invoke_model` passes `--tools ""` (documented to disable all tools) and `--safe-mode` (documented to
  disable every plugin, MCP server, hook, skill and custom command). `--allowedTools ""` has no such
  documented meaning, so the control does not rest on it.
- `cwd` and `CLAUDE_CONFIG_DIR` both point at a fresh, empty directory, never this project. There is no
  `.claude/settings.json` to inherit a permission from and no `hooks/` wired to a Stop event, so a nested
  call cannot fire this hook at its own turn end.
- Only the credential file is copied into that directory, because an empty config directory fails with
  "Not logged in".
- The child's environment is built from a named allow list: the few variables the runtime needs to
  execute and reach the API host, and nothing else. Subtracting from the parent's environment cannot be
  complete (`predicate-is-the-act`). A session that authenticates by API key sees the isolated call fail
  closed, as UNKNOWN.
- Runtime blocking of tools is UNKNOWN, not PASS: a raw subprocess in the sandbox cannot authenticate.

**The `why` field is capped, cleaned, and attributed.** The model's `why` text is bounded to 300
characters, cleaned the way `hooks/guard.py`'s own printed reasons are, and quoted as "the judge model
reported" rather than stated plainly.

**Per-incident, per-session cap.** `hooks/decision_watch.py` hashes the protected paths plus their
evidence into one incident key. It persists seen keys per session under `<config dir>/state/decision-watch/`,
the frozen `state` subtree `hooks/config_watch.py` also uses. A finding already flagged this session,
with unchanged evidence, stays quiet at the next Stop. A finding whose evidence moved further is a new
incident and is reported once more. The cap never applies to an UNKNOWN read, which is always reported
again (`guard-that-cries-wolf-is-spent`).

**The time budget is bounded by code.** A harness kill prints nothing, which reads like "nothing
protected changed". `GIT_TIMEOUT` caps each git call. `MAX_DIFFED_FILES` caps the `git diff` calls one
Stop spends, so the sum cannot grow with the number of protected paths one turn touches. The mod caps
each python run and its model call with its own timers. A timeout reads as UNKNOWN, never ALLOW. The
numbers live in the script's "THE TIME BUDGET" comment and in `mods/decision-watch/hooks/register.mjs`.

**UNKNOWN, named on every failing read.** `transcript_path` can be missing. `git` can be unavailable or
fail. The model subprocess can fail, time out, or answer something other than the asked JSON verdict.
Each one prints a `systemMessage` that says UNKNOWN and names why. None collapses into silence or into a flag.

Tests: `hooks/test_decision_watch.py`, and `mods/decision-watch/decision-watch.test.mjs` for the mod.
`lint/rule_mechanisms.json`'s `roles-orchestrator-never-builds` entry names the script in place of the old agent hook.

Kind: process
Home: hooks/decision_watch.py
