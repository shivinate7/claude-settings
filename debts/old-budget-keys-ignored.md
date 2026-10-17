# Removed budget keys are dropped silently

- **What.** `load_config` keeps only the keys of `DEFAULT_CONFIG`. `max_words_procedural` and `max_words_descriptive` are no longer keys. A `.ste.json` or `.ste.toml` that sets one is ignored with no message. A repo that bumps its pin of `actions/ste-lint` gets the 30-word budget with no notice. A tighter budget loosens and a looser one tightens. This repo has no `.ste.json`. q_max and banchi are unmeasured.
- **Where.** `load_config` in `lint/ste_lint.py`.
- **Decision.** `plain-prose-lint` (the STE lint becomes a plain-prose lint).
- **Retire.** `load_config` prints a notice on stderr for each removed key, and a test pins the notice. Or q_max and banchi are read and set neither key.
