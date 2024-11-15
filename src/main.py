import logging

from markets import usd_lib, usd_rates, usd_rates_vol, usd_bonds, usd_bond_futs, usd_bonds_vol
from markets import cny_rates, cny_fx_vol
from lib import plotter
from lib import bond_helper
from models.rate_curve_builder import RateCurveGroupModel
from models.bond_curve_model import BondCurveModel

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def evaluate_rates_curves(start_date = None, end_date = None, ccys: list[str] = None) -> list[list[RateCurveGroupModel]]:
    ycg_usd = []
    for date in usd_lib.get_trade_dates(start_date, end_date):
        ycg_usd_dt = usd_rates.construct(date)
        for ycg_usd_dt_i in ycg_usd_dt:
            ycg_usd_dt_i.build(calibrate_convexity=True)
        ycg_usd.extend(ycg_usd_dt)
    res = [ycg_usd]

    if ccys and 'CNY' in ccys:
        ycg_cny = cny_rates.construct()
        for ycg_cny_i in ycg_cny:
            ycg_cny_i.build()
        res.append(ycg_cny)

    return res

def evaluate_bonds_curves(start_date = None, end_date = None, **kwargs) -> list[list[BondCurveModel]]:
    bcm_us = []
    for date in usd_lib.get_trade_dates(start_date, end_date):
        bcm_us_dt = usd_bonds.construct(date, **kwargs)
        for bcm_us_dt_i in bcm_us_dt:
            bcm_us_dt_i.build()
            bcm_us.append(bcm_us_dt_i)
    return [bcm_us]

def evaluate_bonds_roll(curve_date = None, trade_date = None):
    return bond_helper.get_analytics(curve_date, trade_date)

def evaluate_bond_futures(start_date = None, end_date = None):
    res = []
    for date in usd_lib.get_trade_dates(start_date, end_date):
        res.append(usd_bond_futs.construct(date))
    return res

def evaluate_vol_surfaces():
    fxvol = cny_fx_vol.construct()
    return [fxvol]

def evaluate_option_surfaces(trade_date = None):
    rfs_vol = usd_rates_vol.construct(trade_date)
    bfs_vol = usd_bonds_vol.construct(trade_date)
    return rfs_vol + bfs_vol


if __name__ == '__main__':
    for ycg_arr in evaluate_rates_curves():
        for ycg in ycg_arr:
            plotter.display_rates_curve(*ycg.get_graph_info())
    for bcm in evaluate_bonds_curves():
        plotter.display_bonds_curve(*bcm.get_graph_info())
    for bfm in evaluate_bond_futures():
        bfm.get_summary()
