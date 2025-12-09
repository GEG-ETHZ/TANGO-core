# 🚀 Antigravity Rules & Conventions

This document defines the strict rules and conventions that the Antigravity
Agent must follow when working on this repository.

## Commit Workflow & Permissions

- **Never Auto-Commit**: You are strictly forbidden from committing changes
  automatically without explicit user approval.
- **Suggestion Workflow**: When you are ready to commit, you must propose the
  commit to the user by providing 3 distinct commit message options:
  1. **Verbose**: A detailed explanation of *what* and *why*.
  2. **Brief**: A concise summary suitable for a quick scan.
  3. **Short**: A one-line message (Subject only).
- **Wait for Instruction**: You must wait for the user to select an option or
  provide their own message before running `git commit`.

## Commit Message Format

All commit messages MUST follow the Conventional Commits specification with
emoji placed after the scope.

### Format

```text
<type>(<scope>): <emoji> <description>

[optional body]

[optional footer(s)]
```

### Examples

- `feat(provisioning): 🎉 implement lazy password loading`
- `fix(nginx): 🔧 correct heredoc delimiter`
- `refactor(common): ♻️ improve error handling`
- `docs(readme): 📝 update installation instructions`
- `chore(deps): ⬆️ update dependencies`

### Type

- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools
- `ci`: Changes to CI configuration files and scripts

### Scope

The scope should be a short description of the area of the codebase affected
(e.g., `provisioning`, `nginx`, `common`, `postgresql`).

### Emoji

