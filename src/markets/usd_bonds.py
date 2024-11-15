import logging
import datetime as dtm

from common.chrono import Tenor
from data_api import treasury_client as tsy_client
from data_api.treasury_config import SERIES_ID
from markets import usd_lib
from models.bond_curve_model import BondCurveModelNS, BondCurveModelNP
from models.bond_curve_types import BondCurveWeightType
from models.config_context import ConfigContext
from models.data_context import DataContext

logger = logging.Logger(__name__)

MIN_TENOR = Tenor('1m')
# CUSIP_COL, TYPE_COL, RATE_COL, MATURITY_COL, BUY_COL, SELL_COL, CLOSE_COL = (
#     td_api.COL_NAMES[id] for id in [0, 1, 2, 3, -3, -2, -1])

def construct(value_date: dtm.date = None, weight_type = BondCurveWeightType.OTR):
    if not value_date:
        value_date = usd_lib.get_last_trade_date()
    if not ConfigContext().has_zero_bonds(SERIES_ID):
        ConfigContext().add_zero_bonds(SERIES_ID, tsy_client.get_zero_bonds(value_date))
    if not ConfigContext().has_coupon_bonds(SERIES_ID):
        ConfigContext().add_coupon_bonds(SERIES_ID, tsy_client.get_coupon_bonds(value_date))
    if not ConfigContext().has_inflation_bonds(SERIES_ID):
        ConfigContext().add_inflation_bonds(SERIES_ID, tsy_client.get_inflation_bonds(value_date))
        DataContext().add_inflation_series(tsy_client.INFLATION_ID, tsy_client.get_inflation_index(tsy_client.INFLATION_ID))
    bonds_map = {b.name: b for b in ConfigContext().get_bonds(SERIES_ID)}
    infl_bonds_map = {b.name: b for b in ConfigContext().get_inflation_bonds(SERIES_ID)}
    min_maturity = MIN_TENOR.get_date(value_date)
    bonds_price = tsy_client.get_bonds_price(value_date)
    bonds_list = []
    infl_bonds_list = []
    for cusip, (price, spread) in bonds_price.items():
        if cusip in bonds_map:
            bond_obj = bonds_map[cusip]
        elif cusip in infl_bonds_map:
            bond_obj = infl_bonds_map[cusip]
        else:
            logger.info(f'{cusip} is missing from bond reference data')
            continue
        if bond_obj.maturity_date < min_maturity:
            continue
    # for _, b_r in bonds_price.iterrows():
        # cusip, b_type, mat_date = b_r[CUSIP_COL], b_r[TYPE_COL], b_r[MATURITY_COL].date()
        # if b_r[CLOSE_COL] == 0:
        #     if b_r[BUY_COL] == 0:
        #         price = b_r[SELL_COL]
        #     else:
        #         price = (b_r[BUY_COL] + b_r[SELL_COL])/2
        # else:
        #     price = b_r[CLOSE_COL]
        # if b_r[BUY_COL] == b_r[SELL_COL]:
        if spread == 0:
            weight = 1
        # elif b_r[BUY_COL] > 0:
        elif spread is None:
            weight = 0
        else:
            if weight_type == BondCurveWeightType.BidAsk:
                # weight = 1e-4 / (b_r[BUY_COL] - b_r[SELL_COL])
                weight = 1e-4 / spread
            elif weight_type == BondCurveWeightType.Equal:
                weight = 1
            else:
                weight = 0
        bond_obj.set_data(value_date, price)
        if cusip in infl_bonds_map:
            infl_bonds_list.append((bond_obj, weight if weight else 1))
        else:
            bonds_list.append((bond_obj, weight))
    match weight_type:
        case BondCurveWeightType.OTR | None:
            tenors = None
        case _:
            tenors = ['6M'] + [f'{t}y' for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30]]
    return [
        BondCurveModelNP(value_date, 'USD-SOFR', bonds_list, tenors, name=f'{SERIES_ID}B'),
        BondCurveModelNP(value_date, 'USD-SOFR', infl_bonds_list, tenors, name=f'{SERIES_ID}IB'),
    ]
    # return BondCurveModelNS(value_date, 'USD-SOFR', bonds, _decay_rate=1/12)
