import datetime as dtm
import pandas as pd

from data_api.treasury_config import SERIES_ID
from instruments.rate_curve import RollForwardCurve
from markets import usd_lib
from models.config_context import ConfigContext
from models.curve_context import CurveContext

def get_analytics(curve_date: dtm.date, trade_date: dtm.date = None) -> pd.DataFrame:
    measures = []
    if not curve_date:
        curve_date = usd_lib.get_last_trade_date()
    bond_curve = CurveContext().get_bond_curve(f'{SERIES_ID}B', curve_date)
    if trade_date:
        price_date = trade_date
        rolled_curve = RollForwardCurve(bond_curve, trade_date)
    else:
        price_date = curve_date
    for bond in ConfigContext().get_bonds(SERIES_ID):
        if trade_date and trade_date not in bond.settle_info:
            if trade_date < bond.maturity_date:
                bond.set_data(trade_date, 0)
                bond.data[trade_date] = bond.get_price_from_curve(trade_date, rolled_curve)
            else:
                continue
        if price_date in bond.data:
            measures.append((bond.display_name(), bond.maturity_date, bond.price(price_date),
                             bond.get_full_price(price_date), bond.get_yield(price_date),
                             bond.get_dv01(price_date), bond.get_modified_duration(price_date)))
    return pd.DataFrame(measures, columns=['Name', 'Maturity', 'Market Price', 'Full Price', 'Yield', 'DV01', 'Duration'])
