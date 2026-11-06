# The link step knows only the `@/` alias at the repo root

- **What.** The opt-in link step of code-check (`mjs-link`) maps only `@/x` to `x` at the repo root. A tsconfig `paths` entry such as `"@/*": ["./src/*"]` or `"~/*"` reads as a missing module, though tsx resolves it.
- **Where.** `actions/code-check/link_check.mjs`, the specifier resolution.
- **Decision.** none
- **Retire.** The link step reads the repo's tsconfig `paths` for `.ts` roots, and a `LinkStep` test with `"@/*": ["./src/*"]` is green.
