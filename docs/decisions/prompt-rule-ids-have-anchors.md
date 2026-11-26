# A rule id that a prompt names must have an anchor

## The ruling

Question: does every rule id that a judge prompt names have a home anchor? Ruling: yes, and CI checks it. `lint/check_prompt_rule_ids.py` fails a prompt that names an id with no `<!-- rule:<id> -->` anchor in the rule files.

- It reads only the prompt constants in its `PROMPT_CONSTANTS` table, with `ast`, from each `hooks/*.py` file. A comment, a docstring or any other string is not read. A name that a prompt is built from, in the same module, is read through.
- An id list (`JUDGED_RULES` in `hooks/reply_judge.py`): each string is an id as written.
- A prose prompt: a hyphenated word is an id when its first segment is a family, the first segment of some anchor in the rule files. `red-run` has no such family, so it is left alone.
- The anchors come from `lint/rule_audit.py`. Its `RULE_FILES` are `CLAUDE.md` and `output-styles/shiv-stylisms.md`, read through `ANCHOR_RE`.
- It prints one `FAIL` line for each id with no anchor, naming the file, the line and the id. It also fails when it reads no id at all, and when a file cannot be read or parsed. A clean run prints `ok` and the count of ids.
- CI runs it as step "Prompt rule-id lint" of the checks job, and runs its fixture suite as "Prompt rule-id fixture suite". The lint is in `merge.readyChecks` of `.github/stamp.json`, so a lane runs it before its draft goes ready.

## Why and harm

Mistake: hook prompts restate rule ids by hand, and an id can outlive its rule. On 2026-11-25, `hooks/reply_judge.py` judged `measure-before-priority`. No rule file holds that id. Its home is `style-measure-before-priority`. Four hook files name rule ids by hand, in five prompts and one id list: `hooks/reply_judge.py`, `hooks/call_judge.py`, `hooks/sendmessage_state.py` and `hooks/prose_judge.py`.

Harm: a judge cites a rule that does not exist, or keeps judging against a stale copy of a rule after its home changed. This lint stops the first harm only. See Known limits.

The owner (owner, 2026-11-25, 16:14 to 16:36 CST). On the judges' own rule copies: "how does it have its own saved copy of rules, and those dont update?!?!?!" On the fix: "yeah this shd be fixed i believe". On the order, this lint first and then judges read their rules' home sentences at run time: "approved".

Cost: one run in CI and one in the ready checks. It reads the hook files that its table names and the two rule files. It starts no child process and writes no log, file, hook or timer. Not pinned beyond `lint/test_check_prompt_rule_ids.py`.

Reader: the step "Prompt rule-id lint" in CI, and its row in the ready checks.

## Known limits

- The lint checks that an id has an anchor. It does not check that a prompt's wording matches the id's home sentence, so a judge can still judge an old wording of a live id. The next step, not built here, is that judges read their rules' home sentences at run time, in the order the owner approved above.
- It does not read a prompt constant that is missing from `PROMPT_CONSTANTS`, a prose id in a family that no anchor uses, or an id split across two joined strings. A hyphenated word that starts with a family word reads as an id. Renaming the word clears the false alarm.

Kind: process
Home: lint/check_prompt_rule_ids.py
