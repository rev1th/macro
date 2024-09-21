import datetime as dtm
import logging
import argparse

from common import request_web as request
from common.models.data import DataPointType, OptionDataFlag
from common import sql
from data_api.config import META_DB, PRICES_DB

logger = logging.Logger(__name__)

# month codes
MONTH_CODES = 'FGHJKMNQUVXZ'
MONTH_NAMES = [dtm.date(2023, m+1, 1).strftime('%b').upper() for m in range(12)]
MONTH_MAP = dict(zip(MONTH_NAMES, MONTH_CODES))
MONTH_MAP['JLY'] = MONTH_MAP['JUL']

DATE_FORMAT = "%m/%d/%Y"
ENCODE_FORMAT = 'utf-8'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
    'Accept-Language': 'en',
    'Cookie': "",
}

def get_month_code(month: str) -> str:
    return MONTH_MAP[month]

def is_valid_price(price: str):
    return price != '-' and price[-1] not in ('A', 'B')

def str_to_num(num: str, num_type = float) -> float:
    return num_type(num.replace(',', ''))

def transform_quote(quote: str, price_params: dict = None):
    if price_params is None:
        return float(quote)
    extra_tick_count = price_params.get('extra_tick_count', None)
    quote_parts = quote.split('\'')
    if len(quote_parts) != 2 or len(quote_parts[1]) != (3 if extra_tick_count else 2):
        raise RuntimeError(f'Invalid quote format {quote}')
    quote_p1, quote_p2 = quote_parts
    quote_3 = (float(quote_p2[2]) / extra_tick_count) if extra_tick_count else 0
    quote_1 = float(quote_p1) if quote_p1 else 0
    return quote_1 + (float(quote_p2[:2]) + quote_3) / price_params.get('tick_count', 32)

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

HOME_URL = 'https://www.cmegroup.com/CmeWS/mvc/'
FUT_PROD_EP = 'ProductCalendar/Future/{code}'
OPT_PROD_EP = 'ProductCalendar/Options/{code}'
FUT_PRODID_MAP = {
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
FUT_PRODCODE_MAP = {
    'FF': '41',

    'ZT': '26',
    'ZF': '25',
    'ZN': '21',
    'ZB': '17',
    'UB': 'UBE',
}

FUT_TABLE = 'futures'
RATE_FUT_PROD_TABLE = 'rate_futures_contracts'
BOND_FUT_PROD_TABLE = 'bond_futures_contracts'
OPT_PROD_TABLE = 'options_contracts'
FUTPROD_DATE_FORMAT = '%d %b %Y'

def update_futures_list(series: str):
    fut_url = f'{HOME_URL}{FUT_PROD_EP}'.format(code=FUT_PRODID_MAP[series])
    content_json = request.get_json(request.url_get(fut_url, headers=HEADERS))
    insert_rows = []
    for row in content_json:
        prod_code = row['productCode']
        if series in FUT_PRODCODE_MAP:
            assert prod_code.startswith(FUT_PRODCODE_MAP[series]), f'Invalid product code {prod_code}'
            prod_code = prod_code.replace(FUT_PRODCODE_MAP[series], series, 1)
        insert_rows.append("\n("\
    f"'{prod_code}', '{series}', '{row['contractMonth']}', "\
    f"'{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['settlement'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}')")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {RATE_FUT_PROD_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return False

def update_bond_futures_list(series: str):
    fut_url = f'{HOME_URL}{FUT_PROD_EP}'.format(code=FUT_PRODID_MAP[series])
    content_json = request.get_json(request.url_get(fut_url, headers=HEADERS))
    insert_rows = []
    for row in content_json:
        prod_code = row['productCode']
        if series in FUT_PRODCODE_MAP:
            assert prod_code.startswith(FUT_PRODCODE_MAP[series]), f'Invalid product code {prod_code}'
            prod_code = prod_code.replace(FUT_PRODCODE_MAP[series], series, 1)
        insert_rows.append("\n("\
    f"'{prod_code}', '{series}', '{row['contractMonth']}', "\
    f"'{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['firstPosition'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['lastPosition'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['firstNotice'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['firstDelivery'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['lastDelivery'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}')")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {BOND_FUT_PROD_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return False

def update_options_list(series: str):
    opt_url = f'{HOME_URL}{OPT_PROD_EP}'.format(code=FUT_PRODID_MAP[series])
    content_json = request.get_json(request.url_get(opt_url, headers=HEADERS))
    insert_rows = []
    for row in content_json[0]['calendarEntries']:
        prod_code = row['productCode']
        if series in FUT_PRODCODE_MAP:
            assert prod_code.startswith(FUT_PRODCODE_MAP[series]), f'Invalid product code {prod_code}'
            prod_code = prod_code.replace(FUT_PRODCODE_MAP[series], series, 1)
        # nearby quarterly future contracts
        pos = MONTH_CODES.find(prod_code[-3])
        fut_code = f'{prod_code[:-3]}{MONTH_CODES[int(pos/3)*3+2]}{prod_code[-2:]}'
        insert_rows.append("\n("\
    f"'{prod_code}', '{fut_code}', '{series}', '{row['contractMonth']}', "\
    f"'{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}')")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {OPT_PROD_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return False

def get_futures_contracts(series: str):
    underlier_query = f"SELECT underlier_code, lot_size FROM {FUT_TABLE} WHERE future_code='{series}'"
    underlier, lot_size = sql.fetch(underlier_query, META_DB, count=1)
    contracts_query = "SELECT contract_code, last_trade_date, settlement_date "\
    f"FROM {RATE_FUT_PROD_TABLE} WHERE series_id='{series}' ORDER BY last_trade_date"
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], dtm.datetime.strptime(row[1], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date(), underlier, lot_size)
                    for row in contracts_list]
    return contracts_fmt

def get_bond_futures_contracts(series: str):
    contracts_query = "SELECT contract_code, last_trade_date, first_delivery_date, last_delivery_date "\
    f"FROM {BOND_FUT_PROD_TABLE} WHERE series_id='{series}'"
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], dtm.datetime.strptime(row[1], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date(),
                    dtm.datetime.strptime(row[3], sql.DATE_FORMAT).date()
                    ) for row in contracts_list]
    return contracts_fmt

