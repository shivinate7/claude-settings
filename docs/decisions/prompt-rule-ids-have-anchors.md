# A rule id that a prompt names must have an anchor

## The ruling

Question: does every rule id that a judge prompt names have a home anchor? Ruling: yes, and CI checks it. `lint/check_prompt_rule_ids.py` fails a prompt that names an id that no home declares: no `<!-- rule:<id> -->` anchor in the rule files, no guard rule name, no decision record slug.

- It reads each non-test `hooks/*.py` with `ast` and `tokenize`, in two places. A prompt constant in its `PROMPT_CONSTANTS` table, with a name it is built from in the same module. A table row whose file is missing, or whose file does not define the row's constant, is reported as a problem, so a reader that sees less never prints ok. And the string a function returns, when the function's name has `prompt` in it (a plain, f-string, implicitly joined or plus-joined string, or a local name that it assigns and returns). A comment, a docstring or any other string is not read.
- An id is read only from an id position, never from free prose, and its first word may be any word. The positions: an item of an id list (`JUDGED_RULES` in `hooks/reply_judge.py`), where the whole item is the id; a rule-list line, an id that opens a string piece or follows a newline in one, then a colon; the word "rule", an optional colon, then the id; and a backticked id. The pieces come from the tokenizer, because implicit joining merges them in `ast`.
- An id in an id position passes when a home declares it. Each home is read at run time, never copied into the lint:
  - a rule anchor: `lint/rule_audit.py` `RULE_FILES` (`CLAUDE.md` and `output-styles/shiv-stylisms.md`), read through `ANCHOR_RE`.
  - a guard rule name: `rule_audit.emitted_rule_ids`, the one reader of the files that write guard.log (`agent-role-model` is the rule argument of a `refuse()` call).
  - a decision record slug: a key of `compliance_probes.decision_records`, the one reader of the decisions folder (`rulings-declare-kind`). The lint calls it and keeps no reader of its own.
- It prints one `FAIL` line for each id that no home declares, naming the file, the line, the id and the homes it looked in. It also fails when it reads no id at all, and when a file cannot be read or parsed. A clean run prints `ok` and the count of ids.
- CI runs it as CI step "Prompt rule-id lint" of the checks job, and runs its fixture suite as CI step "Prompt rule-id fixture suite". The lint is in `merge.readyChecks` of `.github/stamp.json`, so a lane runs it before its draft goes ready.

## Why and harm

Mistake: hook prompts restate rule ids by hand, and an id can outlive its rule. On 2026-11-25, `hooks/reply_judge.py` judged `measure-before-priority`. No rule file holds that id. Its home is `style-measure-before-priority`.

Harm: a judge cites a rule that does not exist, or keeps judging against a stale copy of a rule after its home changed. This lint stops the first harm only. See Known limits.

The owner (owner, 2026-11-25, 16:14 to 16:36 CST). On the judges' own rule copies: "how does it have its own saved copy of rules, and those dont update?!?!?!" On the fix: "yeah this shd be fixed i believe". On the order, this lint first and then judges read their rules' home sentences at run time: "approved".

Cost: it runs in CI and in the ready checks. It parses every hook source file that is not a test file, the rule files, and each decision record once (through `compliance_probes.decision_records`). It starts no child process and writes no log, file, hook or timer. Not pinned beyond `lint/test_check_prompt_rule_ids.py`.

Reader: the CI step "Prompt rule-id lint", and its row in the ready checks.

## Known limits

- The lint checks that an id has an anchor. It does not check that a prompt's wording matches the id's home sentence, so a judge can still judge an old wording of a live id. The next piece of work, not built here, is that judges read their rules' home sentences at run time, in the order the owner approved above.
- It does not read a prompt constant that is missing from `PROMPT_CONSTANTS`, a prompt assembled across functions or files, a prompt function whose name lacks `prompt`, or an id in free prose. A model that is told an id only inside a sentence is not checked.
- A prompt kept in a file, such as `hooks/precompact_handoff_prompt.md`, is not read.
- There is no opt-out: a prompt that writes "rule" before a hyphenated word that is not an id must be reworded.
- `lint/rule_audit.py` `RULE_FILES` omits `.claude/rules/*.md`, so an anchor moved there would not be found, and the lint would flag its id.

Kind: process
Home: lint/check_prompt_rule_ids.py
