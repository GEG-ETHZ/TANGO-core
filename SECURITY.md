# Security policy

Security fixes go into the latest release tag and into `main`; older tags are not patched.

## Reporting a vulnerability

Report it privately through GitHub: **Security → Report a vulnerability** ([direct link](https://github.com/GEG-ETHZ/TANGO-core/security/advisories/new)). Describe the problem, the affected version or commit and how to reproduce it; describe secrets or confidential data rather than attaching them. Expect an acknowledgement within five working days. Do not use an issue, a pull request or a chat channel.

In scope: the `tango` package and its command line, the scripts in `applications/` and `tools/`, and the CI and docs workflows. Vulnerabilities in third-party dependencies that TANGO does not expose go upstream.

TANGO and its outputs are confidential (see [`NOTICE`](NOTICE)). Credentials, confidential site data and results derived from them never enter the repository; if some did, report it as above, since removing it from the history takes a maintainer.
