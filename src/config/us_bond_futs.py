
import logging
from pydantic.dataclasses import dataclass
import pandas as pd

from common.base_class import NameDateClass
import common.chrono as date_lib
from instruments.bond import FixCouponBond
from instruments.bond_future import BondFuture
import data_api.parser as data_parser
import data_api.cme as cme_api
from config import us_bonds
from models.rate_curve_builder import get_rate_curve

logger = logging.Logger(__name__)


FUTPROD_TENORS = {
    'ZT': (1+9/12, 2, 5+3/12, {}, {'extra_tick_count': 8}),
    'ZF': (4+2/12, 5+3/12, 5+3/12, {}, {'extra_tick_count': 4}),
    'ZN': (6+1/2, 7+3/4, 10, {'_months_round': 3}, {'extra_tick_count': 2}),
    'TN': (9+5/12, 10, 10, {'_months_round': 3}, {'extra_tick_count': 2}),
    'ZB': (15, 25, None, {'_months_round': 3}, {}),
    'UB': (25, None, None, {'_months_round': 3}, {}),
}

def get_tenor(term: float):
    if isinstance(term, int): # or term == float(int(term))
        return date_lib.Tenor(f'{term}y')
    else:
        return date_lib.Tenor(f'{int(term*12)}m')

def get_contracts(value_date, bond_universe: list[FixCouponBond], code: str = 'TN') -> list[BondFuture]:
    min_term, max_term, original_term, factor_params, price_params = FUTPROD_TENORS[code]
    min_tenor, max_tenor = get_tenor(min_term), get_tenor(max_term) if max_term else None
    listed_bond_futs = data_parser.read_bond_futures(filename=f'{code}.csv',
                        min_tenor=min_tenor, max_tenor=max_tenor,
                        original_term=original_term, _factor_params=factor_params)
    _, futures_prices = cme_api.load_fut_settle_prices(code, value_date, price_params)
    bond_futs = []
    for ins in listed_bond_futs:
        if ins.name in futures_prices:
            price = futures_prices[ins.name]
            logger.info(f"Setting price for future {ins.name} to {price}")
            ins.set_market(value_date, price, bond_universe)
            bond_futs.append(ins)
        else:
            logger.info(f"No price found for future {ins.name}. Skipping")
    return bond_futs

@dataclass
class BondFutureModel(NameDateClass):
    _instruments: list[BondFuture]
    _curve_name: str

    def get_summary(self):
        res = []
        curve = get_rate_curve(self._curve_name, self.date)
        for bf in self._instruments:
            for bfb in bf.get_basket_metrics(curve):
                res.append((bf.display_name(), bf.expiry, bf.price, bfb.bond.display_name(), bfb.conversion_factor, 
                            bfb.delivery_date, bfb.net_basis, bfb.repo))
        return pd.DataFrame(res, columns=['Name', 'Expiry', 'Price', 'Bond', 'Conversion Factor',
                                        'Delviery Date', 'Net Basis', 'Implied Repo'])

def construct(value_date = None):
    last_settle_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=date_lib.Calendar.USEX)
    if not value_date:
        value_date = last_settle_date
    bond_date = min(value_date, last_settle_date)
    bond_universe = [b for b in us_bonds.get_bond_model(bond_date).bonds if isinstance(b, FixCouponBond)]
    contracts = [get_contracts(value_date, bond_universe, code) for code in FUTPROD_TENORS]
    return BondFutureModel(value_date, [c for cs in contracts for c in cs], 'USD-SOFR')
