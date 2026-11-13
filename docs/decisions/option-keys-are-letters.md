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

An option also keeps its letter once shown (owner ruling R60, roadmap ruling r60, 2026-11-12 15:07 CST: "in general if sessions create options triage should hold those letters the same (or they shd be referenced by IDs each option rather than A B which can be arbitrarily swapped)"). Guard rule `option-letters-frozen` (`hooks/question_form.py`, function `frozen_letters_hit`, run by `item_hit` after `option_letter_hit`) refuses a set or update of an open decision on this repo's waiting page whose write carries `options` when:

  - an option has no non-empty string `id`, has an id that is a lone letter, or shares an id with another option;
  - the write carries no `shown` list. `shown` is the options as first shown, in order, each as `{key, id, label}`;
  - there are fewer options than shown;
  - `shown` is shorter than `options`; or
  - an option at a shown position differs from the shown entry in key, id or label (a reorder, a relabel, a changed id).

  - A note on an option (`note`), with key, id and label unchanged, passes. So does an option appended after the shown ones. A rule-driven change adds a `note` and reorders nothing; the page shows the note on the option's card.
  - On every write that carries `options`, `shown` is as long as `options`. An update that appends options extends `shown` by them on the same write. A first `set` carries a `shown` equal to its own options. The reason names `shown`.
  - A task, a note, a closed item and a write with no `options` pass. `shown` is in the page's `itemFields` block (rule `item-field-rendered`).
  - The reason says: keep each shown option's key, id and label and position, give each option a unique id, carry `shown`. It names no target.
  - Incident: 2026-11-12 14:39 CST, waiting item 646. Triage reordered the options after the chat question went out, so chat a became page b. The owner's "a" (15:03 CST) could have been filed as the opposite pick. `option_letter_hit` could not see it: after the swap each key was still its position's letter.
  - Cost: no new process. It runs in the guard process that every waiting-page write already starts, reads only the write, and writes no file unless it denies.
  - Known limit: a write that carries its own `shown` is trusted. A set or update that rewrites `shown` to match reordered options passes, since the guard cannot see the stored item. A held answer (`page_grant.py`) is the backstop: an answer whose option id or label moved is held. An `options` that is not a list is refused.
  - Known limit: a write that rewrites `shown` itself is not detectable. The guard trusts `shown`, since the stored item is unseen.
  - Known limit: a write that carries no `options` is not judged, so an update that drops `shown` alone passes.

The page keeps the id and the label of an option as they read when the owner picked it, in the draft. A move of the letters between the pick and Send then saves the option picked.

The id is the stable name of an option; the letter is its place. The page saves `optionId` beside `choice` in the answer. `skills/waiting-page/page_grant.py` prints `held:` (exit 3) for an answer that names an option the item no longer holds. The answer's `optionId` is compared with the option at its choice key, or its `label` when it has no `optionId`. A choice key the item lacks is held too. The owner then confirms in words (R60, part 3). `skills/waiting-page/question_source.py` (`render`) builds the chat question and the item's `options` and `shown` from one spec, so the two copies share one source.

A chat answer is not covered by the guard, since no guard can read the chat. Before acting on an owner's chat letter answer to an item that carries `shown`, the session compares the letters in the chat question it asked with the item's `shown`. If they differ, it holds the answer and asks the owner to confirm in words (`skills/waiting-page/SKILL.md`, "Route and close").

