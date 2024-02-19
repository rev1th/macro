
import logging

from config import cny_yc, usd_yc, us_bonds
from lib import plotter

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate():
    ycg_usd = usd_yc.construct()
    ycg_usd.calibrate_convexity()
    # ycs_usd.build()

    ycg_cny = cny_yc.construct(ycg_usd.curves[0])
    ycg_cny.build()

    return [ycg_usd, ycg_cny]


if __name__ == '__main__':
    # plotter.display_bond_curves(us_bonds.get_graph_info(us_bonds.construct()))
    for ycg in evaluate():
        plotter.display_rate_curves(*ycg.get_graph_info())

# python -m src.data_api.nyfed
# python -m src.data_api.cme

# python -m cProfile -o profile src\main.py

# import pstats
# p = pstats.Stats(r'profile')
# p.strip_dirs().sort_stats(pstats.SortKey.CUMULATIVE).print_stats(25)
