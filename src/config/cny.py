
import datetime as dtm
import logging

import lib.date_utils as date_lib
import data_api.scraper as data_scraper
from curve_construction import YieldCurveDefinition, YieldCurveSetConstructor
from lib.curve_instrument import Deposit
from lib.swap import DomesticSwap
from lib.currency import Currency
from lib.fx import FXSwapC, FXSpot

logger = logging.Logger('')
logger.setLevel(logging.DEBUG)


def get_cny_swaps_curve(fixing_type: str = 'FR007') -> list[DomesticSwap]:
    data_date, rates = data_scraper.load_cfets_fixings()
    deposit = Deposit(fixing_type, date_lib.Tenor('7D'))
    deposit.set_market(data_date, rates[fixing_type] / 100)

    data_date, swap_prices = data_scraper.load_cfets_swaps(fixing_type)
    if fixing_type == 'FR007':
        swap_index = 'CNY7DR'
    elif fixing_type == 'Shibor3M':
        swap_index = 'CNYSHIBOR'
    swap_instruments = [deposit]
    for tenor, rate in swap_prices.items():
        ins = DomesticSwap(f'{swap_index}_{tenor}', _index=swap_index, _end=date_lib.Tenor(tenor))
        ins.set_market(data_date, rate)
        swap_instruments.append(ins)
    return swap_instruments

def get_cny_fx_curve(ccy_ref: str = 'USD') -> tuple[dtm.date, FXSpot, list[FXSwapC]]:
    ccy = 'CNY'
    ccy_obj = Currency(ccy)
    spot_data = data_scraper.load_cfets_spot()
    data_date, cny_fx_data = data_scraper.load_cfets_fx()
    inverse = spot_data[ccy_ref][0].startswith(ccy_ref)
    spot_settle_date = cny_fx_data[1][2]
    
    spot_ins = FXSpot('FX_Spot', ccy_obj, _inverse=inverse)
    spot_ins.set_market(data_date, spot_data[ccy_ref][1], settle_date=spot_settle_date)
    
    fxfwd_ins = []
    for r in cny_fx_data:
        ins = FXSwapC(f'{ccy}_{r[0]}', ccy_obj, _inverse=inverse, _is_ndf=True)
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
        YieldCurveDefinition(
            'OIS', fxfwd_instruments,
            _daycount_type=date_lib.DayCount.ACT365,
            _collateral_curve=base_curve,
            _collateral_spot=spot_instrument),
        YieldCurveDefinition('7D', cny_swaps_1, _daycount_type=date_lib.DayCount.ACT365),
        # YieldCurveDefinition('3M', cny_swaps_2, _daycount_type=date_lib.DayCount.ACT365),
    ]
    return YieldCurveSetConstructor('CNY', val_date_xccy, curve_defs, _calendar='CN')
