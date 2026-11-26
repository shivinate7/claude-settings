# The half-share test in base_items_of is untested

- **What.** Dropping the half-share test in `base_items_of` passes all 50 cases of `lint/test_check_list_lines.py`. Mistake: a later edit drops the test. Harm: a new list that reuses a few names of an old list is judged as grown from it, and is refused for a crowded line or for order. No case pins "shares under half passes" or "shares half or more is an add".
- **Where.** `lint/check_list_lines.py`: `base_items_of`. The half-share test is its `if` line.
- **Decision.** `lists-one-line-per-item` names the 8-item rule, not the half-share test. The test's only home is the check's module docstring.
- **Retire.** Two cases in `lint/test_check_list_lines.py`: a list that shares under half of the smaller list passes, and a list that shares half or more is an add. Dropping the half-share test turns the first one red.
