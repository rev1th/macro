
import logging

from instruments.bond import FixCouponBond
from instruments.bond_future import BondFuture
import data_api.reader as data_reader
import data_api.cme as cme_api
import data_api.treasury as tsy_api
from config import usd_mkt
import lib.bond_future_helper as bond_fut_lib
from models.bond_future_model import BondFutureModel

logger = logging.Logger(__name__)


def get_contracts(code: str, value_date, bond_universe: list[FixCouponBond]) -> list[BondFuture]:
    listed_bond_futs = data_reader.read_bond_futures(code)
    futures_prices = cme_api.get_fut_settle_prices(code, value_date)
    bond_futs = []
    for ins in listed_bond_futs:
        if ins.name in futures_prices:
            price = futures_prices[ins.name]
            logger.info(f"Setting price for future {ins.name} to {price}")
            ins.set_market(value_date, price)
            ins._basket_bonds = bond_fut_lib.get_basket_bonds(ins.name, bond_universe, ins.expiry)
            bond_futs.append(ins)
        else:
            logger.info(f"No price found for future {ins.name}. Skipping")
    return bond_futs

_BOND_UNIVERSE: list[FixCouponBond] = None
def construct(value_date = None):
    global _BOND_UNIVERSE
    last_settle_date = usd_mkt.get_last_valuation_date()
    if not value_date or not _BOND_UNIVERSE:
        value_date = last_settle_date
        _BOND_UNIVERSE = tsy_api.get_coupon_bonds(value_date)
    settle_date = min(value_date, last_settle_date)
    bonds_price = tsy_api.get_bonds_price(settle_date)
    for bond in _BOND_UNIVERSE:
        bond.set_market(settle_date, bonds_price[bond.name])
    contracts = [get_contracts(code, value_date, _BOND_UNIVERSE) for code in bond_fut_lib.FUTPROD_TENORS]
    return BondFutureModel(value_date, [c for cs in contracts for c in cs], 'USD-SOFR')
