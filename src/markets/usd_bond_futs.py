import logging

from instruments.bond_future import BondFuture
from data_api import cme_client, db_reader, treasury_client as tsy_client
import lib.bond_future_helper as bond_fut_lib
from markets import usd_lib
from models.bond_future_model import BondFutureModel
from models.config_context import ConfigContext

logger = logging.Logger(__name__)


def get_contracts(code: str, value_date) -> list[BondFuture]:
    bond_futs = ConfigContext().get_bond_futures(code)
    futures_prices = cme_client.get_future_settle_prices(code, value_date)
    contracts_active = []
    for ins in bond_futs:
        if ins.name in futures_prices:
            price = futures_prices[ins.name]
            logger.info(f"Setting price for future {ins.name} to {price}")
            ins.data[value_date] = price
            contracts_active.append(ins)
        else:
            logger.info(f"No price found for future {ins.name}. Skipping")
    return contracts_active

CODE = 'UST'
def construct(value_date = None):
    last_value_date = usd_lib.get_last_trade_date()
    if not value_date:
        value_date = last_value_date
    if not ConfigContext().has_coupon_bonds(CODE):
        ConfigContext().add_coupon_bonds(CODE, tsy_client.get_coupon_bonds(value_date))
    bond_universe = ConfigContext().get_coupon_bonds(CODE)
    contracts = []
    for code in bond_fut_lib.FUTPROD_TENORS:
        if not ConfigContext().has_bond_futures(code):
            bond_futs = db_reader.read_bond_futures(code)
            ConfigContext().add_bond_futures(code, bond_futs)
            for ins in bond_futs:
                if ins.expiry > value_date:
                    ins._basket_bonds = bond_fut_lib.get_basket_bonds(ins.name, bond_universe, ins.expiry)
        contracts.extend(get_contracts(code, value_date))
    bond_value_date = min(value_date, last_value_date)
    bonds_price = tsy_client.get_bonds_price(bond_value_date)
    for bond in bond_universe:
        if bond.name in bonds_price:
            bond.set_data(value_date, bonds_price[bond.name][0])
    return BondFutureModel(value_date, contracts, 'USD-SOFR')
