
import os
import urllib.request as urlreq
import requests
import datetime as dtm
import json
import pandas as pd
import logging
import argparse

from . import core as data_core

logger = logging.Logger(__name__)

URL_STATUS_OK = 200
TIMEOUT_SECS = 20

def url_get(url: str, params: dict[str, any] = None):
    resp = requests.get(url, params=params, timeout=TIMEOUT_SECS, headers={"User-Agent":"Mozilla"})
    if resp.status_code == URL_STATUS_OK:
        return resp.content.decode()
    else:
        raise Exception(f'{resp.url} URL request failed {resp.reason}')
    # with urlreq.urlopen(url, timeout=TIMEOUT_SECS) as u:
    #     if u.status == URL_STATUS_OK:
    #         return u.read().decode()
    #     else:
    #         raise Exception(f'{u.url} URL request failed {u.reason}')

def url_get_json(url: str, params: dict[str, any] = None):
    return json.loads(url_get(url, params=params))

def url_post(url: str, params: dict[str, any] = None):
    resp = requests.post(url, params=params, timeout=TIMEOUT_SECS)
    if resp.status_code == URL_STATUS_OK:
        return resp.content.decode()
    else:
        raise Exception(f'{resp.url} URL request failed {resp.reason}')

# month codes
MONTHCODES = 'FGHJKMNQUVXZ'
MONTH_NAMES = [dtm.date(2023, m+1, 1).strftime('%b').upper() for m in range(12)]
MONTHMAP = dict(zip(MONTH_NAMES, MONTHCODES))
# MONTHMAP = dict([(i+1, MONTHCODES[i]) for i in range(12)])
# MONTHMAP.update(dict([(MONTHCODES[i], i+1) for i in range(12)]))

CME_DATE_FORMAT = "%m/%d/%Y"
CME_ENCODE_FORMAT = 'utf-8'

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
def load_cme_prices(contract_type: str = 'SOFR Futures'):
    with urlreq.urlopen(CME_FTP_URL, timeout=TIMEOUT_SECS) as u:
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


CFETS_FX_URL = 'https://iftp.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/fx-sw-curv-USD.CNY.json'
CFETS_DATE_FORMAT = '%Y-%m-%d'
def load_cfets_fx() -> tuple[dtm.date, list[tuple[str, float, dtm.date]]]:
    content_json = url_get_json(CFETS_FX_URL)
    content_data = content_json["data"]
    tenors = content_data["voArray"]
    data_date = dtm.datetime.strptime(content_data["showDateCN"], CFETS_DATE_FORMAT).date()
    res = []
    for tenor_i in tenors:
        tenor = tenor_i["tenor"]
        tenor_dt = dtm.datetime.strptime(tenor_i["valueDate"], CFETS_DATE_FORMAT).date()
        tenor_points = float(tenor_i["points"])
        res.append((tenor, tenor_points, tenor_dt))
    return (data_date, res)

CFETS_SPOT_URL = 'https://iftp.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/ccpr.json'
def load_cfets_spot() -> dict[str, tuple[str, float]]:
    content_json = url_get_json(CFETS_SPOT_URL)
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['foreignCName']] = (rec['vrtEName'], float(rec['price']))
    return res

CFETS_SWAPS_URL = 'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/Ifcc'
# CFETS_SWAPS_URL = 'https://iftp.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/Ifcc'
# '?lang=EN&cfgItemType={code}'
CFETS_SWAPS_CODEMAP = {
    'Shibor3M': 71,
    'FR007': 72,
}
def load_cfets_swaps(fixing_type: str = 'FR007') -> tuple[dtm.date, dict[str, float]]:
    content = url_get(CFETS_SWAPS_URL, params={'cfgItemType': CFETS_SWAPS_CODEMAP[fixing_type]})
    content_json = json.loads(content)
    content_metadata = content_json["data"]
    data_date = dtm.datetime.strptime(content_metadata["showDateCN"], CFETS_DATE_FORMAT).date()
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['tl']] = float(rec['optimalAvg'])
    return (data_date, res)

