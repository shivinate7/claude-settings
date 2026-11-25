# Restated text follows its home

## The ruling

Owner, 2026-11-25 10:02 CST: "how have you built a way to ensure that if rulings change, they're automatically updating in the briefs and/or utilizing a pointer system so that way staleness never occurs".

Owner, 2026-11-25 10:25 CST: "this might be huge so ensure you send an opus plan agent too and a refuter onthis", and "i assume it will largely be haiku workflow work".

The goal had no home until this record. The answer is a pointer, not a copy: text that restates a rule names the rule's id, and a check or a judge reads the live rule. Nothing here is built yet. The record cites filed with this record are text only.

Premise checked: decision `agent-model-cap` gives haiku to the test-author, the record-writer and the round-1 reviewer, and sonnet to the builder. So "largely haiku" holds for test and record work. Each `.py` edit is a builder's, and runs sonnet.

## The mistake and the harm

The mistake: a ruling changed, and the text that restates it to sessions and agents stayed as it was. The harm: sessions and agents act on the old rule. Rule `building-guard-needs-incident` says a guard is built against a mistake that happened. This is that mistake.

Two incidents, 2026-11-25:

- No check ties the standing brief lines in `hooks/agent_brief.py` to the records they come from. A change to a record cannot reach them.
- A judge prompt in `hooks/reply_judge.py` (the questions-go-to-owner text) may still tell sessions to take a pick. The prompt holds no consult wording. The cause is not confirmed.

## The design (planned; not built)

In this order:

- Records: each copy of a rule sentence in a record becomes a cite of the rule's id, with a short gloss. This change does it for the copies found on 2026-11-25.
- Brief lines carry their id: each standing line in `hooks/agent_brief.py` shows the rule or decision it restates, as an inline cite.
- Judges take the live rule sentence: a judge prompt reads the current sentence of each rule it names, by id, through the one reader in `lint/rule_audit.py`.
- Planned: the check "Rules and records move together" (`lint/compliance_probes.py` `probe_aligned`) also reads ids in Python text, one direction only. A changed record or rule sentence asks the Python string that names it to be touched or confirmed. An edit to the string asks nothing.
- Agent files, skills and templates: the same planned check (`lint/compliance_probes.py` `probe_aligned`) counts a backticked id as a cite. Each file gets its cite.

What the cite-and-confirm check leaves open, so a reader knows the limit:

- a false confirm line;
- a cosmetic touch that passes;
- a restatement that names no id;
- a restatement under the wrong id;
- text built at run time from non-constant parts.

Open premise: whether every agent type, local and cloud, loads root `CLAUDE.md`. Until that is proven per type, no brief line is shortened. Lines keep their full text and gain the id.

## Cost

Nothing runs on a tool call. No long-lived process starts. The planned checks run in the CI step that runs the checks today, with no new git call. The planned judge reader adds a read of the root rule file inside the judge process, on each Stop the judge samples.

## Picks

Practice, not ruled; the owner may reverse them:

- The brief lines show the cite in the text, not hidden.
- The standing-rules record (decision `agents-get-standing-rules`) drops its line list for a cite of the constants.
- The planned check (`lint/compliance_probes.py` `probe_aligned`) reads ids in `.py` files in every repo, not only this one.
- The gate turns on only after a replay of the last 50 merged pull requests shows no false alarms.

Kind: process
Home: rule:building-one-home-per-capability
