# TANGO Documentation

This repository contains the documentation for the TANGO project, which is
written using Markdown and Jupyter Notebooks, using the project
[jupyterbook](https://jupyterbook.org).

## Building the documentation

Ensure the conda environment `tango` has been activated. From the root directory
of the TANGO project source code, execute:

```bash
jupyter-book build docs
```

The documentation will be built in the `docs/_build` directory. You can
visualize it by opening the file `_build/html/index.html` in your browser.

Alternatively, you can also execute the Shell script below:

```bash
docs/deploy
```

This will build the documentation and copy the HTML content into the directory
`public` in the root of the project. You can then visualize the documentation by
opening the file `public/index.html` in your browser.

The `public` directory should not be committed to the repository, and it is
ignored in the `.gitignore` file.
