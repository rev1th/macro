
import datetime as dtm
import pandas as pd
import logging
import argparse

from common import request_web as request
from common.models.data import DataPointType
from common import sql
from data_api.config import META_DB, PRICES_DB

logger = logging.Logger(__name__)

# month codes
MONTHCODES = 'FGHJKMNQUVXZ'
MONTH_NAMES = [dtm.date(2023, m+1, 1).strftime('%b').upper() for m in range(12)]
MONTHMAP = dict(zip(MONTH_NAMES, MONTHCODES))
MONTHMAP['JLY'] = MONTHMAP['JUL']

DATE_FORMAT = "%m/%d/%Y"
ENCODE_FORMAT = 'utf-8'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept-Language': 'en',
    'Cookie': "",
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
    # 'Z3N': '2666',
    'ZF': '329',
    'ZN': '316',
    'TN': '7978',
    'ZB': '307',
    # 'TWE': '10072',
    'UB': '3141',
}
FUTPRODCODE_MAP = {
    'FF': '41',

    'ZT': '26',
    'ZF': '25',
    'ZN': '21',
    'ZB': '17',
    'UB': 'UBE',
}

FUT_TABLE = 'futures'
FUTPROD_TABLE = 'rate_futures_contracts'
BONDFUTPROD_TABLE = 'bond_futures_contracts'
FUTPROD_DATE_FORMAT = '%d %b %Y'

def update_futures_list(code: str):
    fut_url = FUTPROD_URL.format(code=FUTPRODID_MAP[code])
    content_json = request.get_json(request.url_get(fut_url, headers=HEADERS))
    content_df = pd.DataFrame(content_json)
    insert_rows = []
    for _, row in content_df.iterrows():
        prod_code = row['productCode']
        if code in FUTPRODCODE_MAP:
            assert prod_code.startswith(FUTPRODCODE_MAP[code]), f'Invalid product code {prod_code}'
            prod_code = prod_code.replace(FUTPRODCODE_MAP[code], code, 1)
        insert_rows.append(f"""(
    '{prod_code}', '{code}', '{row['contractMonth']}',
    '{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['settlement'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}'
)""")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {FUTPROD_TABLE} VALUES {', '.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return True

def update_bond_futures_list(code: str):
    fut_url = FUTPROD_URL.format(code=FUTPRODID_MAP[code])
    content_json = request.get_json(request.url_get(fut_url, headers=HEADERS))
    content_df = pd.DataFrame(content_json)
    insert_rows = []
    for _, row in content_df.iterrows():
        prod_code = row['productCode']
        if code in FUTPRODCODE_MAP:
            assert prod_code.startswith(FUTPRODCODE_MAP[code]), f'Invalid product code {prod_code}'
            prod_code = prod_code.replace(FUTPRODCODE_MAP[code], code, 1)
        insert_rows.append(f"""(
    '{prod_code}', '{code}', '{row['contractMonth']}',
    '{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['firstPosition'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['lastPosition'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['firstNotice'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['firstDelivery'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
    '{dtm.datetime.strptime(row['lastDelivery'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}'
)""")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {BONDFUTPROD_TABLE} VALUES {', '.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return True

def get_futures_contracts(code: str):
    underlier_query = f"SELECT underlier_code, lot_size FROM {FUT_TABLE} WHERE future_code='{code}'"
    underlier, lot_size = sql.fetch(underlier_query, META_DB, count=1)
    contracts_query = f"""SELECT contract_code, last_trade_date, settlement_date
    FROM {FUTPROD_TABLE} WHERE future_code='{code}'"""
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], dtm.datetime.strptime(row[1], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date(), underlier, lot_size)
                    for row in contracts_list]
    return contracts_fmt

def get_bond_futures_contracts(code: str):
    contracts_query = f"""SELECT contract_code, last_trade_date, first_delivery_date, last_delivery_date
    FROM {BONDFUTPROD_TABLE} WHERE future_code='{code}'"""
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], dtm.datetime.strptime(row[1], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[3], sql.DATE_FORMAT).date()
                    ) for row in contracts_list]
    return contracts_fmt


def request_get_retry(url: str, max_tries: int = 3):
    try:
        return request.get_json(request.url_get(url, headers=HEADERS))
    except Exception as ex:
        if max_tries <= 0:
            logger.warning(f'Request error: {ex}')
        return request_get_retry(url, max_tries-1)

FUT_DATA_DATES_URL = 'https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/TradeDate/{code}'
def load_fut_data_dates(code: str = 'SR1') -> list[dtm.date]:
    fut_settle_dates_url = FUT_DATA_DATES_URL.format(code=FUTPRODID_MAP[code])
    content_json = request_get_retry(fut_settle_dates_url)
    settle_dates = []
    for dr in content_json:
        settle_dates.append(dtm.datetime.strptime(dr[0], DATE_FORMAT).date())
    return settle_dates

