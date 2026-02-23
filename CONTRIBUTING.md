# Contributing

## Branch Naming Conventions
### Persistent Branches
- `main` — production-ready code
- `develop` — integration branch for ongoing work
### Topic Branches
- `dev/<feature>` — feature branches (e.g., `dev/fix-convergence`)
- `fix/<issue>` — bug fixes
- `exp/<name>` — experimental/throwaway work

All merges into `main` should be peer reviewed and merged via gitlab
Merge Request.  Short term work should generally be done in [Topic
Branches](#Topic-Branches) peer reviewed and merged either into `develop` or
directly into `main` via gitlab Merge Request, depending on guidance from TANGO
lead developer (Chad Baker). In some cases, per case-specific guidance from
TANGO lead developer (Chad Baker), work can be done directly in teh `develop`
branch.
