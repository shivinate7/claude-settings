# Commit-message rules read heredoc headers one way only

- **What.** `own_heredoc_bodies` reads heredoc headers without the two-reading rule. So a bash-valid `echo it's`, then a lone `'` line, then a heredoc commit with a path-citing body passes cite-by-id and lane-by-slug. Main denies it.
- **Where.** `own_heredoc_bodies` in `hooks/guard.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** Lane gcp-heredoc-two-read: the walker judges heredoc bodies from both readings. Cite-by-id and lane-by-slug cases for `-F -` and `-m "$(cat <<'EOF'` deny.
