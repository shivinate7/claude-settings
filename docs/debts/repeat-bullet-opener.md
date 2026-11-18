# A decision file can hold two bullets that open the same fact

- **What.** A conflict resolution can leave two copies of one bullet in a decision file, with different detail. One review round found it. Nothing in CI reads it.
- **Where.** `docs/decisions/*.md`; no check compares bullet openers within one file.
- **Decision.** none
- **Retire.** A check fails when two bullets in one decision file share their first 40 characters. `lint/test_repeat_bullet_opener.py` shows it red on a duplicated bullet and green on one copy.
