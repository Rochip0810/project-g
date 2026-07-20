# GitHub setup checklist

## Repository creation

- [ ] Sign in to GitHub
- [ ] Select **New repository**
- [ ] Repository name: `project-g`
- [ ] Visibility: **Private**
- [ ] Do not add an auto-generated README, .gitignore, or license
- [ ] Create the repository

## Upload the starter files

Preferred local method:

```bash
git clone <YOUR_PRIVATE_REPOSITORY_URL>
cd project-g
```

Copy the contents of this starter package into the cloned directory, then:

```bash
git checkout -b chore/foundation-001-repository-setup
git add .
git commit -m "chore: initialize private repository"
git push -u origin chore/foundation-001-repository-setup
```

Create a Pull Request into `main`.

## Main protection

In repository settings, configure a ruleset or branch protection rule for `main`:

- [ ] Require a Pull Request before merging
- [ ] Block force pushes
- [ ] Block branch deletion
- [ ] Require conversation resolution when available
- [ ] Require status checks after CI is added in FOUNDATION-014
- [ ] Do not allow bypass except emergency administration

## Final verification

- [ ] Pull Request template appears
- [ ] Issue forms appear
- [ ] Repository is private
- [ ] `.env` is ignored
- [ ] `.env.example` contains no secret values
- [ ] Production publishing is disabled
