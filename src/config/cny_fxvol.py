
from common.chrono import Tenor, BDayAdjust, BDayAdjustType
from common.chrono.calendar import Calendar
from volatility.models.fx_vol_surface_builder import FXVolQuote, FXVolSurfaceModel
from volatility.models.vol_types import VolatilityQuoteType

import data_api.cfets as cfets_api
from models.rate_curve_builder import get_rate_curve


def get_fx_vols() -> dict[str, list[FXVolQuote]]:
    data_date, fxvol_data = cfets_api.load_fxvol()
    
    vol_quotes = {}
    for t, quotes in fxvol_data.items():
        vol_quotes[t] = []
        for q_info, q_value in quotes.items():
            q_value /= 100
            if q_info == 'ATM':
                vol_quotes[t].append(FXVolQuote(VolatilityQuoteType.ATM, q_value))
            else:
                delta, q_type = q_info.split(' ')
                d_value = int(delta[:-1]) / 100
                vol_quotes[t].append(FXVolQuote(VolatilityQuoteType(q_type), q_value, d_value))
    return data_date, vol_quotes

def construct():
    calendar = Calendar.CNY
    settle_tenor = Tenor.bday(2, calendar)
    bd_adjust = BDayAdjust(BDayAdjustType.Following, calendar)

    value_date, vol_quotes = get_fx_vols()
    fx_curve = get_rate_curve('CNY-USD', value_date)
    vol_data = {}
    for t, quotes in vol_quotes.items():
        expiry_date = Tenor(t).get_date(value_date, bd_adjust)
        settle_date = settle_tenor.get_date(expiry_date)
        fx_rate = fx_curve.get_fx_rate(settle_date)
        vol_data[(expiry_date, fx_rate)] = quotes
    return FXVolSurfaceModel(value_date, vol_data, name='CNYUSD-Vol')
