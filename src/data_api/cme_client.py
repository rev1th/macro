import datetime as dtm

from common import sql
from data_api.db_config import META_DB, PRICES_DB
from data_api.cme_config import *
from data_api import cme_server as server
from data_api.cme_server import get_option_settle_prices

def get_futures_contracts(series: str):
    underlier_query = f"SELECT underlier_code, lot_size FROM {FUT_TABLE} WHERE future_code='{series}'"
    underlier, lot_size = sql.fetch(underlier_query, META_DB, count=1)
    contracts_query = "SELECT contract_code, last_trade_date, settlement_date "\
    f"FROM {RATE_FUT_PROD_TABLE} WHERE series_id='{series}' ORDER BY last_trade_date"
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], dtm.datetime.strptime(row[1], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date(), underlier, lot_size)
                    for row in contracts_list]
    return contracts_fmt

def get_bond_futures_contracts(series: str):
    contracts_query = "SELECT contract_code, last_trade_date, first_delivery_date, last_delivery_date "\
    f"FROM {BOND_FUT_PROD_TABLE} WHERE series_id='{series}'"
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], dtm.datetime.strptime(row[1], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[3], sql.DATE_FORMAT).date()
                    ) for row in contracts_list]
    return contracts_fmt

def get_options_contracts(series: str):
    contracts_query = "SELECT contract_code, underlier_code, last_trade_date "\
    f"FROM {OPT_PROD_TABLE} WHERE series_id='{series}' ORDER BY last_trade_date"
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], row[1], dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date())
                    for row in contracts_list]
    return contracts_fmt


def get_future_settle_prices(code: str, settle_date: dtm.date):
    price_query = f"SELECT contract_code, close_price, open_interest FROM {FUTURES_PRICE_TABLE} "\
    f"WHERE contract_code LIKE '{code}%' AND date='{settle_date.strftime(sql.DATE_FORMAT)}'"
    prices_list = sql.fetch(price_query, PRICES_DB)
    if not prices_list:
        fut_data_dates = server.load_future_data_dates(code=code)
        if settle_date > fut_data_dates[0]:
            return server.load_future_quotes(code)[1]
        elif settle_date in fut_data_dates:
            if not server.load_future_settle_prices(code, settle_date):
                raise RuntimeError(f"Futures prices not loaded for {code} on {settle_date}")
        else:
            raise ValueError(f"Futures prices not available for {code} on {settle_date}")
        prices_list = sql.fetch(price_query, PRICES_DB)
    res: dict[str, float] = {}
    max_oi = 0
    for row in prices_list:
        contract_code, settle_price, oi = row
        max_oi = max(oi, max_oi)
        if oi > max_oi * FUT_OI_MIN_MAX:
            res[contract_code] = settle_price
    return res


def get_swap_data(code: str, date: dtm.date) -> dict[str, float]:
    rates_query = f"SELECT term, rate FROM {SWAP_RATES_TABLE} "\
    f"WHERE code='{code}' AND date='{date.strftime(sql.DATE_FORMAT)}'"
    rates_list = sql.fetch(rates_query, PRICES_DB)
    if not rates_list:
        if not server.load_swap_data(date):
            raise RuntimeError(f"Swap data not loaded for {code}")
        rates_list = sql.fetch(rates_query, PRICES_DB)
    return dict(rates_list)

