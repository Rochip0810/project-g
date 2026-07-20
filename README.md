# Project G

AI-powered automated media platform for Yomiuri Giants fans.

## Status

Project G is currently in **Phase 0: Foundation**.

Current target release:

- Version: `v0.1.0`
- Current issue: `FOUNDATION-001`
- External SNS publishing: disabled

## Vision

> AIで一番面白い巨人専門メディアを作る。

## Mission

> AIの力で、野球をもっと面白くする。

## MVP flow

```text
Trusted Giants information
→ Story
→ AI analysis
→ X post draft
→ Fact Check
→ Safety Check
→ Human approval
→ X publication
→ Analytics
```

## Important safety rules

- Never commit API keys, passwords, tokens, cookies, or production credentials.
- Development and test environments must never publish to production SNS accounts.
- Fact Check and Safety Check may not be bypassed.
- Direct pushes to `main` are not allowed.
- All changes must use an Issue and Pull Request.

## Documentation

Blueprint documents will be stored under:

```text
docs/blueprint/
```

## Development

The executable development environment will be added during the remaining Phase 0 issues.

See:

- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [CHANGELOG.md](CHANGELOG.md)
