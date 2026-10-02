# Issue, Task & Miro Sync

How to sync this repo's issue trackers, its local task docs, and its Miro
board(s). Read this before doing any "sync TANGO" work.

## Remotes

- **GitHub** — `GEG-ETHZ/tango-core`
  (`git@github.com:GEG-ETHZ/tango-core.git`). Formerly `GEG-ETHZ/TANGO`;
  GitHub redirects the old name, so older clones with a `TANGO.git` remote
  still work, but use `tango-core` in new references. Reachable via a
  GitHub MCP server whose token is scoped to this repo (a token scoped to
  other `GEG-ETHZ` repos returns 404 here — that's a token-scope problem,
  not a missing repo).
- **GitLab** — `geg/tango-projects/tango-core`
  (`git@gitlab.ethz.ch:geg/tango-projects/tango-core.git`) — the
  primary/authoritative issue tracker. Access it with `glab` (e.g.
  `glab issue list -R geg/tango-projects/tango-core`). GitLab's native MCP
  endpoint is not enabled on `gitlab.ethz.ch` as of 2026-09-23. A planned
  consolidation of `dev_docs/tango_tasks.md` and GitHub issues into GitLab
  issues is tracked in GitLab issue #45.
- A sibling repo, `geg/tango-projects/tango-super`
  (`git@gitlab.ethz.ch:geg/tango-projects/tango-super.git`, no GitHub
  remote), shares the same TANGO board presence — check it too when doing
  a full TANGO sync, even though its own task docs/Miro presence aren't
  set up yet.

## Local task docs

- `dev_docs/tango_tasks.md` — granular, frequently-updated working task list.
  Scratch-adjacent but checked in; this is where in-flight, multi-step work
  gets tracked across sessions.
- `dev_docs/TANGO_vision_and_roadmap/README.md` — the durable, Confluence-bound
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
    section — keep its GitHub/GitLab links identical to this repo's actual
    remotes (above).
  - "Gantt Chart" frame (widget id `3458764585326789646`) — large, ~127
    items.
  - A timeline widget (id `3458764679176539081`) was set up as a
    Miro-native "linked copy" via the Miro UI, embedded elsewhere by a
    board maintainer. This is **not reproducible through MCP tools** —
    don't try to recreate it if it looks broken; ask a board maintainer
    with UI access instead.
  - The board's bounds are much larger than its content (one oversized
    frame, widget id `3458764668417431565`, is ~334k × 360k units), so
    "zoom to fit" can't show the whole board. Known and deliberately left
    as-is — don't try to fix it through MCP.

## Diagrams on the board

- Put draw.io diagrams on the board with Miro's **draw.io plugin**, not as
  native Miro shapes or static PNGs. The source of truth stays in
  `dev_docs/diagrams/src/**/*.drawio`: edit it there and re-import, so the
  board copy doesn't drift from the repo.
- The plugin drops the embed wherever the viewport happens to be, often
  tiny and outside any frame. After inserting, check its size and
  position and move it into the right frame.
- To find a lost embed, `canvas_search` in `matches` mode for
  `re:type="external_diagram"`, then link to it with
  `?moveToWidget=<id>`.

## What "sync" means here

1. Pull open issues from both remotes for this repo (GitLab first/primary,
   then GitHub).
2. Cross-reference against `dev_docs/tango_tasks.md` and the vision doc's
   Phase 3 list — add anything missing; flag (don't silently drop) anything
   that looks stale or already closed.
3. Cross-reference the same issues against the Miro board's Gantt/kanban
   content — add or update rows to match; always confirm with a board
   maintainer before deleting or removing rows.
4. Keep the **Repos** section text (GitHub + GitLab links) identical
   between the two places it appears: this repo's actual remotes, and the
   TANGO board's "Start Here" doc. These should never drift from each
   other.
