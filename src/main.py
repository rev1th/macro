
import logging

from config import usd_rc, us_bonds, us_bond_futs, cny_rc, cny_fxvol
from lib import plotter

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate_rates_curves(start_date = None, end_date = None):
    ycg_usd = []
    for date in usd_rc.get_valuation_dates(start_date, end_date):
        ycg_usd_dt = usd_rc.construct(date)
        ycg_usd_dt.build(calibrate_convexity=True)
        ycg_usd.append(ycg_usd_dt)

    ycg_cny = cny_rc.construct()
    ycg_cny.build()

    return [ycg_usd, [ycg_cny]]

_CACHED_DATA = {}
def evaluate_bonds_curves(value_date = None, **kwargs):
    bcm_us = us_bonds.construct(value_date, **kwargs)
    bcm_us.build()
    _CACHED_DATA[value_date] = bcm_us
    return [bcm_us]

def evaluate_bonds_roll(curve_date = None, trade_date = None):
    return _CACHED_DATA[curve_date].get_measures(trade_date)

def evaluate_bond_futures(value_date = None):
    return [us_bond_futs.construct(value_date)]

def evaluate_vol_curves():
    fxvol = cny_fxvol.construct()
    return [fxvol]


if __name__ == '__main__':
    for ycg_arr in evaluate_rates_curves():
        for ycg in ycg_arr:
            plotter.display_rates_curve(*ycg.get_graph_info())
    for bcm in evaluate_bonds_curves():
        plotter.display_bonds_curve(*bcm.get_graph_info())
