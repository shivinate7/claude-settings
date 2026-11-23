# Placeholder check skips known markup tags unquoted

- **What.** The placeholder check treats an angle word as markup, not a placeholder, when its name is in `KNOWN_MARKUP_TAGS`, quoted or not. The list holds words that are also placeholder words (head, title, body, key, date), so `<head>` in an owner command passes. Fix idea: skip a known tag only inside quotes. Found in the PR 3808 review (finding F1).
- **Where.** Not on main. Branch `owner-command-placeholder` (PR 3808, open): `hooks/question_form.py` line 781 (`KNOWN_MARKUP_TAGS`), and the comment at line 769 that describes the skip.
- **Decision.** `question-form` (the form's placeholder rule, on main). Branch `owner-command-placeholder` also names the skip in `docs/decisions/guard-remedy-not-to-owner.md` (line 212); that file is not on main.
- **Retire.** Close when an unquoted `<head>` is refused and a quoted `"<head>"` passes, both pinned as cases in `hooks/test_question_form.py`.
