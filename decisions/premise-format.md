# A premise names its source

## Question

How does a session write down a fact its work leans on, so that a weak source is checked before anyone acts on it?

## Ruling

A premise is a claim, not a fact. It is one line: `- P<n> [<kind>] <claim>. Source: <where>. Checked <date or never>.` The kind says how far the source is trusted. The kinds, strongest first:

| Kind | Means | Strength |
|---|---|---|
| `ruling` | The owner said it. Names the date and the home (a decision, a debt, or NO HOME YET). | Strong |
| `measured` | A command ran and showed it. Names the command, the time, the commit, and the log while one exists. | Strong while the commit is current for the files it covers |
| `read` | Read in a file. Names `path:line` and the commit. | Strong while that file has not changed since the commit |
| `notes` | From a handoff, a summary, a digest, memory, a brief, a roadmap note, or an agent report not yet checked. | Weak |
| `assumed` | No source. | Weak |

- Every fact in a compaction summary counts as `notes` until checked.
- A `read` or `measured` premise goes stale when its files change. Cheap check: `git log <commit>..HEAD -- <path>` prints nothing.
- Act on a weak or stale premise only after a check upgrades it. A check that confirms a premise rewrites its line with the new source and date. A check that refutes it deletes the line or replaces it with the true fact and its source. Keep no "was wrong" note. Fix the same fact in any brief, decision or plan that holds it. If work already rested on it, say so under Deviations in the next report.
- A premise that becomes a ruling moves to its home. The premise line then cites that home as `ruling`.
- A kind outside this table is weak: the handoff reorient lists it with the weak ones.
- One home. The table above is the meaning of each kind. `PREMISE_KINDS` in `hooks/precompact_handoff.py` is the list the parser reads, and a test keeps it equal to this table. The kinds run strongest first, and the first one is the kind a compaction reorient leaves out of its list. The one other copy is in `hooks/precompact_handoff_prompt.md`: an installed prompt cannot point at `decisions/`, so it lists the kinds itself, and a test keeps it equal to this table.

Owner, 2026-10-21: the handoff holds the premises. Raw evidence lives in the record that uses it.

Reason: after a compaction every belief arrives with no source, so a guess reads like a measurement.

Kind: process
Home: hooks/precompact_handoff.py
