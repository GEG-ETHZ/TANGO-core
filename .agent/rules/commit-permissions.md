# Commit Workflow & Permissions

- **Never Commit**: Do not commit changes unless the person asks.

GEG uses the conventional commit specification, summarized below. No emoji.

## Format

```text
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

## Examples

- `feat(provisioning): implement lazy password loading`
- `fix(nginx): correct heredoc delimiter`
- `refactor(common): improve error handling`
- `docs(readme): update installation instructions`
- `chore(deps): update dependencies`

## Type

- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools
- `ci`: Changes to CI configuration files and scripts

## Scope

The scope is a short name for the area of the codebase affected (for example `orchestrators`, `docs`, `ci`).

## Subject, body and footer

- Subject in the imperative, under 72 characters, no trailing full stop.
- The body says why; the diff already shows what. Bullets, wrapped at 72.
- Reference issue numbers in the footer; use `BREAKING CHANGE:` for breaking changes.
- Nothing that needs the conversation to make sense, no agent or tool attribution.
- No absolute file paths. Bad: "Updated `/Users/an/git/projects/geg-backend/scripts/import.js`". Good: "Updated `import.js`" or "Fixed `geg-backend/scripts/provision.js`".
