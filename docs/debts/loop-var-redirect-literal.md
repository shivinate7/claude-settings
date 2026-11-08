# A loop variable as a redirect target, or a glob list item, is not judged as the files it names

- **What.** In a `for` body, `> "$f"` keeps the literal reading, so `for f in hooks/guard.py; do echo x > "$f"; done` passes for a coordinator, on main and here. A glob list item is judged as text, so `for f in *.json; do sed -i ... "$f"; done` in the config root misses `settings.json`.
- **Where.** `_loop_rewrites` and `_loop_items` in `hooks/guard_frozen.py`.
- **Decision.** `session-tiers` (tier guards), whose loop bullet names both forms.
- **Retire.** Read a redirect target after the loop's words, and expand a glob list item against the cwd. Cases `for f in hooks/guard.py; do echo x > "$f"; done` and `for f in *.json; do sed -i ... "$f"; done` deny for a coordinator in `hooks/test_guard.py`.
