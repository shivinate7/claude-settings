# Dependabot runs security updates only

Kind: process
Home: .github/dependabot.yml

## The question

Which dependency updates does Dependabot open for this repo?

## The ruling

Owner, 2026-10-16: security updates only. On 2026-10-17 the settings already matched.

- Dependabot alerts and Dependabot security updates are on in the repo settings.
- `.github/dependabot.yml` ignores every version update (major, minor and patch) for GitHub Actions, so only a security fix opens a PR.
- Renovate (`renovate.json`) bumps only the skill version pins. The two tools do not overlap.

## Why

A version bump that fixes nothing costs a review and a CI run. A security fix is worth both.
