# Dependabot runs security updates only

## The ruling

Owner, 2026-10-16: security updates only.

- Dependabot alerts and security updates are on in the repo settings.
- `.github/dependabot.yml` ignores every version update (major, minor, patch) for GitHub Actions, so only a security fix opens a PR.
- Renovate (`renovate.json`) bumps only the skill version pins. The two tools do not overlap.

Why: a version bump that fixes nothing costs a review and a CI run. A security fix is worth both.

Kind: process
Home: .github/dependabot.yml
