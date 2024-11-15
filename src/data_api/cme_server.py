import datetime as dtm
import logging
import argparse

from common import request_web as request
from common.models.market_data import MarketDataType, OptionDataFlag
from common import sql
from data_api.db_config import META_DB, PRICES_DB
from data_api.cme_config import *

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

def get_field(data_dict: dict[str, any], data_field: MarketDataType, params: dict = None):
    match data_field:
        case MarketDataType.LAST:
            return transform_quote(data_dict['last'], params) if is_valid_price(data_dict['last']) else None
        case MarketDataType.SETTLE:
            return transform_quote(data_dict['settle'], params) if is_valid_price(data_dict['settle']) else None
        case MarketDataType.VOLUME:
            return str_to_num(data_dict['volume'], int) if data_dict['volume'] else None
        case MarketDataType.PREV_OI:
            return str_to_num(data_dict['openInterest'], int) if data_dict['openInterest'] else None
        case _:
            logger.error(f'Unhandled {data_field}')

HOME_URL = 'https://www.cmegroup.com/CmeWS/mvc/'
FUT_PROD_EP = 'ProductCalendar/Future/{code}'
OPT_PROD_EP = 'ProductCalendar/Options/{code}'
FUT_PROD_URL_MAP = {
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
FUT_PROD_CODE_MAP = {
    'FF': '41',

    'ZT': '26',
    'ZF': '25',
    'ZN': '21',
    'ZB': '17',
    'UB': 'UBE',
}
FUTPROD_DATE_FORMAT = '%d %b %Y'

def update_futures_list(series: str):
    fut_prod_url = f'{HOME_URL}{FUT_PROD_EP}'.format(code=FUT_PROD_URL_MAP[series])
    content_json = request.get_json(request.url_get(fut_prod_url, headers=HEADERS))
    insert_rows = []
    product_id = FUT_PROD_CODE_MAP.get(series, series)
    for row in content_json:
        product_code = row['productCode']
        assert product_code.startswith(product_id), f'Invalid product code {product_code}'
        contract_code = product_code.replace(product_id, series, 1)
        insert_rows.append("\n("\
    f"'{contract_code}', '{series}', '{row['contractMonth']}', "\
    f"'{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{dtm.datetime.strptime(row['settlement'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}')")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {RATE_FUT_PROD_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return False

def update_bond_futures_list(series: str):
    fut_prod_url = f'{HOME_URL}{FUT_PROD_EP}'.format(code=FUT_PROD_URL_MAP[series])
    content_json = request.get_json(request.url_get(fut_prod_url, headers=HEADERS))
    insert_rows = []
    product_id = FUT_PROD_CODE_MAP.get(series, series)
    for row in content_json:
        product_code = row['productCode']
        assert product_code.startswith(product_id), f'Invalid product code {product_code}'
        contract_code = product_code.replace(product_id, series, 1)
        insert_rows.append("\n("\
    f"'{contract_code}', '{series}', '{row['contractMonth']}', "\
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

OPT_PROD_CODE_MAP = {
    'SR3': {
    },
    'ZT': {
        'AME': '26',
        'MW1': 'VT',
        'WD1': 'WT',
        'E21': 'TW',
    },
    'ZF': {
        'AME': '25',
        'MW1': 'VF',
        'WD1': 'WF',
        'E21': 'FV',
    },
    'ZN': {
        'AME': '21',
        'MW1': 'VY',
        'WD1': 'WY',
        'E21': 'TY',
    },
    'ZB': {
        'AME': '17',
        'MW1': 'VB',
        'WD1': 'WB',
        'E21': 'US',
    },
}
OPT_TYPE_CODE_MAP = {
    'MW1': 'M',
    'WD1': 'W',
    'E21': 'F',
}
def update_options_list(series: str):
    opt_prod_url = f'{HOME_URL}{OPT_PROD_EP}'.format(code=FUT_PROD_URL_MAP[series])
    content_json = request.get_json(request.url_get(opt_prod_url, headers=HEADERS))
    prod_code_map = OPT_PROD_CODE_MAP[series]
    insert_rows = []
    option_expiries = {}
    for series_info in content_json:
        option_type = series_info['optionType']
        option_type_id = OPT_TYPE_CODE_MAP.get(option_type, '')
        product_id = prod_code_map.get(option_type, series)
        for row in series_info['calendarEntries']:
            product_code = row['productCode']
            assert product_code.startswith(product_id), f'Invalid product code {product_code}'
            contract_code = product_code.replace(product_id, f'{series}{option_type_id}', 1)
            last_trade_date = dtm.datetime.strptime(row['lastTrade'], FUTPROD_DATE_FORMAT)
            if not option_type_id:
                # nearby quarterly future contracts
                month_id = MONTH_CODES.find(contract_code[-3])
                quarterly_code = MONTH_CODES[int(month_id/3)*3+2]
                future_code = f'{series}{quarterly_code}{contract_code[-2:]}'
                option_expiries[future_code] = last_trade_date
            else:
                for future_code, expiry in option_expiries.items():
                    if expiry > last_trade_date:
                        break
            insert_rows.append("\n("\
    f"'{contract_code}', '{future_code}', '{series}', '{row['contractMonth']}', "\
    f"'{dtm.datetime.strptime(row['firstTrade'], FUTPROD_DATE_FORMAT).strftime(sql.DATE_FORMAT)}', "\
    f"'{last_trade_date.strftime(sql.DATE_FORMAT)}')")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {OPT_PROD_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, META_DB)
    return False


def request_get_retry(url: str, max_tries: int = 3, **kwargs):
    try:
        return request.get_json(request.url_get(url, headers=HEADERS, **kwargs))
    except Exception as ex:
        if max_tries <= 0:
            logger.warning(f'Exception: {ex}')
        return request_get_retry(url, max_tries-1, **kwargs)

FUT_DATA_DATES_EP = 'Settlements/Futures/TradeDate/{code}'
def load_future_data_dates(code: str = 'SR1') -> list[dtm.date]:
    fut_settle_dates_url = f'{HOME_URL}{FUT_DATA_DATES_EP}'.format(code=FUT_PROD_URL_MAP[code])
    content_json = request_get_retry(fut_settle_dates_url)
    settle_dates = []
    for dr in content_json:
        settle_dates.append(dtm.datetime.strptime(dr[0], DATE_FORMAT).date())
    return settle_dates

FUT_PROD_TICKS = {
    'ZT': {'extra_tick_count': 8},
    'ZF': {'extra_tick_count': 4},
    'ZN': {'extra_tick_count': 2},
    'TN': {'extra_tick_count': 2},
    'ZB': {},
    'UB': {},
}
FUT_SETTLE_EP = 'Settlements/Futures/Settlements/{code}/FUT'
def load_future_settle_prices(series: str, settle_date: dtm.date):
    price_params = FUT_PROD_TICKS.get(series, None)
    fut_settle_url = f'{HOME_URL}{FUT_SETTLE_EP}'.format(code=FUT_PROD_URL_MAP[series])
    content_json = request_get_retry(fut_settle_url, params={'tradeDate': settle_date.strftime(DATE_FORMAT)})
    # assert settle_date == content_json["tradeDate"], f"Inconsistent prices {settle_date}"
    settlements = content_json["settlements"]
    insert_rows = []
    for fut_r in settlements:
        settle_price = get_field(fut_r, MarketDataType.SETTLE, price_params)
        oi, volume = get_field(fut_r, MarketDataType.PREV_OI), get_field(fut_r, MarketDataType.VOLUME)
        if volume > 0 and settle_price:
            month_strs = fut_r['month'].split(' ')
            contract_code = f'{series}{get_month_code(month_strs[0])}{month_strs[1]}'
            insert_rows.append("\n("\
    f"'{contract_code}', '{settle_date.strftime(sql.DATE_FORMAT)}', {settle_price}, {volume}, {oi})")
    if insert_rows:
        insert_query = f"INSERT INTO {FUTURES_PRICE_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, PRICES_DB)
    return False

FUT_QUOTES_EP = 'quotes/v2/{code}' # 'Quotes/Future/{code}/G'
def load_future_quotes(series: str):
    price_params = FUT_PROD_TICKS.get(series, None)
    fut_url = f'{HOME_URL}{FUT_QUOTES_EP}'.format(code=FUT_PROD_URL_MAP[series])
    content_json = request_get_retry(fut_url)
    trade_date = dtm.datetime.strptime(content_json["tradeDate"], '%d %b %Y').date()
    quotes = content_json["quotes"]
    res: dict[str, float] = {}
    max_volume = 0
    for quote_i in quotes:
        settle_price = quote_i['last'] # ['priorSettle']
        volume = get_field(quote_i, MarketDataType.VOLUME)
        max_volume = max(volume, max_volume)
        if is_valid_price(settle_price):
            settle_price = transform_quote(settle_price, price_params)
            expiry_code, expiry_month = quote_i['expirationCode'], quote_i['expirationDate']
            contract_month = f"{series}{expiry_code[0]}{expiry_month[2:4]}"
            if volume > max_volume * FUT_VOLUME_MIN_MAX and settle_price > 0:
                res[contract_month] = settle_price
    return (trade_date, res)

SWAP_URL = 'https://www.cmegroup.com/services/sofr-strip-rates/'
SWAP_DATE_FORMAT = '%Y%m%d'
SWAP_MAP = {
    'USD_SOFR': "sofrRates",
    'USD_FF_SOFR': "sofrFedFundRates",
}
def load_swap_data(date: dtm.date):
    content_json = request_get_retry(SWAP_URL)
    curves = content_json["resultsCurve"]
    insert_rows = []
    for curve_i in curves:
        curve_dt = dtm.datetime.strptime(curve_i["date"], SWAP_DATE_FORMAT).date()
        if curve_dt < date:
            continue
        for code, fixing_type in SWAP_MAP.items():
            for tr in curve_i["rates"][fixing_type]:
                insert_rows.append("\n("\
    f"'{code}', '{tr['term']}', '{curve_dt.strftime(sql.DATE_FORMAT)}', {float(tr['price'])})")
    if insert_rows:
        insert_query = f"INSERT OR IGNORE INTO {SWAP_RATES_TABLE} VALUES {','.join(insert_rows)};"
        return sql.modify(insert_query, PRICES_DB)
    return False

OPT_PROD_URL_MAP = {
    'SR3': 8849,
}
OPT_META_DATA_EP = 'Settlements/Options/TradeDateAndExpirations/{code}'
def load_option_meta_data(series: str) -> dict[str, list[dtm.date]]:
    opt_settle_dates_url = f'{HOME_URL}{OPT_META_DATA_EP}'.format(code=FUT_PROD_URL_MAP[series])
    content_json = request_get_retry(opt_settle_dates_url)
    prod_code_map = OPT_PROD_CODE_MAP[series]
    res = {}
    for series_info in content_json:
        option_type = series_info['optionType']
        option_type_id = OPT_TYPE_CODE_MAP.get(option_type, '')
        product_id = prod_code_map.get(option_type, series)
        expirations = series_info['expirations']
        for row in expirations:
            contract_id_ext = row['contractId']
            if not contract_id_ext.startswith(product_id):
                continue
            contract_id = contract_id_ext.replace(product_id, f'{series}{option_type_id}', 1)
            res[(contract_id_ext, contract_id)] = [dtm.datetime.strptime(
                t_d['formatedDate'], DATE_FORMAT).date() for t_d in row['tradeDates']]
    return res

OPT_SETTLE_EP = 'Settlements/Options/Settlements/{code}/OOF'
OPT_PROD_TICKS = {
    'ZT': {'tick_count': 64, 'extra_tick_count': 2},
    'ZF': {'tick_count': 64, 'extra_tick_count': 2},
    'ZN': {'tick_count': 64},
    'ZB': {'tick_count': 64},
}
def get_option_settle_prices(series: str, settle_date: dtm.date):
    opt_settle_url = f'{HOME_URL}{OPT_SETTLE_EP}'.format(code=FUT_PROD_URL_MAP[series])
    url_params = {'tradeDate': settle_date.strftime(DATE_FORMAT)}
    price_params = OPT_PROD_TICKS.get(series, None)
    opt_meta_data = load_option_meta_data(series)
    # insert_rows = []
    res: dict[str, dict[float, dict[str, tuple[float, float]]]] = {}
    max_oi = 0
    for (product_code, contract_id), trade_dates in opt_meta_data.items():
        if settle_date < trade_dates[-1]:
            raise ValueError(f"Option prices not available for {series} on {settle_date}")
        elif settle_date > trade_dates[0]:
            continue # most probably an expired contract
        contract_res = {}
        url_params.update({'monthYear': product_code})
        content_json = request_get_retry(opt_settle_url, params=url_params)
        settlements = content_json["settlements"]
        for opt_r in settlements:
            if opt_r['strike'] == 'Total':
                continue
            settle_price = get_field(opt_r, MarketDataType.SETTLE, price_params)
            oi, volume = get_field(opt_r, MarketDataType.PREV_OI), get_field(opt_r, MarketDataType.VOLUME)
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
        res[contract_id] = contract_res
    #             insert_rows.append("\n("\
    # f"('{contract_code}', {strike}, '{opt_t}', '{date.strftime(sql.DATE_FORMAT)}', {settle_price}, {volume}, {oi})")
    return res


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CME data scraper')
    parser.add_argument('--rate_futures', default='SR1')
    parser.add_argument('--bond_futures', default='') # ZT,ZF,ZN,TN,ZB,UB
    parser.add_argument('--options', default='') # ZT,ZF,ZN,ZB
    args = parser.parse_args()
    logger.warning(args)
    for code in args.rate_futures.split(','):
        code = code.strip()
        if code:
            update_futures_list(code)
    for code in args.bond_futures.split(','):
        code = code.strip()
        if code:
            update_bond_futures_list(code)
    for code in args.options.split(','):
        code = code.strip()
        if code:
            update_options_list(code)

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
