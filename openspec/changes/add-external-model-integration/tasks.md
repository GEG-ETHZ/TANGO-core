# Tasks

## 1. Partner change template

- [ ] 1.1 Write the partner change template: proposal and design headings, the readiness checklist (design D2) as tasks with an "authors / TANGO team" owner field, and the open-questions section. Decide where it lives (design open question 2). Verify by using it for RevORC (`prepare-for-tango-coupling` in the RevORCHP-SM repository).

## 2. Documentation

- [ ] 2.1 Add `src/tango_core/external/README.md`: how to add a coupling, step by step, linking the spec and the RAFT and RevORC couplings as examples.
- [ ] 2.2 Update `.agent/rules/external-coupling.md` to point to the spec for requirements and process, keeping its principles and RAFT examples.
- [ ] 2.3 Run `just docs-build`.

## 3. RAFT against the spec

- [ ] 3.1 Audit the RAFT coupling against every requirement. Record each gap in `.agent/FINDINGS.md` (for example: no backend protocol; whether RAFT's repository has the readiness items); fix none here.

## 4. Archive

- [ ] 4.1 After review, archive the change so the spec moves to `openspec/specs/external-model-integration/spec.md`.
