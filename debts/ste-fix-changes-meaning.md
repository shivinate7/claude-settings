# Some STE autofixes change the meaning

- **What.** Some autofixes change meaning. `It's all been fixed` becomes `It is all been fixed`. `ad hoc` becomes `unplanned`. `in between` becomes `between`. `in terms of` becomes `for`. `it would appear that` becomes `apparently`. `IT'S A TEST` becomes `It is A TEST`. `Don't Trust` becomes `Do not Trust`.
- **Where.** The fixed-word table in `lint/ste_gate.py`.
- **Decision.** `ste-gate-fixes-not-nags` (the STE gate fixes text, not nags).
- **Retire.** Each fix keeps the meaning, or it is removed. A test per example pins the fixed text.
