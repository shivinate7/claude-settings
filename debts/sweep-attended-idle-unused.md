# An attended sweep reads idle time it does not use

- **What.** An attended run has no deadline, but it reads every tree's idle time in a serial pass before it judges. Review round 3 found that the attended run does not use those reads. It measured the pass at about 7 s at 150 trees. The same review says previews lose their thread pool. That claim was not re-run for this debt. Named in review round 3, item 5.
- **Where.** In `janitor/sweep.py`: `_oldest_idle_first` and `sweep_repo` (the full-mode idle read), and `_begin_preview_cache`, `_pmap` and `_sweep_roots` (the preview pool).
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left` (the sweep that reaps what a finished agent left).
- **Retire.** An attended run reads no idle time that its decisions do not use. A preview keeps its thread pool. Check: a timing case with 150 trees shows no unused idle read in an attended run, and the preview keeps its pool.
