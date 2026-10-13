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

Review round 3 left these open. Each is low harm and is no regression against main.

- A quoted fence line `>code`, with no space after `>`, closes the fence early. That line can give a false alarm.
- A blockquote fence inside a list item at 4 or more columns is not seen as a fence.
- Some list markers that CommonMark does not open still set a content column, such as `* * *` or `2.` after a paragraph line.
- A blank line with no `>` inside a quoted fence does not end the quote.
- A fence inside an HTML comment hides the rest of the file. Main has the same hole.
- The near-miss scan does not skip frontmatter or link targets.

Kind: process
Home: actions/stamp/stamp.mjs
