# README

Write the best README the repo can have, and apply the ladder in SKILL.md to every claim in
it.

## Content

- Write for the person the software serves. The first screen answers three questions: what
  is this, who is it for, and how do I get the first result.
- Use plain, short words. Explain each technical term in everyday words, or drop it.
- Include only what a new user or contributor needs in their first hour. Everything else gets
  one link to its real home: the docs, `--help`, the config schema, CHANGELOG, or the decision
  records.
- Give each fact one home. If the code, a config file, or another doc already states a fact,
  link to it or generate it. Never copy it.
- Omit things that rot or that nobody acts on: badge walls, a roadmap, "coming soon",
  contributor lists, feature lists that repeat the docs, and a table of contents for a short
  file.

## Section order

Drop a section that is empty.

1. Name and one sentence: what the software is, and the result it gives.
2. Status, one line: working, experimental, or archived.
3. Quick start: the shortest path to a working result, with every command copy-pasteable.
4. Usage: only the common tasks.
5. Configuration: generated from its source, if it has one.
6. Development: how to run the tests, and the one command that proves a change works.
7. More: links out.
8. License.

## Applying the ladder

- Rung 4, run it: CI runs each Quick start and Development command in a clean checkout. Mark
  which blocks run.
- Rung 5, check it: check a repo path or relative link on every PR. Check an external link on
  a weekly schedule, not on every PR, so a flaky site never turns a PR red.

## Proof of done

- The README renders cleanly on GitHub. Check the headings, tables, and code blocks.
- List every claim you deleted, every claim you replaced with a link, and every claim you
  left unchecked, with the reason.

If a fact about the repo is unclear, ask. Never guess it.
