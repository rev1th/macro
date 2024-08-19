# Description

* USD (SOFR and EFFR) curve construction using CME futures and swaps data
* CNY (cross currency, FR007 and SHIBOR) curve construction using CFETS swaps data
* US Treasury bond curve construction (asset swap spreads) using treasury direct data
* Bond Futures implied repo basis & rates using CME data
* CNY USD volatility surface construction using CFETS deltas x tenors data
<br/><br/>

# Setup
```
git clone https://github.com/rev1th/common.git
conda env create -f environment.yml
```

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

