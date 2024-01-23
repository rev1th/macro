
import urllib.request as urlreq
import datetime as dtm
import pandas as pd
import logging
import argparse

from common import request_web as request, io

logger = logging.Logger(__name__)

# month codes
MONTHCODES = 'FGHJKMNQUVXZ'
MONTH_NAMES = [dtm.date(2023, m+1, 1).strftime('%b').upper() for m in range(12)]
MONTHMAP = dict(zip(MONTH_NAMES, MONTHCODES))
# MONTHMAP = dict([(i+1, MONTHCODES[i]) for i in range(12)])
# MONTHMAP.update(dict([(MONTHCODES[i], i+1) for i in range(12)]))

CME_DATE_FORMAT = "%m/%d/%Y"
CME_ENCODE_FORMAT = 'utf-8'
CME_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
    'Accept-Language': 'en',
}

def month_code(month: str) -> str:
    return MONTHMAP[month]

CME_FTP_URL = 'ftp://ftp.cmegroup.com/pub/settle/stlint_v2'
# https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/8463/FUT?tradeDate=08/11/2023
# https://www.cmegroup.com/CmeWS/mvc/Quotes/ContractsByNumber?productIds=8463&contractsNumber=100&venue=G
# ['MONTH','OPEN','HIGH','LOW','LAST','SETT','CHGE','EST.VOL','P_SETT','P_VOL','P_INT']
CME_COLUMNS_TO_READ = ['MONTH','OPEN','HIGH','LOW','LAST','SETT','CHGE']
CME_PRICE_MAP = {
    'SOFR': 'SOFR Futures',
    'FF': 'Federal Fund Futures',
}
# Inspired by https://gist.github.com/tristanwietsma/5486236
def load_prices(contract_type: str = 'SOFR Futures'):
    with urlreq.urlopen(CME_FTP_URL, timeout=request.TIMEOUT_SECS) as u:
        lines = u.readlines()
        if lines[0]:
            li = lines[0].strip()
            logger.info(li)
            lines.pop(0)
            header = li.decode(CME_ENCODE_FORMAT).split()
            price_date = dtm.datetime.strptime(header[5], CME_DATE_FORMAT).date()
    
    res: dict[str, dict[str, float]] = {}
    key = None
    contract_suffix = CME_PRICE_MAP[contract_type].encode(CME_ENCODE_FORMAT)
    for li in lines:
        li = li.strip()
        if not li:
            key = None
            continue
        if li.endswith(contract_suffix):
            desc = li.decode(CME_ENCODE_FORMAT).split()
            logger.info(f"Adding {' '.join(desc[1:])}")
            key = desc[0]
            if key in res:
                raise Exception(f'Found duplciate key for {key}')
            res[key] = {}
            continue
        if key:
            cells = li.decode(CME_ENCODE_FORMAT).split()
            if cells[0] == 'TOTAL':
                key = None
                continue
            if len(cells) < len(CME_COLUMNS_TO_READ):
                raise Exception(f'Invalid data for {key}')
            cells = cells[:len(CME_COLUMNS_TO_READ)]
            try:
                contract_month = month_code(cells[0][:3]) + cells[0][3:]
                settle_price = float(cells[-2])
            except:
                key = None
                continue
            res[key][contract_month] = settle_price
    return (price_date, res)


CME_FUTPROD_URL = 'https://www.cmegroup.com/CmeWS/mvc/ProductCalendar/Future/{code}'
CME_FUTPROD_MAP = {
    'SR3': 8462,
    'SR1': 8463,
    'FF': 305,
}
CME_FUTPROD_COLUMNS = ['productCode', 'contractMonth', 'firstTrade', 'lastTrade', 'settlement']
def load_futures(code: str):
    fut_url = CME_FUTPROD_URL.format(code=CME_FUTPROD_MAP[code])
    content_json = request.get_json(request.url_get(fut_url, headers=CME_HEADERS))
    content_df = pd.DataFrame(content_json)[CME_FUTPROD_COLUMNS]
    content_df.set_index(CME_FUTPROD_COLUMNS[0], inplace=True)
    for col in CME_FUTPROD_COLUMNS[-3:]:
        content_df[col] = pd.to_datetime(content_df[col], format='%d %b %Y')
    filename = io.get_path(code, format='csv')
    content_df.to_csv(filename, date_format=CME_DATE_FORMAT)
    logger.info(f"Saved {filename}")
    
    return content_df

CME_SWAP_URL = 'https://www.cmegroup.com/services/sofr-strip-rates/'
CME_SWAP_DATE_FORMAT = '%Y%m%d'
CME_SWAP_MAP = {
    'SOFR': "sofrRates",
    'FF': "sofrFedFundRates",
}
def load_swap_data(fixing_type: str = 'SOFR') -> dict[dtm.date, dict[str, float]]:
    content_json = request.get_json(request.url_get(CME_SWAP_URL, headers=CME_HEADERS))
    curves = content_json["resultsCurve"]
    res = {}
    for curve_i in curves:
        curve_dt = dtm.datetime.strptime(curve_i["date"], CME_SWAP_DATE_FORMAT).date()
        res[curve_dt] = {tr["term"]: float(tr["price"]) for tr in curve_i["rates"][CME_SWAP_MAP[fixing_type]]}
    return res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CME data scraper')
    parser.add_argument('--futures', default='SR1')
    args = parser.parse_args()
    print(args)
    for fut in args.futures.split(','):
        load_futures(fut)
    # load_swap_data()
    # op = load_prices()
    # for key, val in op.items():
    #     for key2, val2 in val.items():
    #         print(key, key2, val2)