Place an appropriate emoji immediately after the scope and colon. Choose emojis
that represent the nature of the change. The following emojis are available
from the [gitmoji project](https://github.com/carloscuesta/gitmoji):

#### By Commit Type (Common Mappings)

- **feat**: ✨ `:sparkles:` - Introduce new features
- **fix**: 🐛 `:bug:` - Fix a bug
- **docs**: 📝 `:memo:` - Add or update documentation
- **style**: 🎨 `:art:` - Improve structure / format of the code
- **refactor**: ♻️ `:recycle:` - Refactor code
- **perf**: ⚡️ `:zap:` - Improve performance
- **test**: ✅ `:white_check_mark:` - Add, update, or pass tests
- **build**: 📦 `:package:` - Add or update compiled files or packages
- **ci**: 👷 `:construction_worker:` - Add or update CI build system
- **chore**: 🔧 `:wrench:` - Add or update configuration files
- **revert**: ⏪️ `:rewind:` - Revert changes

#### Complete Gitmoji List

- 🎨 `:art:` - Improve structure / format of the code
- ⚡️ `:zap:` - Improve performance
- 🔥 `:fire:` - Remove code or files
- 🐛 `:bug:` - Fix a bug
- 🚑️ `:ambulance:` - Critical hotfix
- ✨ `:sparkles:` - Introduce new features
- 📝 `:memo:` - Add or update documentation
- 🚀 `:rocket:` - Deploy stuff
- 💄 `:lipstick:` - Add or update the UI and style files
- 🎉 `:tada:` - Begin a project
- ✅ `:white_check_mark:` - Add, update, or pass tests
- 🔒️ `:lock:` - Fix security or privacy issues
- 🔐 `:closed_lock_with_key:` - Add or update secrets
- 🔖 `:bookmark:` - Release / Version tags
- 🚨 `:rotating_light:` - Fix compiler / linter warnings
- 🚧 `:construction:` - Work in progress
- 💚 `:green_heart:` - Fix CI Build
- ⬇️ `:arrow_down:` - Downgrade dependencies
- ⬆️ `:arrow_up:` - Upgrade dependencies
- 📌 `:pushpin:` - Pin dependencies to specific versions
- 👷 `:construction_worker:` - Add or update CI build system
- 📈 `:chart_with_upwards_trend:` - Add or update analytics or track code
- ♻️ `:recycle:` - Refactor code
- ➕ `:heavy_plus_sign:` - Add a dependency
- ➖ `:heavy_minus_sign:` - Remove a dependency
- 🔧 `:wrench:` - Add or update configuration files
- 🔨 `:hammer:` - Add or update development scripts
- 🌐 `:globe_with_meridians:` - Internationalization and localization
- ✏️ `:pencil2:` - Fix typos
- 💩 `:poop:` - Write bad code that needs to be improved
- ⏪️ `:rewind:` - Revert changes
- 🔀 `:twisted_rightwards_arrows:` - Merge branches
- 📦️ `:package:` - Add or update compiled files or packages
- 👽️ `:alien:` - Update code due to external API changes
- 🚚 `:truck:` - Move or rename resources (e.g.: files, paths, routes)
- 📄 `:page_facing_up:` - Add or update license
- 💥 `:boom:` - Introduce breaking changes
- 🍱 `:bento:` - Add or update assets
- ♿️ `:wheelchair:` - Improve accessibility
- 💡 `:bulb:` - Add or update comments in source code
- 🍻 `:beers:` - Write code drunkenly
- 💬 `:speech_balloon:` - Add or update text and literals
- 🗃️ `:card_file_box:` - Perform database related changes
- 🔊 `:loud_sound:` - Add or update logs
- 🔇 `:mute:` - Remove logs
- 👥 `:busts_in_silhouette:` - Add or update contributor(s)
- 🚸 `:children_crossing:` - Improve user experience / usability
- 🏗️ `:building_construction:` - Make architectural changes
- 📱 `:iphone:` - Work on responsive design
- 🤡 `:clown_face:` - Mock things
- 🥚 `:egg:` - Add or update an easter egg
- 🙈 `:see_no_evil:` - Add or update a .gitignore file
- 📸 `:camera_flash:` - Add or update snapshots
- ⚗️ `:alembic:` - Perform experiments
- 🔍️ `:mag:` - Improve SEO
- 🏷️ `:label:` - Add or update types
- 🌱 `:seedling:` - Add or update seed files
- 🚩 `:triangular_flag_on_post:` - Add, update, or remove feature flags
- 🥅 `:goal_net:` - Catch errors
- 💫 `:dizzy:` - Add or update animations and transitions
- 🗑️ `:wastebasket:` - Deprecate code that needs to be cleaned up
- 🛂 `:passport_control:` - Work on code related to authorization, roles and permissions
- 🩹 `:adhesive_bandage:` - Simple fix for a non-critical issue
- 🧐 `:monocle_face:` - Data exploration/inspection
- ⚰️ `:coffin:` - Remove dead code
- 🧪 `:test_tube:` - Add a failing test
- 👔 `:necktie:` - Add or update business logic
- 🩺 `:stethoscope:` - Add or update healthcheck
- 🧱 `:bricks:` - Infrastructure related changes
- 🧑‍💻 `:technologist:` - Improve developer experience
- 💸 `:money_with_wings:` - Add sponsorships or money related infrastructure
- 🧵 `:thread:` - Add or update code related to multithreading or concurrency
- 🦺 `:safety_vest:` - Add or update code related to validation
- ✈️ `:airplane:` - Improve offline support

### Body and Footer

- Use the body to explain the *what* and *why* vs. the *how*
- Reference issue numbers in the footer
- Use `BREAKING CHANGE:` in the footer for breaking changes

---

## Running Python
- make sure that either the `.pixi/envs/dev` environment is active or that you
  run commands with `pixi run -e dev ...`

---

## Code Quality and Linting

- Don't worry about linting and quality in Python code.  It's so bad that it
  needs careful attention.  When the main developer has had a chance to get it
  whipped into shape, then this section will be updated.  Feel free to pester
  the main dev about this section if it has not been updated.

---

## Date Handling in Documents

- **Always check the current date** before adding dates to documents
- Use `date +"%B %d, %Y"` command to get the current date in a consistent format
- Update "Analysis Date", "Last Updated", "Report generated on", and similar
  date fields with the actual current date
- Do not hardcode dates or assume the current date without verification
- When creating PDFs with dates, ensure the date in the document matches the
  actual generation date

---

## Capability Scopes & Permissions

### 🌐 Browser Control

- **Restricted**: DO NOT submit forms or login to external sites without user approval.

### 💻 Terminal Execution

#### Host Machine

- **Restricted**: NEVER run `rm -rf`, use `sudo`, or modify system-level
  configuration (e.g., `/etc/`) without explicit approval.

---

## Dependency Management

### Python

- Add new python dependendcies in the dependendcies section of pyproject.toml
  unless you have explicit approval otherwise.

---

## Pre-approved Auto-Run Commands

The following commands are considered safe and should be executed with
`SafeToAutoRun: true`:

- `git status`
- `git diff`
- `git log`
- `ls`
- `cat`
- `grep`
- `find`
- `pwd`
- `npx markdownlint-cli`
