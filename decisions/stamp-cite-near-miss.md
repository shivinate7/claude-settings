# The stamp action flags a near-miss cite

The stamp action flags a cite that uses a record's prefix and a known slug in the wrong
wrapper. A brief names the cite form for each record kind.

## The question

Where does the check for a wrongly wrapped cite live, and how does an agent learn the right form?

## The incident

Sessions wrote cites such as D`slug`, with inline-code backticks. The dangling-cite check
did not see them, because no cite pattern matched. The stamp then did not rewrite them to
numbered ids, so the cites stayed broken on main.

## The ruling

Owner ruling, 2026-10-13.

- The check lives in the stamp action, so every adopting repo gets it.
- An optional `cite.form` config field holds the form, such as `{prefix}‹{slug}›`. The remedy names it.
- Inline code stays flagged. A doc that must show the wrong form puts it in a fence.
- `hooks/agent_brief.py` adds one cite-form line per record kind to each agent brief. It reads the repo's stamp config.
- claude-sharables drops its own copy of the check later, in that repo.

Fences follow CommonMark. A fence opens at 0 to 3 columns past the content column of its
list item or blockquote. A tab counts to the next multiple of 4. A top-level fence indented
4 or more is an indented code block, so it gives no protection.

## Holes, named

Debts: `stamp-quote-fence-closes-early` (`>code` closes a fence early). `stamp-list-fence-not-seen` (a fence in a list item at 4 or more columns). `stamp-list-marker-column` (some list markers set a content column). `stamp-blank-line-quote-fence` (a blank line does not end a quoted fence). `stamp-html-comment-hides-file` (a fence in an HTML comment hides the file). `stamp-scan-frontmatter-links` (the near-miss scan reads frontmatter and links).

Each is low harm. None is a regression against main.

Kind: process
Home: actions/stamp/stamp.mjs
