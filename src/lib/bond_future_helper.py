from pydantic.dataclasses import dataclass
import datetime as dtm

from common import sql
from common.chrono.tenor import Tenor
from instruments.bonds.coupon_bond import FixCouponBond, CashFlow, BondYieldParameters
from instruments.bond_future import BondFutureBond
from data_api.db_config import META_DB


BONDFUT_REF_TABLE = 'bond_futures_reference'
FUTPROD_TENORS = {
    'ZT': (1+9/12, 2, 5+3/12, {}),
    # 'Z3N': (2+9/12, 3, 7, {}),
    'ZF': (4+2/12, 5+3/12, 5+3/12, {}),
    'ZN': (6+1/2, 8, None, {'_month_increment': 3}),
    'TN': (9+5/12, 10, 10, {'_month_increment': 3}),
    'ZB': (15, 25, None, {'_month_increment': 3}),
    # 'TWE': (19+2/12, 19+11/12, None, {}),
    'UB': (25, None, None, {'_month_increment': 3}),
}

def get_tenor(term: float):
    if isinstance(term, int): # or term == float(int(term))
        return Tenor(f'{term}y')
    else:
        return Tenor(f'{int(term*12)}m')

def _next_coupon_ratio(ref_date: dtm.date, coupon_date: dtm.date, month_step: int):
    m_diff = coupon_date.month - ref_date.month + (coupon_date.year - ref_date.year) * 12
    assert m_diff < 6, f"Unexpected settle date to next cashflow {coupon_date}"
    return int(m_diff / month_step) * month_step / 6

@dataclass
class BondFactorYieldParams(BondYieldParameters):
    month_step: int = 1
    
    def get_dcf(self, from_date: dtm.date, to_date: dtm.date) -> float:
        return _next_coupon_ratio(from_date, to_date, self.month_step) * self.get_period_dcf()

@dataclass
class BondFutureFactor(FixCouponBond):
    _month_increment: int = 1
    
    @classmethod
    def create(cls, bond: FixCouponBond, factor_params: dict):
        return cls(bond._maturity_date, bond._coupon_rate, bond._coupon_frequency,
            _first_settle_date=bond._first_settle_date, _settle_delay=bond._settle_delay, **factor_params)
    
    def get_accrued_interest(self, settle_date: dtm.date, cashflow: CashFlow):
        return cashflow.amount * (1 - _next_coupon_ratio(settle_date, cashflow.date, self._month_increment))
    
    def get_conversion_factor(self, date: dtm.date, yield_norm: float):
        yield_params = BondFactorYieldParams(month_step=self._month_increment)
        return self._price_from_yield(yield_norm, self.get_settle_info(date), yield_params) / 100

def load_conversion_factors(
        code: str, expiry: dtm.date, bonds: list[FixCouponBond],
        ytm_standard: float = 0.06):
    ref_date = dtm.date(expiry.year, expiry.month, 1)
    min_term, max_term, original_term, factor_params = FUTPROD_TENORS[code[:2]]
    min_maturity = get_tenor(min_term).get_date(ref_date)
    max_maturity = get_tenor(max_term).get_date(ref_date) if max_term else dtm.date.max
    insert_rows = []
    for bond in bonds:
        if bond._first_settle_date <= expiry and \
            (not original_term or bond.original_term <= original_term) and \
            min_maturity <= bond.maturity_date <= max_maturity:
            factor_obj = BondFutureFactor.create(bond, factor_params)
            conversion_factor = factor_obj.get_conversion_factor(ref_date, ytm_standard)
            insert_rows.append(f"\n('{code}', '{bond.name}', {conversion_factor})")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {BONDFUT_REF_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    else:
        return True

def get_basket_bonds(code: str, bond_universe: list[FixCouponBond],
                     expiry: dtm.date = None) -> list[BondFutureBond]:
    select_query = f"""SELECT bond_id, conversion_factor FROM {BONDFUT_REF_TABLE}
    WHERE contract_code='{code}'"""
    select_rows = sql.fetch(select_query, META_DB)
    if not select_rows:
        load_conversion_factors(code, expiry, bond_universe)
        select_rows = sql.fetch(select_query, META_DB)
    bond_cfs = dict(select_rows)
    basket_bonds = []
    for bond in bond_universe:
        if bond.name in bond_cfs:
            basket_bonds.append(BondFutureBond(bond, bond_cfs[bond.name]))
    return basket_bonds

# create_query = f"""CREATE TABLE {BONDFUT_REF_TABLE} (
#     contract_code TEXT, bond_id TEXT, conversion_factor REAL,
#     CONSTRAINT {BONDFUT_REF_TABLE}_pk PRIMARY KEY (contract_code, bond_id)
# )"""
# sql.modify(create_query, META_DB)
