# A tilde fence does not blank a lane number

- **What.** A tilde fence (`~~~`) is not blanked. A session number inside one is refused.
- **Where.** The quoted-text blanking in `hooks/guard.py`.
- **Decision.** `lane-by-slug` (a lane is named by its branch slug, not a session number).
- **Retire.** A tilde fence is blanked as a backtick fence is, and a case with a session number inside one passes.
