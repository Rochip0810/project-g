# Security Policy

## Reporting a security issue

Do not place sensitive security details, credentials, tokens, exploit steps, or private configuration in a normal GitHub Issue.

When a credential leak is suspected:

1. Stop the affected function.
2. Revoke or rotate the credential immediately.
3. Preserve relevant audit logs.
4. Check for unauthorized access or publication.
5. Correct the root cause.
6. Resume only after verification.

## Sensitive information that must never be committed

- API keys
- Passwords
- Access tokens
- Refresh tokens
- OAuth credentials
- Cookies
- Private keys
- Production database connection strings
- Production SNS account credentials

## Supported version

During Phase 0, only the latest commit on the protected `main` branch is supported.

## Emergency principle

When safety cannot be verified, publishing must remain disabled.
