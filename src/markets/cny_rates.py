import datetime as dtm

from common.chrono.daycount import DayCount
from common.chrono.tenor import Tenor, Calendar
from common.currency import Currency

import data_api.cfets as cfets_api
from models.rate_curve_builder import RateCurveModel, RateCurveGroupModel
from instruments.rate_curve_instrument import Deposit, CurveInstrument
from instruments.swap import SwapTemplate, DomesticSwap
from instruments.fx import FXSwap, FXSpot


def get_swaps_curve(fixing_type: str = 'FR007') -> tuple[dtm.date, list[DomesticSwap]]:
    data_date, swap_prices = cfets_api.load_swaps(fixing_type)
    if fixing_type == 'FR007':
        data_date, rates = cfets_api.load_fixings('FR')
        deposit = Deposit(Tenor('7D').get_date(data_date), name=fixing_type)
        deposit.data[data_date] = rates[fixing_type] / 100
        swap_convention = 'CNY_7DR'
    elif fixing_type == 'Shibor3M':
        data_date, rates = cfets_api.load_fixings('Shibor')
        deposit = Deposit(Tenor('3M').get_date(data_date), name=fixing_type)
        deposit.data[data_date] = rates['3M'] / 100
        swap_convention = 'CNY_SHIBOR'
    swap_instruments = [CurveInstrument(deposit)]
    for tenor, rate in swap_prices.items():
        ins = SwapTemplate(swap_convention, Tenor(tenor), name=f'{swap_convention}_{tenor}').to_trade(data_date)
        ins.set_data(data_date, rate)
        swap_instruments.append(CurveInstrument(ins))
    return data_date, swap_instruments

def get_fx_curve(ccy_ref: str = 'USD') -> tuple[dtm.date, FXSpot, list[FXSwap]]:
    ccy = 'CNY'
    ccy_obj = Currency(ccy)
    spot_data = cfets_api.load_spot()
    data_date, fx_data = cfets_api.load_fx()
    inverse = spot_data[ccy_ref][0].startswith(ccy_ref)
    spot_settle_date = fx_data[1][2]
    
    spot_ins = FXSpot(ccy_obj, spot_settle_date, _inverse=inverse, name=f'{ccy}_Spot')
    spot_ins.data[data_date] = spot_data[ccy_ref][1]
    
    fxfwd_ins = []
    last_settle_date = None
    for row in fx_data:
        name = f'{ccy}_{row[0]}'
        exclude_fit = False
        if row[0] == 'ON':
            ins = FXSwap(ccy_obj, row[2], data_date, _inverse=inverse, _is_ndf=True, name=name)
            if row[2] == spot_settle_date:
                exclude_fit = True
        elif row[0] == 'TN':
            # tn_start_date = Tenor(date_lib.CBDay(-1, calendar)).get_date(spot_settle_date)
            ins = FXSwap(ccy_obj, row[2], last_settle_date, _inverse=inverse, _is_ndf=True, name=name)
            if last_settle_date == spot_settle_date:
                exclude_fit = True
        else:
            ins = FXSwap(ccy_obj, row[2], _inverse=inverse, _is_ndf=True, name=name)
            if row[2] == last_settle_date:
                exclude_fit = True
        ins.data[data_date] = row[1]
        fxfwd_ins.append(CurveInstrument(ins, exclude_fit=exclude_fit))
        last_settle_date = row[2]

    return data_date, spot_ins, fxfwd_ins


def construct():
    fx_val_date, spot_instrument, fxfwd_instruments = get_fx_curve()
    fx_curve_defs = [
        RateCurveModel(
            fxfwd_instruments,
            _interpolation_methods = [('CNY_1M', 'LogLinear'), (None, 'LogCubic')], # MonotoneConvex
            _daycount_type=DayCount.ACT365,
            _collateral_curve_id='USD-SOFR',
            _collateral_spot=spot_instrument,
            name='USD'),
    ]
    rates_val_date, swaps_1 = get_swaps_curve(fixing_type='FR007')
    _, swaps_2 = get_swaps_curve(fixing_type='Shibor3M')
    rates_curve_defs = [
        RateCurveModel(swaps_1, _daycount_type=DayCount.ACT365, name='7DR'),
        RateCurveModel(swaps_2, _daycount_type=DayCount.ACT360, _collateral_curve_id='CNY-7DR', name='SHIBOR_3M'),
    ]
    curve_groups = [
        RateCurveGroupModel(rates_val_date, rates_curve_defs, _calendar=Calendar.CNY, name='CNY'),
        RateCurveGroupModel(fx_val_date, fx_curve_defs, _calendar=Calendar.CNY, name='CNY'),
    ]
    return curve_groups
