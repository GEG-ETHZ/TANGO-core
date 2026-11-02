# Deferred verification

Changes no real run has shown working yet. A row leaves, in the commit that
names its evidence, once that evidence exists.

| # | Change | Risk | Evidence that would close it |
|---|---|---|---|
| D1 | Public docs site deploy (`.github/workflows/docs.yml`) | The public build has never been deployed; an excluded internal page could still be reachable | The deploy job runs on `main`, the site loads for a signed-out visitor, and `tango_tasks/` and `archive/` return 404 |
| D2 | Mermaid, `.drawio.svg` and mkdocstrings rendering on the deployed site | Zensical's mkdocstrings support is preliminary; Mermaid was checked only in a local build | One page of each kind checked on the deployed site, light and dark |
