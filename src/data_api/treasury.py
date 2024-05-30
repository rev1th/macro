
import datetime as dtm
from io import StringIO
import pandas as pd

from common import request_web as request

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

BONDS_DETAILS_URL = 'https://www.treasurydirect.gov/TA_WS/securities/search'
def load_bonds_details(start: dtm.date):
    params = {
        'startDate': start.strftime('%Y-%m-%d'),
        'dateFieldName': 'auctionDate',
        'format': 'json',
    }
    content_json = request.get_json(request.url_get(BONDS_DETAILS_URL, params))
    return content_json

def load_bonds_term(start: dtm.date) -> dict[str, str]:
    bonds_info = load_bonds_details(start)
    res = {}
    for bi in bonds_info:
        res[bi['cusip']] = bi['originalSecurityTerm']
    return res
