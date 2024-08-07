
import datetime as dtm

from common.chrono import Tenor
from instruments.bond import ZeroCouponBondSnap
from instruments.coupon_bond import FixCouponBondSnap
from config import usd_mkt
import data_api.treasury as td_api
from models.bond_curve_model import BondCurveModelNS, BondCurveModelNP
from models.bond_curve_types import BondCurveWeightType
from models.context import ConfigContext

MIN_TENOR = Tenor('1m')
CUSIP_COL, TYPE_COL, RATE_COL, MATURITY_COL, BUY_COL, SELL_COL, CLOSE_COL = (
    td_api.COL_NAMES[id] for id in [0, 1, 2, 3, -3, -2, -1])
_INIT = False

def construct(value_date: dtm.date = None, weight_type = BondCurveWeightType.OTR):
    global _INIT
    if not value_date:
        value_date = usd_mkt.get_last_valuation_date()
    if not _INIT:
        ConfigContext().add_bonds(td_api.get_bonds(value_date))
        _INIT = True
    bonds_map = {b.name: b for b in ConfigContext().get_bonds()}
    min_maturity = MIN_TENOR.get_date(value_date)
    settle_delay = Tenor.bday(1, usd_mkt.CALENDAR)
    bonds_price = td_api.load_bonds_price(value_date)
    if sum(bonds_price[CLOSE_COL]) == 0:
        settle_date = value_date
    else:
        settle_date = settle_delay.get_date(value_date)
    bonds_list = []
    bills_list = []
    for _, b_r in bonds_price.iterrows():
        cusip, b_type, mat_date = b_r[CUSIP_COL], b_r[TYPE_COL], b_r[MATURITY_COL].date()
        if b_r[CLOSE_COL] == 0:
            if b_r[BUY_COL] == 0:
                price = b_r[SELL_COL]
            else:
                price = (b_r[BUY_COL] + b_r[SELL_COL])/2
        else:
            price = b_r[CLOSE_COL]
        if b_r[BUY_COL] == b_r[SELL_COL]:
            weight = 1
        else:
            if b_r[BUY_COL] > 0:
                if weight_type == BondCurveWeightType.BidAsk:
                    weight = 1e-4 / (b_r[BUY_COL] - b_r[SELL_COL])
                elif weight_type == BondCurveWeightType.Equal:
                    weight = 1
                else:
                    weight = 0
            else:
                weight = 0
        if mat_date < min_maturity:
            continue
        if b_type == 'BILL':
            bill_obj = bonds_map[cusip]
            bill_state = ZeroCouponBondSnap(bill_obj, settle_date, price)
            bills_list.append((bill_state, weight))
        elif b_type in ('NOTE', 'BOND'):
            bond_obj = bonds_map[cusip]
            bond_state = FixCouponBondSnap(bond_obj, settle_date, price)
            bonds_list.append((bond_state, weight))
    match weight_type:
        case BondCurveWeightType.OTR | None:
            tenors = None
        case _:
            tenors = ['6M'] + [f'{t}y' for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30]]
    return BondCurveModelNP(value_date, 'USD-SOFR', bonds_list + bills_list, tenors, name='UST')
    # return BondCurveModelNS(value_date, 'USD-SOFR', bonds, _decay_rate=1/12)
