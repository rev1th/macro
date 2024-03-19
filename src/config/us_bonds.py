
import logging

import common.chrono as date_lib
from models.bond import Bill, Bond
import data_api.treasury as td
from rate_curve_builder import get_rate_curve
from bond_curve_builder import BondCurveModelNS, BondCurveModelNP

logger = logging.Logger(__name__)

MIN_TENOR_BOND = date_lib.Tenor('6m')
MIN_TENOR_BILL = date_lib.Tenor('1m')

def construct():
    us_cal = 'US-NY'
    val_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=us_cal)
    min_expiry_bond = MIN_TENOR_BOND.get_date(val_date)
    min_expiry_bill = MIN_TENOR_BILL.get_date(val_date)
    bond_prices = td.load_bond_prices(val_date)
    bonds_list = []
    bills_list = []
    for _, b_r in bond_prices.iterrows():
        if b_r['TYPE'] == 'BILL':
            # bond_obj = Bond(b_r['MATURITY_DATE'], 0, date_lib.Frequency.SemiAnnual,
            #                 _daycount_type = date_lib.DayCount.ACT365,
            #                 _settle_delay=date_lib.Tenor.bday(1),
            #                 name=b_r['CUSIP'])
            bill_obj = Bill(b_r['MATURITY_DATE'], name=b_r['CUSIP'], _settle_delay=date_lib.Tenor.bday(1))
            bill_obj.set_market(val_date, b_r['EOD'])
            if bill_obj.maturity_date > min_expiry_bill:
                bills_list.append(bill_obj)
        elif b_r['TYPE'] == 'NOTE' or b_r['TYPE'] == 'BOND':
            bond_obj = Bond(b_r['MATURITY_DATE'], b_r['RATE'], date_lib.Frequency.SemiAnnual,
                            _daycount_type = date_lib.DayCount.ACT365,
                            _settle_delay=date_lib.Tenor.bday(1),
                            name=b_r['CUSIP'])
            bond_obj.set_market(val_date, b_r['EOD'])
            if bond_obj.maturity_date > min_expiry_bond:
                bonds_list.append(bond_obj)
    return bonds_list, bills_list
    
def get_graph_info(bonds: list[Bond], bills: list[Bill]):
    bond_measures = {}
    curve = get_rate_curve('USD-OIS')
    # bcm = BondCurveModelNS(bonds[0].value_date, 'USD-OIS', bonds, _decay_rate=1/12)
    bcm = BondCurveModelNP(bonds[0].value_date, 'USD-OIS', bonds)
    bcm.build()
    bond_curve = bcm.spread_curve
    for b_obj in bonds:
        date = b_obj.maturity_date
        bond_measures[b_obj.maturity_date] = [
            # bond_curve.get_rate(b_obj),
            # b_obj._yield_compounding.get_rate(bond_curve.get_spread_df(date), b_obj.get_settle_dcf(date)),
            bond_curve.get_spread_rate(date),
            b_obj.get_zspread(curve),
            f"{b_obj.name} {b_obj.coupon:.2%}",
        ]
    bill_measures = {}
    # for b_obj in bills:
    #     bill_yields[b_obj.maturity_date] = [b_obj.get_yield(), b_obj.name]
    return bond_measures, bill_measures, ['Bond Curve Spread', 'Zspread']
