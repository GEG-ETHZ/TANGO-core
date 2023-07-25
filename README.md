# tango

## Environment
```bash
conda create -n tango
conda install -n tango numpy scipy coolprop maptlotlib pyyaml python=3.9
```

## Installation
```bash
cd $TANGO_DIR
python setup.py bdist_wheel
pip install -e .
```