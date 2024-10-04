import datetime as dtm
import pandas as pd

from common.chrono import Frequency, Tenor
from instruments.bond.coupon_bond import FixCouponBond
from instruments.bond.inflation_bond import InflationIndexBond
from instruments.bond.zero_bond import ZeroCouponBond
from instruments.fixing import InflationIndex
from common import sql
from common.models.data_series import DataSeries
from data_api.db_config import META_DB, PRICES_DB
from data_api.treasury_config import *
from data_api import treasury_server as server


def get_bonds_price(date: dtm.date) -> dict[str, float]:
    price_query = f"SELECT id, price, buy, sell FROM {BONDS_PRICE_TABLE} WHERE date='{date.strftime(sql.DATE_FORMAT)}'"
    prices_list = sql.fetch(price_query, PRICES_DB)
    if not prices_list:
        load_res = server.load_bonds_price(date)
        if isinstance(load_res, pd.DataFrame):
            price_df = load_res[load_res[server.BUY_COL] > 0]
            mid = (price_df[server.BUY_COL] + price_df[server.SELL_COL]) / 2
            spread = price_df[server.BUY_COL] - price_df[server.SELL_COL]
            return dict(zip(price_df[server.CUSIP_COL], zip(mid, spread)))
        prices_list = sql.fetch(price_query, PRICES_DB)
    res = {}
    for row in prices_list:
        res[row[0]] = row[1], None if row[2] == 0 else row[2]-row[3]
    return res


def get_zero_bonds(date: dtm.date) -> list[ZeroCouponBond]:
    select_query = f"""SELECT id, maturity FROM {BONDS_REF_TABLE}
    WHERE type in ('Bill') AND maturity > '{date.strftime(sql.DATE_FORMAT)}'"""
    select_res = sql.fetch(select_query, META_DB)
    settle_delay = Tenor.bday(1)
    bonds_list = []
    for row in select_res:
        maturity_date = dtm.datetime.strptime(row[1], sql.DATE_FORMAT)
        bonds_list.append(ZeroCouponBond(maturity_date, _settle_delay=settle_delay, name=row[0]))
    return bonds_list

def get_coupon_bonds(date: dtm.date) -> list[FixCouponBond]:
    select_query = f"""SELECT id, maturity, coupon, original_issue_date, original_term FROM {BONDS_REF_TABLE}
    WHERE type in ('Bond', 'Note') AND maturity > '{date.strftime(sql.DATE_FORMAT)}'"""
    select_res = sql.fetch(select_query, META_DB)
    settle_delay = Tenor.bday(1)
    bonds_list = []
    for row in select_res:
        maturity_date = dtm.datetime.strptime(row[1], sql.DATE_FORMAT)
        issue_date = dtm.datetime.strptime(row[3], sql.DATE_FORMAT)
        term = row[4][:-1]
        bonds_list.append(FixCouponBond(maturity_date, row[2], Frequency.SemiAnnual, issue_date,
                                        _original_term=term, _settle_delay=settle_delay, name=row[0]))
    return bonds_list

INFLATION_ID = 'CPIAUNS'
def get_inflation_bonds(date: dtm.date) -> list[InflationIndexBond]:
    select_query = "SELECT id, maturity, coupon, original_issue_date, base_index_value "\
    f"FROM {BONDS_REF_TABLE} WHERE type in ('TIPS') AND maturity > '{date.strftime(sql.DATE_FORMAT)}'"
    select_res = sql.fetch(select_query, META_DB)
    settle_delay = Tenor.bday(1)
    bonds_list = []
    for row in select_res:
        maturity_date = dtm.datetime.strptime(row[1], sql.DATE_FORMAT)
        issue_date = dtm.datetime.strptime(row[3], sql.DATE_FORMAT)
        bonds_list.append(InflationIndexBond(maturity_date, row[2], Frequency.SemiAnnual, 
            issue_date, row[4], INFLATION_ID, _settle_delay=settle_delay, name=row[0]))
    return bonds_list

INFLATION_LAG = Tenor('3m')
def get_inflation_index(code: str):
    select_query = f"SELECT month, value FROM {INFLATION_TABLE} WHERE month >= '1993'"
    select_res = sql.fetch(select_query, PRICES_DB)
    res = dict()
    for row in select_res:
        fixing_month = INFLATION_LAG.get_date(dtm.datetime.strptime(row[0], '%Y-%m'))
        res[fixing_month] = float(row[1])
    return InflationIndex(name=code, _data_series=DataSeries(res))
