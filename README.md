.. These are examples of badges you might want to add to your README:
   please update the URLs accordingly

    .. image:: https://api.cirrus-ci.com/github/<USER>/tango.svg?branch=main
        :alt: Built Status
        :target: https://cirrus-ci.com/github/<USER>/tango
    .. image:: https://readthedocs.org/projects/tango/badge/?version=latest
        :alt: ReadTheDocs
        :target: https://tango.readthedocs.io/en/stable/
    .. image:: https://img.shields.io/coveralls/github/<USER>/tango/main.svg
        :alt: Coveralls
        :target: https://coveralls.io/r/<USER>/tango
    .. image:: https://img.shields.io/pypi/v/tango.svg
        :alt: PyPI-Server
        :target: https://pypi.org/project/tango/
    .. image:: https://img.shields.io/conda/vn/conda-forge/tango.svg
        :alt: Conda-Forge
        :target: https://anaconda.org/conda-forge/tango
    .. image:: https://pepy.tech/badge/tango/month
        :alt: Monthly Downloads
        :target: https://pepy.tech/project/tango
    .. image:: https://img.shields.io/twitter/url/http/shields.io.svg?style=social&label=Twitter
        :alt: Twitter
        :target: https://twitter.com/tango

.. image:: https://img.shields.io/badge/-PyScaffold-005CA0?logo=pyscaffold
    :alt: Project generated with PyScaffold
    :target: https://pyscaffold.org/

|

=====
tango
=====


    Add a short description here!


##Environment
```bash
conda create -n tango
conda install -n tango numpy scipy coolprop maptlotlib pyyaml python=3.9
```

##Installation
```bash
cd $TANGO_DIR
python setup.py bdist_wheel
pip install -e .
```

.. _pyscaffold-notes:

Note
====

This project has been set up using PyScaffold 4.2.2. For details and usage
information on PyScaffold see https://pyscaffold.org/.
