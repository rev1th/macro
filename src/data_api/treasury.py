import datetime as dtm
from io import StringIO
import pandas as pd

from common import request_web as request
from common.chrono import Frequency, Tenor
from instruments.bond import ZeroCouponBond
from instruments.coupon_bond import FixCouponBond
from common import sql
from data_api.config import META_DB, PRICES_DB


BONDS_PRICE_TABLE = 'bonds_close'
BONDS_PRICES_URL = 'https://savingsbonds.gov/GA-FI/FedInvest/securityPriceDetail'
COL_NAMES = ['CUSIP', 'TYPE', 'RATE', 'MATURITY_DATE', 'CALL_DATE', 'BUY', 'SELL', 'EOD']
def load_bonds_price(date: dtm.date) -> pd.DataFrame:
    params = {
        'priceDateDay': date.day,
        'priceDateMonth': date.month,
        'priceDateYear': date.year,
        'fileType': 'csv',
        'csv': 'CSV FORMAT',
    }
    content_csv = request.url_post(BONDS_PRICES_URL, params)
    content_buffer = StringIO(content_csv)
    res_df = pd.read_csv(content_buffer, names=COL_NAMES)
    if sum(res_df[CLOSE_COL]) == 0:
        return res_df
    # res_df[COL_NAMES[1]] = res_df[COL_NAMES[1]].str.split().str[-1]
    # res_df[COL_NAMES[3]] = pd.to_datetime(res_df[COL_NAMES[3]])
    insert_rows = []
    date_str = date.strftime(sql.DATE_FORMAT)
    for _, row in res_df.iterrows():
        insert_rows.append(f"\n('{row[CUSIP_COL]}', '{date_str}', {row[CLOSE_COL]}, {row[BUY_COL]}, {row[SELL_COL]})")
    if insert_rows:
        insert_query = (f"INSERT INTO {BONDS_PRICE_TABLE} VALUES {','.join(insert_rows)};")
        return sql.modify(insert_query, PRICES_DB)
    return False

CUSIP_COL, BUY_COL, SELL_COL, CLOSE_COL = (COL_NAMES[id] for id in [0, -3, -2, -1])
def get_bonds_price(date: dtm.date) -> dict[str, float]:
    price_query = f"SELECT id, price, buy, sell FROM {BONDS_PRICE_TABLE} WHERE date='{date.strftime(sql.DATE_FORMAT)}'"
    prices_list = sql.fetch(price_query, PRICES_DB)
    if not prices_list:
        load_res = load_bonds_price(date)
        if isinstance(load_res, pd.DataFrame):
            price_df = load_res[load_res[BUY_COL] > 0]
            mid = (price_df[BUY_COL] + price_df[SELL_COL]) / 2
            spread = price_df[BUY_COL] - price_df[SELL_COL]
            return dict(zip(price_df[CUSIP_COL], zip(mid, spread)))
        prices_list = sql.fetch(price_query, PRICES_DB)
    res = {}
    for row in prices_list:
        res[row[0]] = row[1], None if row[2] == 0 else row[2]-row[3]
    return res


BONDS_REF_TABLE = 'bond_reference'
BONDS_DETAILS_URL = 'https://www.treasurydirect.gov/TA_WS/securities/search'
def load_bonds_details(start: dtm.date):
    params = {
        'startDate': start.strftime('%Y-%m-%d'),
        'dateFieldName': 'auctionDate',
        'format': 'json',
    }
    bonds_info = request.get_json(request.url_get(BONDS_DETAILS_URL, params))
    insert_rows = []
    today = dtm.date.today()
    for bi in bonds_info:
        auction_date = dtm.datetime.fromisoformat(bi['auctionDate']).date()
        if auction_date >= today:
            continue
        bond_type = bi['type']
        if bond_type == 'CMB':
            bond_type = 'Bill'
        issue_date = bi['originalIssueDate'] if bi['originalIssueDate'] else bi['issueDate']
        issue_date = dtm.datetime.fromisoformat(issue_date).strftime(sql.DATE_FORMAT)
        maturity_date = dtm.datetime.fromisoformat(bi['maturityDate']).strftime(sql.DATE_FORMAT)
        term_code = bi['originalSecurityTerm'].split('-')
        original_term = f'{term_code[0]}{term_code[1][0]}'
        if bi['interestRate']:
            coupon = float(bi['interestRate']) / 100
        else:
            assert bond_type in ('Bill', 'FRN'), f'Invalid coupon rate for {bond_type}'
            coupon = 'NULL'
        insert_rows.append(f"""
    ('{bi['cusip']}', '{bond_type}', '{maturity_date}', {coupon}, '{issue_date}', '{original_term}')""")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {BONDS_REF_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    else:
        return True

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

if __name__ == '__main__':
    # start = dtm.date(1994, 1, 1)
    start = dtm.date(2024, 8, 1)
    load_bonds_details(start)
    # from markets import usd_lib
    # for dt in usd_lib.get_valuation_dates(start):
    #     load_bonds_price(dt)

# create_query = f"""CREATE TABLE {BONDS_REF_TABLE} (
#     id TEXT, type TEXT, maturity TEXT, coupon REAL, original_issue_date TEXT, original_term TEXT,
#     CONSTRAINT {BONDS_REF_TABLE}_pk PRIMARY KEY (id)
# )"""
# sql.modify(create_query, META_DB)
# archive_date = dtm.date(2024, 1, 1).strftime(sql.DATE_FORMAT)
# insert_query = "INSERT INTO bond_ref_archive SELECT * FROM {BONDS_REF_TABLE} WHERE maturity < '{archive_date}';"
# delete_query = "DELETE FROM {BONDS_REF_TABLE} WHERE maturity < '{archive_date}';"

# create_query = f"""CREATE TABLE {BONDS_PRICE_TABLE} (
#     id TEXT, date TEXT, price REAL, buy REAL, sell REAL,
#     CONSTRAINT {BONDS_PRICE_TABLE}_pk PRIMARY KEY (id, date)
# )"""
# sql.modify(create_query, PRICES_DB)

# INFLATION_TABLE = 'inflation_index'
# create_query = f"""CREATE TABLE {INFLATION_TABLE} (
#     id TEXT, month TEXT, value REAL,
#     CONSTRAINT {INFLATION_TABLE}_pk PRIMARY KEY (id, month)
# )"""
# sql.modify(create_query, PRICES_DB)
# file = 'C:\Users\Revanth\Downloads\CPIAUCNS.csv'
# df = pd.read_csv(file)
# DATE_FORMAT = '%Y-%m'
# insert_rows = []
# for _, row in df.iterrows():
#     month = dtm.datetime.strptime(row['DATE'], '%Y-%m-%d').strftime(DATE_FORMAT)
#     insert_rows.append(f"('CPIAUCNS', '{month}', {row['CPIAUCNS']})")
# insert_query = (f"INSERT INTO {INFLATION_TABLE} VALUES {','.join(insert_rows)};")
# sql.modify(insert_query, PRICES_DB)