def get_options_contracts(series: str):
    contracts_query = "SELECT contract_code, underlier_code, last_trade_date "\
    f"FROM {OPT_PROD_TABLE} WHERE series_id='{series}' ORDER BY last_trade_date"
    contracts_list = sql.fetch(contracts_query, META_DB)
    contracts_fmt = [(row[0], row[1], dtm.datetime.strptime(row[2], sql.DATE_FORMAT).date())
                    for row in contracts_list]
    return contracts_fmt


def request_get_retry(url: str, max_tries: int = 3, **kwargs):
    try:
        return request.get_json(request.url_get(url, headers=HEADERS, **kwargs))
    except Exception as ex:
        if max_tries <= 0:
            logger.warning(f'Request error: {ex}')
        return request_get_retry(url, max_tries-1, **kwargs)

FUT_DATA_DATES_EP = 'Settlements/Futures/TradeDate/{code}'
def load_fut_data_dates(code: str = 'SR1') -> list[dtm.date]:
    fut_settle_dates_url = f'{HOME_URL}{FUT_DATA_DATES_EP}'.format(code=FUT_PRODID_MAP[code])
    content_json = request_get_retry(fut_settle_dates_url)
    settle_dates = []
    for dr in content_json:
        settle_dates.append(dtm.datetime.strptime(dr[0], DATE_FORMAT).date())
    return settle_dates

