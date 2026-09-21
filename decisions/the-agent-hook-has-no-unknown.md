# The agent hook has no unknown

CLAUDE.md says: "Verify a claim before you rely on it, and report a read that could
not run as unknown, never as clear or broken." The `type: agent` Stop hook in
`settings.json` now breaks that rule on purpose. An unreadable transcript returns
`{"ok": true}`, the same answer a clean turn returns. This entry records why, and
what the owner accepts.

## What was measured

The old prompt asked the subagent for `{}` or `{"systemMessage": "..."}`. That is not
the contract the hooks guide documents for an agent hook. The documented contract is
`{"ok": true}` or `{"ok": false, "reason": "..."}`.

Measured across the owner's transcripts, the old prompt produced about 55 blocks.
About 32 of them said the subagent could not read the transcript. Each block made
Claude rewrite its end-of-turn report, so the owner read the same report twice.

The unreadable-transcript blocks are therefore the larger half of the defect. They
are not a signal about the turn. They are a signal about the hook.

## Why the rule cannot be met here

The contract has two values. `ok` is true or false. There is no third value, and
there is no side channel. A hook that wants to say "unread" has only two spellings
available:

- `{"ok": false, "reason": "the transcript could not be read"}`. This reports unknown
  honestly. It also blocks the turn and doubles the report. That is the measured
  defect, 32 times over.
- `{"ok": true}`. This does not report unknown. The owner sees nothing.

`lint/check_unknown_reads_contract.py` states the contract's own admission rule: a new
member needs a token that contains "unknown" and is distinct from its clear and broken
outputs. This hook cannot emit such a token. The mechanism has no room for one. The
hook is therefore NOT a member of that contract, and this entry is the record of why
it is not.

## The outcome the rule protects, and what carries it here

The rule protects one outcome. A reader must never take "we did not look" for "we
looked and it is clean".

That outcome is not carried by this hook. It is carried by the hooks that already run
on the same Stop event and do their own reads. `hooks/config_report.py` names every
project config file changed this turn. `lint/report_gate.py` checks the report's own
shape. `hooks/guard.py` runs at PreToolUse, before the act, and it logs
`noted`/`subject-unread` when it cannot read a subject. The guard is a member of the
unknown-reads contract and stays one.

The agent hook is a second look at work the guard already governs. Losing its "unread"
signal costs the owner a second opinion, not the first one.

## The accepted risk

A turn whose transcript cannot be read now looks exactly like a clean turn, to this
hook. A genuine unapproved change made in such a turn goes unreported by it.

The trade is 32 false blocks against a lost second opinion on an unmeasured number of
turns. How often a transcript is unreadable AND the turn holds an unapproved change is
unmeasured. This entry reports that number as unknown.

WHO MADE THIS CALL, AND ON WHAT AUTHORITY. This matters more here than in most
entries, because this entry carves out a CLAUDE.md rule. Read it as an argument to
check, not as a settled permission.

The owner asked for the `{"ok": true}` mapping, in the plan that opened this work. The
owner did NOT rule on its conflict with the unknown-reads rule. A reviewer raised that
conflict afterwards. The orchestrator wrote this entry, on one instruction given in the
session of 2026-09-21, verbatim:

```text
Execute the plan to completion. If you reach a fork that needs a decision, I
trust you to make the right one, but still record it for me to potentially
revise at a later time.
```

That is a session grant. It is not a rule in CLAUDE.md. It names neither this hook nor
this rule, and it does not survive the session. A guardrail hook flagged this entry as
a gate weakened by the orchestrator's own say-so. That flag is fair. This paragraph is
the answer to it: the carve-out is recorded, attributed, and open.

The other spelling, a block on every unreadable transcript, is the pre-change
behaviour. The measurement that argues against it sits above. The owner can revise this
entry at any time. Reverting the prompt restores the old behaviour with no code change.

If the agent-hook contract later gains a third value, or a side channel that reports
without blocking, this entry should be reopened. The hook would then join
`lint/check_unknown_reads_contract.py` as a third member, by the admission rule that
file states.
