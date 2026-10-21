# Deferred verification

Changes no real run has shown working yet. A row leaves, in the commit that
names its evidence, once that evidence exists.

| # | Change | Risk | Evidence that would close it |
|---|---|---|---|
| D1 | Docs site deploy (`.github/workflows/docs.yml`) | The site is public if GEG-ETHZ is not on GitHub Enterprise Cloud; the workflow has never run on GitHub | Settings → Pages shows "Visibility: Private", `PAGES_PRIVATE=true` is set, and a non-member gets 404 on the site URL |
| D2 | Mermaid, `.drawio.svg` and mkdocstrings rendering on the deployed site | Zensical's mkdocstrings support is preliminary; Mermaid was checked only in a local build | One page of each kind checked on the deployed site, light and dark |
