# A heredoc can write a script that the same command then runs

- **What.** Main allows `cat <<EOF2 > x.sh`, with a body that holds a step the guard denies, followed by `sh x.sh` in the same command. The guard does not read a file that the command itself writes. Lane heredoc-hole found it on 2026-10-15. No lane caused it.
- **Where.** The heredoc reading in `hooks/guard_core.py` and `hooks/guard.py`.
- **Decision.** None yet. Owner, 2026-10-15: record now, fix in a later lane.
- **Retire.** The guard reads a heredoc body that the same command writes to a file and then runs. One deny case each covers `sh`, `bash` and `python`.
