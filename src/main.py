
import logging

from config import cny_rc, usd_rc, us_bonds
from lib import plotter

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate():
    ycg_usd = usd_rc.construct()
    ycg_usd.build(calibrate_convexity=True)

    ycg_cny = cny_rc.construct()
    ycg_cny.build()

    return [ycg_usd, ycg_cny]


if __name__ == '__main__':
    for ycg in evaluate():
        plotter.display_rate_curves(*ycg.get_graph_info())
    plotter.display_bond_curves(*us_bonds.get_graph_info(*us_bonds.construct()))
