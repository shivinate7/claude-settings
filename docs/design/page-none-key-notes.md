# Waiting page none-key block, step option-key-guard-gap: design notes

Mockup: `docs/design/page-none-key.html`. Screen: `skills/waiting-page/page.html` at 72034d9a, `problem`, the line that tests
`ks.includes(NONE)`. Its CSS (lines 8–773) is copied whole. Only `#newcss` is new.
Deep links: `#s=named|long|nolabel|marked|askfix|today`, `&w=all|390|800|1280`, `&t=light|dark`, `&lab=off`, `&hide=marked,askfix`.
Sizes: 390, 800 and 1280, which are page.html's bands (`layout.py devices` prints `unknown`). Themes: light and dark.
Incident: Nov 2 12:15 and 12:25 CST. The block said "An option of this decision uses the key none", and the owner had to ask which option.

## 1. The words (pick), states `named`, `long` and `nolabel`, focus `#noneMsg`

- New: `Option B, "Keep search at the top", has the key none. The page keeps that key for "None of these", so this decision cannot be answered.`
  Then today's `fix` sentence: "Ask the session to fix item 12."
- The letter comes from `letterOf`, the same letter the option card shows. The label comes from `pickName`, which cuts at 28 characters, as the sent panel does (`long`).
- With an empty or missing label, the words name the letter only: "Option B has the key none." `pickName` runs `String(o.label)`, which would print "undefined",
  so the builder checks for a string first (`nolabel`).
- At most one option can hold the key none when this line runs. The check for two options with the same key runs first and blocks first.
- Kept: `.status.broken`, `role="alert"`, `blocks: true`, and its place under the title (`buildCard`).
- Gain: the owner sees which option to name in the fix. Loss: a longer line.

## 2. Ring the option too (hide: "rings the option"), state `marked`, focus `#noneOpt`

- The option card with the key none gets the due ring and a "Key none" tag under its head.
- Gain: the eye finds the option on a long card. Loss: one more class in `optCard`, and a second red mark on the card.
- Departs from: `optCard`, which marks no option for a defect. Owner grant: no. It changes no rule.

## 3. Ask to fix (hide: "Ask to fix"), state `askfix`, focus `#noneAskFix`. Owner grant: yes

- A button in the block puts "Item 12: option B has the key none. Please give it another key." in the Ask box. It does not send.
- Gain: the block leads on with a control (ux-no-dead-end). Today it ends with prose. Loss: a second control in a warning, and it applies to this block only.
- Departs from: `problem`, which returns only words. The same control could serve every blocking defect. That is a wider change.

## 4. Today, state `today`

- Today's words, drawn for comparison.

## 5. Out of scope here

- The guard gap (`question_form.py`, `option_letter_hit`) has no screen. That fix is the builder's.

## 6. Measured verdicts

Headless Chrome, every state at 390, 800 and 1280, in light and dark. Checks: no sideways scroll, no element past the page edge,
and every card button at least 44 px high. All pass.
