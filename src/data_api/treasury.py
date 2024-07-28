
import datetime as dtm
from io import StringIO
import pandas as pd

from common import request_web as request
from common.chrono import Frequency, Tenor
from instruments.bond import ZeroCouponBond
from instruments.coupon_bond import FixCouponBond
from common import sql
from data_api.config import META_DB

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
    res_df[COL_NAMES[1]] = res_df[COL_NAMES[1]].str.split().str[-1]
    res_df[COL_NAMES[3]] = pd.to_datetime(res_df[COL_NAMES[3]])
    # del res_df[COL_NAMES[4]]
    return res_df

CUSIP_COL, BUY_COL, SELL_COL, CLOSE_COL = (COL_NAMES[id] for id in [0, -3, -2, -1])
def get_bonds_price(date: dtm.date) -> dict[str, float]:
    res = {}
    for _, b_r in load_bonds_price(date).iterrows():
        if b_r[CLOSE_COL] == 0:            
            if b_r[BUY_COL] == 0:
                price = b_r[SELL_COL]
            else:
                price = (b_r[BUY_COL] + b_r[SELL_COL])/2
        else:
            price = b_r[CLOSE_COL]
        res[b_r[CUSIP_COL]] = price
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
    ('{bi['id']}', '{bond_type}', '{maturity_date}', {coupon}, '{issue_date}', '{original_term}')""")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {BONDS_REF_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    else:
        return True

def get_bonds_term() -> dict[str, str]:
    # load_bonds_details(dtm.date(1995, 1, 1))
    select_query = f"SELECT id, original_term FROM {BONDS_REF_TABLE} WHERE type IN ('Bond', 'Note')"
    term_res = sql.fetch(select_query, META_DB)
    return dict(term_res)

def get_bonds(date: dtm.date) -> list:
    select_query = f"""SELECT type, id, maturity, coupon, original_issue_date FROM {BONDS_REF_TABLE}
    WHERE maturity > '{date.strftime(sql.DATE_FORMAT)}'"""
    select_res = sql.fetch(select_query, META_DB)
    settle_delay = Tenor.bday(1)
    bonds_list = []
    for row in select_res:
        bond_type, bond_id = row[:2]
        maturity_date = dtm.datetime.strptime(row[2], sql.DATE_FORMAT)
        if bond_type in ('Note', 'Bond'):
            issue_date = dtm.datetime.strptime(row[4], sql.DATE_FORMAT)
            bonds_list.append(FixCouponBond(maturity_date, row[3], Frequency.SemiAnnual, issue_date,
                                            _settle_delay=settle_delay, name=bond_id))
        elif bond_type in ('Bill'):
            bonds_list.append(ZeroCouponBond(maturity_date, _settle_delay=settle_delay, name=bond_id))
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

# create_query = f"""CREATE TABLE {BONDS_REF_TABLE} (
#     id TEXT, type TEXT, maturity TEXT, coupon REAL, original_issue_date TEXT, original_term TEXT,
#     CONSTRAINT {BONDS_REF_TABLE}_pk PRIMARY KEY (id)
# )"""
# sql.modify(create_query, META_DB)
# archive_date = dtm.date(2024, 1, 1).strftime(sql.DATE_FORMAT)
# insert_query = "INSERT INTO bond_ref_archive SELECT * FROM {BONDS_REF_TABLE} WHERE maturity < '{archive_date}';"
# delete_query = "DELETE FROM {BONDS_REF_TABLE} WHERE maturity < '{archive_date}';"
