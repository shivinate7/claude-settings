# The source-prose scanner lacks two required test shapes

- **What.** Rule `building-scanner-respects-strings` asks each scanner for two test shapes. One is a multi-line template literal. The other is a lone quote in text, such as JSX `<p>Don't</p>`. The source-prose mode of `ste_lint.py` has no case for either shape.
- **Where.** `Linter.check_source` in `lint/ste_lint.py`; `SourceProseLintTests` in `lint/test_gates.py`.
- **Decision.** `test-strategy-reset` (each kept test names the real failure it catches).
- **Retire.** One case for each shape, each shown red on a scanner that ignores it.
