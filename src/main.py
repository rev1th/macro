
import logging

from config import usd, cny
from lib import plotter

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate():
    ycs_con = usd.construct()
    ycs_con.calibrate_convexity()
    # ycs_con.build()

    ycs_con_xccy = cny.construct(ycs_con.curves[0])
    ycs_con_xccy.build()

    return [ycs_con, ycs_con_xccy]


if __name__ == '__main__':
    for ycs in evaluate():
        plotter.display_curves(*ycs.get_graph_info())

# python -m src.data_api.scraper --fed

# python -m cProfile -o profile src\main.py

# import pstats
# p = pstats.Stats(r'profile')
# p.strip_dirs().sort_stats(pstats.SortKey.CUMULATIVE).print_stats(25)
