
import datetime as dtm
import logging

from common import request_web as request

logger = logging.Logger(__name__)

DATA_URL = 'https://iftp.chinamoney.com.cn/r/cms/www/chinamoney/data/'
FX_SWAPS_EP = 'fx/fx-sw-curv-USD.CNY.json'
DATE_FORMAT = '%Y-%m-%d'
def load_fx() -> tuple[dtm.date, list[tuple[str, float, dtm.date]]]:
    content_json = request.get_json(request.url_get(DATA_URL + FX_SWAPS_EP))
    content_data = content_json["data"]
    tenors = content_data["voArray"]
    data_date = dtm.datetime.strptime(content_data["showDateCN"], DATE_FORMAT).date()
    res = []
    for tenor_i in tenors:
        tenor = tenor_i["tenor"]
        tenor_dt = dtm.datetime.strptime(tenor_i["valueDate"], DATE_FORMAT).date()
        tenor_points = float(tenor_i["points"])
        res.append((tenor, tenor_points, tenor_dt))
        if tenor == '1M':
            implied_spot = float(tenor_i['swapAllPrc']) - tenor_points / 10000
    return (data_date, implied_spot, res)

SPOT_EP = 'fx/ccpr.json'
def load_spot() -> dict[str, tuple[str, float]]:
    content_json = request.get_json(request.url_get(DATA_URL + SPOT_EP))
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['foreignCName']] = (rec['vrtEName'], float(rec['price']))
    return res

SNAP_URL = 'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-'
SNAP_HEADERS = {'User-Agent': 'Mozilla'}
SWAPS_EP = 'shibor/Ifcc'
SWAPS_CODEMAP = {
    'Shibor3M': 71,
    'FR007': 72,
}
def url_get_retry(url: str, params: dict[str, str]):
    while True:
        try:
            return request.url_get(url, params=params, headers=SNAP_HEADERS)
        except Exception as ex:
            # Open https://www.chinamoney.com.cn/english/bmkycvfcc/ in your web browser and continue
            logger.warning(f'Exception: {ex}')

def load_swaps(fixing_type: str = 'FR007') -> tuple[dtm.date, dict[str, float]]:
    content = url_get_retry(SNAP_URL + SWAPS_EP, params={'cfgItemType': SWAPS_CODEMAP[fixing_type]})
    content_json = request.get_json(content)
    content_metadata = content_json["data"]
    data_date = dtm.datetime.strptime(content_metadata["showDateCN"], DATE_FORMAT).date()
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['tl']] = float(rec['optimalAvg'])
    return (data_date, res)

FIXINGS_EP = {
    'FR': 'currency/frr.json',
    'Shibor': 'shibor/shibor.json',
}
FIXINGS_DATE_FORMAT = '%Y-%m-%d %H:%M'
def load_fixings(fix_name: str) -> tuple[dtm.date, dict[str, float]]:
    if fix_name == 'FR':
        code_name = 'productCode'
        value_name = 'value'
    elif fix_name == 'Shibor':
        code_name = 'termCode'
        value_name = 'shibor'
    content_json = request.get_json(request.url_post(DATA_URL + FIXINGS_EP[fix_name]))
    content_metadata = content_json["data"]
    data_date = dtm.datetime.strptime(content_metadata["showDateCN"], FIXINGS_DATE_FORMAT).date()
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec[code_name]] = float(rec[value_name])
    return (data_date, res)

FXVOL_EP = 'fx/FoivltltyCurv'
def load_fxvol() -> tuple[dtm.date, dict[str, dict[str, float]]]:
    res = {}
    # '4', '3', '2', '1',
    for vol_id in ['0', '7', '8', '9', 'a']:
        content = url_get_retry(SNAP_URL + FXVOL_EP, params={'volatilitySurface': vol_id})
        content_json = request.get_json(content)
        content_metadata = content_json["data"]
        data_date = dtm.datetime.strptime(content_metadata["ccyDate"], DATE_FORMAT).date()
        content_data = content_json["records"]
        for rec in content_data:
            vtype = rec['volatilityType']
            if vtype == 'ATM':
                d_key = (vtype, None)
            else:
                delta, quote_type = vtype.split(' ')
                d_key = (int(delta[:-1]) / 100, quote_type)
            tenor = rec['tenor']
            if tenor not in res:
                res[tenor] = {}
            spread = float(rec['askVolatilityStr']) - float(rec['bidVolatilityStr'])
            res[tenor][d_key] = float(rec['midVolatilityStr']), spread
    return data_date, res
