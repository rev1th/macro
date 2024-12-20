from common.chrono import Tenor, BDayAdjust, BDayAdjustType
from common.chrono.calendar import Calendar
from volatility.models.delta_types import FXDeltaType
from volatility.models.fx_vol_surface_construct import FXVolQuote, FXDeltaSlice, FXVolSurfaceConstruct
from volatility.models.vol_types import VolatilityQuoteType

import data_api.cfets as cfets_api
from models.curve_context import CurveContext


def get_fx_vols() -> dict[str, list[FXVolQuote]]:
    data_date, fxvol_data = cfets_api.load_fxvol()
    
    vol_quotes = {}
    for tenor, quotes in fxvol_data.items():
        vol_quotes[tenor] = []
        for (delta, q_type), (q_value, q_spread) in quotes.items():
            q_value /= 100
            weight = 1 / max(q_spread, 1e-2)
            if delta == 'ATM':
                quote = FXVolQuote(VolatilityQuoteType.ATM, q_value, weight=weight)
            else:
                quote = FXVolQuote(VolatilityQuoteType(q_type), q_value, delta=delta, weight=weight)
            vol_quotes[tenor].append(quote)
    return data_date, vol_quotes

def construct():
    calendar = Calendar.CNY
    settle_tenor = Tenor.bday(2, calendar)
    bd_adjust = BDayAdjust(BDayAdjustType.Following, calendar)

    value_date, vol_quotes = get_fx_vols()
    fx_curve = CurveContext().get_rate_curve_last('CNY-USD', value_date)
    value_date = fx_curve.date
    slice_data = []
    for t, quotes in vol_quotes.items():
        expiry_date = Tenor(t).get_date(value_date, bd_adjust)
        settle_date = settle_tenor.get_date(expiry_date)
        fwd_price = fx_curve.get_forward_price(settle_date)
        slice_data.append(FXDeltaSlice(expiry_date, fwd_price, quotes))
    return FXVolSurfaceConstruct(value_date, slice_data, FXDeltaType.ForwardPremium, name='USDCNY-Vol')
