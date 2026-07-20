# FOUNDATION-001: Create the private Project G repository

## Purpose

Create the protected private GitHub repository that will become the single source of truth for Project G design, code, prompts, tests, and operational documentation.

## Scope

- Create repository `project-g`
- Set visibility to Private
- Use `main` as the default branch
- Add the initial repository files
- Add Issue and Pull Request templates
- Configure protection for `main`
- Confirm no secrets are committed

## Out of scope

- Python package initialization
- Docker configuration
- Database configuration
- CI workflow implementation
- News collection
- AI features
- SNS integration

## Files

- `README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `CHANGELOG.md`
- `LICENSE`
- `.gitignore`
- `.editorconfig`
- `.env.example`
- `.github/pull_request_template.md`
- `.github/ISSUE_TEMPLATE/*`

## Acceptance criteria

- [ ] Repository name is `project-g`
- [ ] Repository visibility is Private
- [ ] Default branch is `main`
- [ ] Direct pushes to `main` are restricted
- [ ] Force pushes to `main` are disabled
- [ ] Deletion of `main` is disabled
- [ ] Pull Requests are required
- [ ] Initial files are committed
- [ ] Issue templates are available
- [ ] Pull Request template is displayed
- [ ] No secret or production credential is present
- [ ] `PUBLISHING_ENABLED=false` is shown in `.env.example`

## Verification

1. Open the repository in a private browser session while logged out.
2. Confirm the repository cannot be viewed.
3. Attempt to create a branch and Pull Request.
4. Confirm the Pull Request template appears.
5. Confirm Issue forms appear.
6. Review the commit for credential-like strings.
7. Confirm `main` protection settings.

## Related Blueprint

- ⑬ Security Design
- ⑮ GitHub Structure
- ⑯ CI/CD Structure
- ⑱ MVP Scope
- ⑲ MVP Development Roadmap
- ⑳ Phase 0 Implementation Plan
