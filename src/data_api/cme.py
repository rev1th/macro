
import datetime as dtm
import pandas as pd
import logging
import argparse

from common import request_web as request, io
from common.models.data import DataPointType

logger = logging.Logger(__name__)

# month codes
MONTHCODES = 'FGHJKMNQUVXZ'
MONTH_NAMES = [dtm.date(2023, m+1, 1).strftime('%b').upper() for m in range(12)]
MONTHMAP = dict(zip(MONTH_NAMES, MONTHCODES))
MONTHMAP['JLY'] = MONTHMAP['JUL']
# MONTHMAP = dict([(i+1, MONTHCODES[i]) for i in range(12)])
# MONTHMAP.update(dict([(MONTHCODES[i], i+1) for i in range(12)]))

DATE_FORMAT = "%m/%d/%Y"
ENCODE_FORMAT = 'utf-8'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
    'Accept-Language': 'en',
}

def get_month_code(month: str) -> str:
    return MONTHMAP[month]

def is_valid_price(price: str):
    return price != '-' and price[-1] not in ('A', 'B')

def str_to_num(num: str, num_type = float) -> float:
    return num_type(num.replace(',', ''))

def transform_quote(quote: str, price_params: dict = None):
    if price_params is None:
        return float(quote)
    extra_tick = False
    if 'extra_tick_count' in price_params:
        extra_tick, extra_tick_count = True, price_params['extra_tick_count']
    quote_parts = quote.split('\'')
    if len(quote_parts) != 2 or len(quote_parts[1]) != (3 if extra_tick else 2):
        raise RuntimeError(f'Invalid quote format {quote}')
    quote_p1, quote_p2 = quote_parts
    quote_p3 = (float(quote_p2[2]) / extra_tick_count) if extra_tick else 0
    return float(quote_p1) + (float(quote_p2[:2]) + quote_p3) / 32

def get_field(data_dict: dict[str, any], datapoint_type: DataPointType, params: dict = None):
    match datapoint_type:
        case DataPointType.LAST:
            return transform_quote(data_dict['last'], params) if is_valid_price(data_dict['last']) else None
        case DataPointType.SETTLE:
            return transform_quote(data_dict['settle'], params) if is_valid_price(data_dict['settle']) else None
        case DataPointType.VOLUME:
            return str_to_num(data_dict['volume'], int) if data_dict['volume'] else None
        case DataPointType.PREV_OI:
            return str_to_num(data_dict['openInterest'], int) if data_dict['openInterest'] else None
        case _:
            logger.error(f'Unhandled {datapoint_type}')

FUTPROD_URL = 'https://www.cmegroup.com/CmeWS/mvc/ProductCalendar/Future/{code}'
FUTPRODID_MAP = {
    'SR3': 8462,
    'SR1': 8463,
    'FF': 305,

    'ZT': '303',
    # 'Z3N': '2666',  #2 9/12 - 3, <=7
    'ZF': '329',
    'ZN': '316',
    'TN': '7978',
    'ZB': '307',
    # 'TWE': '10072', #19 2/12 - 19 11/12
    'UB': '3141',
}
FUTPROD_COLUMNS = ['productCode', 'contractMonth', 'firstTrade', 'lastTrade', 'settlement']
# ['firstPosition', 'lastPosition', 'firstNotice', 'firstDelivery', 'lastDelivery']
def load_futures_list(code: str):
    fut_url = FUTPROD_URL.format(code=FUTPRODID_MAP[code])
    content_json = request.get_json(request.url_get(fut_url, headers=HEADERS))
    content_df = pd.DataFrame(content_json)[FUTPROD_COLUMNS]
    content_df.set_index(FUTPROD_COLUMNS[0], inplace=True)
    for col in FUTPROD_COLUMNS[2:]:
        content_df[col] = pd.to_datetime(content_df[col], format='%d %b %Y')
    filename = io.get_path(code, format='csv')
    content_df.to_csv(filename, date_format=DATE_FORMAT)
    logger.info(f"Saved {filename}")
    
    return content_df

FUT_DATA_DATES_URL = 'https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/TradeDate/{code}'
def load_fut_data_dates(code: str = 'SR1') -> list[dtm.date]:
    fut_settle_dates_url = FUT_DATA_DATES_URL.format(code=FUTPRODID_MAP[code])
    content_json = request.get_json(request.url_get(fut_settle_dates_url, headers=HEADERS))
    settle_dates = []
    for dr in content_json:
        settle_dates.append(dtm.datetime.strptime(dr[0], DATE_FORMAT).date())
    return settle_dates

FUTPRODCODE_MAP = {
    'FF': '41',

    'ZT': '26',
    'ZF': '25',
    'ZN': '21',
    'ZB': '17',
    'UB': 'UBE',
}
FUT_SETTLE_URL = 'https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/{code}/FUT?tradeDate={date}'
def load_fut_settle_prices(code: str = 'SR1', settle_date: dtm.date = None, price_params: dict = None):
    fut_data_dates = load_fut_data_dates(code=code)
    if not settle_date:
        settle_date = fut_data_dates[0]
    elif settle_date > fut_data_dates[0]:
        return load_fut_quotes(code, price_params=price_params)
    elif settle_date not in fut_data_dates:
        raise Exception(f"No futures settlement prices found for date {settle_date}")
    fut_settle_url = FUT_SETTLE_URL.format(code=FUTPRODID_MAP[code], date=settle_date.strftime(DATE_FORMAT))
    content_json = request.get_json(request.url_get(fut_settle_url, headers=HEADERS))
    # settle_date = content_json["tradeDate"]
    settlements = content_json["settlements"]
    res: dict[str, float] = {}
    for fut_r in settlements:
        settle_price = get_field(fut_r, DataPointType.SETTLE, price_params)
        oi, volume = get_field(fut_r, DataPointType.PREV_OI), get_field(fut_r, DataPointType.VOLUME)
        if oi > 0 and volume > 0 and settle_price:
            month_strs = fut_r['month'].split(' ')
            contract_code = FUTPRODCODE_MAP.get(code, code) + get_month_code(month_strs[0]) + month_strs[1]
            res[contract_code] = settle_price
    return (settle_date, res)

