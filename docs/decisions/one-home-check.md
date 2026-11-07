# The one-home rule has a check, in this repo and in each child repo

## The ruling

Owner, 2026-11-02 13:38 CST, page item 174, pick a: mechanize rule
`building-one-home-per-capability` (one home per capability), both ways, with room for a child
repo's own nuance. Plan: PR #1106 (the one-home check plan). Owner answers to its questions,
2026-11-07 12:34 CST, page items 337 to 341:

- Item 337, pick a: the old STE sentence fragment joins the retired-names list once the copies are
  fixed. PR #1105 (agent briefs drop the STE name) fixed them, so it joins in this lane.
- Item 338, pick a: a child exception is the marker `<!-- exempt: <rule-id> reason: <text> -->`.
  The word `override` keeps its one meaning, the owner's typed prompt (decision `owner-override`).
- Item 339, pick a, with the note "isnt there a better way than both of these options tho".
  Triage's answer: run the child check inside the shared lint action that child repos already pin,
  with no new CI step. See "The better way", below.
- Item 340, pick a: the reword check uses a 5-word floor for removed rule text.
- Item 341, pick b, with the note "i need a semantic meaning pass on this": build paraphrase
  detection now, judged by a model. It stays advisory until its precision, measured on a labelled
  set, is in this record.
- Plan question 5 is moot: PR #1105 closed debt `ste-into-agent-briefs`.

## The better way (item 339)

The plan offered two child paths: (a) the child CI checks out claude-settings at a pinned sha, or
(b) the child keeps a copy of the rule ids. A third path needs neither.

- `actions/ste-lint/run.sh` already finds the linter at `../../lint` from its own action path. A
  child that pins `ste-lint@<sha>` therefore already holds claude-settings at that sha. That
  checkout is the parent. No extra checkout and no copied ids are needed.
- Measured 2026-11-07 on the default branch of each child: degen, home, joyous, mailaudit and q_max
  each pin `actions/ste-lint` in `.github/workflows/checks.yml`. None pins `actions/claude-md-cites`.
- So the child check runs inside the ste-lint step. A pin bump by Renovate brings it in.

## Measured

Paraphrase pass, `python3 lint/find_copies.py --measure lint/paraphrase_labelled.json`, run once on
2026-11-07. Model `sonnet`, effort `high`. Sample: 51 labelled cases, 29 paraphrase and 22 distinct.

- Precision 1.00: 25 of 25 flagged cases were paraphrases. No false positive.
- Recall 0.86: 25 of 29 paraphrases were flagged. Missed: p11, p26, p27, p28.
- Precision was not under 0.9, so no second prompt was tried. There is one run.
- Limits. The prompt was written after the set was read, so both figures lean high. 22 distinct cases
  is a small base for a precision claim. The set measures the model alone. The lexical pre-filter (3
  shared word stems) runs before it in `--paraphrase`: offline it passes 25 of 29 paraphrase cases
  (misses p16, p20, p25, p27) and 5 of 22 distinct cases. Precision on a real child repo is unmeasured.
- Cost per run: `--paraphrase` starts three processes, python, `git ls-files` and one `claude -p`;
  `--measure` starts two, python and one `claude -p`. Each run reads the tracked `*.md` files
  (`--paraphrase` only), makes at most one model call, and writes no file. `invoke_model` makes and
  removes one temp folder for the call. A run with no candidate line starts no `claude`.
- Where it runs: skill `compliance-check`, as a report-only step. Never in CI or ste-lint: CI has no
  model key.

## Status

Building, lane `one-home-check`. The parts, their homes and the measured counts land here as each
part is built.

Kind: process
Home: rule:building-one-home-per-capability
