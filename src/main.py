
import logging

from config import cny_rc, usd_rc, us_bonds
from lib import plotter

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate_rates(value_date = None):
    ycg_usd = []
    for date in usd_rc.get_valuation_dates(value_date):
        ycg_usd_dt = usd_rc.construct(date)
        ycg_usd_dt.build(calibrate_convexity=True)
        ycg_usd.append(ycg_usd_dt)

    # ycg_cny = cny_rc.construct()
    # ycg_cny.build()

    return [ycg_usd]#, [ycg_cny]]

def evaluate_bonds(value_date = None):
    bcm_us = us_bonds.construct(value_date)
    bcm_us.build()
    return [bcm_us]


if __name__ == '__main__':
    for ycg in evaluate_rates():
        plotter.display_rates_curve(*ycg.get_graph_info())
    for bcm in evaluate_bonds():
        plotter.display_bonds_curve(*bcm.get_graph_info())
