# A waiting-page option's key is the letter the page shows

## The ruling

The waiting page shows an option by its position, as a letter: the first option is A, the second B (`skills/waiting-page/page.html`, symbol `letterOf`). The key of each option is that letter in lowercase. A session keys its options `a`, `b`, `c` in the order the page shows them, and names an option in item text by its letter, never by another key.

- Guard rule `option-letter-keys` (`hooks/question_form.py`, function `option_letter_hit`) refuses an `ArtifactData` set or update to `items`, of `kind: decision` or with no `kind`, when `options` has an option that:
  - has no string `key`;
  - repeats another option's key;
  - has the key `none` (the page's `NONE`, which it reads as "none of these"); or
  - has a key that is not the lowercase letter of its position; or
  - has a `label` that opens with a letter tag other than its key's letter. A tag is one of these forms, each with an optional leading `**`:

    - `X:`, `X)`, `X.` or `X]`, then a space, a `*` or the end of the label.
    - `(X)` or `[X]`.
    - `X`, then a spaced dash: `X — `, `X – ` or `X - `.
    - `Option X` in any case. X is not followed by a word character or a hyphen.

    A tag equal to the key's letter passes. Text with no mark after its letter passes, such as "B", "B rail" and "I think". Text such as "A/B", "AI-first", "X-ray", "B2B" and "A-frame" passes too. The check is a regex (`LABEL_TAG`), with no model call. An option's label and its mockup carry no letter of their own: the page's key is the only letter.
  - It also refuses an item whose text (title, context, why, an option's text or a step) names an option by a letter-and-digit key, such as "option e2". The words that start the match are option, pick and key, in any case. A colon, a bracket, a quote or markdown emphasis may stand between the word and the key, as in "Option: e2", "Option [e2]" and "Pick **e2**". The key also matches in any case, since the page shows its letter in capitals, so "Option E2" is refused. "Option A", "pick b" and "option 2" pass, and so do the decision id "D12" and the topic id "t18", each in that case only.
  - It judges a `str_replace` on the text it adds (`new_str`), in any field, by this text rule only. The stored item is unseen, so a `str_replace` that adds a key-named option is refused even on a task, a note or a closed item.
  - It reads each write in a batch and data read from `file_path`. The item rules read a relative `file_path` against the call's cwd. The picture check and the model review read it against the hook process's cwd (debt note option-key-gap-relative-path-unjoined).
  - Off this repo's waiting page, it refuses only an option keyed `none`: the page reserves that key, and it blocks the item. That holds for an `items` write whose `options` list has such an option, whatever page the call names and when the cwd repo has no page key. Any other non-letter key on another artifact passes. Only a call whose `url` is this repo's waiting page (`layout.waiting_page`) gets every other check in this record and the other page rules.
  - It passes a set or update of a task, a note or a closed item (one whose write carries `status: closed`). It passes an update that carries no `options` and no matching text, and an `items` write to another artifact with no option keyed `none`.
  - It reads last, after the form rules (`question-form`, `owner-judge`). Each older rule keeps naming its own refusals.
  - The reason says: key the options a, b, c in the order shown, each once, never none, and name an option by its letter. It names no target.
  - It is built against a named incident, below. It landed 2026-10-30. The label clause landed 2026-11-01.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: the guard copies the page's letters in `_letter_of` and `OPTION_NONE_KEY`. A test reads the page's `letterOf` and `NONE` lines and fails when they are not `String.fromCharCode(65 + i % 26)` and `"none"`. It compares the page to those two forms, not to the guard's copy.
  - Known limit: an `items` write to an unrelated artifact whose item has an option keyed `none` is refused.
  - Known limit: more than 26 options always refuse, because the page repeats letters after Z and the key then repeats.
  - Known limit: a letter tag that is not at the start of a label, such as "Rail (B)", passes.
  - Known limit: an option named in text by a word, such as "the lint option", or by a key the page never shows that is not letter-and-digit, passes.
  - Known limit: an id or cell with a key's shape, such as the step id "c188", "key d4" or "Pick A1", is refused after option, pick or key.
  - Known limit: an update that carries `options` but no `kind` is judged as a decision, so a task update that carries options is refused only if its keys are wrong. The writer carries `kind: task` again on such an update.
  - Known limit: a word tag other than `Option` passes, such as "Approach B:" or "Plan B:". It is kept out because "Plan B" is plain English.
  - Known limit: an update that carries `options` but no `status` is judged even if the stored item is closed. The guard cannot see the stored status.
  - Known limit: unusual forms pass: `*B*:`, `` `B`: ``, `B:x` and `- B: x`.

A letter also means the same option in the chat and on the page. Guard rule `option-labels-match-chat` (`hooks/question_form.py`, functions `chat_page_label_hit` and `page_label_hit`, run by `hooks/guard.py` `data_tool_label_hit`) refuses a set or update of an open decision on this repo's waiting page. The refusal holds when an option label differs from the chat's text for the same letter.

  - A chat question cites its item in a line `Page item: <id>` and writes one line per option, `a) <text>`, the letters in the page's order. The check reads the newest assistant text in the last 1 MiB of the session's transcript that cites the item's id.
  - A letter is a position, as above. A label's own opening letter tag is dropped before the compare. Texts are compared folded (case, spacing and markdown marks), and equal when either starts with the other, so the chat may shorten a label.
  - It passes when no chat text cites the item, or the chat cites another item. It passes when the chat writes no line for a letter, or the write carries no `options`. A task, a note and a closed item pass.
  - The reason says: the chat and the page carry the same option text in the same order. It names no target.
  - Cost: no new process. It reads the transcript's tail once per call, only for a write that carries `options`, and writes nothing unless it refuses. An unreadable transcript allows and logs one `noted` line.
  - Known limit: only an assistant text block counts. A question asked in the chat box (`AskUserQuestion`) is not read.
  - Known limit: a chat label that is a prefix of the page's label passes, so a chat "Allow" matches a page "Allow merge --role".
  - Known limit: a chat question that cites no item is not compared, and a write with no later chat to compare passes. The rule judges two copies only when the chat names the item.
  - Known limit: a chat question written after the page item is not checked until the item is written again.

Incident:

- 2026-11-08, owner ask: the option letters on the waiting page must mean the same as in the chat question, both being static copies. The same ask found that the item field `pick` held the recommended option, not the owner's answer (`choice` in the answers collection). The page now stars and names `recommended` (it reads `pick` on an old item), and a saved answer carries `label` ("A: Red") beside `choice`.

- 2026-11-02 12:15 and 12:25 CST, Home waiting page: decisions `duo-search-top` and `climate-purifier-preset` were written with an option keyed `none`. The write went through, because the guard judged only a call whose url was the cwd repo's own page, and the page then blocked each item. The none-key rule above closes the gap. Known limit: a `str_replace` carries no `options`, so one that adds a key-named option to another page's item passes.
- 2026-11-01 16:12 CST, a waiting-page decision keyed a-d carried the labels "B: a bottom strip", "D: drag sideways", "A: a rail" and "C: a grab line". It had two letter sets, so the owner's answer letter was ambiguous. The label clause above refuses a write with these four labels, since each tag differs from its key's letter. Forms it does not match are known limits of the ruling.
- 2026-10-30 15:09 CDT, waiting item 77: an option keyed `e2` sat in the first position, so the page showed it as A. The owner's answer "A" was read as the option keyed `a`, which sat second.
- 2026-10-28 12:47 CDT, waiting item 44: an option keyed `none` hid the page's own "none of these" answer.

Kind: process
Home: rule:questions-go-to-owner
