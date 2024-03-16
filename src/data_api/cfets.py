
import datetime as dtm
import logging

from common import request_web as request

logger = logging.Logger(__name__)

CFETS_FX_URL = 'https://iftp.chinamoney.com.cn/r/cms/www/chinamoney/data/fx/fx-sw-curv-USD.CNY.json'
CFETS_DATE_FORMAT = '%Y-%m-%d'
def load_fx() -> tuple[dtm.date, list[tuple[str, float, dtm.date]]]:
    content_json = request.get_json(request.url_get(CFETS_FX_URL))
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
def load_spot() -> dict[str, tuple[str, float]]:
    content_json = request.get_json(request.url_get(CFETS_SPOT_URL))
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['foreignCName']] = (rec['vrtEName'], float(rec['price']))
    return res

CFETS_SWAPS_URL = 'https://www.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/Ifcc'
# CFETS_SWAPS_URL = 'https://iftp.chinamoney.com.cn/ags/ms/cm-u-bk-shibor/Ifcc'
CFETS_SWAPS_CODEMAP = {
    'Shibor3M': 71,
    'FR007': 72,
}
def load_swaps(fixing_type: str = 'FR007') -> tuple[dtm.date, dict[str, float]]:
    while (True):
        try:
            content = request.url_get(CFETS_SWAPS_URL,
                                      params={'cfgItemType': CFETS_SWAPS_CODEMAP[fixing_type]},
                                      headers={'User-Agent': 'Mozilla'})
            break
        except:
            # Open https://www.chinamoney.com.cn/english/bmkycvfcc/ in your web browser and continue
            pass
    content_json = request.get_json(content)
    content_metadata = content_json["data"]
    data_date = dtm.datetime.strptime(content_metadata["showDateCN"], CFETS_DATE_FORMAT).date()
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec['tl']] = float(rec['optimalAvg'])
    return (data_date, res)

CFETS_FIXINGS_URL = 'https://iftp.chinamoney.com.cn/r/cms/www/chinamoney/data/'
CFETS_FIXINGS_FR_EP = 'currency/frr.json'
CFETS_FIXINGS_SH_EP = 'shibor/shibor.json'
CFETS_FIXINGS_DATE_FORMAT = '%Y-%m-%d %H:%M'
def load_fixings(fix_name: str) -> tuple[dtm.date, dict[str, float]]:
    fix_url = CFETS_FIXINGS_URL
    if fix_name == 'FR':
        code_name = 'productCode'
        value_name = 'value'
        fix_url += CFETS_FIXINGS_FR_EP
    elif fix_name == 'Shibor':
        code_name = 'termCode'
        value_name = 'shibor'
        fix_url += CFETS_FIXINGS_SH_EP
    content_json = request.get_json(request.url_post(fix_url))
    content_metadata = content_json["data"]
    data_date = dtm.datetime.strptime(content_metadata["showDateCN"], CFETS_FIXINGS_DATE_FORMAT).date()
    content_data = content_json["records"]
    res = {}
    for rec in content_data:
        res[rec[code_name]] = float(rec[value_name])
    return (data_date, res)
