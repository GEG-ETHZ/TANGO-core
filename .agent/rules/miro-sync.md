# Issue, Task & Miro Sync

How to sync this repo's issue trackers, its local task docs, and its Miro
board(s). Read this before doing any "sync TANGO" work.

## Remotes

- **GitHub** — `GEG-ETHZ/TANGO-core`
  (`git@github.com:GEG-ETHZ/TANGO-core.git`) — the canonical repository
  and the issue tracker: code, issues, pull requests, CI and releases.
  Access it with `gh` (e.g. `gh issue list -R GEG-ETHZ/TANGO-core`) or a
  GitHub MCP server whose token is scoped to this repo (a token scoped to
  other `GEG-ETHZ` repos returns 404 here — that is a token-scope problem,
  not a missing repo).
- **GitLab** — `geg/tango-projects/tango-core` on gitlab.ethz.ch — retired.
  Do not file new issues there; any still-open GitLab issues are migrated
  to GitHub issues.
- A sibling repo, `geg/tango-projects/tango-super`
  (`git@gitlab.ethz.ch:geg/tango-projects/tango-super.git`, no GitHub
  remote), shares the same TANGO board presence — check it too when doing
  a full TANGO sync, even though its own task docs/Miro presence aren't
  set up yet.

## Local task docs

- `docs/tango_tasks.md` — granular, frequently-updated working task list.
  Scratch-adjacent but checked in; this is where in-flight, multi-step work
  gets tracked across sessions.
- `docs/TANGO_vision_and_roadmap/README.md` — the durable, Confluence-bound
  narrative doc; its Phase 3 task list is the reconciled, high-level
  counterpart to `tango_tasks.md`.
- **Reconciliation practice:** when a `tango_tasks.md` entry is fully done,
  fold a one-line summary into the vision doc's Phase 3 list, then prune the
  detail out of `tango_tasks.md` — don't just let it grow forever.

## Miro board(s)

- **Dedicated TANGO project board** — <https://miro.com/app/board/uXjVOfwfxsY=/>
  (any TANGO dev with access to this board can carry out the sync below)
  - Large: ~2000+ widgets across ~80 frames. Always scope reads/writes with
    `canvas_search` first — never attempt an unscoped full-board read.
  - "Start Here" doc (widget id `3458764684563145500`) holds the **Repos**
    section — keep its repository link identical to this repo's actual
    remote (above).
  - "Gantt Chart" frame (widget id `3458764585326789646`) — large, ~127
    items.
  - A timeline widget (id `3458764679176539081`) was set up as a
    Miro-native "linked copy" via the Miro UI, embedded elsewhere by a
    board maintainer. This is **not reproducible through MCP tools** —
    don't try to recreate it if it looks broken; ask a board maintainer
    with UI access instead.

## What "sync" means here

1. Pull open issues from GitHub (`GEG-ETHZ/TANGO-core`).
2. Cross-reference against `docs/tango_tasks.md` and the vision doc's
   Phase 3 list — add anything missing; flag (don't silently drop) anything
   that looks stale or already closed.
3. Cross-reference the same issues against the Miro board's Gantt/kanban
   content — add or update rows to match; always confirm with a board
   maintainer before deleting or removing rows.
4. Keep the **Repos** section text (the GitHub link) identical
   between the two places it appears: this repo's actual remotes, and the
   TANGO board's "Start Here" doc. These should never drift from each
   other.