A letter also names the same option in the chat and on the page. Guard rule `option-labels-match-chat` (`hooks/question_form.py`, functions `chat_page_label_hit` and `page_label_hit`, run by `hooks/guard.py` `data_tool_label_hit`) refuses a set or update of an open decision on this repo's waiting page. The refusal holds when an option label differs from the chat's text for the same letter.

  - A chat question cites its item in a line `Page item: <id>` (the colon may be left out when the id holds a digit or a hyphen, or is the written item's own id) and writes one line per option, the letter then the text: `a) <text>`, `a)<text>`, `a. <text>`, `**a**) <text>`, `**A** <text>`, `**A** — <text>`, `A — <text>` or `Option A: <text>`, the letters in the page's order. The check reads the newest assistant text in the last 1 MiB of the session's transcript that cites the item's id and writes option lines for it.
  - A reply puts each cite on one side of its options, read per reply (`_own_option_lines`). A reply with an option line before its first cite and none after its last cite has its cites below: each cite owns the option lines between the cite before it and itself. In any other reply, each cite owns the option lines after its own line, up to the next cite. The side is read per reply because the text between two cites reads the same in both shapes.
  - A letter is a position, as above. A label's own opening letter tag is dropped before the compare. Texts are compared folded (case, spacing and the marks `*`, `_` and `` ` `` dropped; a curly apostrophe made `'`; an em or en dash made `-`; a closing `.,;:!` cut). They are equal when the chat text is the label, or the label's start up to a word boundary: the chat may shorten a label, the page never may (owner, 12:35 CST Nov 8, "A and B mean the same"; coordinator ruling 07:57 CST Nov 12). A chat `No` does not match a page `Node.js rewrite`.
  - It passes when no chat text cites the item, or the chat cites another item. When the chat writes two or more option letters, a page option at a letter the chat does not write is refused. A chat that writes one letter only is not refused for the letters it omits (coordinator call, 07:57 CST Nov 12). A letter it writes with other text than the page label is still refused. A write that carries no `options` passes. A task, a note and a closed item pass.
  - The reason says: the chat and the page carry the same option text in the same order. It names no target.
  - Cost: no new process. It reads the transcript's tail at most once per page write that carries `options`. Each read is up to 1 MiB, so a call with N such writes reads up to N MiB. It writes a line to `guard.log` only when it refuses or notes; no test pins that. Three cases each allow the write and log a `noted` line; no test pins the count. They are an unreadable transcript, a payload with no `transcript_path`, and a bare chat line `A <text>` at a page letter that has no chat option line. A write whose chat matches, cites another item or cites no item writes nothing.
  - Known limit: only an assistant text block counts. A question asked in the chat box (`AskUserQuestion`) is not read.
  - Known limit: a chat question that cites no item is not compared, and a write with no later chat to compare passes. The rule judges two copies only when the chat names the item.
  - Known limit: a chat question written after the page item is not checked until the item is written again.
  - Known limit: after a `none` answer, ask the chat question again with the new options, then write them after the shown ones, or open a fresh item. The old question still cites the id, so a write made before the new question is compared to the old one.
  - Known limit: only the writing session's own transcript is read. A chat question asked in another session is not compared.
  - Known limit: the chat and the page must match in punctuation beyond the fold. A chat `-role` and a page `--role` differ and refuse.
  - Known limit: a reply that puts one cite above its options and another below is read by one side, so one of its items reads another item's lines. So is a reply that cites its items once before any option line and again below each question's options.
  - Known limit: a line that opens with one letter and a `)`, `.` or `:` then text reads as an option line. A trailing `A: I recommend b.` can flip the read and refuse a matching write. How often it happens is unmeasured.
  - Known limit: a cite's id ends at a space or at `*`, `_` or `` ` ``, the markdown marks (`PAGE_ITEM_CITE`). An item id is a slug of letters, digits and hyphens, so it holds none of them. An id with `_` would be cut short.
  - Known limit: an unreadable or missing transcript, or a payload with no `transcript_path`, allows the write and logs one `noted` line.
  - Known limit: a chat line `A <text>` (a bare letter, a space, text) is not read as an option, since that would read prose as options. It is noted (one `noted` line, the write allowed) when its letter is one of the page's and the chat writes no option line for that letter. Any other unread form, such as `A.Blue` or `A:Blue`, is not compared and logs nothing.
  - Known limit: a chat option line with a trailing note, such as `b) Red (recommended)`, against the page label `Red` is refused, because only the chat may be shorter than the page (owner, 12:35 CST Nov 8; coordinator ruling 07:57 CST Nov 12).
  - Known limit: a chat with a letter the page lacks (the chat lists a, b, c and the page a, b) passes.
  - Known limit: a colon-less cite counts only when its id holds a digit or a hyphen, or is the written item's own id. A colon-less cite of another item with a one-word id is not read, such as `Page item merge` in a write to another item. So it does not end the lines of the cite before it.
  - Known limit: prose `A — I recommend b.` after a cite reads as option a, because `A <dash> <text>` is an option line. A write whose label a differs is then refused (a false alarm).
  - Known limit: a cite older than the last 1 MiB of the transcript is not read, and no line is logged.
  - Known limit: the widening guard (`uniform-pick`) still reads `pick` beside `recommended`. Reading `recommended` alone needs an owner ruling.

Incident:

- 2026-11-08, owner ask: the option letters on the waiting page must mean the same as in the chat question, both being static copies. The same ask found that the item field `pick` held the recommended option, not the owner's answer (`choice` in the answers collection). The page now stars and names `recommended` (it reads `pick` on an old item), and a saved answer carries `label` ("A: Red") beside `choice`.

- 2026-11-02 12:15 and 12:25 CST, Home waiting page: decisions `duo-search-top` and `climate-purifier-preset` were written with an option keyed `none`. The write went through, because the guard judged only a call whose url was the cwd repo's own page, and the page then blocked each item. The none-key rule above closes the gap. Known limit: a `str_replace` carries no `options`, so one that adds a key-named option to another page's item passes.
- 2026-11-01 16:12 CST, a waiting-page decision keyed a-d carried the labels "B: a bottom strip", "D: drag sideways", "A: a rail" and "C: a grab line". It had two letter sets, so the owner's answer letter was ambiguous. The label clause above refuses a write with these four labels, since each tag differs from its key's letter. Forms it does not match are known limits of the ruling.
- 2026-10-30 15:09 CDT, waiting item 77: an option keyed `e2` sat in the first position, so the page showed it as A. The owner's answer "A" was read as the option keyed `a`, which sat second.
- 2026-10-28 12:47 CDT, waiting item 44: an option keyed `none` hid the page's own "none of these" answer.

Kind: process
Home: rule:questions-go-to-owner