FUTURES_PRICE_TABLE = 'futures_settle'
FUTPROD_TICKS = {
    'ZT': {'extra_tick_count': 8},
    'ZF': {'extra_tick_count': 4},
    'ZN': {'extra_tick_count': 2},
    'TN': {'extra_tick_count': 2},
    'ZB': {},
    'UB': {},
}
FUT_SETTLE_URL = 'https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/{code}/FUT?tradeDate={date}'
def load_future_settle_prices(code: str, settle_date: dtm.date):
    price_params = FUTPROD_TICKS.get(code, None)
    fut_settle_url = FUT_SETTLE_URL.format(code=FUTPRODID_MAP[code], date=settle_date.strftime(DATE_FORMAT))
    content_json = request_get_retry(fut_settle_url)
    # assert settle_date == content_json["tradeDate"], f"Inconsistent prices {settle_date}"
    settlements = content_json["settlements"]
    insert_rows = []
    for fut_r in settlements:
        settle_price = get_field(fut_r, DataPointType.SETTLE, price_params)
        oi, volume = get_field(fut_r, DataPointType.PREV_OI), get_field(fut_r, DataPointType.VOLUME)
        if volume > 0 and settle_price:
            month_strs = fut_r['month'].split(' ')
            contract_code = f'{code}{get_month_code(month_strs[0])}{month_strs[1]}'
            insert_rows.append(f"""
    ('{contract_code}', '{settle_date.strftime(sql.DATE_FORMAT)}', {settle_price}, {volume}, {oi})""")
    if insert_rows:
        insert_query = f"INSERT INTO {FUTURES_PRICE_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, PRICES_DB)
    else:
        return True

MIN_MAX_OI = 0.01
def get_fut_settle_prices(code: str, settle_date: dtm.date):
    price_query = f"""SELECT contract_code, close_price, open_interest FROM {FUTURES_PRICE_TABLE} 
    WHERE contract_code LIKE '{code}%' AND date='{settle_date.strftime(sql.DATE_FORMAT)}'"""
    prices_list = sql.fetch(price_query, PRICES_DB)
    if not prices_list:
        fut_data_dates = load_fut_data_dates(code=code)
        if settle_date > fut_data_dates[0]:
            return load_future_quotes(code)[1]
        elif settle_date in fut_data_dates:
            load_future_settle_prices(code, settle_date)
        else:
            raise Exception(f"No futures settlement prices found for date {settle_date}")
        prices_list = sql.fetch(price_query, PRICES_DB)
    res: dict[str, float] = {}
    max_oi = 0
    for row in prices_list:
        contract_code, settle_price, oi = row
        max_oi = max(oi, max_oi)
        if oi > max_oi * MIN_MAX_OI:
            res[contract_code] = settle_price
    return res

MIN_MAX_VOLUME = 0.001
# https://www.cmegroup.com/CmeWS/mvc/Quotes/ContractsByNumber?productIds=8463&contractsNumber=100&venue=G
FUT_QUOTES_URL = 'https://www.cmegroup.com/CmeWS/mvc/Quotes/Future/{code}/G'
def load_future_quotes(code: str):
    price_params = FUTPROD_TICKS.get(code, None)
    fut_url = FUT_QUOTES_URL.format(code=FUTPRODID_MAP[code])
    content_json = request_get_retry(fut_url)
    trade_date = dtm.datetime.strptime(content_json["tradeDate"], '%d %b %Y').date()
    quotes = content_json["quotes"]
    res: dict[str, float] = {}
    max_volume = 0
    for quote_i in quotes:
        settle_price = quote_i['last'] # ['priorSettle']
        volume = get_field(quote_i, DataPointType.VOLUME)
        max_volume = max(volume, max_volume)
        if is_valid_price(settle_price):
            settle_price = transform_quote(settle_price, price_params)
            expiry_code, expiry_month = quote_i['expirationCode'], quote_i['expirationDate']
            contract_month = f"{code}{expiry_code[0]}{expiry_month[2:4]}"
            if volume > max_volume * MIN_MAX_VOLUME and settle_price > 0:
                res[contract_month] = settle_price
    return (trade_date, res)

SWAP_URL = 'https://www.cmegroup.com/services/sofr-strip-rates/'
SWAP_DATE_FORMAT = '%Y%m%d'
SWAP_MAP = {
    'USD_SOFR': "sofrRates",
    'USD_FF_SOFR': "sofrFedFundRates",
}
SWAP_RATES_TABLE = 'swap_rates'
def load_swap_data():
    content_json = request_get_retry(SWAP_URL)
    curves = content_json["resultsCurve"]
    insert_rows = []
    for curve_i in curves:
        curve_dt = dtm.datetime.strptime(curve_i["date"], SWAP_DATE_FORMAT).date()
        for code, fixing_type in SWAP_MAP.items():
            for tr in curve_i["rates"][fixing_type]:
                insert_rows.append(f"""
    ('{code}', '{tr['term']}', '{curve_dt.strftime(sql.DATE_FORMAT)}', {float(tr['price'])})""")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {SWAP_RATES_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, PRICES_DB)
    else:
        return True

