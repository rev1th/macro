import logging

from markets import usd_lib, usd_rc, usd_bonds, usd_bond_futs
from markets import cny_rc, cny_fxvol
from lib import plotter
from models.rate_curve_builder import RateCurveGroupModel

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate_rates_curves(start_date = None, end_date = None, ccys: list[str] = None) -> list[list[RateCurveGroupModel]]:
    ycg_usd = []
    for date in usd_lib.get_valuation_dates(start_date, end_date):
        ycg_usd_dt = usd_rc.construct(date)
        for ycg_usd_dt_i in ycg_usd_dt:
            ycg_usd_dt_i.build(calibrate_convexity=True)
        ycg_usd.extend(ycg_usd_dt)
    res = [ycg_usd]

    if ccys and 'CNY' in ccys:
        ycg_cny = cny_rc.construct()
        for ycg_cny_i in ycg_cny:
            ycg_cny_i.build()
        res.append(ycg_cny)

    return res

_CACHED_DATA = {}
def evaluate_bonds_curves(start_date = None, end_date = None, **kwargs):
    bcm_us = []
    for date in usd_lib.get_valuation_dates(start_date, end_date):
        bcm_us_dt = usd_bonds.construct(date, **kwargs)
        bcm_us_dt.build()
        _CACHED_DATA[date] = bcm_us_dt
        bcm_us.append(bcm_us_dt)
    return [bcm_us]

def evaluate_bonds_roll(curve_date = None, trade_date = None):
    return _CACHED_DATA[curve_date].get_measures(trade_date)

def evaluate_bond_futures(start_date = None, end_date = None):
    res = []
    for date in usd_lib.get_valuation_dates(start_date, end_date):
        res.append(usd_bond_futs.construct(date))
    return res

def evaluate_vol_curves():
    fxvol = cny_fxvol.construct()
    return [fxvol]


if __name__ == '__main__':
    for ycg_arr in evaluate_rates_curves():
        for ycg in ycg_arr:
            plotter.display_rates_curve(*ycg.get_graph_info())
    for bcm in evaluate_bonds_curves():
        plotter.display_bonds_curve(*bcm.get_graph_info())
