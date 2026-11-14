# A repo matches a shared format; the shared tool never grows a second form

## The ruling

Owner, 2026-10-27 12:51 CDT, topic t18 (one home, then variants): when a repo differs from a shared format, the repo changes to match it. The shared tool never grows a second accepted form to fit one repo.

- An option that widens what a shared tool accepts is a second accepted form, an allow-list entry or a per-repo exception. It carries "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo" and is never the recommended option. Rule `style-question-form` holds the text.
- On the waiting page (skill `waiting-page`), such an option carries `widens: true`. Its card shows the label.
- Guard rule `uniform-pick` (`hooks/question_form.py`, run by `hooks/guard.py`) refuses an `ArtifactData` set or update to `items` whose `recommended` (old name `pick`) names an option with `widens: true`. It reads each write in a batch and data read from `file_path`.
  - It judges only a call whose `url` is this repo's waiting page (`layout.waiting_page`), and only an item of kind `decision` or with no kind.
  - It is built against a named incident, below. It landed 2026-10-28.
  - Cost: no new process. It runs inside the guard process that every `ArtifactData` call already starts. It writes no file unless it denies.
  - Known limit: an update that sets `recommended` without `options` cannot see the stored options and passes. The writer carries `options` again on such an update.
  - Known limit: the guard reads the `widens` mark, not the option's text. An unmarked widening option passes this rule. The call judge is the backstop.
- Guard rule `uniform-answered` (same files) refuses a waiting-page item, and a chat question box, whose options leave exactly one that does not widen: the ruling already chose it, so the question is refused with or without a pick. Built by step `widening-question-not-asked`. It also refuses a question that asks the owner to revisit this ruling; he raises a revisit himself in chat (owner, 2026-11-12 15:46 CST, page item 643 a).
  - It judges an open decision of two or more options, from the `widens` mark (page) or the ruling's words in the option (chat). A closed item passes, as in rule `question-form`.
  - An item whose options all widen passes it and is left to `uniform-pick`.
  - Cost and limits: as for `uniform-pick`.
- Call judge (`hooks/call_judge.py`, a model, rule `question-judge`): on an `ArtifactData` set or update of a waiting-page item that carries `options`, the one model prompt adds `WIDENING_RULE`. The model is told to refuse an option that widens a shared tool and lacks the mark, and to name the option key in its reason. The mark is `WIDENS_KEY` in `hooks/question_form.py`, set to the JSON boolean `true`. Code does not check that the key is named. Like every call-judge verdict, it fails open on a model error or timeout. Owner ruling, 2026-11-03 22:28 CST. It adds text to the model call the judge already makes, so it adds no model call or process.
- Reply judge (`hooks/reply_judge.py`, a model, never blocks): it flags a reply whose recommended option widens a shared tool, and a widening option offered without the label. It runs on the Stops it already judges, so it adds no model call.
- A shared check that today lets one repo's variant through is a debt to remove (debt `layout-legacy-repos`).

Incident:

- 2026-10-27 12:51 CDT: a waiting-page item recommended loosening a shared tool so it would accept banchi's record titles.
- 2026-11-01 11:43 CST: the card text quoted a bare topic id (rule `speak-cite-id-plus-gloss`). The card now says the ruling in plain words.
- 2026-11-07 15:38 CST (item 376): a page question whose only change from main was a widening option. It was withdrawn 15:41 CST. Rule `uniform-answered` refuses that shape.

Kind: process
Home: rule:style-question-form
