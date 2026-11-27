# Tasks

## 1. Partner change template

- [x] 1.1 First partner change written as the worked example: `prepare-for-tango-coupling` in the RevORCHP-SM repository (design open question 2).

## 2. Documentation

- [ ] 2.1 Add `src/tango_core/external/README.md`: how to add a coupling, step by step, linking the spec and the RAFT and RevORC couplings as examples.
- [ ] 2.2 Update `.agent/rules/external-coupling.md` to point to the spec for requirements and process, keeping its principles and RAFT examples.
- [ ] 2.3 Run `just docs-build`.

## 3. RAFT against the spec

- [ ] 3.1 Audit the RAFT coupling against every requirement. Record each gap in `.agent/FINDINGS.md` (for example: no backend protocol; whether RAFT's repository has the readiness items); fix none here.

## 4. Archive

- [ ] 4.1 After review, archive the change so the spec moves to `openspec/specs/external-model-integration/spec.md`.
