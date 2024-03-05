# Setup
git clone https://github.com/rev1th/common.git<br />
conda env create -f environment.yml

## Update rate fixings (daily)
```
python -m src.data_api.nyfed
```

## Update future contract list (monthly)
```
python -m src.data_api.cme
```

## (Re)Install **common** package
```
pip uninstall common -y
pip install ..\common\dist\common-1.0-py3-none-any.whl
```

### Profiling
```
python -m cProfile -o profile src\main.py
import pstats
p = pstats.Stats(r'profile')
p.strip_dirs().sort_stats(pstats.SortKey.CUMULATIVE).print_stats(25)
```

