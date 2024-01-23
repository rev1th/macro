
import datetime as dtm
import logging

import common.chrono as date_lib
import data_api.cfets as data_cfets
from rate_curve_builder import YieldCurveModel, YieldCurveSetModel
from models.rate_curve_instrument import Deposit
from models.swap import DomesticSwap
from models.currency import Currency
from models.fx import FXSwapC, FXSpot

logger = logging.Logger(__name__)


def get_cny_swaps_curve(fixing_type: str = 'FR007') -> list[DomesticSwap]:
    data_date, rates = data_cfets.load_fixings()
    deposit = Deposit(date_lib.Tenor('7D'), name=fixing_type)
    deposit.set_market(data_date, rates[fixing_type] / 100)

    data_date, swap_prices = data_cfets.load_swaps(fixing_type)
    if fixing_type == 'FR007':
        swap_index = 'CNY7DR'
    elif fixing_type == 'Shibor3M':
        swap_index = 'CNYSHIBOR'
    swap_instruments = [deposit]
    for tenor, rate in swap_prices.items():
        ins = DomesticSwap(_index=swap_index, _end=date_lib.Tenor(tenor), name=f'{swap_index}_{tenor}')
        ins.set_market(data_date, rate)
        swap_instruments.append(ins)
    return swap_instruments

def get_cny_fx_curve(ccy_ref: str = 'USD') -> tuple[dtm.date, FXSpot, list[FXSwapC]]:
    ccy = 'CNY'
    ccy_obj = Currency(ccy)
    spot_data = data_cfets.load_spot()
    data_date, cny_fx_data = data_cfets.load_fx()
    inverse = spot_data[ccy_ref][0].startswith(ccy_ref)
    spot_settle_date = cny_fx_data[1][2]
    
    spot_ins = FXSpot(ccy_obj, _inverse=inverse, name=f'{ccy}_Spot')
    spot_ins.set_market(data_date, spot_data[ccy_ref][1], settle_date=spot_settle_date)
    
    fxfwd_ins = []
    for r in cny_fx_data:
        ins = FXSwapC(ccy_obj, _inverse=inverse, _is_ndf=True, name=f'{ccy}_{r[0]}')
        if r[0] == 'ON':
            tn_start_date = r[2]
            ins.set_market(data_date, r[1], settle_date=r[2], near_date=data_date)
            if r[2] == spot_settle_date:
                ins.exclude_knot = True
        elif r[0] == 'TN':
            # tn_start_date = date_lib.Tenor(date_lib.CBDay(-1, calendar)).get_date(spot_settle_date)
            ins.set_market(data_date, r[1], settle_date=r[2], near_date=tn_start_date)
            if tn_start_date == spot_settle_date:
                ins.exclude_knot = True
        else:
            ins.set_market(data_date, r[1], settle_date=r[2])
        fxfwd_ins.append(ins)

    return data_date, spot_ins, fxfwd_ins


def construct(base_curve):
    val_date_xccy, spot_instrument, fxfwd_instruments = get_cny_fx_curve()
    cny_swaps_1 = get_cny_swaps_curve(fixing_type='FR007')
    curve_defs = [
        YieldCurveModel(
            fxfwd_instruments,
            _daycount_type=date_lib.DayCount.ACT365,
            _collateral_curve=base_curve,
            _collateral_spot=spot_instrument,
            name='OIS'),
        YieldCurveModel(cny_swaps_1, _daycount_type=date_lib.DayCount.ACT365, name='7D'),
        # YieldCurveModel('3M', cny_swaps_2, _daycount_type=date_lib.DayCount.ACT365),
    ]
    return YieldCurveSetModel(val_date_xccy, curve_defs, _calendar='CN', name='CNY')
