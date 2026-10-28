# c148-port-keeps-behaviour (a port keeps the existing app's behaviour)

- Status: green, reviewed, draft PR #747. Head 322213ba on c148-port-keeps-behaviour.
- Built: rule building-port-keeps-behaviour (port keeps behaviour); questions-go-to-owner reads standing grants from the repo's CLAUDE.md first; guard rule port-question refuses a waiting-page item on a port with no "Departs from:" line, or with `holds`; the reply judge judges every "blocked on" Stop and notes a blocked port question; decision port-keeps-behaviour; one line each in the designer, builder and plan agents; waiting-page skill updated.
- Red first: guard family port-question 10 of 24 red on old code; reply judge 4 of 49 red. Round 2 re-reds: 6 of 32, and 1 of 49.
- Green: ci-job gates --lint, test_reply_judge, GUARD_FAMILY=port-question, ste-changed, silent-undo strict.
- Review: round 1 (reviewer opus) asked for changes: a false alarm on any `items` write, an STE lint failure, a narrower set of port words, and the costs recorded. Round 2 (reviewer sonnet) approved. Builder sonnet. No net-value test was needed: the change finished in two rounds.
- Notes (docs/debts/notes.md): the url-form match, the untested cwd forms, the "redesign" word.
- Known limits (in the record): the incident's own wording ("Duo version of the web screen") passes the guard, and the reply judge is the backstop; an update cannot see the stored `port` field.
- Full test_guard: 1 red, `load-brake: probe control`, which also fails on origin/main (the reviewer checked). It is not this lane's failure.
