# Code Quality and Linting

- **Adhere to Code Quality Standards:** Ensure all modifications comply with both general and language-specific linting rules.
- For Markdown files, ensure:
  - Fenced code blocks have language specified
  - Emphasis uses asterisks (`*text*`) not underscores (`_text_`)
  - Headers follow proper hierarchy
  - Links are properly formatted
- For code files, follow language-specific linting rules
- Use `read_lints` tool or IDE linter integration to check for issues

## Python

- **Avoid `_` prefixes on module-level helpers.** A single leading underscore is
  a convention signaling "internal", but it has no enforcement effect — it only
  suppresses `from module import *` export, which is irrelevant in scripts. Do
  not add it unless there is a concrete reason worth explaining.

- **Never use `**kwargs` as a lazy catch-all in function signatures.** It
  swallows typos silently, destroys IDE autocompletion, makes type checking
  impossible, and forces callers to read the source to know what arguments are
  actually accepted. Every parameter a function uses must be declared explicitly
  with a name and type annotation. The only legitimate uses of `**kwargs` are
  genuine pass-through wrappers (e.g. decorators, `__init_subclass__`) where
  the set of accepted keys is intentionally delegated to another function.

- **Use `__` (name mangling) only inside class bodies, and only when subclass
  collision is a real concern.** Inside a class, `__name` is rewritten by the
  interpreter to `_ClassName__name`, preventing accidental override in
  subclasses. This is a real mechanical effect. Outside a class (module level),
  `__name` has no special behaviour — it is just a name with underscores. When
  name mangling is intentionally used, explain why in the docstring so the
  reason is not lost.
