
import datetime as dtm
from io import StringIO
import pandas as pd

from common import request_web as request

BONDS_URL = 'https://savingsbonds.gov/GA-FI/FedInvest/securityPriceDetail'
COL_NAMES = ['CUSIP', 'TYPE', 'RATE', 'MATURITY_DATE', 'CALL_DATE', 'BUY', 'SELL', 'EOD']
def load_bonds_price(date: dtm.date) -> pd.DataFrame:
    params = {
        'priceDateDay': date.day,
        'priceDateMonth': date.month,
        'priceDateYear': date.year,
        'fileType': 'csv',
        'csv': 'CSV FORMAT',
    }
    content_csv = request.url_post(BONDS_URL, params)
    content_buffer = StringIO(content_csv)
    res_df = pd.read_csv(content_buffer, names=COL_NAMES)
    res_df[COL_NAMES[1]] = res_df[COL_NAMES[1]].str.split().str[-1]
    res_df[COL_NAMES[3]] = pd.to_datetime(res_df[COL_NAMES[3]])
    # del res_df[COL_NAMES[4]]
    return res_df