FUTURES_PRICE_TABLE = 'futures_settle'
FUT_PROD_TICKS = {
    'ZT': {'extra_tick_count': 8},
    'ZF': {'extra_tick_count': 4},
    'ZN': {'extra_tick_count': 2},
    'TN': {'extra_tick_count': 2},
    'ZB': {},
    'UB': {},
}
FUT_SETTLE_EP = 'Settlements/Futures/Settlements/{code}/FUT'
def load_future_settle_prices(code: str, settle_date: dtm.date):
    price_params = FUT_PROD_TICKS.get(code, None)
    fut_settle_url = f'{HOME_URL}{FUT_SETTLE_EP}'.format(code=FUT_PRODID_MAP[code])
    content_json = request_get_retry(fut_settle_url, params={'tradeDate': settle_date.strftime(DATE_FORMAT)})
    # assert settle_date == content_json["tradeDate"], f"Inconsistent prices {settle_date}"
    settlements = content_json["settlements"]
    insert_rows = []
    for fut_r in settlements:
        settle_price = get_field(fut_r, DataPointType.SETTLE, price_params)
        oi, volume = get_field(fut_r, DataPointType.PREV_OI), get_field(fut_r, DataPointType.VOLUME)
        if volume > 0 and settle_price:
            month_strs = fut_r['month'].split(' ')
            contract_code = f'{code}{get_month_code(month_strs[0])}{month_strs[1]}'
            insert_rows.append("\n("\
    f"'{contract_code}', '{settle_date.strftime(sql.DATE_FORMAT)}', {settle_price}, {volume}, {oi})")
    if insert_rows:
        insert_query = f"INSERT INTO {FUTURES_PRICE_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, PRICES_DB)
    return False

FUT_OI_MIN_MAX = 0.01
def get_future_settle_prices(code: str, settle_date: dtm.date):
    price_query = f"SELECT contract_code, close_price, open_interest FROM {FUTURES_PRICE_TABLE} "\
    f"WHERE contract_code LIKE '{code}%' AND date='{settle_date.strftime(sql.DATE_FORMAT)}'"
    prices_list = sql.fetch(price_query, PRICES_DB)
    if not prices_list:
        fut_data_dates = load_fut_data_dates(code=code)
        if settle_date > fut_data_dates[0]:
            return load_future_quotes(code)[1]
        elif settle_date in fut_data_dates:
            if not load_future_settle_prices(code, settle_date):
                raise Exception(f"Futures prices not loaded for {code} on {settle_date}")
        else:
            raise Exception(f"Futures prices not available for {code} on {settle_date}")
        prices_list = sql.fetch(price_query, PRICES_DB)
    res: dict[str, float] = {}
    max_oi = 0
    for row in prices_list:
        contract_code, settle_price, oi = row
        max_oi = max(oi, max_oi)
        if oi > max_oi * FUT_OI_MIN_MAX:
            res[contract_code] = settle_price
    return res

MIN_MAX_VOLUME = 0.001
# Quotes/ContractsByNumber?productIds=8463&contractsNumber=100&venue=G
FUT_QUOTES_EP = 'Quotes/Future/{code}/G'
def load_future_quotes(code: str):
    price_params = FUT_PROD_TICKS.get(code, None)
    fut_url = f'{HOME_URL}{FUT_QUOTES_EP}'.format(code=FUT_PRODID_MAP[code])
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
                insert_rows.append("\n("\
    f"'{code}', '{tr['term']}', '{curve_dt.strftime(sql.DATE_FORMAT)}', {float(tr['price'])})")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {SWAP_RATES_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, PRICES_DB)
    return False

def get_swap_data(code: str, date: dtm.date) -> dict[str, float]:
    rates_query = f"SELECT term, rate FROM {SWAP_RATES_TABLE} "\
    f"WHERE code='{code}' AND date='{date.strftime(sql.DATE_FORMAT)}'"
    rates_list = sql.fetch(rates_query, PRICES_DB)
    if not rates_list:
        if not load_swap_data():
            raise Exception(f"Swap data not loaded for {code}")
        rates_list = sql.fetch(rates_query, PRICES_DB)
    return dict(rates_list)

