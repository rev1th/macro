
import datetime as dtm

import common.chrono as date_lib
from instruments.bond import ZeroCouponBond, FixCouponBond
import data_api.treasury as td_api
from models.bond_curve_builder import BondCurveModelNS, BondCurveModelNP
from models.bond_curve_types import BondCurveWeightType

MIN_TENOR = date_lib.Tenor('1m')
CUSIP_COL, TYPE_COL, RATE_COL, MATURITY_COL, BUY_COL, SELL_COL, CLOSE_COL = (
    td_api.COL_NAMES[id] for id in [0, 1, 2, 3, -3, -2, -1])

def construct(value_date: dtm.date = None, include_term: bool = False, weight_type = BondCurveWeightType.OTR):
    if not value_date:
        value_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=date_lib.Calendar.USEX)
    min_maturity = MIN_TENOR.get_date(value_date)
    trade_date, settle_date = value_date, None
    bonds_price = td_api.load_bonds_price(value_date)
    if sum(bonds_price[CLOSE_COL]) == 0:
        trade_date, settle_date = None, value_date
    bonds_list = []
    bills_list = []
    settle_delay = date_lib.Tenor.bday(1)
    if include_term:
        # auctioned before 2010 must be a T-Bond
        bonds_term = td_api.load_bonds_term(dtm.date(2010, 1, 1))
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
            bill_obj = ZeroCouponBond(mat_date, name=cusip, #_daycount_type=date_lib.DayCount.ACT360,
                                    _settle_delay=settle_delay)
            bill_obj.set_market(settle_date, price, trade_date=trade_date)
            bills_list.append((bill_obj, weight))
        elif b_type in ('NOTE', 'BOND'):
            if include_term and cusip in bonds_term:
                term_years = int(bonds_term[cusip].split('-')[0])
            else:
                term_years = 30
            bond_obj = FixCouponBond(
                        mat_date, b_r[RATE_COL], date_lib.Frequency.SemiAnnual, name=cusip,
                        _daycount_type=date_lib.DayCount.ACT365,
                        _settle_delay=settle_delay,
                        _original_term=term_years)
            bond_obj.set_market(settle_date, price, trade_date=trade_date)
            bonds_list.append((bond_obj, weight))
    match weight_type:
        case BondCurveWeightType.OTR:
            tenors = ['6M'] + [f'{t}y' for t in [1, 2, 3, 5, 7, 10, 30]]
        case _:
            tenors = ['6M'] + [f'{t}y' for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30]]
    return BondCurveModelNP(value_date, 'USD-SOFR', bonds_list + bills_list, tenors, name='UST')
    # return BondCurveModelNS(value_date, 'USD-SOFR', bonds, _decay_rate=1/12)


_BOND_MODEL_CACHE: dict[dtm.date, BondCurveModelNP] = {}
def update_bond_model(curve: BondCurveModelNP) -> None:
    _BOND_MODEL_CACHE[curve.date] = curve
def get_bond_model(date: dtm.date):
    if date not in _BOND_MODEL_CACHE:
        update_bond_model(construct(date, include_term=True))
    return _BOND_MODEL_CACHE[date]
