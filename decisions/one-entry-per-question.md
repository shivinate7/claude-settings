# One entry per question, rewritten in place

On 2026-09-29 the owner ruled that a decision entry answers one question, and a changed
ruling rewrites that entry. The same day the owner capped record slugs.

## The rulings

- One entry per question. When its ruling changes, rewrite the entry in place. Git keeps the
  history.
- Open an entry only for a new question.
- "A decision entry" names the home of a question's ruling. It does not mean a new entry.
- A record slug is 32 characters or fewer, not counting `.md`. The UI crops long file names.
  Existing files keep their names.
- `lint/check_record_slugs.py` checks files newly added in `decisions/` and `deferred/`
  against origin/main, and goes red on a slug over 32 characters.

## Why

Agents read "a decision entry" as "a new entry". They brought the habit "never edit a
decision, supersede it". One repo got five pricing entries, each amending the last. A reader
had to walk the chain to find the current price.

## What would reopen this

- A rewrite loses a ruling that a reader needed, and git history did not recover it. Bring
  the case to the owner.
- A correct record needs a slug over 32 characters, more than once.
