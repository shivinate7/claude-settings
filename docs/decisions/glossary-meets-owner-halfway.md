# The glossary meets the owner halfway

## The ruling

Owner, 2026-11-01 18:46 CST: a session reads what the owner types by meaning, and the glossary keeps one name per thing. The owner's statement, verbatim:

```
"while i want to keep a strict glossary, if the word i say doesn't match the word u know of an item in the repo, but semantically they are synonyms, you need to be able to catch that breadth ... i'm not saying ur glossary shd be able to expand, it should not have multiple words for the same thing, im saying im human so you need to meet me halfway."
```

Three incidents, all on 2026-11-01:

- He said "test groups" for CI test shards.
- He said "time limits" for CI job caps.
- He said "outcomes based test audits" for the test and CI standard plan, roadmap step `test-ci-standard`.

`lint/check_glossary.py` reads added paths and lines, the glossary table and the rule files. It never reads what the owner types.

`lint/rule_mechanisms.json` maps this rule to check_glossary.py, which holds the write half only; the read half is a judgment read.

Why: the owner should not have to learn the vocabulary. The glossary stays one name per thing.

Kind: process
Home: rule:speak-one-name-per-thing
