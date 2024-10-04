import datetime as dtm
from io import StringIO
import pandas as pd

from common import request_web as request
from common import sql
from data_api.db_config import META_DB, PRICES_DB
from data_api.treasury_config import *


BONDS_PRICES_URL = 'https://savingsbonds.gov/GA-FI/FedInvest/securityPriceDetail'
COL_NAMES = ['CUSIP', 'TYPE', 'RATE', 'MATURITY_DATE', 'CALL_DATE', 'BUY', 'SELL', 'EOD']
CUSIP_COL, BUY_COL, SELL_COL, CLOSE_COL = (COL_NAMES[id] for id in [0, -3, -2, -1])
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


# BONDS_ARCHIVE_CUTOFF = dtm.date(2024, 1, 1).strftime(sql.DATE_FORMAT)
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
        if bond_type == 'TIPS':
            base_value = float(bi['refCpiOnDatedDate'])
            base_date = bi['originalDatedDate'] if bi['originalDatedDate'] else bi['datedDate']
            base_date = f"'{dtm.datetime.fromisoformat(base_date).strftime(sql.DATE_FORMAT)}'"
        else:
            base_value, base_date = 'NULL', 'NULL'
        insert_rows.append("\n("\
    f"'{bi['cusip']}', '{bond_type}', '{maturity_date}', {coupon}, '{issue_date}', "\
    f"'{original_term}', {base_value}, {base_date})""")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {BONDS_REF_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    else:
        return True


if __name__ == '__main__':
    # start = dtm.date(1994, 1, 1)
    start = dtm.date(2024, 10, 1)
    load_bonds_details(start)
    # from markets import usd_lib
    # for dt in usd_lib.get_valuation_dates(start):
    #     load_bonds_price(dt)

# create_query = f"""CREATE TABLE {BONDS_REF_TABLE} (
#     id TEXT, type TEXT, maturity TEXT, coupon REAL, original_issue_date TEXT, original_term TEXT,
#     base_index_value REAL, base_index_date TEXT,
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
