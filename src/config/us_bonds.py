
import logging

import common.chrono as date_lib
from models.bond import Bill, Bond
import data_api.treasury as td

logger = logging.Logger(__name__)

def construct():
    us_cal = 'US-NY'
    val_dt = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=us_cal)
    bond_prices = td.load_bond_prices(val_dt)
    bonds_all = []
    bills_all = []
    for _, b_r in bond_prices.iterrows():
        if b_r['TYPE'] == 'BILL':
            bill_obj = Bill(b_r['MATURITY_DATE'], name=b_r['CUSIP'], _settle_delay=date_lib.Tenor.bday(1))
            bill_obj.set_market(val_dt, b_r['EOD'])
            bills_all.append(bill_obj)
        elif b_r['TYPE'] == 'NOTE' or b_r['TYPE'] == 'BOND':
            bond_obj = Bond(b_r['MATURITY_DATE'], b_r['RATE'], date_lib.Frequency.SemiAnnual,
                            _daycount_type = date_lib.DayCount.ACT365,
                            _settle_delay=date_lib.Tenor.bday(1),
                            name=b_r['CUSIP'])
            bond_obj.set_market(val_dt, b_r['EOD'])
            bonds_all.append(bond_obj)
    return bonds_all, bills_all
    
def get_graph_info(bonds: list[Bond], bills: list[Bill]):
    bond_yields = {}
    for b_obj in bonds:
        if b_obj.settle_date < b_obj.maturity_date:
            bond_yields[b_obj.maturity_date] = [b_obj.get_yield(), f"{b_obj.name} {b_obj.coupon:.2%}"]
    bill_yields = {}
    for b_obj in bills:
        if b_obj.settle_date < b_obj.maturity_date:
            bill_yields[b_obj.maturity_date] = [b_obj.get_yield(), b_obj.name]
    return bond_yields, bill_yields