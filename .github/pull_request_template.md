## What and why

<!-- One paragraph: what this changes and the problem it solves. Link the issue. -->

Closes #

## How it was checked

<!-- The commands you ran and what they showed. "just check" is the minimum. -->

- [ ] `just check` passes (format, lint, mypy strict, unit tests)
- [ ] The pre-push hook passed (regression tests)
- [ ] Ran it for real: <!-- config or app, and the result -->

## Checklist

- [ ] Follows the [TANGO commandments](https://github.com/GEG-ETHZ/TANGO-core/blob/main/CONTRIBUTING.md#tango-commandments)
- [ ] New or changed behavior has a test that fails without the change
- [ ] Docs that draw the changed code are updated (`docs/architecture/`, `docs/runtime/`, package READMEs)
- [ ] `CHANGELOG.md` entry under `[In Development]`, if users notice the change
- [ ] `just docs-build` passes, if docs changed
