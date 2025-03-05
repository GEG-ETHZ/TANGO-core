# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['tango_cli.py'],
    pathex=[],
    binaries=[],
    datas=[('tango', 'tango')],
    hiddenimports=['bottleneck', 'cython', 'kiwisolver', 'mkl', 'mkl_fft', 'mkl_random', 'munkres', 'numexpr', 'numpy', 'pandas', 'pip', 'pytz', 'readline', 'setuptools', 'six', 'unicodedata2', 'wheel', 'zlib', 'appnope', 'asttokens', 'attrs', 'backcall', 'bleach', 'certifi', 'click', 'cligj', 'contourpy', 'cycler', 'decorator', 'defusedxml', 'docopt', 'exceptiongroup', 'executing', 'fastjsonschema', 'filelock', 'fiona', 'fluprodia', 'geopandas', 'h5py', 'idna', 'iniconfig', 'jedi', 'jinja2', 'jsonschema', 'markupsafe', 'matplotlib', 'mistune', 'mpmath', 'nbclient', 'nbconvert', 'nbformat', 'networkx', 'openpyxl', 'oyaml', 'packaging', 'pandocfilters', 'parso', 'pexpect', 'pickleshare', 'pipreqs', 'platformdirs', 'pluggy', 'psutil', 'ptyprocess', 'pygments', 'pyparsing', 'pyproj', 'pytest', 'referencing', 'requests', 'scipy', 'shapely', 'soupsieve', 'sympy', 'tabulate', 'tespy', 'tinycss2', 'tomli', 'torch', 'tornado', 'tqdm', 'traitlets', 'urllib3', 'wcwidth', 'webencodings', 'yarg', 'zipp'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='tango_cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
