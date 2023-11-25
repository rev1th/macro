
import logging

from config import usd, cny
from lib import graph_utils

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
        graph_utils.display_curves(*ycs.get_graph_info())

# import pstats
# from pstats import SortKey
# p = pstats.Stats(r'C:\Users\Revanth\Downloads\profile')
# p.strip_dirs().sort_stats(SortKey.CUMULATIVE).print_stats(25)
