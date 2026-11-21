# A mode-only change reads as comment-only

- **What.** A chmod of a .py or .sh file, with no text change, reads as a comment-only change. CI then skips every code suite. A lost exec bit is caught only by the next code PR.
- **Where.** `lint/comment_only.py` lines 93-101 (`comment_only`) compare the file text and never the git file mode. `.github/scripts/ci-scope.sh` line 254 trusts that verdict to skip the suites.
- **Decision.** `push-skip-on-proven-tree` (a push to main skips its checks when a passing PR run already covered its tree).
- **Retire.** Compare the git file mode as well as the text. `lint/test_comment_only_mode.py` does not exist yet. It fails while a chmod-only .py or .sh delta reads as comment-only, and passes once the mode is compared.
