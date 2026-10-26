# The Stop guardrail became a command hook

## The ruling

The Stop guardrail is never a `type: agent` hook. Reason: an agent hook reads `transcript_path` through
the permission system. In the desktop app's `auto` permission mode the sandbox denied it `Read` and
`Bash`, and it blocked with "unable to verify", which cost a turn and resolved nothing. Its judge is the
script `hooks/decision_watch.py`, which takes the same Stop JSON with no permission check. The mod
`mods/decision-watch` runs the script on every Stop and makes the model call itself
(`decision-watch-mod-limits`). A direct run of the script with no split flag runs `claude -p`, isolated,
as below.

- **The gate is an ACTUAL on-disk change to a protected path.** `git status` against HEAD, scoped to this
  turn by mtime, gives the files this turn touched. A broad keyword net
  over each path decides whether a file looks protected, plus `guard.is_settings_file`. When nothing
  looks protected, the hook prints nothing and never spawns a model. Otherwise the judge gets the diff, or
  the new file's text, and the chat text. An outbound `SendMessage` or `Task` can enrich the evidence once
  a real change triggered the call. It cannot trigger the call by itself, because being told to do
  something is not the act the hook exists to catch. Doing it is.
- **Criteria.** Additive or consistent is ALLOW. Silently changed, weakened, removed, or reversed with no
  visible approval is FLAG.
- **The keyword net is triage, not a verdict.** A false positive costs one model call. A false negative
  skips judgment, the worse of the two. So the net stays broad. It decides whether to ask, never what the
  answer is.
- **The judge subprocess is isolated.** Anyone who can land text in a diff or a message can reach the
  evidence, and an injected instruction must not drive a tooled call. `invoke_model` passes `--tools ""`
  and `--safe-mode`. `cwd` and `CLAUDE_CONFIG_DIR` both point at a fresh, empty directory, never this
  project, with only the credential file copied in. So a nested call inherits no permission and cannot
  fire this hook at its own turn end. The child's environment is built from a named allow list, never by
  subtracting from the parent's (`predicate-is-the-act`). A session that authenticates by API key sees
  the isolated call fail closed, as UNKNOWN.
- **The `why` field is capped, cleaned, and attributed.** It is bounded to 300 characters, cleaned the way
  the guard's own printed reasons are, and quoted as "the judge model reported" rather than stated
  plainly.
- **Per-incident, per-session cap.** A finding already flagged this session, with unchanged evidence,
  stays quiet at the next Stop. A finding whose evidence moved further is a new incident and is reported
  once more. The cap never applies to an UNKNOWN read, which is always reported again
  (`guard-that-cries-wolf-is-spent`).
- **UNKNOWN, never silence.** A harness kill prints nothing, and silence reads as no change. So a timeout,
  a missing `transcript_path`, a git failure, and a model failure or odd answer each print a
  `systemMessage` that says UNKNOWN and names why. None collapses into silence, into ALLOW or into a flag.

Measured 2026-09-22 over every session transcript on this machine since 2026-09-15: the agent hook gave
34 real flags and about 60 "Unable to verify" answers, which track the `auto` permission mode. The 34
flags were 8 real incidents; one unresolved finding was re-flagged at ten Stops. An outbound
`SendMessage` or `Task` with no disk change also gave false positives, so the gate keys on the disk.

Kind: process
Home: hooks/decision_watch.py
