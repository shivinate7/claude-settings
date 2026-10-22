Hook load batch, lane A, for claude-settings. Source: a q_max session's load report, Oct 20. These are fixes to existing hooks, not new guard rules, so the freeze on new guards does not apply.

Before any change, measure: time one Edit, one Write, one Bash call and one Stop with the hooks as they are (wall time per hook if guard.log or a timer can give it). Report the numbers. Repeat after the batch.

Lane 1, Edit and Write judges. The prompt hooks on Edit and Write in settings.json (rule speak-rewrite-superseded-in-place) call a model on every edit, including .ts, .tsx and .json, and send the whole Write body. Replace them with one command hook that calls the model only for *.md files and decision records, and exits at once for any other path. Keep the rule text the judge uses.

Lane 2, platform-only hooks. stall_watch only works on posix, sim_boot_record only with xcrun (it runs both before and after Bash), ci_wake only acts on 'ready'. Make each exit before starting python on a platform or input where it does nothing, or register it only where it works. Do not merge hooks into a dispatcher in this batch.

Lane 3, import chain. local_time.py imports question_outcome to read MACHINE_TAGS; that pulls in decision_watch and then guard (14 modules, about 9,900 lines) on every prompt. Move MACHINE_TAGS, and config_dir if it is needed, into a small module that imports nothing from the guard family. Update the importers.

Lane 4, SessionEnd fetch. session_end_sweep runs git fetch --prune and ls-remote at every SessionEnd, /clear included (up to 55 s). Allow at most one fetch per repo per 10 minutes; record the time in the state folder.

Lane 5, verdict logs. bin/verdict makes a verdict-*.log in the temp folder per run and never deletes them (6,374 files, 141 MB on Windows). Delete verdict logs older than 7 days at the start of a run.

Do not touch the AskUserQuestion judges; that waits for the reply-style draft. Report per lane what changed, the before and after timings, and the four size numbers on main: decision files, debt files without README and notes.md, hooks/*.py lines (code and tests separately), CLAUDE.md words.