# https://www.cmegroup.com/CmeWS/mvc/Quotes/ContractsByNumber?productIds=8463&contractsNumber=100&venue=G
FUT_QUOTES_URL = 'https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/{code}/G'
def load_fut_quotes(code: str = 'SR1', price_params: dict = None):
    fut_url = FUT_QUOTES_URL.format(code=FUTPRODID_MAP[code])
    content_json = request.get_json(request.url_get(fut_url, headers=HEADERS))
    trade_date = dtm.datetime.strptime(content_json["tradeDate"], '%d %b %Y').date()
    quotes = content_json["quotes"]
    res: dict[str, float] = {}
    for quote_i in quotes:
        settle_price = quote_i['last'] # ['priorSettle']
        if is_valid_price(settle_price):
            settle_price = transform_quote(settle_price, price_params)
            expiry_code, expiry_month = quote_i['expirationCode'], quote_i['expirationDate']
            contract_month = FUTPRODCODE_MAP.get(code, code) + f"{expiry_code[0]}{expiry_month[2:4]}"
            if settle_price > 0:
                res[contract_month] = settle_price
    return (trade_date, res)

SWAP_URL = 'https://www.cmegroup.com/services/sofr-strip-rates/'
SWAP_DATE_FORMAT = '%Y%m%d'
SWAP_MAP = {
    'SOFR': "sofrRates",
    'SOFR_FF': "sofrFedFundRates",
}
def load_swap_data(fixing_type: str = 'SOFR') -> dict[dtm.date, dict[str, float]]:
    content_json = request.get_json(request.url_get(SWAP_URL, headers=HEADERS))
    curves = content_json["resultsCurve"]
    res = {}
    for curve_i in curves:
        curve_dt = dtm.datetime.strptime(curve_i["date"], SWAP_DATE_FORMAT).date()
        res[curve_dt] = {tr["term"]: float(tr["price"]) for tr in curve_i["rates"][SWAP_MAP[fixing_type]]}
    return res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CME data scraper')
    parser.add_argument('--futures', default='SR1,FF')
    args = parser.parse_args()
    print(args)
    for fut in args.futures.split(','):
        load_futures_list(fut)
    # load_swap_data()
    # op = load_prices_ftp()
    # for key, val in op.items():
    #     for key2, val2 in val.items():
    #         print(key, key2, val2)

# import urllib.request as urlreq
# FTP_URL = 'ftp://ftp.cmegroup.com/pub/settle/stlint_v2'
# # ['MONTH','OPEN','HIGH','LOW','LAST','SETT','CHGE','EST.VOL','P_SETT','P_VOL','P_INT']
# COLUMNS_TO_READ = ['MONTH','OPEN','HIGH','LOW','LAST','SETT','CHGE']
# PRICE_MAP = {
#     'SOFR': 'SOFR Futures',
#     'FF': 'Federal Fund Futures',
# }
# # Inspired by https://gist.github.com/tristanwietsma/5486236
# def load_prices_ftp(contract_type: str = 'SOFR Futures'):
#     with urlreq.urlopen(FTP_URL, timeout=request.TIMEOUT_SECS) as u:
#         lines = u.readlines()
#         if lines[0]:
#             li = lines[0].strip()
#             logger.info(li)
#             lines.pop(0)
#             header = li.decode(ENCODE_FORMAT).split()
#             price_date = dtm.datetime.strptime(header[5], DATE_FORMAT).date()
    
#     res: dict[str, dict[str, float]] = {}
#     key = None
#     contract_suffix = PRICE_MAP[contract_type].encode(ENCODE_FORMAT)
#     for li in lines:
#         li = li.strip()
#         if not li:
#             key = None
#             continue
#         if li.endswith(contract_suffix):
#             desc = li.decode(ENCODE_FORMAT).split()
#             logger.info(f"Adding {' '.join(desc[1:])}")
#             key = desc[0]
#             if key in res:
#                 raise Exception(f'Found duplciate key for {key}')
#             res[key] = {}
#             continue
#         if key:
#             cells = li.decode(ENCODE_FORMAT).split()
#             if cells[0] == 'TOTAL':
#                 key = None
#                 continue
#             if len(cells) < len(COLUMNS_TO_READ):
#                 raise Exception(f'Invalid data for {key}')
#             cells = cells[:len(COLUMNS_TO_READ)]
#             try:
#                 contract_month = get_month_code(cells[0][:3]) + cells[0][3:]
#                 settle_price = float(cells[-2])
#             except:
#                 key = None
#                 continue
#             res[key][contract_month] = settle_price
#     return (price_date, res)
