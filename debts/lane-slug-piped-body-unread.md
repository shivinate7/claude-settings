# A piped commit body is not read

- **What.** A piped body, such as `echo ... | gh pr create -F -`, is not read.
- **Where.** The body reader for `gh pr create` in `hooks/guard.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** A piped body is read, and a case with a lane number in a piped body is refused.
