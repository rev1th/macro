import logging

from instruments.coupon_bond import FixCouponBond
from instruments.bond_future import BondFuture
import data_api.reader as data_reader
import data_api.cme as cme_api
import data_api.treasury as tsy_api
import lib.bond_future_helper as bond_fut_lib
from markets import usd_lib
from models.bond_future_model import BondFutureModel
from models.context import ConfigContext

logger = logging.Logger(__name__)


def get_contracts(code: str, value_date, bond_universe: list[FixCouponBond]) -> list[BondFuture]:
    listed_bond_futs = data_reader.read_bond_futures(code)
    futures_prices = cme_api.get_fut_settle_prices(code, value_date)
    bond_futs = []
    for ins in listed_bond_futs:
        if ins.name in futures_prices:
            price = futures_prices[ins.name]
            logger.info(f"Setting price for future {ins.name} to {price}")
            ins.data[value_date] = price
            ins._basket_bonds = bond_fut_lib.get_basket_bonds(ins.name, bond_universe, ins.expiry)
            bond_futs.append(ins)
        else:
            logger.info(f"No price found for future {ins.name}. Skipping")
    return bond_futs

CODE = 'UST'
def construct(value_date = None):
    last_value_date = usd_lib.get_last_valuation_date()
    if not value_date:
        value_date = last_value_date
    if not ConfigContext().has_coupon_bonds(CODE):
        ConfigContext().add_coupon_bonds(CODE, tsy_api.get_coupon_bonds(value_date))
    bond_universe = ConfigContext().get_coupon_bonds(CODE)
    bond_value_date = min(value_date, last_value_date)
    bonds_price = tsy_api.get_bonds_price(bond_value_date)
    for bond in bond_universe:
        if bond.name in bonds_price:
            bond.set_data(bond_value_date, bonds_price[bond.name][0])
    contracts = [get_contracts(code, value_date, bond_universe) for code in bond_fut_lib.FUTPROD_TENORS]
    return BondFutureModel(value_date, [c for cs in contracts for c in cs], 'USD-SOFR')
