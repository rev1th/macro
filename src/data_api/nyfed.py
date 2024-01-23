
import datetime as dtm
import argparse
import logging

from common import request_web as request, io

logger = logging.Logger(__name__)

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
    content = request.url_get(NYFED_URL, params=params)

    if save:
        filename = io.get_path(code, format='csv')
        # os.rename(filename, filename + '.bkp')
        with open(filename, 'w') as f:
            f.write(content)
        logger.info(f"Saved {filename}")
    
    return [r.split(',') for r in content.split('\n')]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='NYFED data scraper')
    parser.add_argument('-f', '--fixings', default='SOFR,EFFR')
    args = parser.parse_args()
    print(args)
    for fix in args.fixings.split(','):
        load_fed_data(fix, save=True)
