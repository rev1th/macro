import datetime as dtm

from common import request_web as request
from common import sql
from data_api.db_config import PRICES_DB

NYFED_URL = 'https://markets.newyorkfed.org/read'
NYFED_URL_DATE_FORMAT = '%Y-%m-%d'
NYFED_URL_CODEMAP = {
    'SOFR': 520,
    'EFFR': 500,
}
NYFED_DATE_FORMAT = '%m/%d/%Y'
NYFED_TABLE = 'rates_fixings'

def update_fixing(code: str, from_date: dtm.date):
    if code not in NYFED_URL_CODEMAP:
        raise Exception(f'{code} not found in URL mapping')
    params = {
        'startDt': from_date.strftime(NYFED_URL_DATE_FORMAT),
        'eventCodes': NYFED_URL_CODEMAP[code],
        'productCode': 50,
        'sort': 'postDt:-1,eventCode:1',
        'format': 'csv',
    }
    content = request.url_get(NYFED_URL, params=params)
    lines = content.strip().split('\n')
    insert_rows = []
    for row in lines[1:]:
        cells = row.split(',')
        date_str, rate_type, rate = [cells[id] for id in [0, 1, 2]]
        date_sql = dtm.datetime.strptime(date_str, NYFED_DATE_FORMAT).date().strftime(sql.DATE_FORMAT)
        insert_rows.append(f"('USD', '{rate_type}', '{date_sql}', {rate})")
    if insert_rows:
        insert_query = (f"INSERT INTO {NYFED_TABLE} VALUES {','.join(insert_rows)};")
        return sql.modify(insert_query, PRICES_DB)
    else:
        return True

if __name__ == '__main__':
    for code in NYFED_URL_CODEMAP:
        if not update_fixing(code):
            raise Exception(f'Failed {code}')

# create_query = """CREATE TABLE rates_fixings (
#     currency TEXT, type TEXT, date TEXT, rate REAL,
#     CONSTRAINT rates_fixings_pk PRIMARY KEY (currency, type, date)
# )"""
# sql.modify(create_query)
