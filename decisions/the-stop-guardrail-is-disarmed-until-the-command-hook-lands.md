# The Stop guardrail is disarmed until the command hook lands

The `Stop` hook entry of `type: "agent"` is removed from `settings.json`. Its
prompt started "You are a guardrail reviewing the turn that just ended". This
entry records why, what the disarm costs, and what re-arms it.

## The defect

The hook is an agent. It reads the turn's transcript to judge whether a
decision, gate, build order, `CLAUDE.md` rule, or settings file changed
without approval. To read that transcript, it must open a file outside its
own working directory. An agent hook cannot prompt for an out-of-cwd read. In
a sandboxed session, that read needs a permission the hook has no way to ask
for.

MEASURED across 1,500 session transcripts: the hook blocked 80 times. 55 of
those 80, 69 percent, were the hook reporting it could not check anything at
all, because the sandbox denied it `Read` and `Bash`. Each cost a turn and
resolved nothing. The worst run held six consecutive blocks in one turn, none
resolvable, because the sandbox condition does not change between tries.

## Why that makes the hook not worth its cost

CLAUDE.md says: "A guard that goes red when nothing is wrong is spent,
because the reader learns to scroll past it." 69 percent of this hook's
blocks were exactly that: red on its own plumbing, not on a real deviation.
A guardrail the reader learns to scroll past stops catching the deviation it
exists for.

The hook's judgement is not the problem. A separate audit found 8 true
catches against 3 false positives when the hook could actually read the
transcript. The failure is in the plumbing that gets it there.

## The risk this disarm carries

While this hook is absent, an unapproved change to a decision, a gate, a
build order, `CLAUDE.md`, or a settings file goes unflagged. That is a real
loss, not a formality. The same audit found 8 real catches in one week. This
disarm trades that catch rate for the removal of 55 dead-end blocks. The
trade is the owner's call, not a free action.

## The decision

Remove the `Stop` hook entry of `type: "agent"` from `settings.json`. Leave
every other `Stop` entry, and every other hook, unchanged. The owner approved
this disarm directly, on 2026-09-22.

## What re-arms it, and why no nag is needed

Pull request #111 replaces this hook with a command hook,
`hooks/decision_watch.py`. A command hook reads the transcript with a plain
`open()` and passes through no permission check, so the defect above does not
apply to it. When #111 merges, a `Stop` guardrail returns to `settings.json`
on its own, as part of that merge.

This differs from `decisions/session-end-sweep-is-disarmed-until-liveness-is-proven.md`.
That disarm needed `hooks/session_start.sh` to print a notice, because
nothing else would restore the `SessionEnd` hook. Its fix was an unscheduled,
unwritten liveness read, plus a Windows CI job. No PR yet carried either one.
This disarm's replacement already exists, as a numbered pull request, and
landing it is the same act as re-arming the guardrail. A session-start nag
here would watch for a return that a single merge already causes. It is
not needed, and this entry says so rather than leaving a reader to wonder if
it was forgotten.

## Governing decisions, quoted verbatim

- "Judge every rule, check, and design by the outcome for the person the
  software serves."
- "A guard that goes red when nothing is wrong is spent, because the reader
  learns to scroll past it."
- "Never repeal an argument on your own."
- "Never allocate a numbered record on a branch. Write a slug. Claim the
  number at merge."

This entry is filed as a slug, not a number. It records the owner's
approval, not a solo repeal.