CFETS_FIXINGS_URL = 'https://iftp.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/frr.json'
CFETS_FIXINGS_DATE_FORMAT = '%Y-%m-%d %H:%M'
def load_cfets_fixings() -> tuple[dtm.date, dict[str, float]]:
    content = url_post(CFETS_FIXINGS_URL)
    content_json = json.loads(content)
    content_metadata = content_json["data"]
    data_date = dtm.datetime.strptime(content_metadata["showDateCN"], CFETS_FIXINGS_DATE_FORMAT).date()
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['productCode']] = float(rec['value'])
    return (data_date, res)


CME_FUTPROD_URL = 'https://www.cmegroup.com/CmeWS/mvc/ProductCalendar/Future/{code}'
CME_FUTPROD_MAP = {
    'SR3': 8462,
    'SR1': 8463,
    'FF': 305,
}
CME_FUTPROD_COLUMNS = ['productCode', 'contractMonth', 'firstTrade', 'lastTrade', 'settlement']
def load_cme_futs(code: str):
    fut_url = CME_FUTPROD_URL.format(code=CME_FUTPROD_MAP[code])
    content_json = url_get_json(fut_url)
    content_df = pd.DataFrame(content_json)[CME_FUTPROD_COLUMNS]
    content_df.set_index(CME_FUTPROD_COLUMNS[0], inplace=True)
    for col in CME_FUTPROD_COLUMNS[-3:]:
        content_df[col] = pd.to_datetime(content_df[col], format='%d %b %Y')
    filename = os.path.join(data_core.data_path(code, 'csv'))
    content_df.to_csv(filename, date_format=CME_DATE_FORMAT)
    logger.info(f"Saved {filename}")
    
    return content_df

CME_SWAP_URL = 'https://www.cmegroup.com/services/sofr-strip-rates/'
CME_SWAP_DATE_FORMAT = '%Y%m%d'
CME_SWAP_MAP = {
    'SOFR': "sofrRates",
    'FF': "sofrFedFundRates",
}
def load_cme_swap_data(fixing_type: str = 'SOFR') -> dict[dtm.date, dict[str, float]]:
    content_json = url_get_json(CME_SWAP_URL)
    curves = content_json["resultsCurve"]
    res = {}
    for curve_i in curves:
        curve_dt = dtm.datetime.strptime(curve_i["date"], CME_SWAP_DATE_FORMAT).date()
        res[curve_dt] = {tr["term"]: float(tr["price"]) for tr in curve_i["rates"][CME_SWAP_MAP[fixing_type]]}
    return res


NYFED_URL = 'https://markets.newyorkfed.org/read'
# '?startDt={start}&eventCodes={codes}&productCode=50&sort=postDt:-1,eventCode:1&format=csv'
NYFED_URL_DATE_FORMAT = '%Y-%m-%d'
NYFED_URL_CODEMAP = {
    'SOFR': 520,
    'EFFR': 500,
}
def load_fed_data(code: str, start: dtm.date = dtm.date(2023, 1, 1), save: bool = False):
    if code not in NYFED_URL_CODEMAP:
        raise Exception(f'{code} not found in URL mapping')
    params = {
        'startDt': start.strftime(NYFED_URL_DATE_FORMAT),
        'eventCodes': NYFED_URL_CODEMAP[code],
        'productCode': 50,
        'sort': 'postDt:-1,eventCode:1',
        'format': 'csv',
    }
    content = url_get(NYFED_URL, params=params)

    if save:
        filename = os.path.join(data_core.data_path(code, 'csv'))
        # os.rename(filename, filename + '.bkp')
        with open(filename, 'w') as f:
            f.write(content)
        logger.info(f"Saved {filename}")
    
    return [r.split(',') for r in content.split('\n')]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Data scraper')
    parser.add_argument('--fed', action='store_true')
    parser.add_argument('-f', '--fixings', default='SOFR,EFFR')
    parser.add_argument('--cme', action='store_true')
    parser.add_argument('--futures', default='SR1')
    args = parser.parse_args()
    print(args)
    if args.fed:
        for fix in args.fixings.split(','):
            load_fed_data(fix, save=True)
    if args.cme:
        load_cme_futs(args.futures)
    # load_cme_swap_data()
    # op = load_cme_prices()
    # for key, val in op.items():
    #     for key2, val2 in val.items():
    #         print(key, key2, val2)