OPT_PRODID_MAP = {
    'SR3': 8849,
}
OPT_SETTLE_EP = 'Settlements/Options/Settlements/{code}/OOF'
OPT_PROD_TICKS = {
    'ZT': {'tick_count': 64, 'extra_tick_count': 2},
    'ZF': {'tick_count': 64, 'extra_tick_count': 2},
    'ZN': {'tick_count': 64},
    'ZB': {'tick_count': 64},
}
OPT_OI_MIN_MAX = 0.01
def get_option_settle_prices(series: str, contract_codes: list[str], date: dtm.date):
    opt_settle_url = f'{HOME_URL}{OPT_SETTLE_EP}'.format(code=FUT_PRODID_MAP[series])
    url_params = {'tradeDate': date.strftime(DATE_FORMAT)}
    price_params = OPT_PROD_TICKS.get(series, None)
    # insert_rows = []
    res: dict[str, dict[float, dict[str, tuple[float, float]]]] = {}
    max_oi = 0
    for contract_code in contract_codes:
        contract_res = {}
        if series in FUT_PRODCODE_MAP:
            product_code = contract_code.replace(series, FUT_PRODCODE_MAP[series], 1)
        else:
            product_code = contract_code
        url_params.update({'monthYear': product_code})
        content_json = request_get_retry(opt_settle_url, params=url_params)
        settlements = content_json["settlements"]
        for opt_r in settlements:
            if opt_r['strike'] == 'Total':
                continue
            settle_price = get_field(opt_r, DataPointType.SETTLE, price_params)
            oi, volume = get_field(opt_r, DataPointType.PREV_OI), get_field(opt_r, DataPointType.VOLUME)
            max_oi = max(oi, max_oi)
            strike = str_to_num(opt_r['strike'])
            opt_t = opt_r['type']
            if volume > 0 and settle_price and oi > max_oi * OPT_OI_MIN_MAX:
                if strike not in contract_res:
                    contract_res[strike] = {}
                if opt_t == 'Call':
                    contract_res[strike][OptionDataFlag.CALL] = (settle_price, volume)
                elif opt_t == 'Put':
                    contract_res[strike][OptionDataFlag.PUT] = (settle_price, volume)
        res[contract_code] = contract_res
    #             insert_rows.append("\n("\
    # f"('{contract_code}', {strike}, '{opt_t}', '{date.strftime(sql.DATE_FORMAT)}', {settle_price}, {volume}, {oi})")
    return res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CME data scraper')
    parser.add_argument('--rate_futures', default='SR1')
    parser.add_argument('--bond_futures', default='')
    args = parser.parse_args()
    logger.error(args)
    if args.rate_futures:
        for code in args.rate_futures.split(','):
            update_futures_list(code)
    if args.bond_futures:
        for code in args.bond_futures.split(','):
            update_bond_futures_list(code)
    # for fut in BOND_OPT_PRODS:
    #     update_options_list(fut)

# create_query = f"""CREATE TABLE {FUT_TABLE} (
#     future_code TEXT, underlier_code TEXT,
#     CONSTRAINT {FUT_TABLE}_pk PRIMARY KEY (future_code)
# )"""
# sql.modify(create_query)
# for row in [('SR1', 'SOFR'), ('SR3', 'SOFR'), ('FF', 'EFFR')]:
#     insert_query = f"INSERT INTO {FUT_TABLE} VALUES ('{row[0]}', '{row[1]}')"
#     sql.modify(insert_query)

# create_query = f"""CREATE TABLE {RATE_FUT_PROD_TABLE} (
#     contract_code TEXT, series_id TEXT, contract_month TEXT,
#     first_trade_date TEXT, last_trade_date TEXT, settlement_date TEXT,
#     CONSTRAINT {RATE_FUT_PROD_TABLE}_pk PRIMARY KEY (contract_code)
# )"""
# sql.modify(create_query)

# create_query = f"""CREATE TABLE {BOND_FUT_PROD_TABLE} (
#     contract_code TEXT, series_id TEXT, contract_month TEXT,
#     first_trade_date TEXT, last_trade_date TEXT,
#     first_position_date TEXT, last_position_date TEXT, first_notice_date TEXT,
#     first_delivery_date TEXT, last_delivery_date TEXT,
#     CONSTRAINT {BOND_FUT_PROD_TABLE}_pk PRIMARY KEY (contract_code)
# )"""
# sql.modify(create_query)

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

# create_query = f"""CREATE TABLE {OPT_PROD_TABLE} (
#     contract_code TEXT, underlier_code TEXT, series_id TEXT, contract_month TEXT,
#     first_trade_date TEXT, last_trade_date TEXT,
#     CONSTRAINT {OPT_PROD_TABLE}_pk PRIMARY KEY (contract_code)
# )"""
# sql.modify(create_query, META_DB)
