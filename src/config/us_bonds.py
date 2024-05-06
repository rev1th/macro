
import logging
import numpy as np

import common.chrono as date_lib
from models.bond import ZeroCouponBond, FixCouponBond
import data_api.treasury as td
from bond_curve_builder import BondCurveModelNS, BondCurveModelNP

logger = logging.Logger(__name__)

MIN_TENOR_BOND = date_lib.Tenor('6m')
MIN_TENOR_BILL = date_lib.Tenor('1m')
CUSIP_COL, TYPE_COL, RATE_COL, MATURITY_COL, PRICE_COL = (td.COL_NAMES[id] for id in [0, 1, 2, 3, -1])

def construct(value_date = None):
    if not value_date:
        value_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=date_lib.Calendar.USEX)
    min_maturity_bond = MIN_TENOR_BOND.get_date(value_date)
    min_maturity_bill = MIN_TENOR_BILL.get_date(value_date)
    trade_date, settle_date = value_date, None
    bonds_price = td.load_bonds_price(value_date)
    if sum(bonds_price[PRICE_COL]) == 0:
        bonds_price[PRICE_COL] = np.where(bonds_price[td.COL_NAMES[-3]]==0, bonds_price[td.COL_NAMES[-2]], 
                                        (bonds_price[td.COL_NAMES[-3]]+bonds_price[td.COL_NAMES[-2]])/2)
        trade_date, settle_date = None, value_date
    bonds_list = []
    bills_list = []
    for _, b_r in bonds_price.iterrows():
        cusip, b_type, mat_date, price = b_r[CUSIP_COL], b_r[TYPE_COL], b_r[MATURITY_COL].date(), b_r[PRICE_COL]
        if b_type == 'BILL':
            if mat_date < min_maturity_bill:
                continue
            bill_obj = ZeroCouponBond(mat_date, name=cusip, #_daycount_type=date_lib.DayCount.ACT360,
                                    _settle_delay=date_lib.Tenor.bday(1))
            bill_obj.set_market(settle_date, price, trade_date=trade_date)
            bills_list.append(bill_obj)
        elif b_type in ('NOTE', 'BOND'):
            if mat_date < min_maturity_bond:
                continue
            bond_obj = FixCouponBond(
                        mat_date, b_r[RATE_COL], date_lib.Frequency.SemiAnnual, name=cusip,
                        _daycount_type=date_lib.DayCount.ACT365,
                        _settle_delay=date_lib.Tenor.bday(1),
                        _original_term=30 if b_type == 'BOND' else 5)
            bond_obj.set_market(settle_date, price, trade_date=trade_date)
            bonds_list.append(bond_obj)
    tenors = ['6M'] + [f'{t}y' for t in [1, 2, 3, 5, 7, 10, 12, 15, 20, 25, 30]]
    return BondCurveModelNP(value_date, 'USD-SOFR', bonds_list + bills_list, tenors, name='UST')
    # return BondCurveModelNS(value_date, 'USD-SOFR', bonds, _decay_rate=1/12)
