import logging
import datetime as dtm

from common.chrono import Tenor
from markets import usd_lib
import data_api.treasury as td_api
from models.bond_curve_model import BondCurveModelNS, BondCurveModelNP
from models.bond_curve_types import BondCurveWeightType
from models.context import ConfigContext

logger = logging.Logger(__name__)

CODE = 'UST'
MIN_TENOR = Tenor('1m')
# CUSIP_COL, TYPE_COL, RATE_COL, MATURITY_COL, BUY_COL, SELL_COL, CLOSE_COL = (
#     td_api.COL_NAMES[id] for id in [0, 1, 2, 3, -3, -2, -1])

def construct(value_date: dtm.date = None, weight_type = BondCurveWeightType.OTR):
    if not value_date:
        value_date = usd_lib.get_last_valuation_date()
    if not ConfigContext().has_zero_bonds(CODE):
        ConfigContext().add_zero_bonds(CODE, td_api.get_zero_bonds(value_date))
    if not ConfigContext().has_coupon_bonds(CODE):
        ConfigContext().add_coupon_bonds(CODE, td_api.get_coupon_bonds(value_date))
    bonds_map = {b.name: b for b in ConfigContext().get_bonds(CODE)}
    min_maturity = MIN_TENOR.get_date(value_date)
    bonds_price = td_api.get_bonds_price(value_date)
    # settle_delay = Tenor.bday(1, usd_lib.CALENDAR)
    # if sum(bonds_price[CLOSE_COL]) == 0:
    #     settle_date = value_date
    # else:
    #     settle_date = settle_delay.get_date(value_date)
    bonds_list = []
    # bills_list = []
    for cusip, (price, spread) in bonds_price.items():
        if cusip not in bonds_map:
            logger.error(f'{cusip} is missing from bond reference data')
            continue
        bond_obj = bonds_map[cusip]
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
        bonds_list.append((bond_obj, weight))
    match weight_type:
        case BondCurveWeightType.OTR | None:
            tenors = None
        case _:
            tenors = ['6M'] + [f'{t}y' for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30]]
    return BondCurveModelNP(value_date, 'USD-SOFR', bonds_list, tenors, name=CODE)
    # return BondCurveModelNS(value_date, 'USD-SOFR', bonds, _decay_rate=1/12)
