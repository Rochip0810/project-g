# Contributing to Project G

## Development flow

```text
Issue
→ Feature branch
→ Implementation
→ Tests
→ Pull Request
→ Review
→ Merge
```

## Branch names

Use one of the following prefixes:

```text
feature/
fix/
docs/
chore/
hotfix/
```

Examples:

```text
feature/add-health-api
fix/prevent-duplicate-job
docs/update-database-blueprint
```

## Commit messages

Use:

```text
type: short description
```

Allowed types:

```text
feat
fix
docs
test
refactor
security
chore
ci
build
revert
```

Example:

```text
docs: add Project G repository rules
```

## Pull requests

Every Pull Request must:

- Link to an Issue.
- Describe the purpose and changed scope.
- State what is intentionally out of scope.
- Include tests when executable behavior changes.
- Confirm no secrets are included.
- Confirm Project G Blueprint consistency.
- Include a rollback approach for operational changes.

## Prohibited actions

- Direct push to `main`
- Committing secrets
- Disabling Fact Check or Safety Check
- Changing database schemas without a migration
- Adding dependencies without explaining why
- Expanding MVP scope without an approved design change
- Allowing development code to access production SNS credentials

## AI-generated changes

AI-generated code and documents follow the same review and test requirements as human-generated changes.
