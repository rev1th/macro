
import datetime as dtm
import logging

import common.chrono as date_lib
from common.currency import Currency

import data_api.cfets as cfets_api
from models.rate_curve_builder import RateCurveModel, RateCurveGroupModel
from instruments.rate_curve_instrument import Deposit
from instruments.swap import DomesticSwap
from instruments.fx import FXSwapC, FXSpot

logger = logging.Logger(__name__)


def get_swaps_curve(fixing_type: str = 'FR007') -> tuple[dtm.date, list[DomesticSwap]]:
    data_date, swap_prices = cfets_api.load_swaps(fixing_type)
    if fixing_type == 'FR007':
        data_date, rates = cfets_api.load_fixings('FR')
        deposit = Deposit(date_lib.Tenor('7D'), name=fixing_type)
        deposit.set_market(data_date, rates[fixing_type] / 100)
        swap_convention = 'CNY_7DR'
    elif fixing_type == 'Shibor3M':
        data_date, rates = cfets_api.load_fixings('Shibor')
        deposit = Deposit(date_lib.Tenor('3M'), name=fixing_type)
        deposit.set_market(data_date, rates['3M'] / 100)
        swap_convention = 'CNY_SHIBOR'
    swap_instruments = [deposit]
    for tenor, rate in swap_prices.items():
        ins = DomesticSwap(_convention_name=swap_convention, _end=date_lib.Tenor(tenor), name=f'{swap_convention}_{tenor}')
        ins.set_market(data_date, rate)
        swap_instruments.append(ins)
    return data_date, swap_instruments

def get_fx_curve(ccy_ref: str = 'USD') -> tuple[dtm.date, FXSpot, list[FXSwapC]]:
    ccy = 'CNY'
    ccy_obj = Currency(ccy)
    spot_data = cfets_api.load_spot()
    data_date, fx_data = cfets_api.load_fx()
    inverse = spot_data[ccy_ref][0].startswith(ccy_ref)
    spot_settle_date = fx_data[1][2]
    
    spot_ins = FXSpot(ccy_obj, _inverse=inverse, name=f'{ccy}_Spot')
    spot_ins.set_market(data_date, spot_data[ccy_ref][1], settle_date=spot_settle_date)
    
    fxfwd_ins = []
    last_settle_date = None
    for row in fx_data:
        ins = FXSwapC(ccy_obj, _inverse=inverse, _is_ndf=True, name=f'{ccy}_{row[0]}')
        if row[0] == 'ON':
            ins.set_market(data_date, row[1], settle_date=row[2], near_date=data_date)
            if row[2] == spot_settle_date:
                ins.exclude_knot = True
        elif row[0] == 'TN':
            # tn_start_date = date_lib.Tenor(date_lib.CBDay(-1, calendar)).get_date(spot_settle_date)
            ins.set_market(data_date, row[1], settle_date=row[2], near_date=last_settle_date)
            if last_settle_date == spot_settle_date:
                ins.exclude_knot = True
        else:
            ins.set_market(data_date, row[1], settle_date=row[2])
            if row[2] == last_settle_date:
                ins.exclude_knot = True
        fxfwd_ins.append(ins)
        last_settle_date = row[2]

    return data_date, spot_ins, fxfwd_ins


def construct():
    fx_val_date, spot_instrument, fxfwd_instruments = get_fx_curve()
    fx_curve_defs = [
        RateCurveModel(
            fxfwd_instruments,
            _interpolation_methods = [('CNY_1M', 'LogLinear'), (None, 'LogCubic')], # MonotoneConvex
            _daycount_type=date_lib.DayCount.ACT365,
            _collateral_curve='USD-SOFR',
            _collateral_spot=spot_instrument,
            name='USD'),
    ]
    rates_val_date, swaps_1 = get_swaps_curve(fixing_type='FR007')
    _, swaps_2 = get_swaps_curve(fixing_type='Shibor3M')
    rates_curve_defs = [
        RateCurveModel(swaps_1, _daycount_type=date_lib.DayCount.ACT365, name='7DR'),
        RateCurveModel(swaps_2, _daycount_type=date_lib.DayCount.ACT360, _collateral_curve='CNY-7DR', name='SHIBOR'),
    ]
    curve_groups = [
        RateCurveGroupModel(rates_val_date, rates_curve_defs, _calendar=date_lib.Calendar.CNY, name='CNY'),
        RateCurveGroupModel(fx_val_date, fx_curve_defs, _calendar=date_lib.Calendar.CNY, name='CNY'),
    ]
    return curve_groups
