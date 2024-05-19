
import logging
from pydantic.dataclasses import dataclass
import pandas as pd

import common.chrono as date_lib
from common.chrono import Tenor
from models.bond import FixCouponBond
from models.bond_future import BondFuture
import data_api.parser as data_parser
import data_api.cme as data_cme
from config import us_bonds

logger = logging.Logger(__name__)


FUTPROD_TENORS = {
    'ZT': (1+9/12, 2, 5+3/12, {'extra_tick_count': 8}),
    'ZF': (4+2/12, 5+3/12, 5+3/12, {'extra_tick_count': 4}),
    'ZN': (6+1/2, 7+3/4, None, {'extra_tick_count': 2}),
    'TN': (9+5/12, 10, 10, {'extra_tick_count': 2}),
    'ZB': (15, 25, None, {}),
    'UB': (25, None, None, {}),
}

def get_tenor(term: float):
    if isinstance(term, int): # or term == float(int(term))
        return Tenor(f'{term}y')
    else:
        return Tenor(f'{int(term*12)}m')

def get_contracts(value_date, code: str = 'TN') -> list[BondFuture]:
    min_term, max_term, original_term, price_params = FUTPROD_TENORS[code]
    min_tenor, max_tenor = get_tenor(min_term), get_tenor(max_term) if max_term else None
    listed_bond_futs = data_parser.read_bond_futures(filename=f'{code}.csv',
                        min_tenor=min_tenor, max_tenor=max_tenor, original_term=original_term)
    _, futures_prices = data_cme.load_fut_settle_prices(code, value_date, price_params)
    bond_futs = []
    bonds = [b for b in us_bonds.construct().bonds if isinstance(b, FixCouponBond)]
    for ins in listed_bond_futs:
        if ins.name in futures_prices:
            price = futures_prices[ins.name]
            logger.info(f"Setting price for future {ins.name} to {price}")
            ins.set_market(value_date, price, bonds)
            bond_futs.append(ins)
        else:
            logger.info(f"No price found for future {ins.name}. Skipping")
    return bond_futs

@dataclass
class BondFutureModel:
    _instruments: list[BondFuture]

    def get_summary(self):
        res = []
        for bf in self._instruments:
            brs = bf.get_implied_repos()
            for br in brs:
                res.append((bf.display_name(), bf.expiry, bf.price, bf.first_delivery, br[2].display_name(), br[0], br[1]))
        return pd.DataFrame(res,
            columns=['Name', 'Expiry', 'Price', 'First Delivery', 'Bond', 'Implied Repo', 'Delviery Date']
        )

def construct(value_date = None):
    if not value_date:
        value_date = date_lib.get_last_valuation_date(timezone='America/New_York', calendar=date_lib.Calendar.USEX)
    contracts = [get_contracts(value_date, code) for code in FUTPROD_TENORS]
    return BondFutureModel([c for cs in contracts for c in cs])
