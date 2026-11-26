# The list-lines boundary at 8 is untested

- **What.** Changing the `per_line` test from `crowded(n)` to `n >= LIMIT` passes all 50 cases of `lint/test_check_list_lines.py`. Mistake: a later edit moves the boundary, and no case fails. Harm: a list wrapped at 8 items a line is refused, though the rule allows 8. The `crowded` change itself is caught by two cases, but both pin a one-line list of 8 as passing. No case puts exactly 8 items on a line of a longer, wrapped list.
- **Where.** `lint/check_list_lines.py`: `per_line`, which reads `crowded`.
- **Decision.** `lists-one-line-per-item`: a list of more than 8 items has no line of more than 8 items. Not on main yet.
- **Retire.** A case in `lint/test_check_list_lines.py` that wraps a list of more than 8 items with exactly 8 on one line and expects a pass. The case goes red under the `n >= LIMIT` change to `per_line`.
