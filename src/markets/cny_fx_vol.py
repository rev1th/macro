from common.chrono.tenor import Tenor
from common.currency import Currency
from volatility.models.construct_types import NumeraireConvention
from volatility.models.fx_vol_surface_construct import FXVolQuote, FXDeltaSlice, FXVolSurfaceConstruct
from volatility.models.vol_types import VolatilityQuoteType

import data_api.cfets as cfets_api
from lib import fx_dates as fx_date_lib
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
    currency = Currency.CNY
    value_date, vol_quotes = get_fx_vols()
    fx_curve = CurveContext().get_rate_curve_last('CNY-USD', value_date)
    value_date = fx_curve.date
    spot_date = fx_date_lib.get_spot_date(currency, value_date)
    slice_data = []
    for tenor, quotes in vol_quotes.items():
        expiry_date, settle_date = fx_date_lib.get_forward_dates(currency, Tenor(tenor), spot_date)
        fwd_price = fx_curve.get_forward_price(settle_date)
        slice_data.append(FXDeltaSlice(expiry_date, fwd_price, quotes))
    return FXVolSurfaceConstruct(value_date, slice_data, NumeraireConvention.Inverse, name='USDCNY-Vol')
