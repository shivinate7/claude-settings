# A waiting-page option's key is the letter the page shows

## The ruling

The waiting page shows an option by its position, as a letter: the first option is A, the second B (`skills/waiting-page/page.html`, symbol `letterOf`). The key of each option is that letter in lowercase. A session keys its options `a`, `b`, `c` in the order the page shows them, and names an option in item text by its letter, never by another key.

- Guard rule `option-letter-keys` (`hooks/guard.py`, function `option_letter_hit`) refuses an `ArtifactData` set or update to `items`, of `kind: decision` or with no `kind`, when `options` has an option that:
  - has no string `key`;
  - repeats another option's key;
  - has the key `none` (the page's `NONE`, which it reads as "none of these"); or
  - has a key that is not the lowercase letter of its position.
  - It also refuses an item whose text (title, context, why, an option's text or a step) names an option by a letter-and-digit key, such as "option e2". The words that start the match are option, pick and key, in any case. "Option A", "pick b" and "option 2" pass.
  - It reads each write in a batch and data read from `file_path`. It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`).
  - It passes a task, a note, an update that carries no `options` and no matching text, and a call to another artifact.
  - It reads last, after `owner-judge`. Each older rule keeps naming its own refusals.
  - The reason says: key the options a, b, c in the order shown, each once, never none, and name an option by its letter. It names no target.
  - It is built against a named incident, below. It landed 2026-10-30.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: the guard copies the page's letters. A test reads the page's `letterOf` and `NONE` lines and fails when they differ from the copy.
  - Known limit: more than 26 options always refuse, because the page repeats letters after Z and the key then repeats.
  - Known limit: an option named in text by a word, such as "the lint option", or by a key the page never shows that is not letter-and-digit, passes.
  - Known limit: a whole-item write of a closed item with old keys is refused. A status-only update closes it.
  - Known limit: an update that carries `options` but no `kind` is judged as a decision, so a task update that carries options is refused only if its keys are wrong. The writer carries `kind: task` again on such an update.

Incident:

- 2026-10-30 15:09 CDT, waiting item 77: an option keyed `e2` sat in the first position, so the page showed it as A. The owner's answer "A" was read as the option keyed `a`, which sat second.
- 2026-10-28 12:47 CDT, waiting item 44: an option keyed `none` hid the page's own "none of these" answer.

Kind: process
Home: rule:questions-go-to-owner
