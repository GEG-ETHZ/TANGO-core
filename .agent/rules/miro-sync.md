# Issue, Task & Miro Sync

How to sync this repo's issue tracker, its local task docs, and the team's
Miro board. Read this before doing any "sync TANGO" work.

## Issue tracker

GitHub issues on `GEG-ETHZ/TANGO-core` are the only tracker. Access them with
`gh` (e.g. `gh issue list -R GEG-ETHZ/TANGO-core`) or a GitHub MCP server whose
token is scoped to this repo. A token scoped to other repositories returns 404
here: that is a token-scope problem, not a missing repo.

## Local task docs

- `docs/tango_tasks.md`: granular, frequently updated working task list.
  In-flight, multi-step work is tracked here across sessions.
- `docs/TANGO_vision_and_roadmap/README.md`: the durable narrative doc; its
  Phase 3 task list is the reconciled, high-level counterpart to
  `tango_tasks.md`.
- **Reconciliation practice:** when a `tango_tasks.md` entry is fully done,
  fold a one-line summary into the vision doc's Phase 3 list, then prune the
  detail out of `tango_tasks.md`.

## Miro board

The team keeps a TANGO project board in Miro. Ask a board maintainer for the
link and access.

- The board is large. Scope every read or write with `canvas_search` first;
  never attempt an unscoped full-board read.
- Its "Start Here" doc has a **Repos** section. Keep its repository link
  identical to this repo's GitHub URL.
- Some widgets were set up through the Miro UI and cannot be recreated
  through MCP tools. If one looks broken, ask a board maintainer instead of
  rebuilding it.

## Diagrams on the board

- Put draw.io diagrams on the board with Miro's **draw.io plugin**, not as
  native Miro shapes or static PNGs. The source of truth stays in
  `docs/diagrams/src/*.drawio` (topology diagrams), `tools/diagrams/` (the
  generated `docs/diagrams/*.drawio.svg`), or `docs/archive/diagrams/*.drawio`
  (archived developer diagrams): edit it there and re-import, so the board
  copy doesn't drift from the repo.
- The plugin drops the embed wherever the viewport happens to be, often
  small and outside any frame. After inserting, check its size and position
  and move it into the right frame.
- To find a lost embed, `canvas_search` in `matches` mode for
  `re:type="external_diagram"`, then link to it with `?moveToWidget=<id>`.

## What "sync" means here

1. Pull open issues from GitHub (`GEG-ETHZ/TANGO-core`).
2. Cross-reference them against `docs/tango_tasks.md` and the vision doc's
   Phase 3 list. Add anything missing; flag (don't silently drop) anything
   that looks stale or already closed.
3. Cross-reference the same issues against the board's Gantt and kanban
   content. Add or update rows to match; confirm with a board maintainer
   before deleting or removing rows.
4. Keep the board's **Repos** link identical to this repo's GitHub URL.