def get_swap_data(code: str, date: dtm.date) -> dict[str, float]:
    rates_query = f"""SELECT term, rate FROM {SWAP_RATES_TABLE} 
    WHERE code='{code}' AND date='{date.strftime(sql.DATE_FORMAT)}'"""
    rates_list = sql.fetch(rates_query, PRICES_DB)
    if not rates_list:
        load_swap_data()
        rates_list = sql.fetch(rates_query, PRICES_DB)
    return dict(rates_list)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CME data scraper')
    parser.add_argument('--futures', default='SR1')
    args = parser.parse_args()
    print(args)
    for fut in args.futures.split(','):
        update_futures_list(fut)

# create_query = f"""CREATE TABLE {FUT_TABLE} (
#     future_code TEXT, underlier_code TEXT,
#     CONSTRAINT {FUT_TABLE}_pk PRIMARY KEY (future_code)
# )"""
# sql.modify(create_query)
# for row in [('SR1', 'SOFR'), ('SR3', 'SOFR'), ('FF', 'EFFR')]:
#     insert_query = f"INSERT INTO {FUT_TABLE} VALUES ('{row[0]}', '{row[1]}')"
#     sql.modify(insert_query)

# create_query = f"""CREATE TABLE {FUTPROD_TABLE} (
#     contract_code TEXT, future_code TEXT, contract_month TEXT,
#     first_trade_date TEXT, last_trade_date TEXT, settlement_date TEXT,
#     CONSTRAINT {FUTPROD_TABLE}_pk PRIMARY KEY (contract_code)
# )"""
# sql.modify(create_query)
# for file in ['FF.csv', 'SR1.csv', 'SR3.csv']:
#     if file.startswith('SR'):
#         underlier = 'SOFR'
#     else:
#         underlier = 'EFFR'
#     fcode = file.split('.')[0]
#     df = pd.read_csv(f'data/{file}')
#     for _, row in df.iterrows():
#         insert_query = f"""INSERT INTO {FUTPROD_TABLE} VALUES (
#     '{row['productCode']}', '{fcode}', '{row['contractMonth']}',
#     '{dtm.datetime.strptime(row['firstTrade'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['lastTrade'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['settlement'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}'
# )"""
#         sql.modify(insert_query)

# create_query = f"""CREATE TABLE {BONDFUTPROD_TABLE} (
#     contract_code TEXT, future_code TEXT, contract_month TEXT,
#     first_trade_date TEXT, last_trade_date TEXT,
#     first_position_date TEXT, last_position_date TEXT, first_notice_date TEXT,
#     first_delivery_date TEXT, last_delivery_date TEXT,
#     CONSTRAINT {BONDFUTPROD_TABLE}_pk PRIMARY KEY (contract_code)
# )"""
# sql.modify(create_query)
# for file in ['TN.csv', 'UB.csv', 'ZB.csv', 'ZF.csv', 'ZN.csv', 'ZT.csv']:
#     fcode = file.split('.')[0]
#     df = pd.read_csv(f'data/{file}')
#     for _, row in df.iterrows():
#         insert_query = f"""INSERT INTO {BONDFUTPROD_TABLE} VALUES (
#     '{row['productCode']}', '{fcode}', '{row['contractMonth']}',
#     '{dtm.datetime.strptime(row['firstTrade'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['lastTrade'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['firstPosition'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['lastPosition'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['firstNotice'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['firstDelivery'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}',
#     '{dtm.datetime.strptime(row['lastDelivery'], DATE_FORMAT).strftime(sql.DATE_FORMAT)}'
# )"""
#         sql.modify(insert_query)

# create_query = f"""CREATE TABLE {FUTURES_PRICE_TABLE} (
#     contract_code TEXT, date TEXT, close_price REAL, volume INTEGER, open_interest INTEGER,
#     CONSTRAINT {FUTURES_PRICE_TABLE}_pk PRIMARY KEY (contract_code, date)
# )"""
# sql.modify(create_query, PRICES_DB)
# create_query = f"""CREATE TABLE {SWAP_RATES_TABLE} (
#     code TEXT, term TEXT, date TEXT, rate REAL,
#     CONSTRAINT {SWAP_RATES_TABLE}_pk PRIMARY KEY (code, term, date)
# )"""
# sql.modify(create_query, PRICES_DB)
