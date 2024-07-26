from pydantic.dataclasses import dataclass
import datetime as dtm
from typing import Optional, Any

from common.chrono.tenor import Tenor
from instruments.bond import FixCouponBond
from instruments.bond_future import BondFutureBond
from common import sql
from data_api.config import META_DB


BONDFUT_REF_TABLE = 'bond_futures_reference'
FUTPROD_TENORS = {
    'ZT': (1+9/12, 2, 5+3/12, {}),
    # 'Z3N': (2+9/12, 3, 7, {}),
    'ZF': (4+2/12, 5+3/12, 5+3/12, {}),
    'ZN': (6+1/2, 7+3/4, None, {'_months_round': 3}),
    'TN': (9+5/12, 10, 10, {'_months_round': 3}),
    'ZB': (15, 25, None, {'_months_round': 3}),
    # 'TWE': (19+2/12, 19+11/12, None, {}),
    'UB': (25, None, None, {'_months_round': 3}),
}

def get_tenor(term: float):
    if isinstance(term, int): # or term == float(int(term))
        return Tenor(f'{term}y')
    else:
        return Tenor(f'{int(term*12)}m')

@dataclass
class BondFutureFactor(FixCouponBond):
    _months_round: int = 1

    @classmethod
    def create(cls, bond: FixCouponBond, factor_params: dict):
        return BondFutureFactor(bond._maturity_date, bond._coupon_rate, bond._coupon_frequency,
                        _settle_delay=bond._settle_delay, **factor_params)
    
    def _next_coupon_ratio(self, date: dtm.date):
        m_diff = date.month - self.settle_date.month + (date.year - self.settle_date.year) * 12
        assert m_diff < 6, f"Unexpected next cashflow to settle date {date}"
        m_inc = self._months_round
        return int(m_diff / m_inc) * m_inc / 6
    
    def get_settle_dcf(self, date: dtm.date) -> float:
        return self._next_coupon_ratio(date) * self.get_coupon_dcf()
    
    def get_accrued_interest(self, *_):
        return self._coupon_rate * self.get_coupon_dcf() * (1 - self._next_coupon_ratio(self.cashflows[0].date))
    
    def get_conversion_factor(self, ref_date: dtm.date, yield_norm: float):
        self.set_market(ref_date, None)
        return self.get_price_from_yield(yield_norm) / 100

def load_conversion_factors(
        code: str, expiry: dtm.date, bonds: list[FixCouponBond],
        min_tenor: Tenor, max_tenor: Tenor, original_term: Optional[float] = None,
        factor_params: dict[str, Any] = {}, ytm_standard: float = 0.06):
    ref_date = dtm.date(expiry.year, expiry.month, 1)
    min_maturity = min_tenor.get_date(ref_date)
    max_maturity = max_tenor.get_date(ref_date) if max_tenor else dtm.date.max
    insert_rows = []
    for bond in bonds:
        if (not original_term or bond.original_term <= original_term
            ) and min_maturity <= bond.maturity_date <= max_maturity:
            proxy = BondFutureFactor.create(bond, factor_params)
            conversion_factor = proxy.get_conversion_factor(ref_date, ytm_standard)
            insert_rows.append(f"('{code}', '{bond.name}', {conversion_factor})")
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
        min_term, max_term, original_term, factor_params = FUTPROD_TENORS[code[:2]]
        min_tenor, max_tenor = get_tenor(min_term), get_tenor(max_term) if max_term else None
        load_conversion_factors(code, expiry, bond_universe, min_tenor=min_tenor, max_tenor=max_tenor,
                                original_term=original_term, factor_params=factor_params)
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
